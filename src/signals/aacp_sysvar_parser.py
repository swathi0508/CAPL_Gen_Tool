import os
import time
from typing import Any, Dict, List
from lxml import etree
from datetime import timedelta

from signals.base_parser import BaseParser
from core.logger import log

class AacpSysVarParser(BaseParser):
    """
    Parses aacp.vsysvar into a hierarchical structure.
    Output format:
    {
        "Summary": {...},
        "SIGNAL_LIST": {
            "Namespace::Struct": { "member": {...} }
        }
    }
    """

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.parsed_signals = {}

    def parse(self) -> Dict[str, Any]:
        """Parses the vsysvar XML and extracts struct-based signals."""
        start_time = time.time()
        log.info(f"🚀 Parsing AACP SysVar XML: {self.file_path}")
        
        if not os.path.exists(self.file_path):
            log.error(f"❌ File not found: {self.file_path}")
            return {}

        try:
            # Use lxml with huge_tree support for large vsysvar files
            parser = etree.XMLParser(huge_tree=True, recover=True)
            tree = etree.parse(self.file_path, parser)
            root = tree.getroot()

            self.parsed_signals = {}
            total_signals = [0]

            # Start the recursive walk from the root
            self._walk_xml(root, [], total_signals)

            # --- Updated Summary Logic ---
            elapsed = str(timedelta(seconds=int(time.time() - start_time))).zfill(8)
            total = total_signals[0]
            
            # Since these signals are added to the signal_list with full paths, 
            # they are considered resolved.
            resolved = total if self.parsed_signals else 0
            
            self._parsed_data = {
                "Summary": {
                    "Source_File_Name": os.path.basename(self.file_path),
                    "Source_File_Size_Bytes": os.path.getsize(self.file_path),
                    "Total_Signals_Found": total,
                    "Resolved_With_Paths": resolved,
                    "No_Path_Found": total - resolved,
                    "Processing_Time_HH_MM_SS": elapsed
                },
                "SIGNAL_LIST": self.parsed_signals
            }
            # ------------------------------
            
            log.info(f"✅ Successfully extracted {total} signals from AACP vsysvar.")
            return self._parsed_data

        except Exception as e:
            log.error(f"❌ AACP Parser failed: {str(e)}")
            return {}

    def _walk_xml(self, element: etree.Element, path: List[str], count: List[int]):
        """Recursively traverses namespaces and variables/structs."""
        for child in element:
            tag = etree.QName(child).localname
            
            if tag == 'namespace':
                name = child.get('name', '')
                new_path = path + [name] if name else path
                self._walk_xml(child, new_path, count)
            
            elif tag in ['variable', 'struct']:
                name_raw = child.get('name', '')
                clean_name = name_raw.replace('_Struct', '')
                struct_full_path = "::".join(path + [clean_name])
                
                members = child.findall('structMember')
                if members:
                    if struct_full_path not in self.parsed_signals:
                        self.parsed_signals[struct_full_path] = {}

                    for member in members:
                        count[0] += 1
                        self._process_member(member, struct_full_path)

    def _process_member(self, member_node: etree.Element, parent_path: str):
        """Extracts metadata for a single struct member."""
        member_name = member_node.get('name', '')
        db_name = f"{parent_path}.{member_name}"

        raw_encoding = member_node.get('encoding', '65001')
        is_signed = (raw_encoding == "65000")
        bit_count = member_node.get('bitcount')

        signal_metadata = {
            "Signal_DB_Name": db_name,
            "DataType": member_node.get('type', 'int'),
            "BitCount": int(bit_count) if bit_count and bit_count.isdigit() else 0,
            "Encoding": raw_encoding,
            "IsSigned": is_signed,
            "ByteOrder": member_node.get('byteOrder', '0'),
            "Enums": self._extract_enums(member_node)
        }

        self.parsed_signals[parent_path][member_name] = signal_metadata

    def _extract_enums(self, node: etree.Element) -> Dict[str, str]:
        enums = {}
        vt = node.find('valuetable')
        if vt is not None:
            for entry in vt.findall('valuetableentry'):
                val = entry.get('value')
                desc = entry.get('description') or entry.get('name')
                if val is not None:
                    enums[val] = desc
        else:
            for entry in node.findall('enum'):
                val = entry.get('value')
                name = entry.get('name')
                if val is not None:
                    enums[val] = name
        return enums

    def to_json_dict(self) -> Dict[str, Any]:
        return self._parsed_data

    def to_json_file(self, output_path: str, write_allowed: bool = False):
        import json
        if not write_allowed:
            return
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self._parsed_data, f, indent=4)
        except Exception as e:
            log.error(f"❌ Failed to write AACP cache: {e}")