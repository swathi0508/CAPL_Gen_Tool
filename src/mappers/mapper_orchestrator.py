import os
import re
import pandas as pd
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
                "E2E_ETH_REQ_ID": "REQ ID", 
                "SOMEIP_PORT": "Port", 
                "ATTRIBUTE_VALUE": "Attribute value",
                "CAN_PORT": "CAN_PORT_MAPPING", 
                "PATH_SYNTHESIS": "CAN_PATH_SYNTHESIS_MAPPING"
            })
        elif sheet_type == "E2E_CAN":
            base_map.update({
                "E2E_CAN_REQ_ID": "REQ ID", 
                "CAN_PORT": "Port Name", 
                "PATH_SYNTHESIS": "Path Synthesis",
                "SOMEIP_PORT": "SOMEIP_PORT_MAPPING", 
                "ATTRIBUTE_VALUE": "SOMEIP_ATTRIBUTE_VALUE_MAPPING"
            })
        return base_map

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

        if attr is None: return None

        if tt in ['CAN->SOMEIP', 'CAN->SOMEIP_FF', 'CAN->SOMEIP_AACP']: 
            return f"basic_function__{swc}__{cp}__{sp}__{attr}"
        if tt in ['SOMEIP->CAN', 'SOMEIP_FF->CAN']: 
            return f"basic_function__{swc}__{sp}__{attr}__{cp}"
        if tt in ['CAN->SWC', 'CAN->SWC_HVB']: return f"basic_function__{swc}__{cp}__SWC"
        if tt == 'SWC->CAN': return f"basic_function__{swc}__SWC__{cp}"
        if tt in ['SOMEIP->SWC', 'SOMEIP_FF->SWC']: return f"basic_function__{swc}__{sp}__{attr}__SWC"
        if tt in ['SWC->SOMEIP', 'SWC->SOMEIP_FF', 'SWC->SOMEIP_AACP']: 
            return f"basic_function__{swc}__SWC__{sp}__{attr}"
        if tt == 'CAROS->SWC': return f"basic_function__{swc}__CarOS__{sp}__{attr}__SWC"
        if tt == 'CAN->CAN': return f"basic_function__{swc}__{cp}__{cp}"

        return f"basic_function__{swc}__{sp}__{attr}"

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
                df.loc[mask_none, 'BASIC_FUNCTION_NAME'] = df.loc[mask_none, 'SOMEIP_PORT'].map(global_map)
                
            df['BASIC_FUNCTION_NAME'] = df['BASIC_FUNCTION_NAME'].fillna("basic_function__UNKNOWN_CONFIG")
            
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
            for target, source in mapping.items():
                df_out[target] = df_in[source] if source in df_in.columns else None

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
                # --> CRITICAL UPDATE: Passing SOMEIP_PORT (Event) to prevent ValueState collisions
                eth_res = df_out.apply(lambda r: self.eth_mapper.get_signal_data(r.get("ATTRIBUTE_VALUE"), r.get("SOMEIP_PORT")), axis=1, result_type='expand')
                df_out = pd.concat([df_out, eth_res], axis=1)

            # 5. Compute Initial Function Names
            df_out['BASIC_FUNCTION_NAME'] = df_out.apply(self.compute_basic_function_name, axis=1)
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