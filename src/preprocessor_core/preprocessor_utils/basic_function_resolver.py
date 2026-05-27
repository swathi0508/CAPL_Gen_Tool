import re
import pandas as pd

class BasicFunctionResolver:
    """
    Self-contained orchestrator for Basic Function Names.
    Manages Step 1 (Preparation) and Step 2 (Finalization) internally.
    """

    def __init__(self):
        self.cluster_map = {
            "CAN_FD_PT": "PT",
            "CAN_FD_CHASSIS": "CH",
            "CAN_ITS3_FD": "ITS3",
            "CAN_ITS5_FD": "ITS5",
            "PCU4_CAN": "PCU4",
            "CAN_EXT": "EXT",
            "CAN_FD_ACCESS2": "ACC2",
            "EthernetCluster": "ETH"
        }

    def _generate_naming_string(self, row_data: dict) -> str:
        """The core naming engine with internal prefixing and mapping."""
        test_type = str(row_data.get('test_type', '')).upper()
        someip_port = str(row_data.get('someip_port', '')).strip()
        attribute = str(row_data.get('attribute_value', '')).strip()
        
        raw_port = str(row_data.get('can_port_raw', ''))
        can_port = f"I{raw_port}" if raw_port not in ["N/A", "", "None"] else "IUnknownPort"
        
        raw_cluster = str(row_data.get('can_cluster_raw', ''))
        can_cluster = self.cluster_map.get(raw_cluster, "UnknownCluster")

        # Define all new variables for CAN->CAN in the same place as other variables
        can_to_can_port = str(row_data.get('can_to_can_port', '')).strip()
        can2_port = f"I{can_to_can_port}" if can_to_can_port not in ["N/A", "", "None"] else "IUnknownPort"
        raw_can2_cluster = str(row_data.get('can2_cluster_raw', ''))
        can2_cluster = self.cluster_map.get(raw_can2_cluster, "UnknownCluster")
        can_r_p = str(row_data.get('can_r_p', '')).strip().upper()

        event_name = someip_port.split('_')[1] if '_' in someip_port and len(someip_port.split('_')) > 1 else someip_port

        if any(x in test_type for x in ["CAN->SOMEIP", "CAN->SOMEIP_AACP", "CAN->SOMEIP_FF"]): 
            return f"basic_fn_{can_port}_{can_cluster}_{event_name}_{attribute}"
        if any(x in test_type for x in ["SOMEIP->CAN", "SOMEIP_FF->CAN"]): 
            return f"basic_fn_{event_name}_{attribute}_{can_port}_{can_cluster}"
        if any(x in test_type for x in ["CAN->SWC", "CAN->SWC_HVB"]): 
            return f"basic_fn_{can_port}_{can_cluster}_SWC"
        if "SWC->CAN" in test_type: 
            return f"basic_fn_SWC_{can_port}_{can_cluster}"
        if any(x in test_type for x in ["SOMEIP->SWC", "SOMEIP_FF->SWC"]): 
            return f"basic_fn_{event_name}_{attribute}_SWC"
        if any(x in test_type for x in ["SWC->SOMEIP", "SWC->SOMEIP_FF", "SWC->SOMEIP_AACP"]): 
            return f"basic_fn_SWC_{event_name}_{attribute}"
        if "CAROS->SWC" in test_type: 
            return f"basic_fn_CAROS_{event_name}_{attribute}_SWC"
        if "CAN->CAN" in test_type: 
            if can_r_p == "R":
                return f"basic_fn_{can_port}_{can_cluster}_{can2_port}_{can2_cluster}"
            elif can_r_p == "P":
                return f"basic_fn_{can2_port}_{can2_cluster}_{can_port}_{can_cluster}"
            
        return "basic_fn_UNKNOWN"

    def resolve_all_basic_functions(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Finalized BFN Resolver: strictly updates only whitelisted columns.
        """
        # 1. Define the 'Safe Zone' - This class only has permission to write here
        target_cols = ["BASIC_FUNCTION_NAME"]
        
        # Mapping definition adjusted solely to properly fetch cluster via CAN_PORT cross-reference
        port_to_cluster_lookup = (
            df[['CAN_PORT', 'CAN_CLUSTER']]
            .dropna(subset=['CAN_PORT'])
            .assign(CAN_PORT_STR=lambda d: d['CAN_PORT'].astype(str).str.strip())
            .set_index('CAN_PORT_STR')['CAN_CLUSTER']
            .to_dict()
        )

        # 2. Define the processing logic for Pass 1
        def execute_step1_prepare(row):
            test_type = str(row.get('TEST_TYPE', '')).upper()
            if any(x in test_type for x in ["NONEED", "ENABLER", "NO_NEED"]): 
                return "FUNCTION_NOT_REQUIRED"

            attr = str(row.get('ATTRIBUTE_VALUE', '')).strip()
            topic_attr = str(row.get('SOMEIP_TOPIC_ATTRIBUTE', '')).lower()
            port = str(row.get('SOMEIP_PORT', '')).strip()
            
            # Define new CAN->CAN extraction variables in the same block
            can_to_can_port = str(row.get('CAN_TO_CAN_MAPPING', '')).strip()
            can2_cluster_raw = port_to_cluster_lookup.get(can_to_can_port, "UnknownCluster")

            is_state = "value_state" in topic_attr or "valuestate" in topic_attr or \
                       bool(re.search(r'ValueState|value_state', attr, re.IGNORECASE))

            if is_state:
                stripped_attr = re.sub(r'ValueState|value_state', '', attr, flags=re.IGNORECASE).strip()
                return f"PENDING_RESOLVE|{port}|{stripped_attr}|{test_type}"
            
            return self._generate_naming_string({
                'test_type': test_type, 'someip_port': port, 'attribute_value': attr,
                'can_port_raw': row.get('CAN_PORT'), 'can_cluster_raw': row.get('CAN_CLUSTER'),
                'can_to_can_port': can_to_can_port, 'can2_cluster_raw': can2_cluster_raw,
                'can_r_p': row.get('CAN_R_P')
            })

        # --- APPLY STEP 1 ---
        mask = df['TEST_TYPE'].notna()
        if not mask.any():
            return df

        # USE TARGET_COLS HERE: Explicitly limit the write operation
        df.loc[mask, target_cols] = df.loc[mask].apply(execute_step1_prepare, axis=1).values.reshape(-1, 1)

        # --- Internal Lookup Building ---
        # (Filtering only based on the work we just did in the safe zone)
        standard_signals = df[
            (~df['BASIC_FUNCTION_NAME'].str.contains('PENDING_RESOLVE', na=False)) & 
            (df['BASIC_FUNCTION_NAME'] != "FUNCTION_NOT_REQUIRED")
        ]
        
        lookup_by_pair = dict(zip(
            zip(standard_signals['SOMEIP_PORT'].astype(str).str.strip(), standard_signals['ATTRIBUTE_VALUE'].astype(str).str.strip()), 
            standard_signals['BASIC_FUNCTION_NAME']
        ))
        lookup_by_port = dict(zip(standard_signals['SOMEIP_PORT'].astype(str).str.strip(), standard_signals['BASIC_FUNCTION_NAME']))

        # --- APPLY STEP 2 (Final Resolution) ---
        def execute_step2_finalize(row):
            val = str(row.get('BASIC_FUNCTION_NAME', ''))
            if not val.startswith("PENDING_RESOLVE"): 
                return val
            
            parts = val.split('|')
            port, base_attr, tt = parts[1], parts[2], parts[3]

            # Define new CAN->CAN extraction variables in the same block
            can_to_can_port = str(row.get('CAN_TO_CAN_MAPPING', '')).strip()
            can2_cluster_raw = port_to_cluster_lookup.get(can_to_can_port, "UnknownCluster")

            resolved = lookup_by_pair.get((port, base_attr))
            if not resolved or base_attr == "":
                resolved = lookup_by_port.get(port)

            if resolved:
                return resolved

            return self._generate_naming_string({
                'test_type': tt, 'someip_port': port, 'attribute_value': "ValueState",
                'can_port_raw': row.get('CAN_PORT'), 'can_cluster_raw': row.get('CAN_CLUSTER'),
                'can_to_can_port': can_to_can_port, 'can2_cluster_raw': can2_cluster_raw,
                'can_r_p': row.get('CAN_R_P')
            })

        # USE TARGET_COLS HERE: Again, strictly limit the update to the whitelist
        df.loc[mask, target_cols] = df.loc[mask].apply(execute_step2_finalize, axis=1).values.reshape(-1, 1)

        return df
