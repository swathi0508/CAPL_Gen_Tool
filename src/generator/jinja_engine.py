import sys
import os
import time
import pandas as pd
from pathlib import Path
from datetime import timedelta

# Ensure the src path is in sys.path for relative imports
current_file = Path(__file__).resolve()
src_path = current_file.parent.parent
if str(src_path) not in sys.path:
    sys.path.append(str(src_path))

from core.logger import log
from generator.CaplSignalValidationLibGenerator import CaplSignalValidationLibGenerator
from generator.CaplCampaignGenerator import CaplCampaignGenerator
from generator.CaplCanToSomeipBasicFuncAndVarsGenerator import CaplCanToSomeipBasicFuncAndVarsGenerator

class JinjaEngine:
    GENERATOR_REGISTRY = {
        "CAN->SOMEIP": CaplCanToSomeipBasicFuncAndVarsGenerator,
        # Future additions:
        # "SOMEIP->CAN": CaplSomeipToCanGenerator,
    }

    def __init__(self, output_root="Output_CAPL_Scripts"):
        current_file = Path(__file__).resolve()
        self.base_src_dir = current_file.parent.parent
        self.template_dir = self.base_src_dir / "templates"
        self.output_dir = self.base_src_dir.parent / output_root
        
        if not self.template_dir.exists():
            log.error(f"Template directory missing at: {self.template_dir}")
            raise FileNotFoundError(f"Missing templates folder at {self.template_dir}")

    def load_excel_data(self, excel_path: str) -> dict:
        """Loads all parsed sheets into memory once for lightning-fast generation."""
        log.info(f"Loading data from {Path(excel_path).name}...")
        try:
            xls = pd.ExcelFile(excel_path)
            # Find sheets processed by the Mapper Orchestrator
            sheets = [s for s in xls.sheet_names if s.endswith("_PARSED")]
            if not sheets:
                log.error("No '_PARSED' sheets found. Did you run the Pre-Processor?")
                return {}
            
            return {sheet: pd.read_excel(xls, sheet_name=sheet) for sheet in sheets}
        except Exception as e:
            log.error(f"Failed to read Excel: {e}")
            return {}

    def run(self, excel_path, json_path, category, test_type):
        overall_start = time.time()
        log.info(f"--- STARTING CAPL GENERATION: {category} | {test_type} ---")
        
        # 1. Load Data Once
        data_frames = self.load_excel_data(excel_path)
        if not data_frames: 
            return

        try:
            # 2. Generate Validation Lib
            lib_gen = CaplSignalValidationLibGenerator(json_path, self.template_dir)
            lib_gen.render(self.output_dir / "COMMON_FUNCTIONS")
            
            # 3. Generate Specific Logic (CAN->SOMEIP)
            gen_class = self.GENERATOR_REGISTRY.get(test_type)
            if gen_class:
                specialized_gen = gen_class(self.template_dir)
                specialized_gen.render(data_frames, test_type, self.output_dir)
            else:
                log.warning(f"No registered generator found for TEST_TYPE: {test_type}")
            
            # 4. Generate Campaign
            camp_gen = CaplCampaignGenerator(self.template_dir)
            camp_gen.generate(data_frames, category, test_type, self.output_dir)
            
            log.info(f"--- TOTAL TIME: {str(timedelta(seconds=round(time.time() - overall_start)))} ---")
        except Exception as e:
            log.exception(f"Engine Failure: {e}")