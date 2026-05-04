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
        """Returns {TARGET_INTERNAL_COLUMN : SOURCE_EXCEL_COLUMN}"""
        base_map = {
            "SWC": "SWC", 
            "TEST_TYPE": "TEST_TYPE", 
            "BASIC_FUNCTION_NAME": "BASIC_FUNCTION_NAME",
            "CAN_CLUSTER": "CAN_CLUSTER"
        }
        if sheet_type == "E2E_ETH":
            base_map.update({
                "E2E_ETH_REQ_ID": ["E2E_ETH_REQ_ID", "REQ ID", "REQ_ID", "REQID"],
                "SOMEIP_PORT": ["SOMEIP_PORT", "Port", "SOMEIP_PORT_MAPPING", "Port Name"],
                "ATTRIBUTE_VALUE": ["ATTRIBUTE_VALUE", "Attribute value", "SOMEIP_ATTRIBUTE_VALUE_MAPPING"],
                "CAN_PORT": ["CAN_PORT", "CAN_PORT_MAPPING", "Port Name"],
                "PATH_SYNTHESIS": ["PATH_SYNTHESIS", "CAN_PATH_SYNTHESIS_MAPPING", "Path Synthesis"],
                "SOMEIP_TOPIC": ["SOMEIP_TOPIC", "Topic", "Topic Name"],
                "SOMEIP_TOPIC_ATTRIBUTE": ["SOMEIP_TOPIC_ATTRIBUTE", "Topic Attribute", "Attribute"]
            })
        elif sheet_type == "E2E_CAN":
            base_map.update({
                "E2E_CAN_REQ_ID": ["E2E_CAN_REQ_ID", "REQ ID", "REQ_ID", "REQID"],
                "CAN_PORT": ["CAN_PORT", "Port Name", "CAN_PORT_MAPPING"],
                "PATH_SYNTHESIS": ["PATH_SYNTHESIS", "Path Synthesis", "CAN_PATH_SYNTHESIS_MAPPING"],
                "SOMEIP_PORT": ["SOMEIP_PORT", "SOMEIP_PORT_MAPPING", "Port", "Port Name"],
                "ATTRIBUTE_VALUE": ["ATTRIBUTE_VALUE", "Attribute value", "SOMEIP_ATTRIBUTE_VALUE_MAPPING"],
                "SOMEIP_TOPIC": ["SOMEIP_TOPIC", "Topic", "Topic Name"],
                "SOMEIP_TOPIC_ATTRIBUTE": ["SOMEIP_TOPIC_ATTRIBUTE", "Topic Attribute", "Attribute"]
            })
        return base_map

    def get_output_columns(self, sheet_type: str) -> list:
        base_cols = [
            "CAN_CLUSTER",
            "BASIC_FUNCTION_NAME",
            "CAN_DB_SIGNAL_NAME",
            "CAN_PERIODICITY",
            "CAN_ENUM",
            "CAN_MIN_RAW",
            "CAN_MAX_RAW",
            "CAN_OFFSET",
            "CAN_RESOLUTION",
            "SOMEIP_DB_SIGNAL_NAME",
            "SOMEIP_ENUM",
            "SOMEIP_MIN_PHY",
            "SOMEIP_MAX_PHY",
            "SOMEIP_OFFSET",
            "SOMEIP_RESOLUTION",
            "COMPUTED_CAN_ENUM_MIN",
            "COMPUTED_CAN_ENUM_MID",
            "COMPUTED_CAN_ENUM_MAX",
            "COMPUTED_CAN_MIN_PHY",
            "COMPUTED_CAN_MID_PHY",
            "COMPUTED_CAN_MAX_PHY",
            "COMPUTED_SOMEIP_ENUM_MIN",
            "COMPUTED_SOMEIP_ENUM_MID",
            "COMPUTED_SOMEIP_ENUM_MAX",
            "COMPUTED_SOMEIP_MIN_PHY",
            "COMPUTED_SOMEIP_MID_PHY",
            "COMPUTED_SOMEIP_MAX_PHY"
        ]

        if sheet_type == "E2E_ETH":
            return [
                "E2E_ETH_REQ_ID",
                "SWC",
                "SOMEIP_PORT",
                "ATTRIBUTE_VALUE",
                "CAN_PORT",
                "PATH_SYNTHESIS",
                "SOMEIP_TOPIC",
                "SOMEIP_TOPIC_ATTRIBUTE",
                "TEST_TYPE"
            ] + base_cols

        if sheet_type == "E2E_CAN":
            return [
                "E2E_CAN_REQ_ID",
                "SWC",
                "CAN_PORT",
                "PATH_SYNTHESIS",
                "SOMEIP_PORT",
                "ATTRIBUTE_VALUE",
                "SOMEIP_TOPIC",
                "SOMEIP_TOPIC_ATTRIBUTE",
                "TEST_TYPE"
            ] + base_cols

        return ["SWC", "TEST_TYPE"] + base_cols

    def clean_test_type(self, val) -> str:
        if pd.isna(val): return "UNKNOWN_TT"
        tt = str(val).upper().replace(" ", "")
        tt = re.sub(r"F&FSOMEIP|SOMEIPF&F", "SOMEIP_FF", tt)
        tt = re.sub(r"[\(\)]", "_", tt)
        tt = re.sub(r"__+", "_", tt).strip("_")
        if "HVB" in tt: tt = "CAN->SWC_HVB"
        return tt

    def compute_basic_function_name(self, row) -> str:
        tt_raw = str(row.get('TEST_TYPE', '')).upper()
        if any(x in tt_raw for x in ["NONEED", "ENABLER", "NO_NEED"]):
            return "FUNCTION_NOT_REQUIRED"

        tt = str(row.get('TEST_TYPE', '')).strip()
        swc = str(row.get('SWC', '')).strip()
        sp = str(row.get('SOMEIP_PORT', '')).strip()
        raw_cp = str(row.get('CAN_PORT', '')).strip() if pd.notna(row.get('CAN_PORT')) else "UnknownPort"
        cp = f"I{raw_cp}"
        attr = self.can_mapper.normalize_attr(row.get('ATTRIBUTE_VALUE'))

        # For valuestate attributes, use the corresponding value attribute for function naming
        if attr and ("valuestate" in attr.lower() or "value_state" in attr.lower()):
            attr = re.sub(r'valuestate', '', attr, flags=re.IGNORECASE).strip()
            attr = re.sub(r'value_state', '', attr, flags=re.IGNORECASE).strip()

        # Extract event name from SOMEIP_PORT (second part after splitting by '_')
        event_name = sp.split('_')[1] if '_' in sp and len(sp.split('_')) > 1 else sp

        name = None
        if tt in ['CAN->SOMEIP', 'CAN->SOMEIP_FF', 'CAN->SOMEIP_AACP']: 
            name = f"basic_function_{cp}_{event_name}_{attr}" if attr else None
        elif tt in ['SOMEIP->CAN', 'SOMEIP_FF->CAN']: 
            name = f"basic_function_{event_name}_{attr}_{cp}" if attr else None
        elif tt in ['CAN->SWC', 'CAN->SWC_HVB']: 
            name = f"basic_function_{cp}_SWC"
        elif tt == 'SWC->CAN': 
            name = f"basic_function_SWC_{cp}"
        elif tt in ['SOMEIP->SWC', 'SOMEIP_FF->SWC']: 
            name = f"basic_function_{event_name}_{attr}_SWC" if attr else None
        elif tt in ['SWC->SOMEIP', 'SWC->SOMEIP_FF', 'SWC->SOMEIP_AACP']: 
            name = f"basic_function_SWC_{event_name}_{attr}" if attr else None
        elif tt == 'CAROS->SWC': 
            name = f"basic_function_CarOS_{event_name}_{attr}_SWC" if attr else None
        elif tt == 'CAN->CAN': 
            name = f"basic_function_{cp}_{cp}"
        else:
            name = f"basic_function_{event_name}_{attr}" if attr else None

        if name and len(name) > 128:
            log.warning(f"Function name exceeds 128 characters: {name} (length: {len(name)})")

        return name

    def cross_fill_function_names(self, df_list):
        """Cross-references SOMEIP_PORT to fill in missing BASIC_FUNCTION_NAMEs."""
        combined = pd.concat(df_list, ignore_index=True)
        
        # Filter to only rows that have a valid function name computed
        valid_pool = combined[~combined['BASIC_FUNCTION_NAME'].isin([None, "FUNCTION_NOT_REQUIRED"])]
        
        # Safety check to avoid KeyErrors if the sheet was empty or had no valid SOMEIP_PORT matches
        global_map = {}
        if not valid_pool.empty and 'SOMEIP_PORT' in valid_pool.columns:
            global_map = valid_pool.drop_duplicates('SOMEIP_PORT').set_index('SOMEIP_PORT')['BASIC_FUNCTION_NAME'].to_dict()

        for df in df_list:
            if 'BASIC_FUNCTION_NAME' not in df.columns:
                df['BASIC_FUNCTION_NAME'] = None
                
            mask_none = df['BASIC_FUNCTION_NAME'].isna()
            
            # Map if we have a mapping available
            if mask_none.any() and 'SOMEIP_PORT' in df.columns and global_map:
                # Only fill if SOMEIP_PORT is valid (not NaN, not empty, not 'N/A')
                valid_sp_mask = df['SOMEIP_PORT'].notna() & (df['SOMEIP_PORT'] != '') & (df['SOMEIP_PORT'] != 'N/A')
                fill_mask = mask_none & valid_sp_mask
                if fill_mask.any():
                    df.loc[fill_mask, 'BASIC_FUNCTION_NAME'] = df.loc[fill_mask, 'SOMEIP_PORT'].map(global_map)
                
            # df['BASIC_FUNCTION_NAME'] = df['BASIC_FUNCTION_NAME'].fillna("basic_function__UNKNOWN_CONFIG")
            
        return df_list

    def process_file(self, input_excel: str, output_dir: str):
        log.info(f"Orchestrating mappings for: {os.path.basename(input_excel)}")
        
        base_name = os.path.basename(input_excel).replace(".xlsx", "_Intermediate.xlsx")
        output_path = os.path.join(output_dir, base_name)
        os.makedirs(output_dir, exist_ok=True)

        xls = pd.ExcelFile(input_excel)
        sheets_to_process = [s for s in ["E2E_ETH", "E2E_CAN"] if s in xls.sheet_names]
        
        processed_dfs = []

        for sheet in sheets_to_process:
            log.info(f"Processing sheet: {sheet}")
            df_in = pd.read_excel(xls, sheet_name=sheet)
            df_out = pd.DataFrame()
            
            # 1. Map Columns 
            mapping = self.get_column_mapping(sheet)
            for target, source_candidates in mapping.items():
                source_candidates = source_candidates if isinstance(source_candidates, list) else [source_candidates]
                source_column = BaseMapper.resolve_column_name(df_in.columns, source_candidates)
                df_out[target] = df_in[source_column] if source_column else None

            # 2. Clean Core Data
            if "TEST_TYPE" in df_out.columns:
                df_out["TEST_TYPE"] = df_out["TEST_TYPE"].apply(self.clean_test_type)
            if "PATH_SYNTHESIS" in df_out.columns:
                df_out["CAN_CLUSTER"] = df_out["PATH_SYNTHESIS"].apply(self.can_mapper.extract_cluster)

            # 3. Enrich with CAN Data
            if "CAN_PORT" in df_out.columns:
                can_res = df_out.apply(lambda r: self.can_mapper.get_signal_data(r.get("CAN_PORT"), r.get("CAN_CLUSTER")), axis=1, result_type='expand')
                df_out = pd.concat([df_out, can_res], axis=1)

            # 4. Enrich with SOME/IP Data
            if "ATTRIBUTE_VALUE" in df_out.columns:
                eth_res = df_out.apply(lambda r: self.eth_mapper.get_signal_data(r.get("ATTRIBUTE_VALUE"), r.get("SOMEIP_PORT")), axis=1, result_type='expand')
                df_out = pd.concat([df_out, eth_res], axis=1)

            # 5. Compute Initial Function Names
            df_out['BASIC_FUNCTION_NAME'] = df_out.apply(self.compute_basic_function_name, axis=1)

            ordered_columns = [c for c in self.get_output_columns(sheet) if c in df_out.columns]
            extra_columns = [c for c in df_out.columns if c not in ordered_columns]
            df_out = pd.concat([df_out[ordered_columns], df_out[extra_columns]], axis=1)

            processed_dfs.append(df_out)

        # 6. Cross-Fill Function Names across all parsed sheets
        if processed_dfs:
            processed_dfs = self.cross_fill_function_names(processed_dfs)

        # 7. Save Output
        log.info(f"Saving to {output_path}...")
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for idx, sheet in enumerate(sheets_to_process):
                processed_dfs[idx].to_excel(writer, sheet_name=f"{sheet}_PARSED", index=False)
        
        log.info("✅ Intermediate Generation Complete.")