import sys
import argparse
from pathlib import Path
from core.logger import log
from .gui.tool_gui import launch_gui
from .cli import run_headless_generation

def main():
    """Universal Entry Point for the CAPL Gen Tool."""
    
    if len(sys.argv) == 1:
        log.info("Starting Graphical User Interface...")
        try:
            launch_gui()
        except Exception as e:
            log.critical(f"Failed to launch GUI: {e}")
            sys.exit(1)
        return

    parser = argparse.ArgumentParser(description="CAPL Generation Tool Pipeline.")
    parser.add_argument("--cli", action="store_true", help="Run in headless mode")
    parser.add_argument("--enable-log", action="store_true", help="DEV ONLY: Saves intermediate files to disk and boosts logging verbosity")
    parser.add_argument("--excel", type=Path, required=True, help="Path to input Excel Requirements")
    parser.add_argument("--arxml", type=str, required=True, help="Path to the unified Raw ARXML Network File")
    parser.add_argument("--out", type=Path, default=Path("./Output_CAPL_Scripts"), help="Output directory")
    parser.add_argument("--can-cache", default="can_db_cache.json", help="Path to generated CAN Cache")
    parser.add_argument("--eth-cache", default="someip_db_cache.json", help="Path to generated ETH Cache")
    parser.add_argument("--category", default="E2E_CAN", help="Target Category")
    parser.add_argument("--type", default="CAN->SOMEIP", help="Target Test Type")

    args = parser.parse_args()

    run_headless_generation(
        excel_path=args.excel, 
        output_dir=args.out, 
        can_db=args.can_cache, 
        eth_db=args.eth_cache, 
        category=args.category, 
        test_type=args.type,
        raw_arxml=args.arxml,
        enable_log=args.enable_log
    )

if __name__ == "__main__":
    main()