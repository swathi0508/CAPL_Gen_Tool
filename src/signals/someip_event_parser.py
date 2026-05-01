import os
import re
import math
import pandas as pd
from typing import Any, Dict, List
from lxml import etree

from signals.base_parser import BaseParser
from core.logger import log

class SomeIPEventParser(BaseParser):
    """Parses SOME/IP ARXML files to extract signals, Data Types, Ports, Enums, and Scaling boundaries."""

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self._parsed_data: Dict[str, Any] = {}
    
    def parse(self) -> Dict[str, Any]:
        """Parses the ARXML and returns a standard dictionary."""
        log.info(f"Parsing ETH ARXML: {self.file_path}")
        
        if not os.path.exists(self.file_path):
            log.error(f"Error: File '{self.file_path}' not found.")
            return {}
            
        try:
            tree = etree.parse(self.file_path)
            root = tree.getroot()
        except Exception as e:
            log.error(f"Failed to parse ARXML file {self.file_path}: {e}")
            return {}

        # 1. Pre-process Lookup Dictionaries via Private Methods
        compu_methods = self._extract_compu_methods(root)
        app_to_compu = self._extract_app_to_compu(root)
        impl_to_basetype = self._extract_impl_to_basetype(root)
        app_to_basetype = self._extract_app_to_basetype(root, impl_to_basetype)
        records_dict = self._extract_records(root)
        mapping_to_ports = self._extract_mapping_to_ports(root)

        # Nested Data Retrievers
        def get_compu_data(app_type_name: str) -> Dict[str, Any]:
            compu_name = app_to_compu.get(app_type_name, app_type_name)
            return compu_methods.get(compu_name, {
                "enums": {}, "has_enums": False, 
                "min": None, "max": None, "mid": None,
                "unit": "N/A", "factor": "N/A", "offset": "N/A"
            })

        def format_val(v: Any) -> Any:
            if v is None or v == "N/A": return "N/A"
            return int(v) if float(v).is_integer() else round(v, 4)

        def find_best_ports(app_name: str, event_name: str, available_ports: List[str]) -> List[str]:
            if not available_ports: return ["N/A"]
            if len(available_ports) == 1: return [available_ports[0]]
            for p in available_ports:
                if app_name.lower() in p.lower(): return [p]
            for p in available_ports:
                if event_name.lower() in p.lower(): return [p]
            return available_ports # Explode all if it's a shared primitive

        self._parsed_data = {}

        # 2. Main Mapping & Exploding Loop
        for dtms in root.xpath("//*[local-name()='DATA-TYPE-MAPPING-SET']"):
            short_name_elem = dtms.xpath("*[local-name()='SHORT-NAME']")
            if not short_name_elem:
                continue
                
            mapping_short_name = short_name_elem[0].text.strip()
            match = re.search(r'^X(\d+)_(.*?)SvcProv', mapping_short_name)
            if not match:
                continue
                
            sif = match.group(1)
            raw_event_name = match.group(2)
            someip_event = f"SomeIp{raw_event_name}"
            
            swc_ports = mapping_to_ports.get(mapping_short_name, [])
            valid_methods = []
            valuestate_app_name = None
            valuestate_impl_name = None
            
            # Sub-loop: Extract maps from the set
            for dt_map in dtms.xpath(".//*[local-name()='DATA-TYPE-MAP']"):
                app_ref = dt_map.xpath("*[local-name()='APPLICATION-DATA-TYPE-REF']")
                impl_ref = dt_map.xpath("*[local-name()='IMPLEMENTATION-DATA-TYPE-REF']")
                
                if app_ref and app_ref[0].text:
                    app_path_raw = app_ref[0].text.split("/")[-1].strip()
                    impl_path_raw = impl_ref[0].text.split("/")[-1].strip() if impl_ref and impl_ref[0].text else None
                    
                    if re.match(r'^ValueState\d*$', app_path_raw, re.IGNORECASE):
                        valuestate_app_name = app_path_raw
                        valuestate_impl_name = impl_path_raw
                        continue 
                        
                    clean_method = app_path_raw[:-1] if app_path_raw.endswith("T") else app_path_raw
                    valid_methods.append((clean_method, app_path_raw, impl_path_raw))
            
            # Sub-loop: Explode Methods into Ports
            for clean_method, raw_app_name, raw_impl_name in valid_methods:
                actual_ports = find_best_ports(raw_app_name, raw_event_name, swc_ports)
                
                for actual_port_name in actual_ports:
                    
                    # Clean the Port Name for the CAPL string (Removes 'Interface' + trailing numbers)
                    if actual_port_name != "N/A":
                        clean_port = re.sub(r'Interface\d*$', '', actual_port_name, flags=re.IGNORECASE)
                    else:
                        clean_port = someip_event 
                    
                    # SCENARIO A: Application Record (Unroll Struct)
                    if raw_app_name in records_dict:
                        for element in records_dict[raw_app_name]:
                            elem_name = element["name"]
                            tref = element["tref"] 
                            
                            c_data = get_compu_data(tref)
                            datatype = app_to_basetype.get(tref, "N/A")
                            if datatype == "N/A":
                                clean_match = re.match(r'^(u?s?int(?:8|16|32|64)|float(?:32|64)|boolean|double)', tref, re.IGNORECASE)
                                datatype = clean_match.group(1).lower() if clean_match else "N/A"
                            
                            states_str = " | ".join([f"{k}: {v}" for k, v in c_data["enums"].items()]) if c_data["has_enums"] else ("Physical Value" if c_data["min"] is not None else "No Data")
                            sig_str = f'"EthernetCluster::sif_{sif}::{clean_port}::{elem_name}"'
                            
                            self._parsed_data[sig_str] = {
                                "Cluster": "EthernetCluster", "SIF": sif, "Event": someip_event,
                                "Port": actual_port_name, "Method": elem_name, "DataType": datatype,
                                "Available_States": states_str, "Min": format_val(c_data["min"]),
                                "Mid": format_val(c_data["mid"]), "Max": format_val(c_data["max"]),
                                "Factor": format_val(c_data["factor"]), "Offset": format_val(c_data["offset"]),
                                "Unit": c_data["unit"]
                            }

                    # SCENARIO B: Primitive Value
                    else:
                        c_data = get_compu_data(raw_app_name)
                        datatype = impl_to_basetype.get(raw_impl_name, "N/A") if raw_impl_name else "N/A"
                        states_str = " | ".join([f"{k}: {v}" for k, v in c_data["enums"].items()]) if c_data["has_enums"] else ("Physical Value" if c_data["min"] is not None else "No Data")
                        sig_str = f'"EthernetCluster::sif_{sif}::{clean_port}::{clean_method}"'
                        
                        self._parsed_data[sig_str] = {
                            "Cluster": "EthernetCluster", "SIF": sif, "Event": someip_event,
                            "Port": actual_port_name, "Method": clean_method, "DataType": datatype,
                            "Available_States": states_str, "Min": format_val(c_data["min"]),
                            "Mid": format_val(c_data["mid"]), "Max": format_val(c_data["max"]),
                            "Factor": format_val(c_data["factor"]), "Offset": format_val(c_data["offset"]),
                            "Unit": c_data["unit"]
                        }
                    
                    # EXPANSION: ValueState
                    if valuestate_app_name and raw_app_name not in records_dict:
                        vs_event = someip_event[:-1] if someip_event.endswith('s') else someip_event
                        vs_method = f"{clean_method}ValueState"
                        
                        vs_c_data = get_compu_data(valuestate_app_name)
                        vs_datatype = impl_to_basetype.get(valuestate_impl_name, "N/A") if valuestate_impl_name else "N/A"
                        vs_states = " | ".join([f"{k}: {v}" for k, v in vs_c_data["enums"].items()]) if vs_c_data["has_enums"] else "Physical Value"
                        vs_sig_str = f'"EthernetCluster::sif_{sif}::{clean_port}::{vs_method}"'
                        
                        self._parsed_data[vs_sig_str] = {
                            "Cluster": "EthernetCluster", "SIF": sif, "Event": vs_event,
                            "Port": actual_port_name, "Method": vs_method, "DataType": vs_datatype, 
                            "Available_States": vs_states, "Min": format_val(vs_c_data["min"]), 
                            "Mid": format_val(vs_c_data["mid"]), "Max": format_val(vs_c_data["max"]), 
                            "Factor": format_val(vs_c_data["factor"]), "Offset": format_val(vs_c_data["offset"]), 
                            "Unit": vs_c_data["unit"]
                        }

        log.info(f"Successfully extracted {len(self._parsed_data)} unique signals.")
        return self._parsed_data

    # --- Private Helper Methods ---

    def _extract_compu_methods(self, root) -> Dict[str, Dict]:
        compu_methods = {}
        for cm in root.xpath("//*[local-name()='COMPU-METHOD']"):
            cm_name_elem = cm.xpath("*[local-name()='SHORT-NAME']")
            if not cm_name_elem: continue
            cm_name = cm_name_elem[0].text.strip()
            
            unit_ref = cm.xpath("*[local-name()='UNIT-REF']")
            unit = unit_ref[0].text.split("/")[-1].strip() if unit_ref and unit_ref[0].text else "N/A"
            
            enums, min_val, max_val, factor, offset = {}, float('inf'), float('-inf'), "N/A", "N/A"
            
            for scale in cm.xpath(".//*[local-name()='COMPU-SCALE']"):
                ll_node = scale.xpath("*[local-name()='LOWER-LIMIT']")
                ul_node = scale.xpath("*[local-name()='UPPER-LIMIT']")
                vt_node = scale.xpath(".//*[local-name()='VT']")
                coeffs_node = scale.xpath(".//*[local-name()='COMPU-RATIONAL-COEFFS']")
                
                ll_text = ll_node[0].text.strip() if ll_node and ll_node[0].text else None
                ul_text = ul_node[0].text.strip() if ul_node and ul_node[0].text else ll_text
                
                if ll_text is not None:
                    try:
                        ll_f = float(ll_text)
                        if ll_f < min_val: min_val = ll_f
                    except ValueError: pass
                
                if ul_text is not None:
                    try:
                        ul_f = float(ul_text)
                        if ul_f > max_val: max_val = ul_f
                    except ValueError: pass
                
                if ll_text is not None and vt_node and vt_node[0].text:
                    enums[ll_text] = vt_node[0].text.strip()
                    
                if coeffs_node:
                    try:
                        num_v = coeffs_node[0].xpath(".//*[local-name()='COMPU-NUMERATOR']/*[local-name()='V']")
                        den_v = coeffs_node[0].xpath(".//*[local-name()='COMPU-DENOMINATOR']/*[local-name()='V']")
                        n0 = float(num_v[0].text) if len(num_v) > 0 else 0.0
                        n1 = float(num_v[1].text) if len(num_v) > 1 else 1.0
                        d = float(den_v[0].text) if len(den_v) > 0 else 1.0
                        if d != 0:
                            offset, factor = n0 / d, n1 / d
                    except Exception: pass
            
            has_limits = min_val != float('inf') and max_val != float('-inf')
            mid_val = math.floor((min_val + max_val) / 2) if has_limits else None
                
            compu_methods[cm_name] = {
                "enums": enums, "has_enums": len(enums) > 0,
                "min": min_val if has_limits else None, "max": max_val if has_limits else None,
                "mid": mid_val, "unit": unit, "factor": factor, "offset": offset
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

    def _extract_impl_to_basetype(self, root) -> Dict[str, str]:
        impl_to_basetype = {}
        for impl_dt in root.xpath("//*[local-name()='IMPLEMENTATION-DATA-TYPE']"):
            impl_name_elem = impl_dt.xpath("*[local-name()='SHORT-NAME']")
            base_ref = impl_dt.xpath(".//*[local-name()='BASE-TYPE-REF']")
            if impl_name_elem and base_ref and base_ref[0].text:
                impl_name = impl_name_elem[0].text.strip()
                basetype_raw = base_ref[0].text.split("/")[-1].strip()
                clean_match = re.match(r'^(u?s?int(?:8|16|32|64)|float(?:32|64)|boolean|double)', basetype_raw, re.IGNORECASE)
                impl_to_basetype[impl_name] = clean_match.group(1).lower() if clean_match else basetype_raw
        return impl_to_basetype

    def _extract_app_to_basetype(self, root, impl_to_basetype: Dict[str, str]) -> Dict[str, str]:
        app_to_basetype = {}
        for dt_map in root.xpath(".//*[local-name()='DATA-TYPE-MAP']"):
            a_ref = dt_map.xpath("*[local-name()='APPLICATION-DATA-TYPE-REF']")
            i_ref = dt_map.xpath("*[local-name()='IMPLEMENTATION-DATA-TYPE-REF']")
            if a_ref and i_ref and a_ref[0].text and i_ref[0].text:
                a_name = a_ref[0].text.split("/")[-1].strip()
                i_name = i_ref[0].text.split("/")[-1].strip()
                basetype = impl_to_basetype.get(i_name, "N/A")
                if basetype != "N/A":
                    app_to_basetype[a_name] = basetype
        return app_to_basetype

    def _extract_records(self, root) -> Dict[str, List[Dict[str, str]]]:
        records_dict = {}
        for rec in root.xpath("//*[local-name()='APPLICATION-RECORD-DATA-TYPE']"):
            short_name_elem = rec.xpath("*[local-name()='SHORT-NAME']")
            if not short_name_elem: continue
            rec_name = short_name_elem[0].text.strip()
            
            elements = []
            for elem in rec.xpath(".//*[local-name()='APPLICATION-RECORD-ELEMENT']"):
                elem_name_node = elem.xpath("*[local-name()='SHORT-NAME']")
                tref_node = elem.xpath("*[local-name()='TYPE-TREF']")
                if elem_name_node and tref_node:
                    elements.append({
                        "name": elem_name_node[0].text.strip(),
                        "tref": tref_node[0].text.split("/")[-1].strip()
                    })
            records_dict[rec_name] = elements
        return records_dict

    def _extract_mapping_to_ports(self, root) -> Dict[str, List[str]]:
        mapping_to_ports = {}
        for swc in root.xpath("//*[local-name()='APPLICATION-SW-COMPONENT-TYPE']"):
            swc_ports = []
            for port in swc.xpath(".//*[local-name()='R-PORT-PROTOTYPE'] | .//*[local-name()='P-PORT-PROTOTYPE']"):
                p_name_node = port.xpath("*[local-name()='SHORT-NAME']")
                if p_name_node:
                    swc_ports.append(p_name_node[0].text.strip())

            for m_ref in swc.xpath(".//*[local-name()='DATA-TYPE-MAPPING-REF']"):
                if m_ref.text:
                    m_short_name = m_ref.text.split("/")[-1].strip()
                    if m_short_name not in mapping_to_ports:
                        mapping_to_ports[m_short_name] = set()
                    mapping_to_ports[m_short_name].update(swc_ports)
                    
        return {k: list(v) for k, v in mapping_to_ports.items()}