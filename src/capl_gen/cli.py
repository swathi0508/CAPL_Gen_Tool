import argparse
import sys
import os
from pathlib import Path

from capl_gen.gui.tool_gui import launch_gui
from capl_gen.core.logger import log
from capl_gen.mappers.mapper_orchestrator import MapperOrchestrator
from capl_gen.validators.cross_validator import CrossValidator
from capl_gen.generator.jinja_engine import JinjaEngine

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

def main():
    """Parses command line arguments and routes execution."""
    parser = argparse.ArgumentParser(
        prog="capl-gen",
        description="CAPL Generation Tool Pipeline.",
        epilog="Run without arguments to launch the GUI."
    )

    # CLI Flags
    parser.add_argument("--cli", action="store_true", help="Run in headless mode (requires all flags)")
    parser.add_argument("--excel", type=Path, help="Path to the input Excel mapping file")
    parser.add_argument("--out", type=Path, default=Path("./output"), help="Directory to save generated CAPL scripts")
    
    # New backend flags
    parser.add_argument("--can-db", default="can_db_cache.json", help="Path to CAN JSON Cache")
    parser.add_argument("--eth-db", default="someip_db_cache.json", help="Path to ETH JSON Cache")
    parser.add_argument("--category", default="E2E_CAN", help="Target Category (e.g. E2E_CAN)")
    parser.add_argument("--type", default="CAN->SOMEIP", help="Target Test Type (e.g. CAN->SOMEIP)")

    args = parser.parse_args()

    # Route Execution
    if args.cli:
        if not args.excel:
            log.error("Missing argument: --cli mode requires the --excel flag.")
            log.info("Example: capl-gen --cli --excel Requirements.xlsx --out ./Output_CAPL_Scripts")
            sys.exit(1)

        run_headless_generation(
            excel_path=args.excel, 
            output_dir=args.out, 
            can_db=args.can_db, 
            eth_db=args.eth_db, 
            category=args.category, 
            test_type=args.type
        )
    else:
        log.info("Starting Graphical User Interface...")
        try:
            launch_gui()
        except Exception as e:
            log.critical(f"Failed to launch GUI: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()