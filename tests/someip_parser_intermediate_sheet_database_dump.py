import os
import pandas as pd
from signals.someip_event_parser import SomeIPEventParser
from core.logger import log  # Assuming you have your logger setup

def update_eth_intermediate_sheet(arxml_path: str, excel_path: str, sheet_name: str = "E2E_ETH"):
    """
    Parses the ARXML and merges the SOME/IP properties into an existing Excel requirements sheet.
    """
    log.info("Starting SOME/IP Database Dump to Intermediate Sheet...")

    # ==========================================
    # 1. INVOKE THE PARSER
    # ==========================================
    parser = SomeIPEventParser(arxml_path)
    df_signals = parser.to_dataframe()
    
    if df_signals.empty:
        log.error("Parsing failed or ARXML is empty. Aborting Excel update.")
        return

    # ==========================================
    # 2. LOAD EXISTING EXCEL SHEET
    # ==========================================
    if not os.path.exists(excel_path):
        log.error(f"Excel file '{excel_path}' not found. Please ensure the file exists.")
        return

    try:
        # Load only the specific sheet we want to update
        df_req = pd.read_excel(excel_path, sheet_name=sheet_name)
    except Exception as e:
        log.error(f"Failed to read sheet '{sheet_name}' from {excel_path}: {e}")
        return

    # ==========================================
    # 3. PREPARE KEYS FOR MATCHING (SIF + Method)
    # ==========================================
    # Clean the requirements keys
    df_req['match_sif'] = df_req['Service ID'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df_req['match_method'] = df_req['Attribute value'].astype(str).str.strip().str.lower()
    
    # Clean the ARXML database keys
    df_signals['match_sif'] = df_signals['SIF'].astype(str).str.strip()
    df_signals['match_method'] = df_signals['Method'].astype(str).str.strip().str.lower()

    # Drop duplicates on SIF+Method just for the merge to prevent duplicating CSV rows
    df_signals_unique = df_signals.drop_duplicates(subset=['match_sif', 'match_method'])

    # Columns we want to pull from the ARXML into the Excel sheet
    columns_to_add = [
        'match_sif', 'match_method', 'Signal_String', 'DataType', 
        'Available_States', 'Min', 'Mid', 'Max', 'Factor', 'Offset', 'Unit'
    ]

    # Clean up old ARXML columns if this script is being re-run, to prevent _x and _y suffixing
    existing_cols = df_req.columns.tolist()
    cols_to_drop = [c for c in columns_to_add if c in existing_cols and c not in ['match_sif', 'match_method']]
    df_req = df_req.drop(columns=cols_to_drop)

    # ==========================================
    # 4. PERFORM THE MERGE
    # ==========================================
    # Left merge ensures we don't lose any requirements, even if they aren't found in the ARXML
    df_updated = pd.merge(
        df_req, 
        df_signals_unique[columns_to_add], 
        on=['match_sif', 'match_method'], 
        how='left'
    )

    # Drop the temporary matching columns to keep the Excel sheet clean
    df_updated = df_updated.drop(columns=['match_sif', 'match_method'])

    # ==========================================
    # 5. WRITE BACK TO EXCEL (Safely)
    # ==========================================
    log.info(f"Saving updated data back to {excel_path} (Tab: {sheet_name})...")
    try:
        # engine='openpyxl', mode='a', if_sheet_exists='replace' is the magic combo
        # It replaces ONLY the E2E_ETH sheet, leaving E2E_CAN completely untouched.
        with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df_updated.to_excel(writer, sheet_name=sheet_name, index=False)
        log.info("✅ Excel update completed successfully!")
    except PermissionError:
        log.error("Permission Denied: Please close the Excel file if you have it open and try again.")
    except Exception as e:
        log.error(f"Failed to write to Excel: {e}")

# ==========================================
# EXECUTION BLOCK
# ==========================================
if __name__ == "__main__":
    ARXML_FILE = "ETH_CAN.arxml"
    EXCEL_FILE = "Intermediate_Requirements.xlsx" # Change to your actual file name
    
    update_eth_intermediate_sheet(ARXML_FILE, EXCEL_FILE, sheet_name="E2E_ETH")