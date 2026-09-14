# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Strict contracts for the agent evolution episode log (Issue #1090).

Episodes are append-oriented records for offline eval, weight calibration, and
post-mortem. Default payloads exclude secrets, raw provider bodies, and full
Agent Soul charter text; only ``soul_version`` / ``soul_hash`` may be stored.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.schemas.memory_fact_opinion import FACT_FIELD_NAMES
from src.schemas.memory_write_guard import (
    MemoryWriteRejectedError,
    reject_memory_write_text,
)

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

# Secret-free router subset persisted under outcome_labels_json (#1120).
# error / explain / raw overrides are intentionally absent.
EPISODE_ROUTER_MODES: Tuple[str, ...] = ("quick", "standard", "full", "specialist")
EPISODE_ROUTER_CHAT_PATHS: Tuple[str, ...] = ("incremental_tool", "full_repipeline")
EPISODE_ROUTER_REASON_CODES: Tuple[str, ...] = (
    "explicit_override",
    "default_standard",
    "quick_eligible",
    "floor_need_risk",
    "floor_compare",
    "floor_multi_symbol",
    "floor_need_news",
    "invalid_override",
    "invalid_intent",
    "invalid_symbol_count",
    "invalid_flag",
    "invalid_entry_kind",
    "invalid_miss_rate",
    "invalid_request",
    "unknown_field",
    "inconsistent_facts",
)
_EPISODE_ROUTER_MODE_SET = frozenset(EPISODE_ROUTER_MODES)
_EPISODE_ROUTER_CHAT_PATH_SET = frozenset(EPISODE_ROUTER_CHAT_PATHS)
_EPISODE_ROUTER_REASON_SET = frozenset(EPISODE_ROUTER_REASON_CODES)
_ROUTER_DECISION_SOURCE_KEY = "router_decision"


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
    router_accepted: Optional[bool] = None
    router_mode: Optional[Literal["quick", "standard", "full", "specialist"]] = None
    router_chat_path: Optional[Literal["incremental_tool", "full_repipeline"]] = None
    router_reason_code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    extra: Dict[str, str] = Field(default_factory=dict)

    @field_validator("user_feedback")
    @classmethod
    def _reject_soul_user_feedback(cls, value: Optional[str]) -> Optional[str]:
        return reject_memory_write_text(
            value,
            field_name="user_feedback",
            max_length=AGENT_EPISODE_MAX_STRING,
        )

    @field_validator("router_reason_code")
    @classmethod
    def _allowlisted_router_reason(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        reject_memory_write_text(
            value,
            field_name="router_reason_code",
            max_length=64,
        )
        if value not in _EPISODE_ROUTER_REASON_SET:
            raise ValueError("router_reason_code is not an allowed router enum")
        return value

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


def _reject_router_enum_field(
    value: Any,
    *,
    field_name: str,
    allowed: frozenset[str],
) -> None:
    if value is None:
        return
    if isinstance(value, str):
        reject_memory_write_text(
            value,
            field_name=field_name,
            max_length=64,
        )
        if value in allowed:
            return
    raise MemoryWriteRejectedError(f"{field_name} is not an allowed router enum")


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
        accepted = getattr(labels, "router_accepted", None)
        if accepted is not None and type(accepted) is not bool:
            raise MemoryWriteRejectedError("router_accepted must be a boolean")
        _reject_router_enum_field(
            getattr(labels, "router_mode", None),
            field_name="router_mode",
            allowed=_EPISODE_ROUTER_MODE_SET,
        )
        _reject_router_enum_field(
            getattr(labels, "router_chat_path", None),
            field_name="router_chat_path",
            allowed=_EPISODE_ROUTER_CHAT_PATH_SET,
        )
        _reject_router_enum_field(
            getattr(labels, "router_reason_code", None),
            field_name="router_reason_code",
            allowed=_EPISODE_ROUTER_REASON_SET,
        )
    lessons = getattr(episode, "lessons", None) or []
    for lesson in lessons:
        reject_memory_write_text(
            getattr(lesson, "remedy", None),
            field_name="remedy",
            max_length=AGENT_EPISODE_MAX_REMEDY,
        )


def bounded_router_outcome_labels(decision: Any) -> Optional[Dict[str, Any]]:
    """Copy allowlisted router enums/bools; omit missing keys and secret-bearing fields."""
    if not isinstance(decision, Mapping):
        return None
    labels: Dict[str, Any] = {}
    accepted = decision.get("accepted")
    if type(accepted) is bool:
        labels["router_accepted"] = accepted
    mode = decision.get("mode")
    if mode in _EPISODE_ROUTER_MODE_SET:
        labels["router_mode"] = mode
    chat_path = decision.get("chat_path")
    if chat_path in _EPISODE_ROUTER_CHAT_PATH_SET:
        labels["router_chat_path"] = chat_path
    reason_code = decision.get("reason_code")
    if reason_code in _EPISODE_ROUTER_REASON_SET:
        labels["router_reason_code"] = reason_code
    return labels or None


def router_decision_from_planning_metadata(result: Any) -> Any:
    """Return ``planning_metadata['router_decision']`` when it is a mapping."""
    metadata = getattr(result, "planning_metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    decision = metadata.get(_ROUTER_DECISION_SOURCE_KEY)
    return decision if isinstance(decision, Mapping) else None


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
    provenance_source: Optional[str] = None
    actor_id: Optional[str] = None


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
    "EPISODE_ROUTER_CHAT_PATHS",
    "EPISODE_ROUTER_MODES",
    "EPISODE_ROUTER_REASON_CODES",
    "EpisodeLesson",
    "EpisodeOutcomeLabels",
    "TrajectoryStepSummary",
    "bounded_router_outcome_labels",
    "reject_episode_free_text",
    "router_decision_from_planning_metadata",
]
