# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Trajectory evaluation contracts for agent tool-call logs (Issue #269).

These structures describe a **read-only** view of ``tool_calls_log`` entries
produced by the agent runner. They intentionally mirror the runner log shape
and do not require runner changes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# Failure classes derived only from fields already present on tool_calls_log.
FAILURE_CLASS_NONE = "none"
FAILURE_CLASS_TIMEOUT = "timeout"
FAILURE_CLASS_GUARDED = "guarded"
FAILURE_CLASS_ERROR = "error"

# Path labels for comparable single-agent vs multi-agent (orchestrator) baselines.
PATH_SINGLE = "single"
PATH_ORCHESTRATOR = "orchestrator"
PATH_LABELS = frozenset({PATH_SINGLE, PATH_ORCHESTRATOR})

TRAJECTORY_EVAL_ENGINE_VERSION = "agent-trajectory-eval-v1"


@dataclass(frozen=True)
class TrajectoryStep:
    """One normalized step projected from a runner ``tool_calls_log`` entry."""

    index: int
    step: Optional[int]
    tool: str
    success: bool
    duration_ms: Optional[int]
    cached: bool
    failure_class: str
    is_redundant: bool = False
    is_retry: bool = False
    arguments: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if data.get("arguments") is None:
            data.pop("arguments", None)
        return data


@dataclass(frozen=True)
class TrajectoryMetrics:
    """Aggregate process-quality metrics for one or more agent runs.

    Metric semantics (deterministic, no LLM):

    - ``tool_selection_accuracy``: process success rate
      (``successful_steps / sample_size``). Without gold tool labels this is
      an operational proxy, not oracle selection accuracy. ``None`` when
      ``sample_size == 0`` (do not fabricate).
    - ``redundant_call_count``: later calls with the same tool + normalized
      arguments after a prior **successful** call in the same run.
    - ``retry_count``: later calls with the same tool + normalized arguments
      after a prior **failed** call in the same run.
    - ``step_efficiency``: ``(sample_size - redundant_call_count) / sample_size``
      when ``sample_size > 0``, else ``None``.
    - ``total_duration_ms``: sum of per-step durations converted from runner
      seconds; missing/invalid durations contribute ``0``.
    - ``sample_size``: number of log entries evaluated.
    """

    tool_selection_accuracy: Optional[float]
    redundant_call_count: int
    retry_count: int
    step_efficiency: Optional[float]
    total_duration_ms: int
    sample_size: int
    path_label: str = PATH_SINGLE
    engine_version: str = TRAJECTORY_EVAL_ENGINE_VERSION
    enabled: bool = True
    neutral: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrajectoryEvalResult:
    """Metrics plus per-step detail for one evaluation request."""

    metrics: TrajectoryMetrics
    steps: List[TrajectoryStep] = field(default_factory=list)
    run_count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics": self.metrics.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "run_count": self.run_count,
        }
