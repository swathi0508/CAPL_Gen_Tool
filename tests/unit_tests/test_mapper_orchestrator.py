import json
import os
from pathlib import Path

import pandas as pd
from cache_cleanup import cleanup_pycache

from logger import log
from preprocessor_core.mapper_orchestrator import MapperOrchestrator

# Clean __pycache__ at test start
cleanup_pycache()


def load_json_cache(path: str) -> dict:
    """Helper to mock the pipeline loading caches for testing."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Cache file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle different JSON structures from the parsers
    if "SIGNAL_LIST" in data:
        return data["SIGNAL_LIST"]
    if "SOMEIP_SIGNAL" in data:
        return data["SOMEIP_SIGNAL"]
    return data


def test_mapper_orchestration(
    input_excel: str,
    output_dir: str,
    can_cache: str,
    eth_cache: str,
    someip_ff_cache: str,
    aacp_cache: str,
):
    """
    Executes the full 7-step Mapping & Processing sequence in RAM.
    This replaces the old Phase 1 (Mapping) + Phase 2 (Validation) sequence.
    """
    log.info("🚀 STARTING MAPPER ORCHESTRATOR IN-MEMORY TEST")

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Define output file for manual verification
    base_name = Path(input_excel).name.replace(
        ".xlsx",
        "_Intermediate.xlsx",
    )
    output_verification_file = out_path / base_name

    try:
        # 1. Load Caches to Mock Database State
        log.info(f"Loading CAN cache: {can_cache}")
        can_db = load_json_cache(can_cache)

        log.info(f"Loading ETH cache: {eth_cache}")
        eth_db = load_json_cache(eth_cache)

        log.info(f"Loading SOMEIP_FF cache: {someip_ff_cache}")
        someip_ff_db = load_json_cache(someip_ff_cache)

        log.info(f"Loading AACP cache: {aacp_cache}")
        aacp_db = load_json_cache(aacp_cache)

        # 2. Initialize Orchestrator
        # This internalizes the CommonProcessor which now handles Enum & Phys logic
        orchestrator = MapperOrchestrator(
            can_db_data=can_db,
            eth_db_data=eth_db,
            someip_ff_db_data=someip_ff_db,
            aacp_db_data=aacp_db,
        )

        # 3. Execute the 7-Step Sequence
        # Steps: Copy -> Define -> Cluster/BFN -> Map Raw -> Namespace
        # -> Enum Map -> Phys Derive
        log.info("--- EXECUTING 7-STEP ORCHESTRATION ---")
        in_memory_dfs = orchestrator.process_to_dataframes(input_excel)

        # 4. Verification & Disk Export
        if not in_memory_dfs:
            log.error(
                "❌ No DataFrames were generated. "
                "Check sheet names in Excel "
                "(Expects E2E_ETH/E2E_CAN)."
            )
            return

        log.info(f"--- SAVING {len(in_memory_dfs)} PROCESSED SHEETS TO DISK ---")

        with pd.ExcelWriter(
            output_verification_file,
            engine="openpyxl",
        ) as writer:
            for sheet_name, df in in_memory_dfs.items():
                log.info(f"Exporting: {sheet_name} ({len(df)} rows)")
                df.to_excel(
                    writer,
                    sheet_name=sheet_name,
                    index=False,
                )

                # Quick Logic Check: Physical Values
                sample_phys = (
                    df["COMPUTED_CAN_VALUE_MAX"].iloc[0]
                    if "COMPUTED_CAN_VALUE_MAX" in df.columns
                    else "N/A"
                )
                log.debug(f"[{sheet_name}] Sample Phys Max: {sample_phys}")

        log.info(f"✅ TEST COMPLETE! Verify results at: {output_verification_file}")

    except Exception as e:
        log.exception(f"❌ Test encountered a fatal error: {e}")


if __name__ == "__main__":
    # --- CONFIGURATION ---
    # Update these paths to point to your actual local files
    INPUT_REQ_FILE = r"../Requirements.xlsx"
    OUTPUT_DIRECTORY = r"./output"
    CAN_JSON_CACHE = r"can_db_cache.json"
    ETH_JSON_CACHE = r"someip_db_cache.json"
    SOMEIP_FF_JSON_CACHE = r"someip_ff_cache.json"
    AACP_JSON_CACHE = r"aacp_sysvar_cache.json"

    # Ensure the input files exist before starting
    if os.path.exists(INPUT_REQ_FILE):
        test_mapper_orchestration(
            INPUT_REQ_FILE,
            OUTPUT_DIRECTORY,
            CAN_JSON_CACHE,
            ETH_JSON_CACHE,
            SOMEIP_FF_JSON_CACHE,
            AACP_JSON_CACHE,
        )
    else:
        log.error(f"Input Excel not found at {INPUT_REQ_FILE}. Please check the path.")
