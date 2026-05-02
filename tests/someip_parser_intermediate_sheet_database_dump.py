import os
import pandas as pd
from signals.someip_event_parser import SomeIPEventParser
from core.logger import log

def update_eth_intermediate_sheet(arxml_path: str, excel_path: str, sheet_name: str = "E2E_ETH", json_cache: str = None):
    """
    Parses the ARXML (or loads from JSON cache) and merges the SOME/IP properties 
    into an existing Excel requirements sheet.
    """
    log.info(f"Starting SOME/IP Database Dump to Intermediate Sheet (Tab: {sheet_name})...")

    # ==========================================
    # 1. INVOKE THE PARSER (WITH CACHE SUPPORT)
    # ==========================================
    parser = SomeIPEventParser(arxml_path)
    
    # Try to load from JSON first to save time
    if json_cache and os.path.exists(json_cache):
        parser.load_from_json(json_cache)
    
    # BaseParser.to_dataframe() will now handle the logic:
    # If load_from_json worked, it uses that. If not, it triggers parse().
    df_signals = parser.to_dataframe()
    
    if df_signals.empty:
        log.error("Parsing failed or no data found. Aborting Excel update.")
        return

    # If we parsed fresh and have a cache path, save it for next time
    if json_cache and not os.path.exists(json_cache):
        parser.to_json_file(json_cache)

    # ==========================================
    # 2. LOAD EXISTING EXCEL SHEET
    # ==========================================
    if not os.path.exists(excel_path):
        log.error(f"Excel file '{excel_path}' not found.")
        return

    try:
        df_req = pd.read_excel(excel_path, sheet_name=sheet_name)
    except Exception as e:
        log.error(f"Failed to read sheet '{sheet_name}': {e}")
        return

    # ==========================================
    # 3. PREPARE KEYS FOR MATCHING (SIF + Method)
    # ==========================================
    # Clean the requirements keys
    df_req['match_sif'] = df_req['Service ID'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_req['match_method'] = df_req['Attribute value'].astype(str).str.strip().str.lower()
    
    # Clean the ARXML database keys
    df_signals['match_sif'] = df_signals['SIF'].astype(str).str.strip()
    df_signals['match_method'] = df_signals['Attribute_Value'].astype(str).str.strip().str.lower()

    # Drop duplicates to prevent row-multiplication
    df_signals_unique = df_signals.drop_duplicates(subset=['match_sif', 'match_method'])

    # Columns to pull into the sheet
    columns_to_add = [
        'match_sif', 'match_method', 'Signal_String', 'DataType', 
        'Available_States', 'Min', 'Mid', 'Max', 'Factor', 'Offset', 'Unit'
    ]

    # Clean up old ARXML columns from the Excel to prevent duplication suffixes
    existing_cols = df_req.columns.tolist()
    cols_to_drop = [c for c in columns_to_add if c in existing_cols and c not in ['match_sif', 'match_method']]
    df_req = df_req.drop(columns=cols_to_drop)

    # ==========================================
    # 4. PERFORM THE MERGE
    # ==========================================
    df_updated = pd.merge(
        df_req, 
        df_signals_unique[columns_to_add], 
        on=['match_sif', 'match_method'], 
        how='left'
    )

    # Cleanup temp match keys
    df_updated = df_updated.drop(columns=['match_sif', 'match_method'])

    # ==========================================
    # 5. WRITE BACK TO EXCEL
    # ==========================================
    log.info(f"Writing to {excel_path}...")
    try:
        with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df_updated.to_excel(writer, sheet_name=sheet_name, index=False)
        log.info("✅ SOME/IP Intermediate sheet updated successfully!")
    except Exception as e:
        log.error(f"Excel Write Error: {e}")

# ==========================================
# EXECUTION BLOCK
# ==========================================
if __name__ == "__main__":
    ARXML_FILE = "ETH_CAN.arxml"
    EXCEL_FILE = "Intermediate_Requirements.xlsx"
    CACHE_FILE = "someip_db_cache.json"
    
    update_eth_intermediate_sheet(ARXML_FILE, EXCEL_FILE, json_cache=CACHE_FILE)