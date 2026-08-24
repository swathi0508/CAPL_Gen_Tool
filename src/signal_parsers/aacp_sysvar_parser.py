import os
import time
from datetime import timedelta
from typing import Any, Dict, List

from lxml import etree

from logger import log
from signal_parsers.base_parser import BaseParser


class AacpSysVarParser(BaseParser):
    """
    Parses aacp.vsysvar into a deeply nested hierarchical structure.
    """

    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.parsed_signals = {}
        # Stores lookup layouts for structural references found during pass 1
        self.struct_definitions: Dict[str, etree.Element] = {}

    def parse(self) -> Dict[str, Any]:
        """Parses the vsysvar XML, caches structures, and builds nested variable trees."""
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
            self.struct_definitions = {}
            total_signals = [0]

            # Pass 1: Build a template map of all struct layouts globally by their definitions
            log.info("📋 Pass 1: Caching structural blueprints...")
            self._cache_struct_definitions(root, [])

            # Pass 2: Map active system variables, nesting sub-struct dictionaries inline
            log.info("🔧 Pass 2: Processing and nesting data types...")
            self._process_variables(root, [], total_signals)

            # --- Summary Logic ---
            elapsed = str(timedelta(seconds=int(time.time() - start_time))).zfill(8)
            total = total_signals[0]
            resolved = total if self.parsed_signals else 0

            # CRITICAL FIX: Explicitly assign to self._parsed_data using a unique key
            self._parsed_data = {
                "Summary": {
                    "Source_File_Name": os.path.basename(self.file_path),
                    "Source_File_Size_Bytes": os.path.getsize(self.file_path),
                    "Total_Signals_Found": total,
                    "Resolved_With_Paths": resolved,
                    "No_Path_Found": total - resolved,
                    "Processing_Time_HH_MM_SS": elapsed
                },
                "AACP_TREE": self.parsed_signals
            }

            log.info(f"✅ Successfully extracted {total} signals into nested keys.")
            return self._parsed_data

        except Exception as e:
            log.error(f"❌ AACP Parser failed: {str(e)}")
            import traceback
            log.error(traceback.format_exc())
            return {}

    def _cache_struct_definitions(self, element: etree.Element, current_ns: List[str]):
        """Collects standalone struct declarations to use as type templates."""
        for child in element:
            tag = etree.QName(child).localname

            if tag == 'namespace':
                name = child.get('name', '')
                new_ns = current_ns + [name] if name else current_ns
                self._cache_struct_definitions(child, new_ns)

            elif tag == 'struct':
                name_raw = child.get('name', '')
                full_struct_key = "::".join(current_ns + [name_raw])
                self.struct_definitions[full_struct_key] = child

    def _process_variables(self, element: etree.Element, current_ns: List[str], count: List[int]):
        """Processes actual active system variable instantiations."""
        for child in element:
            tag = etree.QName(child).localname

            if tag == 'namespace':
                name = child.get('name', '')
                new_ns = current_ns + [name] if name else current_ns
                self._process_variables(child, new_ns, count)

            elif tag == 'variable':
                var_name = child.get('name', '')
                var_type = child.get('type', '')
                var_full_path = "::".join(current_ns + [var_name])

                if var_full_path not in self.parsed_signals:
                    self.parsed_signals[var_full_path] = {}

                # Top-level dictionary block context
                current_container = self.parsed_signals[var_full_path]

                if var_type == 'struct':
                    struct_def = child.get('structDefinition', '')
                    if struct_def in self.struct_definitions:
                        struct_node = self.struct_definitions[struct_def]
                        # Track the absolute variable path separately for Signal_DB_Name construction
                        self._resolve_struct_nested(struct_node, current_container, var_full_path, count)
                else:
                    # Flat standalone variables
                    count[0] += 1
                    self._parse_primitive_metadata(child, current_container, var_name, var_full_path)

    def _resolve_struct_nested(self, struct_node: etree.Element, current_container: Dict[str, Any], current_db_path: str, count: List[int]):
        """
        Recursively steps through structural templates.
        Creates inline sub-dictionaries for nested structures, ensuring Signal_DB_Name preserves dots.
        """
        for member in struct_node.findall('structMember'):
            member_name = member.get('name', '')
            member_type = member.get('type', '')

            # The exact dot-notated string track needed for "Signal_DB_Name"
            next_db_path = f"{current_db_path}.{member_name}"

            if member_type == 'struct':
                struct_def = member.get('structDefinition', '')
                if struct_def in self.struct_definitions:
                    nested_struct_node = self.struct_definitions[struct_def]

                    # Create a sub-dictionary block for this inner structure if it doesn't exist yet
                    if member_name not in current_container:
                        current_container[member_name] = {}

                    # Pass the nested inner dictionary downstream to hold its children
                    self._resolve_struct_nested(nested_struct_node, current_container[member_name], next_db_path, count)
            else:
                # Leaf primitive node reached
                count[0] += 1
                self._parse_primitive_metadata(member, current_container, member_name, next_db_path)

    def _parse_primitive_metadata(self, node: etree.Element, target_dict: Dict[str, Any], field_name: str, complete_db_path: str):
        """Builds schema values and places them into the current active container."""
        raw_encoding = node.get('encoding', '65001')
        is_signed = (raw_encoding == "65000")
        bit_count = node.get('bitcount')

        target_dict[field_name] = {
            "Signal_DB_Name": complete_db_path,
            "DataType": node.get('type', 'int'),
            "BitCount": int(bit_count) if bit_count and bit_count.isdigit() else 0,
            "Encoding": raw_encoding,
            "IsSigned": is_signed,
            "ByteOrder": node.get('byteOrder', '0'),
            "Enums": self._extract_enums(node)
        }

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
