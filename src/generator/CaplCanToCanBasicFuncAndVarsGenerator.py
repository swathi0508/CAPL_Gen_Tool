import os
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from logger import log

pd.set_option("future.no_silent_downcasting", True)


class CaplCanToCanBasicFuncAndVarsGenerator:
    def __init__(self, template_dir):
        self.env = Environment(loader=FileSystemLoader(template_dir))
        self.func_template = "can_to_can_basic_functions_template.j2"
        self.var_template = "variables_template.j2"

        # --- UNIFIED COLUMN SCHEMA FOR CAN->CAN ROUTING STRUCTURES ---
        self.j2_columns = [
            "CAN_PORT",
            "CAN_DB_SIGNAL_NAME",
            "CAN2_DB_SIGNAL_NAME",
            "CAN_ENUM",
            "CAN2_ENUM",
            "CAN_TO_CAN_MAPPING",
            "BASIC_FUNCTION_NAME",
            "CAN_OFFSET",
            "CAN_RESOLUTION",
            "CAN2_OFFSET",
            "CAN2_RESOLUTION",
            "IS_ENUM",
            "COMPUTED_CAN_VALUE_MIN",
            "COMPUTED_CAN_VALUE_MID",
            "COMPUTED_CAN_VALUE_MAX",
            "COMPUTED_CAN2_VALUE_MIN",
            "COMPUTED_CAN2_VALUE_MID",
            "COMPUTED_CAN2_VALUE_MAX",
        ]

    def _validate_and_clean(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        # Fill missing required columns safely
        missing_cols = [c for c in self.j2_columns if c not in df.columns]
        for c in missing_cols:
            df[c] = pd.NA

        # 1. Cleaner for MIN, MID, MAX, and ENUMS (Forces Integers)
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
                return str(float(val))
            except ValueError:
                return str(val).strip()

        # 3. Gentle cleaner for Strings / Names
        def clean_standard(val):
            if pd.isna(val) or str(val).strip() in ["", "N/A", "nan", "None", "MISSING_DATA"]:
                return "MISSING_DATA"
            return str(val).strip()

        # Route clean rules based on target column names
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
            # 1. Extract and Filter target sheet logs
            target_sheets = ["E2E_CAN_PARSED", "E2E_ETH_PARSED"]
            valid_dfs = []
            for s in target_sheets:
                if s in data_frames:
                    df_temp = data_frames[s].copy()
                    df_temp.columns = df_temp.columns.str.strip()
                    df_filtered = df_temp[df_temp["TEST_TYPE"].astype(str).str.strip() == test_type]
                    valid_dfs.append(df_filtered)

            if not valid_dfs:
                log.warning(f"No valid records located for {test_type} across {target_sheets}")
                return

            full_df = pd.concat(valid_dfs, ignore_index=True)
            full_df = self._validate_and_clean(full_df)

            if full_df.empty:
                return

            # 2. GENERATE MASTER FUNCTIONS CAPL BLOCK RECORDS
            full_df = full_df.sort_values(by=["BASIC_FUNCTION_NAME", "CAN_PORT"])
            func_df = full_df.drop_duplicates(subset=["BASIC_FUNCTION_NAME"])
            func_records = func_df.to_dict(orient="records")

            # 3. ROBUST POOLING FOR VARIABLES (Mapped to original template keys)
            full_df["IS_ENUM_STR"] = full_df["IS_ENUM"].astype(str).str.upper()

            # --- Pool Physical/Standard Variables ---
            std_vars_df = full_df[full_df["IS_ENUM_STR"] != "TRUE"].copy()
            standard_vars_pooled = {}

            for _, row in std_vars_df.iterrows():
                # Extract primary CAN network side profile using keys variables_template.j2 expects
                p1 = row.get("CAN_PORT")
                if p1 and p1 != "MISSING_DATA" and p1 not in standard_vars_pooled:
                    standard_vars_pooled[p1] = {
                        "CAN_PORT": p1,
                        "COMPUTED_CAN_VALUE_MIN": row.get("COMPUTED_CAN_VALUE_MIN"),
                        "COMPUTED_CAN_VALUE_MID": row.get("COMPUTED_CAN_VALUE_MID"),
                        "COMPUTED_CAN_VALUE_MAX": row.get("COMPUTED_CAN_VALUE_MAX"),
                        "CAN_OFFSET": row.get("CAN_OFFSET"),
                        "CAN_RESOLUTION": row.get("CAN_RESOLUTION"),
                    }
                # Extract mapped destination CAN2 network side profile, mapped back to CAN keys!
                p2 = row.get("CAN_TO_CAN_MAPPING")
                if p2 and p2 != "MISSING_DATA" and p2 not in standard_vars_pooled:
                    standard_vars_pooled[p2] = {
                        "CAN_PORT": p2,
                        "COMPUTED_CAN_VALUE_MIN": row.get("COMPUTED_CAN2_VALUE_MIN"),
                        "COMPUTED_CAN_VALUE_MID": row.get("COMPUTED_CAN2_VALUE_MID"),
                        "COMPUTED_CAN_VALUE_MAX": row.get("COMPUTED_CAN2_VALUE_MAX"),
                        "CAN_OFFSET": row.get("CAN2_OFFSET"),
                        "CAN_RESOLUTION": row.get("CAN2_RESOLUTION"),
                    }

            # --- Pool Enum Variables ---
            enum_base = full_df[full_df["IS_ENUM_STR"] == "TRUE"].copy()
            can_enums_pooled = {}

            for _, row in enum_base.iterrows():
                # Primary CAN Enum
                p1 = row.get("CAN_PORT")
                if p1 and p1 != "MISSING_DATA" and p1 not in can_enums_pooled:
                    can_enums_pooled[p1] = {
                        "CAN_PORT": p1,
                        "COMPUTED_CAN_VALUE_MIN": row.get("COMPUTED_CAN_VALUE_MIN"),
                        "COMPUTED_CAN_VALUE_MID": row.get("COMPUTED_CAN_VALUE_MID"),
                        "COMPUTED_CAN_VALUE_MAX": row.get("COMPUTED_CAN_VALUE_MAX"),
                    }
                # Destination Mapped CAN2 Enum mapped to CAN keys!
                p2 = row.get("CAN_TO_CAN_MAPPING")
                if p2 and p2 != "MISSING_DATA" and p2 not in can_enums_pooled:
                    can_enums_pooled[p2] = {
                        "CAN_PORT": p2,
                        "COMPUTED_CAN_VALUE_MIN": row.get("COMPUTED_CAN2_VALUE_MIN"),
                        "COMPUTED_CAN_VALUE_MID": row.get("COMPUTED_CAN2_VALUE_MID"),
                        "COMPUTED_CAN_VALUE_MAX": row.get("COMPUTED_CAN2_VALUE_MAX"),
                    }

            # Convert dictionary back to sequential record lists for Jinja loop iterations
            std_vars = list(standard_vars_pooled.values())
            can_enums = list(can_enums_pooled.values())

            # 4. WRITE GENERATED FILES
            f_dir = Path(output_root) / "BASIC_FUNCTIONS"
            v_dir = Path(output_root) / "VARIABLES"
            os.makedirs(f_dir, exist_ok=True)
            os.makedirs(v_dir, exist_ok=True)

            func_filename = "can_to_can_basic_functions.cin"
            var_filename = "can_to_can_variables.cin"

            # Generate basic functions include implementation code file (.cin)
            with open(f_dir / func_filename, "w") as f:
                f.write(self.env.get_template(self.func_template).render(functions=func_records))

            # Generate synchronized global variables include layout file (.cin)
            with open(v_dir / var_filename, "w") as f:
                f.write(
                    self.env.get_template(self.var_template).render(
                        standard_vars=std_vars,
                        can_enums=can_enums,
                        eth_enums=[],
                        ethernet_signals=[],
                    )
                )

            log.info(
                f"Generated {len(func_records)} functions into {func_filename} and variables into {var_filename}."
            )

        except Exception as e:
            log.exception(f"CAN->CAN Code Generation Engine Failed: {e}")
