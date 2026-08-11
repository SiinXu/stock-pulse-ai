# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Strict contracts for deterministic agent-trajectory evaluation (Issue #269)."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


INPUT_SCHEMA_VERSION = "agent-trajectory-input-v1"
TRAJECTORY_EVAL_ENGINE_VERSION = "agent-trajectory-eval-v2"
RUBRIC_VERSION = "agent-trajectory-rubric-v1"

PATH_SINGLE = "single"
PATH_ORCHESTRATOR = "orchestrator"
PathLabel = Literal["single", "orchestrator"]

FAILURE_CLASS_NONE = "none"
FAILURE_CLASS_TIMEOUT = "timeout"
FAILURE_CLASS_GUARDED = "guarded"
FAILURE_CLASS_ERROR = "error"
FailureClass = Literal["none", "timeout", "guarded", "error"]

# Upper bound of the aggregate rejected-call counter carried in output
# provenance. Oversized sources saturate at this value and set the companion
# saturation flag rather than failing output validation.
MAX_REPORTED_REJECTED_CALLS = 128_000


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class TrajectoryRubric(_StrictModel):
    """Expected-tool annotations supplied by the owned benchmark scenario."""

    version: Literal["agent-trajectory-rubric-v1"] = "agent-trajectory-rubric-v1"
    required_tools: list[str] = Field(default_factory=list, max_length=64)
    forbidden_tools: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("required_tools", "forbidden_tools")
    @classmethod
    def _validate_tool_names(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.strip()
            if not item or len(item) > 120:
                raise ValueError("rubric tool names must contain 1..120 characters")
            if item not in normalized:
                normalized.append(item)
        return normalized

    @model_validator(mode="after")
    def _validate_disjoint_sets(self) -> "TrajectoryRubric":
        overlap = set(self.required_tools) & set(self.forbidden_tools)
        if overlap:
            raise ValueError("required_tools and forbidden_tools must be disjoint")
        return self


class TrajectoryToolCallInput(_StrictModel):
    """One strict, already-redacted runner tool-call record."""

    tool: str = Field(min_length=1, max_length=120)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    success: bool
    duration: Optional[float] = Field(default=None, ge=0.0, le=3_600.0)
    cached: bool = False
    timeout: bool = False
    guarded: bool = False
    result_length: Optional[int] = Field(default=None, ge=0, le=100_000_000)
    expected_stock_code: Optional[str] = Field(default=None, max_length=32)
    requested_stock_code: Optional[str] = Field(default=None, max_length=32)
    allowed_stock_codes: list[str] = Field(default_factory=list, max_length=64)
    step: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    dispatch_index: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    call_id: Optional[str] = Field(default=None, max_length=160)
    agent_id: Optional[str] = Field(default=None, max_length=120)
    dispatched_at: Optional[str] = Field(default=None, max_length=64)
    started_at: Optional[str] = Field(default=None, max_length=64)
    ended_at: Optional[str] = Field(default=None, max_length=64)

    @field_validator("tool")
    @classmethod
    def _nonempty_tool(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tool must not be blank")
        return value.strip()


class TrajectoryRunInput(_StrictModel):
    """Joinable source run supplied to the evaluator."""

    schema_version: Literal["agent-trajectory-input-v1"] = "agent-trajectory-input-v1"
    run_id: str = Field(min_length=1, max_length=160)
    execution_id: Optional[str] = Field(default=None, max_length=160)
    task_id: Optional[str] = Field(default=None, max_length=160)
    agent_id: str = Field(default="agent", min_length=1, max_length=120)
    stock_code: Optional[str] = Field(default=None, max_length=32)
    market: Optional[str] = Field(default=None, max_length=32)
    started_at: Optional[str] = Field(default=None, max_length=64)
    completed: Optional[bool] = None
    source_truncated: bool = False
    tool_calls: list[TrajectoryToolCallInput] = Field(default_factory=list, max_length=2_000)


class TrajectoryStep(_StrictModel):
    """Bounded output detail; raw argument bodies are deliberately excluded."""

    index: int = Field(ge=0, le=1_999)
    run_id: str = Field(min_length=1, max_length=160)
    execution_id: Optional[str] = Field(default=None, max_length=160)
    task_id: Optional[str] = Field(default=None, max_length=160)
    agent_id: str = Field(min_length=1, max_length=120)
    call_id: str = Field(min_length=1, max_length=200)
    step: Optional[int] = Field(default=None, ge=0)
    dispatch_index: Optional[int] = Field(default=None, ge=0)
    tool: str = Field(min_length=1, max_length=120)
    argument_fingerprint: str = Field(min_length=64, max_length=64)
    success: bool
    duration_ms: Optional[int] = Field(default=None, ge=0, le=3_600_000)
    cached: bool
    failure_class: FailureClass
    is_redundant: bool = False
    is_retry: bool = False
    dispatched_at: Optional[str] = Field(default=None, max_length=64)
    started_at: Optional[str] = Field(default=None, max_length=64)
    ended_at: Optional[str] = Field(default=None, max_length=64)


class TrajectoryRunProvenance(_StrictModel):
    run_id: str = Field(min_length=1, max_length=160)
    execution_id: Optional[str] = Field(default=None, max_length=160)
    task_id: Optional[str] = Field(default=None, max_length=160)
    agent_id: str = Field(min_length=1, max_length=120)
    stock_code: Optional[str] = Field(default=None, max_length=32)
    market: Optional[str] = Field(default=None, max_length=32)
    started_at: Optional[str] = Field(default=None, max_length=64)
    completed: Optional[bool] = None
    source_truncated: bool = False
    accepted_call_count: int = Field(ge=0)
    rejected_call_count: int = Field(ge=0)


class TrajectoryMetrics(_StrictModel):
    """Separate observable rates avoid a misleading synthetic efficiency score."""

    tool_selection_precision: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    tool_selection_recall: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    tool_selection_f1: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    tool_call_success_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    productive_step_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    redundancy_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    retry_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    cache_hit_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    task_completion_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    redundant_call_count: int = Field(ge=0, le=2_000)
    retry_count: int = Field(ge=0, le=2_000)
    successful_call_count: int = Field(ge=0, le=2_000)
    productive_step_count: int = Field(ge=0, le=2_000)
    total_duration_ms: int = Field(ge=0, le=7_200_000_000)
    missing_duration_count: int = Field(ge=0, le=2_000)
    sample_size: int = Field(ge=0, le=2_000)


class TrajectoryEvaluationProvenance(_StrictModel):
    evaluation_id: str = Field(min_length=64, max_length=64)
    input_schema_version: Literal["agent-trajectory-input-v1"] = (
        "agent-trajectory-input-v1"
    )
    engine_version: Literal["agent-trajectory-eval-v2"] = "agent-trajectory-eval-v2"
    rubric_version: Literal["agent-trajectory-rubric-v1"] = (
        "agent-trajectory-rubric-v1"
    )
    rubric_fingerprint: str = Field(min_length=64, max_length=64)
    path_label: PathLabel
    as_of: Optional[str] = Field(default=None, max_length=64)
    run_count: int = Field(ge=0, le=64)
    rejected_run_count: int = Field(ge=0, le=64)
    # Bounded aggregate. When the true rejected total exceeds the reported cap,
    # the value saturates and ``rejected_call_count_saturated`` says so instead
    # of the evaluator raising on oversized input. Per-run provenance keeps the
    # exact unsaturated count.
    rejected_call_count: int = Field(ge=0, le=MAX_REPORTED_REJECTED_CALLS)
    rejected_call_count_saturated: bool = False
    source_truncated: bool = False
    output_truncated: bool = False
    output_dropped_step_count: int = Field(ge=0, le=2_000)


class TrajectoryEvalResult(_StrictModel):
    """Versioned, bounded and strict-JSON-safe benchmark output."""

    schema_version: Literal["agent-trajectory-evaluation-v1"] = (
        "agent-trajectory-evaluation-v1"
    )
    provenance: TrajectoryEvaluationProvenance
    metrics: TrajectoryMetrics
    runs: list[TrajectoryRunProvenance] = Field(default_factory=list, max_length=64)
    steps: list[TrajectoryStep] = Field(default_factory=list, max_length=1_000)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
