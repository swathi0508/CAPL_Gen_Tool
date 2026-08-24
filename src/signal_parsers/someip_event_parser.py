import math
import os
import re
from typing import Any, Dict, List

from lxml import etree

from logger import log
from signal_parsers.base_parser import BaseParser


class SomeIPEventParser(BaseParser):
    """
    Parses SOME/IP ARXML files to extract signals, Data Types, and Scaling boundaries.
    Constructs exact CAPL routing strings directly from Data Type Mapping Sets
    and Sender-Receiver Interfaces.
    """

    def __init__(self, file_path: str):
        super().__init__(file_path)

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

        # 1. Pre-process Lookup Dictionaries
        compu_methods = self._extract_compu_methods(root)
        app_to_compu = self._extract_app_to_compu(root)
        impl_to_basetype = self._extract_impl_to_basetype(root)
        app_to_basetype = self._extract_app_to_basetype(root, impl_to_basetype)
        records_dict = self._extract_records(root)
        app_to_interface = self._extract_app_to_interface(root)

        def get_compu_data(app_type_name: str) -> Dict[str, Any]:
            compu_name = app_to_compu.get(app_type_name, app_type_name)
            return compu_methods.get(
                compu_name,
                {
                    "enums": {},
                    "has_enums": False,
                    "min": None,
                    "max": None,
                    "mid": None,
                    "unit": "N/A",
                    "factor": "N/A",
                    "offset": "N/A",
                },
            )

        def format_val(v: Any) -> Any:
            if v is None or v == "N/A":
                return "N/A"
            return int(v) if float(v).is_integer() else round(v, 4)

        self._parsed_data = {}

        # 2. Main Mapping Loop (Strict Reconstruction - Records Only)
        for dtms in root.xpath("//*[local-name()='DATA-TYPE-MAPPING-SET']"):
            short_name_elem = dtms.xpath("*[local-name()='SHORT-NAME']")
            if not short_name_elem:
                continue

            mapping_short_name = short_name_elem[0].text.strip()
            # Extract SIF (e.g., 591) and base event name
            match = re.search(r"^X(\d+)_(.*?)SvcProv", mapping_short_name)
            if not match:
                continue

            sif = match.group(1)

            # Loop over individual maps within the SIF
            for dt_map in dtms.xpath(".//*[local-name()='DATA-TYPE-MAP']"):
                app_ref = dt_map.xpath("*[local-name()='APPLICATION-DATA-TYPE-REF']")

                if app_ref and app_ref[0].text:
                    app_name = app_ref[0].text.split("/")[-1].strip()

                    # -----------------------------------------------------
                    # ONLY PROCESS APPLICATION RECORDS (Struct Unrolling)
                    # -----------------------------------------------------
                    if app_name in records_dict:
                        # NEW APPROACH: Look up the exact name from the Interface mapping
                        interface_name = app_to_interface.get(app_name)

                        if interface_name:
                            # ARXML Interface names usually end in "Interface".
                            # We strip it to get the CAPL routing port name (e.g., SomeIpEcoMode)
                            someip_port = re.sub(r"Interface$", "", interface_name)
                            # Extract the event part for your JSON by dropping the "SomeIp" prefix
                            canonical_event_name = re.sub(r"^SomeIp", "", someip_port)
                        else:
                            # FALLBACK: Just in case the ARXML mapping is broken
                            # for a specific signal
                            canonical_event_name = re.sub(r"\d+$", "", app_name)
                            someip_port = f"SomeIp{canonical_event_name}"

                        for element in records_dict[app_name]:
                            elem_name = element["name"]
                            tref = element["tref"]

                            c_data = get_compu_data(tref)
                            datatype = app_to_basetype.get(tref, "N/A")

                            if datatype == "N/A":
                                clean_match = re.match(
                                    r"^(u?s?int(?:8|16|32|64)|float(?:32|64)|boolean|double)",
                                    tref,
                                    re.IGNORECASE,
                                )
                                datatype = clean_match.group(1).lower() if clean_match else "N/A"

                            # Check if enums exist, otherwise default to an empty dictionary
                            enums_dict = c_data["enums"] if c_data["has_enums"] else {}

                            # EXACT RECONSTRUCTION using the ARXML-provided name
                            sig_str = f"EthernetCluster::sif_{sif}::{someip_port}::{elem_name}"

                            self._parsed_data[sig_str] = {
                                "Cluster": "EthernetCluster",
                                "SIF": sif,
                                "Event": canonical_event_name,
                                "Attribute_Value": elem_name,
                                "DataType": datatype,
                                "Enums": enums_dict,
                                "Min": format_val(c_data["min"]),
                                "Mid": format_val(c_data["mid"]),
                                "Max": format_val(c_data["max"]),
                                "Factor": format_val(c_data["factor"]),
                                "Offset": format_val(c_data["offset"]),
                                "Unit": c_data["unit"],
                            }
                    else:
                        # Drop primitives that don't belong to a struct mapping.
                        continue

        log.info(f"✅ Successfully extracted {len(self._parsed_data)} valid SOME/IP signals.")
        return self._parsed_data

    # --- Private Helper Methods ---
    def _extract_compu_methods(self, root) -> Dict[str, Dict]:
        compu_methods = {}
        for cm in root.xpath("//*[local-name()='COMPU-METHOD']"):
            cm_name_elem = cm.xpath("*[local-name()='SHORT-NAME']")
            if not cm_name_elem:
                continue
            cm_name = cm_name_elem[0].text.strip()

            unit_ref = cm.xpath("*[local-name()='UNIT-REF']")
            unit = (
                unit_ref[0].text.split("/")[-1].strip() if unit_ref and unit_ref[0].text else "N/A"
            )

            enums, min_val, max_val, factor, offset = {}, float("inf"), float("-inf"), "N/A", "N/A"

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
                        if ll_f < min_val:
                            min_val = ll_f
                    except ValueError:
                        pass

                if ul_text is not None:
                    try:
                        ul_f = float(ul_text)
                        if ul_f > max_val:
                            max_val = ul_f
                    except ValueError:
                        pass

                if ll_text is not None and vt_node and vt_node[0].text:
                    enums[ll_text] = vt_node[0].text.strip()

                if coeffs_node:
                    try:
                        num_v = coeffs_node[0].xpath(
                            ".//*[local-name()='COMPU-NUMERATOR']/*[local-name()='V']"
                        )
                        den_v = coeffs_node[0].xpath(
                            ".//*[local-name()='COMPU-DENOMINATOR']/*[local-name()='V']"
                        )
                        n0 = float(num_v[0].text) if len(num_v) > 0 else 0.0
                        n1 = float(num_v[1].text) if len(num_v) > 1 else 1.0
                        d = float(den_v[0].text) if len(den_v) > 0 else 1.0
                        if d != 0:
                            offset, factor = n0 / d, n1 / d
                    except Exception:
                        pass

            has_limits = min_val != float("inf") and max_val != float("-inf")
            mid_val = math.floor((min_val + max_val) / 2) if has_limits else None

            compu_methods[cm_name] = {
                "enums": enums,
                "has_enums": len(enums) > 0,
                "min": min_val if has_limits else None,
                "max": max_val if has_limits else None,
                "mid": mid_val,
                "unit": unit,
                "factor": factor,
                "offset": offset,
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

                clean_match = re.match(
                    r"^(u?s?int(?:8|16|32|64)|float(?:32|64)|boolean|double)",
                    basetype_raw,
                    re.IGNORECASE,
                )

                impl_to_basetype[impl_name] = (
                    clean_match.group(1).lower() if clean_match else basetype_raw
                )

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
            if not short_name_elem:
                continue
            rec_name = short_name_elem[0].text.strip()

            elements = []
            for elem in rec.xpath(".//*[local-name()='APPLICATION-RECORD-ELEMENT']"):
                elem_name_node = elem.xpath("*[local-name()='SHORT-NAME']")
                tref_node = elem.xpath("*[local-name()='TYPE-TREF']")
                if elem_name_node and tref_node:
                    elements.append(
                        {
                            "name": elem_name_node[0].text.strip(),
                            "tref": tref_node[0].text.split("/")[-1].strip(),
                        }
                    )
            records_dict[rec_name] = elements
        return records_dict

    def _extract_app_to_interface(self, root) -> Dict[str, str]:
        """Maps Application Data Types to their exact Sender-Receiver Interface names."""
        app_to_interface = {}
        for sr_if in root.xpath("//*[local-name()='SENDER-RECEIVER-INTERFACE']"):
            if_name_elem = sr_if.xpath("*[local-name()='SHORT-NAME']")
            if not if_name_elem:
                continue

            if_name = if_name_elem[0].text.strip()

            # Find the Data Elements pointing to an App Data Type
            for data_elem in sr_if.xpath(".//*[local-name()='VARIABLE-DATA-PROTOTYPE']"):
                tref = data_elem.xpath("*[local-name()='TYPE-TREF']")
                if tref and tref[0].text:
                    app_name = tref[0].text.split("/")[-1].strip()
                    app_to_interface[app_name] = if_name

        return app_to_interface
