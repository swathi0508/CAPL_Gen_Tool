import pandas as pd
import math
from preprocessor_core.db_mappers.base_mapper import BaseMapper

class SomeIPFFSysVarMapper(BaseMapper):
    def _load_database(self) -> dict:
        """Flatten the nested INTERFACES DB into a flat list for searching."""
        raw_db = super()._load_database()
        self.raw_db_values = []
        
        interfaces = raw_db.get("INTERFACES", {})
        for iface_name, iface_data in interfaces.items():
            nodes = iface_data.get("NODES", {})
            for node_name, node_data in nodes.items():
                role = str(node_data.get("Role", "")).strip().upper()
                params = node_data.get("PARAMETERS", {})
                controls = node_data.get("CONTROLS", {})
                
                # Pre-fetch Control Signal
                ctrl_sig = next((c.get("Signal_DB_Name") for c in controls.values() if c.get("Signal_DB_Name")), None)

                for attr_name, attr_data in params.items():
                    entry = {
                        "iface_key": iface_name,
                        "node_key": node_name.lower(),
                        "role_key": role,
                        "attr_key": attr_name,
                        "ctrl_sig": ctrl_sig,
                        **attr_data
                    }
                    self.raw_db_values.append(entry)
        return raw_db

    def resolve(self, df_subset: pd.DataFrame) -> pd.DataFrame:
        cols = [
            "SOMEIP_FF_DB_SIGNAL_NAME", "SOMEIP_FF_DB_SIGNAL_VALUESTATE", 
            "SOMEIP_FF_DB_SIGNAL_CONTROL", "SOMEIP_FF_ENUM", "SOMEIP_FF_DATATYPE",
            "SOMEIP_FF_SIGNAME_NAMESPACE", "SOMEIP_FF_SIGNAME_VARIABLE", 
            "SOMEIP_FF_SIGVALUESTATE_NAMESPACE", "SOMEIP_FF_SIGVALUESTATE_VARIABLE", 
            "SOMEIP_FF_CONTROL_NAMESPACE", "SOMEIP_FF_CONTROL_VARIABLE", "IS_ENUM"
        ]

        def process_row(r):
            # --- 1. Normalization (Nodes) ---
            port_val = str(r.get("SOMEIP_PORT", ""))
            if "PIU_MASTER" in port_val.upper():
                port_val = port_val.replace("PIU_MASTER", "PIU_Mst").replace("Piu_Master", "PIU_Mst")

            # Interface/Event extraction logic
            parts = port_val.split("_")
            if "::" in port_val:
                target_iface = port_val.split("::")[-1].strip()
            elif len(parts) > 1:
                target_iface = "_".join(parts[math.ceil(len(parts)/2):]).strip()
            else:
                target_iface = port_val

            target_role = "PROVIDED" if "->SOMEIP_FF" in str(r.get("TEST_TYPE", "")) else "CONSUMED"
            
            target_node = str(r.get("RUNTIME_ENV_RECEIVER", "")).strip().lower()
            if target_node == "piu_master": target_node = "piu_mst"
            
            target_attr = str(r.get("ATTRIBUTE_VALUE", "")).strip()

            # --- 2. Database Lookup Context ---
            sig_data = None
            parent_siblings = [] 
            
            for data in self.raw_db_values:
                if (data["iface_key"] == target_iface and 
                    data["node_key"] == target_node and 
                    data["role_key"] == target_role):
                    
                    parent_siblings.append(data)
                    
                    if data["attr_key"] == target_attr:
                        sig_data = data

            res = {col: "ETH_NOT_FOUND" for col in cols}
            
            # --- 3. Enum logic using _HAS_ENUM style ---
            db_has_enum = False
            if sig_data:
                raw_enums = sig_data.get("Enums", {})
                db_has_enum = bool(raw_enums)
                
                # Found the primary signal
                main_sig_name = sig_data.get("Signal_DB_Name")
                res["SOMEIP_FF_DB_SIGNAL_NAME"] = main_sig_name
                res["SOMEIP_FF_DB_SIGNAL_CONTROL"] = sig_data.get("ctrl_sig")
                res["SOMEIP_FF_DATATYPE"] = sig_data.get("DataType")
                res["SOMEIP_FF_ENUM"] = self.format_enum_to_string(raw_enums)

                # --- 4. ValueState Logic ---
                if "valuestate" in target_attr.lower():
                    res["SOMEIP_FF_DB_SIGNAL_VALUESTATE"] = main_sig_name
                else:
                    vs_candidates = [f"{target_attr}ValueState".lower(), f"{target_attr}value_state".lower(), "valuestate"]
                    
                    # 1. Primary check using exact candidate matching
                    for sibling in parent_siblings:
                        if sibling["attr_key"].lower() in vs_candidates:
                            res["SOMEIP_FF_DB_SIGNAL_VALUESTATE"] = sibling.get("Signal_DB_Name")
                            break
                    else:
                        # 2. Final Fallback: Grab the first sibling that contains 'valuestate' in its key
                        for sibling in parent_siblings:
                            if "valuestate" in sibling["attr_key"].lower():
                                res["SOMEIP_FF_DB_SIGNAL_VALUESTATE"] = sibling.get("Signal_DB_Name")
                                break

            # --- 5. IS_ENUM Update (Same as someip_mapper) ---
            existing_is_enum = str(r.get("IS_ENUM", "FALSE")).upper() == "TRUE"
            res["IS_ENUM"] = True if (db_has_enum or existing_is_enum) else False

            # --- 6. Namespace and Variable Extraction ---
            for pre, db_col in [("SIGNAME", "SOMEIP_FF_DB_SIGNAL_NAME"), 
                                ("SIGVALUESTATE", "SOMEIP_FF_DB_SIGNAL_VALUESTATE"), 
                                ("CONTROL", "SOMEIP_FF_DB_SIGNAL_CONTROL")]:
                val = res.get(db_col)
                if val and val != "ETH_NOT_FOUND":
                    ns, var = self.split_namespace_variable(val)
                    res[f"SOMEIP_FF_{pre}_NAMESPACE"] = ns
                    res[f"SOMEIP_FF_{pre}_VARIABLE"] = var
                else:
                    res[f"SOMEIP_FF_{pre}_NAMESPACE"] = "ETH_NOT_FOUND"
                    res[f"SOMEIP_FF_{pre}_VARIABLE"] = "ETH_NOT_FOUND"

            return pd.Series(res)

        temp_res = df_subset.apply(process_row, axis=1)
        df_subset.update(temp_res)
        return df_subset
