import argparse
import sys
import os
from pathlib import Path

from .gui.tool_gui import launch_gui
from core.logger import log
from mappers.mapper_orchestrator import MapperOrchestrator
from validators.cross_validator import CrossValidator
from generator.jinja_engine import JinjaEngine

from signals.can_parser import CANSignalParser
from signals.someip_event_parser import SomeIPEventParser

def ensure_databases(can_cache: str, eth_cache: str):
    """Synchronously builds databases if they don't exist before running the CLI pipeline."""
    if not os.path.exists(can_cache):
        log.warning(f"CAN Cache missing. Parsing network now...")
        can_parser = CANSignalParser("network.dbc")
        can_parser.to_json_file(can_cache)
        
    if not os.path.exists(eth_cache):
        log.warning(f"ETH Cache missing. Parsing ARXML now...")
        eth_parser = SomeIPEventParser("ETH_CAN.arxml")
        eth_parser.to_json_file(eth_cache)

def run_headless_generation(excel_path: Path, output_dir: Path, can_db: str, eth_db: str, category: str, test_type: str):
    """Executes the complete generation pipeline without a GUI (for CI/CD)."""
    log.info("==================================================")
    log.info("🤖 STARTING HEADLESS CAPL PIPELINE")
    log.info("==================================================")
    
    if not excel_path.exists():
        log.error(f"Input file not found: {excel_path}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_dir_str = str(output_dir)
    excel_path_str = str(excel_path)

    base_name = os.path.basename(excel_path_str).replace(".xlsx", "_Intermediate.xlsx")
    intermediate_excel = os.path.join(out_dir_str, base_name)

    try:

        ensure_databases(can_db, eth_db)
        
        # --- PHASE 1: PRE-PROCESS & MAP ---
        log.info("--- PHASE 1: GENERATING INTERMEDIATE SHEETS ---")
        orchestrator = MapperOrchestrator(can_db, eth_db)
        orchestrator.process_file(excel_path_str, out_dir_str)

        if not os.path.exists(intermediate_excel):
            log.error(f"Intermediate file creation failed: {intermediate_excel}")
            sys.exit(1)

        # --- PHASE 2: VALIDATE ---
        log.info("--- PHASE 2: CROSS-VALIDATING & COMPUTING LIMITS ---")
        validator = CrossValidator(orchestrator.can_mapper.db, orchestrator.eth_mapper.db)
        validator.process_sheet(intermediate_excel, "E2E_CAN_PARSED", is_can_sheet=True)
        validator.process_sheet(intermediate_excel, "E2E_ETH_PARSED", is_can_sheet=False)

        # --- PHASE 3: GENERATE CAPL ---
        log.info("--- PHASE 3: RUNNING JINJA GENERATOR ---")
        engine = JinjaEngine(output_root=out_dir_str)
        engine.run(intermediate_excel, eth_db, category, test_type)

        log.info("==================================================")
        log.info("✅ HEADLESS GENERATION COMPLETED SUCCESSFULLY")
        log.info("==================================================")

    except Exception as e:
        log.exception(f"Fatal error during headless generation: {e}")
        sys.exit(1)

