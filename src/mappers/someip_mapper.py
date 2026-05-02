import pandas as pd
from .base_mapper import BaseMapper

class SomeIPMapper(BaseMapper):
    def _load_database(self) -> dict:
        raw_db = super()._load_database()
        clean_db = {}
        for _, data in raw_db.items():
            meth = str(data.get('Method', data.get('Attribute_Value', ''))).strip().lower()
            if meth:
                clean_db[meth] = data
        return clean_db

    def get_signal_data(self, attr_value: str) -> dict:
        cols = ["SOMEIP_DB_SIGNAL_NAME", "SOMEIP_ENUM", "SOMEIP_MIN_PHY", 
                "SOMEIP_MAX_PHY", "SOMEIP_OFFSET", "SOMEIP_RESOLUTION"]
        
        if pd.isna(attr_value) or str(attr_value).strip() == "":
            return {col: None for col in cols}

        search_key = str(attr_value).strip().lower()
        if search_key not in self.db:
            return {col: "ETH_NOT_FOUND" for col in cols}

        sig_data = self.db[search_key]

        return {
            "SOMEIP_DB_SIGNAL_NAME": sig_data.get("Signal_String", search_key),
            "SOMEIP_ENUM": self.format_enum_to_string(sig_data.get("Enums", {})),
            "SOMEIP_MIN_PHY": sig_data.get("Min"),
            "SOMEIP_MAX_PHY": sig_data.get("Max"),
            "SOMEIP_OFFSET": sig_data.get("Offset"),
            "SOMEIP_RESOLUTION": sig_data.get("Resolution")
        }