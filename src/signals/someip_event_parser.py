import re
import pandas as pd
from typing import Any, Dict
from lxml import etree

from base_parser import BaseParser
from core.logger import log


class SomeIPEventParser(BaseParser):
    """Parses SOME/IP ARXML files to extract signals, Enums, and Physical Value ranges (Min/Mid/Max)."""

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self._parsed_data: Dict[str, Any] = {}
    
    def parse(self) -> Dict[str, Any]:
        log.info(f"Parsing ETH ARXML: {self.file_path}")
        
        try:
            tree = etree.parse(self.file_path)
            root = tree.getroot()
        except Exception as e:
            log.error(f"Failed to parse ARXML file {self.file_path}: {e}")
            return {}

        # 1. Pre-process Dictionaries
        compu_methods = self._extract_compu_methods(root)
        app_to_compu = self._extract_app_to_compu(root)

        def get_compu_data(app_type_name: str) -> Dict[str, Any]:
            compu_name = app_to_compu.get(app_type_name)
            # Default empty structure if no CompuMethod is found
            return compu_methods.get(compu_name, {
                "enums": {}, "has_enums": False, 
                "min": None, "max": None, "mid": None
            })

        def format_val(v):
            """Helper to format numbers cleanly (e.g., 5.0 -> 5)"""
            if v is None:
                return "N/A"
            return int(v) if float(v).is_integer() else round(v, 4)

        self._parsed_data = {}

        # 2. Main Mapping Loop
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
                
                # Retrieve CompuMethod details
                c_data = get_compu_data(raw_app_name)
                
                # Determine state string
                if c_data["has_enums"]:
                    states_str = " | ".join([f"{k}: {v}" for k, v in c_data["enums"].items()])
                elif c_data["min"] is not None:
                    states_str = "Physical Value" # Used to be "No Enums"
                else:
                    states_str = "No Data"

                base_sig_str = f'"EthernetCluster::sif_{sif}::{someip_event}::{clean_method}"'
                
                # Add to Dictionary
                self._parsed_data[base_sig_str] = {
                    "Cluster": "EthernetCluster",
                    "SIF": sif,
                    "Event": someip_event,
                    "Method": clean_method,
                    "Available_States": states_str,
                    "Min": format_val(c_data["min"]),
                    "Mid": format_val(c_data["mid"]),
                    "Max": format_val(c_data["max"])
                }
                
                # Expanded ValueState Signal
                if valuestate_app_name:
                    vs_event = someip_event[:-1] if someip_event.endswith('s') else someip_event
                    vs_method = f"{clean_method}ValueState"
                    
                    vs_c_data = get_compu_data(valuestate_app_name)
                    vs_states = " | ".join([f"{k}: {v}" for k, v in vs_c_data["enums"].items()]) if vs_c_data["has_enums"] else "Physical Value"
                    vs_sig_str = f'"EthernetCluster::sif_{sif}::{vs_event}::{vs_method}"'
                    
                    self._parsed_data[vs_sig_str] = {
                        "Cluster": "EthernetCluster",
                        "SIF": sif,
                        "Event": vs_event,
                        "Method": vs_method,
                        "Available_States": vs_states,
                        "Min": format_val(vs_c_data["min"]),
                        "Mid": format_val(vs_c_data["mid"]),
                        "Max": format_val(vs_c_data["max"])
                    }

        log.info(f"Successfully extracted {len(self._parsed_data)} signals.")
        return self._parsed_data

    def to_dataframe(self) -> pd.DataFrame:
        """Converts the parsed dictionary into a structured Pandas DataFrame."""
        if not self._parsed_data:
            self.parse()
        if not self._parsed_data:
            return pd.DataFrame()

        df_rows = []
        for signal_string, properties in self._parsed_data.items():
            row = {"Signal_String": signal_string}
            row.update(properties)
            df_rows.append(row)
            
        df = pd.DataFrame(df_rows)
        df = df.sort_values(by=['SIF', 'Event', 'Method']).reset_index(drop=True)
        return df

    # --- Private Helper Methods ---

    def _extract_compu_methods(self, root) -> Dict[str, Dict]:
        """Finds COMPU-METHODS, tracking Enums and numerical Min/Mid/Max boundaries."""
        compu_methods = {}
        for cm in root.xpath("//*[local-name()='COMPU-METHOD']"):
            cm_name_elem = cm.xpath("*[local-name()='SHORT-NAME']")
            if not cm_name_elem:
                continue
            cm_name = cm_name_elem[0].text.strip()
            
            enums = {}
            min_val = float('inf')
            max_val = float('-inf')
            
            for scale in cm.xpath(".//*[local-name()='COMPU-SCALE']"):
                ll_node = scale.xpath("*[local-name()='LOWER-LIMIT']")
                ul_node = scale.xpath("*[local-name()='UPPER-LIMIT']")
                vt_node = scale.xpath(".//*[local-name()='VT']")
                
                ll_text = ll_node[0].text.strip() if ll_node and ll_node[0].text else None
                # If there is no UPPER-LIMIT, it's usually a single enum mapping, so Max = Min
                ul_text = ul_node[0].text.strip() if ul_node and ul_node[0].text else ll_text
                
                # Check for numerical Min
                if ll_text is not None:
                    try:
                        ll_f = float(ll_text)
                        if ll_f < min_val: min_val = ll_f
                    except ValueError:
                        pass
                
                # Check for numerical Max
                if ul_text is not None:
                    try:
                        ul_f = float(ul_text)
                        if ul_f > max_val: max_val = ul_f
                    except ValueError:
                        pass
                
                # Check for Enums
                if ll_text is not None and vt_node and vt_node[0].text:
                    enums[ll_text] = vt_node[0].text.strip()
            
            has_limits = min_val != float('inf') and max_val != float('-inf')
            
            compu_methods[cm_name] = {
                "enums": enums,
                "has_enums": len(enums) > 0,
                "min": min_val if has_limits else None,
                "max": max_val if has_limits else None,
                "mid": (min_val + max_val) / 2 if has_limits else None
            }
            
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