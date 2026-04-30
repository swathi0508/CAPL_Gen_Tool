import lxml.etree as ET
from collections import defaultdict
import pandas as pd
import json
import time
import sys
import logging
from pathlib import Path

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("CAN_Parser")

def format_time(seconds):
    """Converts seconds into HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

class CAN_Parser:
    def __init__(self, arxml_path: str):
        self.arxml_path = Path(arxml_path)
        self.root = None
        self.ns = {}
        self.compu_map = {}
        self.sig_attr_data = {}
        self.sig_to_pdu = {}
        self.pdu_period_map = {}
        self.ecu_port_map = defaultdict(dict)
        self.cluster_cache = []
        self.pdu_group_data = []

    def load_and_index(self):
        try:
            parser = ET.XMLParser(huge_tree=True, encoding='utf-8')
            tree = ET.parse(str(self.arxml_path), parser)
            self.root = tree.getroot()
            self.ns = {'as': self.root.tag.split('}')[0].strip('{')}
            logger.info(f"Loaded ARXML: {self.arxml_path.name}")
        except Exception as e:
            logger.error(f"ARXML Load Error: {e}")
            sys.exit(1)

        # --- COMPU-METHOD INDEXING ---
        for cm in self.root.xpath("//as:COMPU-METHOD", namespaces=self.ns):
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

        sys_sig_to_cm = {ss.findtext("as:SHORT-NAME", namespaces=self.ns): 
                         (ss.findtext(".//as:COMPU-METHOD-REF", namespaces=self.ns) or "").split('/')[-1]
                         for ss in self.root.xpath("//as:SYSTEM-SIGNAL", namespaces=self.ns)}

        for i_sig in self.root.xpath("//as:I-SIGNAL", namespaces=self.ns):
            name = i_sig.findtext("as:SHORT-NAME", namespaces=self.ns)
            if not name.startswith('I'):
                continue

            cm_ref = i_sig.findtext(".//as:COMPU-METHOD-REF", namespaces=self.ns)
            cm_key = cm_ref.split('/')[-1] if cm_ref else sys_sig_to_cm.get((i_sig.findtext(".//as:SYSTEM-SIGNAL-REF", namespaces=self.ns) or "").split('/')[-1])
            self.sig_attr_data[name] = {
                'datatype': (i_sig.findtext(".//as:BASE-TYPE-REF", namespaces=self.ns) or "").split('/')[-1],
                'db_attr': self.compu_map.get(cm_key, {})
            }

        # --- TOPOLOGY & PERIODICITY INDEXING ---
        for pdu in self.root.xpath("//as:I-SIGNAL-I-PDU", namespaces=self.ns):
            p_name = pdu.findtext("as:SHORT-NAME", namespaces=self.ns)
            period_val = pdu.findtext(".//as:CYCLIC-TIMING//as:TIME-PERIOD//as:VALUE", namespaces=self.ns)
            
            if period_val:
                try:
                    ms_val = int(float(period_val.strip()) * 1000)
                    self.pdu_period_map[p_name] = ms_val
                except ValueError:
                    self.pdu_period_map[p_name] = "N/A"
            else:
                self.pdu_period_map[p_name] = "Event/None"

            for r in pdu.xpath(".//as:I-SIGNAL-REF/text()", namespaces=self.ns):
                sig_short_name = r.split('/')[-1]
                if sig_short_name.startswith('I'):
                    self.sig_to_pdu[sig_short_name] = p_name

        for ecu in self.root.xpath("//as:ECU-INSTANCE", namespaces=self.ns):
            e_name = ecu.findtext("as:SHORT-NAME", namespaces=self.ns)
            for port in ecu.xpath(".//*[contains(local-name(), 'PORT') or contains(local-name(), 'CONNECTOR') or contains(local-name(), 'GROUP')]", namespaces=self.ns):
                direction = port.findtext("as:COMMUNICATION-DIRECTION", namespaces=self.ns)
                port_text = "".join(port.itertext())
                self.ecu_port_map[e_name][port_text] = direction

        for cluster in self.root.xpath("//as:CAN-CLUSTER | //as:ETHERNET-CLUSTER", namespaces=self.ns):
            self.cluster_cache.append({
                'name': cluster.findtext("as:SHORT-NAME", namespaces=self.ns),
                'type': "ETHERNET" if "ETHERNET" in cluster.tag.upper() else "CAN",
                'triggerings': [ET.tostring(t, encoding='unicode') for t in cluster.xpath(".//*[local-name()='PDU-TRIGGERING']", namespaces=self.ns)]
            })

        for group in self.root.xpath("//as:I-SIGNAL-I-PDU-GROUP[as:COMMUNICATION-DIRECTION='OUT']", namespaces=self.ns):
            self.pdu_group_data.append({'name': group.findtext("as:SHORT-NAME", namespaces=self.ns), 'text': "".join(group.xpath(".//text()"))})

    def parse_signals(self, signal_list):
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

def main():
    arxml_in = sys.argv[1] if len(sys.argv) > 1 else r"C:/poc/Autosar/can_parser/ETH_CAN.arxml"
    json_out = sys.argv[2] if len(sys.argv) > 2 else r"C:/poc/Autosar/can_parser/CAN_Signals_Database.json"

    start_time = time.time()

    parser = CAN_Parser(arxml_in)
    parser.load_and_index()

    can_signals = sorted([s for s in parser.sig_attr_data.keys() if s.startswith('I')])
    logger.info(f"Filtered for {len(can_signals)} CAN signals (starting with 'I').")

    results, missing = parser.parse_signals(can_signals)
    
    # Calculate and format time
    raw_duration = time.time() - start_time
    formatted_duration = format_time(raw_duration)
    
    output_payload = {
        "Summary": {
            "Total_CAN_Signals_Found": len(can_signals),
            "Resolved_With_Paths": len(can_signals) - len(missing),
            "No_Path_Found": len(missing),
            "Processing_Time_HH_MM_SS": formatted_duration
        },
        "ICAN_SIGNAL": results
    }

    try:
        out_path = Path(json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(output_payload, f, indent=4, ensure_ascii=False)
        logger.info(f"CAN Database JSON saved to: {json_out}")
    except Exception as e:
        logger.error(f"Failed to write JSON: {e}")

    logger.info("="*40)
    logger.info(f"TOTAL TIME:  {formatted_duration}")
    logger.info(f"CAN SIGNALS: {len(can_signals)}")
    logger.info("="*40)

if __name__ == "__main__":
    main()
    