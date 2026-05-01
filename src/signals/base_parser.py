import os
import json
import pandas as pd
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from core.logger import log

class BaseParser(ABC):
    """Abstract Base Class defining the contract and Data API for all parsers."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._parsed_data: Dict[str, Any] = {}

    @abstractmethod
    def parse(self) -> Dict[str, Any]:
        """Parses the input file and returns a standardized dictionary."""
        pass

    def to_json_file(self, output_path: str, indent: int = 4):
        """Dumps the parsed data to a physical JSON file for caching/debugging."""
        data = self.to_json_dict()
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            log.info(f"✅ Database successfully cached to: {output_path}")
        except Exception as e:
            log.error(f"❌ Failed to write JSON file: {e}")

    def load_from_json(self, input_path: str) -> bool:
        """Hydrates the parser from a JSON cache, bypassing the ARXML parse tax."""
        if not os.path.exists(input_path):
            log.warning(f"Cache file not found: {input_path}")
            return False
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                self._parsed_data = json.load(f)
            log.info(f"🚀 Parser hydrated from cache: {input_path} ({len(self._parsed_data)} signals)")
            return True
        except Exception as e:
            log.error(f"❌ Failed to load JSON cache: {e}")
            return False

    def to_dataframe(self) -> pd.DataFrame:
        """
        Universal DataFrame converter with edge-case handling for 
        nested CAN paths and protocol-specific columns.
        """
        # Edge Case 1: Check if data is already loaded (from JSON or Parse)
        # We only call self.parse() if the dictionary is truly empty.
        if not self._parsed_data:
            self.parse()
        
        if not self._parsed_data:
            log.warning("No data available to convert to DataFrame.")
            return pd.DataFrame()

        df_rows = []
        
        # Get a sample to detect the structure
        sample_key = next(iter(self._parsed_data))
        sample_val = self._parsed_data[sample_key]

        # Edge Case 2: Handle Nested CAN Structures vs Flat SOME/IP
        # We look for the 'signal_paths' key which is unique to your CAN parser
        is_can_structure = isinstance(sample_val, dict) and 'signal_paths' in sample_val

        if is_can_structure:
            for sig_name, content in self._parsed_data.items():
                attrs = content.get('Attributes', {})
                paths = content.get('signal_paths', [])
                
                if not paths:
                    # Handle signals found in ARXML but missing from topology
                    row = {"Signal_Name": sig_name, "Status": "No Path", **attrs}
                    df_rows.append(row)
                else:
                    for path in paths:
                        row = {"Signal_Name": sig_name, "Status": "Resolved", **attrs, **path}
                        df_rows.append(row)
        else:
            # Handle standard flat SOME/IP mapping
            for sig_str, props in self._parsed_data.items():
                row = {"Signal_String": sig_str, **props}
                df_rows.append(row)

        df = pd.DataFrame(df_rows)

        # Edge Case 3: Dynamic "Safe Sorting"
        # We define a priority list. It sorts by what it finds, and ignores the rest.
        priority_cols = ['SIF', 'Cluster', 'Port', 'TX_Node', 'Method', 'Signal_Name']
        available_sort_cols = [c for c in priority_cols if c in df.columns]
        
        if available_sort_cols:
            try:
                df = df.sort_values(by=available_sort_cols).reset_index(drop=True)
            except Exception as e:
                log.debug(f"Sorting skipped: {e}")
            
        return df

    def to_json_dict(self) -> Dict[str, Any]:
        """In-memory dictionary access. Ensures data exists before returning."""
        if not self._parsed_data:
            self.parse()
        return self._parsed_data