import json
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict

import pandas as pd

from core.logger import log


class BaseParser(ABC):
    """Abstract Base Class defining the contract and Data API for all parsers."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._parsed_data: Dict[str, Any] = {}
        self._start_time = time.time()

    @abstractmethod
    def parse(self) -> Dict[str, Any]:
        """Parses the input file and returns a standardized dictionary."""
        pass

    def _get_processing_time(self) -> str:
        """Calculates elapsed time in HH:MM:SS format."""
        elapsed = time.time() - self._start_time
        return time.strftime("%H:%M:%S", time.gmtime(elapsed))

    def to_json_file(self, output_path: str, indent: int = 4, write_allowed: bool = False):
        """GATED BY PIPELINE: Will only execute if write_allowed is True (Dev Mode)."""
        if not write_allowed:
            log.debug(f"🛡️ PROD MODE: In-memory cache secured. Disk dump to {output_path} blocked.")
            return

        data = self.to_json_dict()
        total = len(data)
        resolved = sum(1 for v in data.values() if isinstance(v, dict) and len(v.get('signal_paths', [])) > 0)
        no_path = total - resolved

        # Safely grab the exact file size of the ARXML
        try:
            file_size_bytes = os.path.getsize(self.file_path)
        except OSError:
            file_size_bytes = 0

        # We now stamp the cache with both the NAME and SIZE of the source ARXML
        output_data = {
            "Summary": {
                "Source_File_Name": os.path.basename(self.file_path),
                "Source_File_Size_Bytes": file_size_bytes,
                "Total_Signals_Found": total,
                "Resolved_With_Paths": resolved,
                "No_Path_Found": no_path,
                "Processing_Time_HH_MM_SS": self._get_processing_time()
            },
            "SIGNAL_LIST": data
        }

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=indent, ensure_ascii=False)
            log.info(f"✅ DEV MODE: Database cached with summary to: {output_path}")
        except Exception as e:
            log.error(f"❌ Failed to write JSON: {e}")

    def load_from_json(self, input_path: str) -> bool:
        """Hydrates the parser while stripping the Summary/Wrapper layers."""
        if not os.path.exists(input_path):
            return False
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                raw_cache = json.load(f)

            # Legacy Stripping: Look for the signal dictionary inside the wrapper
            if "SIGNAL_LIST" in raw_cache:
                self._parsed_data = raw_cache["SIGNAL_LIST"]
            elif "SOMEIP_SIGNAL" in raw_cache:
                self._parsed_data = raw_cache["SOMEIP_SIGNAL"]
            else:
                # Fallback: just remove Summary
                self._parsed_data = {k: v for k, v in raw_cache.items() if k != "Summary"}

            log.info(f"🚀 Loaded {len(self._parsed_data)} signals from cache.")
            return True
        except Exception as e:
            log.error(f"❌ Cache load failed: {e}")
            return False

    def to_dataframe(self) -> pd.DataFrame:
        """Universal conversion with nested CAN path flattening."""
        data = self.to_json_dict()
        if not data:
            return pd.DataFrame()

        df_rows = []
        sample_val = next(iter(data.values()))

        # Check if we are dealing with the nested CAN structure
        if isinstance(sample_val, dict) and 'signal_paths' in sample_val:
            for sig_name, content in data.items():
                attrs = content.get('Attributes', {})
                paths = content.get('signal_paths', [])

                # Base attributes common to all paths of this signal
                # We pull everything from attrs (Resolution, Offset, etc.)
                base_info = {"Signal_Name": sig_name, **attrs}

                if not paths:
                    df_rows.append({**base_info, "Status": "No Path"})
                else:
                    for path in paths:
                        # Explode path-specific info (Cluster, TX, RX)
                        # and format RX nodes as a string for Excel
                        row = {**base_info, "Status": "Resolved", **path}
                        if isinstance(row.get('rx'), list):
                            row['rx'] = ", ".join(row['rx'])
                        df_rows.append(row)
        else:
            # Flat SOME/IP structure
            df_rows = [{"Signal_String": k, **v} for k, v in data.items()]

        df = pd.DataFrame(df_rows)

        # Dynamic safe sorting
        sort_prio = ['SIF', 'Cluster', 'can_cluster', 'Port', 'tx', 'Method', 'Signal_Name']
        avail = [c for c in sort_prio if c in df.columns]
        return df.sort_values(by=avail).reset_index(drop=True) if avail else df

    def to_json_dict(self) -> Dict[str, Any]:
        """In-memory dictionary access. Ensures data exists before returning."""
        if not self._parsed_data:
            self.parse()
        return self._parsed_data
