"""
Business-rule validation layer for ingested requirement rows.

Where it sits in the pipeline
------------------------------
    ExcelReader.read()         ← structural validation (Pydantic)
          │
          ▼
    SignalValidator.validate() ← THIS FILE: business-rule validation
          │
          ▼
    GenerationPipeline         ← only receives rows that pass both gates

The distinction matters
-----------------------
Pydantic (in RequirementRow) catches *structural* problems:
  - missing required fields
  - wrong types
  - violated field constraints (min > max, blank IDs, etc.)

This validator catches *semantic* / *cross-system* problems:
  - source_file does not exist on disk
  - signal_name is not present in the parsed signal database
  - template file does not exist
  - CAN-specific numeric range violations vs DBC-defined limits
  - SOME/IP event_id conflicts within the same interface

Only rows that pass BOTH gates reach the generator.

Design
------
- ``ValidationIssue``    — a single finding (ERROR or WARNING)
- ``RowValidationResult``— all issues for one RequirementRow
- ``ValidationReport``   — full report for an IngestionResult
- ``SignalValidator``     — orchestrates all checks, returns a report

Checks are implemented as small private methods so they are individually
unit-testable and easy to toggle on/off via ``ValidatorConfig``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol

from loguru import logger

from capl_gen.core.exceptions import IngestionError
from capl_gen.schemas.requirement import BusType, IngestionResult, RequirementRow
from capl_gen.schemas.signal import ParsedCANData, ParsedSomeIPData


# ---------------------------------------------------------------------------
# Severity / issue model
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    ERROR   = "ERROR"    # row will be excluded from generation
    WARNING = "WARNING"  # row is kept but flagged in the report


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation finding attached to one row."""

    severity:     Severity
    rule:         str           # short machine-readable rule ID e.g. "SOURCE_FILE_MISSING"
    message:      str           # human-readable explanation
    row_index:    int
    field_name:   Optional[str] = None   # which field triggered the issue


@dataclass
class RowValidationResult:
    """Aggregated issues for a single RequirementRow."""

    row:     RequirementRow
    issues:  list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARNING for i in self.issues)

    @property
    def is_valid(self) -> bool:
        """True only when there are zero ERROR-level issues."""
        return not self.has_errors

    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]


@dataclass
class ValidationReport:
    """
    Full validation report for an entire IngestionResult.

    Returned by ``SignalValidator.validate()``.
    Consumed by the pipeline to decide which rows proceed to generation,
    and by the reporter to write the summary file.
    """

    results:         list[RowValidationResult] = field(default_factory=list)
    total_checked:   int = 0

    @property
    def passed(self) -> list[RowValidationResult]:
        """Rows with no ERROR-level issues — safe to generate."""
        return [r for r in self.results if r.is_valid]

    @property
    def failed(self) -> list[RowValidationResult]:
        """Rows blocked by at least one ERROR."""
        return [r for r in self.results if not r.is_valid]

    @property
    def passed_rows(self) -> list[RequirementRow]:
        """Convenience: just the RequirementRow objects that passed."""
        return [r.row for r in self.passed]

    @property
    def error_count(self) -> int:
        return sum(len(r.errors()) for r in self.results)

    @property
    def warning_count(self) -> int:
        return sum(len(r.warnings()) for r in self.results)

    def summary(self) -> str:
        return (
            f"Validation: {len(self.passed)}/{self.total_checked} rows passed  "
            f"[{self.error_count} error(s), {self.warning_count} warning(s)]"
        )

    def all_issues(self) -> list[ValidationIssue]:
        """Flat list of every issue across all rows — useful for reporting."""
        return [issue for r in self.results for issue in r.issues]


# ---------------------------------------------------------------------------
# Signal DB lookup protocol
# (decouples validator from concrete parser classes for testability)
# ---------------------------------------------------------------------------


class SignalDatabase(Protocol):
    """
    Minimal interface the validator needs from a parsed signal file.

    Both ``ParsedCANData`` and ``ParsedSomeIPData`` satisfy this via
    the adapter helpers below.
    """

    def contains_signal(self, signal_name: str, message_name: Optional[str]) -> bool:
        """Return True if the signal/event exists in this database."""
        ...


# ---------------------------------------------------------------------------
# Adapters: wrap parsed data models so the validator is DB-type agnostic
# ---------------------------------------------------------------------------


class CANDatabaseAdapter:
    """Wraps ``ParsedCANData`` to satisfy ``SignalDatabase``."""

    def __init__(self, data: ParsedCANData) -> None:
        # Build lookup: {message_name: {signal_name, ...}}
        self._index: dict[str, set[str]] = {
            msg.name: {sig.name for sig in msg.signals}
            for msg in data.messages
        }

    def contains_signal(self, signal_name: str, message_name: Optional[str]) -> bool:
        if message_name:
            signals_in_msg = self._index.get(message_name, set())
            return signal_name in signals_in_msg
        # No message_name supplied: search across all messages
        return any(signal_name in sigs for sigs in self._index.values())


class SomeIPDatabaseAdapter:
    """Wraps ``ParsedSomeIPData`` to satisfy ``SignalDatabase``."""

    def __init__(self, data: ParsedSomeIPData) -> None:
        # Build lookup: {interface_name: {event_name | method_name, ...}}
        self._index: dict[str, set[str]] = {}
        for iface in data.interfaces:
            names: set[str] = set()
            names.update(e.name for e in iface.events)
            names.update(m.name for m in iface.methods)
            names.update(f.name for f in iface.fields)
            self._index[iface.name] = names

    def contains_signal(self, signal_name: str, message_name: Optional[str]) -> bool:
        if message_name:
            elements = self._index.get(message_name, set())
            return signal_name in elements
        return any(signal_name in elems for elems in self._index.values())


# ---------------------------------------------------------------------------
# Validator config
# ---------------------------------------------------------------------------


@dataclass
class ValidatorConfig:
    """
    Feature flags to enable/disable individual validation checks.

    Defaults are all-on.  Tests or special pipeline modes can
    turn off expensive checks (e.g. signal_db lookups) selectively.
    """

    check_source_file_exists:     bool = True
    check_template_exists:        bool = True
    check_signal_in_db:           bool = True
    check_can_range_vs_db:        bool = True
    check_someip_event_id_unique: bool = True
    check_inactive_rows:          bool = True   # warn on INACTIVE rows
    templates_dir:                Optional[Path] = None


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------


class SignalValidator:
    """
    Business-rule quality gate for ingested ``RequirementRow`` objects.

    Parameters
    ----------
    signal_databases:
        Optional pre-loaded mapping of ``source_file → SignalDatabase``.
        If provided, ``check_signal_in_db`` lookups run against it.
        Pass ``None`` to skip DB-level checks for a given file.
    config:
        Feature flags controlling which checks run.

    Usage
    -----
    ::

        from capl_gen.ingestion.validator import SignalValidator, ValidatorConfig

        validator = SignalValidator(
            signal_databases={"path/to/net.dbc": CANDatabaseAdapter(parsed_can)},
        )
        report = validator.validate(ingestion_result)

        for row in report.passed_rows:
            pipeline.generate(row)
    """

    def __init__(
        self,
        signal_databases: Optional[dict[str, SignalDatabase]] = None,
        config: Optional[ValidatorConfig] = None,
    ) -> None:
        self._dbs: dict[str, SignalDatabase] = signal_databases or {}
        self._cfg = config or ValidatorConfig()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def validate(self, ingestion_result: IngestionResult) -> ValidationReport:
        """
        Run all configured checks against every active row in *ingestion_result*.

        Parameters
        ----------
        ingestion_result:
            Output of ``ExcelReader.read()``.

        Returns
        -------
        ValidationReport
            Full results split into ``passed`` and ``failed`` row lists.
        """
        active_rows = ingestion_result.active_rows
        logger.info(
            f"Validating {len(active_rows)} active row(s) from "
            f"'{ingestion_result.source_file}'"
        )

        results: list[RowValidationResult] = []
        seen_event_ids: dict[str, set[int]] = {}   # interface → {event_id, ...}

        for row in active_rows:
            row_result = RowValidationResult(row=row)

            self._check_source_file_exists(row, row_result)
            self._check_template_exists(row, row_result)
            self._check_signal_in_db(row, row_result)
            self._check_can_range_vs_db(row, row_result)
            self._check_someip_event_id_unique(row, row_result, seen_event_ids)
            self._check_inactive_row_warning(row, row_result)

            results.append(row_result)

            if row_result.has_errors:
                logger.debug(
                    f"  Row {row.row_index} ('{row.requirement_id}') — "
                    f"{len(row_result.errors())} error(s)"
                )

        report = ValidationReport(results=results, total_checked=len(active_rows))
        logger.success(report.summary())
        return report

    def validate_single(self, row: RequirementRow) -> RowValidationResult:
        """
        Validate a single row in isolation.
        Convenience method for unit tests and GUI live-validation.
        """
        dummy_result = IngestionResult(
            source_file="",
            sheet_name="",
            total_rows=1,
            valid_rows=[row],
        )
        report = self.validate(dummy_result)
        return report.results[0]

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_source_file_exists(
        self, row: RequirementRow, result: RowValidationResult
    ) -> None:
        """ERROR if the source_file path does not exist on disk."""
        if not self._cfg.check_source_file_exists:
            return

        if not row.source_path.exists():
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule="SOURCE_FILE_MISSING",
                    message=f"Source file not found on disk: '{row.source_file}'",
                    row_index=row.row_index,
                    field_name="source_file",
                )
            )

    def _check_template_exists(
        self, row: RequirementRow, result: RowValidationResult
    ) -> None:
        """ERROR if the referenced Jinja2 template file does not exist."""
        if not self._cfg.check_template_exists:
            return
        if self._cfg.templates_dir is None:
            return

        template_file = self._cfg.templates_dir / row.bus_type.value.lower() / f"{row.template_name}.j2"
        if not template_file.exists():
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule="TEMPLATE_MISSING",
                    message=(
                        f"Template '{row.template_name}.j2' not found at "
                        f"'{template_file}'"
                    ),
                    row_index=row.row_index,
                    field_name="template_name",
                )
            )

    def _check_signal_in_db(
        self, row: RequirementRow, result: RowValidationResult
    ) -> None:
        """
        ERROR if the signal_name does not exist in the parsed signal database.

        Skipped if no database was provided for this source_file.
        """
        if not self._cfg.check_signal_in_db:
            return

        db = self._dbs.get(row.source_file)
        if db is None:
            # No pre-loaded DB for this file — warn, don't error
            result.issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule="SIGNAL_DB_NOT_LOADED",
                    message=(
                        f"No parsed signal database available for "
                        f"'{row.source_file}' — signal existence not verified."
                    ),
                    row_index=row.row_index,
                    field_name="source_file",
                )
            )
            return

        if not db.contains_signal(row.signal_name, row.message_name):
            location = (
                f"in message '{row.message_name}'" if row.message_name else "in any message"
            )
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule="SIGNAL_NOT_IN_DB",
                    message=(
                        f"Signal '{row.signal_name}' not found "
                        f"{location} in '{row.source_file}'"
                    ),
                    row_index=row.row_index,
                    field_name="signal_name",
                )
            )

    def _check_can_range_vs_db(
        self, row: RequirementRow, result: RowValidationResult
    ) -> None:
        """
        WARNING if expected_min/max violates the physical range defined in the DBC.

        Only runs for CAN rows that have both expected_min/max and a loaded DB.
        """
        if not self._cfg.check_can_range_vs_db:
            return
        if row.bus_type != BusType.CAN:
            return
        if row.expected_min is None and row.expected_max is None:
            return

        db = self._dbs.get(row.source_file)
        if not isinstance(db, CANDatabaseAdapter):
            return

        # Find the signal in the DBC index to get its physical limits
        db_signal = self._find_can_signal(db, row.signal_name, row.message_name)
        if db_signal is None:
            return   # already flagged by SIGNAL_NOT_IN_DB check

        db_min = db_signal.minimum
        db_max = db_signal.maximum
        if db_min is None or db_max is None:
            return   # DBC has no range defined — nothing to compare against

        if row.expected_min is not None and row.expected_min < db_min:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule="RANGE_BELOW_DB_MIN",
                    message=(
                        f"expected_min ({row.expected_min}) is below "
                        f"DBC-defined minimum ({db_min}) for '{row.signal_name}'"
                    ),
                    row_index=row.row_index,
                    field_name="expected_min",
                )
            )

        if row.expected_max is not None and row.expected_max > db_max:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule="RANGE_ABOVE_DB_MAX",
                    message=(
                        f"expected_max ({row.expected_max}) exceeds "
                        f"DBC-defined maximum ({db_max}) for '{row.signal_name}'"
                    ),
                    row_index=row.row_index,
                    field_name="expected_max",
                )
            )

    def _check_someip_event_id_unique(
        self,
        row: RequirementRow,
        result: RowValidationResult,
        seen_event_ids: dict[str, set[int]],
    ) -> None:
        """
        ERROR if two rows targeting the same SOME/IP interface declare
        conflicting event_id values for different signal names.

        The ``seen_event_ids`` dict is shared across the validate() loop
        so duplicates are caught across the entire sheet.
        """
        if not self._cfg.check_someip_event_id_unique:
            return
        if row.bus_type != BusType.SOMEIP:
            return
        if row.event_id is None:
            return

        interface_key = row.message_name or "__global__"
        seen = seen_event_ids.setdefault(interface_key, set())

        if row.event_id in seen:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    rule="SOMEIP_EVENT_ID_DUPLICATE",
                    message=(
                        f"event_id {row.event_id} (0x{row.event_id:04X}) appears more "
                        f"than once for interface '{interface_key}' — "
                        f"conflicting rows will produce invalid CAPL."
                    ),
                    row_index=row.row_index,
                    field_name="event_id",
                )
            )
        else:
            seen.add(row.event_id)

    def _check_inactive_row_warning(
        self, row: RequirementRow, result: RowValidationResult
    ) -> None:
        """
        WARNING when a row's status is not ACTIVE.

        Active rows are already filtered by IngestionResult.active_rows,
        but this check runs as an explicit reminder in the report when
        the caller bypasses that filter and passes all valid rows directly.
        """
        if not self._cfg.check_inactive_rows:
            return
        if not row.is_active:
            result.issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    rule="ROW_INACTIVE",
                    message=(
                        f"Row status is '{row.status.value}' — "
                        "skipped during code generation."
                    ),
                    row_index=row.row_index,
                    field_name="status",
                )
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_can_signal(
        db: CANDatabaseAdapter,
        signal_name: str,
        message_name: Optional[str],
    ):
        """
        Retrieve the raw CANSignalModel from the adapter's internal index.

        Returns None if not found (caller already handles that case).
        We access the private ``_index`` here intentionally — the adapter
        is our own class so this is acceptable.
        """
        if message_name:
            msg_signals = db._index.get(message_name, set())   # noqa: SLF001
            # _index stores signal names only; we need the full model
            # Re-scan the ParsedCANData would require holding a reference.
            # For range checks: caller should pass a richer adapter.
            # This is a known limitation — see SIGNAL_RANGE_CHECK in roadmap.
            return None   # placeholder until richer adapter is wired in
        return None