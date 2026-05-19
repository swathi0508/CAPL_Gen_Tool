import sys
import time
from datetime import timedelta
from pathlib import Path

# Ensure the src path is in sys.path for relative imports
current_file = Path(__file__).resolve()
src_path = current_file.parent.parent
if str(src_path) not in sys.path:
    sys.path.append(str(src_path))

from logger import log
from generator.CaplCampaignGenerator import CaplCampaignGenerator
from generator.CaplCanToSomeipBasicFuncAndVarsGenerator import CaplCanToSomeipBasicFuncAndVarsGenerator
from generator.CaplSomeipToCanBasicFuncAndVarsGenerator import CaplSomeipToCanBasicFuncAndVarsGenerator
from generator.CaplCanToSomeipAacpBasicFuncAndVarsGenerator import CaplCanToSomeipAacpBasicFuncAndVarsGenerator
from generator.CaplSignalValidationLibGenerator import CaplSignalValidationLibGenerator


class JinjaEngine:
    GENERATOR_REGISTRY = {
        "CAN->SOMEIP": CaplCanToSomeipBasicFuncAndVarsGenerator,
        "CAN->SOMEIP_AACP": CaplCanToSomeipAacpBasicFuncAndVarsGenerator,
        # Future additions:
        "SOMEIP->CAN": CaplSomeipToCanBasicFuncAndVarsGenerator,
    }

    def __init__(self, output_root="Output_CAPL_Scripts"):
        current_file = Path(__file__).resolve()
        self.base_src_dir = current_file.parent.parent

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            self.template_dir = Path(sys._MEIPASS) / "templates"
            app_root = Path(sys.executable).resolve().parent
        else:
            self.template_dir = self.base_src_dir / "templates"
            app_root = self.base_src_dir.parent

        self.output_dir = app_root / output_root

        if not self.template_dir.exists():
            log.error(f"Template directory missing at: {self.template_dir}")
            raise FileNotFoundError(f"Missing templates folder at {self.template_dir}")

    def run_from_memory(self, data_frames: dict, eth_db_data: dict, category: str, test_type: str):
        """Generates CAPL code directly from the in-memory DataFrames mapped by the pipeline."""
        overall_start = time.time()
        log.info(f"--- STARTING CAPL GENERATION: {category} | {test_type} ---")

        if not data_frames:
            log.error("No valid dataframes provided to the Jinja Engine.")
            return

        try:
            # 1. Generate Validation Lib (Now accepts RAM dictionary instead of JSON path)
            lib_gen = CaplSignalValidationLibGenerator(eth_db_data, self.template_dir)
            lib_gen.render(self.output_dir / "COMMON_FUNCTIONS")

            # 2. Generate Specific Logic (CAN->SOMEIP)
            gen_class = self.GENERATOR_REGISTRY.get(test_type)
            if gen_class:
                specialized_gen = gen_class(self.template_dir)
                specialized_gen.render(data_frames, test_type, self.output_dir)
            else:
                log.warning(f"No registered generator found for TEST_TYPE: {test_type}")

            # 3. Generate Campaign
            camp_gen = CaplCampaignGenerator(self.template_dir)
            camp_gen.generate(data_frames, category, test_type, self.output_dir)

            log.info(f"--- TOTAL GENERATION TIME: {str(timedelta(seconds=round(time.time() - overall_start)))} ---")
        except Exception as e:
            log.exception(f"Engine Failure: {e}")
