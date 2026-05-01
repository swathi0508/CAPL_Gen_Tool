import os
import pandas as pd
from signals.can_parser import CANSignalParser
from core.logger import log

def update_can_intermediate_sheet(arxml_path: str, excel_path: str, sheet_name: str = "E2E_CAN", json_cache: str = None):
    """
    Parses the CAN ARXML (or loads from JSON cache) and merges topology/scaling 
    properties into the existing Excel requirements sheet.
    """
    log.info(f"Starting CAN Database Dump to Intermediate Sheet (Tab: {sheet_name})...")

    # ==========================================
    # 1. INVOKE THE PARSER (WITH CACHE SUPPORT)
    # ==========================================
    parser = CANSignalParser(arxml_path)
    
    # Try to load from JSON first to save time if cache exists
    if json_cache and os.path.exists(json_cache):
        parser.load_from_json(json_cache)
    
    # BaseParser logic: trigger parse() only if data isn't loaded/hydrated
    df_signals = parser.to_dataframe()
    
    if df_signals.empty:
        log.error("CAN Parsing failed or data is empty. Aborting Excel update.")
        return None, None

    # Save cache if we parsed fresh
    if json_cache and not os.path.exists(json_cache):
        # Note: BaseParser to_json_file can be called here
        parser.to_json_file(json_cache)

    # ==========================================
    # 2. LOAD EXISTING EXCEL SHEET
    # ==========================================
    if not os.path.exists(excel_path):
        log.error(f"Excel file '{excel_path}' not found.")
        return None, None

    try:
        df_req = pd.read_excel(excel_path, sheet_name=sheet_name)
    except Exception as e:
        log.error(f"Failed to read sheet '{sheet_name}': {e}")
        return None, None

    # ==========================================
    # 3. NORMALIZE KEYS FOR MATCHING
    # ==========================================
    req_signal_column = "Can Signal" 
    
    if req_signal_column not in df_req.columns:
        log.error(f"Column '{req_signal_column}' not found. Available: {df_req.columns.tolist()}")
        return None, None

    # Alias Map: Fixes discrepancies found in previous debug runs
    alias_map = {
        "global_brakewheeltorquerequest_v2": "global_brakewheeltorquereq_v2"
    }

    # Normalize Requirements Side
    df_req['match_key'] = df_req[req_signal_column].astype(str).str.strip().str.lower()
    df_req['match_key'] = df_req['match_key'].replace(alias_map)
    
    # Normalize Database Side
    # We use 'Signal_Name' as it's the standard column produced by BaseParser for CAN
    df_signals['match_key'] = df_signals['Signal_Name'].astype(str).str.strip().str.lower()
    df_signals['match_key'] = df_signals['match_key'].str.replace(r'^i', '', regex=True)

    # Deduplicate DB on match_key to prevent row explosion
    df_signals_unique = df_signals.drop_duplicates(subset=['match_key'])

    # Define columns to pull into Excel. 
    # Note: These column names must match what BaseParser produces (e.g., 'Cluster', 'TX_Node')
    columns_to_add = [
        'match_key', 'Signal_String', 'Cluster', 'TX_Node', 'RX_Nodes', 
        'Periodicity_ms', 'Base_Type', 'CAPL_Type', 'Unit', 
        'Resolution', 'Offset', 'Min', 'Max'
    ]

    # Clean up old columns from previous runs to prevent .x .y suffixes
    existing_cols = df_req.columns.tolist()
    cols_to_drop = [c for c in columns_to_add if c in existing_cols and c != 'match_key']
    df_req = df_req.drop(columns=cols_to_drop)

    # ==========================================
    # 4. PERFORM THE MERGE
    # ==========================================
    df_updated = pd.merge(
        df_req, 
        df_signals_unique[[c for c in columns_to_add if c in df_signals_unique.columns]], 
        on='match_key', 
        how='left'
    )

    # Tracking for statistics
    df_updated['Is_Found_In_DB'] = df_updated['Signal_String'].notna()
    df_matched = df_updated[df_updated['Is_Found_In_DB'] == True].copy()
    df_missing = df_updated[df_updated['Is_Found_In_DB'] == False].copy()

    # Drop temp columns
    df_final_save = df_updated.drop(columns=['match_key', 'Is_Found_In_DB'])

    # ==========================================
    # 5. WRITE BACK TO EXCEL
    # ==========================================
    log.info(f"Saving updated CAN data back to {excel_path}...")
    try:
        with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df_final_save.to_excel(writer, sheet_name=sheet_name, index=False)
        log.info("✅ CAN Excel update completed successfully!")
    except Exception as e:
        log.error(f"Failed to write to Excel: {e}")

    return df_matched, df_missing

# ==========================================
# EXECUTION BLOCK
# ==========================================
if __name__ == "__main__":
    ARXML_FILE = "ETH_CAN.arxml"
    EXCEL_FILE = "Intermediate_Requirements.xlsx"
    CACHE_FILE = "can_db_cache.json"
    
    df_m, df_miss = update_can_intermediate_sheet(ARXML_FILE, EXCEL_FILE, json_cache=CACHE_FILE)

    if df_m is not None:
        print("\n=== FINAL CAN VALIDATION STATISTICS ===")
        print(f"✅ Matched : {len(df_m)}")
        print(f"❌ Missing : {len(df_miss)}")
        
        if not df_miss.empty:
            print("\nTop 5 Missing:")
            print(df_miss[['REQ ID', 'Can Signal']].head(5))