from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SignalType(str, Enum):
    CAN_DBC = "CAN_DBC"
    SOMEIP_ARXML = "SOMEIP_ARXML"


class ByteOrder(str, Enum):
    LITTLE_ENDIAN = "little_endian"
    BIG_ENDIAN = "big_endian"


class SomeIPPrimitive(str, Enum):
    """AUTOSAR primitive base types commonly found in ARXML."""
    UINT8 = "uint8"
    UINT16 = "uint16"
    UINT32 = "uint32"
    UINT64 = "uint64"
    SINT8 = "sint8"
    SINT16 = "sint16"
    SINT32 = "sint32"
    SINT64 = "sint64"
    FLOAT32 = "float32"
    FLOAT64 = "float64"
    BOOLEAN = "boolean"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# CAN Models
# ---------------------------------------------------------------------------


class CANSignalModel(BaseModel):
    """Represents a single signal within a CAN message frame."""

    name: str
    start_bit: int = Field(..., ge=0)
    length: int = Field(..., gt=0)
    byte_order: ByteOrder
    is_signed: bool
    factor: float = 1.0
    offset: float = 0.0
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    unit: str = ""
    choices: dict[int, str] = Field(default_factory=dict)  # mux / value table
    comment: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Signal name must not be blank")
        return v.strip()


class CANMessageModel(BaseModel):
    """Represents a complete CAN message (frame) with its signals."""

    name: str
    frame_id: int = Field(..., ge=0)
    frame_id_hex: str = ""            # populated automatically, e.g. "0x1A0"
    length: int = Field(..., ge=1, le=64)  # DLC — up to 64 for CAN-FD
    is_fd: bool = False               # True for CAN-FD frames
    signals: list[CANSignalModel] = Field(default_factory=list)
    comment: Optional[str] = None
    senders: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: object) -> None:  # noqa: ANN001
        if not self.frame_id_hex:
            self.frame_id_hex = f"0x{self.frame_id:03X}"


class ParsedCANData(BaseModel):
    """Top-level container returned by CANDBCParser.parse()."""

    signal_type: SignalType = SignalType.CAN_DBC
    source_file: str
    messages: list[CANMessageModel] = Field(default_factory=list)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def signal_count(self) -> int:
        return sum(len(m.signals) for m in self.messages)


# ---------------------------------------------------------------------------
# SOME/IP Models
# ---------------------------------------------------------------------------


class SomeIPDataElement(BaseModel):
    """A typed data element — used in events, method in/out params, fields."""

    name: str
    type_ref: str                        # raw AUTOSAR type-ref short name
    primitive: SomeIPPrimitive = SomeIPPrimitive.UNKNOWN
    is_array: bool = False
    array_size: Optional[int] = None     # None = dynamic length
    comment: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Data element name must not be blank")
        return v.strip()


class SomeIPEvent(BaseModel):
    """A SOME/IP event (fire-and-forget, producer → consumer)."""

    name: str
    event_id: int = Field(..., ge=0)
    event_id_hex: str = ""
    data_elements: list[SomeIPDataElement] = Field(default_factory=list)
    comment: Optional[str] = None

    def model_post_init(self, __context: object) -> None:  # noqa: ANN001
        if not self.event_id_hex:
            self.event_id_hex = f"0x{self.event_id:04X}"


class SomeIPMethod(BaseModel):
    """A SOME/IP method (request/response or fire-and-forget)."""

    name: str
    method_id: int = Field(..., ge=0)
    method_id_hex: str = ""
    fire_and_forget: bool = False
    in_params: list[SomeIPDataElement] = Field(default_factory=list)
    out_params: list[SomeIPDataElement] = Field(default_factory=list)
    comment: Optional[str] = None

    def model_post_init(self, __context: object) -> None:  # noqa: ANN001
        if not self.method_id_hex:
            self.method_id_hex = f"0x{self.method_id:04X}"


class SomeIPField(BaseModel):
    """A SOME/IP field — has getter/setter/notifier semantics."""

    name: str
    field_id: int = Field(..., ge=0)
    data_element: SomeIPDataElement
    has_getter: bool = True
    has_setter: bool = False
    has_notifier: bool = False
    comment: Optional[str] = None


class SomeIPServiceInterface(BaseModel):
    """Represents one SERVICE-INTERFACE block from the ARXML."""

    name: str
    service_id: int = Field(..., ge=0)
    service_id_hex: str = ""
    version_major: int = 1
    version_minor: int = 0
    events: list[SomeIPEvent] = Field(default_factory=list)
    methods: list[SomeIPMethod] = Field(default_factory=list)
    fields: list[SomeIPField] = Field(default_factory=list)

    def model_post_init(self, __context: object) -> None:  # noqa: ANN001
        if not self.service_id_hex:
            self.service_id_hex = f"0x{self.service_id:04X}"


class ParsedSomeIPData(BaseModel):
    """Top-level container returned by SomeIPARXMLParser.parse()."""

    signal_type: SignalType = SignalType.SOMEIP_ARXML
    source_file: str
    interfaces: list[SomeIPServiceInterface] = Field(default_factory=list)

    @property
    def interface_count(self) -> int:
        return len(self.interfaces)

    @property
    def total_events(self) -> int:
        return sum(len(i.events) for i in self.interfaces)

    @property
    def total_methods(self) -> int:
        return sum(len(i.methods) for i in self.interfaces)