import os
import time
from typing import Any, Dict, List
from lxml import etree
from datetime import timedelta

from signal_parsers.base_parser import BaseParser
from logger import log

class SomeipFFParser(BaseParser):
    """
    Parses SysVarDef.xml into a hierarchical, method-centric JSON structure.
    Structure: Summary, INTERFACES, and GENERAL_SIGNALS.
    Includes IsSigned metadata based on encoding ID.
    """
    
    CLUSTER_TARGET = "IL_EthernetCluster"

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.summary_stats = {}
        self.interfaces = {}
        self.general_signals = {}

    def parse(self) -> Dict[str, Any]:
        """
        Parses the XML and populates hierarchical dictionaries.
        Returns the full nested structure.
        """
        start_time = time.time()
        log.info(f"🚀 Parsing SOME/IP FF XML (Hierarchical Mode): {self.file_path}")
        
        if not os.path.exists(self.file_path):
            log.error(f"❌ File not found: {self.file_path}")
            return {}

        try:
            # Use huge_tree for large SysVar files
            parser = etree.XMLParser(huge_tree=True, recover=True)
            tree = etree.parse(self.file_path, parser)
            root = tree.getroot()

            # Reset internal containers
            self.interfaces = {}
            self.general_signals = {}
            total_vars = [0] 

            self._walk_namespace(root, [], total_vars)

            # --- Fixed Summary Logic ---
            elapsed = str(timedelta(seconds=int(time.time() - start_time))).zfill(8)
            total = total_vars[0]
            
            # In this parser, if a signal is counted, it has been successfully 
            # placed into either INTERFACES or GENERAL_SIGNALS.
            resolved = total 

            self.summary_stats = {
                "Source_File_Name": os.path.basename(self.file_path),
                "Source_File_Size_Bytes": os.path.getsize(self.file_path),
                "Total_Signals_Found": total,
                "Resolved_With_Paths": resolved,
                "No_Path_Found": total - resolved,
                "Interfaces_Found": len(self.interfaces),
                "Processing_Time_HH_MM_SS": elapsed
            }
            # ---------------------------

            # CRITICAL FIX: Explicitly assign the built dictionary to self._parsed_data
            # This ensures BaseParser's to_json_dict() works perfectly during fresh parses.
            self._parsed_data = {
                "Summary": self.summary_stats,
                "INTERFACES": self.interfaces,
                "GENERAL_SIGNALS": self.general_signals
            }
            
            log.info(f"✅ Successfully extracted {total} signals across {len(self.interfaces)} interfaces.")
            return self._parsed_data

        except Exception as e:
            log.error(f"❌ SOME/IP FF Parser failed: {str(e)}")
            return {}

    def _walk_namespace(self, element: etree.Element, path: List[str], count: List[int]):
        """Recursive walk through XML namespaces."""
        for child in element:
            tag = etree.QName(child).localname
            
            if tag == 'namespace':
                name = child.get('name', '')
                self._walk_namespace(child, path + [name] if name else path, count)
            
            elif tag == 'variable':
                # Only count and process if it belongs to our target cluster
                if self.CLUSTER_TARGET not in path:
                    continue
                
                count[0] += 1
                self._process_variable_hierarchical(child, path)

    def _process_variable_hierarchical(self, var_node: etree.Element, path: List[str]):
        """Nests signals into INTERFACES or GENERAL_SIGNALS with bit metadata."""
        var_name = var_node.get('name', '')
        db_name = "::".join(path + [var_name])
        
        role = "PROVIDED" if "PROVIDED_SERVICES" in path else "CONSUMED" if "CONSUMED_SERVICES" in path else "N/A"
        raw_node = path[2] if len(path) > 2 else "GENERAL"
        node_clean = raw_node.replace('N_', '', 1) if raw_node.startswith('N_') else raw_node

        interface_name = "N/A"
        i_type = "GENERAL"
        
        if "METHODS" in path:
            idx = path.index("METHODS")
            if len(path) > idx + 1: interface_name = path[idx + 1]
            i_type = "METHOD"
        elif "EVENTGROUPS" in path or "EVENT_GROUPS" in path:
            marker = "EVENTGROUPS" if "EVENTGROUPS" in path else "EVENT_GROUPS"
            idx = path.index(marker)
            if len(path) > idx + 1: interface_name = path[idx + 1]
            i_type = "EVENT_GROUP"

        raw_encoding = var_node.get('encoding', '65001')
        is_signed = (raw_encoding == "65000")
        
        raw_bitcount = var_node.get('bitcount') or var_node.get('bitlength')
        bit_count = int(raw_bitcount) if raw_bitcount and str(raw_bitcount).isdigit() else 0

        signal_data = {
            "Signal_DB_Name": db_name,
            "DataType": var_node.get('type', "N/A"),
            "BitCount": bit_count,
            "Encoding": raw_encoding,
            "IsSigned": is_signed,
            "ByteOrder": var_node.get('byteOrder', '0'),
            "Enums": self._extract_enums(var_node)
        }

        if i_type != "GENERAL":
            if interface_name not in self.interfaces:
                sif_ns = next((x for x in path if x.startswith("sif_")), "N/A")
                parts = sif_ns.split('_')
                self.interfaces[interface_name] = {
                    "Type": i_type,
                    "SIF": f"{parts[0]}_{parts[1]}" if len(parts) > 1 else sif_ns,
                    "Version": "_".join(parts[2:]) if len(parts) > 2 else "N/A",
                    "NODES": {}
                }
            
            if node_clean not in self.interfaces[interface_name]["NODES"]:
                self.interfaces[interface_name]["NODES"][node_clean] = {
                    "Role": role,
                    "CONTROLS": {},
                    "PARAMETERS": {}
                }
            
            category = "CONTROLS" if "CONTROLS" in path else "PARAMETERS"
            self.interfaces[interface_name]["NODES"][node_clean][category][var_name] = signal_data
        else:
            if node_clean not in self.general_signals:
                self.general_signals[node_clean] = {}
            self.general_signals[node_clean][var_name] = signal_data

    def _extract_enums(self, var_node: etree.Element) -> Dict[str, str]:
        enums = {}
        vt = var_node.find('valuetable')
        if vt is not None:
            for entry in vt.findall('valuetableentry'):
                val = entry.get('value')
                desc = entry.get('description')
                if val is not None:
                    enums[val] = desc
        return enums

