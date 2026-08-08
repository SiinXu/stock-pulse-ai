# -*- coding: utf-8 -*-
"""Additive schema for multi-strategy evidence contract and deliberation payload."""
from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrategyEvidenceDiagnosticsRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    agent_name: str = Field(min_length=1)
    raw_signal: Optional[Any] = None
    confidence: float = 0.0
    reason: str = Field(min_length=1)


class DeliberationAgendaItemSchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    agenda_id: str
    conflict_type: str
    severity: str = "medium"
    participants: List[str] = Field(default_factory=list)
    question_key: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DeliberationResponseSchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    agenda_id: str
    skill_id: str
    stance: str = "defend"
    revision: Literal["unchanged", "softened"]
    original_signal: str
    revised_signal: str
    original_confidence: float = Field(ge=0, le=1)
    revised_confidence: float = Field(ge=0, le=1)
    critique_key: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DeliberationSummarySchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    resolution_status: Literal["unresolved", "partially_resolved"]
    resolved_conflict_count: int = 0
    unresolved_conflict_count: int = 0
    minority_view_preserved: bool = False
    confidence_adjustment: float = 0.0
    confidence_adjustment_reason_key: str = ""


class StrategyDeliberationSchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str
    mode: str
    rounds: int = 0
    agenda: List[DeliberationAgendaItemSchema] = Field(default_factory=list)
    responses: List[DeliberationResponseSchema] = Field(default_factory=list)
    summary: DeliberationSummarySchema
    round_history: List[Dict[str, Any]] = Field(default_factory=list)


class RevisionProjectionSchema(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str = "computed"
    mode: Literal["preview_only"] = "preview_only"
    source_mode: str = ""
    projected_signal: str
    projected_weighted_score: float
    projected_confidence: float
    projected_original_confidence: float
    projected_conflict_count: int = 0
    projected_conflict_severity: str = "none"
    projected_consensus_level: str = "insufficient"
    changed_skill_count: int = 0
    changed_skills: List[str] = Field(default_factory=list)
    final_signal_overridden: bool = False

    @field_validator("final_signal_overridden")
    @classmethod
    def _must_remain_preview(cls, value: bool) -> bool:
        if value:
            raise ValueError("revision projection must not override final_signal")
        return value


def validate_deliberation_payload(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    return StrategyDeliberationSchema.model_validate(value).model_dump(mode="json")


def validate_revision_projection_payload(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    return RevisionProjectionSchema.model_validate(value).model_dump(mode="json")
