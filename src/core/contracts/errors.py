# -*- coding: utf-8 -*-
"""Stage error taxonomy for Pipeline stage boundaries.

These exceptions classify stage outcomes without changing the existing
``PipelineStageResult`` execution model. Callers may raise them or convert
them via :func:`stage_result_from_error`. Existing bare exceptions still
flow through ``PipelineStageRunner`` unchanged.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from src.core.pipeline_stage_results import (
    PipelineStageName,
    PipelineStageResult,
)


class StageError(Exception):
    """Base error for an explicit Pipeline stage terminal."""

    def __init__(
        self,
        message: str = "",
        *,
        stage: Union[PipelineStageName, str, None] = None,
        reason: Optional[str] = None,
        retryable: bool = True,
        side_effect_committed: bool = False,
        value: Any = None,
    ) -> None:
        super().__init__(message or reason or self.__class__.__name__)
        self.stage = (
            PipelineStageName(stage)
            if stage is not None and not isinstance(stage, PipelineStageName)
            else stage
        )
        self.reason = reason or (message or None)
        self.retryable = bool(retryable)
        self.side_effect_committed = bool(side_effect_committed)
        self.value = value


class StageFailedError(StageError):
    """Stage terminated unsuccessfully and produced no usable value."""


class StageDegradedError(StageError):
    """Stage produced a usable value with reduced evidence quality."""


class StageSkippedError(StageError):
    """Stage was intentionally not executed."""

    def __init__(
        self,
        message: str = "",
        *,
        stage: Union[PipelineStageName, str, None] = None,
        reason: Optional[str] = None,
        value: Any = None,
    ) -> None:
        super().__init__(
            message,
            stage=stage,
            reason=reason,
            retryable=False,
            side_effect_committed=False,
            value=value,
        )


def stage_result_from_error(
    error: BaseException,
    *,
    stage: Union[PipelineStageName, str],
    attempt: int = 1,
) -> PipelineStageResult[Any]:
    """Map a stage error (or bare exception) into a ``PipelineStageResult``.

    ``StageError`` subclasses preserve their status, reason, and retry flags.
    All other exceptions become a failed, retryable result matching the
    historical ``PipelineStageRunner._invoke`` fallback.
    """
    stage_name = PipelineStageName(stage)
    if isinstance(error, StageSkippedError):
        return PipelineStageResult.skipped(
            stage_name,
            reason=error.reason,
            value=error.value,
            attempt=attempt,
        )
    if isinstance(error, StageDegradedError):
        return PipelineStageResult.degraded(
            stage_name,
            error.value,
            reason=error.reason,
            retryable=error.retryable,
            side_effect_committed=error.side_effect_committed,
            attempt=attempt,
            error=error,
        )
    if isinstance(error, StageFailedError):
        return PipelineStageResult.failed(
            stage_name,
            error=error,
            value=error.value,
            retryable=error.retryable,
            side_effect_committed=error.side_effect_committed,
            attempt=attempt,
            reason=error.reason,
        )
    if isinstance(error, StageError):
        return PipelineStageResult.failed(
            stage_name,
            error=error,
            value=error.value,
            retryable=error.retryable,
            side_effect_committed=error.side_effect_committed,
            attempt=attempt,
            reason=error.reason,
        )
    return PipelineStageResult.failed(
        stage_name,
        error=error,
        retryable=True,
        attempt=attempt,
    )


__all__ = [
    "StageDegradedError",
    "StageError",
    "StageFailedError",
    "StageSkippedError",
    "stage_result_from_error",
]
