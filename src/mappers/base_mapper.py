import os
import json
import re
import pandas as pd
from core.logger import log

class BaseMapper:
    """Base class providing shared utilities for protocol mappers."""
    
    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        self.db = self._load_database()

    def _load_database(self) -> dict:
        """Loads the JSON cache. Overridden by child classes for key formatting."""
        if not self.cache_path or not os.path.exists(self.cache_path):
            log.warning(f"Database cache not found: {self.cache_path}")
            return {}
        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("SIGNAL_LIST", data.get("ICAN_SIGNAL", data))
        except Exception as e:
            log.error(f"Failed to load database {self.cache_path}: {e}")
            return {}

    @staticmethod
    def normalize_attr(val) -> str:
        if pd.isna(val):
            return None
        val_str = str(val).strip()
        if val_str.lower() == "valuestate":
            return None
        clean_val = re.sub(r'(valuestate|value state)$', '', val_str, flags=re.IGNORECASE).strip()
        if not clean_val or clean_val.lower() in ["nan", "unknown"]:
            return None
        return clean_val

    @staticmethod
    def resolve_column_name(columns, candidates):
        for candidate in candidates:
            if candidate in columns:
                return candidate
        return None

    @staticmethod
    def extract_cluster(path_val) -> str:
        if pd.isna(path_val) or str(path_val).strip() == "":
            return ""
        clusters = ["CAN_FD_CHASSIS", "CAN_FD_PT", "CAN_ITS3_FD", "CAN_ITS5_FD", 
                    "PCU4_CAN", "CAN_EXT", "CAN_FD_ACCESS2"]
        tokens = re.split(r'\s*=>\s*|\s*::\s*', str(path_val))
        for token in tokens:
            token_upper = str(token).upper()
            for c in clusters:
                if c in token_upper:
                    return c
        path_upper = str(path_val).upper()
        if any(trig.upper() in path_upper for trig in ["PIU_Mst", "PIU_Sub", "PIU_Hood"]):
            return "EthernetCluster"
        return "UNKNOWN_CLUSTER"

    @staticmethod
    def format_enum_to_string(enums) -> str:
        if not enums: return ""
        if isinstance(enums, dict): return str(enums) # Preserves dict string format
        return str(enums)