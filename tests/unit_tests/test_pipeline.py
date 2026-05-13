from cache_cleanup import cleanup_pycache

from logger import log
from pipeline.main_pipeline import CaplGenerationPipeline

# Clean __pycache__ at test start
cleanup_pycache()

def test_full_pipeline(input_excel: str, output_dir: str, category: str, test_type: str, raw_arxml: str, someip_sysvar_xml: str, aacp_sysvar_vsysvar: str):
    """Tests the entire unified, in-memory pipeline."""
    log.info("==================================================")
    log.info("🚀 STARTING UNIFIED PIPELINE INTEGRATION TEST")
    log.info("==================================================")

    # Initialize the Pipeline in DEV MODE (enable_log=True) so it dumps caches to disk
    pipeline = CaplGenerationPipeline(
        can_db_cache="can_db_cache.json",
        eth_db_cache="someip_db_cache.json",
        someip_ff_db_cache="someip_ff_cache.json",
        aacp_sysvar_vsysvar_db_cache="aacp_sysvar_cache.json",
        enable_log=False
    )

    try:
        pipeline.run_full_headless_flow(
            input_excel=input_excel,
            out_dir=output_dir,
            category=category,
            test_type=test_type,
            raw_arxml=raw_arxml,
            someip_sysvar_xml=someip_sysvar_xml,
            aacp_sysvar_vsysvar=aacp_sysvar_vsysvar
        )
        log.info("==================================================")
        log.info("✅ FULL PIPELINE EXECUTED SUCCESSFULLY")
        log.info("==================================================")

    except Exception as e:
        log.exception(f"❌ Pipeline Integration Test Failed: {e}")

if __name__ == "__main__":
    # Ensure these point to valid sample files in your workspace
    RAW_ARXML = "../ETH_CAN.arxml"
    SOMEIP_SYSVAR_XML = "../SysVarDef.xml"
    AACP_SYSVAR_VSYSVAR = "../aacp.vsysvar"
    REQUIREMENTS_EXCEL = r"../Requirements.xlsx" 
    OUTPUT_DIR = r"./output"
    
    CATEGORY = "E2E_CAN"            
    TEST_TYPE = "CAN->SOMEIP"

    test_full_pipeline(REQUIREMENTS_EXCEL, OUTPUT_DIR, CATEGORY, TEST_TYPE, RAW_ARXML, SOMEIP_SYSVAR_XML, AACP_SYSVAR_VSYSVAR)
