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
            meth = str(data.get('Method', data.get('Attribute_Value', ''))).strip().lower()
            if meth:
                clean_db[meth] = data
        return clean_db

    def get_signal_data(self, attr_value: str, someip_port: str = None) -> dict:
        cols = [
            "SOMEIP_DB_SIGNAL_NAME", "SOMEIP_ENUM", "SOMEIP_MIN_PHY",
            "SOMEIP_MAX_PHY", "SOMEIP_OFFSET", "SOMEIP_RESOLUTION",
            "SOMEIP_DB_SIGNAL_VALUESTATE"
        ]

        if pd.isna(attr_value) or str(attr_value).strip() == "":
            return {col: None for col in cols}

        attr_str = str(attr_value).strip()
        attr_lower = attr_str.lower()

        target_event = ""
        if someip_port and "_" in str(someip_port):
            parts = str(someip_port).split("_")
            if len(parts) >= 2:
                target_event = parts[1].strip().lower()

        sig_data = None
        for data in self.raw_db_values:
            db_attr = str(data.get('Attribute_Value', '')).strip().lower()
            db_ev = str(data.get('Event', '')).strip().lower()
            if db_attr == attr_lower and (not target_event or target_event == db_ev):
                sig_data = data
                break

        if not sig_data:
            return {col: "ETH_NOT_FOUND" for col in cols}

        # --- ValueState Search Logic ---
        vs_attr_full_path = None
        db_event_exact = sig_data.get("Event")

        if "valuestate" in attr_lower:
            vs_attr_full_path = sig_data.get("Signal_String")
        elif db_event_exact:
            # 1. Prepare match targets
            common_suffixes = ["occurence", "status", "signal", "value"]
            stemmed_attr = attr_lower
            for suffix in common_suffixes:
                if attr_lower.endswith(suffix):
                    stemmed_attr = attr_lower[:len(attr_lower) - len(suffix)].rstrip("_")
                    break
            
            target_vs_append_1 = f"{attr_str}ValueState".lower()
            target_vs_append_2 = f"{attr_str}value_state".lower()
            target_vs_stemmed = f"{stemmed_attr}valuestate"
            
            # This handles the 'voltege' vs 'voltage' typo 
            # by looking for a signal that contains the core name + valuestate
            fuzzy_stem = stemmed_attr[:len(stemmed_attr)//2] # Take first half of string to be safe

            any_vs_in_event = None
            fuzzy_vs_match = None

            for data in self.raw_db_values:
                if data.get("Event") == db_event_exact:
                    curr_attr_lower = str(data.get("Attribute_Value", "")).strip().lower()
                    
                    # Priority 1: Exact matches (including your previous fix)
                    if curr_attr_lower in [target_vs_append_1, target_vs_append_2, target_vs_stemmed]:
                        vs_attr_full_path = data.get("Signal_String")
                        break
                    
                    # Priority 2: Fuzzy stem match (Handles typos like VoltEge vs VoltAge)
                    # We check if the attribute name is a partial match to the ValueState signal
                    if "valuestate" in curr_attr_lower:
                        # Check if the core name (minus suffixes) exists in this ValueState signal
                        if stemmed_attr in curr_attr_lower or curr_attr_lower.startswith(stemmed_attr[:5]):
                            fuzzy_vs_match = data.get("Signal_String")

                    # Priority 3: Dead fallback (Any ValueState)
                    if "valuestate" in curr_attr_lower and not any_vs_in_event:
                        any_vs_in_event = data.get("Signal_String")

            # Resolve hierarchy
            if not vs_attr_full_path:
                vs_attr_full_path = fuzzy_vs_match or any_vs_in_event

        return {
            "SOMEIP_DB_SIGNAL_NAME": sig_data.get("Signal_String"),
            "SOMEIP_ENUM": self.format_enum_to_string(sig_data.get("Enums", {})),
            "SOMEIP_MIN_PHY": sig_data.get("Min"),
            "SOMEIP_MAX_PHY": sig_data.get("Max"),
            "SOMEIP_OFFSET": sig_data.get("Offset"),
            "SOMEIP_RESOLUTION": sig_data.get("Resolution"),
            "SOMEIP_DB_SIGNAL_VALUESTATE": vs_attr_full_path
        }

    def resolve(self, df_subset: pd.DataFrame) -> pd.DataFrame:
        """Mapper focuses only on Ethernet lookup logic."""
        cols = ["SOMEIP_DB_SIGNAL_NAME", "SOMEIP_ENUM", "SOMEIP_MIN_PHY",
                "SOMEIP_MAX_PHY", "SOMEIP_OFFSET", "SOMEIP_RESOLUTION",
                "SOMEIP_DB_SIGNAL_VALUESTATE", "IS_ENUM"]

        def process_row(r):
            data = self.get_signal_data(r.get("ATTRIBUTE_VALUE"), r.get("SOMEIP_PORT"))
            
            # Check for Enum presence
            enum_val = str(data.get("CAN_ENUM", "")).strip().upper()
            is_enum = enum_val not in ["", "NONE", "NAN", "N/A"]
            
            existing_is_enum = str(r.get("IS_ENUM")).upper() == "TRUE"
            data["IS_ENUM"] = True if (is_enum or existing_is_enum) else False
            return data

        res = df_subset.apply(process_row, axis=1, result_type='expand')
        df_subset.loc[:, cols] = res[cols].values
        return df_subset
