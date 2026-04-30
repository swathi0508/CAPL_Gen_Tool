import os
import pandas as pd
from signals.can_parser import CANSignalParser
from core.logger import log

def update_can_intermediate_sheet(arxml_path: str, excel_path: str, sheet_name: str = "E2E_CAN"):
    """
    Parses the CAN ARXML and merges topology/scaling properties into the existing Excel sheet.
    Includes normalization for leading 'I' and specific signal abbreviations.
    """
    log.info("Starting CAN Database Dump to Intermediate Sheet...")

    # ==========================================
    # 1. INVOKE THE CAN PARSER
    # ==========================================
    parser = CANSignalParser(arxml_path)
    df_signals = parser.to_dataframe()
    
    if df_signals.empty:
        log.error("CAN Parsing failed. Aborting Excel update.")
        return None, None

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

    # Alias Map: Fixes discrepancies between Req doc and ARXML abbreviations
    alias_map = {
        "global_brakewheeltorquerequest_v2": "global_brakewheeltorquereq_v2"
    }

    # Normalize Requirements Side
    df_req['match_key'] = df_req[req_signal_column].astype(str).str.strip().str.lower()
    df_req['match_key'] = df_req['match_key'].replace(alias_map)
    
    # Normalize ARXML Database Side (Strip leading 'I' without underscore)
    df_signals['match_key'] = df_signals['Signal_Name'].astype(str).str.strip().str.lower()
    df_signals['match_key'] = df_signals['match_key'].str.replace(r'^i', '', regex=True)

    # Deduplicate DB on match_key to prevent row explosion in Excel
    df_signals_unique = df_signals.drop_duplicates(subset=['match_key'])

    # Define columns to pull into Excel
    columns_to_add = [
        'match_key', 'Signal_String', 'Cluster', 'TX_Node', 'RX_Nodes', 
        'Periodicity_ms', 'Base_Type', 'CAPL_Type', 'Unit', 
        'Resolution', 'Offset', 'Min', 'Max'
    ]

    # Clean up old columns from previous runs
    existing_cols = df_req.columns.tolist()
    cols_to_drop = [c for c in columns_to_add if c in existing_cols and c != 'match_key']
    df_req = df_req.drop(columns=cols_to_drop)

    # ==========================================
    # 4. PERFORM THE MERGE
    # ==========================================
    df_updated = pd.merge(
        df_req, 
        df_signals_unique[columns_to_add], 
        on='match_key', 
        how='left'
    )

    # Tracking for statistics
    df_updated['Is_Found_In_DB'] = df_updated['Signal_String'].notna()
    df_matched = df_updated[df_updated['Is_Found_In_DB'] == True].copy()
    df_missing = df_updated[df_updated['Is_Found_In_DB'] == False].copy()

    # Drop temp columns before saving
    df_final_save = df_updated.drop(columns=['match_key', 'Is_Found_In_DB'])

    # ==========================================
    # 5. WRITE BACK TO EXCEL
    # ==========================================
    log.info(f"Saving updated CAN data back to {excel_path} (Tab: {sheet_name})...")
    try:
        with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df_final_save.to_excel(writer, sheet_name=sheet_name, index=False)
        log.info("✅ CAN Excel update completed successfully!")
    except Exception as e:
        log.error(f"Failed to write to Excel: {e}")

    return df_matched, df_missing

# ==========================================
# EXECUTION BLOCK & TERMINAL VISUALIZATION
# ==========================================
if __name__ == "__main__":
    # Update these paths as needed
    ARXML_FILE = "ETH_CAN.arxml"
    EXCEL_FILE = "Intermediate_Requirements.xlsx"
    
    df_matched, df_missing = update_can_intermediate_sheet(ARXML_FILE, EXCEL_FILE)

    if df_matched is not None:
        total = len(df_matched) + len(df_missing)
        print("\n" + "="*50)
        print(" 📊 FINAL CAN VALIDATION STATISTICS")
        print("="*50)
        print(f"Total Requirements : {total}")
        print(f"✅ Matched         : {len(df_matched)} ({(len(df_matched)/total)*100 if total else 0:.2f}%)")
        print(f"❌ Missing         : {len(df_missing)}")
        print("="*50)

        # Terminal Display Logic
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        
        if not df_matched.empty:
            print("\n--- 🟢 MATCHED SAMPLES ---")
            cols = ['REQ ID', 'Can Signal', 'TX_Node', 'Signal_String', 'CAPL_Type']
            print(df_matched[[c for c in cols if c in df_matched.columns]].head(10).to_string())

        if not df_missing.empty:
            print("\n--- 🔴 MISSING SAMPLES ---")
            cols = ['REQ ID', 'Can Signal', 'match_key']
            print(df_missing[[c for c in cols if c in df_missing.columns]].head(10).to_string())