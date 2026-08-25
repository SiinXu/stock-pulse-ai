# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Strict contracts for the append-only EvolutionEvent store (Issue #1113).

This module is the persistence/query boundary only. It does not emit adapter,
overlay, planner, or skill-flag mutations. Payloads must stay JSON-safe and
must not store secrets, full system prompts, or raw provider bodies.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from typing import Any, FrozenSet, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.schemas.memory_write_guard import reject_memory_write_text


EVOLUTION_EVENT_SCHEMA_VERSION: Literal["evolution-event-v1"] = "evolution-event-v1"
EVOLUTION_EVENT_ACTORS: FrozenSet[str] = frozenset({"system", "user", "operator"})
EVOLUTION_EVENT_DEFAULT_LIMIT = 100
EVOLUTION_EVENT_MAX_LIMIT = 200
EVOLUTION_EVENT_MAX_REASON_REFS = 32
EVOLUTION_EVENT_MAX_SNAPSHOT_KEYS = 16
EVOLUTION_EVENT_MAX_SNAPSHOT_LIST_ITEMS = 64
EVOLUTION_EVENT_MAX_SNAPSHOT_STRING = 256
EVOLUTION_EVENT_MAX_SNAPSHOT_DEPTH = 2
EVOLUTION_EVENT_MAX_EVENT_TYPE = 64

EvolutionEventActor = Literal["system", "user", "operator"]

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$"
_EVENT_TYPE_PATTERN = r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$"
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "completion",
        "full_prompt",
        "messages",
        "password",
        "prompt",
        "provider_payload",
        "raw_payload",
        "raw_provider",
        "raw_response",
        "refresh_token",
        "secret",
        "soul",
        "soul_charter",
        "system_prompt",
        "token",
    }
)


class _StrictEvolutionModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


def _require_utc_datetime(value: Any, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _normalize_payload_key(key: Any) -> str:
    """Canonicalize snapshot keys for secret/prompt/provider-payload checks.

    CamelCase, hyphen, and dotted names collapse to snake_case so
    ``accessToken``, ``system-prompt``, and ``provider.payload`` match the
    same allowlist as ``access_token`` / ``system_prompt`` / ``provider_payload``.
    """
    text = str(key or "").strip()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _bounded_snapshot_value(value: Any, *, field_name: str, depth: int = 0) -> Any:
    if depth > EVOLUTION_EVENT_MAX_SNAPSHOT_DEPTH:
        raise ValueError(f"{field_name} nesting is too deep")
    if value is None or type(value) in {bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{field_name} number must be finite")
        return value
    if isinstance(value, str):
        reject_memory_write_text(
            value,
            field_name=field_name,
            max_length=EVOLUTION_EVENT_MAX_SNAPSHOT_STRING,
        )
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > EVOLUTION_EVENT_MAX_SNAPSHOT_LIST_ITEMS:
            raise ValueError(f"{field_name} list has too many items")
        return [
            _bounded_snapshot_value(item, field_name=field_name, depth=depth + 1)
            for item in value
        ]
    if isinstance(value, dict):
        if len(value) > EVOLUTION_EVENT_MAX_SNAPSHOT_KEYS:
            raise ValueError(f"{field_name} has too many keys")
        bounded: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise ValueError(f"{field_name} key is invalid")
            normalized = _normalize_payload_key(key)
            if normalized in _FORBIDDEN_PAYLOAD_KEYS:
                raise ValueError(
                    f"{field_name} must not persist secrets, prompts, or raw provider payloads"
                )
            bounded[key] = _bounded_snapshot_value(
                item,
                field_name=field_name,
                depth=depth + 1,
            )
        return bounded
    raise ValueError(f"{field_name} contains an unsupported value")


class EvolutionEventReasonRefs(_StrictEvolutionModel):
    """Structured correlation ids for later adapter/overlay producers."""

    prediction_ids: list[str] = Field(
        default_factory=list,
        max_length=EVOLUTION_EVENT_MAX_REASON_REFS,
    )
    run_ids: list[str] = Field(
        default_factory=list,
        max_length=EVOLUTION_EVENT_MAX_REASON_REFS,
    )

    @field_validator("prediction_ids", "run_ids")
    @classmethod
    def _bounded_ids(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        canonical: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("reason_refs ids must be strings")
            text = item.strip()
            if not text:
                raise ValueError("reason_refs ids must be nonempty")
            reject_memory_write_text(
                text,
                field_name="reason_refs",
                max_length=128,
            )
            if len(text) > 128:
                raise ValueError("reason_refs id is too long")
            if re.fullmatch(_ID_PATTERN, text) is None:
                raise ValueError("reason_refs id is invalid")
            if text not in seen:
                seen.add(text)
                canonical.append(text)
        return canonical


class EvolutionEventCreate(_StrictEvolutionModel):
    """Append payload accepted by the EvolutionEvent store."""

    schema_version: Literal["evolution-event-v1"] = EVOLUTION_EVENT_SCHEMA_VERSION
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex, pattern=_ID_PATTERN)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = Field(min_length=1, max_length=EVOLUTION_EVENT_MAX_EVENT_TYPE)
    actor: EvolutionEventActor
    reason_refs: EvolutionEventReasonRefs = Field(default_factory=EvolutionEventReasonRefs)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def _nonempty_event_type(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("event_type must be nonempty")
        if len(text) > EVOLUTION_EVENT_MAX_EVENT_TYPE:
            raise ValueError("event_type is too long")
        if re.fullmatch(_EVENT_TYPE_PATTERN, text) is None:
            raise ValueError("event_type is invalid")
        reject_memory_write_text(
            text,
            field_name="event_type",
            max_length=EVOLUTION_EVENT_MAX_EVENT_TYPE,
        )
        return text

    @field_validator("actor")
    @classmethod
    def _allowlisted_actor(cls, value: str) -> str:
        actor = str(value or "").strip()
        if actor not in EVOLUTION_EVENT_ACTORS:
            raise ValueError("actor must be system, user, or operator")
        return actor

    @field_validator("occurred_at")
    @classmethod
    def _occurred_at_is_utc(cls, value: datetime) -> datetime:
        return _require_utc_datetime(value, field_name="occurred_at")

    @field_validator("before", "after")
    @classmethod
    def _bounded_snapshot(cls, value: dict[str, Any], info: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(f"{info.field_name} must be an object")
        bounded = _bounded_snapshot_value(value, field_name=str(info.field_name))
        if not isinstance(bounded, dict):
            raise ValueError(f"{info.field_name} must be an object")
        return bounded

    @model_validator(mode="after")
    def _require_mutation(self) -> "EvolutionEventCreate":
        if self.before == self.after:
            raise ValueError("before and after must describe a mutation")
        return self


class EvolutionEvent(EvolutionEventCreate):
    """Persisted EvolutionEvent row returned by the store."""

    id: int = Field(ge=1)


def validate_query_window(
    occurred_from: datetime,
    occurred_to: datetime,
) -> tuple[datetime, datetime]:
    """Validate an inclusive UTC query window."""
    start = _require_utc_datetime(occurred_from, field_name="occurred_from")
    end = _require_utc_datetime(occurred_to, field_name="occurred_to")
    if start > end:
        raise ValueError("occurred_from must be less than or equal to occurred_to")
    return start, end


def validate_query_limit(limit: Optional[int]) -> int:
    """Reject non-integer, non-positive, or oversized query limits."""
    if limit is None:
        return EVOLUTION_EVENT_DEFAULT_LIMIT
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be an integer")
    if not 1 <= limit <= EVOLUTION_EVENT_MAX_LIMIT:
        raise ValueError(
            f"limit must be between 1 and {EVOLUTION_EVENT_MAX_LIMIT}"
        )
    return limit


def normalize_optional_event_type(event_type: Optional[str]) -> Optional[str]:
    """Exact type filter. Only ``None`` omits it; blank/whitespace fail closed."""
    if event_type is None:
        return None
    if not isinstance(event_type, str):
        raise ValueError("event_type must be a string")
    text = event_type.strip()
    if not text:
        raise ValueError("event_type filter must be nonempty")
    if len(text) > EVOLUTION_EVENT_MAX_EVENT_TYPE:
        raise ValueError("event_type is too long")
    if re.fullmatch(_EVENT_TYPE_PATTERN, text) is None:
        raise ValueError("event_type is invalid")
    reject_memory_write_text(
        text,
        field_name="event_type",
        max_length=EVOLUTION_EVENT_MAX_EVENT_TYPE,
    )
    return text
