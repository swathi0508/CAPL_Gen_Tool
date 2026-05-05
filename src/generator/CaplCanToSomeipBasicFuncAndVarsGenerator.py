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
        if df.empty:
            return df
            
        # Fill missing required columns
        missing_cols = [c for c in self.j2_columns if c not in df.columns]
        for c in missing_cols: df[c] = pd.NA

        # Replace variations of nulls
        df.replace(["", " ", "N/A", "nan", "None", "MISSING_DATA"], pd.NA, inplace=True)
        
        # We fill NaNs here so the deduplication logic sees string values
        return df.fillna("MISSING_DATA").astype(str)

    def render(self, data_frames: dict, test_type: str, output_root: str):
        try:
            # 1. Combine and Clean Sheets
            target_sheets = ['E2E_CAN_PARSED', 'E2E_ETH_PARSED']
            valid_dfs = []
            for s in target_sheets:
                if s in data_frames:
                    df_temp = data_frames[s].copy()
                    df_temp.columns = df_temp.columns.str.strip()
                    # Apply test_type filter immediately per sheet
                    df_filtered = df_temp[df_temp['TEST_TYPE'].astype(str).str.strip() == test_type]
                    valid_dfs.append(df_filtered)
            
            if not valid_dfs:
                log.warning(f"No data for {test_type} in {target_sheets}")
                return

            full_df = pd.concat(valid_dfs, ignore_index=True)
            full_df = self._validate_and_clean(full_df)

            if full_df.empty:
                return

            # 2. STRICT FILTER: Remove all ValueState metadata rows
            actual_value_rows = full_df[~full_df['ATTRIBUTE_VALUE'].str.contains("ValueState", case=False)].copy()

            if actual_value_rows.empty:
                log.error(f"No actual value rows found after filtering ValueState for {test_type}.")
                return

            # 3. GENERATE UNIQUE MASTER FUNCTIONS
            actual_value_rows = actual_value_rows.sort_values(by=['BASIC_FUNCTION_NAME', 'CAN_PORT'])
            func_df = actual_value_rows.drop_duplicates(subset=['BASIC_FUNCTION_NAME'])
            func_records = func_df.to_dict(orient='records')

            # 4. GENERATE VARIABLES
            # --- Physical/Standard Variables ---
            std_vars_df = actual_value_rows[actual_value_rows['CAN_ENUM'] == "MISSING_DATA"].copy()
            std_vars = std_vars_df.drop_duplicates(subset=['CAN_PORT']).to_dict(orient='records')

            # --- Enum Variables ---
            enum_base = actual_value_rows[actual_value_rows['CAN_ENUM'] != "MISSING_DATA"].copy()
            can_enums = enum_base.drop_duplicates(subset=['CAN_PORT']).to_dict(orient='records')
            eth_enums = enum_base.drop_duplicates(subset=['SOMEIP_PORT', 'ATTRIBUTE_VALUE']).to_dict(orient='records')

            # --- UNIQUE ETHERNET SIGNALS (NEW LOGIC) ---
            # Extract all signals from both relevant columns
            all_signals = pd.concat([full_df['SOMEIP_DB_SIGNAL_NAME'], full_df['SOMEIP_DB_SIGNAL_VALUESTATE']])
            # Filter out missing data and get unique list
            unique_signals = sorted([s for s in all_signals.unique() if s != "MISSING_DATA"])

            # 5. RENDER OUTPUTS
            f_dir = Path(output_root) / "BASIC_FUNCTIONS"
            v_dir = Path(output_root) / "VARIABLES"
            os.makedirs(f_dir, exist_ok=True)
            os.makedirs(v_dir, exist_ok=True)

            # Render Functions File
            with open(f_dir / "can_to_someip_basic_functions.cin", "w") as f:
                f.write(self.env.get_template(self.func_template).render(functions=func_records))

            # Render Variables File
            with open(v_dir / "can_to_someip_variables.cin", "w") as f:
                f.write(self.env.get_template(self.var_template).render(
                    standard_vars=std_vars, 
                    can_enums=can_enums,
                    eth_enums=eth_enums,
                    ethernet_signals=unique_signals  # Passing the new unique signals list
                ))

            log.info(f"Generated {len(func_records)} functions. ValueState metadata excluded.")

        except Exception as e:
            log.exception(f"Logic Gen failed: {e}")