import re
import pandas as pd
from typing import Any, Dict
from lxml import etree

from base_parser import BaseParser
from core.logger import log


class SomeIPEventParser(BaseParser):
    """Parses SOME/IP ARXML files to extract signals and Enums, supporting both Dict and DataFrame outputs."""

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self._parsed_data: Dict[str, Any] = {}
    
    def parse(self) -> Dict[str, Any]:
        """Parses the ARXML and returns a standard dictionary (satisfies BaseParser contract)."""
        log.info(f"Parsing ETH ARXML: {self.file_path}")
        
        try:
            tree = etree.parse(self.file_path)
            root = tree.getroot()
        except Exception as e:
            log.error(f"Failed to parse ARXML file {self.file_path}: {e}")
            return {}

        compu_methods = self._extract_compu_methods(root)
        app_to_compu = self._extract_app_to_compu(root)

        def get_enum_string(app_type_name: str) -> str:
            compu_name = app_to_compu.get(app_type_name)
            enum_dict = compu_methods.get(compu_name, {})
            if not enum_dict:
                return "No Enums"
            return " | ".join([f"{k}: {v}" for k, v in enum_dict.items()])

        self._parsed_data = {}

        for dtms in root.xpath("//*[local-name()='DATA-TYPE-MAPPING-SET']"):
            short_name_elem = dtms.xpath("*[local-name()='SHORT-NAME']")
            if not short_name_elem:
                continue
                
            short_name = short_name_elem[0].text.strip()
            match = re.search(r'^X(\d+)_(.*?)SvcProv', short_name)
            if not match:
                continue
                
            sif = match.group(1)
            raw_event_name = match.group(2)
            someip_event = f"SomeIp{raw_event_name}"
            
            valid_methods = []
            valuestate_app_name = None
            
            for dt_map in dtms.xpath(".//*[local-name()='DATA-TYPE-MAP']"):
                app_ref = dt_map.xpath("*[local-name()='APPLICATION-DATA-TYPE-REF']")
                
                if app_ref and app_ref[0].text:
                    app_path_raw = app_ref[0].text.split("/")[-1].strip()
                    
                    if re.match(r'^ValueState\d*$', app_path_raw, re.IGNORECASE):
                        valuestate_app_name = app_path_raw
                        continue 
                        
                    clean_method = app_path_raw[:-1] if app_path_raw.endswith("T") else app_path_raw
                    valid_methods.append((clean_method, app_path_raw))
            
            for clean_method, raw_app_name in valid_methods:
                
                # 1. Base Signal
                base_enums = get_enum_string(raw_app_name)
                base_sig_str = f'"EthernetCluster::sif_{sif}::{someip_event}::{clean_method}"'
                
                self._parsed_data[base_sig_str] = {
                    "Cluster": "EthernetCluster",
                    "SIF": sif,
                    "Event": someip_event,
                    "Method": clean_method,
                    "Available_States": base_enums
                }
                
                # 2. Expanded ValueState Signal
                if valuestate_app_name:
                    vs_event = someip_event[:-1] if someip_event.endswith('s') else someip_event
                    vs_method = f"{clean_method}ValueState"
                    vs_enums = get_enum_string(valuestate_app_name)
                    vs_sig_str = f'"EthernetCluster::sif_{sif}::{vs_event}::{vs_method}"'
                    
                    self._parsed_data[vs_sig_str] = {
                        "Cluster": "EthernetCluster",
                        "SIF": sif,
                        "Event": vs_event,
                        "Method": vs_method,
                        "Available_States": vs_enums
                    }

        log.info(f"Successfully extracted {len(self._parsed_data)} signals.")
        return self._parsed_data

    def to_dataframe(self) -> pd.DataFrame:
        """Converts the parsed dictionary into a structured Pandas DataFrame."""
        # Ensure data is parsed before attempting to convert
        if not self._parsed_data:
            self.parse()
            
        # If still empty (e.g., parsing failed), return empty DataFrame
        if not self._parsed_data:
            return pd.DataFrame()

        # Build list of rows for the DataFrame, injecting the dictionary Key as a column
        df_rows = []
        for signal_string, properties in self._parsed_data.items():
            row = {"Signal_String": signal_string}
            row.update(properties) # Merges Cluster, SIF, Event, Method, Available_States
            df_rows.append(row)
            
        df = pd.DataFrame(df_rows)
        
        # Sort values logically for readability/Jinja output
        df = df.sort_values(by=['SIF', 'Event', 'Method']).reset_index(drop=True)
        return df

    # --- Private Helper Methods ---

    def _extract_compu_methods(self, root) -> Dict[str, Dict[str, str]]:
        compu_methods = {}
        for cm in root.xpath("//*[local-name()='COMPU-METHOD']"):
            cm_name_elem = cm.xpath("*[local-name()='SHORT-NAME']")
            if not cm_name_elem:
                continue
            cm_name = cm_name_elem[0].text.strip()
            
            enums = {}
            for scale in cm.xpath(".//*[local-name()='COMPU-SCALE']"):
                lower_limit = scale.xpath("*[local-name()='LOWER-LIMIT']")
                vt = scale.xpath(".//*[local-name()='VT']")
                
                if lower_limit and vt and lower_limit[0].text and vt[0].text:
                    enums[lower_limit[0].text.strip()] = vt[0].text.strip()
                    
            if enums:
                compu_methods[cm_name] = enums
        return compu_methods

    def _extract_app_to_compu(self, root) -> Dict[str, str]:
        app_to_compu = {}
        for app_dt in root.xpath("//*[local-name()='APPLICATION-PRIMITIVE-DATA-TYPE']"):
            app_name_elem = app_dt.xpath("*[local-name()='SHORT-NAME']")
            compu_ref = app_dt.xpath(".//*[local-name()='COMPU-METHOD-REF']")
            
            if app_name_elem and compu_ref and compu_ref[0].text:
                app_name = app_name_elem[0].text.strip()
                ref_name = compu_ref[0].text.split("/")[-1].strip()
                app_to_compu[app_name] = ref_name
        return app_to_compu
