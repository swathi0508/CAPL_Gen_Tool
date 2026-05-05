import os
import re
import pandas as pd
from mappers.base_mapper import BaseMapper
from mappers.can_mapper import CANMapper
from mappers.someip_mapper import SomeIPMapper
from core.logger import log

class MapperOrchestrator:
    """Coordinates the end-to-end creation of Intermediate Excel sheets."""
    
    def __init__(self, can_cache: str, eth_cache: str):
        self.can_mapper = CANMapper(can_cache)
        self.eth_mapper = SomeIPMapper(eth_cache)

    def get_column_mapping(self, sheet_type: str) -> dict:
        base_map = {
            "SWC": "SWC", 
            "TEST_TYPE": "TEST_TYPE", 
            "BASIC_FUNCTION_NAME": "BASIC_FUNCTION_NAME",
            "CAN_CLUSTER": "CAN_CLUSTER"
        }
        common_cols = {
            "SOMEIP_PORT": ["SOMEIP_PORT", "PORT", "SOMEIP_PORT_MAPPING", "PORT NAME"],
            "ATTRIBUTE_VALUE": ["ATTRIBUTE_VALUE", "ATTRIBUTE VALUE", "SOMEIP_ATTRIBUTE_VALUE_MAPPING"],
            "CAN_PORT": ["CAN_PORT", "CAN_PORT_MAPPING", "PORT NAME"],
            "PATH_SYNTHESIS": ["PATH_SYNTHESIS", "CAN_PATH_SYNTHESIS_MAPPING", "PATH SYNTHESIS"],
            "SOMEIP_TOPIC": ["SOMEIP_TOPIC", "TOPIC", "TOPIC NAME"],
            "SOMEIP_TOPIC_ATTRIBUTE": ["SOMEIP_TOPIC_ATTRIBUTE", "ATTRIBUTE", "TOPIC ATTRIBUTE"]
        }
        if sheet_type == "E2E_ETH":
            base_map.update({"E2E_ETH_REQ_ID": ["E2E_ETH_REQ_ID", "REQ ID", "REQ_ID"], **common_cols})
        elif sheet_type == "E2E_CAN":
            base_map.update({"E2E_CAN_REQ_ID": ["E2E_CAN_REQ_ID", "REQ ID", "REQ_ID"], **common_cols})
        return base_map

    def get_output_columns(self, sheet_type: str) -> list:
        base_cols = [
            "CAN_CLUSTER", "BASIC_FUNCTION_NAME", "CAN_DB_SIGNAL_NAME", "CAN_PERIODICITY",
            "CAN_ENUM", "CAN_MIN_RAW", "CAN_MAX_RAW", "CAN_OFFSET", "CAN_RESOLUTION",
            "SOMEIP_DB_SIGNAL_NAME", "SOMEIP_ENUM", "SOMEIP_MIN_PHY", "SOMEIP_MAX_PHY",
            "SOMEIP_OFFSET", "SOMEIP_RESOLUTION", "COMPUTED_CAN_ENUM_MIN", "COMPUTED_CAN_ENUM_MID",
            "COMPUTED_CAN_ENUM_MAX", "COMPUTED_CAN_MIN_PHY", "COMPUTED_CAN_MID_PHY",
            "COMPUTED_CAN_MAX_PHY", "COMPUTED_SOMEIP_ENUM_MIN", "COMPUTED_SOMEIP_ENUM_MID",
            "COMPUTED_SOMEIP_ENUM_MAX", "COMPUTED_SOMEIP_MIN_PHY", "COMPUTED_SOMEIP_MID_PHY",
            "COMPUTED_SOMEIP_MAX_PHY"
        ]
        if sheet_type == "E2E_ETH":
            return ["E2E_ETH_REQ_ID", "SWC", "SOMEIP_PORT", "ATTRIBUTE_VALUE", "CAN_PORT", "PATH_SYNTHESIS", "SOMEIP_TOPIC", "SOMEIP_TOPIC_ATTRIBUTE", "TEST_TYPE"] + base_cols
        if sheet_type == "E2E_CAN":
            return ["E2E_CAN_REQ_ID", "SWC", "CAN_PORT", "PATH_SYNTHESIS", "SOMEIP_PORT", "ATTRIBUTE_VALUE", "SOMEIP_TOPIC", "SOMEIP_TOPIC_ATTRIBUTE", "TEST_TYPE"] + base_cols
        return ["SWC", "TEST_TYPE"] + base_cols

    def clean_test_type(self, val) -> str:
        if pd.isna(val): return "UNKNOWN_TT"
        tt = str(val).upper().replace(" ", "")
        tt = re.sub(r"F&FSOMEIP|SOMEIPF&F", "SOMEIP_FF", tt)
        tt = re.sub(r"[\(\)]", "_", tt)
        tt = re.sub(r"__+", "_", tt).strip("_")
        return tt

    def compute_basic_function_name(self, row) -> str:
        tt = str(row.get('TEST_TYPE', '')).upper()
        if any(x in tt for x in ["NONEED", "ENABLER", "NO_NEED"]):
            return "FUNCTION_NOT_REQUIRED"
        
        sp = str(row.get('SOMEIP_PORT', '')).strip()
        attr_raw = str(row.get('ATTRIBUTE_VALUE', '')).strip()
        topic_attr = str(row.get('SOMEIP_TOPIC_ATTRIBUTE', '')).lower()
        
        is_state = "value_state" in topic_attr or "valuestate" in topic_attr or \
                   bool(re.search(r'ValueState|value_state', attr_raw, re.IGNORECASE))

        def generate_name():
            cluster_map = {
                "CAN_FD_PT": "PT", "CAN_FD_CHASSIS": "CH", "CAN_ITS3_FD": "ITS3",
                "CAN_ITS5_FD": "ITS5", "PCU4_CAN": "PCU4", "CAN_EXT": "EXT", "CAN_FD_ACCESS2": "ACC2"
            }
            raw_cp = str(row.get('CAN_PORT', '')).strip() if pd.notna(row.get('CAN_PORT')) else "UnknownPort"
            cp = f"I{raw_cp}"
            raw_cc = str(row.get('CAN_CLUSTER', '')).strip()
            cc = cluster_map.get(raw_cc, raw_cc)
            attr = attr_raw
            event_name = sp.split('_')[1] if '_' in sp and len(sp.split('_')) > 1 else sp

            if any(x in tt for x in ["CAN->SOMEIP", "CAN->SOMEIP_AACP", "CAN->SOMEIP_FF"]):
                return f"basic_fn_{cp}_{cc}_{event_name}_{attr}"
            if any(x in tt for x in ["SOMEIP->CAN", "SOMEIP_FF->CAN"]):
                return f"basic_fn_{event_name}_{attr}_{cp}_{cc}"
            if any(x in tt for x in ["CAN->SWC", "CAN->SWC_HVB"]):
                return f"basic_fn_{cp}_{cc}_SWC"
            if "SWC->CAN" in tt:
                return f"basic_fn_SWC_{cp}_{cc}"
            if any(x in tt for x in ["SOMEIP->SWC", "SOMEIP_FF->SWC"]):
                return f"basic_fn_{event_name}_{attr}_SWC"
            if any(x in tt for x in ["SWC->SOMEIP", "SWC->SOMEIP_FF", "SWC->SOMEIP_AACP"]):
                return f"basic_fn_SWC_{event_name}_{attr}"
            if "CAROS->SWC" in tt:
                return f"basic_fn_CAROS_{event_name}_{attr}_SWC"
            if "CAN->CAN" in tt:
                return f"basic_fn_{cp}_{cc}_{cp}_{cc}"
            return "basic_fn_UNKNOWN"

        if is_state:
            stripped = re.sub(r'ValueState|value_state', '', attr_raw, flags=re.IGNORECASE).strip()
            return f"PENDING_STATE_MATCH|{sp}|{stripped}|{generate_name()}|{tt}"
        
        return generate_name()

    def cross_fill_global_data(self, df_list):
        """
        SELF-HEALING MODULE:
        Scans all sheets. If E2E_CAN has the Path/Cluster/BFN, it universally copies 
        them into the E2E_ETH sheet to heal missing or <NA> cells.
        """
        combined = pd.concat(df_list, ignore_index=True)
        bfn_lookup = {}
        path_lookup = {}
        cluster_lookup = {}

        # Safely detect empty values across all Pandas versions
        def is_empty(val):
            return pd.isna(val) or str(val).strip() in ["nan", "None", "", "N/A", "<NA>"]

        for _, row in combined.iterrows():
            sp = str(row.get('SOMEIP_PORT', '')).strip()
            attr = str(row.get('ATTRIBUTE_VALUE', '')).strip()
            cp = str(row.get('CAN_PORT', '')).strip()

            if not is_empty(row.get('BASIC_FUNCTION_NAME')):
                bfn = str(row['BASIC_FUNCTION_NAME'])
                if "PENDING_STATE_MATCH" not in bfn and "UNKNOWN" not in bfn:
                    bfn_lookup[(sp, attr)] = bfn
                    bfn_lookup[sp] = bfn

            if not is_empty(cp):
                if not is_empty(row.get('PATH_SYNTHESIS')):
                    path_lookup[cp] = str(row['PATH_SYNTHESIS'])
                if not is_empty(row.get('CAN_CLUSTER')):
                    cluster_lookup[cp] = str(row['CAN_CLUSTER'])

        processed_dfs = []
        for df in df_list:
            # Heal Path Synthesis
            if 'PATH_SYNTHESIS' in df.columns:
                df['PATH_SYNTHESIS'] = df.apply(
                    lambda r: path_lookup.get(str(r.get('CAN_PORT', '')).strip(), r['PATH_SYNTHESIS']) 
                    if is_empty(r.get('PATH_SYNTHESIS')) else r['PATH_SYNTHESIS'], axis=1
                )
            
            # Heal CAN Cluster
            if 'CAN_CLUSTER' in df.columns:
                df['CAN_CLUSTER'] = df.apply(
                    lambda r: cluster_lookup.get(str(r.get('CAN_PORT', '')).strip(), r['CAN_CLUSTER']) 
                    if is_empty(r.get('CAN_CLUSTER')) else r['CAN_CLUSTER'], axis=1
                )

            # Heal Basic Function Name
            def resolve_bfn(row):
                val = str(row.get('BASIC_FUNCTION_NAME', ''))
                if not val.startswith("PENDING_STATE_MATCH") and "UNKNOWN" not in val:
                    return val if not is_empty(val) else "basic_fn_UNKNOWN"
                
                parts = val.split('|')
                if len(parts) >= 4:
                    sp, stripped_attr, fallback_name = parts[1], parts[2], parts[3]
                    
                    if stripped_attr and (sp, stripped_attr) in bfn_lookup:
                        return bfn_lookup[(sp, stripped_attr)]
                    if sp in bfn_lookup:
                        return bfn_lookup[sp]
                        
                    # Inject the newly healed CAN_CLUSTER into the fallback name!
                    if fallback_name != "basic_fn_UNKNOWN" and not is_empty(row.get('CAN_CLUSTER')):
                        fallback_name = fallback_name.replace("__", f"_{row['CAN_CLUSTER']}_")
                    return fallback_name
                return "basic_fn_UNKNOWN"

            if 'BASIC_FUNCTION_NAME' in df.columns:
                df['BASIC_FUNCTION_NAME'] = df.apply(resolve_bfn, axis=1)

            # Replace any lingering Pandas <NA> artifacts with clean "N/A"
            df = df.fillna("N/A").replace("<NA>", "N/A")
            processed_dfs.append(df)
            
        return processed_dfs

    def process_file(self, input_excel: str, output_dir: str):
        log.info(f"Processing: {os.path.basename(input_excel)}")
        base_name = os.path.basename(input_excel).replace(".xlsx", "_Intermediate.xlsx")
        output_path = os.path.join(output_dir, base_name)
        os.makedirs(output_dir, exist_ok=True)

        xls = pd.ExcelFile(input_excel)
        sheets_to_process = [s for s in xls.sheet_names if s.strip().upper() in ["E2E_ETH", "E2E_CAN"]]
        results = []

        for sheet in sheets_to_process:
            df_in = pd.read_excel(xls, sheet_name=sheet)
            df_in.columns = df_in.columns.astype(str).str.strip().str.upper()
            
            df_out = pd.DataFrame()
            mapping = self.get_column_mapping(sheet.strip().upper())
            
            for target, source in mapping.items():
                col = BaseMapper.resolve_column_name(df_in.columns, source if isinstance(source, list) else [source])
                df_out[target] = df_in[col] if col else None

            if "TEST_TYPE" in df_out.columns:
                df_out["TEST_TYPE"] = df_out["TEST_TYPE"].apply(self.clean_test_type)
            if "PATH_SYNTHESIS" in df_out.columns:
                df_out["CAN_CLUSTER"] = df_out["PATH_SYNTHESIS"].apply(self.can_mapper.extract_cluster)

            if "CAN_PORT" in df_out.columns:
                can_res = df_out.apply(lambda r: self.can_mapper.get_signal_data(r.get("CAN_PORT"), r.get("CAN_CLUSTER")), axis=1, result_type='expand')
                df_out = pd.concat([df_out, can_res], axis=1)
            if "ATTRIBUTE_VALUE" in df_out.columns:
                eth_res = df_out.apply(lambda r: self.eth_mapper.get_signal_data(r.get("ATTRIBUTE_VALUE"), r.get("SOMEIP_PORT")), axis=1, result_type='expand')
                df_out = pd.concat([df_out, eth_res], axis=1)

            df_out['BASIC_FUNCTION_NAME'] = df_out.apply(self.compute_basic_function_name, axis=1)
            
            ordered = [c for c in self.get_output_columns(sheet.strip().upper()) if c in df_out.columns]
            extra = [c for c in df_out.columns if c not in ordered]
            df_out = pd.concat([df_out[ordered], df_out[extra]], axis=1)
            results.append(df_out)

        # Triggers the Self-Healing process
        if results:
            results = self.cross_fill_global_data(results)

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for idx, sheet in enumerate(sheets_to_process):
                clean_sheet_name = sheet.strip().upper()
                results[idx].to_excel(writer, sheet_name=f"{clean_sheet_name}_PARSED", index=False)
        log.info("✅ Final resolution complete.")