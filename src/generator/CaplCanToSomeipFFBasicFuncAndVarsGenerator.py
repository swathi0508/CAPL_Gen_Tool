import os
from pathlib import Path
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from core.logger import log

class CaplCanToSomeipFFBasicFuncAndVarsGenerator:
    def __init__(self, template_dir: str = "."):
        """
        Initializes the generator and sets up the Jinja2 environment.
        """
        # trim_blocks and lstrip_blocks keeps the layout perfectly matching your template layout
        self.env = Environment(
            loader=FileSystemLoader(template_dir), 
            trim_blocks=True, 
            lstrip_blocks=True
        )
        self.var_template = "variables_template.j2"
        self.func_template = "can_to_someipff_basic_functions_template.j2"

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
            # --- NEW: Process rows matching the parameterized test_type ---
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
            
            # Safely extract CAN limits
            can_min = row.get('COMPUTED_CAN_VALUE_MIN', 0.0)
            can_mid = row.get('COMPUTED_CAN_VALUE_MID', 0.0)
            can_max = row.get('COMPUTED_CAN_VALUE_MAX', 0.0)
            
            # Safely extract SOMEIP limits (Checking various header formats)
            eth_min = row.get('COMPUTED_SOMEIP_VALUE_MIN', row.get('COMPUTED_SOMEIP_FF_MIN_PHY', row.get('COMPUTED_SOMEIP_FF_MIN', 0.0)))
            eth_mid = row.get('COMPUTED_SOMEIP_VALUE_MID', row.get('COMPUTED_SOMEIP_FF_MID_PHY', row.get('COMPUTED_SOMEIP_FF_MID', 0.0)))
            eth_max = row.get('COMPUTED_SOMEIP_VALUE_MAX', row.get('COMPUTED_SOMEIP_FF_MAX_PHY', row.get('COMPUTED_SOMEIP_FF_MAX', 0.0)))

            can_offset = row.get('CAN_OFFSET', 0)
            can_res = row.get('CAN_RESOLUTION', 1)

            # Store unique variables required for the 'variables' block template
            if not is_enum:
                if can_port not in standard_vars_dict:
                    standard_vars_dict[can_port] = {
                        'CAN_PORT': can_port,
                        'COMPUTED_CAN_VALUE_MIN': can_min, 'COMPUTED_CAN_VALUE_MID': can_mid, 'COMPUTED_CAN_VALUE_MAX': can_max,
                        'CAN_OFFSET': can_offset, 'CAN_RESOLUTION': can_res,
                        'COMPUTED_SOMEIP_VALUE_MIN': eth_min, 'COMPUTED_SOMEIP_VALUE_MID': eth_mid, 'COMPUTED_SOMEIP_VALUE_MAX': eth_max,
                    }
            else:
                if can_port not in can_enums_dict:
                    can_enums_dict[can_port] = {
                        'CAN_PORT': can_port,
                        'COMPUTED_CAN_VALUE_MIN': can_min, 'COMPUTED_CAN_VALUE_MID': can_mid, 'COMPUTED_CAN_VALUE_MAX': can_max
                    }
                eth_key = f"{someip_port}_{attr_val}"
                if eth_key not in eth_enums_dict:
                    eth_enums_dict[eth_key] = {
                        'SOMEIP_PORT': someip_port, 'ATTRIBUTE_VALUE': attr_val,
                        'COMPUTED_SOMEIP_VALUE_MIN': eth_min, 'COMPUTED_SOMEIP_VALUE_MID': eth_mid, 'COMPUTED_SOMEIP_VALUE_MAX': eth_max
                    }

            # Extracting specific Signal Name and Namespace details robustly
            full_sysvar = str(row.get('SOMEIP_DB_SIGNAL_NAME', 'Namespace::SignalName'))
            sysvar_parts = full_sysvar.split('::')
            
            ns = "::".join(sysvar_parts[:-1]) if len(sysvar_parts) > 1 else "EthernetCluster"
            name = sysvar_parts[-1]
            
            # Defaulting datatype to float if resolution has decimals, otherwise int
            resolution = str(row.get('SOMEIP_RESOLUTION', '1'))
            datatype = "float" if "." in resolution else "int"

            # Preparing requirement object for the basic function template
            requirements.append({
                'Basic_Function': basic_func_name,
                'CAN_PORT': can_port,
                'SOMEIP_PORT': someip_port,
                'ATTRIBUTE_VALUE': attr_val,
                'CAN_DB_SIGNAL_NAME': str(row.get('CAN_DB_SIGNAL_NAME', 'Unknown_CAN_Signal')),
                'IS_ENUM': is_enum_str,
                'SOMEIP_DB_SIGNAL_NAME': full_sysvar,
                'SOMEIP_NS': ns,
                'SOMEIP_NAME': name,
                'DATATYPE': datatype,
                'labels': ['Mid', 'Min', 'Max'] # Mid -> Min -> Max iteration order
            })

        if not requirements:
            log.warning(f"No applicable rows found for test type {test_type}.")
            return

        log.info("Data extracted successfully. Rendering Jinja2 templates...")

        # Setup standard output directories dynamically using output_root
        f_dir = Path(output_root) / "BASIC_FUNCTIONS"
        v_dir = Path(output_root) / "VARIABLES"
        os.makedirs(f_dir, exist_ok=True)
        os.makedirs(v_dir, exist_ok=True)

        output_path = str(f_dir / "can_to_someipff_basic_functions.can")
        var_output_file = str(v_dir / "can_to_someipff_Variables.cin")

        try:
            # 1. Render Variables
            var_template = self.env.get_template(self.var_template)
            rendered_vars = var_template.render(
                standard_vars=list(standard_vars_dict.values()),
                can_enums=list(can_enums_dict.values()),
                eth_enums=list(eth_enums_dict.values())
            )

            # 2. Render Test Functions
            func_template = self.env.get_template(self.func_template)
            rendered_funcs = func_template.render(
                requirements=requirements
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