import os
from signals.can_parser import CANSignalParser
from core.logger import log

def test_can_parsing(arxml_path: str, json_cache: str):
    """Tests the CAN Parser's ability to extract data from the Unified ARXML."""
    log.info("🚀 Starting CAN Parser Test...")

    if not os.path.exists(arxml_path):
        log.error(f"❌ ARXML file not found at {arxml_path}")
        return

    # 1. Initialize and Parse into RAM
    parser = CANSignalParser(arxml_path)
    signals_dict = parser.parse()
    
    if not signals_dict:
        log.error("❌ Parsing failed. Dictionary is empty.")
        return

    log.info(f"✅ Successfully parsed {len(signals_dict)} CAN signals into memory.")

    # 2. Test Disk Dump (Simulating Dev Mode)
    parser.to_json_file(json_cache, write_allowed=True)

if __name__ == "__main__":
    ARXML_FILE = "../ETH_CAN.arxml"
    CACHE_FILE = "can_db_cache.json"
    
    test_can_parsing(ARXML_FILE, CACHE_FILE)