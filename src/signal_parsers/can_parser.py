from typing import Any, Dict, List

from lxml import etree

from logger import log
from signal_parsers.base_parser import BaseParser


class CANSignalParser(BaseParser):
    def __init__(self, file_path: str):
        super().__init__(file_path)
        self._parsed_data: Dict[str, Any] = {}
        self.ns: Dict[str, str] = {}

        # Lookups
        self.compu_map = {}
        self.sig_attr_data = {}
        self.sig_to_pdu = {}
        self.pdu_period_map = {}

        # Caches
        self._topology_cache = {}
        self._ecu_cache = []
        self._group_cache = []
        self._cluster_cache = []

    def parse(self) -> Dict[str, Any]:
        log.info(f"Parsing CAN ARXML: {self.file_path}")
        parser = etree.XMLParser(huge_tree=True, encoding='utf-8', collect_ids=False)
        tree = etree.parse(self.file_path, parser)
        root = tree.getroot()
        self.ns = {'as': root.tag.split('}')[0].strip('{')}
        _ns = self.ns

        self._index_compu_methods(root)
        self._index_signals(root)

        # 1. Cache ECUs and their port text
        for ecu in root.xpath("//as:ECU-INSTANCE", namespaces=_ns):
            e_name = ecu.findtext("as:SHORT-NAME", namespaces=_ns)
            ports = []
            for p in ecu.iter():
                tag_local = etree.QName(p).localname
                if 'PORT' in tag_local or 'CONNECTOR' in tag_local or 'GROUP' in tag_local:
                    ports.append({
                        'dir': p.findtext(f"{{{_ns['as']}}}COMMUNICATION-DIRECTION"),
                        'text': "".join(p.itertext())
                    })
            self._ecu_cache.append({'name': e_name, 'ports': ports})

        # 2. Cache PDU Groups
        for gp in root.xpath("//as:I-SIGNAL-I-PDU-GROUP[as:COMMUNICATION-DIRECTION='OUT']", namespaces=_ns):
            self._group_cache.append({
                'name': gp.findtext("as:SHORT-NAME", namespaces=_ns),
                'text': "".join(gp.xpath(".//text()"))
            })

        # 3. Cache Clusters with FULL TEXT (Fixes missing clusters)
        for cluster in root.xpath("//as:CAN-CLUSTER | //as:ETHERNET-CLUSTER", namespaces=_ns):
            self._cluster_cache.append({
                'name': cluster.findtext("as:SHORT-NAME", namespaces=_ns),
                'is_eth': "ETHERNET" in cluster.tag.upper(),
                'full_text': "".join(cluster.itertext()),
                'trig_nodes': cluster.xpath(".//*[local-name()='PDU-TRIGGERING']", namespaces=_ns)
            })

        # 4. Map Signal -> PDU
        for pdu in root.xpath("//as:I-SIGNAL-I-PDU", namespaces=_ns):
            p_name = pdu.findtext("as:SHORT-NAME", namespaces=_ns)
            period = pdu.findtext(".//as:CYCLIC-TIMING//as:TIME-PERIOD//as:VALUE", namespaces=_ns)
            self.pdu_period_map[p_name] = int(float(period) * 1000) if period else "Event/None"
            for r in pdu.xpath(".//as:I-SIGNAL-REF/text()", namespaces=_ns):
                self.sig_to_pdu[r.split('/')[-1]] = p_name

        can_signals = [s for s in self.sig_attr_data.keys() if s.startswith('I')]
        self._parsed_data = self._resolve_signals(can_signals)
        return self._parsed_data

    def _calculate_pdu_paths(self, pdu_name: str) -> List[Dict]:
        paths = []
        for cluster in self._cluster_cache:
            if pdu_name not in cluster['full_text']:
                continue

            c_name = cluster['name']
            tx, rx_list = "Unknown/Gateway", set()

            tr_node = next((t for t in cluster['trig_nodes'] if pdu_name in (t.findtext(".//as:I-PDU-REF", namespaces=self.ns) or "")), None)
            tr_xml = etree.tostring(tr_node, encoding='unicode') if tr_node is not None else ""

            for ecu in self._ecu_cache:
                for port in ecu['ports']:
                    if c_name in port['text'] and pdu_name in port['text']:
                        if port['dir'] == "OUT": tx = ecu['name']
                        elif port['dir'] == "IN": rx_list.add(ecu['name'])
                        elif cluster['is_eth'] and tr_xml:
                            if f"/{ecu['name']}/" in tr_xml and tx == "Unknown/Gateway": tx = ecu['name']
                            else: rx_list.add(ecu['name'])

            if tx in ["Unknown/Gateway", "PCU_LLCE_2"]:
                for group in self._group_cache:
                    if c_name in group['name'] and pdu_name in group['text']:
                        tx = group['name'].split('_')[0].replace("PIU", "PIU_Mst")
                        break

            if tx in rx_list: rx_list.remove(tx)
            if tx == "Unknown/Gateway" and c_name == "CAN_FD_CHASSIS": tx = "PCU_LLCE_2"
            paths.append({"can_cluster": c_name, "tx": tx, "rx": sorted(list(rx_list))})
        return paths

    def _index_compu_methods(self, root):
        _ns = self.ns
        for cm in root.xpath("//as:COMPU-METHOD", namespaces=_ns):
            cm_name = cm.findtext("as:SHORT-NAME", namespaces=_ns)
            v_nodes = cm.xpath(".//as:COMPU-NUMERATOR/as:V", namespaces=_ns)
            v_list = [float(v.text) for v in v_nodes]
            v0, v1, v2 = 0.0, 1.0, 1.0
            if len(v_list) == 1: v1 = v_list[0]
            elif len(v_list) >= 2: v0, v1 = v_list[0], v_list[1]
            den_val = cm.findtext(".//as:COMPU-DENOMINATOR/as:V", namespaces=_ns)
            if den_val: v2 = float(den_val)
            res, off = v1 / v2, v0 / v2
            if res == 0: res = 1.0

            enums = {}
            for s in cm.xpath(".//as:COMPU-SCALE", namespaces=_ns):
                vt = s.findtext(".//as:VT", namespaces=_ns)
                v = s.findtext(".//as:V", namespaces=_ns) or s.findtext("as:LOWER-LIMIT", namespaces=_ns)
                if vt and v and v.lower() != "null":
                    enums[v] = vt

            raw_unit = (cm.findtext(".//as:UNIT-REF", namespaces=_ns) or "").split('/')[-1]
            self.compu_map[cm_name] = {
                'category': cm.findtext("as:CATEGORY", namespaces=_ns),
                'res': res, 'off': off,
                'low_raw': cm.findtext(".//as:LOWER-LIMIT", namespaces=_ns) or "0",
                'upp_raw': cm.findtext(".//as:UPPER-LIMIT", namespaces=_ns) or "0",
                'enums': enums,
                'unit': "\u00b0C" if raw_unit == "X_C" else (raw_unit if raw_unit else "None")
            }

    def _index_signals(self, root):
        _ns = self.ns
        sys_sig_to_cm = {ss.findtext("as:SHORT-NAME", namespaces=_ns):
                         (ss.findtext(".//as:COMPU-METHOD-REF", namespaces=_ns) or "").split('/')[-1]
                         for ss in root.xpath("//as:SYSTEM-SIGNAL", namespaces=_ns)}
        for i_sig in root.xpath("//as:I-SIGNAL", namespaces=_ns):
            name = i_sig.findtext("as:SHORT-NAME", namespaces=_ns)
            if not name or not name.startswith('I'): continue
            cm_ref = i_sig.findtext(".//as:COMPU-METHOD-REF", namespaces=_ns)
            cm_key = cm_ref.split('/')[-1] if cm_ref else sys_sig_to_cm.get((i_sig.findtext(".//as:SYSTEM-SIGNAL-REF", namespaces=_ns) or "").split('/')[-1])
            self.sig_attr_data[name] = {
                'datatype': (i_sig.findtext(".//as:BASE-TYPE-REF", namespaces=_ns) or "").split('/')[-1],
                'db_attr': self.compu_map.get(cm_key, {})
            }

    def _resolve_signals(self, signal_list: List[str]) -> Dict[str, Any]:
        results = {}
        _topo_cache = self._topology_cache
        for sig_name in signal_list:
            pdu_name = self.sig_to_pdu.get(sig_name)
            if not pdu_name:
                results[sig_name] = {"Status": "Missing from Topology", "Attributes": {}, "signal_paths": []}
                continue

            if pdu_name not in _topo_cache:
                _topo_cache[pdu_name] = self._calculate_pdu_paths(pdu_name)

            s_info = self.sig_attr_data.get(sig_name, {})
            db = s_info.get('db_attr', {})
            res, off = db.get('res', 1.0), db.get('off', 0.0)
            low, upp = float(db.get('low_raw', 0) or 0), float(db.get('upp_raw', 0) or 0)

            results[sig_name] = {
                "Status": "Resolved",
                "Attributes": {
                    "periodicity_ms": self.pdu_period_map.get(pdu_name, "N/A"),
                    "Category": db.get('category', 'N/A'),
                    "Base_Type": s_info.get('datatype', 'N/A'),
                    "Unit": db.get('unit', 'None'),
                    "Resolution": res, "Offset": off,
                    "Raw_Limits": {"Min": int(low), "Max": int(upp)},
                    "Phys_Limits": {"Min": (low * res) + off, "Max": (upp * res) + off},
                    "Enums": db.get('enums', {})
                },
                "signal_paths": [
                    {**path, "signal_name": f"{path['can_cluster']}::{path['tx']}::{pdu_name}::{sig_name}"}
                    for path in _topo_cache[pdu_name]
                ]
            }
        return results
