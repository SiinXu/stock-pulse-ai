"""Typed execution results and retry fences for Pipeline stages."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Dict, Generic, Hashable, Optional, Tuple, TypeVar, Union

from src.utils.sanitize import log_safe_exception


T = TypeVar("T")
logger = logging.getLogger(__name__)


class PipelineStageName(str, Enum):
    """Stable Pipeline stage names shared by execution and diagnostics."""

    RESOLVE = "resolve"
    FETCH = "fetch"
    INTELLIGENCE = "intelligence"
    CONTEXT = "context"
    ANALYZE = "analyze"
    PERSIST = "persist"
    RENDER = "render"
    DISPATCH = "dispatch"


class PipelineStageStatus(str, Enum):
    """Terminal status of one executable Pipeline stage."""

    SUCCESS = "success"
    DEGRADED = "degraded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class PipelinePersistValue:
    """Value produced after attempting analysis-history persistence."""

    saved: bool
    history_id: Optional[int]
    context_snapshot: Dict[str, Any] = field(compare=False, repr=False)


@dataclass(frozen=True)
class PipelineStageResult(Generic[T]):
    """Immutable outcome used to continue, retry, or fence one stage."""

    stage: PipelineStageName
    status: PipelineStageStatus
    value: Optional[T] = None
    retryable: bool = False
    side_effect_committed: bool = False
    attempt: int = 1
    reused: bool = False
    degradation_reason: Optional[str] = None
    error: Optional[BaseException] = field(
        default=None,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        """Normalize enum inputs and enforce retry safety invariants."""
        if not isinstance(self.stage, PipelineStageName):
            object.__setattr__(self, "stage", PipelineStageName(self.stage))
        if not isinstance(self.status, PipelineStageStatus):
            object.__setattr__(self, "status", PipelineStageStatus(self.status))
        if self.attempt < 1:
            raise ValueError("Pipeline stage attempt must be at least 1")
        if self.side_effect_committed and self.retryable:
            object.__setattr__(self, "retryable", False)

    @property
    def successful(self) -> bool:
        """Return whether the stage produced a usable value."""
        return self.status in {
            PipelineStageStatus.SUCCESS,
            PipelineStageStatus.DEGRADED,
        }

    def unwrap(self) -> Optional[T]:
        """Return the value or re-raise the original failed-stage error."""
        if self.status == PipelineStageStatus.FAILED and self.error is not None:
            raise self.error
        return self.value

    @classmethod
    def success(
        cls,
        stage: Union[PipelineStageName, str],
        value: Optional[T] = None,
        *,
        side_effect_committed: bool = False,
        attempt: int = 1,
    ) -> "PipelineStageResult[T]":
        """Build a successful result."""
        return cls(
            stage=PipelineStageName(stage),
            status=PipelineStageStatus.SUCCESS,
            value=value,
            side_effect_committed=side_effect_committed,
            attempt=attempt,
        )

    @classmethod
    def degraded(
        cls,
        stage: Union[PipelineStageName, str],
        value: Optional[T] = None,
        *,
        reason: Optional[str] = None,
        retryable: bool = True,
        side_effect_committed: bool = False,
        attempt: int = 1,
        error: Optional[BaseException] = None,
    ) -> "PipelineStageResult[T]":
        """Build a usable but degraded result."""
        return cls(
            stage=PipelineStageName(stage),
            status=PipelineStageStatus.DEGRADED,
            value=value,
            retryable=retryable,
            side_effect_committed=side_effect_committed,
            attempt=attempt,
            degradation_reason=reason,
            error=error,
        )

    @classmethod
    def failed(
        cls,
        stage: Union[PipelineStageName, str],
        *,
        error: Optional[BaseException] = None,
        value: Optional[T] = None,
        retryable: bool = True,
        side_effect_committed: bool = False,
        attempt: int = 1,
        reason: Optional[str] = None,
    ) -> "PipelineStageResult[T]":
        """Build a failed result."""
        return cls(
            stage=PipelineStageName(stage),
            status=PipelineStageStatus.FAILED,
            value=value,
            retryable=retryable,
            side_effect_committed=side_effect_committed,
            attempt=attempt,
            degradation_reason=reason,
            error=error,
        )

    @classmethod
    def skipped(
        cls,
        stage: Union[PipelineStageName, str],
        *,
        reason: Optional[str] = None,
        value: Optional[T] = None,
        attempt: int = 1,
    ) -> "PipelineStageResult[T]":
        """Build a skipped result."""
        return cls(
            stage=PipelineStageName(stage),
            status=PipelineStageStatus.SKIPPED,
            value=value,
            attempt=attempt,
            degradation_reason=reason,
        )


class PipelineStageRunner:
    """Execute stages and fence committed side effects within one Pipeline run."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._side_effect_locks: Dict[
            Tuple[PipelineStageName, Hashable],
            threading.Lock,
        ] = {}
        self._committed: Dict[
            Tuple[PipelineStageName, Hashable],
            PipelineStageResult[object],
        ] = {}
        self._attempts: Dict[Tuple[PipelineStageName, Hashable], int] = {}
        self._started_scopes: set[Hashable] = set()
        self._latest: Dict[PipelineStageName, PipelineStageResult[object]] = {}

    def record(self, result: PipelineStageResult[T]) -> PipelineStageResult[T]:
        """Store the latest typed result for its stage."""
        with self._lock:
            self._latest[result.stage] = result
        return result

    def latest(
        self,
        stage: Union[PipelineStageName, str],
    ) -> Optional[PipelineStageResult[object]]:
        """Return the latest result recorded for a stage."""
        with self._lock:
            return self._latest.get(PipelineStageName(stage))

    def scope_started(self, scope_key: Hashable) -> bool:
        """Return whether an effectful execution scope has started."""
        with self._lock:
            return scope_key in self._started_scopes

    def mark_scope_started(self, scope_key: Hashable) -> None:
        """Mark an effectful scope after its first-entry gate has passed."""
        with self._lock:
            self._started_scopes.add(scope_key)

    def clear_scope_started(self, scope_key: Hashable) -> None:
        """Clear a scope whose effectful operations all remained uncommitted."""
        with self._lock:
            self._started_scopes.discard(scope_key)

    def run(
        self,
        stage: Union[PipelineStageName, str],
        operation: Callable[[], Union[T, PipelineStageResult[T]]],
        *,
        retryable: bool = False,
        side_effect_key: Optional[Hashable] = None,
        attempt: int = 1,
    ) -> PipelineStageResult[T]:
        """Run one stage, reusing a committed side effect when keyed."""
        stage_name = PipelineStageName(stage)
        if side_effect_key is None:
            return self.record(
                self._invoke(
                    stage_name,
                    operation,
                    retryable=retryable,
                    attempt=attempt,
                )
            )

        cache_key = (stage_name, side_effect_key)
        with self._lock:
            side_effect_lock = self._side_effect_locks.setdefault(
                cache_key,
                threading.Lock(),
            )
        with side_effect_lock:
            with self._lock:
                cached = self._committed.get(cache_key)
            if cached is not None:
                return self.record(replace(cached, reused=True))  # type: ignore[arg-type]

            with self._lock:
                effective_attempt = max(
                    attempt,
                    self._attempts.get(cache_key, 0) + 1,
                )
                self._attempts[cache_key] = effective_attempt

            result = self._invoke(
                stage_name,
                operation,
                retryable=retryable,
                attempt=effective_attempt,
            )
            if result.side_effect_committed:
                with self._lock:
                    self._committed[cache_key] = result  # type: ignore[assignment]
            return self.record(result)

    def retry(
        self,
        previous: PipelineStageResult[T],
        operation: Callable[[], Union[T, PipelineStageResult[T]]],
        *,
        side_effect_key: Optional[Hashable] = None,
    ) -> PipelineStageResult[T]:
        """Retry an eligible result without replaying a committed side effect."""
        if previous.side_effect_committed:
            return self.record(replace(previous, reused=True))
        if not previous.retryable:
            return self.record(previous)
        return self.run(
            previous.stage,
            operation,
            retryable=previous.retryable,
            side_effect_key=side_effect_key,
            attempt=previous.attempt + 1,
        )

    @staticmethod
    def _invoke(
        stage: PipelineStageName,
        operation: Callable[[], Union[T, PipelineStageResult[T]]],
        *,
        retryable: bool,
        attempt: int,
    ) -> PipelineStageResult[T]:
        """Invoke an operation and preserve its exception as a typed result."""
        try:
            value = operation()
        except Exception as exc:  # broad-exception: fallback_recorded - Stage errors are safely recorded before callers decide whether to retry or propagate.
            log_safe_exception(
                logger,
                "Pipeline stage operation failed",
                exc,
                error_code="pipeline_stage_operation_failed",
                level=logging.DEBUG,
                context={"stage": stage.value, "attempt": attempt},
            )
            return PipelineStageResult.failed(
                stage,
                error=exc,
                retryable=retryable,
                attempt=attempt,
            )
        if isinstance(value, PipelineStageResult):
            if value.stage != stage:
                raise ValueError(
                    f"Pipeline stage result mismatch: expected {stage.value}, "
                    f"got {value.stage.value}"
                )
            return replace(value, attempt=attempt, reused=False)
        return PipelineStageResult.success(stage, value, attempt=attempt)
