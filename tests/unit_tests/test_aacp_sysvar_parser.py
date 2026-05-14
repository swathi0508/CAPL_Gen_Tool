import os
from signal_parsers.aacp_sysvar_parser import AacpSysVarParser
from logger import log
from cache_cleanup import cleanup_pycache

# Clean __pycache__ at test start to ensure fresh imports
cleanup_pycache()

def test_aacp_sysvar_parsing(vsysvar_path: str, json_cache: str):
    """Tests the AACP SysVar Parser's ability to extract struct data from .vsysvar files."""
    log.info("🚀 Starting AACP SysVar Parser Test...")

    if not os.path.exists(vsysvar_path):
        log.error(f"❌ vsysvar file not found at {vsysvar_path}")
        return

    # 1. Initialize and Parse into RAM
    parser = AacpSysVarParser(vsysvar_path)
    aacp_dict = parser.parse()
    
    if not aacp_dict or "Summary" not in aacp_dict:
        log.error("❌ Parsing failed. AACP Dictionary is empty or malformed.")
        return

    # Extract the actual signal count from the Summary block
    summary = aacp_dict.get("Summary", {})
    total_signals = summary.get("Total_Signals_Found", 0)
    log.info(f"✅ Successfully parsed {total_signals} signals from struct members into memory.")

    # 2. Verify Hierarchical Signal Data
    data = aacp_dict.get("DATA", {})
    if data:
        # Get a sample struct path (the keys in DATA)
        sample_struct_path = list(data.keys())[0]
        struct_content = data[sample_struct_path]
        
        log.info(f"🔍 Validating Sample Struct: {sample_struct_path}")
        log.debug(f"📂 Struct contains {len(struct_content)} members.")
        
        # Log the first member details to verify BitCount and Encoding
        if struct_content:
            first_member = list(struct_content.keys())[0]
            log.debug(f"📊 Sample Member [{first_member}]: {struct_content[first_member]}")
    else:
        log.warning("⚠️ No struct data found in the parsed output.")

    # 3. Test Disk Dump (Simulating Dev Mode)
    parser.to_json_file(json_cache, write_allowed=True)
    
    if os.path.exists(json_cache):
        log.info(f"✅ Cache successfully dumped to {json_cache}")
    else:
        log.error("❌ Failed to dump cache to disk.")

if __name__ == "__main__":
    # Update these paths based on your local directory structure
    AACP_VSYSVAR_FILE = "../aacp.vsysvar"
    CACHE_FILE = "aacp_sysvar_cache.json"
    
    test_aacp_sysvar_parsing(AACP_VSYSVAR_FILE, CACHE_FILE)
