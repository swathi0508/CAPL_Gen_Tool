"""
GenerationPipeline — the top-level orchestrator.

Responsibilities
----------------
1. Hold an ordered list of steps.
2. Thread PipelineContext through each step's ``execute()`` call.
3. Time every step and record results in the context.
4. Catch CAPLGenError from any step: mark context as aborted and stop.
5. Expose a fluent ``.add_step()`` API and a ``build_default()`` factory.

What this file does NOT do
---------------------------
- Business logic (that lives in steps).
- Logging configuration (that lives in core/logging.py).
- CLI parsing (that lives in cli.py).

Usage — custom pipeline
-----------------------
::

    from pathlib import Path
    from capl_gen.pipeline.pipeline import GenerationPipeline
    from capl_gen.pipeline.context import PipelineContext
    from capl_gen.pipeline.steps import IngestStep, ParseSignalsStep, ValidateStep

    ctx = PipelineContext(
        excel_path=Path("requirements.xlsx"),
        output_dir=Path("output/"),
        templates_dir=Path("src/capl_gen/templates"),
    )

    result = (
        GenerationPipeline()
        .add_step(IngestStep())
        .add_step(ParseSignalsStep())
        .add_step(ValidateStep())
        .run(ctx)
    )

Usage — default pipeline (recommended for CLI / GUI)
-----------------------------------------------------
::

    ctx = PipelineContext(...)
    result = GenerationPipeline.build_default().run(ctx)
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, Optional

from loguru import logger

from capl_gen.core.exceptions import CAPLGenError
from capl_gen.pipeline.context import PipelineContext, StepTiming
from capl_gen.pipeline.steps import (
    BaseStep,
    IngestStep,
    ParseSignalsStep,
    RenderStep,
    ValidateStep,
    WriteStep,
)


# ---------------------------------------------------------------------------
# Optional step-level hooks (for GUI progress callbacks)
# ---------------------------------------------------------------------------

# Called with (step_name, step_index, total_steps) before each step runs.
StepStartCallback = Callable[[str, int, int], None]
# Called with (step_timing) after each step completes (success or failure).
StepDoneCallback  = Callable[[StepTiming], None]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class GenerationPipeline:
    """
    Orchestrates an ordered sequence of ``BaseStep`` instances against a
    shared ``PipelineContext``.

    Parameters
    ----------
    on_step_start:
        Optional callback fired before each step.  Signature:
        ``(step_name: str, step_index: int, total_steps: int) -> None``
        Use this to update a GUI progress bar.
    on_step_done:
        Optional callback fired after each step.  Signature:
        ``(timing: StepTiming) -> None``
    abort_on_empty_validated_rows:
        If True, the pipeline aborts after ValidateStep when zero rows
        passed validation (prevents wasting time rendering nothing).
        Default True.
    """

    def __init__(
        self,
        on_step_start: Optional[StepStartCallback] = None,
        on_step_done:  Optional[StepDoneCallback]  = None,
        abort_on_empty_validated_rows: bool = True,
    ) -> None:
        self._steps: list[BaseStep] = []
        self._on_step_start = on_step_start
        self._on_step_done  = on_step_done
        self._abort_on_empty = abort_on_empty_validated_rows

    # ------------------------------------------------------------------
    # Builder API
    # ------------------------------------------------------------------

    def add_step(self, step: BaseStep) -> "GenerationPipeline":
        """
        Append a step to the pipeline.

        Returns ``self`` for fluent chaining::

            pipeline = (
                GenerationPipeline()
                .add_step(IngestStep())
                .add_step(ParseSignalsStep())
                ...
            )
        """
        if not isinstance(step, BaseStep):
            raise TypeError(
                f"Expected a BaseStep subclass, got {type(step).__name__}"
            )
        self._steps.append(step)
        return self

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def build_default(
        cls,
        on_step_start: Optional[StepStartCallback] = None,
        on_step_done:  Optional[StepDoneCallback]  = None,
        parse_fail_fast:  bool = False,
        render_fail_fast: bool = False,
        write_fail_fast:  bool = False,
        overwrite_outputs: bool = True,
    ) -> "GenerationPipeline":
        """
        Factory that builds the standard 5-step pipeline.

        Prefer this over manually wiring steps in application code.

        Steps in order
        --------------
        1. IngestStep         — read Excel
        2. ParseSignalsStep   — parse DBC / ARXML files
        3. ValidateStep       — business-rule gate
        4. RenderStep         — Jinja2 CAPL generation
        5. WriteStep          — write .can files

        Parameters
        ----------
        parse_fail_fast / render_fail_fast / write_fail_fast:
            Abort on the first error in the respective step.
            Default False (lenient — skip bad items, continue).
        overwrite_outputs:
            Whether WriteStep overwrites existing .can files.
        """
        return (
            cls(on_step_start=on_step_start, on_step_done=on_step_done)
            .add_step(IngestStep())
            .add_step(ParseSignalsStep(fail_fast=parse_fail_fast))
            .add_step(ValidateStep())
            .add_step(RenderStep(fail_fast=render_fail_fast))
            .add_step(WriteStep(fail_fast=write_fail_fast, overwrite=overwrite_outputs))
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """
        Execute all steps in order against *ctx*.

        On ``CAPLGenError``: marks the context as aborted, logs the error,
        and returns immediately — remaining steps are skipped.

        On any other unexpected exception: wraps in a ``CAPLGenError``,
        aborts, and re-raises so the caller always sees a typed error.

        Parameters
        ----------
        ctx:
            Pre-configured ``PipelineContext`` (excel_path, output_dir, etc.)

        Returns
        -------
        PipelineContext
            The same context, mutated with results from all completed steps.
        """
        total = len(self._steps)
        if total == 0:
            logger.warning("Pipeline has no steps — nothing to execute.")
            return ctx

        logger.info(
            f"Pipeline starting  [{total} step(s)]  "
            f"excel='{ctx.excel_path.name}'  "
            f"output='{ctx.output_dir}'"
        )

        ctx.pipeline_start = time.monotonic()

        for idx, step in enumerate(self._steps):
            step_start = time.monotonic()

            # Fire pre-step callback (GUI progress bar etc.)
            if self._on_step_start:
                try:
                    self._on_step_start(step.name, idx + 1, total)
                except Exception:
                    pass  # callbacks must never abort the pipeline

            logger.info(f"  Step {idx + 1}/{total}: {step.name}")

            try:
                ctx = step.execute(ctx)
                duration = time.monotonic() - step_start
                timing = StepTiming(
                    step_name=step.name,
                    duration_secs=duration,
                    success=True,
                )
                ctx.step_timings.append(timing)
                logger.debug(f"  {step.name} completed in {timing.duration_ms:.1f} ms")

            except CAPLGenError as exc:
                duration = time.monotonic() - step_start
                timing = StepTiming(
                    step_name=step.name,
                    duration_secs=duration,
                    success=False,
                    error_message=str(exc),
                )
                ctx.step_timings.append(timing)
                ctx.aborted = True
                ctx.abort_reason = f"{step.name} failed: {exc}"
                logger.error(f"  {step.name} FAILED: {exc}")
                self._fire_done_callback(timing)
                break  # stop pipeline — don't run remaining steps

            except Exception as exc:
                # Unexpected — wrap and abort
                duration = time.monotonic() - step_start
                msg = f"Unexpected error in {step.name}: {exc}\n{traceback.format_exc()}"
                timing = StepTiming(
                    step_name=step.name,
                    duration_secs=duration,
                    success=False,
                    error_message=msg,
                )
                ctx.step_timings.append(timing)
                ctx.aborted = True
                ctx.abort_reason = msg
                logger.critical(msg)
                self._fire_done_callback(timing)
                raise CAPLGenError(msg) from exc

            self._fire_done_callback(timing)

            # Early-exit guard after ValidateStep
            if (
                self._abort_on_empty
                and isinstance(step, ValidateStep)
                and not ctx.validated_rows
            ):
                ctx.aborted = True
                ctx.abort_reason = (
                    "ValidateStep produced 0 validated rows — "
                    "no CAPL will be generated."
                )
                logger.warning(f"  Aborting pipeline: {ctx.abort_reason}")
                break

        ctx.pipeline_end = time.monotonic()

        # Final summary
        self._log_final_summary(ctx)
        return ctx

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire_done_callback(self, timing: StepTiming) -> None:
        if self._on_step_done:
            try:
                self._on_step_done(timing)
            except Exception:
                pass

    @staticmethod
    def _log_final_summary(ctx: PipelineContext) -> None:
        logger.info("=" * 60)
        logger.info(ctx.summary())
        for line in ctx.step_summary():
            logger.info(line)
        logger.info("=" * 60)