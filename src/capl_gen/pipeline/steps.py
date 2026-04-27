"""
Discrete pipeline step classes.

Each step:
  1. Reads what it needs from ``PipelineContext``.
  2. Does one focused piece of work.
  3. Writes its output back into the context.
  4. Returns the (mutated) context so the pipeline can chain steps.

Adding a new step
-----------------
Subclass ``BaseStep``, implement ``execute()``, and call
``pipeline.add_step(MyNewStep(...))`` — nothing else changes.

Step catalogue
--------------
IngestStep          Reads the Excel sheet → IngestionResult
ParseSignalsStep    Parses unique source files → signal_databases
ValidateStep        Business-rule validation → validated_rows / rejected_rows
RenderStep          Jinja2 rendering → rendered_outputs
WriteStep           Writes .can files → written_files
"""
from __future__ import annotations

import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from loguru import logger

from capl_gen.core.exceptions import (
    CAPLGenError,
    IngestionError,
    ParseError,
    TemplateRenderError,
    OutputWriteError,
)
from capl_gen.ingestion.excel_reader import ExcelReader
from capl_gen.ingestion.validator import (
    CANDatabaseAdapter,
    SignalValidator,
    SomeIPDatabaseAdapter,
    ValidatorConfig,
)
from capl_gen.pipeline.context import PipelineContext, ParsedSignalDB
from capl_gen.schemas.requirement import RequirementRow
from capl_gen.schemas.signal import ParsedCANData, ParsedSomeIPData
from capl_gen.signals.registry import get_parser


# ---------------------------------------------------------------------------
# Abstract base step
# ---------------------------------------------------------------------------


class BaseStep(ABC):
    """
    Contract for all pipeline steps.

    Subclasses implement ``execute()`` and should:
    - Raise ``CAPLGenError`` subclasses on unrecoverable failures.
    - Log progress at DEBUG/INFO level using loguru.
    - Never raise bare ``Exception`` — wrap in the appropriate typed error.
    """

    @property
    def name(self) -> str:
        """Human-readable step name used in logging and timing reports."""
        return self.__class__.__name__

    @abstractmethod
    def execute(self, ctx: PipelineContext) -> PipelineContext:
        """
        Run the step against the shared context.

        Parameters
        ----------
        ctx:
            Current pipeline context — read inputs, write outputs here.

        Returns
        -------
        PipelineContext
            The same context object (mutated in-place and returned for
            fluent chaining).
        """


# ---------------------------------------------------------------------------
# Step 1 — Ingest
# ---------------------------------------------------------------------------


class IngestStep(BaseStep):
    """
    Reads the requirements Excel sheet and populates ``ctx.ingestion_result``.

    Internally uses ``ExcelReader`` (which applies ``ColumnMapper`` and
    Pydantic validation per row).

    After this step
    ---------------
    ``ctx.ingestion_result``  is set.
    ``ctx.ingestion_result.active_rows``  are the rows ready for parsing.

    Parameters
    ----------
    sheet_name:
        Override the sheet to read (default: use ``ctx.sheet_name``).
    header_row:
        0-based index of the header row in the sheet (default 0).
    """

    def __init__(
        self,
        sheet_name: Optional[str | int] = None,
        header_row: int = 0,
    ) -> None:
        self._sheet_name_override = sheet_name
        self._header_row = header_row

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        sheet = self._sheet_name_override if self._sheet_name_override is not None else ctx.sheet_name
        logger.info(f"[{self.name}] Reading '{ctx.excel_path.name}'  sheet='{sheet}'")

        try:
            reader = ExcelReader(
                file_path=ctx.excel_path,
                sheet_name=sheet,
                header_row=self._header_row,
            )
            ctx.ingestion_result = reader.read()

        except FileNotFoundError as exc:
            raise IngestionError(
                f"Excel file not found: {ctx.excel_path}"
            ) from exc
        except IngestionError:
            raise
        except Exception as exc:
            raise IngestionError(
                f"Unexpected error reading Excel file: {exc}\n"
                f"{traceback.format_exc()}"
            ) from exc

        result = ctx.ingestion_result
        logger.info(
            f"[{self.name}] Done — {result.valid_count} valid rows, "
            f"{result.invalid_count} skipped, "
            f"{len(result.active_rows)} active"
        )
        return ctx


# ---------------------------------------------------------------------------
# Step 2 — Parse signals
# ---------------------------------------------------------------------------


class ParseSignalsStep(BaseStep):
    """
    Parses every unique source file referenced by active rows.

    Uses the signal registry (``get_parser``) so it automatically
    handles DBC and ARXML without any ``if/elif`` logic.

    After this step
    ---------------
    ``ctx.signal_databases``  maps ``str(resolved_path) → ParsedCANData | ParsedSomeIPData``.

    Behaviour on partial failure
    ----------------------------
    If one source file fails to parse, the error is logged as a warning
    and that file's rows are excluded from ``ctx.validated_rows`` during
    the subsequent ValidateStep.  The pipeline continues with all other files.

    Parameters
    ----------
    fail_fast:
        If True, any parse error aborts the entire pipeline immediately.
        Default False (lenient — skip bad files, continue with the rest).
    """

    def __init__(self, fail_fast: bool = False) -> None:
        self._fail_fast = fail_fast

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.ingestion_result is None:
            raise IngestionError(
                f"[{self.name}] IngestStep must run before ParseSignalsStep."
            )

        active_rows = ctx.ingestion_result.active_rows
        if not active_rows:
            logger.warning(f"[{self.name}] No active rows to parse — skipping.")
            return ctx

        # Collect unique (source_file, bus_type) pairs so each file is parsed once
        unique_sources = self._collect_unique_sources(active_rows)
        logger.info(
            f"[{self.name}] Parsing {len(unique_sources)} unique source file(s)"
        )

        failed_sources: set[str] = set()

        for source_file, signal_type in unique_sources.items():
            resolved_path = str(Path(source_file).resolve())
            logger.info(f"[{self.name}]  → [{signal_type}] {source_file}")

            try:
                parser = get_parser(signal_type, source_file)
                parsed: ParsedSignalDB = parser.parse()
                ctx.signal_databases[resolved_path] = parsed
                self._log_parse_summary(parsed)

            except (FileNotFoundError, ValueError, KeyError) as exc:
                msg = f"Cannot parse '{source_file}': {exc}"
                if self._fail_fast:
                    raise ParseError(msg) from exc
                logger.warning(f"[{self.name}] SKIPPED — {msg}")
                failed_sources.add(resolved_path)

            except ParseError as exc:
                if self._fail_fast:
                    raise
                logger.warning(f"[{self.name}] SKIPPED — ParseError: {exc}")
                failed_sources.add(resolved_path)

            except Exception as exc:
                msg = f"Unexpected error parsing '{source_file}': {exc}"
                if self._fail_fast:
                    raise ParseError(msg) from exc
                logger.warning(f"[{self.name}] SKIPPED — {msg}")
                failed_sources.add(resolved_path)

        successful = len(ctx.signal_databases)
        logger.info(
            f"[{self.name}] Done — {successful}/{len(unique_sources)} file(s) parsed"
        )

        if failed_sources:
            logger.warning(
                f"[{self.name}] {len(failed_sources)} source file(s) failed — "
                "affected rows will be excluded by ValidateStep."
            )

        return ctx

    @staticmethod
    def _collect_unique_sources(rows: list[RequirementRow]) -> dict[str, str]:
        """
        Return ``{source_file: signal_type}`` for all unique source files.

        signal_type is derived from ``BusType``:
            CAN    → "CAN_DBC"
            SOMEIP → "SOMEIP_ARXML"
        """
        _BUS_TO_SIGNAL_TYPE = {
            "CAN":    "CAN_DBC",
            "SOMEIP": "SOMEIP_ARXML",
        }
        seen: dict[str, str] = {}
        for row in rows:
            if row.source_file not in seen:
                signal_type = _BUS_TO_SIGNAL_TYPE.get(row.bus_type.value)
                if signal_type is None:
                    logger.warning(
                        f"No parser registered for bus_type='{row.bus_type.value}' "
                        f"(row {row.row_index}, signal '{row.signal_name}') — skipping."
                    )
                    continue
                seen[row.source_file] = signal_type
        return seen

    @staticmethod
    def _log_parse_summary(parsed: ParsedSignalDB) -> None:
        """Log a type-appropriate one-liner after a successful parse."""
        if isinstance(parsed, ParsedCANData):
            logger.debug(
                f"     CAN: {parsed.message_count} messages, "
                f"{parsed.signal_count} signals"
            )
        elif isinstance(parsed, ParsedSomeIPData):
            logger.debug(
                f"     SOME/IP: {parsed.interface_count} interface(s), "
                f"{parsed.total_events} event(s), "
                f"{parsed.total_methods} method(s)"
            )


# ---------------------------------------------------------------------------
# Step 3 — Validate
# ---------------------------------------------------------------------------


class ValidateStep(BaseStep):
    """
    Runs business-rule validation and splits rows into
    ``ctx.validated_rows`` (passed) and ``ctx.rejected_rows`` (blocked).

    Builds ``SignalDatabase`` adapters from whatever is in
    ``ctx.signal_databases`` automatically — no manual wiring needed.

    After this step
    ---------------
    ``ctx.validated_rows``  ← rows safe to pass to RenderStep.
    ``ctx.rejected_rows``   ← rows blocked by ≥1 ERROR-level issue.

    Parameters
    ----------
    validator_config:
        Feature flags to enable/disable individual checks.
        Defaults to all checks enabled, using ``ctx.templates_dir``.
    """

    def __init__(self, validator_config: Optional[ValidatorConfig] = None) -> None:
        self._config_override = validator_config

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.ingestion_result is None:
            raise IngestionError(
                f"[{self.name}] IngestStep must run before ValidateStep."
            )

        active_rows = ctx.ingestion_result.active_rows
        if not active_rows:
            logger.warning(f"[{self.name}] No active rows to validate.")
            return ctx

        logger.info(f"[{self.name}] Validating {len(active_rows)} active row(s)")

        # Build config — inject templates_dir from context unless overridden
        config = self._config_override or ValidatorConfig(
            templates_dir=ctx.templates_dir if ctx.templates_dir != Path() else None,
        )

        # Build signal database adapters from whatever ParseSignalsStep loaded
        adapters = self._build_adapters(ctx)

        validator = SignalValidator(signal_databases=adapters, config=config)
        report = validator.validate(ctx.ingestion_result)

        ctx.validated_rows = report.passed_rows
        ctx.rejected_rows  = [r.row for r in report.failed]

        logger.info(
            f"[{self.name}] Done — "
            f"{len(ctx.validated_rows)} passed, "
            f"{len(ctx.rejected_rows)} rejected  "
            f"[{report.error_count} error(s), {report.warning_count} warning(s)]"
        )

        if ctx.rejected_rows:
            for row_result in report.failed:
                for issue in row_result.errors():
                    logger.warning(
                        f"[{self.name}]   Row {issue.row_index} "
                        f"[{issue.rule}]: {issue.message}"
                    )

        return ctx

    @staticmethod
    def _build_adapters(ctx: PipelineContext) -> dict:
        """
        Wrap each parsed DB in the appropriate adapter expected by SignalValidator.

        The validator keys adapters by the *original* source_file string from
        RequirementRow, so we need to reverse-map from resolved path back to
        the original paths that rows reference.
        """
        from capl_gen.ingestion.validator import CANDatabaseAdapter, SomeIPDatabaseAdapter

        adapters = {}

        for resolved_path_str, parsed in ctx.signal_databases.items():
            if isinstance(parsed, ParsedCANData):
                adapter = CANDatabaseAdapter(parsed)
            elif isinstance(parsed, ParsedSomeIPData):
                adapter = SomeIPDatabaseAdapter(parsed)
            else:
                logger.warning(
                    f"[ValidateStep] No adapter for type {type(parsed).__name__} — skipping."
                )
                continue

            # The validator looks up by the raw source_file string from RequirementRow.
            # Map both the resolved path AND the original path so either works.
            adapters[resolved_path_str] = adapter
            # Also key by original (non-resolved) paths used in rows
            for source_file in (parsed.source_file,):
                adapters[source_file] = adapter

        logger.debug(f"[ValidateStep] Built {len(adapters)} signal DB adapter(s)")
        return adapters


# ---------------------------------------------------------------------------
# Step 4 — Render
# ---------------------------------------------------------------------------


class RenderStep(BaseStep):
    """
    Renders Jinja2 templates for each validated row and populates
    ``ctx.rendered_outputs``.

    Template lookup
    ---------------
    Templates are resolved relative to ``ctx.templates_dir``::

        {templates_dir}/{bus_type_lower}/{template_name}.j2

    e.g. ``templates/can/rx_signal_check.j2``

    Template context (variables available inside .j2 files)
    --------------------------------------------------------
    ``row``        RequirementRow (all fields accessible)
    ``signal_db``  ParsedCANData | ParsedSomeIPData for this row's source_file
    ``meta``       dict with tool version, timestamp, source_excel filename

    After this step
    ---------------
    ``ctx.rendered_outputs``  maps requirement_id → CAPL source string.
    ``ctx.render_errors``     maps requirement_id → error message (rows that failed).

    Parameters
    ----------
    fail_fast:
        Abort on first render failure.  Default False.
    extra_globals:
        Extra variables injected into every template's render context.
    """

    def __init__(
        self,
        fail_fast: bool = False,
        extra_globals: Optional[dict] = None,
    ) -> None:
        self._fail_fast   = fail_fast
        self._extra_globals = extra_globals or {}

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.validated_rows:
            logger.warning(f"[{self.name}] No validated rows to render — skipping.")
            return ctx

        logger.info(
            f"[{self.name}] Rendering {len(ctx.validated_rows)} row(s) "
            f"from '{ctx.templates_dir}'"
        )

        env = self._build_jinja_env(ctx.templates_dir)
        meta = self._build_meta(ctx)

        for row in ctx.validated_rows:
            try:
                rendered = self._render_row(row, ctx, env, meta)
                ctx.rendered_outputs[row.requirement_id] = rendered
                logger.debug(
                    f"[{self.name}]  ✓  {row.requirement_id}  "
                    f"({row.signal_name} → {row.template_name})"
                )
            except TemplateRenderError as exc:
                error_msg = str(exc)
                ctx.render_errors[row.requirement_id] = error_msg
                logger.warning(
                    f"[{self.name}]  ✗  {row.requirement_id}: {error_msg}"
                )
                if self._fail_fast:
                    raise

        logger.info(
            f"[{self.name}] Done — "
            f"{len(ctx.rendered_outputs)} rendered, "
            f"{len(ctx.render_errors)} failed"
        )
        return ctx

    def _build_jinja_env(self, templates_dir: Path):
        """Build and configure the Jinja2 Environment."""
        from jinja2 import Environment, FileSystemLoader, StrictUndefined

        if not templates_dir.exists():
            raise TemplateRenderError(
                f"Templates directory not found: '{templates_dir}'"
            )

        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            # StrictUndefined raises immediately on any undefined variable
            # instead of silently rendering empty strings into CAPL code.
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        # Register custom filters (add capl_gen.generator.filters when ready)
        env.filters["hex"] = lambda v: f"0x{int(v):X}"
        env.globals.update(self._extra_globals)

        return env

    def _render_row(self, row: RequirementRow, ctx: PipelineContext, env, meta: dict) -> str:
        """Resolve template path, build context dict, and render."""
        from jinja2 import TemplateNotFound, UndefinedError

        template_path = f"{row.bus_type.value.lower()}/{row.template_name}.j2"

        try:
            template = env.get_template(template_path)
        except TemplateNotFound:
            raise TemplateRenderError(
                f"Template not found: '{template_path}' "
                f"(templates_dir='{ctx.templates_dir}')"
            )

        signal_db = ctx.get_db_for_row(row)

        render_ctx = {
            "row":       row,
            "signal_db": signal_db,
            "meta":      meta,
        }

        try:
            return template.render(**render_ctx)
        except UndefinedError as exc:
            raise TemplateRenderError(
                f"Undefined variable in template '{template_path}': {exc}"
            )
        except Exception as exc:
            raise TemplateRenderError(
                f"Rendering '{template_path}' failed for row "
                f"'{row.requirement_id}': {exc}"
            )

    @staticmethod
    def _build_meta(ctx: PipelineContext) -> dict:
        """Build the ``meta`` dict injected into every template."""
        import datetime
        return {
            "tool_name":    "CAPL Gen Tool",
            "tool_version": "0.0.1",
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_excel": ctx.excel_path.name,
        }


# ---------------------------------------------------------------------------
# Step 5 — Write
# ---------------------------------------------------------------------------


class WriteStep(BaseStep):
    """
    Writes rendered CAPL strings to ``.can`` files in ``ctx.output_dir``.

    Directory structure under output_dir
    -------------------------------------
    Files are grouped by bus type::

        output_dir/
            can/
                SignalA_rx_check.can
                SignalB_rx_check.can
            someip/
                EventX_handler.can

    After this step
    ---------------
    ``ctx.written_files``  maps requirement_id → absolute Path of written file.
    ``ctx.write_errors``   maps requirement_id → error message.

    Parameters
    ----------
    fail_fast:
        Abort on first write failure.  Default False.
    overwrite:
        If False, existing files are not overwritten and a warning is logged.
        Default True.
    """

    def __init__(self, fail_fast: bool = False, overwrite: bool = True) -> None:
        self._fail_fast  = fail_fast
        self._overwrite  = overwrite

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.rendered_outputs:
            logger.warning(f"[{self.name}] No rendered outputs to write — skipping.")
            return ctx

        if ctx.dry_run:
            logger.info(
                f"[{self.name}] DRY RUN — skipping {len(ctx.rendered_outputs)} file write(s)"
            )
            return ctx

        logger.info(
            f"[{self.name}] Writing {len(ctx.rendered_outputs)} file(s) "
            f"to '{ctx.output_dir}'"
        )

        ctx.output_dir.mkdir(parents=True, exist_ok=True)

        # Build a lookup so we can find the row for each requirement_id
        row_map: dict[str, RequirementRow] = {
            r.requirement_id: r for r in ctx.validated_rows
        }

        for req_id, capl_source in ctx.rendered_outputs.items():
            row = row_map.get(req_id)
            if row is None:
                logger.warning(
                    f"[{self.name}] No matching row for requirement_id='{req_id}' — skipping write."
                )
                continue

            try:
                out_path = self._resolve_output_path(ctx.output_dir, row)
                self._write_file(out_path, capl_source, req_id)
                ctx.written_files[req_id] = out_path

            except OutputWriteError as exc:
                ctx.write_errors[req_id] = str(exc)
                logger.warning(f"[{self.name}]  ✗  {req_id}: {exc}")
                if self._fail_fast:
                    raise

        logger.info(
            f"[{self.name}] Done — "
            f"{len(ctx.written_files)} written, "
            f"{len(ctx.write_errors)} failed"
        )
        return ctx

    def _resolve_output_path(self, output_dir: Path, row: RequirementRow) -> Path:
        """Build the output file path from the row's bus type and filename."""
        sub_dir = output_dir / row.bus_type.value.lower()
        sub_dir.mkdir(parents=True, exist_ok=True)
        return sub_dir / row.resolved_output_file

    def _write_file(self, path: Path, content: str, req_id: str) -> None:
        """Write content to path, respecting overwrite flag."""
        if path.exists() and not self._overwrite:
            logger.warning(
                f"[{self.name}]  SKIP (exists)  {path.name}  [{req_id}]"
            )
            return

        try:
            path.write_text(content, encoding="utf-8")
            logger.debug(f"[{self.name}]  ✓  {path}  [{req_id}]")
        except OSError as exc:
            raise OutputWriteError(
                f"Failed to write '{path}' for requirement '{req_id}': {exc}"
            ) from exc