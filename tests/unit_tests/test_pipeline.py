import sys
import tempfile
from pathlib import Path

from cache_cleanup import cleanup_pycache

from logger import log
from pipeline.main_pipeline import CaplGenerationPipeline

# Replicate the CLI's cross-platform Temp Directory logic
SYSTEM_TEMP_DIR = Path(tempfile.gettempdir()) / ".capl_bolt_cache"


def test_full_pipeline(
    input_excel: Path,
    output_dir: Path,
    category: str,
    test_type: str,
    raw_arxml: Path,
    someip_sysvar_xml: Path,
    aacp_sysvar_vsysvar: Path,
):
    """Tests the entire unified pipeline using secure OS-level temp caching."""

    log.info("==================================================")
    log.info("🚀 STARTING UNIFIED PIPELINE INTEGRATION TEST")
    log.info("==================================================")

    missing_files = [
        f
        for f in [input_excel, raw_arxml, someip_sysvar_xml, aacp_sysvar_vsysvar]
        if not f.exists()
    ]
    if missing_files:
        log.error("❌ Pre-flight check failed! The following files are missing:")
        for f in missing_files:
            log.error(f"  - {f}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Route caches to the secure system temp directory using the .capldb extension
    pipeline = CaplGenerationPipeline(
        can_db_cache=str(SYSTEM_TEMP_DIR / "can_db.capldb"),
        someip_db_cache=str(SYSTEM_TEMP_DIR / "someip_db.capldb"),
        someip_ff_db_cache=str(SYSTEM_TEMP_DIR / "someip_ff.capldb"),
        aacp_sysvar_db_cache=str(SYSTEM_TEMP_DIR / "aacp_sysvar.capldb"),
        enable_log=True,  # DEV MODE: Dumps intermediate Excel to output_dir
    )

    try:
        pipeline.run_full_headless_flow(
            input_excel=str(input_excel),
            out_dir=str(output_dir),
            category=category,
            test_type=test_type,
            raw_arxml=str(raw_arxml),
            someip_sysvar_xml=str(someip_sysvar_xml),
            aacp_sysvar_vsysvar=str(aacp_sysvar_vsysvar),
        )
        log.info("==================================================")
        log.info("✅ FULL PIPELINE EXECUTED SUCCESSFULLY")
        log.info(f"📁 Check output at: {output_dir.resolve()}")
        log.info(f"🔒 Secure Caches stored at: {SYSTEM_TEMP_DIR.resolve()}")
        log.info("==================================================")

    except Exception as e:
        log.exception(f"❌ Pipeline Integration Test Failed: {e}")


if __name__ == "__main__":
    cleanup_pycache()

    TEST_DIR = Path(__file__).parent.resolve()
    WORKSPACE_DIR = TEST_DIR.parent

    RAW_ARXML = WORKSPACE_DIR / "ETH_CAN.arxml"
    SOMEIP_SYSVAR_XML = WORKSPACE_DIR / "SysVarDef.xml"
    AACP_SYSVAR_VSYSVAR = WORKSPACE_DIR / "aacp.vsysvar"
    REQUIREMENTS_EXCEL = WORKSPACE_DIR / "Requirements.xlsx"

    OUTPUT_DIR = TEST_DIR / "output"

    CATEGORY = "E2E_CAN"
    TEST_TYPE = "CAN->SOMEIP_AACP"

    test_full_pipeline(
        REQUIREMENTS_EXCEL,
        OUTPUT_DIR,
        CATEGORY,
        TEST_TYPE,
        RAW_ARXML,
        SOMEIP_SYSVAR_XML,
        AACP_SYSVAR_VSYSVAR,
    )
