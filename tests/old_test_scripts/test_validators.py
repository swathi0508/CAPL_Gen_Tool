import os

from logger import log
from preprocessor_core.mapper_orchestrator import MapperOrchestrator


def run_pipeline(input_excel: str, output_dir: str, can_cache: str, eth_cache: str):
    """Executes the complete Mapping and Validation pipeline."""

    log.info("==================================================")
    log.info("🚀 STARTING CAPL GEN PIPELINE")
    log.info("==================================================")

    # Calculate expected intermediate file path based on orchestrator logic
    base_name = os.path.basename(input_excel).replace(".xlsx", "_Intermediate.xlsx")
    intermediate_excel = os.path.join(output_dir, base_name)

    try:
        # ---------------------------------------------------------
        # PHASE 1: ORCHESTRATION & MAPPING
        # ---------------------------------------------------------
        log.info("--- PHASE 1: GENERATING INTERMEDIATE SHEETS ---")

        # Instantiate Orchestrator (This automatically loads the JSON caches)
        orchestrator = MapperOrchestrator(can_cache=can_cache, eth_cache=eth_cache)

        # Process the raw requirements and create the Intermediate Excel
        orchestrator.process_file(input_excel, output_dir)

        if not os.path.exists(intermediate_excel):
            log.error(f"Failed to locate expected intermediate file: {intermediate_excel}")
            return

        # ---------------------------------------------------------
        # PHASE 2: CROSS VALIDATION REMOVED
        # ---------------------------------------------------------
        log.info("--- PHASE 2: SKIPPING CROSS VALIDATION ---")

        log.info("==================================================")
        log.info(f"✅ PIPELINE COMPLETE! Final Output: {intermediate_excel}")
        log.info("==================================================")

    except Exception as e:
        log.exception(f"❌ Pipeline encountered a fatal error: {e}")

if __name__ == "__main__":
    # --- CONFIGURE YOUR LOCAL PATHS HERE ---
    INPUT_REQ_FILE = r"Requirements.xlsx"  # Replace with your actual raw input file
    OUTPUT_DIRECTORY = r"./output"

    CAN_JSON_CACHE = r"can_db_cache.json"
    ETH_JSON_CACHE = r"someip_db_cache.json"

    # Run the pipeline
    run_pipeline(
        input_excel=INPUT_REQ_FILE,
        output_dir=OUTPUT_DIRECTORY,
        can_cache=CAN_JSON_CACHE,
        eth_cache=ETH_JSON_CACHE
    )
