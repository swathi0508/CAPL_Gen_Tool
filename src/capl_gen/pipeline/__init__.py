# src/capl_gen/pipeline/__init__.py
"""
capl_gen.pipeline — explicit pipeline orchestration.

Public API
----------
The three things callers need:

    from capl_gen.pipeline import GenerationPipeline, PipelineContext, build_default_pipeline

Everything else (step classes, StepTiming, callbacks) is importable
directly from the submodules for advanced use.
"""
from capl_gen.pipeline.context import PipelineContext
from capl_gen.pipeline.pipeline import GenerationPipeline
from capl_gen.pipeline.steps import (
    BaseStep,
    IngestStep,
    ParseSignalsStep,
    RenderStep,
    ValidateStep,
    WriteStep,
)


def build_default_pipeline(**kwargs) -> GenerationPipeline:
    """
    Convenience wrapper around ``GenerationPipeline.build_default()``.

    All keyword arguments are forwarded unchanged::

        pipeline = build_default_pipeline(parse_fail_fast=True)
        result   = pipeline.run(ctx)
    """
    return GenerationPipeline.build_default(**kwargs)


__all__ = [
    "PipelineContext",
    "GenerationPipeline",
    "build_default_pipeline",
    # Step classes — exported for custom pipeline assembly
    "BaseStep",
    "IngestStep",
    "ParseSignalsStep",
    "ValidateStep",
    "RenderStep",
    "WriteStep",
]