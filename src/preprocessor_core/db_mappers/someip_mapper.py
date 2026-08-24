import math

import pandas as pd

from preprocessor_core.db_mappers.base_mapper import BaseMapper


class SomeIPMapper(BaseMapper):
    def _load_database(self) -> dict:
        raw_db = super()._load_database()
        self.raw_db_values = []
        clean_db = {}

        for key, data in raw_db.items():
            data["Signal_String"] = key
            self.raw_db_values.append(data)
            meth = str(data.get("Method", data.get("Attribute_Value", ""))).strip().lower()
            if meth:
                clean_db[meth] = data
        return clean_db

    def get_signal_data(self, attr_value: str, someip_port: str = None) -> dict:
        cols = [
            "SOMEIP_DB_SIGNAL_NAME",
            "SOMEIP_ENUM",
            "SOMEIP_MIN_PHY",
            "SOMEIP_MID_PHY",
            "SOMEIP_MAX_PHY",
            "SOMEIP_OFFSET",
            "SOMEIP_RESOLUTION",
            "SOMEIP_DB_SIGNAL_VALUESTATE",
        ]

        if pd.isna(attr_value) or str(attr_value).strip() == "":
            return {col: None for col in cols}

        attr_str = str(attr_value).strip()
        attr_lower = attr_str.lower()
        port_val = str(someip_port or "").strip()

        # --- EXACT Extraction Logic as requested ---
        parts = port_val.split("_")
        if "::" in port_val:
            target_event = port_val.split("::")[-1].strip()
        elif len(parts) > 1:
            target_event = "_".join(parts[math.ceil(len(parts) / 2) :]).strip()
        else:
            target_event = port_val

        target_event_lower = target_event.lower()

        # --- Database Lookup ---
        sig_data = None
        for data in self.raw_db_values:
            db_attr = str(data.get("Attribute_Value", "")).strip().lower()
            db_ev = str(data.get("Event", "")).strip().lower()
            # Match Attribute AND the extracted Event name
            if db_attr == attr_lower and (not target_event_lower or target_event_lower == db_ev):
                sig_data = data
                break

        if not sig_data:
            return {col: "ETH_NOT_FOUND" for col in cols}

        # --- ORIGINAL ValueState Logic (Unmodified) ---
        vs_attr_full_path = None
        db_event_exact = sig_data.get("Event")

        if "valuestate" in attr_lower:
            vs_attr_full_path = sig_data.get("Signal_String")
        elif db_event_exact:
            common_suffixes = ["occurence", "status", "signal", "value"]
            stemmed_attr = attr_lower
            for suffix in common_suffixes:
                if attr_lower.endswith(suffix):
                    stemmed_attr = attr_lower[: len(attr_lower) - len(suffix)].rstrip("_")
                    break

            target_vs_append_1 = f"{attr_str}ValueState".lower()
            target_vs_append_2 = f"{attr_str}value_state".lower()
            target_vs_stemmed = f"{stemmed_attr}valuestate"

            any_vs_in_event = None
            fuzzy_vs_match = None

            for data in self.raw_db_values:
                if data.get("Event") == db_event_exact:
                    curr_attr_lower = str(data.get("Attribute_Value", "")).strip().lower()

                    if curr_attr_lower in [
                        target_vs_append_1,
                        target_vs_append_2,
                        target_vs_stemmed,
                    ]:
                        vs_attr_full_path = data.get("Signal_String")
                        break

                    if "valuestate" in curr_attr_lower:
                        if stemmed_attr in curr_attr_lower or curr_attr_lower.startswith(
                            stemmed_attr[:5]
                        ):
                            fuzzy_vs_match = data.get("Signal_String")

                    if "valuestate" in curr_attr_lower and not any_vs_in_event:
                        any_vs_in_event = data.get("Signal_String")

            if not vs_attr_full_path:
                vs_attr_full_path = fuzzy_vs_match or any_vs_in_event

        # --- Formatting ---
        raw_enums = sig_data.get("Enums", {})
        min_val = sig_data.get("Min")
        max_val = sig_data.get("Max")
        mid_val = sig_data.get("Mid")

        is_bool = str(sig_data.get("DataType", "")).lower() == "boolean"
        if is_bool and str(min_val).upper() == "N/A" and str(max_val).upper() == "N/A":
            min_val, mid_val, max_val = 0, 1, 1

        return {
            "SOMEIP_DB_SIGNAL_NAME": sig_data.get("Signal_String"),
            "SOMEIP_ENUM": self.format_enum_to_string(raw_enums),
            "SOMEIP_MIN_PHY": min_val,
            "SOMEIP_MID_PHY": mid_val,
            "SOMEIP_MAX_PHY": max_val,
            "SOMEIP_OFFSET": sig_data.get("Offset"),
            "SOMEIP_RESOLUTION": sig_data.get("Factor"),
            "SOMEIP_DB_SIGNAL_VALUESTATE": vs_attr_full_path,
            "_HAS_ENUM": bool(raw_enums),
        }

    def resolve(self, df_subset: pd.DataFrame) -> pd.DataFrame:
        def process_row(r):
            data = self.get_signal_data(r.get("ATTRIBUTE_VALUE"), r.get("SOMEIP_PORT"))
            db_has_enum = data.pop("_HAS_ENUM", False)
            existing_is_enum = str(r.get("IS_ENUM", "FALSE")).upper() == "TRUE"
            data["IS_ENUM"] = True if (db_has_enum or existing_is_enum) else False
            return pd.Series(data)

        temp_res = df_subset.apply(process_row, axis=1)
        df_subset.update(temp_res)
        return df_subset
