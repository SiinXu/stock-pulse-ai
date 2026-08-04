# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Versioned contract for durable privileged-operation audit events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SECURITY_AUDIT_SCHEMA_VERSION: Literal["security-audit-v1"] = "security-audit-v1"
SECURITY_AUDIT_RETENTION_DAYS = 90
SECURITY_AUDIT_MAX_PAGE_SIZE = 100
SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS = 64
SECURITY_AUDIT_MAX_METADATA_STRING_LENGTH = 256

SecurityAuditPhase = Literal["attempt", "completion"]
SecurityAuditOutcome = Literal[
    "pending",
    "success",
    "denied",
    "failure",
    "accepted",
    "rejected",
]

_STABLE_NAME_PATTERN = r"^[a-z][a-z0-9_.-]{0,63}$"
_IDENTITY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$"
_CORRELATION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{15,63}$"
_MAX_METADATA_KEYS = 16


class _StrictAuditModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class SecurityAuditActor(_StrictAuditModel):
    """Bounded actor identity for the current single-admin execution model."""

    type: str = Field(pattern=_STABLE_NAME_PATTERN)
    id: str = Field(pattern=_IDENTITY_PATTERN)


class SecurityAuditTarget(_StrictAuditModel):
    """Bounded resource identity; values must never contain request payloads."""

    type: str = Field(pattern=_STABLE_NAME_PATTERN)
    id: str = Field(pattern=_IDENTITY_PATTERN)


def _bounded_metadata_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 2:
        raise ValueError("security audit metadata nesting is too deep")
    if value is None or type(value) in {bool, int, float}:
        return value
    if isinstance(value, str):
        if len(value) > SECURITY_AUDIT_MAX_METADATA_STRING_LENGTH:
            raise ValueError("security audit metadata string is too long")
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS:
            raise ValueError("security audit metadata list has too many items")
        return [
            _bounded_metadata_value(item, depth=depth + 1)
            for item in value
        ]
    if isinstance(value, dict):
        if len(value) > _MAX_METADATA_KEYS:
            raise ValueError("security audit metadata has too many keys")
        bounded = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key or len(key) > 64:
                raise ValueError("security audit metadata key is invalid")
            bounded[key] = _bounded_metadata_value(item, depth=depth + 1)
        return bounded
    raise ValueError("security audit metadata contains an unsupported value")


class SecurityAuditEventCreate(_StrictAuditModel):
    """Append-only event accepted by the security-audit service."""

    schema_version: Literal["security-audit-v1"] = SECURITY_AUDIT_SCHEMA_VERSION
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = Field(pattern=_STABLE_NAME_PATTERN)
    phase: SecurityAuditPhase
    actor: SecurityAuditActor
    execution_id: str = Field(min_length=1, max_length=128)
    action: str = Field(pattern=_STABLE_NAME_PATTERN)
    target: SecurityAuditTarget
    outcome: SecurityAuditOutcome
    reason_code: str = Field(pattern=_STABLE_NAME_PATTERN)
    correlation_id: str = Field(pattern=_CORRELATION_PATTERN)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def _occurred_at_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("security audit timestamp must be timezone-aware")
        normalized = value.astimezone(timezone.utc)
        if normalized.utcoffset() != timezone.utc.utcoffset(normalized):
            raise ValueError("security audit timestamp must normalize to UTC")
        return normalized

    @field_validator("metadata")
    @classmethod
    def _metadata_is_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        bounded = _bounded_metadata_value(value)
        if not isinstance(bounded, dict):
            raise ValueError("security audit metadata must be an object")
        return bounded

    @model_validator(mode="after")
    def _phase_matches_outcome(self) -> "SecurityAuditEventCreate":
        if self.phase == "attempt" and self.outcome != "pending":
            raise ValueError("security audit attempts must use pending outcome")
        if self.phase == "completion" and self.outcome == "pending":
            raise ValueError("security audit completions cannot use pending outcome")
        return self


class SecurityAuditEvent(SecurityAuditEventCreate):
    """Persisted event returned by the administrator query API."""

    id: int = Field(ge=1)


class SecurityAuditEventPage(_StrictAuditModel):
    """Bounded page returned by the administrator query API."""

    items: list[SecurityAuditEvent]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=SECURITY_AUDIT_MAX_PAGE_SIZE)
    total: int = Field(ge=0)
