# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Optional run and prediction user-feedback API schemas (Issue #1105)."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from src.schemas.memory_fact_opinion import lock_opinion_payload
from src.schemas.memory_provenance import reject_client_provenance_keys
from src.schemas.memory_write_guard import FEEDBACK_NOTE_MAX_LENGTH, reject_memory_write_text


MemoryProvenanceSource = Literal["system_resolve", "user_feedback", "operator"]
AgentRunFeedbackValue = Literal["useful", "partial", "wrong", "harmful"]
AgentPredictionFeedbackValue = Literal[
    "agree_hit", "agree_miss", "disagree_score", "context_note"
]
AgentFeedbackSource = Literal["web", "api"]


class _AgentFeedbackRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Optional[str] = Field(
        None, json_schema_extra={"maxLength": FEEDBACK_NOTE_MAX_LENGTH}
    )
    source: AgentFeedbackSource = "api"

    @model_validator(mode="before")
    @classmethod
    def _reject_fact_and_client_provenance(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            lock_opinion_payload(value)
            reject_client_provenance_keys(value)
        return value

    @field_validator("note")
    @classmethod
    def _reject_soul_or_controls(
        cls, value: Optional[str], info: ValidationInfo
    ) -> Optional[str]:
        return reject_memory_write_text(
            value,
            field_name=str(info.field_name),
            max_length=FEEDBACK_NOTE_MAX_LENGTH,
        )


class AgentRunFeedbackRequest(_AgentFeedbackRequestBase):
    feedback_value: AgentRunFeedbackValue


class AgentPredictionFeedbackRequest(_AgentFeedbackRequestBase):
    feedback_value: AgentPredictionFeedbackValue


class AgentRunFeedbackItem(BaseModel):
    run_id: str
    feedback_value: Optional[AgentRunFeedbackValue] = None
    note: Optional[str] = None
    source: Optional[AgentFeedbackSource] = None
    provenance_source: Optional[MemoryProvenanceSource] = None
    actor_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentPredictionFeedbackItem(BaseModel):
    prediction_id: str
    feedback_value: Optional[AgentPredictionFeedbackValue] = None
    note: Optional[str] = None
    source: Optional[AgentFeedbackSource] = None
    provenance_source: Optional[MemoryProvenanceSource] = None
    actor_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
