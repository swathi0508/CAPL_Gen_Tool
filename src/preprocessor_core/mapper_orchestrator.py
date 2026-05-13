import os
import pandas as pd
from logger import log
from preprocessor_core.common_processor import CommonProcessor

class MapperOrchestrator:
    """Coordinates the 7-step mapping sequence into in-memory DataFrames."""

    def __init__(self, can_db_data: dict, eth_db_data: dict):
        self.processor = CommonProcessor(can_db_data, eth_db_data)

    def process_to_dataframes(self, input_excel: str) -> dict:
        """
        Executes the finalized 7-step orchestration for input requirements.
        """
        log.info(f"Starting 7-step orchestration for: {os.path.basename(input_excel)}")
        
        xls = pd.ExcelFile(input_excel)
        sheets_to_process = [s for s in xls.sheet_names if s.strip().upper() in ["E2E_ETH", "E2E_CAN"]]
        
        final_results = {}

        for sheet_name in sheets_to_process:
            log.info(f"Processing sheet: {sheet_name}")
            df_raw = pd.read_excel(xls, sheet_name=sheet_name)
            
            # --- THE 7 STEP SEQUENCE (Aligned with CommonProcessor) ---
            # Extract the test_type once per sheet
            current_test_type = str(df_raw["TEST_TYPE"].iloc[0]).upper() if not df_raw.empty else ""

            # STEP 1: Copy necessary columns from Original requirements
            df = self.processor.copy_requirement_columns(df_raw, sheet_name)
            
            # STEP 2: Append and initialize Additional Columns
            df = self.processor.define_additional_columns(df)
            
            # STEP 3: Derive CAN Cluster
            df = self.processor.derive_can_cluster(df)
            
            # STEP 4: Compute Basic Function Name
            df = self.processor.derive_basic_function_names(df)
            
            # STEP 5: Signal Resolution (Map raw/phys from DB)
            df = self.processor.resolve_can_signals_from_db(df, current_test_type)
            df = self.processor.resolve_someip_signals_from_db(df, current_test_type)
            
            # STEP 6: ENUM Resolution (Orchestrates single vs dual signal logic)
            df = self.processor.resolve_enum_mappings(df, current_test_type)
            
            # STEP 7: Physical Range Resolution (Non-Enums only)
            df = self.processor.resolve_phys_ranges(df, current_test_type)
            
            final_results[f"{sheet_name.upper()}_PARSED"] = df

        log.info("Completed 7-step orchestration sequence.")
        return final_results
    