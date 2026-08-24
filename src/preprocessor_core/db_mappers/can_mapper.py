import pandas as pd

from preprocessor_core.db_mappers.base_mapper import BaseMapper


class CANMapper(BaseMapper):
    def _load_database(self) -> dict:
        raw_db = super()._load_database()
        return {str(k).lower(): v for k, v in raw_db.items()}

    def get_signal_data(self, port_name: str, cluster: str) -> dict:
        cols = ["CAN_DB_SIGNAL_NAME", "CAN_ENUM", "CAN_MIN_RAW", "CAN_MAX_RAW",
                "CAN_PERIODICITY", "CAN_OFFSET", "CAN_RESOLUTION"]

        if pd.isna(port_name) or str(port_name).strip() == "":
            return {col: None for col in cols}

        search_key = ("i" + str(port_name).strip()).lower()
        if search_key not in self.db:
            return {col: "CAN_NOT_FOUND" for col in cols}

        sig_data = self.db[search_key]
        attr = sig_data.get("Attributes", {})
        paths = sig_data.get("signal_paths", [])

        fallback_order = filter(None, [cluster, "CAN_FD_CHASSIS", "CAN_FD_PT", "CAN_ITS3_FD",
                                       "CAN_ITS5_FD", "PCU4_CAN", "CAN_EXT", "CAN_FD_ACCESS2"])

        db_signal_name = None
        for c in fallback_order:
            match = next((p for p in paths if str(p.get("can_cluster")).upper() == str(c).upper()), None)
            if match:
                db_signal_name = match.get("signal_name")
                break

        if not db_signal_name and paths:
            db_signal_name = paths[0].get("signal_name")

        raw_enums = attr.get("Enums", {})

        return {
            "CAN_DB_SIGNAL_NAME": db_signal_name or "CAN_CLUSTER_NOT_FOUND",
            "CAN_ENUM": self.format_enum_to_string(raw_enums),
            "CAN_MIN_RAW": attr.get("Raw_Limits", {}).get("Min"),
            "CAN_MAX_RAW": attr.get("Raw_Limits", {}).get("Max"),
            "CAN_PERIODICITY": attr.get("periodicity_ms"),
            "CAN_OFFSET": attr.get("Offset"),
            "CAN_RESOLUTION": attr.get("Resolution"),
            "_HAS_ENUM": bool(raw_enums)
        }

    def resolve(self, df_subset: pd.DataFrame) -> pd.DataFrame:
        base_cols = ["CAN_DB_SIGNAL_NAME", "CAN_ENUM", "CAN_MIN_RAW", "CAN_MAX_RAW",
                     "CAN_PERIODICITY", "CAN_OFFSET", "CAN_RESOLUTION"]

        can2_cols = ["CAN2_DB_SIGNAL_NAME", "CAN2_PERIODICITY", "CAN2_ENUM",
                     "CAN2_MIN_RAW", "CAN2_MAX_RAW", "CAN2_OFFSET", "CAN2_RESOLUTION"]

        # Fix: Create explicit new empty series keys to break the slice view warnings cleanly
        for col in can2_cols:
            if col not in df_subset.columns:
                df_subset = df_subset.assign(**{col: None})

        # 1. Batch execute primary CAN signal lookups
        can1_results = pd.DataFrame(
            [self.get_signal_data(p, c) for p, c in zip(df_subset["CAN_PORT"], df_subset["CAN_CLUSTER"], strict=False)],
            index=df_subset.index
        )

        for col in base_cols:
            df_subset.loc[:, col] = can1_results[col]

        # 2. Batch execute secondary CAN2 signal lookups (Only for CAN->CAN rows)
        is_can_to_can = df_subset["TEST_TYPE"].astype(str).str.strip().str.upper() == "CAN->CAN"
        db2_has_enum = pd.Series(False, index=df_subset.index)

        if is_can_to_can.any():
            can2_subset = df_subset[is_can_to_can]
            can2_results = pd.DataFrame(
                [self.get_signal_data(p, c) for p, c in zip(can2_subset["CAN_TO_CAN_MAPPING"], can2_subset["CAN2_CLUSTER"], strict=False)],
                index=can2_subset.index
            )

            for col in can2_cols:
                source_col = col.replace("CAN2_", "CAN_")
                df_subset.loc[is_can_to_can, col] = can2_results[source_col]

            db2_has_enum.loc[is_can_to_can] = can2_results["_HAS_ENUM"].astype(bool)

        # 3. Holistic vectorized update for the generic IS_ENUM tracking flag
        db1_has_enum = can1_results["_HAS_ENUM"].astype(bool)
        existing_is_enum = df_subset["IS_ENUM"].astype(str).str.upper() == "TRUE"

        df_subset.loc[:, "IS_ENUM"] = db1_has_enum | db2_has_enum | existing_is_enum

        return df_subset
