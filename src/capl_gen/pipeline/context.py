"""
PipelineContext — the single shared state object that flows through
every pipeline step.

Design rationale
----------------
Steps communicate exclusively through the context — they never call
each other directly. This means:

  - Each step is independently unit-testable by pre-populating only
    the context fields it reads.
  - Steps are reorderable / replaceable without ripple changes.
  - The full pipeline state is inspectable at any point (GUI progress,
    logging, error recovery).

Immutability contract
---------------------
Steps APPEND to lists and ASSIGN to None fields — they never mutate
data produced by a previous step. If a step needs to filter rows, it
writes a new list to a different field (e.g. ValidateStep writes
``validated_rows``, it does not overwrite ``ingestion_result``).

Timing
------
``StepTiming`` records wall-clock duration per step. The pipeline
populates this automatically — individual steps don't touch it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from capl_gen.schemas.requirement import IngestionResult, RequirementRow
from capl_gen.schemas.signal import ParsedCANData, ParsedSomeIPData

# Union of all possible parsed signal DB types.
# Extend when new parsers are added (e.g. ParsedLINData).
ParsedSignalDB = Union[ParsedCANData, ParsedSomeIPData]


# ---------------------------------------------------------------------------
# Step timing record
# ---------------------------------------------------------------------------


@dataclass
class StepTiming:
    """Wall-clock duration for a single completed step."""

    step_name:      str
    duration_secs:  float
    success:        bool
    error_message:  Optional[str] = None

    @property
    def duration_ms(self) -> float:
        return self.duration_secs * 1000


# ---------------------------------------------------------------------------
# Pipeline context
# ---------------------------------------------------------------------------


@dataclass
class PipelineContext:
    """
    Shared state object threaded through every pipeline step.

    Populated progressively — earlier steps fill their output fields,
    later steps read them.  Fields are ``None`` until the step that
    produces them has run.

    Parameters (constructor kwargs)
    --------------------------------
    excel_path:
        Path to the requirements Excel file.  Set before pipeline.run().
    sheet_name:
        Sheet to read from the Excel file.  Defaults to 0 (first sheet).
    output_dir:
        Directory where generated ``.can`` files are written.
    templates_dir:
        Root directory of Jinja2 templates (e.g. ``src/capl_gen/templates``).
    dry_run:
        If True, RenderStep and WriteStep execute but no files are written.
        Useful for CI validation.
    """

    # --- Inputs (set by caller before pipeline.run()) ---
    excel_path:     Path                    = field(default_factory=Path)
    sheet_name:     Union[str, int]         = 0
    output_dir:     Path                    = field(default_factory=Path)
    templates_dir:  Path                    = field(default_factory=Path)
    dry_run:        bool                    = False

    # --- IngestStep output ---
    ingestion_result: Optional[IngestionResult] = None

    # --- ParseSignalsStep output ---
    # Maps absolute source_file path string → parsed signal DB
    signal_databases: dict[str, ParsedSignalDB] = field(default_factory=dict)

    # --- ValidateStep output ---
    # Rows that passed both Pydantic + business-rule validation; ready for generation
    validated_rows: list[RequirementRow] = field(default_factory=list)
    # Rows blocked by at least one ERROR-level issue
    rejected_rows:  list[RequirementRow] = field(default_factory=list)

    # --- RenderStep output ---
    # Maps requirement_id → rendered CAPL source string
    rendered_outputs: dict[str, str] = field(default_factory=dict)
    # Maps requirement_id → error message for rows that failed rendering
    render_errors:    dict[str, str] = field(default_factory=dict)

    # --- WriteStep output ---
    # Maps requirement_id → absolute path of written .can file
    written_files:  dict[str, Path] = field(default_factory=dict)
    # Maps requirement_id → write error message
    write_errors:   dict[str, str]  = field(default_factory=dict)

    # --- Pipeline metadata (populated by GenerationPipeline) ---
    step_timings:   list[StepTiming] = field(default_factory=list)
    aborted:        bool             = False
    abort_reason:   Optional[str]    = None
    pipeline_start: Optional[float]  = None   # time.monotonic()
    pipeline_end:   Optional[float]  = None

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def total_duration_secs(self) -> float:
        if self.pipeline_start and self.pipeline_end:
            return self.pipeline_end - self.pipeline_start
        return 0.0

    @property
    def ingest_ok(self) -> bool:
        return self.ingestion_result is not None

    @property
    def parse_ok(self) -> bool:
        return bool(self.signal_databases)

    @property
    def has_validated_rows(self) -> bool:
        return bool(self.validated_rows)

    @property
    def generation_count(self) -> int:
        """Number of rows that were successfully rendered."""
        return len(self.rendered_outputs)

    @property
    def write_count(self) -> int:
        """Number of files actually written to disk."""
        return len(self.written_files)

    def get_db_for_row(self, row: RequirementRow) -> Optional[ParsedSignalDB]:
        """
        Look up the parsed signal database for a given row's source_file.

        The key is the *resolved* absolute path string, matching what
        ParseSignalsStep stores.
        """
        resolved = str(Path(row.source_file).resolve())
        return self.signal_databases.get(resolved)

    # ------------------------------------------------------------------
    # Reporting helpers
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Single-line pipeline summary for logging / GUI status bar."""
        if self.aborted:
            return f"Pipeline ABORTED — {self.abort_reason}"

        parts = [
            f"Pipeline complete in {self.total_duration_secs:.2f}s",
            f"ingested={self.ingestion_result.valid_count if self.ingestion_result else 0}",
            f"validated={len(self.validated_rows)}",
            f"rendered={self.generation_count}",
            f"written={self.write_count}",
        ]
        if self.render_errors:
            parts.append(f"render_errors={len(self.render_errors)}")
        if self.write_errors:
            parts.append(f"write_errors={len(self.write_errors)}")
        return "  |  ".join(parts)

    def step_summary(self) -> list[str]:
        """Per-step timing lines for the detailed report."""
        lines = []
        for t in self.step_timings:
            status = "✓" if t.success else "✗"
            line = f"  {status}  {t.step_name:<25} {t.duration_ms:>8.1f} ms"
            if t.error_message:
                line += f"  — {t.error_message}"
            lines.append(line)
        return lines