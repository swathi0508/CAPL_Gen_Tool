import os
from signals.someip_ff_parser import SomeipFFParser
from core.logger import log
from cache_cleanup import cleanup_pycache

# Clean __pycache__ at test start to ensure fresh imports
cleanup_pycache()

def test_someip_ff_parsing(xml_path: str, json_cache: str):
    """Tests the SOME/IP FF (SysVar) Parser's ability to extract data from SysVarDef.xml."""
    log.info("🚀 Starting SOME/IP FF Parser Test...")

    if not os.path.exists(xml_path):
        log.error(f"❌ XML file not found at {xml_path}")
        return

    # 1. Initialize and Parse into RAM
    parser = SomeipFFParser(xml_path)
    ff_dict = parser.parse()
    
    if not ff_dict or "Summary" not in ff_dict:
        log.error("❌ Parsing failed. FF Dictionary is empty or malformed.")
        return

    # UPDATED: Extract the actual signal count from the Summary block
    total_signals = ff_dict.get("Summary", {}).get("Total_Signals_Found", 0)
    log.info(f"✅ Successfully parsed {total_signals} System Variables into memory.")

    # Optional: Log a sample interface to verify hierarchical structure
    interfaces = ff_dict.get("INTERFACES", {})
    if interfaces:
        sample_iface_name = list(interfaces.keys())[0]
        log.debug(f"🔍 Sample Interface [{sample_iface_name}]: {interfaces[sample_iface_name]}")

    # 2. Test Disk Dump (Simulating Dev Mode)
    parser.to_json_file(json_cache, write_allowed=True)
    log.info(f"✅ Cache dumped to {json_cache}")

if __name__ == "__main__":
    # Ensure this points to your actual SysVar XML file
    SOMEIP_SYSVAR_XML = "../SysVarDef.xml"
    CACHE_FILE = "someip_ff_cache.json"
    
    test_someip_ff_parsing(SOMEIP_SYSVAR_XML, CACHE_FILE)