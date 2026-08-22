# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Strict contracts for the agent evolution episode log (Issue #1090).

Episodes are append-oriented records for offline eval, weight calibration, and
post-mortem. Default payloads exclude secrets, raw provider bodies, and full
Agent Soul charter text; only ``soul_version`` / ``soul_hash`` may be stored.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.schemas.memory_fact_opinion import FACT_FIELD_NAMES
from src.schemas.memory_write_guard import reject_memory_write_text

AGENT_EPISODE_SCHEMA_VERSION: Literal["agent-episode-v1"] = "agent-episode-v1"

AGENT_EPISODE_DEFAULT_RETENTION_DAYS = 90
AGENT_EPISODE_MIN_RETENTION_DAYS = 1
AGENT_EPISODE_MAX_RETENTION_DAYS = 3650
AGENT_EPISODE_DEFAULT_MAX_ROWS = 50_000
AGENT_EPISODE_MIN_MAX_ROWS = 100
AGENT_EPISODE_MAX_MAX_ROWS = 1_000_000
AGENT_EPISODE_MAX_PAGE_SIZE = 200
AGENT_EPISODE_MAX_TRAJECTORY_STEPS = 64
AGENT_EPISODE_MAX_LESSONS = 8
AGENT_EPISODE_MAX_STRING = 256
AGENT_EPISODE_MAX_REMEDY = 300
AGENT_EPISODE_MAX_OUTCOME_KEYS = 16

_MODE_PATTERN = r"^[a-z][a-z0-9_.-]{0,31}$"
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$"
_SYMBOL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$"
_HASH_PATTERN = r"^(?:sha256:)?[a-f0-9]{8,128}$"


class _StrictEpisodeModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class TrajectoryStepSummary(_StrictEpisodeModel):
    """Compact, already-redacted tool/step summary for offline replay."""

    step: Optional[int] = Field(default=None, ge=0, le=10_000)
    tool: str = Field(min_length=1, max_length=128)
    success: bool
    cached: Optional[bool] = None
    timeout: Optional[bool] = None
    guarded: Optional[bool] = None
    duration_ms: Optional[int] = Field(default=None, ge=0, le=3_600_000)
    argument_fingerprint: Optional[str] = Field(
        default=None, min_length=8, max_length=64, pattern=r"^[a-f0-9]+$"
    )


class EpisodeLesson(_StrictEpisodeModel):
    """Bounded lesson projection for offline promotion and post-mortem."""

    kind: str = Field(min_length=1, max_length=64)
    severity: Literal["low", "medium", "high"] = "medium"
    claim_ref: Optional[str] = Field(default=None, max_length=128)
    remedy: Optional[str] = Field(default=None, max_length=AGENT_EPISODE_MAX_REMEDY)
    source_step: Optional[str] = Field(default=None, max_length=64)

    @field_validator("remedy")
    @classmethod
    def _reject_soul_remedy(cls, value: Optional[str]) -> Optional[str]:
        return reject_memory_write_text(
            value,
            field_name="remedy",
            max_length=AGENT_EPISODE_MAX_REMEDY,
        )


class EpisodeOutcomeLabels(_StrictEpisodeModel):
    """Optional additive outcome labels (never required for resolution)."""

    user_feedback: Optional[str] = Field(default=None, max_length=AGENT_EPISODE_MAX_STRING)
    forward_return_bucket: Optional[str] = Field(
        default=None, max_length=AGENT_EPISODE_MAX_STRING
    )
    manual_grade: Optional[str] = Field(default=None, max_length=64)
    prediction_outcome: Optional[str] = Field(default=None, max_length=64)
    prediction_id: Optional[str] = Field(default=None, max_length=128)
    extra: Dict[str, str] = Field(default_factory=dict)

    @field_validator("user_feedback")
    @classmethod
    def _reject_soul_user_feedback(cls, value: Optional[str]) -> Optional[str]:
        return reject_memory_write_text(
            value,
            field_name="user_feedback",
            max_length=AGENT_EPISODE_MAX_STRING,
        )

    @field_validator("extra")
    @classmethod
    def _bounded_extra(cls, value: Dict[str, str]) -> Dict[str, str]:
        if len(value) > AGENT_EPISODE_MAX_OUTCOME_KEYS:
            raise ValueError("outcome labels extra has too many keys")
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise ValueError("outcome labels extra key is invalid")
            if key in FACT_FIELD_NAMES:
                raise ValueError(
                    "outcome labels extra cannot carry PredictionOutcome actuals fields"
                )
            if not isinstance(item, str) or len(item) > AGENT_EPISODE_MAX_STRING:
                raise ValueError("outcome labels extra value is invalid")
            reject_memory_write_text(
                item,
                field_name="extra",
                max_length=AGENT_EPISODE_MAX_STRING,
            )
        return value


def reject_episode_free_text(episode: Any) -> None:
    """Reject Soul markers / illegal controls on persisted episode free-text."""
    labels = getattr(episode, "outcome_labels", None)
    if labels is not None:
        reject_memory_write_text(
            getattr(labels, "user_feedback", None),
            field_name="user_feedback",
            max_length=AGENT_EPISODE_MAX_STRING,
        )
        extra = getattr(labels, "extra", None) or {}
        if isinstance(extra, dict):
            for item in extra.values():
                reject_memory_write_text(
                    item,
                    field_name="extra",
                    max_length=AGENT_EPISODE_MAX_STRING,
                )
    lessons = getattr(episode, "lessons", None) or []
    for lesson in lessons:
        reject_memory_write_text(
            getattr(lesson, "remedy", None),
            field_name="remedy",
            max_length=AGENT_EPISODE_MAX_REMEDY,
        )


class AgentEpisodeCreate(_StrictEpisodeModel):
    """Append payload accepted by the episode service."""

    schema_version: Literal["agent-episode-v1"] = AGENT_EPISODE_SCHEMA_VERSION
    episode_id: str = Field(pattern=_ID_PATTERN)
    run_id: str = Field(pattern=_ID_PATTERN)
    mode: str = Field(pattern=_MODE_PATTERN)
    symbol: Optional[str] = Field(default=None, pattern=_SYMBOL_PATTERN)
    market: Optional[str] = Field(default=None, min_length=1, max_length=16)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    success: Optional[bool] = None
    soul_version: Optional[str] = Field(default=None, min_length=1, max_length=64)
    soul_hash: Optional[str] = Field(default=None, pattern=_HASH_PATTERN)
    trajectory_summary: List[TrajectoryStepSummary] = Field(
        default_factory=list, max_length=AGENT_EPISODE_MAX_TRAJECTORY_STEPS
    )
    lessons: List[EpisodeLesson] = Field(
        default_factory=list, max_length=AGENT_EPISODE_MAX_LESSONS
    )
    outcome_labels: Optional[EpisodeOutcomeLabels] = None
    soul_charter: Optional[str] = Field(default=None, max_length=0)

    @field_validator("soul_charter")
    @classmethod
    def _reject_charter(cls, value: Optional[str]) -> Optional[str]:
        if value:
            raise ValueError("soul_charter must not be stored on episodes")
        return None

    @field_validator("started_at", "completed_at", mode="before")
    @classmethod
    def _coerce_dt(cls, value: Any) -> Any:
        if value is None:
            return value
        parsed = value
        if isinstance(value, str) and value.strip():
            text = value.strip().replace("Z", "+00:00")
            parsed = datetime.fromisoformat(text)
        if not isinstance(parsed, datetime):
            raise ValueError("timestamp must be datetime or ISO-8601 string")
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return parsed.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _time_order(self) -> "AgentEpisodeCreate":
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("completed_at must not precede started_at")
        return self


class AgentEpisode(AgentEpisodeCreate):
    """Persisted episode with durable row identity."""

    id: int = Field(ge=1)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class AgentEpisodePage(_StrictEpisodeModel):
    """Bounded query page for offline jobs."""

    items: List[AgentEpisode]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=AGENT_EPISODE_MAX_PAGE_SIZE)


__all__ = [
    "AGENT_EPISODE_DEFAULT_MAX_ROWS",
    "AGENT_EPISODE_DEFAULT_RETENTION_DAYS",
    "AGENT_EPISODE_MAX_LESSONS",
    "AGENT_EPISODE_MAX_MAX_ROWS",
    "AGENT_EPISODE_MAX_PAGE_SIZE",
    "AGENT_EPISODE_MAX_RETENTION_DAYS",
    "AGENT_EPISODE_MAX_TRAJECTORY_STEPS",
    "AGENT_EPISODE_MIN_MAX_ROWS",
    "AGENT_EPISODE_MIN_RETENTION_DAYS",
    "AGENT_EPISODE_SCHEMA_VERSION",
    "AgentEpisode",
    "AgentEpisodeCreate",
    "AgentEpisodePage",
    "EpisodeLesson",
    "EpisodeOutcomeLabels",
    "TrajectoryStepSummary",
    "reject_episode_free_text",
]
