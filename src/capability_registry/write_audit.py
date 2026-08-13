# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed security-audit adapter for capability write-side mutations."""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Protocol

from src.utils.sanitize import log_safe_exception, redact_sensitive_data

logger = logging.getLogger(__name__)

CAPABILITY_WRITE_EVENT_TYPE = "capability.write"
CAPABILITY_TARGET_TYPE = "capability"
CAPABILITY_ACTOR_TYPE = "administrator"
CAPABILITY_ACTOR_ID = "capability_registry"

_STABLE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_MAX_METADATA_KEYS = 16
_MAX_STRING = 256

_ACTION_BY_OPERATION: Mapping[str, str] = {
    "register": "capability.register",
    "update": "capability.update",
    "retire": "capability.retire",
}


class CapabilityWriteAuditRecorder(Protocol):
    def record_attempt(self, **fields: Any) -> Any: ...
    def record_completion(self, **fields: Any) -> Any: ...


def _bounded_identity(value: str, *, fallback: str) -> str:
    candidate = value.strip() if type(value) is str else ""
    if candidate and _IDENTITY_PATTERN.fullmatch(candidate) is not None:
        return candidate[:128]
    return fallback


def _bounded_stable_name(value: str, *, fallback: str) -> str:
    candidate = value.strip().replace(" ", "_").lower() if type(value) is str else ""
    if candidate and _STABLE_NAME_PATTERN.fullmatch(candidate) is not None:
        return candidate[:64]
    sanitized = re.sub(r"[^a-z0-9_.-]", ".", candidate.lower())
    sanitized = sanitized.strip(".-")
    if sanitized and _STABLE_NAME_PATTERN.fullmatch(sanitized) is not None:
        return sanitized[:64]
    return fallback


def _bounded_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    out: dict[str, Any] = {}
    for key, raw in list(metadata.items())[:_MAX_METADATA_KEYS]:
        if type(key) is not str or not key or len(key) > 64:
            continue
        if raw is None or type(raw) in {bool, int}:
            out[key] = raw
            continue
        if type(raw) is float:
            out[key] = raw
            continue
        if type(raw) is str:
            out[key] = raw[:_MAX_STRING]
            continue
        if isinstance(raw, (list, tuple)):
            items: list[Any] = []
            for item in list(raw)[:64]:
                if type(item) is str:
                    items.append(item[:_MAX_STRING])
                elif item is None or type(item) in {bool, int, float}:
                    items.append(item)
            out[key] = items
            continue
    redacted = redact_sensitive_data(out)
    return redacted if isinstance(redacted, dict) else {}


class CapabilityWriteAuditor:
    """Record attempt/completion pairs for capability write-side mutations."""

    def __init__(
        self,
        recorder: CapabilityWriteAuditRecorder | None = None,
        *,
        actor_type: str = CAPABILITY_ACTOR_TYPE,
        actor_id: str = CAPABILITY_ACTOR_ID,
    ) -> None:
        self._recorder = recorder
        self._actor_type = _bounded_stable_name(actor_type, fallback=CAPABILITY_ACTOR_TYPE)
        self._actor_id = _bounded_identity(actor_id, fallback=CAPABILITY_ACTOR_ID)

    def bind_recorder(self, recorder: CapabilityWriteAuditRecorder | None) -> None:
        self._recorder = recorder

    def _resolve_recorder(self) -> CapabilityWriteAuditRecorder:
        if self._recorder is not None:
            return self._recorder
        from src.services.security_audit_service import (
            SecurityAuditUnavailable,
            get_security_audit_service,
            require_security_audit_recorder,
        )

        try:
            recorder = require_security_audit_recorder(get_security_audit_service())
        except Exception as exc:  # broad-exception: fallback_recorded - fail closed
            log_safe_exception(
                logger,
                "Capability write audit service unavailable",
                exc,
                error_code="capability_write_audit_unavailable",
            )
            raise SecurityAuditUnavailable() from None
        self._recorder = recorder
        return recorder

    def begin(
        self,
        *,
        capability_id: str,
        operation: str,
        metadata: Mapping[str, Any] | None = None,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> str:
        from src.services.security_audit_service import (
            SecurityAuditService,
            SecurityAuditUnavailable,
        )

        action = _ACTION_BY_OPERATION.get(operation)
        if action is None:
            raise ValueError(f"unsupported capability write operation: {operation}")
        recorder = self._resolve_recorder()
        try:
            correlation_id = SecurityAuditService.new_correlation_id()
            execution_id = _bounded_identity(
                f"capability-{capability_id}-{operation}",
                fallback="capability-write",
            )
            target_id = _bounded_identity(capability_id, fallback="unknown-capability")
            recorder.record_attempt(
                event_type=CAPABILITY_WRITE_EVENT_TYPE,
                actor_type=_bounded_stable_name(
                    actor_type or self._actor_type,
                    fallback=self._actor_type,
                ),
                actor_id=_bounded_identity(
                    actor_id or self._actor_id,
                    fallback=self._actor_id,
                ),
                execution_id=execution_id,
                action=action,
                target_type=CAPABILITY_TARGET_TYPE,
                target_id=target_id,
                correlation_id=correlation_id,
                metadata=_bounded_metadata(metadata),
            )
            return correlation_id
        except SecurityAuditUnavailable:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - fail closed
            log_safe_exception(
                logger,
                "Capability write audit attempt failed",
                exc,
                error_code="capability_write_audit_attempt_failed",
                context={"capability_id": capability_id, "operation": operation},
            )
            raise SecurityAuditUnavailable() from None

    def complete(
        self,
        *,
        capability_id: str,
        operation: str,
        success: bool,
        correlation_id: str,
        error_code: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        from src.services.security_audit_service import SecurityAuditUnavailable

        action = _ACTION_BY_OPERATION.get(operation)
        if action is None:
            raise ValueError(f"unsupported capability write operation: {operation}")
        recorder = self._resolve_recorder()
        try:
            execution_id = _bounded_identity(
                f"capability-{capability_id}-{operation}",
                fallback="capability-write",
            )
            target_id = _bounded_identity(capability_id, fallback="unknown-capability")
            if success:
                outcome = "success"
                reason = f"capability_{operation}_succeeded"
            else:
                outcome = "failure"
                reason = error_code or f"capability_{operation}_failed"
            reason_code = _bounded_stable_name(reason, fallback="capability_write_failed")
            payload = dict(metadata or {})
            if error_code:
                payload.setdefault("error_code", error_code)
            recorder.record_completion(
                event_type=CAPABILITY_WRITE_EVENT_TYPE,
                actor_type=_bounded_stable_name(
                    actor_type or self._actor_type,
                    fallback=self._actor_type,
                ),
                actor_id=_bounded_identity(
                    actor_id or self._actor_id,
                    fallback=self._actor_id,
                ),
                execution_id=execution_id,
                action=action,
                target_type=CAPABILITY_TARGET_TYPE,
                target_id=target_id,
                outcome=outcome,
                reason_code=reason_code,
                correlation_id=correlation_id,
                metadata=_bounded_metadata(payload),
            )
        except SecurityAuditUnavailable:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - fail closed
            log_safe_exception(
                logger,
                "Capability write audit completion failed",
                exc,
                error_code="capability_write_audit_completion_failed",
                context={
                    "capability_id": capability_id,
                    "operation": operation,
                    "error_code": error_code,
                },
            )
            raise SecurityAuditUnavailable() from None
