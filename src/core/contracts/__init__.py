# -*- coding: utf-8 -*-
"""Typed Pipeline stage IO contracts (Issue #1072).

These types formalize the shared run context and the primary stage
boundaries (fetch / analyze / render). ``src.core.pipeline`` remains an
orchestration-only facade; business logic stays in ``src.core.stages`` and
services (Issue #1083).
"""

from __future__ import annotations

from src.core.contracts.context import RunContext, build_run_context
from src.core.contracts.errors import (
    StageDegradedError,
    StageError,
    StageFailedError,
    StageSkippedError,
    stage_result_from_error,
)
from src.core.contracts.stage_io import (
    AnalyzeStageInput,
    AnalyzeStageOutput,
    FetchDailyDataOutput,
    FetchMarketInputsOutput,
    FetchStageInput,
    RenderStageInput,
    RenderStageOutput,
    RenderStageRoute,
)

__all__ = [
    "AnalyzeStageInput",
    "AnalyzeStageOutput",
    "FetchDailyDataOutput",
    "FetchMarketInputsOutput",
    "FetchStageInput",
    "RenderStageInput",
    "RenderStageOutput",
    "RenderStageRoute",
    "RunContext",
    "StageDegradedError",
    "StageError",
    "StageFailedError",
    "StageSkippedError",
    "build_run_context",
    "stage_result_from_error",
]
