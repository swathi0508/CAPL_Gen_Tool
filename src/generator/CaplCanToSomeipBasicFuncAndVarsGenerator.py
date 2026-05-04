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
        """Aggregates errors to prevent log flooding and enforces MISSING_DATA triggers."""
        missing_cols = [c for c in self.j2_columns if c not in df.columns]
        if missing_cols:
            log.error(f"Logic Gen: Missing columns injected as MISSING_DATA -> {missing_cols}")
            for c in missing_cols: df[c] = pd.NA

        # Anti-spam logging: count missing cells per column
        for col in self.j2_columns:
            empty_mask = df[col].isna() | (df[col].astype(str).str.strip() == "") | (df[col] == "N/A")
            empty_count = empty_mask.sum()
            if empty_count > 0:
                log.warning(f"Logic Gen: Column '{col}' is missing data in {empty_count} rows. (Will trigger compile crash)")

        # Convert empty strings, "N/A" (from validator), and actual nulls to MISSING_DATA
        df.replace(["", "N/A", "nan", "None"], pd.NA, inplace=True)
        return df.fillna("MISSING_DATA").astype(str)

    def render(self, data_frames: dict, test_type: str, output_root: str):
        try:
            # Combine all available parsed sheets safely
            df = pd.concat(data_frames.values(), ignore_index=True)
            df.columns = df.columns.str.strip()
            
            if 'TEST_TYPE' not in df.columns:
                log.error("TEST_TYPE column missing from sheets.")
                return
                
            df['TEST_TYPE'] = df['TEST_TYPE'].astype(str).str.strip()
            df = df[df['TEST_TYPE'] == test_type].copy()
            
            if df.empty:
                log.warning(f"No data found for TEST_TYPE: {test_type}. Skipping generation.")
                return

            df = self._validate_and_clean(df)

            # --- RENDER BASIC FUNCTIONS ---
            f_dir = Path(output_root) / "BASIC_FUNCTIONS"
            os.makedirs(f_dir, exist_ok=True)
            with open(f_dir / "can_to_someip_basic_functions.cin", "w") as f:
                f.write(self.env.get_template(self.func_template).render(functions=df.to_dict(orient='records')))
            
            # --- RENDER VARIABLES (Deduplicated per Signal) ---
            v_dir = Path(output_root) / "VARIABLES"
            os.makedirs(v_dir, exist_ok=True)
            var_df = df.drop_duplicates(subset=['CAN_PORT'])
            
            # Split data based on presence of ENUMs
            std_vars = var_df[var_df['CAN_ENUM'] == "MISSING_DATA"].to_dict(orient='records')
            enum_vars = var_df[var_df['CAN_ENUM'] != "MISSING_DATA"].to_dict(orient='records')
            
            with open(v_dir / "can_to_someip_variables.cin", "w") as f:
                f.write(self.env.get_template(self.var_template).render(standard_vars=std_vars, enum_vars=enum_vars))
                
            log.info(f"Logic & Variables generation finished for {test_type}.")
        except Exception as e:
            log.exception(f"Logic Gen failed: {e}")