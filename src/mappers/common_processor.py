import math
import pandas as pd
from core.logger import log
from mappers.base_mapper import BaseMapper
from mappers.can_mapper import CANMapper
from mappers.someip_mapper import SomeIPMapper
from .basic_function_resolver import BasicFunctionResolver
from .enum_resolver import EnumResolver

class CommonProcessor:
    def __init__(self, can_db_data: dict, eth_db_data: dict):
        """
        Initializes the processor with specialized mappers and resolvers.
        The mappers are responsible for flagging IS_ENUM during database resolution.
        """
        self.can_mapper = CANMapper(can_db_data)
        self.eth_mapper = SomeIPMapper(eth_db_data)
        self.basic_function_mapper = BasicFunctionResolver()
        self.enum_mapper = EnumResolver()

    @staticmethod
    def _compute_bounds(mi, ma):
        """Modular Math Engine: Logic for physical boundary calculation."""
        try:
            mi_f, ma_f = float(mi), float(ma)
            return {
                'MIN': int(math.ceil(mi_f)),
                'MID': int(math.ceil((mi_f + ma_f) / 2.0)),
                'MAX': int(math.floor(ma_f))
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
                core_order = ["E2E_ETH_REQ_ID", "SWC", "SOMEIP_PORT", "ATTRIBUTE_VALUE", "CAN_PORT", "PATH_SYNTHESIS", "SOMEIP_TOPIC", "SOMEIP_TOPIC_ATTRIBUTE", "TEST_TYPE"]
            else:
                core_order = ["E2E_CAN_REQ_ID", "SWC", "CAN_PORT", "PATH_SYNTHESIS", "SOMEIP_PORT", "ATTRIBUTE_VALUE", "SOMEIP_TOPIC", "SOMEIP_TOPIC_ATTRIBUTE", "TEST_TYPE"]

            mapping = {
                "E2E_ETH_REQ_ID": ["E2E_ETH_REQ_ID", "REQ ID", "REQ_ID", "REQUIREMENT ID"],
                "E2E_CAN_REQ_ID": ["E2E_CAN_REQ_ID", "REQ ID", "REQ_ID", "REQUIREMENT ID"],
                "SOMEIP_PORT": ["SOMEIP_PORT", "PORT", "SOMEIP_PORT_MAPPING", "PORT NAME"],
                "ATTRIBUTE_VALUE": ["ATTRIBUTE_VALUE", "ATTRIBUTE VALUE", "SOMEIP_ATTRIBUTE_VALUE_MAPPING"],
                "CAN_PORT": ["CAN_PORT", "CAN_PORT_MAPPING", "PORT NAME"],
                "PATH_SYNTHESIS": ["PATH_SYNTHESIS", "CAN_PATH_SYNTHESIS_MAPPING", "PATH SYNTHESIS"],
                "SOMEIP_TOPIC": ["SOMEIP_TOPIC", "TOPIC", "TOPIC NAME"],
                "SOMEIP_TOPIC_ATTRIBUTE": ["SOMEIP_TOPIC_ATTRIBUTE", "ATTRIBUTE", "TOPIC ATTRIBUTE"]
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
            "CAN_CLUSTER", "BASIC_FUNCTION_NAME", "IS_ENUM", "ENUM_LEXICAL_MATCH", 
            "CAN_DB_SIGNAL_NAME", "CAN_PERIODICITY", "CAN_ENUM", "CAN_MIN_RAW", 
            "CAN_MAX_RAW", "CAN_OFFSET", "CAN_RESOLUTION", "SOMEIP_DB_SIGNAL_NAME", 
            "SOMEIP_ENUM", "SOMEIP_MIN_PHY", "SOMEIP_MAX_PHY", "SOMEIP_OFFSET", 
            "SOMEIP_RESOLUTION", "SOMEIP_DB_SIGNAL_VALUESTATE", "COMPUTED_CAN_VALUE_MIN",
            "COMPUTED_CAN_VALUE_MID", "COMPUTED_CAN_VALUE_MAX", "COMPUTED_SOMEIP_VALUE_MIN",
            "COMPUTED_SOMEIP_VALUE_MID", "COMPUTED_SOMEIP_VALUE_MAX"
        ]
        
        master_order = list(df.columns) + additional_cols
        seen = set()
        final_cols = [x for x in master_order if not (x in seen or seen.add(x))]

        for col in final_cols:
            if col not in df.columns:
                df[col] = False if col == "IS_ENUM" else ""

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
        return df

    # --- STEP 4: Compute Basic Function Name ---
    def derive_basic_function_names(self, df: pd.DataFrame) -> pd.DataFrame:
        log.info("Step 4: Resolving standardized Basic Function Names")
        return self.basic_function_mapper.resolve_all_basic_functions(df)

    # --- STEP 5_a: CAN Signal Resolution ---
    def resolve_can_signals_from_db(self, df: pd.DataFrame, test_type: str) -> pd.DataFrame:
        log.info(f"Step 5_a: Mapping CAN signals for Test Type: {test_type}")
        # Use the passed test_type for the mask
        mask = (df["CAN_PORT"] != "") & (pd.Series(test_type).str.contains("CAN").iloc[0])
        if mask.any():
            df.loc[mask] = self.can_mapper.resolve(df.loc[mask])
        return df

    # --- STEP 5_b: SOME/IP Signal Resolution ---
    def resolve_someip_signals_from_db(self, df: pd.DataFrame, test_type: str) -> pd.DataFrame:
        log.info(f"Step 5_b: Mapping SOME/IP signals for Test Type: {test_type}")
        # Use the passed test_type for the mask
        mask = (df["SOMEIP_PORT"] != "") & (any(x in test_type for x in ["SOMEIP", "CAROS", "AACP"]))
        if mask.any():
            df.loc[mask] = self.eth_mapper.resolve(df.loc[mask])
        return df

    # --- STEP 6: ENUM mapping (Processes rows where IS_ENUM is True) ---
    def resolve_enum_mappings(self, df: pd.DataFrame, test_type: str) -> pd.DataFrame:
        """
        Orchestrates enum resolution based on test_type.
        Only executes if IS_ENUM contains True values.
        """
        # Step 6: Safety Check - Exit early if no enum rows exist
        if "IS_ENUM" not in df.columns or not df["IS_ENUM"].any():
            log.info("Step 6: No Enum signals flagged. Skipping.")
            return df

        log.info(f"Step 6: Executing Enum mapping for Test Type: {test_type}")
        t = test_type.upper()

        # --- BRANCH 1: SWC tests (Single Signal Boundary) ---
        if "SWC" in t:
            if "CAN" in t:
                df = self.enum_mapper.resolve_single_enum(df, "CAN_ENUM")
            # elif "AACP" in t: 
            #     df = self.enum_mapper.resolve_single_enum(df, "AACP_ENUM")
            # elif "SOMEIP_FF" in t:
            #     df = self.enum_mapper.resolve_single_enum(df, "SOMEIP_FF_ENUM")
            elif "SOMEIP" in t or "CAROS" in t:
                df = self.enum_mapper.resolve_single_enum(df, "SOMEIP_ENUM")

        # --- BRANCH 2: Mapping tests (Dual Signal Comparison) ---
        else:
            if "CAN" in t:
                # if "AACP" in t:
                #     df = self.enum_mapper.resolve_enum_mapping(df, "CAN_ENUM", "AACP_ENUM")
                # elif "SOMEIP_FF" in t:
                #     df = self.enum_mapper.resolve_enum_mapping(df, "CAN_ENUM", "SOMEIP_FF_ENUM")
                if "SOMEIP" in t:
                    df = self.enum_mapper.resolve_enum_mapping(df, "CAN_ENUM", "SOMEIP_ENUM")

        return df

    # --- STEP 7: NON-ENUM mapping (Generalize deriving physical values for min, mid and max) ---
    def resolve_phys_ranges(self, df: pd.DataFrame, test_type: str) -> pd.DataFrame:
        log.info(f"Step 7: Computing physical range boundaries for test type: {test_type}")
        phys_mask = df["IS_ENUM"] == False
        if not phys_mask.any():
            log.info("Step 7: All signals are Enums. Skipping physical range calculation.")
            return df

        log.info(f"Step 7: Processing {phys_mask.sum()} continuous/linear signals.")

        tt_u = str(test_type).upper()
        # Mirroring Logic: Apply CAN bounds to Ethernet if Ethernet DB info is missing
        auto_mirror = "CAN" in tt_u and any(x in tt_u for x in ["SOMEIP", "AACP", "SOMEIP_FF"])
        if auto_mirror:
            log.info("Step 7: Hybrid test detected. Cross-protocol mirroring enabled (CAN -> ETH).")

        def process_row(row):
            # Resolve CAN Bounds
            try:
                c_mi = (float(row.get('CAN_MIN_RAW', 0)) * float(row.get('CAN_RESOLUTION', 1))) + float(row.get('CAN_OFFSET', 0))
                c_ma = (float(row.get('CAN_MAX_RAW', 0)) * float(row.get('CAN_RESOLUTION', 1))) + float(row.get('CAN_OFFSET', 0))
                can_bounds = self._compute_bounds(c_mi, c_ma)
            except (ValueError, TypeError):
                can_bounds = {k: "N/A" for k in ['MIN', 'MID', 'MAX']}

            # Resolve SOMEIP Bounds
            sip_bounds = self._compute_bounds(row.get('SOMEIP_MIN_PHY'), row.get('SOMEIP_MAX_PHY'))

            res = {}
            for suffix in ['MIN', 'MID', 'MAX']:
                c_val = can_bounds[suffix]
                s_val = sip_bounds[suffix]

                final_eth_val = s_val
                if final_eth_val == "N/A" and auto_mirror:
                    final_eth_val = c_val

                res[f'COMPUTED_CAN_VALUE_{suffix}'] = c_val
                res[f'COMPUTED_SOMEIP_VALUE_{suffix}'] = final_eth_val
                
                # placeholders for other protocols
                # res[f'COMPUTED_AACP_VALUE_{suffix}'] = final_eth_val
                # res[f'COMPUTED_SOMEIP_FF_VALUE_{suffix}'] = final_eth_val
                
            return res

        computed_df = df.loc[phys_mask].apply(process_row, axis=1, result_type='expand')
        df.update(computed_df)
        return df