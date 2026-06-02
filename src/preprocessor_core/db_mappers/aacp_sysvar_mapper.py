import pandas as pd
from preprocessor_core.db_mappers.base_mapper import BaseMapper
from logger import log

class AacpSysVarMapper(BaseMapper):
    def _load_database(self) -> dict:
        return super()._load_database()

    def resolve(self, df_subset: pd.DataFrame) -> pd.DataFrame:
        cols = [
            "AACP_DB_SIGNAL_NAME", "AACP_DB_SIGNAL_VALUESTATE", 
            "AACP_ENUM", "AACP_DATATYPE",
            "AACP_SIGNAME_NAMESPACE", "AACP_SIGNAME_VARIABLE", 
            "AACP_SIGVALUESTATE_NAMESPACE", "AACP_SIGVALUESTATE_VARIABLE",
            "AACP_SIGNAME_DAQ", "IS_ENUM"
        ]

        # self.db is already the SIGNAL_LIST dict (not wrapped in another dict)
        if "AACP_TREE" in self.db:
            signal_list = self.db["AACP_TREE"]
        elif "SIGNAL_LIST" in self.db:
            signal_list = self.db["SIGNAL_LIST"]
        else:
            signal_list = self.db
        
        # Build case-insensitive lookup map (lowercase key -> (original_key, container_dict))
        lowercase_signal_list = {}
        for k, v in signal_list.items():
            clean_k = str(k).strip().lower()
            lowercase_signal_list[clean_k] = (k, v)

        def process_row(r):
            # Initialize all columns to AACP_NOT_FOUND, except AACP_ENUM which defaults to blank
            res = {col: "AACP_NOT_FOUND" for col in cols}
            res["AACP_ENUM"] = ""
            res["IS_ENUM"] = False

            # Extract and clean inputs
            raw_topic = str(r.get("SOMEIP_TOPIC", "")).strip()
            raw_attribute = str(r.get("SOMEIP_TOPIC_ATTRIBUTE", "")).strip()

            if not raw_topic or not raw_attribute:
                return pd.Series(res)

            # --- STEP 1 & 2: Build target key and search case-insensitively ---
            # Convert dots to double colons and prefix with AACP::
            target_container_key = f"AACP::{raw_topic.replace('.', '::')}"
            search_key_lower = target_container_key.lower()
            
            # Try exact match first (case-insensitive)
            if search_key_lower in lowercase_signal_list:
                original_db_key, container = lowercase_signal_list[search_key_lower]
                
                # --- STEP 7: Store the DAQ context (the container key) ---
                res["AACP_SIGNAME_DAQ"] = original_db_key
                
                # --- STEP 3: Search for SOMEIP_TOPIC_ATTRIBUTE in the container ---
                matched_attr_key = None
                target_attr_lower = raw_attribute.lower()
                
                # Case-insensitive attribute lookup
                for attr_key in container.keys():
                    if attr_key.lower() == target_attr_lower:
                        matched_attr_key = attr_key
                        break
                
                # --- STEP 4 & 5: Extract Signal_DB_Name, Enums, and DataType ---
                if matched_attr_key:
                    attr_data = container[matched_attr_key]
                    
                    # Retrieve Signal_DB_Name
                    signal_db_name = attr_data.get("Signal_DB_Name", "AACP_NOT_FOUND")
                    res["AACP_DB_SIGNAL_NAME"] = signal_db_name
                    
                    # Retrieve DataType
                    res["AACP_DATATYPE"] = attr_data.get("DataType", "AACP_NOT_FOUND")
                    
                    # Retrieve and format Enums (Keep blank if missing/empty)
                    raw_enums = attr_data.get("Enums", {})
                    res["AACP_ENUM"] = self.format_enum_to_string(raw_enums) if raw_enums else ""
                    
                    # --- STEP 6: Handle ValueState logic (Enhanced Fallbacks) ---
                    clean_attr_lower = matched_attr_key.lower()
                    
                    if "value_state" in clean_attr_lower or "valuestate" in clean_attr_lower:
                        # If searching specifically for a value_state attribute, the main name IS the value_state
                        res["AACP_DB_SIGNAL_VALUESTATE"] = signal_db_name
                    else:
                        # Dynamic sibling matching strategy for non-valuestate attributes
                        found_vs_signal = None
                        
                        # Extract the base root prefix of the current attribute
                        base_prefix = clean_attr_lower
                        for suffix in ["_timestamp", "_value", "_raw", "_signal", "_status"]:
                            if clean_attr_lower.endswith(suffix):
                                base_prefix = clean_attr_lower[:-len(suffix)]
                                break
                        
                        # TIER 1: Predictable suffix construction
                        tier1_target = f"{base_prefix}_value_state"
                        tier1_target_alt = f"{base_prefix}_valuestate"
                        
                        for sibling_key in container.keys():
                            sib_lower = sibling_key.lower()
                            if sib_lower in [tier1_target, tier1_target_alt]:
                                found_vs_signal = container[sibling_key].get("Signal_DB_Name")
                                break
                        
                        # TIER 2: Fuzzy prefix containment
                        if not found_vs_signal and base_prefix != clean_attr_lower:
                            for sibling_key in container.keys():
                                sib_lower = sibling_key.lower()
                                if base_prefix in sib_lower and ("value_state" in sib_lower or "valuestate" in sib_lower):
                                    found_vs_signal = container[sibling_key].get("Signal_DB_Name")
                                    break
                                    
                        # TIER 3: Absolute Fallback
                        if not found_vs_signal:
                            for sibling_key in container.keys():
                                sib_lower = sibling_key.lower()
                                if sib_lower in ["value_state", "valuestate"]:
                                    found_vs_signal = container[sibling_key].get("Signal_DB_Name")
                                    break
                        
                        if found_vs_signal:
                            res["AACP_DB_SIGNAL_VALUESTATE"] = found_vs_signal

            # --- STEP 8: Split Signal Names into Namespace and Variable ---
            # Split AACP_DB_SIGNAL_NAME
            if res["AACP_DB_SIGNAL_NAME"] != "AACP_NOT_FOUND":
                ns, var = self.split_namespace_variable(res["AACP_DB_SIGNAL_NAME"])
                res["AACP_SIGNAME_NAMESPACE"] = ns if ns else "AACP_NOT_FOUND"
                res["AACP_SIGNAME_VARIABLE"] = var if var else "AACP_NOT_FOUND"
            
            # Split AACP_DB_SIGNAL_VALUESTATE
            if res["AACP_DB_SIGNAL_VALUESTATE"] != "AACP_NOT_FOUND":
                ns_vs, var_vs = self.split_namespace_variable(res["AACP_DB_SIGNAL_VALUESTATE"])
                res["AACP_SIGVALUESTATE_NAMESPACE"] = ns_vs if ns_vs else "AACP_NOT_FOUND"
                res["AACP_SIGVALUESTATE_VARIABLE"] = var_vs if var_vs else "AACP_NOT_FOUND"
            
            # --- Update IS_ENUM flag based on Enums presence ---
            db_has_enum = bool(res["AACP_ENUM"])
            existing_is_enum = str(r.get("IS_ENUM", "FALSE")).upper() == "TRUE"
            res["IS_ENUM"] = True if (db_has_enum or existing_is_enum) else False

            return pd.Series(res)

        if df_subset.empty:
            return pd.DataFrame(columns=cols, index=df_subset.index)

        return df_subset.apply(process_row, axis=1)
