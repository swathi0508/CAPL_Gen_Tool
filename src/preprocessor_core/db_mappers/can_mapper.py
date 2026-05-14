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
        """Mapper handles data lookup and column formatting."""
        cols = ["CAN_DB_SIGNAL_NAME", "CAN_ENUM", "CAN_MIN_RAW", "CAN_MAX_RAW",
                "CAN_PERIODICITY", "CAN_OFFSET", "CAN_RESOLUTION", "IS_ENUM"]

        def process_row(r):
            data = self.get_signal_data(r.get("CAN_PORT"), r.get("CAN_CLUSTER"))
            
            db_has_enum = data.pop("_HAS_ENUM", False)
            existing_is_enum = str(r.get("IS_ENUM", "FALSE")).upper() == "TRUE"
            
            data["IS_ENUM"] = True if (db_has_enum or existing_is_enum) else False
            return pd.Series(data)

        res = df_subset.apply(process_row, axis=1)
        df_subset.loc[:, cols] = res[cols].values
        return df_subset
