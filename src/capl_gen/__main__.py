import sys
import argparse
from pathlib import Path

# core is at the root, so it stays the same
from core.logger import log

# gui and cli are inside capl_gen, so we must explicitly name the parent package
from capl_gen.gui.tool_gui import launch_gui
from capl_gen.cli import run_headless_generation

# --- SECURITY SHIELD: Global Exception Handler ---
def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Intercepts unhandled crashes to prevent leaking source code paths to users."""
    is_production = getattr(sys, 'frozen', False)
    
    if is_production:
        # In Production: Give a generic, safe error message. Do NOT print the traceback.
        log.critical(f"A fatal application error occurred: {exc_type.__name__}. Please contact support.")
    else:
        # In Development: Print the full traceback so you can fix the bug.
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

# Attach the shield
sys.excepthook = global_exception_handler
# -------------------------------------------------

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
    parser.add_argument("--cli", action="store_true", help=" INTERFACE TEST - CAPL SCRIPT GENERATOR TOOL")
    parser.add_argument("--enable-log", action="store_true")
    parser.add_argument("--req_excel", type=Path, required=True, help="Path to Input Requirement.xlsx")
    parser.add_argument("--arxml", type=str, required=True, help="Path to the ETH_CAN.arxml File")
    parser.add_argument("--out", type=Path, default=Path("./Output_CAPL_Scripts"), help="Output directory for generated CAPL Scripts")
    parser.add_argument("--can-cache", default="can_db_cache.json")
    parser.add_argument("--eth-cache", default="someip_db_cache.json")
    parser.add_argument("--category", default="E2E_CAN", required=True, help="Target Category - E2E_CAN | E2E_ETH")
    parser.add_argument("--type", default="CAN->SOMEIP", required=True, help="Target Test Type")

    args = parser.parse_args()

    run_headless_generation(
        excel_path=args.req_excel, 
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