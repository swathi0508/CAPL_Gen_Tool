import pandas as pd
import os
import time
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from core.logger import log

class CaplCanToSomeipBasicFuncAndVarsGenerator:
    def __init__(self, excel_path, template_dir):
        self.excel_path = excel_path
        self.env = Environment(loader=FileSystemLoader(template_dir))
        self.func_template = "can_to_someip_basic_functions_template.j2"
        self.var_template = "can_to_someip_variables_template.j2"

    def render(self, output_root):
        try:
            xls = pd.ExcelFile(self.excel_path)
            sheets = [s for s in xls.sheet_names if 'intermediate' in s.lower()]
            if not sheets:
                log.error("Logic Gen: No 'intermediate' sheets found.")
                return

            df = pd.concat([pd.read_excel(xls, sheet_name=s) for s in sheets], ignore_index=True)
            df.columns = df.columns.str.strip()
            
            # Filter for the specific test type
            df['TEST_TYPE'] = df['TEST_TYPE'].astype(str).str.strip()
            df = df[df['TEST_TYPE'] == 'CAN->SOMEIP'].copy()

            # Define every column the J2 templates depend on
            j2_columns = [
                'CAN_PORT', 'CAN_DB_SIGNAL_NAME', 'SOMEIP_DB_SIGNAL_NAME', 
                'SOMEIP_DB_SIGNAL_VALUESTATE', 'CAN_ENUM', 'SOMEIP_ENUM',
                'SOMEIP_PORT', 'ATTRIBUTE_VALUE', 'BASIC_FUNCTION_NAME',
                'COMPUTED_CAN_MIN_PHY', 'COMPUTED_CAN_MID_PHY', 'COMPUTED_CAN_MAX_PHY',
                'CAN_OFFSET', 'CAN_RESOLUTION', 'COMPUTED_CAN_ENUM_MIN', 
                'COMPUTED_SOMEIP_ENUM_MIN', 'COMPUTED_CAN_ENUM_MID', 
                'COMPUTED_SOMEIP_ENUM_MID', 'COMPUTED_CAN_ENUM_MAX', 'COMPUTED_SOMEIP_ENUM_MAX'
            ]

            # Validation Loop: Log errors for missing columns or empty cells
            for col in j2_columns:
                if col not in df.columns:
                    log.error(f"Logic Gen: Excel column '{col}' is MISSING entirely.")
                    df[col] = pd.NA
                
                # Identify rows where this specific column is empty
                empty_rows = df[df[col].isna()].index.tolist()
                for r_idx in empty_rows:
                    # Row index + 2 accounts for 0-indexing and header row in Excel
                    log.error(f"Logic Gen: EMPTY CELL at Row {r_idx+2}, Column '{col}'")

            # Final Cleanup: Replace all NaNs with string and force to string type
            df = df.fillna("MISSING_DATA").astype(str)

            # --- RENDER BASIC FUNCTIONS ---
            f_dir = Path(output_root) / "BASIC_FUNCTIONS"
            os.makedirs(f_dir, exist_ok=True)
            with open(f_dir / "can_to_someip_basic_functions.cin", "w") as f:
                f.write(self.env.get_template(self.func_template).render(functions=df.to_dict(orient='records')))

            # --- RENDER VARIABLES (Deduplicated per Signal) ---
            v_dir = Path(output_root) / "VARIABLES"
            os.makedirs(v_dir, exist_ok=True)
            var_df = df.drop_duplicates(subset=['CAN_PORT'])
            
            # Split data for the standard vs enum sections of the template
            std_vars = var_df[var_df['CAN_ENUM'] == "MISSING_DATA"].to_dict(orient='records')
            enum_vars = var_df[var_df['CAN_ENUM'] != "MISSING_DATA"].to_dict(orient='records')
            
            with open(v_dir / "can_to_someip_variables.cin", "w") as f:
                f.write(self.env.get_template(self.var_template).render(standard_vars=std_vars, enum_vars=enum_vars))

            log.info("Logic & Variables generation finished.")
        except Exception as e:
            log.error(f"Logic Gen failed silently: {e}")