# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed security-audit adapter for capability write-side mutations."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping, NamedTuple, Protocol
from urllib.parse import unquote

from src.utils.sanitize import log_safe_exception, redact_sensitive_data

logger = logging.getLogger(__name__)

CAPABILITY_WRITE_EVENT_TYPE = "capability.write"
CAPABILITY_TARGET_TYPE = "capability"
CAPABILITY_ACTOR_TYPE = "administrator"
CAPABILITY_ACTOR_ID = "capability_registry"
CAPABILITY_DENIED_ACTOR_TYPE = "unauthenticated"
CAPABILITY_DENIED_ACTOR_ID = "unauthenticated"
CAPABILITY_DENIED_REASON_CODE = "unauthorized"
UNKNOWN_CAPABILITY_ID = "unknown-capability"
DENIED_BODY_PEEK_BYTES = 4096
CAPABILITY_REGISTRY_PATH = "/api/v1/capabilities/registry"

_STABLE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_MAX_METADATA_KEYS = 16
_MAX_STRING = 256

_ACTION_BY_OPERATION: Mapping[str, str] = {
    "register": "capability.register",
    "update": "capability.update",
    "retire": "capability.retire",
}


class CapabilityWriteMutation(NamedTuple):
    """Privileged capability-registry mutation classified from method + path."""

    operation: str
    path_capability_id: str


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


def classify_capability_write(method: str, path: str) -> CapabilityWriteMutation | None:
    """Return the privileged write mutation for this request, if any.

    GET inventory/registry reads and non-mutating resolve/route POSTs are
    excluded. Capability write routes are never auth-exempt; callers must still
    enforce authentication and only use this helper to attach a denied audit.
    """

    if type(method) is not str or type(path) is not str:
        return None
    verb = method.strip().upper()
    normalized = unquote(path.split("?", 1)[0]).rstrip("/") or "/"
    if normalized == CAPABILITY_REGISTRY_PATH:
        if verb == "POST":
            return CapabilityWriteMutation("register", "")
        return None
    prefix = CAPABILITY_REGISTRY_PATH + "/"
    if not normalized.startswith(prefix):
        return None
    rest = normalized[len(prefix) :]
    if not rest:
        return None
    if verb == "PUT" and "/" not in rest:
        return CapabilityWriteMutation("update", rest)
    retire_suffix = "/retire"
    if verb == "POST" and rest.endswith(retire_suffix):
        capability_id = rest[: -len(retire_suffix)]
        if capability_id and "/" not in capability_id:
            return CapabilityWriteMutation("retire", capability_id)
    return None


def peek_register_capability_id(
    body: bytes | bytearray | str | None,
    *,
    max_bytes: int = DENIED_BODY_PEEK_BYTES,
) -> str:
    """Extract a bounded capability_id from a register JSON body.

    Inspection is identity-only: other keys (including secrets/tokens) are
    never returned or copied. Oversized, invalid, or non-object bodies fall
    back to ``unknown-capability``.
    """

    if body is None:
        return UNKNOWN_CAPABILITY_ID
    if type(body) is str:
        raw = body.encode("utf-8")
    elif type(body) in {bytes, bytearray}:
        raw = bytes(body)
    else:
        return UNKNOWN_CAPABILITY_ID
    if not raw or len(raw) > max_bytes:
        return UNKNOWN_CAPABILITY_ID
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError, RecursionError):
        return UNKNOWN_CAPABILITY_ID
    if type(payload) is not dict:
        return UNKNOWN_CAPABILITY_ID
    value = payload.get("capability_id")
    if type(value) is not str:
        return UNKNOWN_CAPABILITY_ID
    return _bounded_identity(value, fallback=UNKNOWN_CAPABILITY_ID)


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

    def record_denied(
        self,
        *,
        capability_id: str,
        operation: str,
        reason_code: str = CAPABILITY_DENIED_REASON_CODE,
        metadata: Mapping[str, Any] | None = None,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> str:
        """Persist attempt + denied completion for a blocked privileged write."""

        from src.services.security_audit_service import SecurityAuditUnavailable

        denied_actor_type = actor_type or CAPABILITY_DENIED_ACTOR_TYPE
        denied_actor_id = actor_id or CAPABILITY_DENIED_ACTOR_ID
        correlation_id = self.begin(
            capability_id=capability_id,
            operation=operation,
            metadata=metadata,
            actor_type=denied_actor_type,
            actor_id=denied_actor_id,
        )
        action = _ACTION_BY_OPERATION.get(operation)
        if action is None:
            raise ValueError(f"unsupported capability write operation: {operation}")
        recorder = self._resolve_recorder()
        try:
            execution_id = _bounded_identity(
                f"capability-{capability_id}-{operation}",
                fallback="capability-write",
            )
            target_id = _bounded_identity(
                capability_id, fallback=UNKNOWN_CAPABILITY_ID
            )
            payload = dict(metadata or {})
            payload.setdefault("error_code", reason_code or CAPABILITY_DENIED_REASON_CODE)
            recorder.record_completion(
                event_type=CAPABILITY_WRITE_EVENT_TYPE,
                actor_type=_bounded_stable_name(
                    denied_actor_type,
                    fallback=CAPABILITY_DENIED_ACTOR_TYPE,
                ),
                actor_id=_bounded_identity(
                    denied_actor_id,
                    fallback=CAPABILITY_DENIED_ACTOR_ID,
                ),
                execution_id=execution_id,
                action=action,
                target_type=CAPABILITY_TARGET_TYPE,
                target_id=target_id,
                outcome="denied",
                reason_code=_bounded_stable_name(
                    reason_code,
                    fallback=CAPABILITY_DENIED_REASON_CODE,
                ),
                correlation_id=correlation_id,
                metadata=_bounded_metadata(payload),
            )
            return correlation_id
        except SecurityAuditUnavailable:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - fail closed
            log_safe_exception(
                logger,
                "Capability write denied-audit completion failed",
                exc,
                error_code="capability_write_denied_audit_failed",
                context={
                    "capability_id": capability_id,
                    "operation": operation,
                    "error_code": reason_code,
                },
            )
            raise SecurityAuditUnavailable() from None
