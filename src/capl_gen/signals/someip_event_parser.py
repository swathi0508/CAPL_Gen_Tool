"""
SOME/IP ARXML parser — extracts AUTOSAR service interfaces using lxml.

Why not cantools?
-----------------
cantools is built for CAN DBC / AUTOSAR CAN ARXML.  SOME/IP service
interfaces live in a completely different part of the AUTOSAR metamodel
(SERVICE-INTERFACE, SOMEIP-SERVICE-INSTANCE-TO-MACHINE-MAPPING, etc.).
cantools silently ignores these elements; lxml + XPath gives us direct,
reliable access to the SOME/IP portion of the schema.

AUTOSAR namespace
-----------------
AUTOSAR 4.x ARXML files declare a default namespace::

    xmlns="http://autosar.org/schema/r4.0"   (or r4.1 / r4.2 / r4.3 ...)

The parser detects the namespace at runtime so it works across schema
revisions without hard-coding a version.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from loguru import logger
from lxml import etree

from capl_gen.core.exceptions import ParseError
from capl_gen.schemas.signal import (
    ParsedSomeIPData,
    SomeIPDataElement,
    SomeIPEvent,
    SomeIPField,
    SomeIPMethod,
    SomeIPPrimitive,
    SomeIPServiceInterface,
)
from capl_gen.signals.base_parser import BaseParser
from capl_gen.signals.registry import register

# Mapping from AUTOSAR short names → our SomeIPPrimitive enum.
# Covers the most common base type short names — extend as needed.
_PRIMITIVE_MAP: dict[str, SomeIPPrimitive] = {
    "uint8":   SomeIPPrimitive.UINT8,
    "uint16":  SomeIPPrimitive.UINT16,
    "uint32":  SomeIPPrimitive.UINT32,
    "uint64":  SomeIPPrimitive.UINT64,
    "sint8":   SomeIPPrimitive.SINT8,
    "sint16":  SomeIPPrimitive.SINT16,
    "sint32":  SomeIPPrimitive.SINT32,
    "sint64":  SomeIPPrimitive.SINT64,
    "float32": SomeIPPrimitive.FLOAT32,
    "float64": SomeIPPrimitive.FLOAT64,
    "boolean": SomeIPPrimitive.BOOLEAN,
}


@register
class SomeIPARXMLParser(BaseParser):
    """
    Extracts SOME/IP service interface definitions from AUTOSAR 4.x ARXML files.

    Parsed artefacts per SERVICE-INTERFACE
    ----------------------------------------
    - Service ID  (from SOMEIP-SERVICE-INTERFACE-DEPLOYMENT or heuristic)
    - Major / minor version
    - Events      (VARIABLE-DATA-PROTOTYPES)
    - Methods     (CLIENT-SERVER-OPERATIONS — both R/R and fire-and-forget)
    - Fields      (FIELDS containing getter/setter/notifier declarations)
    """

    signal_type = "SOMEIP_ARXML"
    supported_extensions: tuple[str, ...] = (".arxml", ".xml")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def parse(self) -> ParsedSomeIPData:
        """
        Parse the ARXML file and return a ``ParsedSomeIPData`` model.

        Raises
        ------
        ParseError
            On XML parse failure or unexpected schema structure.
        """
        logger.info(f"Parsing SOME/IP ARXML: {self.file_path}")

        root = self._load_xml()
        ns   = self._detect_namespace(root)
        interfaces = self._extract_interfaces(root, ns)

        result = ParsedSomeIPData(
            source_file=str(self.file_path),
            interfaces=interfaces,
        )

        logger.success(
            f"ARXML parsed — {result.interface_count} interface(s), "
            f"{result.total_events} event(s), "
            f"{result.total_methods} method(s)  [{self.file_name}]"
        )
        return result

    # ------------------------------------------------------------------
    # XML loading
    # ------------------------------------------------------------------

    def _load_xml(self) -> etree._Element:
        try:
            tree = etree.parse(str(self.file_path))
            return tree.getroot()
        except etree.XMLSyntaxError as exc:
            raise ParseError(
                f"ARXML file '{self.file_name}' is not valid XML: {exc}"
            ) from exc
        except Exception as exc:
            raise ParseError(
                f"Could not open ARXML file '{self.file_name}': {exc}"
            ) from exc

    @staticmethod
    def _detect_namespace(root: etree._Element) -> str:
        """
        Extract the AUTOSAR namespace URI from the root element.

        AUTOSAR 4.x uses a versioned namespace:
          http://autosar.org/schema/r4.0   (and r4.1, r4.2, r4.3 …)

        Returns an empty string if the file has no namespace (unusual but handled).
        """
        tag = root.tag  # e.g. "{http://autosar.org/schema/r4.0}AUTOSAR"
        match = re.match(r"\{(.+?)\}", tag)
        ns = match.group(1) if match else ""
        if ns:
            logger.debug(f"Detected AUTOSAR namespace: {ns}")
        else:
            logger.warning("No XML namespace found — XPath queries will use bare tags")
        return ns

    # ------------------------------------------------------------------
    # Interface extraction
    # ------------------------------------------------------------------

    def _extract_interfaces(
        self,
        root: etree._Element,
        ns: str,
    ) -> list[SomeIPServiceInterface]:
        """Walk the ARXML tree and collect all SERVICE-INTERFACE elements."""
        q = self._q  # shorthand
        interfaces: list[SomeIPServiceInterface] = []

        # SERVICE-INTERFACE elements can appear inside any AR-PACKAGE at any depth.
        xpath = f".//{q('SERVICE-INTERFACE', ns)}"
        for svc_elem in root.findall(xpath):
            try:
                iface = self._map_interface(svc_elem, root, ns)
                interfaces.append(iface)
                logger.debug(
                    f"  Interface '{iface.name}' — "
                    f"ID={iface.service_id_hex}, "
                    f"events={len(iface.events)}, "
                    f"methods={len(iface.methods)}, "
                    f"fields={len(iface.fields)}"
                )
            except Exception as exc:
                name = self._short_name(svc_elem, ns) or "<unknown>"
                logger.warning(f"Skipping interface '{name}': {exc}")

        return interfaces

    def _map_interface(
        self,
        elem: etree._Element,
        root: etree._Element,
        ns: str,
    ) -> SomeIPServiceInterface:
        q   = self._q
        name = self._require_short_name(elem, ns)

        # --- Version ---
        version_major, version_minor = self._parse_version(elem, ns)

        # --- Service ID: prefer deployment mapping, fall back to heuristic ---
        service_id = self._resolve_service_id(name, root, ns)

        # --- Events ---
        events   = self._extract_events(elem, ns)
        methods  = self._extract_methods(elem, ns)
        fields   = self._extract_fields(elem, ns)

        return SomeIPServiceInterface(
            name=name,
            service_id=service_id,
            version_major=version_major,
            version_minor=version_minor,
            events=events,
            methods=methods,
            fields=fields,
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _extract_events(
        self, svc_elem: etree._Element, ns: str
    ) -> list[SomeIPEvent]:
        """
        Events live under SERVICE-INTERFACE/EVENTS/VARIABLE-DATA-PROTOTYPE.
        Each prototype is one logical event with typed data elements.
        """
        q = self._q
        events: list[SomeIPEvent] = []
        events_container = svc_elem.find(q("EVENTS", ns))
        if events_container is None:
            return events

        for idx, proto in enumerate(
            events_container.findall(q("VARIABLE-DATA-PROTOTYPE", ns))
        ):
            try:
                name       = self._require_short_name(proto, ns)
                event_id   = idx + 1          # positional fallback; deployment may override
                comment    = self._find_text(proto, q("DESC", ns))
                data_elems = self._extract_data_elements(proto, ns)

                events.append(
                    SomeIPEvent(
                        name=name,
                        event_id=event_id,
                        data_elements=data_elems,
                        comment=comment,
                    )
                )
            except Exception as exc:
                logger.warning(f"  Skipping event at index {idx}: {exc}")

        return events

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def _extract_methods(
        self, svc_elem: etree._Element, ns: str
    ) -> list[SomeIPMethod]:
        """
        Methods live under SERVICE-INTERFACE/METHODS/CLIENT-SERVER-OPERATION.
        Fire-and-forget is indicated by <FIRE-AND-FORGET>true</FIRE-AND-FORGET>.
        """
        q = self._q
        methods: list[SomeIPMethod] = []
        methods_container = svc_elem.find(q("METHODS", ns))
        if methods_container is None:
            return methods

        for idx, op in enumerate(
            methods_container.findall(q("CLIENT-SERVER-OPERATION", ns))
        ):
            try:
                name      = self._require_short_name(op, ns)
                method_id = idx + 1           # positional fallback
                comment   = self._find_text(op, q("DESC", ns))
                faf_text  = self._find_text(op, q("FIRE-AND-FORGET", ns)) or ""
                faf       = faf_text.strip().lower() in ("true", "1")

                in_params  = self._extract_arguments(op, ns, direction="IN")
                out_params = self._extract_arguments(op, ns, direction="OUT")

                methods.append(
                    SomeIPMethod(
                        name=name,
                        method_id=method_id,
                        fire_and_forget=faf,
                        in_params=in_params,
                        out_params=out_params,
                        comment=comment,
                    )
                )
            except Exception as exc:
                logger.warning(f"  Skipping method at index {idx}: {exc}")

        return methods

    def _extract_arguments(
        self,
        op_elem: etree._Element,
        ns: str,
        direction: str,  # "IN" or "OUT"
    ) -> list[SomeIPDataElement]:
        """Parse ARGUMENT-DATA-PROTOTYPEs filtered by their DIRECTION."""
        q      = self._q
        params: list[SomeIPDataElement] = []
        args_container = op_elem.find(q("ARGUMENTS", ns))
        if args_container is None:
            return params

        for arg in args_container.findall(q("ARGUMENT-DATA-PROTOTYPE", ns)):
            dir_text = self._find_text(arg, q("DIRECTION", ns)) or ""
            if dir_text.strip().upper() != direction:
                continue
            try:
                params.append(self._map_data_element(arg, ns))
            except Exception as exc:
                logger.warning(f"  Skipping {direction} arg: {exc}")

        return params

    # ------------------------------------------------------------------
    # Fields
    # ------------------------------------------------------------------

    def _extract_fields(
        self, svc_elem: etree._Element, ns: str
    ) -> list[SomeIPField]:
        """
        Fields live under SERVICE-INTERFACE/FIELDS/FIELD.
        Presence of <GETTER>, <SETTER>, <NOTIFIER> sub-elements indicates
        what access semantics the field supports.
        """
        q = self._q
        fields: list[SomeIPField] = []
        fields_container = svc_elem.find(q("FIELDS", ns))
        if fields_container is None:
            return fields

        for idx, field_elem in enumerate(fields_container.findall(q("FIELD", ns))):
            try:
                name     = self._require_short_name(field_elem, ns)
                field_id = idx + 1
                comment  = self._find_text(field_elem, q("DESC", ns))

                has_getter   = field_elem.find(q("GETTER", ns)) is not None
                has_setter   = field_elem.find(q("SETTER", ns)) is not None
                has_notifier = field_elem.find(q("NOTIFIER", ns)) is not None

                data_el = self._map_data_element(field_elem, ns)

                fields.append(
                    SomeIPField(
                        name=name,
                        field_id=field_id,
                        data_element=data_el,
                        has_getter=has_getter,
                        has_setter=has_setter,
                        has_notifier=has_notifier,
                        comment=comment,
                    )
                )
            except Exception as exc:
                logger.warning(f"  Skipping field at index {idx}: {exc}")

        return fields

    # ------------------------------------------------------------------
    # Data element helpers
    # ------------------------------------------------------------------

    def _extract_data_elements(
        self, parent: etree._Element, ns: str
    ) -> list[SomeIPDataElement]:
        """
        A VARIABLE-DATA-PROTOTYPE IS itself the data element — but it may
        contain an array type.  Return it as a single-item list for consistency
        with the event schema.
        """
        try:
            return [self._map_data_element(parent, ns)]
        except Exception:
            return []

    def _map_data_element(
        self, elem: etree._Element, ns: str
    ) -> SomeIPDataElement:
        q = self._q

        name     = self._require_short_name(elem, ns)
        comment  = self._find_text(elem, q("DESC", ns))
        type_ref = self._resolve_type_ref(elem, ns)

        # Array detection: ARRAY-SIZE or MAX-NUMBER-OF-ELEMENTS hint
        is_array   = False
        array_size: Optional[int] = None
        array_size_elem = elem.find(q("ARRAY-SIZE", ns))
        if array_size_elem is not None and array_size_elem.text:
            is_array = True
            with _suppress_value_error():
                array_size = int(array_size_elem.text.strip())

        primitive = _PRIMITIVE_MAP.get(type_ref.lower(), SomeIPPrimitive.UNKNOWN)

        return SomeIPDataElement(
            name=name,
            type_ref=type_ref,
            primitive=primitive,
            is_array=is_array,
            array_size=array_size,
            comment=comment,
        )

    def _resolve_type_ref(self, elem: etree._Element, ns: str) -> str:
        """
        Extract the type reference short name from the element.

        AUTOSAR uses a TYPE-TREF (an XPATH-like path) or a TYPE-IREF.
        We take the last path segment as the short name.
        """
        q = self._q

        # Try TYPE-TREF first (most common for primitive types)
        type_tref = elem.find(q("TYPE-TREF", ns))
        if type_tref is not None and type_tref.text:
            # e.g. "/AUTOSAR/PlatformTypes/uint32" → "uint32"
            return type_tref.text.strip().split("/")[-1]

        # Try nested TYPE-IREF/TARGET-DATA-PROTOTYPE-REF
        type_iref = elem.find(f".//{q('TARGET-DATA-PROTOTYPE-REF', ns)}")
        if type_iref is not None and type_iref.text:
            return type_iref.text.strip().split("/")[-1]

        return "unknown"

    # ------------------------------------------------------------------
    # Service ID resolution
    # ------------------------------------------------------------------

    def _resolve_service_id(
        self, iface_name: str, root: etree._Element, ns: str
    ) -> int:
        """
        Look up the service ID from a SOMEIP-SERVICE-INTERFACE-DEPLOYMENT.

        AUTOSAR 4.x deployment mappings are separate from the service interface
        definition and linked by name.  If not found, returns a stable hash-
        based placeholder so Pydantic validation still passes.
        """
        q = self._q
        deployment_xpath = (
            f".//{q('SOMEIP-SERVICE-INTERFACE-DEPLOYMENT', ns)}"
        )

        for dep in root.findall(deployment_xpath):
            ref_elem = dep.find(
                f".//{q('SERVICE-INTERFACE-REF', ns)}"
            )
            if ref_elem is None or not ref_elem.text:
                continue

            # The ref path ends with the interface short name
            if ref_elem.text.strip().split("/")[-1] == iface_name:
                sid_elem = dep.find(q("SERVICE-IDENTIFIER", ns))
                if sid_elem is not None and sid_elem.text:
                    with _suppress_value_error():
                        return int(sid_elem.text.strip(), 0)  # handles 0x prefix

        # No deployment mapping found — use a deterministic placeholder
        placeholder = abs(hash(iface_name)) % 0xFFFF
        logger.debug(
            f"No deployment mapping for '{iface_name}' — "
            f"using placeholder ID 0x{placeholder:04X}"
        )
        return placeholder

    # ------------------------------------------------------------------
    # Version parsing
    # ------------------------------------------------------------------

    def _parse_version(
        self, svc_elem: etree._Element, ns: str
    ) -> tuple[int, int]:
        q = self._q
        major, minor = 1, 0

        version_elem = svc_elem.find(q("SERVICE-INTERFACE-VERSION", ns))
        if version_elem is not None:
            major_txt = self._find_text(version_elem, q("MAJOR-VERSION", ns))
            minor_txt = self._find_text(version_elem, q("MINOR-VERSION", ns))
            with _suppress_value_error():
                if major_txt:
                    major = int(major_txt.strip())
            with _suppress_value_error():
                if minor_txt:
                    minor = int(minor_txt.strip())

        return major, minor

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _q(tag: str, ns: str) -> str:
        """Build a namespace-qualified tag: _q('SHORT-NAME', ns) → '{ns}SHORT-NAME'."""
        return f"{{{ns}}}{tag}" if ns else tag

    @staticmethod
    def _short_name(elem: etree._Element, ns: str) -> Optional[str]:
        q_tag = f"{{{ns}}}SHORT-NAME" if ns else "SHORT-NAME"
        sn = elem.find(q_tag)
        return sn.text.strip() if sn is not None and sn.text else None

    def _require_short_name(self, elem: etree._Element, ns: str) -> str:
        name = self._short_name(elem, ns)
        if not name:
            raise ValueError("Element has no SHORT-NAME")
        return name

    @staticmethod
    def _find_text(elem: etree._Element, tag: str) -> Optional[str]:
        child = elem.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return None


# ---------------------------------------------------------------------------
# Small context manager to swallow int() conversion errors cleanly
# ---------------------------------------------------------------------------

from contextlib import contextmanager  # noqa: E402 (after class body)


@contextmanager
def _suppress_value_error():  # type: ignore[misc]
    try:
        yield
    except (ValueError, TypeError):
        pass