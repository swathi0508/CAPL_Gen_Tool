import os
import pandas as pd
from typing import Any, Dict, Tuple, List
from lxml import etree as ET
from collections import defaultdict

from signals.base_parser import BaseParser
from core.logger import log

class CANSignalParser(BaseParser):
    """Parses CAN ARXML files to extract I-Signals, PDUs, Scaling, and TX/RX nodes."""

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self._parsed_data: Dict[str, Any] = {}
        self.ns: Dict[str, str] = {}
        
        # Internal Parsing Caches
        self.compu_map = {}
        self.sig_attr_data = {}
        self.sig_to_pdu = {}
        self.pdu_period_map = {}
        self.ecu_port_map = defaultdict(dict)
        self.cluster_cache = []
        self.pdu_group_data = []

    def parse(self) -> Dict[str, Any]:
        """Parses the ARXML and returns a standard dictionary."""
        log.info(f"Parsing CAN ARXML: {self.file_path}")
        
        if not os.path.exists(self.file_path):
            log.error(f"Error: File '{self.file_path}' not found.")
            return {}

        try:
            parser = ET.XMLParser(huge_tree=True, encoding='utf-8')
            tree = ET.parse(self.file_path, parser)
            root = tree.getroot()
            self.ns = {'as': root.tag.split('}')[0].strip('{')}
        except Exception as e:
            log.error(f"Failed to parse ARXML file {self.file_path}: {e}")
            return {}

        # 1. Build Lookups
        self._index_compu_methods(root)
        self._index_signals(root)
        self._index_topology(root)

        # 2. Filter for CAN Signals (I-Prefix)
        can_signals = [s for s in self.sig_attr_data.keys() if s.startswith('I')]
        log.info(f"Filtered for {len(can_signals)} CAN signals (starting with 'I').")

        # 3. Resolve Paths and Attributes
        self._parsed_data, missing_signals = self._resolve_signals(can_signals)
        
        log.info(f"Successfully extracted {len(self._parsed_data)} CAN signals. ({len(missing_signals)} missing topology paths).")
        return self._parsed_data

    def to_dataframe(self) -> pd.DataFrame:
        """Converts the nested parsed CAN data into a flattened Pandas DataFrame."""
        if not self._parsed_data:
            self.parse()
        if not self._parsed_data:
            return pd.DataFrame()

        df_rows = []
        for signal_name, data in self._parsed_data.items():
            attrs = data.get("Attributes", {})
            paths = data.get("signal_paths", [])
            
            base_row = {
                "Signal_Name": signal_name,
                "Status": data.get("Status", "Unknown"),
                "Periodicity_ms": attrs.get("periodicity_ms", "N/A"),
                "Base_Type": attrs.get("Base_Type", "N/A"),
                "CAPL_Type": attrs.get("CAPL_Suggestions", {}).get("Phys_Type", "N/A"),
                "Unit": attrs.get("Unit", "N/A"),
                "Resolution": attrs.get("Resolution", "N/A"),
                "Offset": attrs.get("Offset", "N/A"),
                "Min": attrs.get("Phys_Limits", {}).get("Min", "N/A"),
                "Max": attrs.get("Phys_Limits", {}).get("Max", "N/A"),
            }

            if not paths:
                # If no routing paths, append base row with empty cluster info
                base_row.update({"Cluster": "N/A", "TX_Node": "N/A", "RX_Nodes": "N/A", "Signal_String": "N/A"})
                df_rows.append(base_row)
            else:
                # Explode rows for signals with multiple network paths
                for path in paths:
                    row = base_row.copy()
                    row.update({
                        "Cluster": path.get("can_cluster", "N/A"),
                        "TX_Node": path.get("tx", "N/A"),
                        "RX_Nodes": ", ".join(path.get("rx", [])),
                        "Signal_String": path.get("signal_name", "N/A")
                    })
                    df_rows.append(row)

        df = pd.DataFrame(df_rows)
        return df

    # --- Private Helper Methods ---

    def _index_compu_methods(self, root):
        for cm in root.xpath("//as:COMPU-METHOD", namespaces=self.ns):
            cm_name = cm.findtext("as:SHORT-NAME", namespaces=self.ns)
            v_nodes = cm.xpath(".//as:COMPU-NUMERATOR/as:V", namespaces=self.ns)
            v_list = [float(v.text) for v in v_nodes]
            
            v0, v1, v2 = 0.0, 1.0, 1.0
            if len(v_list) == 1: v1 = v_list[0]
            elif len(v_list) >= 2: v0, v1 = v_list[0], v_list[1]
            
            den_val = cm.findtext(".//as:COMPU-DENOMINATOR/as:V", namespaces=self.ns)
            if den_val: v2 = float(den_val)

            res, off = v1 / v2, v0 / v2
            if res == 0: res = 1.0

            enums = {}
            for scale in cm.xpath(".//as:COMPU-SCALE", namespaces=self.ns):
                vt = scale.findtext(".//as:VT", namespaces=self.ns)
                if vt:
                    v = scale.findtext(".//as:V", namespaces=self.ns) or scale.findtext("as:LOWER-LIMIT", namespaces=self.ns)
                    if v:
                        enums[v.split('.')[0]] = vt

            raw_unit_node = cm.findtext(".//as:UNIT-REF", namespaces=self.ns)
            if raw_unit_node:
                raw_unit = raw_unit_node.split('/')[-1].strip()
                raw_unit = raw_unit.encode('utf-8', 'ignore').decode('utf-8')
            else:
                raw_unit = ""

            display_unit = "\u00b0C" if raw_unit == "X_C" else (raw_unit if raw_unit else "None")

            self.compu_map[cm_name] = {
                'category': cm.findtext("as:CATEGORY", namespaces=self.ns),
                'res': res, 'off': off,
                'low_raw': cm.findtext(".//as:LOWER-LIMIT", namespaces=self.ns) or "0",
                'upp_raw': cm.findtext(".//as:UPPER-LIMIT", namespaces=self.ns) or "0",
                'enums': enums, 'unit': display_unit
            }

    def _index_signals(self, root):
        sys_sig_to_cm = {ss.findtext("as:SHORT-NAME", namespaces=self.ns): 
                         (ss.findtext(".//as:COMPU-METHOD-REF", namespaces=self.ns) or "").split('/')[-1]
                         for ss in root.xpath("//as:SYSTEM-SIGNAL", namespaces=self.ns)}

        for i_sig in root.xpath("//as:I-SIGNAL", namespaces=self.ns):
            name = i_sig.findtext("as:SHORT-NAME", namespaces=self.ns)
            if not name.startswith('I'):
                continue

            cm_ref = i_sig.findtext(".//as:COMPU-METHOD-REF", namespaces=self.ns)
            cm_key = cm_ref.split('/')[-1] if cm_ref else sys_sig_to_cm.get((i_sig.findtext(".//as:SYSTEM-SIGNAL-REF", namespaces=self.ns) or "").split('/')[-1])
            self.sig_attr_data[name] = {
                'datatype': (i_sig.findtext(".//as:BASE-TYPE-REF", namespaces=self.ns) or "").split('/')[-1],
                'db_attr': self.compu_map.get(cm_key, {})
            }

    def _index_topology(self, root):
        for pdu in root.xpath("//as:I-SIGNAL-I-PDU", namespaces=self.ns):
            p_name = pdu.findtext("as:SHORT-NAME", namespaces=self.ns)
            period_val = pdu.findtext(".//as:CYCLIC-TIMING//as:TIME-PERIOD//as:VALUE", namespaces=self.ns)
            
            if period_val:
                try:
                    self.pdu_period_map[p_name] = int(float(period_val.strip()) * 1000)
                except ValueError:
                    self.pdu_period_map[p_name] = "N/A"
            else:
                self.pdu_period_map[p_name] = "Event/None"

            for r in pdu.xpath(".//as:I-SIGNAL-REF/text()", namespaces=self.ns):
                sig_short_name = r.split('/')[-1]
                if sig_short_name.startswith('I'):
                    self.sig_to_pdu[sig_short_name] = p_name

        for ecu in root.xpath("//as:ECU-INSTANCE", namespaces=self.ns):
            e_name = ecu.findtext("as:SHORT-NAME", namespaces=self.ns)
            for port in ecu.xpath(".//*[contains(local-name(), 'PORT') or contains(local-name(), 'CONNECTOR') or contains(local-name(), 'GROUP')]", namespaces=self.ns):
                direction = port.findtext("as:COMMUNICATION-DIRECTION", namespaces=self.ns)
                port_text = "".join(port.itertext())
                self.ecu_port_map[e_name][port_text] = direction

        for cluster in root.xpath("//as:CAN-CLUSTER | //as:ETHERNET-CLUSTER", namespaces=self.ns):
            self.cluster_cache.append({
                'name': cluster.findtext("as:SHORT-NAME", namespaces=self.ns),
                'type': "ETHERNET" if "ETHERNET" in cluster.tag.upper() else "CAN",
                'triggerings': [ET.tostring(t, encoding='unicode') for t in cluster.xpath(".//*[local-name()='PDU-TRIGGERING']", namespaces=self.ns)]
            })

        for group in root.xpath("//as:I-SIGNAL-I-PDU-GROUP[as:COMMUNICATION-DIRECTION='OUT']", namespaces=self.ns):
            self.pdu_group_data.append({'name': group.findtext("as:SHORT-NAME", namespaces=self.ns), 'text': "".join(group.xpath(".//text()"))})

    def _resolve_signals(self, signal_list: List[str]) -> Tuple[Dict[str, Any], List[str]]:
        results = {}
        missing_signals = []

        for signal_name in signal_list:
            base_pdu_name = self.sig_to_pdu.get(signal_name)
            
            if not base_pdu_name:
                missing_signals.append(signal_name)
                results[signal_name] = {"Status": "Missing from Topology", "Attributes": {}, "signal_paths": []}
                continue

            s_info = self.sig_attr_data.get(signal_name, {})
            db = s_info.get('db_attr', {})
            res, off = db.get('res', 1.0), db.get('off', 0.0)
            low_raw, upp_raw = float(db.get('low_raw', 0) or 0), float(db.get('upp_raw', 0) or 0)
            mid_raw = int((low_raw + upp_raw) // 2)

            base_type = s_info.get('datatype', '').lower()
            if "uint8" in base_type: capl_raw_type = "byte"
            elif "uint16" in base_type: capl_raw_type = "word"
            elif "uint32" in base_type: capl_raw_type = "dword"
            else: capl_raw_type = "word"
            
            capl_phys_type = "double" if (res % 1 != 0 or off % 1 != 0) else "int"

            entry = {
                "Status": "Resolved",
                "Attributes": {
                    "periodicity_ms": self.pdu_period_map.get(base_pdu_name, "N/A"),
                    "Category": db.get('category', 'N/A'),
                    "Base_Type": s_info.get('datatype', 'N/A'),
                    "Unit": db.get('unit', 'None'),
                    "Resolution": res, "Offset": off,
                    "Raw_Limits": {"Min": int(low_raw), "Max": int(upp_raw)},
                    "Phys_Limits": {"Min": (low_raw * res) + off, "Max": (upp_raw * res) + off},
                    "Enums": db.get('enums', {}),
                    "CAPL_Suggestions": {
                        "Phys_Type": capl_phys_type, "Raw_Type": capl_raw_type,
                        "Mid_Phys": (mid_raw * res) + off, "Mid_Raw": mid_raw
                    }
                },
                "signal_paths": []
            }

            for cluster in self.cluster_cache:
                cluster_name = cluster['name']
                matched_trig_xml = next((t for t in cluster['triggerings'] if base_pdu_name in t), None)
                if not matched_trig_xml: continue

                tx, rx_list = "Unknown/Gateway", set()
                for ecu_name, ports in self.ecu_port_map.items():
                    for port_text, direction in ports.items():
                        if cluster_name in port_text and base_pdu_name in port_text:
                            if direction == "OUT": tx = ecu_name
                            elif direction == "IN": rx_list.add(ecu_name)
                            elif cluster['type'] == "ETHERNET":
                                if f"/{ecu_name}/" in matched_trig_xml and tx == "Unknown/Gateway": 
                                    tx = ecu_name
                                else: 
                                    rx_list.add(ecu_name)

                if tx == "Unknown/Gateway" or tx == "PCU_LLCE_2":
                    for group in self.pdu_group_data:
                        if cluster_name in group['name'] and base_pdu_name in group['text']:
                            ptx = group['name'].split('_')[0]
                            tx = "PIU_Mst" if ptx == "PIU" else ptx
                            break

                if tx in rx_list: rx_list.remove(tx)
                if tx == "Unknown/Gateway" and cluster_name == "CAN_FD_CHASSIS": tx = "PCU_LLCE_2"

                entry["signal_paths"].append({
                    "can_cluster": cluster_name,
                    "tx": tx,
                    "rx": sorted(list(rx_list)),
                    "signal_name": f"{cluster_name}::{tx}::{base_pdu_name}::{signal_name}"
                })
            
            results[signal_name] = entry
            
        return results, missing_signals