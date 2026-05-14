import json
import os

import pandas as pd
from cache_cleanup import cleanup_pycache

from logger import log
from generator.jinja_engine import JinjaEngine

# Clean __pycache__ at test start
cleanup_pycache()

def test_generator(excel_path: str, eth_json_path: str, category: str, test_type: str, output_root: str):
    """Executes the CAPL Code Generation pipeline from RAM DataFrames."""
    log.info(f"⚙️ STARTING JINJA ENGINE TEST ({category} | {test_type})")

    if not os.path.exists(excel_path) or not os.path.exists(eth_json_path):
        log.error("❌ Required input files missing. Run mapper/validator test first.")
        return

    try:
        # 1. Mock the Pipeline by loading Excel into a DataFrame Dictionary
        log.info("Loading Excel into RAM Dictionary...")
        xls = pd.ExcelFile(excel_path)
        in_memory_dfs = {sheet: pd.read_excel(xls, sheet_name=sheet) for sheet in xls.sheet_names if sheet.endswith("_PARSED")}

        # 2. Mock the Pipeline by loading the ETH Cache into a Dictionary
        log.info("Loading SOME/IP Dictionary...")
        with open(eth_json_path, 'r', encoding='utf-8') as f:
            eth_data = json.load(f)
            eth_db_data = eth_data.get("SIGNAL_LIST", eth_data.get("SOMEIP_SIGNAL", eth_data))

        # 3. Trigger the Engine entirely in RAM
        log.info("Triggering Jinja Engine...")
        engine = JinjaEngine(output_root=output_root)
        engine.run_from_memory(
            data_frames=in_memory_dfs,
            eth_db_data=eth_db_data,
            category=category,
            test_type=test_type
        )

        log.info(f"✅ GENERATION COMPLETE! Check the '{output_root}' folder.")

    except Exception as e:
        log.exception(f"❌ Generator encountered a fatal error: {e}")

if __name__ == "__main__":
    INTERMEDIATE_EXCEL = r"./output/Requirements_Intermediate.xlsx"
    SOMEIP_JSON_CACHE = r"someip_db_cache.json"
    OUTPUT_DIRECTORY = "Output_CAPL_Scripts"

    TARGET_CATEGORY = "E2E_ETH"
    TARGET_TEST_TYPE = "CAN->SOMEIP_FF"

    test_generator(INTERMEDIATE_EXCEL, SOMEIP_JSON_CACHE, TARGET_CATEGORY, TARGET_TEST_TYPE, OUTPUT_DIRECTORY)
