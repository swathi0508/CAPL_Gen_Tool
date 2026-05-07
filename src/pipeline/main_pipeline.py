import sys
import os
import time
import logging
import pandas as pd
from pathlib import Path
from datetime import timedelta

from core.logger import log
from mappers.mapper_orchestrator import MapperOrchestrator
from validators.cross_validator import CrossValidator
from generator.jinja_engine import JinjaEngine
from signals.can_parser import CANSignalParser
from signals.someip_event_parser import SomeIPEventParser

class CaplGenerationPipeline:
    """The central brain orchestrating Parsers, Mappers, Validators, and Generators strictly in RAM."""

    def __init__(self, can_db_cache: str = "can_db_cache.json", eth_db_cache: str = "someip_db_cache.json", enable_log: bool = False):
        self.can_db = can_db_cache
        self.eth_db = eth_db_cache
        
        # State Tracking
        self.can_db_data = {}
        self.eth_db_data = {}
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

    def _is_cache_valid(self, cache_path: str, source_arxml: str) -> bool:
        """Determines if the JSON cache is stale, belongs to a different ARXML, or size mismatched."""
        if not os.path.exists(cache_path) or not os.path.exists(source_arxml):
            return False
            
        # 1. Timestamp Check (Fastest check)
        if os.path.getmtime(source_arxml) > os.path.getmtime(cache_path):
            log.info(f"🔄 ARXML timestamp modified. Cache '{os.path.basename(cache_path)}' is stale.")
            return False
            
        # 2. Deep Integrity Check: Name & File Size
        try:
            import re
            current_size = os.path.getsize(source_arxml)
            
            with open(cache_path, 'r', encoding='utf-8') as f:
                # Still reading only the first 1KB for O(1) lightning speed
                head = f.read(1024) 
                
                # Check A: Did the filename change?
                if os.path.basename(source_arxml) not in head:
                    log.info(f"🔄 Different ARXML selected. Invalidating cache '{os.path.basename(cache_path)}'.")
                    return False
                    
                # Check B: Did the file size change? (Extract size from the JSON string)
                size_match = re.search(r'"Source_File_Size_Bytes":\s*(\d+)', head)
                if size_match:
                    cached_size = int(size_match.group(1))
                    if cached_size != current_size:
                        log.info(f"🔄 ARXML file size changed ({cached_size}b -> {current_size}b). Invalidating cache.")
                        return False
                        
        except Exception as e:
            log.debug(f"Cache validation check failed, defaulting to re-parse: {e}")
            return False
            
        return True

    def build_databases(self, raw_arxml_path: str) -> tuple[bool, bool]:
        """Loads databases from JSON cache if valid, otherwise parses from ARXML."""
        self._configure_logging()
        can_built, eth_built = False, False
        
        try:
            # --- CAN DATABASE ---
            if not self.can_db_data:
                can_parser = CANSignalParser(raw_arxml_path)
                
                # Check if the cache is valid AND loads successfully
                if self._is_cache_valid(self.can_db, raw_arxml_path) and can_parser.load_from_json(self.can_db):
                    log.info(f"✅ Loaded CAN Network from fast cache: {self.can_db}")
                    self.can_db_data = can_parser.to_json_dict()
                
                # Fallback to ARXML parsing
                elif os.path.exists(raw_arxml_path):
                    log.info(f"⚙️ Parsing CAN Network from ARXML (Cache invalid or missing)...")
                    self.can_db_data = can_parser.parse() 
                    can_parser.to_json_file(self.can_db, write_allowed=self.write_to_disk)
                    can_built = True

            # --- SOME/IP DATABASE ---
            if not self.eth_db_data:
                eth_parser = SomeIPEventParser(raw_arxml_path)
                
                # Check if the cache is valid AND loads successfully
                if self._is_cache_valid(self.eth_db, raw_arxml_path) and eth_parser.load_from_json(self.eth_db):
                    log.info(f"✅ Loaded SOME/IP Network from fast cache: {self.eth_db}")
                    self.eth_db_data = eth_parser.to_json_dict()
                
                # Fallback to ARXML parsing
                elif os.path.exists(raw_arxml_path):
                    log.info(f"⚙️ Parsing SOME/IP Network from ARXML (Cache invalid or missing)...")
                    self.eth_db_data = eth_parser.parse()
                    eth_parser.to_json_file(self.eth_db, write_allowed=self.write_to_disk)
                    eth_built = True
                
        except Exception as e:
            log.error(f"Failed to build or load database caches: {e}")
            raise
            
        return can_built, eth_built

    def run_preprocessing_memory(self, input_excel: str, output_dir: str):
        """PHASE 1 & 2: Maps and Validates strictly via DataFrames."""
        start_time = time.time()
        log.info("=== STARTING IN-MEMORY PRE-PROCESSING ===")

        if not self.can_db_data or not self.eth_db_data:
            raise RuntimeError("Databases not loaded into memory. Run build_databases first.")

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize missing signals list for the GUI to pick up
        self.missing_signals = []
        
        try:
            # 1. Map requirements (Now returns dict of DataFrames)
            log.info("-> Phase 1: Mapping Databases to Requirements")
            orchestrator = MapperOrchestrator(self.can_db_data, self.eth_db_data)
            self.in_memory_dfs = orchestrator.process_to_dataframes(input_excel)

            # --- START OF MISSING SIGNALS CAPTURE ---
            can_keys = {str(k).lower() for k in self.can_db_data.keys()}
            eth_keys = {str(k).lower() for k in self.eth_db_data.keys()}

            for sheet_name, df in self.in_memory_dfs.items():
                for _, row in df.iterrows():
                    req_id = str(row.get('REQ ID', 'Unknown')).strip()
                    
                    # Check CAN Ports
                    can_port = str(row.get('CAN_PORT', '')).strip()
                    if can_port and can_port.lower() not in ['nan', 'none', '']:
                        search_key = f"i{can_port.lower()}"
                        if search_key not in can_keys:
                            self.missing_signals.append(f"CAN Port '{can_port}' [Req: {req_id}]")
                            log.warning(f"❌ MISSING CAN: {req_id} | Target: {search_key}")

                    # Check SOME/IP Attributes
                    eth_attr = str(row.get('ATTRIBUTE_VALUE', '')).strip()
                    if eth_attr and eth_attr.lower() not in ['nan', 'none', '']:
                        if eth_attr.lower() not in eth_keys:
                            self.missing_signals.append(f"ETH Attr '{eth_attr}' [Req: {req_id}]")
                            log.warning(f"❌ MISSING ETH: {req_id} | Target: {eth_attr.lower()}")
            
            # Deduplicate the list in case of duplicate requirements
            self.missing_signals = list(dict.fromkeys(self.missing_signals))
            # --- END OF MISSING SIGNALS CAPTURE ---

            # 2. Compute Limits and Validate
            log.info("-> Phase 2: Cross-Validating Signals & Computing Bounds")
            validator = CrossValidator(orchestrator.can_mapper.db, orchestrator.eth_mapper.db)
            
            if "E2E_CAN_PARSED" in self.in_memory_dfs:
                self.in_memory_dfs["E2E_CAN_PARSED"] = validator.process_dataframe(self.in_memory_dfs["E2E_CAN_PARSED"], is_can_sheet=True)
            if "E2E_ETH_PARSED" in self.in_memory_dfs:
                self.in_memory_dfs["E2E_ETH_PARSED"] = validator.process_dataframe(self.in_memory_dfs["E2E_ETH_PARSED"], is_can_sheet=False)

            # GATED FILE WRITE: Save intermediate Excel ONLY in Dev Mode
            if self.write_to_disk:
                base_name = Path(input_excel).name.replace(".xlsx", "_Intermediate.xlsx")
                intermediate_excel = out_path / base_name
                log.info(f"🛠️ DEV MODE: Saving debug intermediate file to: {intermediate_excel}")
                with pd.ExcelWriter(intermediate_excel, engine='openpyxl') as writer:
                    for sheet_name, df in self.in_memory_dfs.items():
                        df.to_excel(writer, sheet_name=sheet_name, index=False)

            elapsed = str(timedelta(seconds=round(time.time() - start_time)))
            log.info(f"=== PRE-PROCESSING COMPLETE ({elapsed}) ===")
            
            # Return the dfs (optional, but good practice)
            return self.in_memory_dfs

        except Exception as e:
            log.exception(f"Fatal error during Pre-Processing: {e}")
            raise

    def run_generation(self, output_dir: str, category: str, test_type: str):
        """PHASE 3: Passes the memory dict directly to the Jinja Engine."""
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

    def run_full_headless_flow(self, input_excel: str, out_dir: str, category: str, test_type: str, raw_arxml: str):
        """Used strictly by the CLI to run everything top-to-bottom in RAM."""
        self.build_databases(raw_arxml)
        self.run_preprocessing_memory(input_excel, out_dir)
        self.run_generation(out_dir, category, test_type)