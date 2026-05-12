import json
import os
import re

import pandas as pd

from core.logger import log


class BaseMapper:
    """Base class providing shared utilities for protocol mappers."""

    def __init__(self, db_source):
        # Save the raw input (can be a string path OR a dictionary)
        self._raw_source = db_source

        # Keep cache_path for legacy disk compatibility. If it's a dict, this becomes None.
        self.cache_path = db_source if isinstance(db_source, str) else None

        # Trigger the load (which now handles both RAM and Disk)
        self.db = self._load_database()

    def _load_database(self) -> dict:
        """Loads data from disk, or returns the RAM dictionary directly."""

        # 1. IN-MEMORY PIPELINE: If we were passed a dictionary, return it instantly!
        if isinstance(self._raw_source, dict):
            return self._raw_source

        # 2. LEGACY DISK PIPELINE: If it's a file path, load it from the JSON.
        if not self.cache_path or not os.path.exists(self.cache_path):
            log.warning(f"Database cache not found at: {self.cache_path}")
            return {}

        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Failed to load Database Cache '{self.cache_path}': {e}")
            return {}

    @staticmethod
    def resolve_column_name(available_columns, possible_names):
        """Helper function to find a column name ignoring case and whitespace."""
        avail_upper = [str(c).strip().upper() for c in available_columns]
        for name in possible_names:
            name_upper = str(name).strip().upper()
            if name_upper in avail_upper:
                idx = avail_upper.index(name_upper)
                return available_columns[idx]
        return None

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
