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
            "SOMEIP_PORT": ["SOMEIP_PORT", "Port", "SOMEIP_PORT_MAPPING", "Port Name"],
            "ATTRIBUTE_VALUE": ["ATTRIBUTE_VALUE", "Attribute value", "SOMEIP_ATTRIBUTE_VALUE_MAPPING"],
            "CAN_PORT": ["CAN_PORT", "CAN_PORT_MAPPING", "Port Name"],
            "PATH_SYNTHESIS": ["PATH_SYNTHESIS", "CAN_PATH_SYNTHESIS_MAPPING", "Path Synthesis"],
            "SOMEIP_TOPIC": ["SOMEIP_TOPIC", "Topic", "Topic Name"],
            "SOMEIP_TOPIC_ATTRIBUTE": ["SOMEIP_TOPIC_ATTRIBUTE", "Attribute", "Topic Attribute"]
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

    def cross_fill_function_names(self, df_list):
        combined = pd.concat(df_list, ignore_index=True)
        lookup_map = {}
        port_only_map = {}

        for _, row in combined.iterrows():
            bfn = str(row['BASIC_FUNCTION_NAME'])
            if "PENDING_STATE_MATCH" not in bfn and bfn not in ["basic_fn_UNKNOWN", "FUNCTION_NOT_REQUIRED"]:
                sp = str(row['SOMEIP_PORT']).strip()
                attr = str(row['ATTRIBUTE_VALUE']).strip()
                lookup_map[(sp, attr)] = bfn
                port_only_map[sp] = bfn

        processed_dfs = []
        for df in df_list:
            def resolve_state(row):
                val = row['BASIC_FUNCTION_NAME']
                if not isinstance(val, str) or not val.startswith("PENDING_STATE_MATCH"):
                    return val
                
                parts = val.split('|')
                _, sp, stripped_attr, fallback_name, _ = parts
                
                if stripped_attr and (sp, stripped_attr) in lookup_map:
                    return lookup_map[(sp, stripped_attr)]

                if sp in port_only_map:
                    return port_only_map[sp]
                
                if fallback_name != "basic_fn_UNKNOWN":
                    return fallback_name

                return "basic_fn_UNKNOWN"

            df['BASIC_FUNCTION_NAME'] = df.apply(resolve_state, axis=1)
            processed_dfs.append(df)
        return processed_dfs

    def process_file(self, input_excel: str, output_dir: str):
        log.info(f"Processing: {os.path.basename(input_excel)}")
        base_name = os.path.basename(input_excel).replace(".xlsx", "_Intermediate.xlsx")
        output_path = os.path.join(output_dir, base_name)
        os.makedirs(output_dir, exist_ok=True)

        xls = pd.ExcelFile(input_excel)
        sheets_to_process = [s for s in ["E2E_ETH", "E2E_CAN"] if s in xls.sheet_names]
        results = []

        for sheet in sheets_to_process:
            df_in = pd.read_excel(xls, sheet_name=sheet)
            df_out = pd.DataFrame()
            mapping = self.get_column_mapping(sheet)
            
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
            
            ordered = [c for c in self.get_output_columns(sheet) if c in df_out.columns]
            extra = [c for c in df_out.columns if c not in ordered]
            df_out = pd.concat([df_out[ordered], df_out[extra]], axis=1)
            results.append(df_out)

        if results:
            results = self.cross_fill_function_names(results)

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for idx, sheet in enumerate(sheets_to_process):
                results[idx].to_excel(writer, sheet_name=f"{sheets_to_process[idx]}_PARSED", index=False)
        log.info("✅ Final resolution complete.")