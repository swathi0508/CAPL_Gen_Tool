import sys
from pathlib import Path

from logger import log
from pipeline.main_pipeline import CaplGenerationPipeline

def run_headless_generation(
    excel_path: Path, 
    output_dir: Path, 
    can_db: str, 
    someip_cache: str,
    someip_ff_cache: str,   
    aacp_cache: str,        
    category: str, 
    test_type: str, 
    raw_arxml: str, 
    someip_sysvar_xml: str, 
    aacp_sysvar_vsysvar: str, 
    enable_log: bool,
    no_cache: bool
):
    """Executes the complete generation pipeline without a GUI (for CI/CD)."""

    pipeline = CaplGenerationPipeline(
        can_db_cache=can_db, 
        someip_db_cache=someip_cache,
        someip_ff_db_cache=someip_ff_cache,  
        aacp_sysvar_db_cache=aacp_cache,    
        enable_log=enable_log,
        no_cache=no_cache                  
    )

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
