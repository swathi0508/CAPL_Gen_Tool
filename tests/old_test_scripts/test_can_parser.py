import os

import pandas as pd

from logger import log
from signal_parsers.can_parser import CANSignalParser


def update_can_intermediate_sheet(arxml_path, excel_path, sheet_name="E2E_CAN", json_cache="can_db_cache.json"):
    """
    Direct loop-based implementation to ensure zero 'KeyError' crashes and
    strict 'i' + Port Name matching.
    """
    log.info(f"🚀 Starting CAN Database Sync (Tab: {sheet_name})")

    # 1. Initialize Parser / Load Cache
    parser = CANSignalParser(arxml_path)
    if json_cache and os.path.exists(json_cache):
        parser.load_from_json(json_cache)

    # Ensure data is parsed (to_json_dict handles the logic)
    signals_dict = parser.to_json_dict()

    if json_cache and not os.path.exists(json_cache):
        parser.to_json_file(json_cache)

    # Create search set for O(1) lookup
    arxml_keys_lower = {str(k).lower(): v for k, v in signals_dict.items()}

    # 2. Load Excel
    if not os.path.exists(excel_path):
        log.error(f"Excel file not found at {excel_path}")
        return

    df_req = pd.read_excel(excel_path, sheet_name=sheet_name)
    target_col = "Port Name"

    if target_col not in df_req.columns:
        log.error(f"Column '{target_col}' missing.")
        return

    # 3. Process Rows (The Working Loop Logic)
    updated_rows = []
    matched_count = 0
    missing_count = 0

    for _index, row in df_req.iterrows():
        new_row = row.to_dict()
        port_val = str(row.get(target_col, '')).strip()

        # Default empty attributes
        found_data = {}
        validation_status = "CAN_NOT_FOUND"

        if port_val and port_val.lower() != 'nan':
            search_key = f"i{port_val.lower()}"

            if search_key in arxml_keys_lower:
                validation_status = "MATCHED"
                matched_count += 1
                # Retrieve all attributes from the parser dictionary
                found_data = arxml_keys_lower[search_key]
            else:
                missing_count += 1
                log.warning(f"❌ MISSING: {str(row.get('REQ ID')).ljust(15)} | Target: {search_key}")

        # Flatten found_data attributes into the row
        # This handles the 'Attributes' and 'signal_paths' from your JSON structure
        if found_data:
            new_row.update(found_data.get('Attributes', {}))
            # If multiple paths exist, we take the first one for the intermediate sheet
            paths = found_data.get('signal_paths', [])
            if paths:
                p = paths[0]
                new_row.update({
                    "Cluster": p.get("can_cluster"),
                    "TX_Node": p.get("tx"),
                    "RX_Nodes": ", ".join(p.get("rx", [])),
                    "Signal_String": p.get("signal_name")
                })

        new_row["Validation"] = validation_status
        updated_rows.append(new_row)

    # 4. Save Results
    df_final = pd.DataFrame(updated_rows)

    print("\n" + "="*50)
    print(f"📊 SYNC COMPLETE: {matched_count} Matched | {missing_count} Missing")
    print("="*50)

    try:
        with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df_final.to_excel(writer, sheet_name=sheet_name, index=False)
        log.info(f"✅ Sheet '{sheet_name}' updated successfully.")
    except Exception as e:
        log.error(f"Failed to write Excel: {e}")

if __name__ == "__main__":
    ARXML_FILE = "ETH_CAN.arxml"
    EXCEL_FILE = "Requirements.xlsx"
    CACHE_FILE = "can_db_cache.json"

    update_can_intermediate_sheet(ARXML_FILE, EXCEL_FILE, json_cache=CACHE_FILE)
