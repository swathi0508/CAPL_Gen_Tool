import os
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from logger import log

pd.set_option('future.no_silent_downcasting', True)

class CaplSomeipFFToCanBasicFuncAndVarsGenerator:
    def __init__(self, template_dir: str = "."):
        """
        Initializes the generator and sets up the Jinja2 environment.
        """
        self.env = Environment(
            loader=FileSystemLoader(template_dir), 
            trim_blocks=True, 
            lstrip_blocks=True
        )
        self.var_template = "variables_template.j2"
        self.func_template = "someip_ff_to_can_basic_functions_template.j2"

    def render(self, data_frames: dict, test_type: str, output_root: str):
        """
        Reads from provided dataframes, processes target rows matching test_type, and renders the CAPL files.
        """
        log.info(f"Processing data for {test_type}...")
        
        # 1. Combine and Extract DataFrames from the dictionary
        target_sheets = ['E2E_CAN_PARSED', 'E2E_ETH_PARSED']
        valid_dfs = []
        for s in target_sheets:
            if s in data_frames:
                df_temp = data_frames[s].copy()
                df_temp.columns = df_temp.columns.str.strip()
                valid_dfs.append(df_temp)

        if not valid_dfs:
            log.warning(f"No valid data frames found for sheets: {target_sheets}")
            return

        df = pd.concat(valid_dfs, ignore_index=True)

        requirements = []
        
        # Dictionaries to filter out duplicate variables across requirements
        standard_vars_dict = {}
        can_enums_dict = {}
        eth_enums_dict = {}

        for index, row in df.iterrows():
            # --- Process rows matching the parameterized test_type ---
            row_test_type = str(row.get('TEST_TYPE', '')).strip()
            if row_test_type != test_type:
                continue
            # ----------------------------------------------------------------

            basic_func_name = str(row.get('BASIC_FUNCTION_NAME', f'Test_{index}')).strip()
            
            can_port = str(row.get('CAN_PORT', f'UnknownCAN_{index}')).strip()
            someip_port = str(row.get('SOMEIP_PORT', f'UnknownETH_{index}')).strip()
            attr_val = str(row.get('ATTRIBUTE_VALUE', f'UnknownAttr_{index}')).strip()

            is_enum_str = str(row.get('IS_ENUM', 'FALSE')).strip().upper()
            is_enum = (is_enum_str == 'TRUE')

            is_topic_attr_str = str(row.get('SOMEIP_TOPIC_ATTRIBUTE', 'FALSE')).strip().lower()
            is_topic_attr = (is_topic_attr_str == 'value_state')

            # Safely extract CAN limits
            can_min = row.get('COMPUTED_CAN_VALUE_MIN', 0.0)
            can_mid = row.get('COMPUTED_CAN_VALUE_MID', 0.0)
            can_max = row.get('COMPUTED_CAN_VALUE_MAX', 0.0)
            
            # Safely extract SOMEIP FF explicit limits from the updated columns
            eth_min = row.get('COMPUTED_SOMEIP_FF_VALUE_MIN', row.get('COMPUTED_SOMEIP_VALUE_MIN', 0.0))
            eth_mid = row.get('COMPUTED_SOMEIP_FF_VALUE_MID', row.get('COMPUTED_SOMEIP_VALUE_MID', 0.0))
            eth_max = row.get('COMPUTED_SOMEIP_FF_VALUE_MAX', row.get('COMPUTED_SOMEIP_VALUE_MAX', 0.0))

            can_offset = row.get('CAN_OFFSET', 0)
            can_res = row.get('CAN_RESOLUTION', 1)

            # --- FIX: Ensure SOMEIP FF values map to generic SOMEIP columns for variables_template.j2 ---
            mapped_eth_min = eth_min if not pd.isna(eth_min) else row.get('COMPUTED_SOMEIP_VALUE_MIN', 0.0)
            mapped_eth_mid = eth_mid if not pd.isna(eth_mid) else row.get('COMPUTED_SOMEIP_VALUE_MID', 0.0)
            mapped_eth_max = eth_max if not pd.isna(eth_max) else row.get('COMPUTED_SOMEIP_VALUE_MAX', 0.0)
            # ---------------------------------------------------------------------------------------------

            # Datatype from SOMEIP_FF_DATATYPE column
            datatype = str(row.get('SOMEIP_FF_DATATYPE', '')).strip().lower()
            if not datatype or datatype == 'nan' or datatype == 'missing_data':
                resolution = str(row.get('SOMEIP_RESOLUTION', '1'))
                datatype = "float" if "." in resolution else "int"

            # Store unique variables required for the 'variables' block template
            if not is_enum:
                if can_port not in standard_vars_dict:
                    standard_vars_dict[can_port] = {
                        'CAN_PORT': can_port,
                        'COMPUTED_CAN_VALUE_MIN': can_min, 'COMPUTED_CAN_VALUE_MID': can_mid, 'COMPUTED_CAN_VALUE_MAX': can_max,
                        'CAN_OFFSET': can_offset, 'CAN_RESOLUTION': can_res,
                        'COMPUTED_SOMEIP_VALUE_MIN': mapped_eth_min, 'COMPUTED_SOMEIP_VALUE_MID': mapped_eth_mid, 'COMPUTED_SOMEIP_VALUE_MAX': mapped_eth_max,
                    }
            else:
                if not is_topic_attr:
                    if can_port not in can_enums_dict:
                        can_enums_dict[can_port] = {
                            'CAN_PORT': can_port,
                            'COMPUTED_CAN_VALUE_MIN': can_min, 'COMPUTED_CAN_VALUE_MID': can_mid, 'COMPUTED_CAN_VALUE_MAX': can_max
                        }
                    eth_key = f"{someip_port}_{attr_val}"
                    if eth_key not in eth_enums_dict:
                        eth_enums_dict[eth_key] = {
                            'SOMEIP_PORT': someip_port, 'ATTRIBUTE_VALUE': attr_val,
                            'COMPUTED_SOMEIP_VALUE_MIN': mapped_eth_min, 'COMPUTED_SOMEIP_VALUE_MID': mapped_eth_mid, 'COMPUTED_SOMEIP_VALUE_MAX': mapped_eth_max
                        }

            # Extracting specific Signal Name and Namespace details robustly
            full_sysvar = str(row.get('SOMEIP_DB_SIGNAL_NAME', 'Namespace::SignalName'))
            sysvar_parts = full_sysvar.split('::')
            ns = "::".join(sysvar_parts[:-1]) if len(sysvar_parts) > 1 else "EthernetCluster"
            name = sysvar_parts[-1]
            
            # Extracting the FF explicit DB signal name
            someip_ff_signal_name = str(row.get('SOMEIP_FF_DB_SIGNAL_NAME', '')).strip()
            if not someip_ff_signal_name or someip_ff_signal_name == 'nan':
                someip_ff_signal_name = full_sysvar # Safe fallback if empty
                
            # Extracting the ValueState parameters
            someip_ff_valuestate = str(row.get('SOMEIP_FF_DB_SIGNAL_VALUESTATE', '')).strip()
            someip_ff_control = str(row.get('SOMEIP_FF_DB_SIGNAL_CONTROL', '')).strip()

            # --- NEW: Extracting the specific Namespace and Variable parameters ---
            someip_ff_signame_namespace = str(row.get('SOMEIP_FF_SIGNAME_NAMESPACE', '')).strip()
            someip_ff_signame_variable = str(row.get('SOMEIP_FF_SIGNAME_VARIABLE', '')).strip()
            someip_ff_sigvaluestate_namespace = str(row.get('SOMEIP_FF_SIGVALUESTATE_NAMESPACE', '')).strip()
            someip_ff_sigvaluestate_variable = str(row.get('SOMEIP_FF_SIGVALUESTATE_VARIABLE', '')).strip()
            someip_ff_control_namespace = str(row.get('SOMEIP_FF_CONTROL_NAMESPACE', '')).strip()
            someip_ff_control_variable = str(row.get('SOMEIP_FF_CONTROL_VARIABLE', '')).strip()

            # Preparing requirement object for the basic function template
            requirements.append({
                'Basic_Function': basic_func_name,
                'CAN_PORT': can_port,
                'SOMEIP_PORT': someip_port,
                'ATTRIBUTE_VALUE': attr_val,
                'CAN_DB_SIGNAL_NAME': str(row.get('CAN_DB_SIGNAL_NAME', 'Unknown_CAN_Signal')),
                'IS_ENUM': is_enum_str,
                'SOMEIP_TOPIC_ATTRIBUTE': is_topic_attr_str,
                'SOMEIP_DB_SIGNAL_NAME': full_sysvar,
                'SOMEIP_FF_DB_SIGNAL_NAME': someip_ff_signal_name, 
                'SOMEIP_NS': ns,
                'SOMEIP_NAME': name,
                'SOMEIP_FF_DATATYPE': datatype, 
                'COMPUTED_SOMEIP_FF_VALUE_MIN': eth_min, 
                'COMPUTED_SOMEIP_FF_VALUE_MID': eth_mid, 
                'COMPUTED_SOMEIP_FF_VALUE_MAX': eth_max, 
                'SOMEIP_FF_DB_SIGNAL_VALUESTATE': someip_ff_valuestate,
                'SOMEIP_FF_DB_SIGNAL_CONTROL': someip_ff_control,
                'SOMEIP_FF_SIGNAME_NAMESPACE': someip_ff_signame_namespace,
                'SOMEIP_FF_SIGNAME_VARIABLE': someip_ff_signame_variable,
                'SOMEIP_FF_SIGVALUESTATE_NAMESPACE': someip_ff_sigvaluestate_namespace,
                'SOMEIP_FF_SIGVALUESTATE_VARIABLE': someip_ff_sigvaluestate_variable,
                'SOMEIP_FF_CONTROL_NAMESPACE': someip_ff_control_namespace,
                'SOMEIP_FF_CONTROL_VARIABLE': someip_ff_control_variable,
                'labels': ['Mid', 'Min', 'Max']
            })

        if not requirements:
            log.warning(f"No applicable rows found for test type {test_type}.")
            return

        # --- Filter out duplicate Basic Functions before passing to Jinja ---
        unique_requirements = []
        seen_funcs = set()
        for req in requirements:
            if req['Basic_Function'] not in seen_funcs:
                unique_requirements.append(req)
                seen_funcs.add(req['Basic_Function'])
        # --------------------------------------------------------------------------

        log.info("Data extracted successfully. Rendering Jinja2 templates...")

        # Setup standard output directories dynamically using output_root
        f_dir = Path(output_root) / "BASIC_FUNCTIONS"
        v_dir = Path(output_root) / "VARIABLES"
        os.makedirs(f_dir, exist_ok=True)
        os.makedirs(v_dir, exist_ok=True)

        output_path = str(f_dir / "someip_ff_to_can_basic_functions.cin")
        var_output_file = str(v_dir / "someip_ff_to_can_Variables.cin")

        try:
            # 1. Render Variables
            var_template = self.env.get_template(self.var_template)
            rendered_vars = var_template.render(
                standard_vars=list(standard_vars_dict.values()),
                can_enums=list(can_enums_dict.values()),
                eth_enums=list(eth_enums_dict.values())
            )

            # 2. Render Test Functions (Using the filtered unique list)
            func_template = self.env.get_template(self.func_template)
            rendered_funcs = func_template.render(
                requirements=unique_requirements
            )

            # 3. Save to separate files (Variables in one, Functions in the other)
            with open(var_output_file, 'w') as f_vars:
                f_vars.write(rendered_vars)
                
            with open(output_path, 'w') as f_funcs:
                f_funcs.write(rendered_funcs)

            log.info(f"Variables successfully generated at: {os.path.abspath(var_output_file)}")
            log.info(f"CAPL Basic Functions successfully generated at: {os.path.abspath(output_path)}")
            
        except Exception as e:
            log.exception(f"Logic Gen failed during template generation: {e}")

class CaplSomeipToCanBasicFuncAndVarsGenerator:
    def __init__(self, template_dir):
        self.env = Environment(loader=FileSystemLoader(template_dir))
        self.func_template = "someip_ff_to_can_basic_functions_template.j2"
        self.var_template = "variables_template.j2"

        # --- UPDATED TO MATCH NEW UNIFIED COLUMN NAMES ---
        self.j2_columns = [
            'CAN_PORT', 'CAN_DB_SIGNAL_NAME', 'SOMEIP_DB_SIGNAL_NAME',
            'SOMEIP_DB_SIGNAL_VALUESTATE', 'CAN_ENUM', 'SOMEIP_ENUM',
            'SOMEIP_PORT', 'ATTRIBUTE_VALUE', 'BASIC_FUNCTION_NAME',
            'CAN_OFFSET', 'CAN_RESOLUTION', 'IS_ENUM',
            'COMPUTED_CAN_VALUE_MIN', 'COMPUTED_CAN_VALUE_MID', 'COMPUTED_CAN_VALUE_MAX',
            'COMPUTED_SOMEIP_VALUE_MIN', 'COMPUTED_SOMEIP_VALUE_MID', 'COMPUTED_SOMEIP_VALUE_MAX'
        ]

    def _validate_and_clean(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        # Fill missing required columns
        missing_cols = [c for c in self.j2_columns if c not in df.columns]
        for c in missing_cols: df[c] = pd.NA

        # 1. Aggressive cleaner for MIN, MID, MAX, and ENUMS (Forces Integers)
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

        # 2. STRICT FLOAT CLEANER for OFFSET and RESOLUTION (Forces Decimals)
        def clean_float(val):
            if pd.isna(val) or str(val).strip() in ["", "N/A", "nan", "None", "MISSING_DATA"]:
                return "MISSING_DATA"
            try:
                # Casting to float forces Python to append '.0' if it is a whole number
                return str(float(val))
            except ValueError:
                return str(val).strip()

        # 3. Gentle cleaner for Strings / Names
        def clean_standard(val):
            if pd.isna(val) or str(val).strip() in ["", "N/A", "nan", "None", "MISSING_DATA"]:
                return "MISSING_DATA"
            return str(val).strip()

        # Apply specific logic based on the column name keywords
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

            # Run the column-aware cleaner
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
            # Force IS_ENUM to uppercase string to safely check True/False without typing issues
            actual_value_rows['IS_ENUM_STR'] = actual_value_rows['IS_ENUM'].astype(str).str.upper()

            # --- Physical/Standard Variables (Where IS_ENUM is False or Missing) ---
            std_vars_df = actual_value_rows[actual_value_rows['IS_ENUM_STR'] != "TRUE"].copy()
            std_vars = std_vars_df.drop_duplicates(subset=['CAN_PORT']).to_dict(orient='records')

            # --- Enum Variables (Where IS_ENUM is True) ---
            enum_base = actual_value_rows[actual_value_rows['IS_ENUM_STR'] == "TRUE"].copy()
            can_enums = enum_base.drop_duplicates(subset=['CAN_PORT']).to_dict(orient='records')
            eth_enums = enum_base.drop_duplicates(subset=['SOMEIP_PORT', 'ATTRIBUTE_VALUE']).to_dict(orient='records')

            # --- UNIQUE ETHERNET SIGNALS ---
            all_signals = pd.concat([full_df['SOMEIP_DB_SIGNAL_NAME'], full_df['SOMEIP_DB_SIGNAL_VALUESTATE']])
            unique_signals = sorted([s for s in all_signals.unique() if s != "MISSING_DATA"])

            # 5. RENDER OUTPUTS
            f_dir = Path(output_root) / "BASIC_FUNCTIONS"
            v_dir = Path(output_root) / "VARIABLES"
            os.makedirs(f_dir, exist_ok=True)
            os.makedirs(v_dir, exist_ok=True)

            # Render Functions File
            with open(f_dir / "someip_ff_to_can_basic_functions.cin", "w") as f:
                f.write(self.env.get_template(self.func_template).render(functions=func_records))

            # Render Variables File
            with open(v_dir / "someip_ff_to_can_variables.cin", "w") as f:
                f.write(self.env.get_template(self.var_template).render(
                    standard_vars=std_vars,
                    can_enums=can_enums,
                    eth_enums=eth_enums,
                    ethernet_signals=unique_signals
                ))

            log.info(f"Generated {len(func_records)} functions. ValueState metadata excluded.")

        except Exception as e:
            log.exception(f"Logic Gen failed: {e}")

