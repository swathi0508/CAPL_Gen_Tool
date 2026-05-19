import os
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from logger import log

pd.set_option('future.no_silent_downcasting', True)

class CaplCanToSomeipAacpBasicFuncAndVarsGenerator:
    def __init__(self, template_dir):
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            trim_blocks=True, 
            lstrip_blocks=True
        )
        self.func_template = "can_to_someip_aacp_basic_functions_template.j2"
        self.var_template = "variables_template.j2"

        self.j2_columns = [
            'CAN_PORT', 'CAN_DB_SIGNAL_NAME', 'SOMEIP_DB_SIGNAL_NAME',
            'SOMEIP_DB_SIGNAL_VALUESTATE', 'CAN_ENUM', 'SOMEIP_ENUM',
            'SOMEIP_PORT', 'ATTRIBUTE_VALUE', 'BASIC_FUNCTION_NAME',
            'CAN_OFFSET', 'CAN_RESOLUTION', 'IS_ENUM',
            'COMPUTED_CAN_VALUE_MIN', 'COMPUTED_CAN_VALUE_MID', 'COMPUTED_CAN_VALUE_MAX',
            'COMPUTED_SOMEIP_VALUE_MIN', 'COMPUTED_SOMEIP_VALUE_MID', 'COMPUTED_SOMEIP_VALUE_MAX',
            'COMPUTED_AACP_VALUE_MIN', 'COMPUTED_AACP_VALUE_MID', 'COMPUTED_AACP_VALUE_MAX',
            'AACP_SIGNAME_DAQ', 'AACP_DATATYPE', 'AACP_DB_SIGNAL_NAME',
            'AACP_SIGNAME_NAMESPACE', 'AACP_SIGNAME_VARIABLE', 'AACP_DB_SIGNAL_VALUESTATE',
            'AACP_SIGVALUESTATE_NAMESPACE', 'AACP_SIGVALUESTATE_VARIABLE'   
        ]

    def _validate_and_clean(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        missing_cols = [c for c in self.j2_columns if c not in df.columns]
        for c in missing_cols: df[c] = pd.NA

        def clean_bounds(val):
            if pd.isna(val) or str(val).strip() in ["", "N/A", "nan", "None", "MISSING_DATA"]:
                return "MISSING_DATA"
            if isinstance(val, float) and val.is_integer():
                return str(int(val))
            if isinstance(val, str) and val.endswith(".0"):
                try:
                    float(val)
                    return val[:-2]
                except ValueError:
                    pass
            return str(val).strip()

        def clean_float(val):
            if pd.isna(val) or str(val).strip() in ["", "N/A", "nan", "None", "MISSING_DATA"]:
                return "MISSING_DATA"
            try:
                return str(float(val))
            except ValueError:
                return str(val).strip()

        def clean_standard(val):
            if pd.isna(val) or str(val).strip() in ["", "N/A", "nan", "None", "MISSING_DATA"]:
                return "MISSING_DATA"
            return str(val).strip()

        for col in df.columns:
            if any(kw in col.upper() for kw in ['MIN', 'MID', 'MAX', 'ENUM']):
                df[col] = df[col].apply(clean_bounds)
            elif any(kw in col.upper() for kw in ['OFFSET', 'RESOLUTION']):
                df[col] = df[col].apply(clean_float)
            else:
                df[col] = df[col].apply(clean_standard)

        return df

    def render(self, data_frames: dict, test_type: str, output_root: str):
        try:
            target_sheets = ['E2E_CAN_PARSED', 'E2E_ETH_PARSED']
            valid_dfs = []
            for s in target_sheets:
                if s in data_frames:
                    df_temp = data_frames[s].copy()
                    df_temp.columns = df_temp.columns.str.strip()
                    df_filtered = df_temp[df_temp['TEST_TYPE'].astype(str).str.strip() == test_type]
                    valid_dfs.append(df_filtered)

            if not valid_dfs:
                log.warning(f"No data for {test_type} in {target_sheets}")
                return

            full_df = pd.concat(valid_dfs, ignore_index=True)
            full_df = self._validate_and_clean(full_df)

            if full_df.empty:
                return

            actual_value_rows = full_df[~full_df['ATTRIBUTE_VALUE'].str.contains("ValueState", case=False)].copy()

            if actual_value_rows.empty:
                log.error(f"No actual value rows found after filtering ValueState for {test_type}.")
                return
            
            # Ensure AACP values are passed to SOMEIP columns so variables_template.j2 does not default to 0
            for stat in ['MIN', 'MID', 'MAX']:
                someip_col = f'COMPUTED_SOMEIP_VALUE_{stat}'
                aacp_col = f'COMPUTED_AACP_VALUE_{stat}'
                
                if aacp_col in actual_value_rows.columns:
                    if someip_col not in actual_value_rows.columns:
                        actual_value_rows[someip_col] = actual_value_rows[aacp_col]
                    else:
                        actual_value_rows[someip_col] = actual_value_rows.apply(
                            lambda row: row[aacp_col] if pd.isna(row[someip_col]) or str(row[someip_col]).strip() in ["", "MISSING_DATA"] else row[someip_col],
                            axis=1
                        )

            actual_value_rows['BASIC_FUNCTION_NAME'] = actual_value_rows['BASIC_FUNCTION_NAME'].astype(str).str.strip()
            actual_value_rows = actual_value_rows.sort_values(by=['BASIC_FUNCTION_NAME', 'CAN_PORT'])
            
            func_df = actual_value_rows.drop_duplicates(subset=['BASIC_FUNCTION_NAME'], keep='first')
            func_records = func_df.to_dict(orient='records')

            actual_value_rows['IS_ENUM_STR'] = actual_value_rows['IS_ENUM'].astype(str).str.upper()

            std_vars_df = actual_value_rows[actual_value_rows['IS_ENUM_STR'] != "TRUE"].copy()
            std_vars = std_vars_df.drop_duplicates(subset=['CAN_PORT']).to_dict(orient='records')

            enum_base = actual_value_rows[actual_value_rows['IS_ENUM_STR'] == "TRUE"].copy()
            can_enums = enum_base.drop_duplicates(subset=['CAN_PORT']).to_dict(orient='records')
            eth_enums = enum_base.drop_duplicates(subset=['SOMEIP_PORT', 'ATTRIBUTE_VALUE']).to_dict(orient='records')

            all_signals = pd.concat([full_df['SOMEIP_DB_SIGNAL_NAME'], full_df['SOMEIP_DB_SIGNAL_VALUESTATE']])
            unique_signals = sorted([s for s in all_signals.unique() if s != "MISSING_DATA"])

            f_dir = Path(output_root) / "BASIC_FUNCTIONS"
            v_dir = Path(output_root) / "VARIABLES"
            os.makedirs(f_dir, exist_ok=True)
            os.makedirs(v_dir, exist_ok=True)

            with open(f_dir / "can_to_someip_aacp_basic_functions.can", "w") as f:
                f.write(self.env.get_template(self.func_template).render(functions=func_records))

            with open(v_dir / "can_to_someip_aacp_variables.cin", "w") as f:
                f.write(self.env.get_template(self.var_template).render(
                    standard_vars=std_vars,
                    can_enums=can_enums,
                    eth_enums=eth_enums,
                    ethernet_signals=unique_signals
                ))

            log.info(f"Generated {len(func_records)} unique functions. ValueState metadata excluded.")

        except Exception as e:
            log.exception(f"Logic Gen failed: {e}")