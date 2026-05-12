from cache_cleanup import cleanup_pycache

from core.logger import log
from pipeline.main_pipeline import CaplGenerationPipeline

# Clean __pycache__ at test start
cleanup_pycache()

def test_full_pipeline(input_excel: str, output_dir: str, category: str, test_type: str, raw_arxml: str):
    """Tests the entire unified, in-memory pipeline."""
    log.info("==================================================")
    log.info("🚀 STARTING UNIFIED PIPELINE INTEGRATION TEST")
    log.info("==================================================")

    # Initialize the Pipeline in DEV MODE (enable_log=True) so it dumps caches to disk
    pipeline = CaplGenerationPipeline(
        can_db_cache="can_db_cache.json",
        eth_db_cache="someip_db_cache.json",
        enable_log=False
    )

    try:
        pipeline.run_full_headless_flow(
            input_excel=input_excel,
            out_dir=output_dir,
            category=category,
            test_type=test_type,
            raw_arxml=raw_arxml
        )
        log.info("==================================================")
        log.info("✅ FULL PIPELINE EXECUTED SUCCESSFULLY")
        log.info("==================================================")

    except Exception as e:
        log.exception(f"❌ Pipeline Integration Test Failed: {e}")

if __name__ == "__main__":
    # Ensure these point to valid sample files in your workspace
    RAW_ARXML = "../ETH_CAN.arxml"
    REQUIREMENTS_EXCEL = "../Requirements.xlsx"
    OUTPUT_DIR = "./output_test"

    CATEGORY = "E2E_CAN"
    TEST_TYPE = "CAN->SOMEIP"

    test_full_pipeline(REQUIREMENTS_EXCEL, OUTPUT_DIR, CATEGORY, TEST_TYPE, RAW_ARXML)
