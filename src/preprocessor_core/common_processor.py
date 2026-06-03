import math
import pandas as pd
from logger import log
from preprocessor_core.db_mappers.base_mapper import BaseMapper
from preprocessor_core.db_mappers.can_mapper import CANMapper
from preprocessor_core.db_mappers.someip_mapper import SomeIPMapper
from preprocessor_core.db_mappers.someip_ff_sysvar_mapper import SomeIPFFSysVarMapper
from preprocessor_core.db_mappers.aacp_sysvar_mapper import AacpSysVarMapper
from preprocessor_core.preprocessor_utils.basic_function_resolver import BasicFunctionResolver
from preprocessor_core.preprocessor_utils.enum_resolver import EnumResolver

class CommonProcessor:
    def __init__(self, can_db_data: dict, eth_db_data: dict, someip_ff_db_data: dict, aacp_db_data: dict):
        """
        Initializes the processor with specialized mappers and resolvers.
        The mappers are responsible for flagging IS_ENUM during database resolution.
        """
        self.can_mapper = CANMapper(can_db_data)
        self.eth_mapper = SomeIPMapper(eth_db_data)
        self.someip_ff_mapper = SomeIPFFSysVarMapper(someip_ff_db_data)
        self.aacp_mapper = AacpSysVarMapper(aacp_db_data)
        self.basic_function_mapper = BasicFunctionResolver()
        self.enum_mapper = EnumResolver()

    @staticmethod
    def _compute_bounds(min_in, max_in):
        """Modular Math Engine: Logic for physical boundary calculation."""
        try:
            # 1. Cast inputs directly to 64-bit doubles (Python floats)
            min_val = float(min_in)
            max_val = float(max_in)
            mid_val = (min_val + max_val) / 2.0

            # 2. Change to 'or': Apply rounding logic if EITHER mid or max is >= 1.0
            if mid_val >= 1.0 or max_val >= 1.0:
                min_rounded = float(math.ceil(min_val))
                max_rounded = float(math.floor(max_val))
                mid_rounded = float(math.ceil(mid_val))

                # Clamp rounded values strictly inside the original [min_val, max_val] window
                final_min = max(min_val, min(min_rounded, max_val))
                final_max = max(min_val, min(max_rounded, max_val))
                final_mid = max(final_min, min(mid_rounded, final_max))
            else:
                # Sub-1 or completely negative scale: use exact doubles natively
                final_min, final_mid, final_max = min_val, mid_val, max_val

            # 3. Explicitly return values as 64-bit doubles
            return {
                'MIN': float(final_min), 
                'MID': float(final_mid), 
                'MAX': float(final_max)
            }

        except (ValueError, TypeError):
            return {k: "N/A" for k in ['MIN', 'MID', 'MAX']}

    # --- STEP 1: Copy all necessary columns from Original requirements sheet into intermediate sheet ---
    def copy_requirement_columns(self, df_in: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
        log.info(f"Step 1: Extracting requirement columns for sheet '{sheet_name}'")
        try:
            df_in.columns = df_in.columns.astype(str).str.strip().str.upper()
            is_eth = "ETH" in sheet_name.upper()
            
            if is_eth:
                core_order = ["E2E_ETH_REQ_ID", "SWC", "SOMEIP_PORT", "ATTRIBUTE_VALUE", "CAN_PORT", "PATH_SYNTHESIS", "SOMEIP_TOPIC", "SOMEIP_TOPIC_ATTRIBUTE", "RUNTIME_ENV_RECEIVER", "TEST_TYPE"]
            else:
                core_order = ["E2E_CAN_REQ_ID", "SWC", "CAN_PORT", "PATH_SYNTHESIS", "SOMEIP_PORT", "ATTRIBUTE_VALUE", "SOMEIP_TOPIC", "SOMEIP_TOPIC_ATTRIBUTE", "RUNTIME_ENV_RECEIVER", "CAN_TO_CAN_MAPPING", "CAN_R_P", "TEST_TYPE"]

            mapping = {
                "E2E_ETH_REQ_ID": ["E2E_ETH_REQ_ID", "REQ ID", "REQ_ID", "REQUIREMENT ID"],
                "E2E_CAN_REQ_ID": ["E2E_CAN_REQ_ID", "REQ ID", "REQ_ID", "REQUIREMENT ID"],
                "SOMEIP_PORT": ["SOMEIP_PORT", "PORT", "SOMEIP_PORT_MAPPING", "PORT NAME"],
                "ATTRIBUTE_VALUE": ["ATTRIBUTE_VALUE", "ATTRIBUTE VALUE", "SOMEIP_ATTRIBUTE_VALUE_MAPPING"],
                "CAN_PORT": ["CAN_PORT", "CAN_PORT_MAPPING", "PORT NAME"],
                "PATH_SYNTHESIS": ["PATH_SYNTHESIS", "CAN_PATH_SYNTHESIS_MAPPING", "PATH SYNTHESIS"],
                "SOMEIP_TOPIC": ["SOMEIP_TOPIC", "TOPIC", "TOPIC NAME"],
                "SOMEIP_TOPIC_ATTRIBUTE": ["SOMEIP_TOPIC_ATTRIBUTE", "ATTRIBUTE", "TOPIC ATTRIBUTE"],
                "RUNTIME_ENV_RECEIVER": ["RUNTIME_ENV_RECEIVER", "RUNTIME ENV RECEIVER"],
                "CAN_TO_CAN_MAPPING" : ["CAN_TO_CAN_MAPPING"],
                "CAN_R_P": ["R/P"]
            }

            df_out = pd.DataFrame()
            for col in core_order:
                search_names = mapping.get(col, [col])
                found_col = BaseMapper.resolve_column_name(df_in.columns, search_names)
                df_out[col] = df_in[found_col].fillna("").astype(str) if found_col else ""
            
            return df_out
        
        except Exception as e:
            log.error(f"Step 1 critical failure: {str(e)}")
            raise

    # --- STEP 2: Append Additional Columns ---
    def define_additional_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        log.info("Step 2: Initializing intermediate template columns and IS_ENUM flags")
        
        additional_cols = [
            "CAN_CLUSTER", "CAN2_CLUSTER", "BASIC_FUNCTION_NAME", "IS_ENUM", "ENUM_LEXICAL_MATCH",
            "CAN_DB_SIGNAL_NAME", "CAN_PERIODICITY", "CAN_ENUM", "CAN_MIN_RAW", "CAN_MAX_RAW", "CAN_OFFSET", "CAN_RESOLUTION",
            "CAN2_DB_SIGNAL_NAME", "CAN2_PERIODICITY", "CAN2_ENUM", "CAN2_MIN_RAW", "CAN2_MAX_RAW", "CAN2_OFFSET", "CAN2_RESOLUTION",
            "SOMEIP_DB_SIGNAL_NAME", "SOMEIP_DB_SIGNAL_VALUESTATE", "SOMEIP_ENUM", "SOMEIP_MIN_PHY", "SOMEIP_MAX_PHY", "SOMEIP_OFFSET", "SOMEIP_RESOLUTION",
            "SOMEIP_FF_DB_SIGNAL_NAME", "SOMEIP_FF_DB_SIGNAL_VALUESTATE", "SOMEIP_FF_DB_SIGNAL_CONTROL", "SOMEIP_FF_ENUM", "SOMEIP_FF_DATATYPE",
            "SOMEIP_FF_SIGNAME_NAMESPACE", "SOMEIP_FF_SIGNAME_VARIABLE", "SOMEIP_FF_SIGVALUESTATE_NAMESPACE", "SOMEIP_FF_SIGVALUESTATE_VARIABLE", "SOMEIP_FF_CONTROL_NAMESPACE", "SOMEIP_FF_CONTROL_VARIABLE",
            "AACP_DB_SIGNAL_NAME", "AACP_DB_SIGNAL_VALUESTATE", "AACP_ENUM", "AACP_DATATYPE",
            "AACP_SIGNAME_NAMESPACE", "AACP_SIGNAME_VARIABLE", "AACP_SIGVALUESTATE_NAMESPACE", "AACP_SIGVALUESTATE_VARIABLE", "AACP_SIGNAME_DAQ",
            "COMPUTED_CAN_VALUE_MIN", "COMPUTED_CAN_VALUE_MID", "COMPUTED_CAN_VALUE_MAX",
            "COMPUTED_SOMEIP_VALUE_MIN", "COMPUTED_SOMEIP_VALUE_MID", "COMPUTED_SOMEIP_VALUE_MAX",
            "COMPUTED_SOMEIP_FF_VALUE_MIN", "COMPUTED_SOMEIP_FF_VALUE_MID", "COMPUTED_SOMEIP_FF_VALUE_MAX",
            "COMPUTED_AACP_VALUE_MIN", "COMPUTED_AACP_VALUE_MID", "COMPUTED_AACP_VALUE_MAX",
            "COMPUTED_CAN2_VALUE_MIN", "COMPUTED_CAN2_VALUE_MID", "COMPUTED_CAN2_VALUE_MAX"
        ]
        
        # Isolate and clean the target list if dealing with an active Ethernet signature
        if "E2E_ETH_REQ_ID" in df.columns:
            prohibited_can2_cols = {
                "CAN2_CLUSTER", "CAN2_DB_SIGNAL_NAME", "CAN2_PERIODICITY", "CAN2_ENUM", "CAN2_MIN_RAW", 
                "CAN2_MAX_RAW", "CAN2_OFFSET", "CAN2_RESOLUTION", "COMPUTED_CAN2_VALUE_MIN", 
                "COMPUTED_CAN2_VALUE_MID", "COMPUTED_CAN2_VALUE_MAX"
            }
            additional_cols = [col for col in additional_cols if col not in prohibited_can2_cols]
        
        master_order = list(df.columns) + additional_cols
        seen = set()
        final_cols = [x for x in master_order if not (x in seen or seen.add(x))]

        # Initializing new headers safely avoiding slice assignment warnings
        for col in final_cols:
            if col not in df.columns:
                df.loc[:, col] = False if col == "IS_ENUM" else ""

        df = df.reindex(columns=final_cols)
        df["IS_ENUM"] = df["IS_ENUM"].astype(bool)
        return df

    # --- STEP 3: Derive CAN Cluster ---
    def derive_can_cluster(self, df: pd.DataFrame) -> pd.DataFrame:
        log.info("Step 3: Extracting CAN Cluster information from Path Synthesis")
        
        if {"PATH_SYNTHESIS", "TEST_TYPE"}.issubset(df.columns):
            df["CAN_CLUSTER"] = df.apply(
                lambda r: self.can_mapper.extract_cluster(str(r["PATH_SYNTHESIS"])) 
                if "CAN" in str(r["TEST_TYPE"]).upper() else "", axis=1
            )
            
        if {"CAN_PORT", "CAN_CLUSTER", "CAN_TO_CAN_MAPPING", "TEST_TYPE"}.issubset(df.columns):
            df["CAN2_CLUSTER"] = ""
            
            lookup_df = df[['CAN_PORT', 'CAN_CLUSTER']].dropna()
            port_to_cluster = dict(zip(
                lookup_df['CAN_PORT'].astype(str).str.strip().str.replace('\u200b', ''),
                lookup_df['CAN_CLUSTER'].astype(str).str.strip().str.replace('\u200b', '')
            ))
            
            is_can_to_can = df["TEST_TYPE"].astype(str).str.strip().str.upper() == "CAN->CAN"
            
            if is_can_to_can.any():
                clean_mappings = df.loc[is_can_to_can, "CAN_TO_CAN_MAPPING"].astype(str).str.strip().str.replace('\u200b', '')
                df.loc[is_can_to_can, "CAN2_CLUSTER"] = clean_mappings.map(port_to_cluster).fillna("")
            
        return df

    # --- STEP 4: Compute Basic Function Name ---
    def derive_basic_function_names(self, df: pd.DataFrame) -> pd.DataFrame:
        log.info("Step 4: Resolving standardized Basic Function Names")
        return self.basic_function_mapper.resolve_all_basic_functions(df)

    # --- STEP 5_a: CAN Signal Resolution ---
    def resolve_can_signals_from_db(self, df: pd.DataFrame, test_type: str) -> pd.DataFrame:
        # Match any test type containing "CAN"
        pattern = "CAN"
        
        mask = (df["CAN_PORT"].notna()) & \
               (df["CAN_PORT"] != "") & \
               (df["TEST_TYPE"].str.contains(pattern, case=False, na=False))

        if mask.any():
            log.info(f"Step 5_a: Mapping CAN signals for {mask.sum()} matching rows.")
            df.loc[mask] = self.can_mapper.resolve(df.loc[mask])
            
        return df

    # --- STEP 5_b: SOMEIP Signal Resolution ---
    def resolve_someip_signals_from_db(self, df: pd.DataFrame, test_type: str) -> pd.DataFrame:
        # Matches if the row contains ANY of these keywords anywhere in its test type string
        pattern = "SOMEIP|SOMEIP_FF|CAROS|AACP"
    
        mask = (df["SOMEIP_PORT"].fillna("") != "") & \
               (df["TEST_TYPE"].str.contains(pattern, case=False, na=False))
    
        if mask.any():
            log.info(f"Step 5_b: Mapping SOME/IP signals for {mask.sum()} matching rows.")
            resolved_subset = self.eth_mapper.resolve(df.loc[mask].copy())
            
            # --- PANDAS 2.x WARNING FIX: Bypass df.update() ---
            # Directly overwrite the specific rows and columns using .loc 
            for col in resolved_subset.columns:
                if col not in df.columns:
                    df[col] = pd.NA  # Initialize if the column is entirely new
                
                # Coerce target column to object so it safely accepts bools, strings, or floats
                df[col] = df[col].astype(object)
                
                # Inject the resolved data strictly into the matching rows
                df.loc[mask, col] = resolved_subset[col]
            
        return df

    # --- STEP 5_c: SOMEIP_FF SysVar Resolution ---
    def resolve_someip_ff_signals_from_db(self, df: pd.DataFrame, test_type: str) -> pd.DataFrame:
        pattern = "SOMEIP_FF|CAROS"

        mask = (df["SOMEIP_PORT"].fillna("") != "") & \
               (df["TEST_TYPE"].str.contains(pattern, case=False, na=False))

        if mask.any():
            log.info(f"Step 5_c: Mapping SOMEIP_FF SysVar signals for {mask.sum()} matching rows.")
            resolved_subset = self.someip_ff_mapper.resolve(df.loc[mask].copy())
            
            # SAFE INJECTION (Bypassing df.update warning)
            for col in resolved_subset.columns:
                if col not in df.columns:
                    df[col] = pd.NA
                df[col] = df[col].astype(object)
                df.loc[mask, col] = resolved_subset[col]

        return df
    
    # --- STEP 5_d: AACP SysVar Resolution ---
    def resolve_aacp_signals_from_db(self, df: pd.DataFrame, test_type: str) -> pd.DataFrame:
        pattern = "AACP"

        mask = (df["SOMEIP_TOPIC"].fillna("") != "") & \
               (df["SOMEIP_TOPIC_ATTRIBUTE"].fillna("") != "") & \
               (df["TEST_TYPE"].str.contains(pattern, case=False, na=False))

        if mask.any():
            log.info(f"Step 5_d: Mapping AACP SysVar signals for {mask.sum()} matching rows.")
            
            # 1. Pass the subset without .copy() or fragmentation to preserve index alignment
            resolved_subset = self.aacp_mapper.resolve(df.loc[mask])
            
            # 2. FIX: Explicitly map every column back using the mask context
            for col in resolved_subset.columns:
                df.loc[mask, col] = resolved_subset[col]

        return df
    
    # --- STEP 6: ENUM mapping (Processes rows where IS_ENUM is True) ---
    def resolve_enum_mappings(self, df: pd.DataFrame, test_type: str) -> pd.DataFrame:
        if "IS_ENUM" not in df.columns or not df["IS_ENUM"].any():
            log.info("Step 6: No Enum signals flagged. Skipping.")
            return df

        log.info("Step 6: Executing optimized vectorized Enum mapping.")
        
        # Create a mask for rows that need processing
        enum_mask = df["IS_ENUM"] == True
        
        # Group by TEST_TYPE to process batches of similar rows at once
        # This is significantly faster than row-by-row iteration
        for row_tt_raw, group_df in df[enum_mask].groupby("TEST_TYPE"):
            row_tt = str(row_tt_raw).upper()
            temp_df = group_df.copy()

            # --- BRANCH 1: SWC tests ---
            if "SWC" in row_tt:
                if "CAN" in row_tt:
                    temp_df = self.enum_mapper.resolve_single_enum(temp_df, "CAN_ENUM")
                
                if "SOMEIP_FF" in row_tt:
                    temp_df = self.enum_mapper.resolve_single_enum(temp_df, "SOMEIP_FF_ENUM")
                elif "SOMEIP" in row_tt or "CAROS" in row_tt:
                    temp_df = self.enum_mapper.resolve_single_enum(temp_df, "SOMEIP_ENUM")
                
                if "AACP" in row_tt:
                    temp_df = self.enum_mapper.resolve_single_enum(temp_df, "AACP_ENUM")

            # --- BRANCH 2: Mapping tests ---
            elif "CAN" in row_tt:
                if "CAN->CAN" in row_tt or "CAN-CAN" in row_tt:
                    temp_df = self.enum_mapper.resolve_enum_mapping(temp_df, "CAN_ENUM", "CAN2_ENUM")
                elif "SOMEIP_FF" in row_tt:
                    temp_df = self.enum_mapper.resolve_enum_mapping(temp_df, "CAN_ENUM", "SOMEIP_FF_ENUM")
                elif "AACP" in row_tt:
                    temp_df = self.enum_mapper.resolve_enum_mapping(temp_df, "CAN_ENUM", "AACP_ENUM")
                elif "CAROS" in row_tt:
                    temp_df = self.enum_mapper.resolve_enum_mapping(temp_df, "CAN_ENUM", "SOMEIP_ENUM")
                elif "SOMEIP" in row_tt:
                    temp_df = self.enum_mapper.resolve_enum_mapping(temp_df, "CAN_ENUM", "SOMEIP_ENUM")

            # Update the main dataframe with the batch-resolved results
            df.update(temp_df)

        return df

    # --- STEP 7: NON-ENUM mapping ---
    def resolve_phys_ranges(self, df: pd.DataFrame, test_type: str) -> pd.DataFrame:
        phys_mask = df["IS_ENUM"] == False
        if not phys_mask.any():
            return df
        
        log.info("Step 7: Computing physical ranges for non-enum signals.")

        def process_row(row):
            row_tt = str(row.get("TEST_TYPE", "")).upper()
            is_can_can = "CAN->CAN" in row_tt or "CAN-CAN" in row_tt

            # Clean local helper function to eliminate repetitive CAN/CAN2 math blocks
            def calculate_can_bounds(prefix: str) -> dict:
                min_raw = row.get(f'{prefix}_MIN_RAW')
                if pd.notna(min_raw) and str(min_raw).upper() != 'N/A':
                    try:
                        res = float(row.get(f'{prefix}_RESOLUTION', 1))
                        off = float(row.get(f'{prefix}_OFFSET', 0))
                        c_min = (float(min_raw) * res) + off
                        c_max = (float(row.get(f'{prefix}_MAX_RAW', 0)) * res) + off
                        return self._compute_bounds(c_min, c_max)
                    except (ValueError, TypeError):
                        pass
                return {k: "N/A" for k in ['MIN', 'MID', 'MAX']}

            # 1. Dynamically call our helper for both variants
            can_b = calculate_can_bounds("CAN")
            can2_b = calculate_can_bounds("CAN2")

            # 2. Compute SOMEIP Bounds from DB
            sip_b = self._compute_bounds(row.get('SOMEIP_MIN_PHY'), row.get('SOMEIP_MAX_PHY'))

            # 3. Protocol Priority Logic
            is_gateway = "CAN" in row_tt and "SOMEIP" in row_tt
            eth_source = can_b if is_gateway else sip_b

            # 4. Fill Output Dictionary selectively
            out = {}
            for sfx in ['MIN', 'MID', 'MAX']:
                out[f'COMPUTED_CAN_VALUE_{sfx}'] = can_b[sfx]
                
                # Exclusion: Only fill SOMEIP computed metrics if it is NOT a CAN->CAN test pattern
                if not is_can_can:
                    out[f'COMPUTED_SOMEIP_VALUE_{sfx}'] = eth_source[sfx]

                if is_can_can:
                    out[f'COMPUTED_CAN2_VALUE_{sfx}'] = can2_b[sfx]

                if "SOMEIP_FF" in row_tt:
                    out[f'COMPUTED_SOMEIP_FF_VALUE_{sfx}'] = eth_source[sfx]

                if "AACP" in row_tt:
                    out[f'COMPUTED_AACP_VALUE_{sfx}'] = eth_source[sfx]

            return pd.Series(out)

        resolved_subset = df.loc[phys_mask].apply(process_row, axis=1)
        df.update(resolved_subset)

        return df
