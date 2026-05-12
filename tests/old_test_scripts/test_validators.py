import os

# Adjust these imports based on how your IDE resolves the 'src' folder
from core.logger import log
from mappers.mapper_orchestrator import MapperOrchestrator
from validators.cross_validator import CrossValidator


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
        # PHASE 2: CROSS VALIDATION & LIMIT COMPUTATION
        # ---------------------------------------------------------
        log.info("--- PHASE 2: CROSS-VALIDATING & COMPUTING LIMITS ---")

        # Instantiate Validator using the ALREADY LOADED databases from the Orchestrator
        # This saves massive amounts of time by not re-reading the JSONs!
        validator = CrossValidator(
            can_db=orchestrator.can_mapper.db,
            eth_db=orchestrator.eth_mapper.db
        )

        # Note: The Orchestrator saves the sheets with a "_PARSED" suffix
        # 1. Validate the CAN Sheet
        validator.process_sheet(
            excel_path=intermediate_excel,
            sheet_name="E2E_CAN_PARSED",
            is_can_sheet=True
        )

        # 2. Validate the ETH Sheet
        validator.process_sheet(
            excel_path=intermediate_excel,
            sheet_name="E2E_ETH_PARSED",
            is_can_sheet=False
        )

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
