import logging
import os
import sys
import time
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

    def __init__(self, can_db_cache: str = "can_db_cache.json", 
                 eth_db_cache: str = "someip_db_cache.json", 
                 someip_ff_db_cache: str = "someip_ff_cache.json",
                 aacp_sysvar_vsysvar_db_cache: str = "aacp_sysvar_cache.json",
                 enable_log: bool = False):
        self.can_db = can_db_cache
        self.eth_db = eth_db_cache
        self.ff_db = someip_ff_db_cache
        self.aacp_db = aacp_sysvar_vsysvar_db_cache
        
        # State Tracking
        self.can_db_data = {}
        self.eth_db_data = {}
        self.ff_db_data = {}
        self.aacp_db_data = {}
        self.in_memory_dfs = {}
        self.missing_signals = []

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
        """Determines if the JSON cache is stale, belongs to a different source file, or size mismatched."""
        if not os.path.exists(cache_path) or not os.path.exists(source_file):
            return False
            
        if os.path.getmtime(source_file) > os.path.getmtime(cache_path):
            log.info(f"🔄 Source file timestamp modified. Cache '{os.path.basename(cache_path)}' is stale.")
            return False
            
        try:
            import re
            current_size = os.path.getsize(source_file)
            with open(cache_path, 'r', encoding='utf-8') as f:
                head = f.read(1024) 
                if os.path.basename(source_file) not in head:
                    log.info(f"🔄 Different source file selected. Invalidating cache '{os.path.basename(cache_path)}'.")
                    return False
                size_match = re.search(r'"Source_File_Size_Bytes":\s*(\d+)', head)
                if size_match:
                    cached_size = int(size_match.group(1))
                    if cached_size != current_size:
                        log.info(f"🔄 File size changed ({cached_size}b -> {current_size}b). Invalidating cache.")
                        return False
        except Exception as e:
            log.debug(f"Cache validation check failed, defaulting to re-parse: {e}")
            return False
        return True

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
                    can_parser.to_json_file(self.can_db, write_allowed=self.write_to_disk)
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
                    eth_parser.to_json_file(self.eth_db, write_allowed=self.write_to_disk)
                    eth_built = True

            # --- SOME/IP FF (SYSVAR) DATABASE ---
            if not self.ff_db_data:
                ff_parser = SomeipFFParser(someip_sysvar_xml)
                if self._is_cache_valid(self.ff_db, someip_sysvar_xml) and ff_parser.load_from_json(self.ff_db):
                    log.info(f"✅ Loaded SOME/IP FF from fast cache: {self.ff_db}")
                    self.ff_db_data = ff_parser.to_json_dict()
                elif os.path.exists(someip_sysvar_xml):
                    log.info(f"⚙️ Parsing SOME/IP FF from XML...")
                    self.ff_db_data = ff_parser.parse()
                    ff_parser.to_json_file(self.ff_db, write_allowed=self.write_to_disk)
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
                    aacp_parser.to_json_file(self.aacp_db, write_allowed=self.write_to_disk)
                    aacp_built = True
                
        except Exception as e:
            log.error(f"Failed to build or load database caches: {e}")
            raise
            
        return can_built, eth_built, ff_built, aacp_built

    def run_preprocessing_memory(self, input_excel: str, output_dir: str):
        """PHASE 1: Maps and processes data using Orchestrator (Steps 1-8)."""
        start_time = time.time()
        log.info("=== STARTING IN-MEMORY PRE-PROCESSING ===")

        if not self.can_db_data or not self.eth_db_data:
            raise RuntimeError("Databases not loaded into memory. Run build_databases first.")

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        self.missing_signals = []

        try:
            # --- THE ORCHESTRATION ---
            # Instantiate Processor and Orchestrator
            from preprocessor_core.common_processor import CommonProcessor # Ensure correct import path
            processor = CommonProcessor(self.can_db_data, self.eth_db_data)
            orchestrator = MapperOrchestrator(processor)
            
            # This single call now executes all 7 steps defined in Step-by-Step logic
            log.info("-> Executing 7-Step Mapping Pipeline...")
            self.in_memory_dfs = orchestrator.process_to_dataframes(input_excel)

            # --- MISSING SIGNALS CAPTURE ---
            # We keep this here as it is a validation step, not a mapping step.
            can_keys = {str(k).lower() for k in self.can_db_data.keys()}
            eth_keys = {str(v.get('Method', v.get('Attribute_Value', ''))).strip().lower() 
                        for v in self.eth_db_data.values() if isinstance(v, dict)}

            for sheet_name, df in self.in_memory_dfs.items():
                # Skip capture if sheet is empty or failed
                if df.empty: continue
                
                for _, row in df.iterrows():
                    req_id = str(row.get('E2E_ETH_REQ_ID', row.get('E2E_CAN_REQ_ID', 'Unknown'))).strip()
                    
                    # Check CAN Port existence
                    can_port = str(row.get('CAN_PORT', '')).strip()
                    if can_port and can_port.lower() not in ['nan', 'none', '', 'n/a']:
                        search_key = f"i{can_port.lower()}"
                        if search_key not in can_keys:
                            self.missing_signals.append(f"CAN Port '{can_port}' [Req: {req_id}]")

                    # Check ETH Attribute existence
                    eth_attr = str(row.get('ATTRIBUTE_VALUE', '')).strip()
                    if eth_attr and eth_attr.lower() not in ['nan', 'none', '', 'n/a']:
                        if eth_attr.lower() not in eth_keys:
                            self.missing_signals.append(f"ETH Attr '{eth_attr}' [Req: {req_id}]")
            
            self.missing_signals = list(dict.fromkeys(self.missing_signals))

            # --- DEV MODE DISK DUMP ---
            if self.write_to_disk:
                base_name = Path(input_excel).name.replace(".xlsx", "_Intermediate.xlsx")
                intermediate_excel = out_path / base_name
                log.info(f"🛠️ DEV MODE: Saving debug intermediate file to: {intermediate_excel}")
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