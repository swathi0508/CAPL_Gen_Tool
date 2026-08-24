import os
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from logger import log

pd.set_option("future.no_silent_downcasting", True)


class CaplSomeipToCanBasicFuncAndVarsGenerator:
    def __init__(self, template_dir):
        self.env = Environment(loader=FileSystemLoader(template_dir))
        self.func_template = "someip_to_can_basic_functions_template.j2"
        self.var_template = "variables_template.j2"

        # --- UPDATED TO MATCH NEW UNIFIED COLUMN NAMES ---
        self.j2_columns = [
            "CAN_PORT",
            "CAN_DB_SIGNAL_NAME",
            "SOMEIP_DB_SIGNAL_NAME",
            "SOMEIP_DB_SIGNAL_VALUESTATE",
            "CAN_ENUM",
            "SOMEIP_ENUM",
            "SOMEIP_PORT",
            "ATTRIBUTE_VALUE",
            "BASIC_FUNCTION_NAME",
            "CAN_OFFSET",
            "CAN_RESOLUTION",
            "IS_ENUM",
            "COMPUTED_CAN_VALUE_MIN",
            "COMPUTED_CAN_VALUE_MID",
            "COMPUTED_CAN_VALUE_MAX",
            "COMPUTED_SOMEIP_VALUE_MIN",
            "COMPUTED_SOMEIP_VALUE_MID",
            "COMPUTED_SOMEIP_VALUE_MAX",
        ]

    def _validate_and_clean(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        # Fill missing required columns
        missing_cols = [c for c in self.j2_columns if c not in df.columns]
        for c in missing_cols:
            df[c] = pd.NA

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
            if any(kw in col.upper() for kw in ["MIN", "MID", "MAX", "ENUM"]):
                df[col] = df[col].apply(clean_bounds)
            elif any(kw in col.upper() for kw in ["OFFSET", "RESOLUTION"]):
                df[col] = df[col].apply(clean_float)
            else:
                df[col] = df[col].apply(clean_standard)

        return df

    def render(self, data_frames: dict, test_type: str, output_root: str):
        try:
            # 1. Combine and Clean Sheets
            target_sheets = ["E2E_CAN_PARSED", "E2E_ETH_PARSED"]
            valid_dfs = []
            for s in target_sheets:
                if s in data_frames:
                    df_temp = data_frames[s].copy()
                    df_temp.columns = df_temp.columns.str.strip()
                    # Apply test_type filter immediately per sheet
                    df_filtered = df_temp[df_temp["TEST_TYPE"].astype(str).str.strip() == test_type]
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
            actual_value_rows = full_df[
                ~full_df["ATTRIBUTE_VALUE"].str.contains("ValueState", case=False)
            ].copy()

            if actual_value_rows.empty:
                log.error(f"No actual value rows found after filtering ValueState for {test_type}.")
                return

            # 3. GENERATE UNIQUE MASTER FUNCTIONS
            actual_value_rows = actual_value_rows.sort_values(
                by=["BASIC_FUNCTION_NAME", "CAN_PORT"]
            )
            func_df = actual_value_rows.drop_duplicates(subset=["BASIC_FUNCTION_NAME"])
            func_records = func_df.to_dict(orient="records")

            # 4. GENERATE VARIABLES
            # Force IS_ENUM to uppercase string to safely check True/False without typing issues
            actual_value_rows["IS_ENUM_STR"] = actual_value_rows["IS_ENUM"].astype(str).str.upper()

            # --- Physical/Standard Variables (Where IS_ENUM is False or Missing) ---
            std_vars_df = actual_value_rows[actual_value_rows["IS_ENUM_STR"] != "TRUE"].copy()
            std_vars = std_vars_df.drop_duplicates(subset=["CAN_PORT"]).to_dict(orient="records")

            # --- Enum Variables (Where IS_ENUM is True) ---
            enum_base = actual_value_rows[actual_value_rows["IS_ENUM_STR"] == "TRUE"].copy()
            can_enums = enum_base.drop_duplicates(subset=["CAN_PORT"]).to_dict(orient="records")
            eth_enums = enum_base.drop_duplicates(
                subset=["SOMEIP_PORT", "ATTRIBUTE_VALUE"]
            ).to_dict(orient="records")

            # --- UNIQUE ETHERNET SIGNALS ---
            all_signals = pd.concat(
                [full_df["SOMEIP_DB_SIGNAL_NAME"], full_df["SOMEIP_DB_SIGNAL_VALUESTATE"]]
            )
            unique_signals = sorted([s for s in all_signals.unique() if s != "MISSING_DATA"])

            # 5. RENDER OUTPUTS
            f_dir = Path(output_root) / "BASIC_FUNCTIONS"
            v_dir = Path(output_root) / "VARIABLES"
            os.makedirs(f_dir, exist_ok=True)
            os.makedirs(v_dir, exist_ok=True)

            func_filename = "someip_to_can_basic_functions.cin"
            var_filename = "someip_to_can_variables.cin"

            # Render Functions File
            with open(f_dir / func_filename, "w") as f:
                f.write(self.env.get_template(self.func_template).render(functions=func_records))

            # Render Variables File
            with open(v_dir / var_filename, "w") as f:
                f.write(
                    self.env.get_template(self.var_template).render(
                        standard_vars=std_vars,
                        can_enums=can_enums,
                        eth_enums=eth_enums,
                        ethernet_signals=unique_signals,
                    )
                )

            log.info(
                f"Generated {len(func_records)} functions into {func_filename} "
                f"and variables into {var_filename}."
            )

        except Exception as e:
            log.exception(f"Logic Gen failed: {e}")
