# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Strict public contract for reasoning-trace export (Issue #135)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _StrictTraceModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        str_strip_whitespace=True,
    )


class ReasoningTraceRun(_StrictTraceModel):
    record_id: Optional[str] = Field(default=None, max_length=128)
    query_id: Optional[str] = Field(default=None, max_length=128)
    trace_id: Optional[str] = Field(default=None, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    lookup_key: Optional[str] = Field(default=None, max_length=128)
    lookup_mode: Optional[Literal["primary_key", "latest_by_query_id"]] = None
    stock_code: Optional[str] = Field(default=None, max_length=32)
    stock_name: Optional[str] = Field(default=None, max_length=120)
    market: Optional[str] = Field(default=None, max_length=32)
    model: Optional[str] = Field(default=None, max_length=120)
    started_at: Optional[str] = Field(default=None, max_length=64)
    config_fingerprint: str = Field(min_length=16, max_length=16)
    exported_at: str = Field(min_length=1, max_length=64)


class ReasoningTraceAgentEvent(_StrictTraceModel):
    event_type: Optional[str] = Field(default=None, max_length=120)
    name: Optional[str] = Field(default=None, max_length=120)
    status: Optional[str] = Field(default=None, max_length=64)
    timestamp: Optional[str] = Field(default=None, max_length=64)
    duration_ms: Optional[float] = None
    sequence: Optional[int] = None
    phase: Optional[str] = Field(default=None, max_length=64)


class ReasoningTraceToolCall(_StrictTraceModel):
    name: str = Field(min_length=1, max_length=120)
    status: Optional[str] = Field(default=None, max_length=64)
    duration_ms: Optional[float] = None
    step: Optional[str] = Field(default=None, max_length=120)
    sequence: Optional[int] = None
    timestamp: Optional[str] = Field(default=None, max_length=64)
    tool_call_id: Optional[str] = Field(default=None, max_length=120)
    error_code: Optional[str] = Field(default=None, max_length=120)


class ReasoningTraceAgent(_StrictTraceModel):
    role: str = Field(min_length=1, max_length=64)
    input_summary: Optional[str] = Field(default=None, max_length=500)
    tool_calls: list[ReasoningTraceToolCall] = Field(default_factory=list, max_length=50)
    output_opinion: Optional[str] = Field(default=None, max_length=500)
    events: list[ReasoningTraceAgentEvent] = Field(default_factory=list, max_length=200)


class ReasoningTraceDisagreement(_StrictTraceModel):
    conflict_severity: Optional[str] = Field(default=None, max_length=64)
    conflict_count: Optional[int] = Field(default=None, ge=0)
    consensus_level: Optional[str] = Field(default=None, max_length=64)
    supporting_skills: list[str] = Field(default_factory=list, max_length=64)
    opposing_skills: list[str] = Field(default_factory=list, max_length=64)


class ReasoningTraceConsensus(_StrictTraceModel):
    consensus_level: Optional[str] = Field(default=None, max_length=64)
    committee_status: Optional[str] = Field(default=None, max_length=64)


class ReasoningTraceConclusion(_StrictTraceModel):
    final_signal: Optional[str] = Field(default=None, max_length=64)
    operation_advice: Optional[str] = Field(default=None, max_length=800)
    confidence_level: Optional[str] = Field(default=None, max_length=64)
    analysis_summary: Optional[str] = Field(default=None, max_length=1200)
    sentiment_score: Optional[float] = None


class ReasoningTraceSynthesis(_StrictTraceModel):
    disagreement: ReasoningTraceDisagreement = Field(default_factory=ReasoningTraceDisagreement)
    consensus: ReasoningTraceConsensus = Field(default_factory=ReasoningTraceConsensus)
    final_conclusion: ReasoningTraceConclusion = Field(default_factory=ReasoningTraceConclusion)


class ReasoningTraceProviderRun(_StrictTraceModel):
    provider: Optional[str] = Field(default=None, max_length=64)
    data_type: Optional[str] = Field(default=None, max_length=64)
    operation: Optional[str] = Field(default=None, max_length=64)
    status: Optional[str] = Field(default=None, max_length=32)
    duration_ms: Optional[float] = None
    error_code: Optional[str] = Field(default=None, max_length=64)


class ReasoningTraceTokenUsage(_StrictTraceModel):
    prompt_tokens: Optional[int] = Field(default=None, ge=0)
    completion_tokens: Optional[int] = Field(default=None, ge=0)
    total_tokens: Optional[int] = Field(default=None, ge=0)


class ReasoningTraceLlmRun(_StrictTraceModel):
    provider: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=120)
    call_type: Optional[str] = Field(default=None, max_length=64)
    status: Optional[str] = Field(default=None, max_length=32)
    duration_ms: Optional[float] = None
    usage: ReasoningTraceTokenUsage = Field(default_factory=ReasoningTraceTokenUsage)


class ReasoningTraceDataQuality(_StrictTraceModel):
    status: Optional[str] = Field(default=None, max_length=64)
    score: Optional[float] = None
    warnings: list[str] = Field(default_factory=list, max_length=64)
    missing_fields: list[str] = Field(default_factory=list, max_length=64)


class ReasoningTracePipelineStage(_StrictTraceModel):
    stage: Optional[str] = Field(default=None, max_length=64)
    status: Optional[str] = Field(default=None, max_length=32)
    duration_ms: Optional[float] = None


class ReasoningTraceDataSources(_StrictTraceModel):
    provider_trace: list[ReasoningTraceProviderRun] = Field(default_factory=list, max_length=100)
    llm_runs: list[ReasoningTraceLlmRun] = Field(default_factory=list, max_length=100)
    data_quality_status: Optional[ReasoningTraceDataQuality] = None
    pipeline_stage_runs: list[ReasoningTracePipelineStage] = Field(default_factory=list, max_length=100)


class ReasoningTraceCoverageSource(_StrictTraceModel):
    source: str = Field(min_length=1, max_length=96)
    supported: bool
    present: bool
    absent: bool
    source_truncated: bool = False
    # True when capture loss cannot be proven either way (legacy records written
    # before the runtime recorded an agent_events capture marker).
    source_truncated_unknown: bool = False
    export_truncated: bool = False
    original_count: Optional[int] = Field(default=None, ge=0)
    returned_count: Optional[int] = Field(default=None, ge=0)
    # Capture-stage (upstream retention) loss, distinct from the total gap
    # between original_count and what the response actually carries.
    source_dropped_count: Optional[int] = Field(default=None, ge=0)
    dropped_count: Optional[int] = Field(default=None, ge=0)
    reasons: list[str] = Field(default_factory=list, max_length=16)


class ReasoningTraceCoverage(_StrictTraceModel):
    sources: list[ReasoningTraceCoverageSource] = Field(default_factory=list, max_length=16)
    not_recorded: list[str] = Field(default_factory=list, max_length=16)
    notes: str = Field(max_length=500)


class ReasoningTraceTruncationDrop(_StrictTraceModel):
    path: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=96)
    count: Optional[int] = Field(default=None, ge=0)


class ReasoningTraceTruncation(_StrictTraceModel):
    marker: Literal["truncated"] = "truncated"
    reason: str = Field(min_length=1, max_length=96)
    max_chars: int = Field(ge=1)
    dropped: list[ReasoningTraceTruncationDrop] = Field(default_factory=list, max_length=128)


class ReasoningTraceExportResponse(_StrictTraceModel):
    """JSON export envelope for ``reasoning-trace-v1``."""

    schema_version: Literal["reasoning-trace-v1"]
    run: ReasoningTraceRun
    agents: list[ReasoningTraceAgent] = Field(default_factory=list, max_length=200)
    synthesis: ReasoningTraceSynthesis = Field(default_factory=ReasoningTraceSynthesis)
    data_sources: ReasoningTraceDataSources = Field(default_factory=ReasoningTraceDataSources)
    coverage: ReasoningTraceCoverage
    truncated: bool = False
    truncation: Optional[ReasoningTraceTruncation] = None
    markdown: Optional[str] = Field(default=None, max_length=2_000_000)
