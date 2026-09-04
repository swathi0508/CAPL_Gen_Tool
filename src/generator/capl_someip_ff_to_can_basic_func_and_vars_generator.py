import os
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from logger import log

pd.set_option("future.no_silent_downcasting", True)


class CaplSomeipFFToCanBasicFuncAndVarsGenerator:
    def __init__(self, template_dir: str = "."):
        """
        Initializes the generator and sets up the Jinja2 environment.
        """
        self.env = Environment(
            loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True
        )
        self.var_template = "variables_template.j2"
        self.func_template = "someipff_to_can_basic_functions_template.j2"

    def render(self, data_frames: dict, test_type: str, output_root: str):
        """
        Reads from provided dataframes, processes target rows
        matching test_type, and renders the CAPL files.
        """
        log.info(f"Processing data for {test_type}...")

        # 1. Combine and Extract DataFrames from the dictionary
        target_sheets = ["E2E_CAN_PARSED", "E2E_ETH_PARSED"]
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
            row_test_type = str(row.get("TEST_TYPE", "")).strip()
            if row_test_type != test_type:
                continue
            # ----------------------------------------------------------------

            basic_func_name = str(row.get("BASIC_FUNCTION_NAME", f"Test_{index}")).strip()

            can_port = str(row.get("CAN_PORT", f"UnknownCAN_{index}")).strip()
            someip_port = str(row.get("SOMEIP_PORT", f"UnknownETH_{index}")).strip()
            attr_val = str(row.get("ATTRIBUTE_VALUE", f"UnknownAttr_{index}")).strip()

            is_enum_str = str(row.get("IS_ENUM", "FALSE")).strip().upper()
            is_enum = is_enum_str == "TRUE"

            is_topic_attr_str = str(row.get("SOMEIP_TOPIC_ATTRIBUTE", "FALSE")).strip().lower()
            is_topic_attr = is_topic_attr_str == "value_state"

            # Safely extract CAN limits
            can_min = row.get("COMPUTED_CAN_VALUE_MIN", 0.0)
            can_mid = row.get("COMPUTED_CAN_VALUE_MID", 0.0)
            can_max = row.get("COMPUTED_CAN_VALUE_MAX", 0.0)

            # Safely extract SOMEIP FF explicit limits from the updated columns
            eth_min = row.get(
                "COMPUTED_SOMEIP_FF_VALUE_MIN", row.get("COMPUTED_SOMEIP_VALUE_MIN", 0.0)
            )
            eth_mid = row.get(
                "COMPUTED_SOMEIP_FF_VALUE_MID", row.get("COMPUTED_SOMEIP_VALUE_MID", 0.0)
            )
            eth_max = row.get(
                "COMPUTED_SOMEIP_FF_VALUE_MAX", row.get("COMPUTED_SOMEIP_VALUE_MAX", 0.0)
            )

            can_offset = row.get("CAN_OFFSET", 0)
            can_res = row.get("CAN_RESOLUTION", 1)

            # --- FIX: Ensure SOMEIP FF values map to generic SOMEIP columns
            #    for variables_template.j2 ---
            mapped_eth_min = (
                eth_min if not pd.isna(eth_min) else row.get("COMPUTED_SOMEIP_VALUE_MIN", 0.0)
            )
            mapped_eth_mid = (
                eth_mid if not pd.isna(eth_mid) else row.get("COMPUTED_SOMEIP_VALUE_MID", 0.0)
            )
            mapped_eth_max = (
                eth_max if not pd.isna(eth_max) else row.get("COMPUTED_SOMEIP_VALUE_MAX", 0.0)
            )
            # -----------------------------------------------------------------------------------

            # Datatype from SOMEIP_FF_DATATYPE column
            datatype = str(row.get("SOMEIP_FF_DATATYPE", "")).strip().lower()
            if not datatype or datatype == "nan" or datatype == "missing_data":
                resolution = str(row.get("SOMEIP_RESOLUTION", "1"))
                datatype = "float" if "." in resolution else "int"

            # Store unique variables required for the 'variables' block template
            if not is_enum:
                if can_port not in standard_vars_dict:
                    standard_vars_dict[can_port] = {
                        "CAN_PORT": can_port,
                        "COMPUTED_CAN_VALUE_MIN": can_min,
                        "COMPUTED_CAN_VALUE_MID": can_mid,
                        "COMPUTED_CAN_VALUE_MAX": can_max,
                        "CAN_OFFSET": can_offset,
                        "CAN_RESOLUTION": can_res,
                        "COMPUTED_SOMEIP_VALUE_MIN": mapped_eth_min,
                        "COMPUTED_SOMEIP_VALUE_MID": mapped_eth_mid,
                        "COMPUTED_SOMEIP_VALUE_MAX": mapped_eth_max,
                    }
            else:
                if not is_topic_attr:
                    if can_port not in can_enums_dict:
                        can_enums_dict[can_port] = {
                            "CAN_PORT": can_port,
                            "COMPUTED_CAN_VALUE_MIN": can_min,
                            "COMPUTED_CAN_VALUE_MID": can_mid,
                            "COMPUTED_CAN_VALUE_MAX": can_max,
                        }
                    eth_key = f"{someip_port}_{attr_val}"
                    if eth_key not in eth_enums_dict:
                        eth_enums_dict[eth_key] = {
                            "SOMEIP_PORT": someip_port,
                            "ATTRIBUTE_VALUE": attr_val,
                            "COMPUTED_SOMEIP_VALUE_MIN": mapped_eth_min,
                            "COMPUTED_SOMEIP_VALUE_MID": mapped_eth_mid,
                            "COMPUTED_SOMEIP_VALUE_MAX": mapped_eth_max,
                        }

            # Extracting specific Signal Name and Namespace details robustly
            full_sysvar = str(row.get("SOMEIP_DB_SIGNAL_NAME", "Namespace::SignalName"))
            sysvar_parts = full_sysvar.split("::")
            ns = "::".join(sysvar_parts[:-1]) if len(sysvar_parts) > 1 else "EthernetCluster"
            name = sysvar_parts[-1]

            # Extracting the FF explicit DB signal name
            someip_ff_signal_name = str(row.get("SOMEIP_FF_DB_SIGNAL_NAME", "")).strip()
            if not someip_ff_signal_name or someip_ff_signal_name == "nan":
                someip_ff_signal_name = full_sysvar  # Safe fallback if empty

            # Extracting the ValueState parameters
            someip_ff_valuestate = str(row.get("SOMEIP_FF_DB_SIGNAL_VALUESTATE", "")).strip()
            someip_ff_control = str(row.get("SOMEIP_FF_DB_SIGNAL_CONTROL", "")).strip()

            # --- NEW: Extracting the specific Namespace and Variable parameters ---
            someip_ff_signame_namespace = str(row.get("SOMEIP_FF_SIGNAME_NAMESPACE", "")).strip()
            someip_ff_signame_variable = str(row.get("SOMEIP_FF_SIGNAME_VARIABLE", "")).strip()
            someip_ff_sigvaluestate_namespace = str(
                row.get("SOMEIP_FF_SIGVALUESTATE_NAMESPACE", "")
            ).strip()
            someip_ff_sigvaluestate_variable = str(
                row.get("SOMEIP_FF_SIGVALUESTATE_VARIABLE", "")
            ).strip()
            someip_ff_control_namespace = str(row.get("SOMEIP_FF_CONTROL_NAMESPACE", "")).strip()
            someip_ff_control_variable = str(row.get("SOMEIP_FF_CONTROL_VARIABLE", "")).strip()

            # Preparing requirement object for the basic function template
            requirements.append(
                {
                    "Basic_Function": basic_func_name,
                    "CAN_PORT": can_port,
                    "SOMEIP_PORT": someip_port,
                    "ATTRIBUTE_VALUE": attr_val,
                    "CAN_DB_SIGNAL_NAME": str(row.get("CAN_DB_SIGNAL_NAME", "Unknown_CAN_Signal")),
                    "IS_ENUM": is_enum_str,
                    "SOMEIP_TOPIC_ATTRIBUTE": is_topic_attr_str,
                    "SOMEIP_DB_SIGNAL_NAME": full_sysvar,
                    "SOMEIP_FF_DB_SIGNAL_NAME": someip_ff_signal_name,
                    "SOMEIP_NS": ns,
                    "SOMEIP_NAME": name,
                    "SOMEIP_FF_DATATYPE": datatype,
                    "COMPUTED_SOMEIP_FF_VALUE_MIN": eth_min,
                    "COMPUTED_SOMEIP_FF_VALUE_MID": eth_mid,
                    "COMPUTED_SOMEIP_FF_VALUE_MAX": eth_max,
                    "SOMEIP_FF_DB_SIGNAL_VALUESTATE": someip_ff_valuestate,
                    "SOMEIP_FF_DB_SIGNAL_CONTROL": someip_ff_control,
                    "SOMEIP_FF_SIGNAME_NAMESPACE": someip_ff_signame_namespace,
                    "SOMEIP_FF_SIGNAME_VARIABLE": someip_ff_signame_variable,
                    "SOMEIP_FF_SIGVALUESTATE_NAMESPACE": someip_ff_sigvaluestate_namespace,
                    "SOMEIP_FF_SIGVALUESTATE_VARIABLE": someip_ff_sigvaluestate_variable,
                    "SOMEIP_FF_CONTROL_NAMESPACE": someip_ff_control_namespace,
                    "SOMEIP_FF_CONTROL_VARIABLE": someip_ff_control_variable,
                    "labels": ["Mid", "Min", "Max"],
                }
            )

        if not requirements:
            log.warning(f"No applicable rows found for test type {test_type}.")
            return

        # --- Filter out duplicate Basic Functions before passing to Jinja ---
        unique_requirements = []
        seen_funcs = set()
        for req in requirements:
            if req["Basic_Function"] not in seen_funcs:
                unique_requirements.append(req)
                seen_funcs.add(req["Basic_Function"])
        # --------------------------------------------------------------------------

        log.info("Data extracted successfully. Rendering Jinja2 templates...")

        # Setup standard output directories dynamically using output_root
        f_dir = Path(output_root) / "BASIC_FUNCTIONS"
        v_dir = Path(output_root) / "VARIABLES"
        os.makedirs(f_dir, exist_ok=True)
        os.makedirs(v_dir, exist_ok=True)

        func_filename = "someip_ff_to_can_basic_functions.cin"
        var_filename = "someip_ff_to_can_Variables.cin"

        output_path = str(f_dir / func_filename)
        var_output_file = str(v_dir / var_filename)

        try:
            # 1. Render Variables
            var_template = self.env.get_template(self.var_template)
            rendered_vars = var_template.render(
                standard_vars=list(standard_vars_dict.values()),
                can_enums=list(can_enums_dict.values()),
                eth_enums=list(eth_enums_dict.values()),
            )

            # 2. Render Test Functions (Using the filtered unique list)
            func_template = self.env.get_template(self.func_template)
            rendered_funcs = func_template.render(requirements=unique_requirements)

            # 3. Save to separate files (Variables in one, Functions in the other)
            with open(var_output_file, "w") as f_vars:
                f_vars.write(rendered_vars)

            with open(output_path, "w") as f_funcs:
                f_funcs.write(rendered_funcs)

            log.info(
                f"Generated {len(unique_requirements)} functions into {func_filename} "
                f"and variables into {var_filename}."
            )

        except Exception as e:
            log.exception(f"Logic Gen failed during template generation: {e}")
