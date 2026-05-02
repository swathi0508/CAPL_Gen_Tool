import sys
import os
import time
import argparse
from pathlib import Path
from datetime import timedelta

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
    }

    def __init__(self, output_root="Output_CAPL_Scripts"):
        current_file = Path(__file__).resolve()
        self.base_src_dir = current_file.parent.parent
        self.template_dir = self.base_src_dir / "templates"
        self.output_dir = self.base_src_dir.parent / output_root
        
        if not self.template_dir.exists():
            log.error(f"Template directory missing at: {self.template_dir}")
            raise FileNotFoundError(f"Missing templates folder at {self.template_dir}")

    def run(self, excel_path, json_path, category, test_type):
        overall_start = time.time()
        log.info(f"--- STARTING CAPL GENERATION: {category} | {test_type} ---")
        try:
            lib_gen = CaplSignalValidationLibGenerator(json_path, self.template_dir)
            lib_gen.render(self.output_dir / "COMMON_FUNCTIONS")

            gen_class = self.GENERATOR_REGISTRY.get(test_type)
            if gen_class:
                specialized_gen = gen_class(excel_path, self.template_dir)
                specialized_gen.render(self.output_dir)

            camp_gen = CaplCampaignGenerator(excel_path, self.template_dir)
            camp_gen.generate(category, test_type, self.output_dir)

            log.info(f"--- TOTAL TIME: {str(timedelta(seconds=round(time.time() - overall_start)))} ---")
        except Exception as e:
            log.error(f"Engine Failure: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--excel", default=r"C:\poc\workspace_autosar\Input\Processed_AUTOSAR_INTERFACES_STATUS vECU 6.0.2.xlsx")
    parser.add_argument("--json", default=r"C:\poc\workspace_autosar\Input\someip_db_cache.json")
    parser.add_argument("--category", default="E2E_CAN")
    parser.add_argument("--type", default="CAN->SOMEIP")
    args = parser.parse_args()

    engine = JinjaEngine()
    engine.run(args.excel, args.json, args.category, args.type)

if __name__ == "__main__":
    main()
