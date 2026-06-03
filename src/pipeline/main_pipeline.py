import logging
import os
import sys
import time
import tempfile
from datetime import timedelta
from pathlib import Path

import pandas as pd

from logger import log
from generator.jinja_engine import JinjaEngine
from preprocessor_core.mapper_orchestrator import MapperOrchestrator
from signal_parsers.can_parser import CANSignalParser
from signal_parsers.someip_event_parser import SomeIPEventParser
from signal_parsers.someip_ff_parser import SomeipFFParser
from signal_parsers.aacp_sysvar_parser import AacpSysVarParser 

class CaplGenerationPipeline:
    """The central brain orchestrating Parsers, Mappers, and Generators strictly in RAM."""

    def __init__(self, can_db_cache: str = str(Path(tempfile.gettempdir()) / ".capl_bolt_cache" / "can_db_cache.json"), 
                 someip_db_cache: str = str(Path(tempfile.gettempdir()) / ".capl_bolt_cache" / "someip_db_cache.json") , 
                 someip_ff_db_cache: str = str(Path(tempfile.gettempdir()) / ".capl_bolt_cache" /"someip_ff_cache.json"),
                 aacp_sysvar_db_cache: str = str(Path(tempfile.gettempdir()) / ".capl_bolt_cache" /"aacp_sysvar_cache.json"),
                 enable_log: bool = False,
                 no_cache: bool = False):
        self.can_db = can_db_cache
        self.eth_db = someip_db_cache
        self.ff_db = someip_ff_db_cache
        self.aacp_db = aacp_sysvar_db_cache
        self.no_cache = no_cache
        
        # State Tracking
        self.can_db_data = {}
        self.eth_db_data = {}
        self.someip_ff_db_data = {}
        self.aacp_db_data = {}
        self.in_memory_dfs = {}

        # Security Lock: If running as compiled EXE, forcefully block file dumping
        self.is_production = getattr(sys, 'frozen', False)
        self.enable_log = enable_log

    @property
    def write_to_disk(self) -> bool:
        """Returns True ONLY if user requested logs AND it is NOT a compiled production build."""
        return self.enable_log and not self.is_production

    def _configure_logging(self):
        """Adjusts verbosity based on environment."""
        if self.enable_log:
            log.setLevel(logging.DEBUG)
            if self.write_to_disk:
                log.info("🛠️ DEV MODE ACTIVE: High verbosity. Intermediate files WILL be saved to disk.")
            else:
                log.info("🛡️ PROD DEBUG ACTIVE: High verbosity. Intermediate file dumping is LOCKED.")
        else:
            log.setLevel(logging.INFO)

    def _is_cache_valid(self, cache_path: str, source_file: str) -> bool:
        """Determines if the secure cache is valid, stale, or bypassed."""
        
        if getattr(self, 'no_cache', False):
            log.info(f"🧹 --no-cache flag detected. Forcing fresh parse.")
            return False

        if not os.path.exists(cache_path):
            return False
            
        # The User Risk Warning (Cache-Only Mode)
        if not source_file or not os.path.exists(source_file):
            log.warning(f"⚠️ DANGER: Source file missing. Blind-loading secure cache '{os.path.basename(cache_path)}'.")
            return True
            
        if os.path.getmtime(source_file) > os.path.getmtime(cache_path):
            log.info(f"🔄 Source file timestamp modified. Cache '{os.path.basename(cache_path)}' is stale.")
            return False
            
        try:
            import zlib
            import json
            current_size = os.path.getsize(source_file)
            
            # Read and decompress just enough to check the Summary
            with open(cache_path, 'rb') as f:
                compressed_blob = f.read()
                
            json_str = zlib.decompress(compressed_blob).decode('utf-8')
            cache_data = json.loads(json_str)
            summary = cache_data.get("Summary", {})
            
            if summary.get("Source_File_Name") != os.path.basename(source_file):
                log.info(f"🔄 Different source file selected. Invalidating cache.")
                return False
                
            if summary.get("Source_File_Size_Bytes") != current_size:
                log.info(f"🔄 Source file size changed. Invalidating cache.")
                return False
                
        except Exception as e:
            log.debug(f"Secure cache validation failed, defaulting to re-parse: {e}")
            return False
            
        return True
    
    def _ensure_cache_dir(self, cache_path: str):
        """Safely creates the hidden .capl_cache/ directory if it doesn't exist."""
        parent_dir = os.path.dirname(cache_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

    def build_databases(self, raw_arxml_path: str, someip_sysvar_xml: str, aacp_sysvar_vsysvar: str) -> tuple[bool, bool, bool, bool]:
        """Loads databases from JSON cache if valid, otherwise parses from source files."""
        self._configure_logging()
        can_built, eth_built, ff_built, aacp_built = False, False, False, False
        
        try:
            # --- CAN DATABASE ---
            if not self.can_db_data:
                can_parser = CANSignalParser(raw_arxml_path)
                if self._is_cache_valid(self.can_db, raw_arxml_path) and can_parser.load_from_json(self.can_db):
                    log.info(f"✅ Loaded CAN Network from fast cache: {self.can_db}")
                    self.can_db_data = can_parser.to_json_dict()
                elif os.path.exists(raw_arxml_path):
                    log.info(f"⚙️ Parsing CAN Network from ARXML...")
                    self.can_db_data = can_parser.parse() 
                    self._ensure_cache_dir(self.can_db)
                    can_parser.to_json_file(self.can_db, write_allowed=True)
                    can_built = True

            # --- SOME/IP EVENT DATABASE ---
            if not self.eth_db_data:
                eth_parser = SomeIPEventParser(raw_arxml_path)
                if self._is_cache_valid(self.eth_db, raw_arxml_path) and eth_parser.load_from_json(self.eth_db):
                    log.info(f"✅ Loaded SOME/IP Network from fast cache: {self.eth_db}")
                    self.eth_db_data = eth_parser.to_json_dict()
                elif os.path.exists(raw_arxml_path):
                    log.info(f"⚙️ Parsing SOME/IP Network from ARXML...")
                    self.eth_db_data = eth_parser.parse()
                    self._ensure_cache_dir(self.eth_db)
                    eth_parser.to_json_file(self.eth_db, write_allowed=True)
                    eth_built = True

            # --- SOME/IP FF (SYSVAR) DATABASE ---
            if not self.someip_ff_db_data:
                ff_parser = SomeipFFParser(someip_sysvar_xml)
                if self._is_cache_valid(self.ff_db, someip_sysvar_xml) and ff_parser.load_from_json(self.ff_db):
                    log.info(f"✅ Loaded SOME/IP FF from fast cache: {self.ff_db}")
                    self.someip_ff_db_data = ff_parser.to_json_dict()
                elif os.path.exists(someip_sysvar_xml):
                    log.info(f"⚙️ Parsing SOME/IP FF from XML...")
                    self.someip_ff_db_data = ff_parser.parse()
                    self._ensure_cache_dir(self.ff_db)
                    ff_parser.to_json_file(self.ff_db, write_allowed=True)
                    ff_built = True

            # --- AACP SYSVAR DATABASE ---
            if not self.aacp_db_data:
                aacp_parser = AacpSysVarParser(aacp_sysvar_vsysvar)
                if self._is_cache_valid(self.aacp_db, aacp_sysvar_vsysvar) and aacp_parser.load_from_json(self.aacp_db):
                    log.info(f"✅ Loaded AACP SysVar from fast cache: {self.aacp_db}")
                    self.aacp_db_data = aacp_parser.to_json_dict()
                elif os.path.exists(aacp_sysvar_vsysvar):
                    log.info(f"⚙️ Parsing AACP SysVar from VSYSVAR...")
                    self.aacp_db_data = aacp_parser.parse()
                    self._ensure_cache_dir(self.aacp_db)
                    aacp_parser.to_json_file(self.aacp_db, write_allowed=True)
                    aacp_built = True
                
        except Exception as e:
            log.error(f"Failed to build or load database caches: {e}")
            raise
            
        return can_built, eth_built, ff_built, aacp_built

    def run_preprocessing_memory(self, input_excel: str, output_dir: str):
        """PHASE 1: Maps and processes data using Orchestrator (Steps 1-7)."""
        start_time = time.time()
        log.info("=== STARTING IN-MEMORY PRE-PROCESSING ===")

        # Safety Check: Ensure databases were built/loaded first
        if not self.can_db_data or not self.eth_db_data or not self.someip_ff_db_data:
            raise RuntimeError("Databases not loaded. Run build_databases() first.")

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        try:
            # --- THE ORCHESTRATION ---
            # We pass the raw dicts; Orchestrator handles the CommonProcessor internally.
            orchestrator = MapperOrchestrator(self.can_db_data, self.eth_db_data, self.someip_ff_db_data, self.aacp_db_data)
            
            log.info(f"-> Processing {os.path.basename(input_excel)}...")
            self.in_memory_dfs = orchestrator.process_to_dataframes(input_excel)

            # --- OPTIONAL: DEV MODE DISK DUMP ---
            # Only saves the intermediate file if logging is enabled and not a production build.
            if self.write_to_disk:
                base_name = Path(input_excel).name.replace(".xlsx", "_Intermediate.xlsx")
                intermediate_excel = out_path / base_name
                log.info(f"🛠️  DEV MODE: Dumping intermediate results to: {intermediate_excel}")
                with pd.ExcelWriter(intermediate_excel, engine='openpyxl') as writer:
                    for sheet_name, df in self.in_memory_dfs.items():
                        df.to_excel(writer, sheet_name=sheet_name, index=False)

            elapsed = str(timedelta(seconds=round(time.time() - start_time)))
            log.info(f"=== PRE-PROCESSING COMPLETE ({elapsed}) ===")
            return self.in_memory_dfs

        except Exception as e:
            log.exception(f"Fatal error during Pre-Processing: {e}")
            raise

    def run_generation(self, output_dir: str, category: str, test_type: str):
        """PHASE 2: Passes the memory dict directly to the Jinja Engine."""
        start_time = time.time()
        log.info(f"=== STARTING CAPL GENERATION ({category} | {test_type}) ===")
        if not self.in_memory_dfs:
            raise RuntimeError("Missing DataFrame memory. Run Preprocessing first.")
        try:
            engine = JinjaEngine(output_root=output_dir)
            engine.run_from_memory(self.in_memory_dfs, self.eth_db_data, category, test_type)
            elapsed = str(timedelta(seconds=round(time.time() - start_time)))
            log.info(f"=== GENERATION COMPLETE ({elapsed}) ===")
        except Exception as e:
            log.exception(f"Fatal error during Generation: {e}")
            raise

    def run_full_headless_flow(self, input_excel: str, out_dir: str, category: str, test_type: str, 
                               raw_arxml: str, someip_sysvar_xml: str, aacp_sysvar_vsysvar: str):
        """Used strictly by the CLI to run everything top-to-bottom in RAM."""
        self.build_databases(raw_arxml, someip_sysvar_xml, aacp_sysvar_vsysvar)
        self.run_preprocessing_memory(input_excel, out_dir)
        self.run_generation(out_dir, category, test_type)
