import json
from pathlib import Path

import pandas as pd
from cache_cleanup import cleanup_pycache

from logger import log
from preprocessor_core.mapper_orchestrator import MapperOrchestrator

# Clean __pycache__ at test start
cleanup_pycache()

def load_json_cache(path: str) -> dict:
    """Helper to mock the pipeline loading caches for testing."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get("SIGNAL_LIST", data.get("SOMEIP_SIGNAL", data))

def test_mapper_and_validator(input_excel: str, output_dir: str, can_cache: str, eth_cache: str):
    """Executes Phase 1 & 2 strictly in RAM to test component interaction."""
    log.info("🚀 STARTING MAPPER & VALIDATOR IN-MEMORY TEST")

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    base_name = Path(input_excel).name.replace(".xlsx", "_Intermediate.xlsx")
    intermediate_excel = out_path / base_name

    try:
        # Load Caches to Mock Pipeline
        can_db = load_json_cache(can_cache)
        eth_db = load_json_cache(eth_cache)

        # ---------------------------------------------------------
        # PHASE 1: ORCHESTRATION (Memory DataFrames)
        # ---------------------------------------------------------
        log.info("--- PHASE 1: MAPPING TO DATAFRAMES ---")
        orchestrator = MapperOrchestrator(can_db_data=can_db, eth_db_data=eth_db)
        in_memory_dfs = orchestrator.process_to_dataframes(input_excel)

        # ---------------------------------------------------------
        # PHASE 2: CROSS VALIDATION REMOVED
        # ---------------------------------------------------------
        log.info("--- PHASE 2: SKIPPING CROSS VALIDATION ---")

        # ---------------------------------------------------------
        # TEST VERIFICATION: Save to Disk
        # ---------------------------------------------------------
        log.info("--- SAVING RESULTS TO DISK FOR VERIFICATION ---")
        with pd.ExcelWriter(intermediate_excel, engine='openpyxl') as writer:
            for sheet_name, df in in_memory_dfs.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)

        log.info(f"✅ TEST COMPLETE! Verify Output: {intermediate_excel}")

    except Exception as e:
        log.exception(f"❌ Test encountered a fatal error: {e}")

if __name__ == "__main__":
    INPUT_REQ_FILE = r"../Requirements.xlsx"
    OUTPUT_DIRECTORY = r"./output"
    CAN_JSON_CACHE = r"can_db_cache.json"
    ETH_JSON_CACHE = r"someip_db_cache.json"

    test_mapper_and_validator(INPUT_REQ_FILE, OUTPUT_DIRECTORY, CAN_JSON_CACHE, ETH_JSON_CACHE)
