import argparse
import sys
import tempfile
from pathlib import Path

from capl_bolt.cli import run_headless_generation
from capl_bolt.gui.tool_gui import launch_gui
from logger import log


# --- SECURITY SHIELD: Global Exception Handler ---
def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Intercepts unhandled crashes to prevent leaking source code paths to users."""
    is_production = getattr(sys, "frozen", False)

    if is_production:
        # In Production: Give a generic, safe error message. Do NOT print the traceback.
        log.critical(
            f"A fatal application error occurred: {exc_type.__name__}. Please contact support."
        )
    else:
        # In Development: Print the full traceback so you can fix the bug.
        sys.__excepthook__(exc_type, exc_value, exc_traceback)


sys.excepthook = global_exception_handler
# -------------------------------------------------

# Calculate the cross-platform System Temp Directory
SYSTEM_TEMP_DIR = Path(tempfile.gettempdir()) / ".capl_bolt_cache"


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
    parser.add_argument("--cli", action="store_true", help="Run in headless CLI mode")
    parser.add_argument("--enable-log", action="store_true")

    # Core Inputs (Required inputs first)
    parser.add_argument(
        "--req_excel", type=Path, required=True, help="Path to Input Requirements.xlsx"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("./Output_CAPL_Scripts"),
        help="Output directory for generated CAPL Scripts",
    )
    parser.add_argument(
        "--category", default="E2E_CAN", required=True, help="Target Category - E2E_CAN | E2E_ETH"
    )
    parser.add_argument("--type", default="CAN->SOMEIP", required=True, help="Target Test Type")

    # Raw File Inputs (Optional now, to allow Cache-Only mode)
    parser.add_argument(
        "--arxml", type=str, default="", help="Path to the ETH_CAN.arxml File (Optional if cached)"
    )
    parser.add_argument(
        "--aacp-sysvar", type=str, default="", help="Path to the AACP sysvar (Optional if cached)"
    )
    parser.add_argument(
        "--someip-sysvar",
        type=str,
        default="",
        help="Path to the SOMEIP_FF sysvar (Optional if cached)",
    )

    # The Escape Hatch
    parser.add_argument(
        "--no-cache", action="store_true", help="Force a fresh parse (ignores existing caches)"
    )

    # Hidden Cache Overrides (Disguised as proprietary DBs in the system temp folder)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=SYSTEM_TEMP_DIR,
        help="Path to directory containing .capldb or .json caches. Defaults to system temp.",
    )

    args = parser.parse_args()

    run_headless_generation(
        excel_path=args.req_excel,
        output_dir=args.out,
        cache_dir=args.cache_dir,  # Pass the single directory
        category=args.category,
        test_type=args.type,
        raw_arxml=args.arxml,
        someip_sysvar_xml=args.someip_sysvar,
        aacp_sysvar_vsysvar=args.aacp_sysvar,
        enable_log=args.enable_log,
        no_cache=args.no_cache,
    )


if __name__ == "__main__":
    main()
