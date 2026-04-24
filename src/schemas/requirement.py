"""
Pydantic models representing rows from the Excel requirements sheet.

Design intent
-------------
The Excel sheet is the "contract" between the test engineer and the tool.
These models enforce that contract at load time — a missing required column
or a bad value raises a clear error immediately, not halfway through Jinja
rendering.

Row hierarchy
-------------
RequirementRow          ← one row in the sheet
    └── part of IngestionResult
            ├── valid_rows: list[RequirementRow]
            └── invalid_rows: list[InvalidRow]   ← skipped, with reason
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class BusType(str, Enum):
    CAN       = "CAN"
    SOMEIP    = "SOMEIP"
    LIN       = "LIN"       # reserved for future parsers
    FLEXRAY   = "FLEXRAY"   # reserved for future parsers


class RowStatus(str, Enum):
    ACTIVE   = "ACTIVE"      # row should generate code
    INACTIVE = "INACTIVE"    # row is commented-out / disabled
    REVIEW   = "REVIEW"      # flagged for engineer review, skip codegen


# ---------------------------------------------------------------------------
# Core requirement row
# ---------------------------------------------------------------------------


class RequirementRow(BaseModel):
    """
    Represents one validated row from the requirements Excel sheet.

    Field names here are the **internal** canonical names.
    The column_mapper translates whatever the Excel headers say
    into these names before Pydantic ever sees the data.
    """

    # --- Identity ---
    row_index: int = Field(..., description="0-based row index in the sheet (for error reporting)")
    requirement_id: str = Field(..., description="Unique requirement ID, e.g. REQ_001")
    description: Optional[str] = Field(None, description="Human-readable test description")
    status: RowStatus = Field(RowStatus.ACTIVE, description="Whether this row should generate code")

    # --- Signal source ---
    bus_type: BusType = Field(..., description="CAN / SOMEIP / LIN / FLEXRAY")
    signal_name: str = Field(..., description="Signal or event name to test")
    message_name: Optional[str] = Field(None, description="Parent message/interface name (CAN)")
    source_file: str = Field(..., description="Path to the .dbc or .arxml file")

    # --- CAPL generation directives ---
    template_name: str = Field(..., description="Jinja2 template filename to use (without .j2)")
    output_file: Optional[str] = Field(None, description="Override output filename; auto-generated if blank")

    # --- CAN-specific (optional, populated for CAN rows) ---
    expected_min: Optional[float] = Field(None, description="Expected minimum physical value")
    expected_max: Optional[float] = Field(None, description="Expected maximum physical value")
    timeout_ms: Optional[int] = Field(None, ge=0, description="Signal reception timeout in milliseconds")
    cycle_time_ms: Optional[int] = Field(None, ge=0, description="Expected cyclic send time in milliseconds")

    # --- SOME/IP-specific (optional, populated for SOME/IP rows) ---
    event_id: Optional[int] = Field(None, ge=0, description="SOME/IP event/method ID")
    service_version_major: Optional[int] = Field(None, ge=0)
    service_version_minor: Optional[int] = Field(None, ge=0)

    # --- Metadata ---
    author: Optional[str] = Field(None, description="Test author from the sheet")
    tags: list[str] = Field(default_factory=list, description="Comma-separated tags from sheet")

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("requirement_id")
    @classmethod
    def req_id_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("requirement_id must not be blank")
        return v.strip()

    @field_validator("signal_name")
    @classmethod
    def signal_name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("signal_name must not be blank")
        return v.strip()

    @field_validator("source_file")
    @classmethod
    def source_file_has_valid_extension(cls, v: str) -> str:
        ext = Path(v).suffix.lower()
        allowed = {".dbc", ".arxml", ".xml"}
        if ext not in allowed:
            raise ValueError(
                f"source_file extension '{ext}' not in allowed set {allowed}"
            )
        return v.strip()

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v: object) -> list[str]:
        """Accept a raw comma-separated string or an already-split list."""
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t).strip() for t in v if str(t).strip()]
        return []

    @field_validator("status", mode="before")
    @classmethod
    def normalise_status(cls, v: object) -> str:
        if isinstance(v, str):
            return v.strip().upper()
        return v  # let Pydantic handle enum coercion

    @field_validator("bus_type", mode="before")
    @classmethod
    def normalise_bus_type(cls, v: object) -> str:
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @model_validator(mode="after")
    def can_row_must_have_message_name(self) -> "RequirementRow":
        if self.bus_type == BusType.CAN and not self.message_name:
            raise ValueError(
                "message_name is required for CAN rows "
                f"(row {self.row_index}, signal '{self.signal_name}')"
            )
        return self

    @model_validator(mode="after")
    def expected_range_ordering(self) -> "RequirementRow":
        if (
            self.expected_min is not None
            and self.expected_max is not None
            and self.expected_min > self.expected_max
        ):
            raise ValueError(
                f"expected_min ({self.expected_min}) > expected_max ({self.expected_max}) "
                f"at row {self.row_index}"
            )
        return self

    # ------------------------------------------------------------------
    # Convenience helpers used by the generator
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self.status == RowStatus.ACTIVE

    @property
    def source_path(self) -> Path:
        return Path(self.source_file)

    @property
    def resolved_output_file(self) -> str:
        """Return the output filename, auto-generating one if not specified."""
        if self.output_file:
            return self.output_file
        safe_name = self.signal_name.replace(" ", "_").replace("/", "_")
        return f"{safe_name}_{self.template_name}.can"


# ---------------------------------------------------------------------------
# Invalid row — skipped with a reason, kept for reporting
# ---------------------------------------------------------------------------


class InvalidRow(BaseModel):
    """Represents a row that failed validation — preserved for the summary report."""

    row_index: int
    raw_data: dict
    error_message: str


# ---------------------------------------------------------------------------
# Top-level ingestion result
# ---------------------------------------------------------------------------


class IngestionResult(BaseModel):
    """
    Returned by ExcelReader.read() — contains all rows split into
    valid (ready for generation) and invalid (skipped, logged).
    """

    source_file: str
    sheet_name: str
    total_rows: int
    valid_rows: list[RequirementRow] = Field(default_factory=list)
    invalid_rows: list[InvalidRow] = Field(default_factory=list)

    @property
    def valid_count(self) -> int:
        return len(self.valid_rows)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid_rows)

    @property
    def active_rows(self) -> list[RequirementRow]:
        """Rows that are valid AND marked ACTIVE — what the generator consumes."""
        return [r for r in self.valid_rows if r.is_active]

    def summary(self) -> str:
        return (
            f"Ingestion complete: {self.valid_count} valid "
            f"({len(self.active_rows)} active), "
            f"{self.invalid_count} skipped  [{self.source_file}]"
        )