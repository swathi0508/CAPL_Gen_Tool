import sys
from pathlib import Path

from core.logger import log
from pipeline.main_pipeline import CaplGenerationPipeline

def run_headless_generation(excel_path: Path, output_dir: Path, can_db: str, eth_db: str, category: str, test_type: str, raw_arxml: str, someip_sysvar_xml: str, aacp_sysvar_vsysvar: str, enable_log: bool):
    """Executes the complete generation pipeline without a GUI (for CI/CD)."""

    pipeline = CaplGenerationPipeline(can_db_cache=can_db, eth_db_cache=eth_db, enable_log=enable_log)

    try:
        pipeline.run_full_headless_flow(
            input_excel=str(excel_path),
            out_dir=str(output_dir),
            category=category,
            test_type=test_type,
            raw_arxml=raw_arxml,
            someip_sysvar_xml=someip_sysvar_xml,
            aacp_sysvar_vsysvar=aacp_sysvar_vsysvar
        )
        log.info("✅ HEADLESS GENERATION COMPLETED SUCCESSFULLY")
    except Exception as e:
        log.error(f"❌ Pipeline Aborted: {e}")
        sys.exit(1)
