import argparse
import sys
from pathlib import Path

from capl_bolt.cli import run_headless_generation

# gui and cli are inside capl_bolt, so we must explicitly name the parent package
from capl_bolt.gui.tool_gui import launch_gui

# core is at the root, so it stays the same
from logger import log


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
    parser.add_argument("--req_excel", type=Path, required=True, help="Path to Input Requirements.xlsx")
    parser.add_argument("--arxml", type=str, required=True, help="Path to the ETH_CAN.arxml File")
    parser.add_argument("--aacp-sysvar", type=str, required=True, help="Path to the AACP sysvar (aacp.vsysvar) File")
    parser.add_argument("--someip-sysvar", type=str, required=True, help="Path to the SOMEIP_FF sysvar (SysVarDef.xml) File")
    parser.add_argument("--out", type=Path, default=Path("./Output_CAPL_Scripts"), help="Output directory for generated CAPL Scripts")
    
    # --- Cache Arguments ---
    parser.add_argument("--can-cache", default="can_db_cache.json", help="Path to CAN cache file")
    parser.add_argument("--eth-cache", default="someip_db_cache.json", help="Path to SOMEIP cache file")
    parser.add_argument("--someip-ff-cache", default="someip_ff_cache.json", help="Path to SOMEIP FF cache file")
    parser.add_argument("--aacp-cache", default="aacp_sysvar_cache.json", help="Path to AACP cache file")
    
    parser.add_argument("--category", default="E2E_CAN", required=True, help="Target Category - E2E_CAN | E2E_ETH")
    parser.add_argument("--type", default="CAN->SOMEIP", required=True, help="Target Test Type")

    args = parser.parse_args()

    run_headless_generation(
        excel_path=args.req_excel,
        output_dir=args.out,
        can_db=args.can_cache,
        eth_db=args.eth_cache,
        someip_ff_cache=args.someip_ff_cache,  
        aacp_cache=args.aacp_cache,           
        category=args.category,
        test_type=args.type,
        raw_arxml=args.arxml,
        someip_sysvar_xml=args.someip_sysvar,
        aacp_sysvar_vsysvar=args.aacp_sysvar,
        enable_log=args.enable_log
    )

if __name__ == "__main__":
    main()
