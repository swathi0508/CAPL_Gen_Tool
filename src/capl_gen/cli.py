import argparse
import sys
from pathlib import Path

from capl_gen.gui.tool_gui import launch_gui

from core.logger import log

# Import your core modules here as you build them:
# from core.mapper import ExcelMapper
# from signals.can_parser import CANParser
# from core.validator import SignalValidator
# from generator.jinja_engine import JinjaEngine

def run_headless_generation(excel_path: Path, output_dir: Path):
    """Executes the core generation pipeline without a GUI (for CI/CD)."""
    log.info("=== Starting Headless CAPL Generation ===")
    log.info(f"Input Excel: {excel_path}")
    log.info(f"Output Directory: {output_dir}")

    if not excel_path.exists():
        log.error(f"Input file not found: {excel_path}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # --- PIPELINE ORCHESTRATION ---

        # 1. Load mapping requirements
        # mapper = ExcelMapper(str(excel_path))
        # req_data = mapper.load_requirements()

        # 2. Parse DBC/ARXML
        # parser = CANParser("path/to/network.dbc")
        # signals = parser.parse()

        # 3. Validate
        # if not SignalValidator.validate_signal(signals):
        #     raise ValueError("Signal validation failed.")

        # 4. Generate CAPL
        # engine = JinjaEngine()
        # output_file = output_dir / "generated_nodes.can"
        # engine.generate("campaign/main.j2", req_data, str(output_file))

        log.info("=== Generation Completed Successfully ===")

    except Exception as e:
        log.exception(f"Fatal error during generation: {e}")
        sys.exit(1)

def main():
    """Parses command line arguments and routes execution."""
    parser = argparse.ArgumentParser(
        prog="capl-gen",
        description="CAPL Generation Tool for mapping CAN and SOME/IP signals.",
        epilog="Run without arguments to launch the GUI."
    )

    # CLI Flags
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in headless mode (requires --excel and --out)"
    )
    parser.add_argument(
        "--excel",
        type=Path,
        help="Path to the input Excel mapping file"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("./output"),
        help="Directory to save generated CAPL scripts (default: ./output)"
    )

    args = parser.parse_args()

    # Route Execution
    if args.cli:
        if not args.excel:
            log.error("Missing argument: --cli mode requires the --excel flag.")
            log.info("Example: capl-gen --cli --excel mapping.xlsx --out ./capl_src")
            sys.exit(1)

        run_headless_generation(args.excel, args.out)
    else:
        log.info("Starting Graphical User Interface...")
        try:
            launch_gui()
        except Exception as e:
            log.critical(f"Failed to launch GUI: {e}")
            sys.exit(1)