import sys
import argparse
from pathlib import Path
from core.logger import log
from .gui.tool_gui import launch_gui
from .cli import run_headless_generation

def main():
    """Universal Entry Point for the CAPL Gen Tool."""
    
    # If the user just double-clicks the app or runs it without flags, launch GUI immediately
    if len(sys.argv) == 1:
        log.info("No CLI arguments detected. Starting Graphical User Interface...")
        try:
            launch_gui()
        except Exception as e:
            log.critical(f"Failed to launch GUI: {e}")
            sys.exit(1)
        return

    # If arguments are passed, we parse them for headless execution
    parser = argparse.ArgumentParser(
        prog="capl-gen",
        description="CAPL Generation Tool Pipeline.",
        epilog="Run without arguments to launch the Graphical User Interface."
    )

    parser.add_argument("--cli", action="store_true", help="Run in headless mode (requires --excel)")
    parser.add_argument("--excel", type=Path, help="Path to the input Excel mapping file")
    parser.add_argument("--out", type=Path, default=Path("./Output_CAPL_Scripts"), help="Directory to save generated scripts")
    parser.add_argument("--can-db", default="can_db_cache.json", help="Path to CAN JSON Cache")
    parser.add_argument("--eth-db", default="someip_db_cache.json", help="Path to ETH JSON Cache")
    parser.add_argument("--category", default="E2E_CAN", help="Target Category (e.g. E2E_CAN)")
    parser.add_argument("--type", default="CAN->SOMEIP", help="Target Test Type (e.g. CAN->SOMEIP)")

    args = parser.parse_args()

    if args.cli:
        if not args.excel:
            log.error("Missing argument: --cli mode requires the --excel flag.")
            log.info("Example: capl-gen --cli --excel Requirements.xlsx")
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
        # If they passed some arguments but forgot --cli, print the help menu
        parser.print_help()

if __name__ == "__main__":
    main()