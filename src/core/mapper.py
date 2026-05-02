import pandas as pd
import os
import glob
import re
import json
import warnings

# Suppress openpyxl warnings for a cleaner console output
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

class ExcelProcessor:
    def __init__(self, input_folder):
        self.input_folder = input_folder
        self.can_db = {}
        self.eth_db = {}
        # Define columns expected to be filled by JSON databases
        self.can_attr_cols = [
            "CAN_DB_SIGNAL_NAME", "CAN_ENUM", "CAN_MIN_RAW",  
            "CAN_MAX_RAW", "CAN_PERIODICITY", "CAN_OFFSET", "CAN_RESOLUTION"
        ]
        self.eth_attr_cols = [
            "SOMEIP_DB_SIGNAL_NAME", "SOMEIP_ENUM", "SOMEIP_MIN_PHY", 
            "SOMEIP_MAX_PHY", "SOMEIP_OFFSET", "SOMEIP_RESOLUTION"
        ]
        self._load_databases()

    def _load_databases(self):
        """Identifies and loads the CAN and ETH JSON databases from the folder."""
        # Find CAN JSON
        can_files = glob.glob(os.path.join(self.input_folder, "*can*.json"))
        if can_files:
            print(f"--- Loading CAN database: {os.path.basename(can_files[0])} ---")
            with open(can_files[0], 'r') as f:
                self.can_db = json.load(f).get("SIGNAL_LIST", {})
        
        # Find ETH JSON
        eth_files = glob.glob(os.path.join(self.input_folder, "*eth*.json"))
        if eth_files:
            print(f"--- Loading ETH database: {os.path.basename(eth_files[0])} ---")
            with open(eth_files[0], 'r') as f:
                self.eth_db = json.load(f).get("SIGNAL_LIST", {})

    @staticmethod
    def extract_cluster(path_val):
        """Extracts cluster name from PATH_SYNTHESIS using regex and keyword matching."""
        if pd.isna(path_val) or str(path_val).strip() == "": 
            return ""
        clusters = ["CAN_FD_CHASSIS", "CAN_FD_PT", "CAN_ITS3_FD", "CAN_ITS5_FD", 
                    "PCU4_CAN", "CAN_EXT", "CAN_FD_ACCESS2"]
        tokens = re.split(r'\s*=>\s*|\s*::\s*', str(path_val))
        for token in tokens:
            for c in clusters:
                if c in token: return c
        
        path_str = str(path_val)
        if any(trig in path_str for trig in ["PIU_Mst", "PIU_Sub", "PIU_Hood"]):
            return "EthernetCluster"
        return "UNKNOWN_CLUSTER"

    @staticmethod
    def normalize_attr(val):
        """
        Refined normalization logic:
        1. Case-insensitively removes 'ValueState' suffix.
        2. Filters out 'nan', 'unknown', or empty strings.
        3. Returns None if the value is invalid or purely 'ValueState'.
        """
        if pd.isna(val):
            return None
        val_str = str(val).strip()
        if val_str.lower() == "valuestate":
            return None

        # Regex replacement: removes 'valuestate' at the end of the string
        clean_val = re.sub(r'valuestate$', '', val_str, flags=re.IGNORECASE).strip()
        
        if not clean_val or clean_val.lower() in ["nan", "unknown"]:
            return None
        return clean_val

    def _get_can_json_data(self, port_name, cluster):
        """Retrieves technical signal attributes from the CAN JSON DB."""
        if pd.isna(port_name) or str(port_name).strip() == "":
            return {col: None for col in self.can_attr_cols}

        search_key = "I" + str(port_name).strip()
        if search_key not in self.can_db:
            return {col: "CAN_NOT_FOUND" for col in self.can_attr_cols}

        sig_data = self.can_db[search_key]
        attr = sig_data.get("Attributes", {})
        paths = sig_data.get("signal_paths", [])
        
        fallback_order = [cluster, "CAN_FD_CHASSIS", "CAN_FD_PT", "CAN_ITS3_FD", 
                          "CAN_ITS5_FD", "PCU4_CAN", "CAN_EXT", "CAN_FD_ACCESS2"]
        
        db_signal_name = "CAN_CLUSTER_NOT_FOUND"
        for c in fallback_order:
            if not c: continue
            match = next((p for p in paths if str(p.get("can_cluster")) == str(c)), None)
            if match:
                db_signal_name = match.get("signal_name")
                break

        enums = attr.get("Enums", {})
        enum_str = ", ".join([f'"{k}": "{v}"' for k, v in enums.items()]) if enums else ""

        return {
            "CAN_DB_SIGNAL_NAME": db_signal_name, "CAN_ENUM": enum_str,
            "CAN_MIN_RAW": attr.get("Raw_Limits", {}).get("Min"),
            "CAN_MAX_RAW": attr.get("Raw_Limits", {}).get("Max"),
            "CAN_PERIODICITY": attr.get("periodicity_ms"),
            "CAN_OFFSET": attr.get("Offset"), "CAN_RESOLUTION": attr.get("Resolution")
        }

    def _get_eth_json_data(self, someip_port, attr_value):
        """Retrieves technical signal attributes from the ETH JSON DB."""
        if pd.isna(someip_port) or pd.isna(attr_value):
            return {col: None for col in self.eth_attr_cols}

        event_name = str(someip_port).split('_')[-1].strip()
        attr_str = str(attr_value).strip()

        found_key, sig_data = None, None
        for key, data in self.eth_db.items():
            if data.get("Event") == event_name and data.get("Attribute_Value") == attr_str:
                found_key = key
                sig_data = data
                break

        if not found_key:
            return {col: "ETH_NOT_FOUND" for col in self.eth_attr_cols}

        enums = sig_data.get("Enums", {})
        enum_str = ", ".join([f'"{k}": "{v}"' for k, v in enums.items()]) if enums else ""

        return {
            "SOMEIP_DB_SIGNAL_NAME": found_key,
            "SOMEIP_ENUM": enum_str,
            "SOMEIP_MIN_PHY": sig_data.get("Min"),
            "SOMEIP_MAX_PHY": sig_data.get("Max"),
            "SOMEIP_OFFSET": sig_data.get("Offset"),
            "SOMEIP_RESOLUTION": sig_data.get("Resolution")
        }

    def compute_logic(self, row):
        """Generates the BASIC_FUNCTION_NAME based on the processed row data."""
        tt_raw = str(row.get('TEST_TYPE', '')).upper()
        if any(x in tt_raw for x in ["NONEED", "ENABLER", "NO_NEED"]):
            return "FUNCTION_NOT_REQUIRED"

        tt = str(row.get('TEST_TYPE', '')).strip()
        swc = str(row.get('SWC', '')).strip()
        sp = str(row.get('SOMEIP_PORT', '')).strip()
        raw_cp = str(row.get('CAN_PORT', '')).strip() if pd.notna(row.get('CAN_PORT')) else "UnknownPort"
        cp = f"I{raw_cp}"
        
        # Use the static normalization function
        attr = self.normalize_attr(row.get('ATTRIBUTE_VALUE'))
        
        # If attribute is invalid, return None so it can be filled by global port mapping
        if attr is None: 
            return None

        if tt in ['CAN->SOMEIP', 'CAN->SOMEIP_FF', 'CAN->SOMEIP_AACP']: 
            return f"basic_function__{swc}__{cp}__{sp}__{attr}"
        if tt in ['SOMEIP->CAN', 'SOMEIP_FF->CAN']: 
            return f"basic_function__{swc}__{sp}__{attr}__{cp}"
        if tt in ['CAN->SWC', 'CAN->SWC_HVB']: 
            return f"basic_function__{swc}__{cp}__SWC"
        if tt == 'SWC->CAN': 
            return f"basic_function__{swc}__SWC__{cp}"
        if tt in ['SOMEIP->SWC', 'SOMEIP_FF->SWC']: 
            return f"basic_function__{swc}__{sp}__{attr}__SWC"
        if tt in ['SWC->SOMEIP', 'SWC->SOMEIP_FF', 'SWC->SOMEIP_AACP']: 
            return f"basic_function__{swc}__SWC__{sp}__{attr}"
        if tt == 'CAROS->SWC': 
            return f"basic_function__{swc}__CarOS__{sp}__{attr}__SWC"
        if tt == 'CAN->CAN': 
            return f"basic_function__{swc}__{cp}__{cp}"

        return f"basic_function__{swc}__{sp}__{attr}"

    def apply_global_mapping(self, df_eth, df_can):
        """Fills missing BASIC_FUNCTION_NAMEs by mapping SOMEIP_PORT to known valid names."""
        combined = pd.concat([df_eth, df_can])
        valid_pool = combined[~combined['BASIC_FUNCTION_NAME'].isin([None, "FUNCTION_NOT_REQUIRED", "basic_function__UNKNOWN_CONFIG"])]
        
        global_port_map = valid_pool.drop_duplicates('SOMEIP_PORT').set_index('SOMEIP_PORT')['BASIC_FUNCTION_NAME'].to_dict()

        for df in [df_eth, df_can]:
            mask_none = df['BASIC_FUNCTION_NAME'].isna()
            df.loc[mask_none, 'BASIC_FUNCTION_NAME'] = df.loc[mask_none, 'SOMEIP_PORT'].map(global_port_map)
            df['BASIC_FUNCTION_NAME'] = df['BASIC_FUNCTION_NAME'].fillna("basic_function__UNKNOWN_CONFIG")
        
        return df_eth, df_can

    def transform_all_data(self, df_list, sheet_names):
        """Main engine to transform all raw DataFrames into processed sheets."""
        processed_dfs = []
        for df in df_list:

            if "TEST_TYPE" in df.columns:
                df["TEST_TYPE"] = df["TEST_TYPE"].astype(str)
                df["TEST_TYPE"] = df["TEST_TYPE"].str.replace(r"F&F\s*SOMEIP|SOMEIP\s*F&F", "SOMEIP_FF", regex=True)
                df["TEST_TYPE"] = df["TEST_TYPE"].str.replace(r"[\(\)]", "_", regex=True)
                df["TEST_TYPE"] = df["TEST_TYPE"].str.replace(r"__+", "_", regex=True).str.strip("_")

            if "PATH_SYNTHESIS" in df.columns:
                df["CAN_CLUSTER"] = df["PATH_SYNTHESIS"].apply(self.extract_cluster)

            # JSON Lookups
            if "CAN_PORT" in df.columns and "CAN_CLUSTER" in df.columns:
                can_res = df.apply(lambda r: self._get_can_json_data(r["CAN_PORT"], r["CAN_CLUSTER"]), axis=1)
                df[self.can_attr_cols] = pd.DataFrame(can_res.tolist(), index=df.index)

            if "SOMEIP_PORT" in df.columns and "ATTRIBUTE_VALUE" in df.columns:
                eth_res = df.apply(lambda r: self._get_eth_json_data(r["SOMEIP_PORT"], r["ATTRIBUTE_VALUE"]), axis=1)
                df[self.eth_attr_cols] = pd.DataFrame(eth_res.tolist(), index=df.index)

            # Initial naming compute
            df['BASIC_FUNCTION_NAME'] = df.apply(self.compute_logic, axis=1)
            processed_dfs.append(df)

        # Cross-sheet filling
        try:
            eth_idx = sheet_names.index("E2E_ETH")
            can_idx = sheet_names.index("E2E_CAN")
            processed_dfs[eth_idx], processed_dfs[can_idx] = self.apply_global_mapping(processed_dfs[eth_idx], processed_dfs[can_idx])
        except (ValueError, IndexError):
            pass
            
        return processed_dfs

def get_mapping_config():
    """Maps internal processing column names to raw Excel sheet headers."""
    eth_map = {
        "E2E_ETH_REQ_ID": "REQ ID", "SWC": "SWC", "SOMEIP_PORT": "Port",
        "ATTRIBUTE_VALUE": "Attribute value", "CAN_PORT": "CAN_PORT_MAPPING",
        "PATH_SYNTHESIS": "CAN_PATH_SYNTHESIS_MAPPING", "Topic": "Topic",
        "TEST_TYPE": "TEST_TYPE", "CAN_CLUSTER": "CAN_CLUSTER", 
        "BASIC_FUNCTION_NAME": "BASIC_FUNCTION_NAME",
        "CAN_DB_SIGNAL_NAME": "CAN_DB_SIGNAL_NAME", "CAN_ENUM": "CAN_ENUM",
        "CAN_MIN_RAW": "CAN_MIN_RAW", "CAN_MAX_RAW": "CAN_MAX_RAW", 
        "CAN_PERIODICITY": "CAN_PERIODICITY", "CAN_OFFSET": "CAN_OFFSET", "CAN_RESOLUTION": "CAN_RESOLUTION",
        "SOMEIP_DB_SIGNAL_NAME": "SOMEIP_DB_SIGNAL_NAME", "SOMEIP_ENUM": "SOMEIP_ENUM",
        "SOMEIP_MIN_PHY": "SOMEIP_MIN_PHY", "SOMEIP_MAX_PHY": "SOMEIP_MAX_PHY",
        "SOMEIP_OFFSET": "SOMEIP_OFFSET", "SOMEIP_RESOLUTION": "SOMEIP_RESOLUTION"
    }
    
    can_map = {
        "E2E_CAN_REQ_ID": "REQ ID", "SWC": "SWC", "CAN_PORT": "Port Name",
        "PATH_SYNTHESIS": "Path Synthesis", "SOMEIP_PORT": "SOMEIP_PORT_MAPPING",
        "ATTRIBUTE_VALUE": "SOMEIP_ATTRIBUTE_VALUE_MAPPING", "TEST_TYPE": "TEST_TYPE",
        "CAN_CLUSTER": "CAN_CLUSTER", "BASIC_FUNCTION_NAME": "BASIC_FUNCTION_NAME", 
        "CAN_DB_SIGNAL_NAME": "CAN_DB_SIGNAL_NAME", "CAN_ENUM": "CAN_ENUM", 
        "CAN_MIN_RAW": "CAN_MIN_RAW", "CAN_MAX_RAW": "CAN_MAX_RAW", "CAN_PERIODICITY": "CAN_PERIODICITY", 
        "CAN_OFFSET": "CAN_OFFSET", "CAN_RESOLUTION": "CAN_RESOLUTION",
        "SOMEIP_DB_SIGNAL_NAME": "SOMEIP_DB_SIGNAL_NAME", "SOMEIP_ENUM": "SOMEIP_ENUM",
        "SOMEIP_MIN_PHY": "SOMEIP_MIN_PHY", "SOMEIP_MAX_PHY": "SOMEIP_MAX_PHY",
        "SOMEIP_OFFSET": "SOMEIP_OFFSET", "SOMEIP_RESOLUTION": "SOMEIP_RESOLUTION"
    }
    return {"E2E_ETH": eth_map, "E2E_CAN": can_map}

def main(in_p, out_p):
    """Main application entry point."""
    processor = ExcelProcessor(in_p)
    os.makedirs(out_p, exist_ok=True)
    mapping_cfg = get_mapping_config()

    for file_path in glob.glob(os.path.join(in_p, "*.xlsx")):
        fname = os.path.basename(file_path)
        dest_path = os.path.join(out_p, f"Processed_{fname}")
        
        if os.path.exists(dest_path):
            try: os.remove(dest_path)
            except: continue

        try:
            with pd.ExcelWriter(dest_path, engine='openpyxl') as writer:
                xl_reader = pd.ExcelFile(file_path)
                sheets_present = [s for s in ["E2E_ETH", "E2E_CAN"] if s in xl_reader.sheet_names]
                
                raw_dfs = []
                for s_name in sheets_present:
                    df_in = pd.read_excel(file_path, sheet_name=s_name)
                    df_out = pd.DataFrame()
                    for target, source in mapping_cfg[s_name].items():
                        df_out[target] = df_in[source] if source in df_in.columns else ""
                    raw_dfs.append(df_out)
                
                processed_dfs = processor.transform_all_data(raw_dfs, sheets_present)
                
                for idx, s_name in enumerate(sheets_present):
                    processed_dfs[idx].to_excel(writer, sheet_name=f"{s_name}_intermediate", index=False)
            print(f"File processed successfully: {dest_path}")
        except Exception as e:
            print(f"An error occurred while processing {fname}: {e}")

if __name__ == "__main__":
    # --- CONFIGURE YOUR DIRECTORIES HERE ---
    INPUT_DIR = r"C:\Madhan\CAPL_Gen_Tool\input"
    OUTPUT_DIR = r"C:\Madhan\CAPL_Gen_Tool\output"
    
    main(INPUT_DIR, OUTPUT_DIR)
