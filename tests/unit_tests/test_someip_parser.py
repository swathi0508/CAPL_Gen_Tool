import os

from cache_cleanup import cleanup_pycache

from logger import log
from signal_parsers.someip_event_parser import SomeIPEventParser

# Clean __pycache__ at test start
cleanup_pycache()

def test_someip_parsing(arxml_path: str, json_cache: str):
    """Tests the SOME/IP Parser's ability to extract data from the Unified ARXML."""
    log.info("🚀 Starting SOME/IP Parser Test...")

    if not os.path.exists(arxml_path):
        log.error(f"❌ ARXML file not found at {arxml_path}")
        return

    # 1. Initialize and Parse into RAM
    parser = SomeIPEventParser(arxml_path)
    signals_dict = parser.parse()

    if not signals_dict:
        log.error("❌ Parsing failed. Dictionary is empty.")
        return

    log.info(f"✅ Successfully parsed {len(signals_dict)} SOME/IP events into memory.")

    # 2. Test Disk Dump (Simulating Dev Mode)
    parser.to_json_file(json_cache, write_allowed=True)

if __name__ == "__main__":
    ARXML_FILE = "../ETH_CAN.arxml"
    CACHE_FILE = "someip_db_cache.json"

    test_someip_parsing(ARXML_FILE, CACHE_FILE)
