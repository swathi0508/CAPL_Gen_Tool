import pandas as pd
import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from core.logger import log

pd.set_option('future.no_silent_downcasting', True)

class CaplCanToSomeipBasicFuncAndVarsGenerator:
    def __init__(self, template_dir):
        self.env = Environment(loader=FileSystemLoader(template_dir))
        self.func_template = "can_to_someip_basic_functions_template.j2"
        self.var_template = "can_to_someip_variables_template.j2"
        
        self.j2_columns = [
            'CAN_PORT', 'CAN_DB_SIGNAL_NAME', 'SOMEIP_DB_SIGNAL_NAME', 
            'SOMEIP_DB_SIGNAL_VALUESTATE', 'CAN_ENUM', 'SOMEIP_ENUM',
            'SOMEIP_PORT', 'ATTRIBUTE_VALUE', 'BASIC_FUNCTION_NAME',
            'COMPUTED_CAN_MIN_PHY', 'COMPUTED_CAN_MID_PHY', 'COMPUTED_CAN_MAX_PHY',
            'CAN_OFFSET', 'CAN_RESOLUTION', 'COMPUTED_CAN_ENUM_MIN', 
            'COMPUTED_SOMEIP_ENUM_MIN', 'COMPUTED_CAN_ENUM_MID', 
            'COMPUTED_SOMEIP_ENUM_MID', 'COMPUTED_CAN_ENUM_MAX', 'COMPUTED_SOMEIP_ENUM_MAX'
        ]

    def _validate_and_clean(self, df: pd.DataFrame) -> pd.DataFrame:
        # Fill missing required columns
        missing_cols = [c for c in self.j2_columns if c not in df.columns]
        for c in missing_cols: df[c] = pd.NA

        # Replace variations of nulls
        df.replace(["", " ", "N/A", "nan", "None", "MISSING_DATA"], pd.NA, inplace=True)
        
        # We fill NaNs here so the deduplication logic sees string values
        return df.fillna("MISSING_DATA").astype(str)

    def render(self, data_frames: dict, test_type: str, output_root: str):
        try:
            # 1. Pick and Combine Sheets
            target_sheets = ['E2E_CAN_PARSED', 'E2E_ETH_PARSED']
            available_dfs = [data_frames[s] for s in target_sheets if s in data_frames]
            
            if not available_dfs:
                log.error(f"Required sheets {target_sheets} not found.")
                return

            df = pd.concat(available_dfs, ignore_index=True)
            df.columns = df.columns.str.strip()
            
            # 2. Filter by TEST_TYPE
            df = df[df['TEST_TYPE'].astype(str).str.strip() == test_type].copy()
            
            if df.empty:
                log.warning(f"No data for {test_type} in targeted sheets.")
                return

            # 3. CLEAN DATA (Preserving your specific null handling)
            df = self._validate_and_clean(df)

            # 4. BASIC FUNCTIONS: Filter out ValueState rows and deduplicate by Function Name
            func_df = df[~df['ATTRIBUTE_VALUE'].str.contains("ValueState", case=False)].copy()
            func_df = func_df.drop_duplicates(subset=['BASIC_FUNCTION_NAME'])
            func_records = func_df.to_dict(orient='records')

            # 5. VARIABLES: Strictly separate Standard (Physical) and Enum variables
            
            # --- Collection A: Physical/Standard Variables Only ---
            # Filter for rows that DO NOT have an Enum defined
            std_mask = (df['CAN_ENUM'] == "MISSING_DATA")
            std_vars_df = df[std_mask].copy()
            std_vars_df = std_vars_df.drop_duplicates(subset=['CAN_PORT'])
            std_vars = std_vars_df.to_dict(orient='records')

            # --- Collection B: Enum Variables (Decoupled) ---
            enum_mask = (df['CAN_ENUM'] != "MISSING_DATA") & (~df['ATTRIBUTE_VALUE'].str.contains("ValueState", case=False))
            enum_rows_df = df[enum_mask].copy()

            # 1. Unique CAN Enums: Keyed by CAN_PORT
            can_enums_df = enum_rows_df.drop_duplicates(subset=['CAN_PORT'])
            can_enums = can_enums_df.to_dict(orient='records')

            # 2. Unique SOME/IP Enums: Keyed by SOMEIP_PORT + ATTRIBUTE_VALUE
            eth_enums_df = enum_rows_df.drop_duplicates(subset=['SOMEIP_PORT', 'ATTRIBUTE_VALUE'])
            eth_enums = eth_enums_df.to_dict(orient='records')

            # --- RENDER ---
            f_dir = Path(output_root) / "BASIC_FUNCTIONS"
            v_dir = Path(output_root) / "VARIABLES"
            os.makedirs(f_dir, exist_ok=True)
            os.makedirs(v_dir, exist_ok=True)
            
            # Render Functions
            with open(f_dir / "can_to_someip_basic_functions.cin", "w") as f:
                f.write(self.env.get_template(self.func_template).render(functions=func_records))
            
            # Render Variables - CRITICAL: Passing can_enums and eth_enums keys correctly
            with open(v_dir / "can_to_someip_variables.cin", "w") as f:
                f.write(self.env.get_template(self.var_template).render(
                    standard_vars=std_vars, 
                    can_enums=can_enums,
                    eth_enums=eth_enums
                ))
                
            log.info(f"Generated {len(func_records)} functions and {len(std_vars) + len(can_enums) + len(eth_enums)} variables for {test_type}.")
            
        except Exception as e:
            log.exception(f"Logic Gen failed: {e}")