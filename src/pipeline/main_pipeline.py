import os
import time
from pathlib import Path
from datetime import timedelta

from core.logger import log
from mappers.mapper_orchestrator import MapperOrchestrator
from validators.cross_validator import CrossValidator
from generator.jinja_engine import JinjaEngine
from signals.can_parser import CANSignalParser
from signals.someip_event_parser import SomeIPEventParser

class CaplGenerationPipeline:
    """The central brain orchestrating Parsers, Mappers, Validators, and Generators."""

    def __init__(self, can_db_cache: str = "can_db_cache.json", eth_db_cache: str = "someip_db_cache.json"):
        self.can_db = can_db_cache
        self.eth_db = eth_db_cache

    def build_databases(self, raw_arxml_path: str) -> tuple[bool, bool]:
        """Parses the unified Raw ARXML into separate JSON caches. Returns (can_built, eth_built)."""
        can_built, eth_built = False, False
        try:
            if not os.path.exists(self.can_db) and os.path.exists(raw_arxml_path):
                log.info(f"⚙️ Parsing CAN Network from ARXML: {raw_arxml_path}")
                can_parser = CANSignalParser(raw_arxml_path)
                can_parser.to_json_file(self.can_db)
                can_built = True

            if not os.path.exists(self.eth_db) and os.path.exists(raw_arxml_path):
                log.info(f"⚙️ Parsing SOME/IP Network from ARXML: {raw_arxml_path}")
                eth_parser = SomeIPEventParser(raw_arxml_path)
                eth_parser.to_json_file(self.eth_db)
                eth_built = True
                
        except Exception as e:
            log.error(f"Failed to build database caches: {e}")
            raise
            
        return can_built, eth_built

    def run_preprocessing(self, input_excel: str, output_dir: str) -> str:
        """PHASE 1 & 2: Runs the Mappers and the Cross-Validator."""
        start_time = time.time()
        log.info("=== STARTING PRE-PROCESSING PIPELINE ===")
        
        input_path = Path(input_excel)
        out_path = Path(output_dir)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_excel}")
            
        out_path.mkdir(parents=True, exist_ok=True)
        base_name = input_path.name.replace(".xlsx", "_Intermediate.xlsx")
        intermediate_excel = out_path / base_name

        try:
            # 1. Map requirements
            log.info("-> Phase 1: Mapping Databases to Requirements")
            orchestrator = MapperOrchestrator(self.can_db, self.eth_db)
            orchestrator.process_file(str(input_path), str(out_path))

            if not intermediate_excel.exists():
                raise RuntimeError("Mapper failed to create the Intermediate Excel file.")

            # 2. Compute Limits and Validate
            log.info("-> Phase 2: Cross-Validating Signals & Computing Bounds")
            validator = CrossValidator(orchestrator.can_mapper.db, orchestrator.eth_mapper.db)
            validator.process_sheet(str(intermediate_excel), "E2E_CAN_PARSED", is_can_sheet=True)
            validator.process_sheet(str(intermediate_excel), "E2E_ETH_PARSED", is_can_sheet=False)

            elapsed = str(timedelta(seconds=round(time.time() - start_time)))
            log.info(f"=== PRE-PROCESSING COMPLETE ({elapsed}) ===")
            return str(intermediate_excel)

        except Exception as e:
            log.exception(f"Fatal error during Pre-Processing: {e}")
            raise

    def run_generation(self, intermediate_excel: str, output_dir: str, category: str, test_type: str):
        """PHASE 3: Runs the Jinja Engine to build CAPL code."""
        start_time = time.time()
        log.info(f"=== STARTING CAPL GENERATION ({category} | {test_type}) ===")
        
        if not os.path.exists(intermediate_excel):
            raise FileNotFoundError(f"Intermediate file not found: {intermediate_excel}")

        try:
            engine = JinjaEngine(output_root=output_dir)
            engine.run(intermediate_excel, self.eth_db, category, test_type)

            elapsed = str(timedelta(seconds=round(time.time() - start_time)))
            log.info(f"=== GENERATION COMPLETE ({elapsed}) ===")
            
        except Exception as e:
            log.exception(f"Fatal error during Generation: {e}")
            raise

    def run_full_headless_flow(self, input_excel: str, out_dir: str, category: str, test_type: str, raw_arxml: str):
        """Used strictly by the CLI to run everything top-to-bottom in one shot."""
        self.build_databases(raw_arxml)
        intermediate_excel = self.run_preprocessing(input_excel, out_dir)
        self.run_generation(intermediate_excel, out_dir, category, test_type)