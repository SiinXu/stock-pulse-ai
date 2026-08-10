# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Security-audit adapter for plugin lifecycle operations.

Plugin lifecycle is a privileged surface (enable / disable / reload / load).
Automatic startup loading uses best-effort writes so one unavailable recorder
does not block unrelated plugins. Administrator-requested mutations opt into
the existing fail-closed ``SecurityAuditService`` contract.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Protocol

from src.utils.sanitize import log_safe_exception, redact_sensitive_data


logger = logging.getLogger(__name__)

PLUGIN_LIFECYCLE_EVENT_TYPE = "plugin.lifecycle"
PLUGIN_TARGET_TYPE = "plugin"
PLUGIN_ACTOR_TYPE = "system"
PLUGIN_ACTOR_ID = "plugin_manager"

_STABLE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_MAX_METADATA_KEYS = 16
_MAX_STRING = 256

_ACTION_BY_OPERATION: Mapping[str, str] = {
    "load": "plugin.load",
    "enable": "plugin.enable",
    "disable": "plugin.disable",
    "reload": "plugin.reload",
}


class LifecycleAuditRecorder(Protocol):
    """Structural subset of ``SecurityAuditRecorder`` used by plugins."""

    def record_attempt(self, **fields: Any) -> Any:
        """Persist an attempt event before a privileged operation."""

    def record_completion(self, **fields: Any) -> Any:
        """Persist a completion event after a privileged operation."""


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


class PluginLifecycleAuditor:
    """Record attempt/completion pairs for plugin lifecycle transitions.

    Failures to persist audit events never propagate to the caller.
    """

    def __init__(
        self,
        recorder: LifecycleAuditRecorder | None = None,
        *,
        actor_type: str = PLUGIN_ACTOR_TYPE,
        actor_id: str = PLUGIN_ACTOR_ID,
    ) -> None:
        self._recorder = recorder
        self._actor_type = _bounded_stable_name(actor_type, fallback=PLUGIN_ACTOR_TYPE)
        self._actor_id = _bounded_identity(actor_id, fallback=PLUGIN_ACTOR_ID)

    @property
    def recorder(self) -> LifecycleAuditRecorder | None:
        return self._recorder

    def bind_recorder(self, recorder: LifecycleAuditRecorder | None) -> None:
        """Replace the recorder (tests and late composition wiring)."""

        self._recorder = recorder

    def _resolve_recorder(
        self,
        *,
        required: bool,
    ) -> LifecycleAuditRecorder | None:
        if self._recorder is not None:
            return self._recorder
        try:
            from src.services.security_audit_service import (
                get_security_audit_service,
                require_security_audit_recorder,
            )

            recorder = get_security_audit_service()
            resolved = require_security_audit_recorder(recorder)
            self._recorder = resolved
            return resolved
        except Exception as exc:  # broad-exception: fallback_recorded - caller selects fail-open startup or fail-closed operator semantics
            log_safe_exception(
                logger,
                "Plugin lifecycle audit service unavailable",
                exc,
                error_code="plugin_lifecycle_audit_unavailable",
            )
            if required:
                from src.services.security_audit_service import SecurityAuditUnavailable

                raise SecurityAuditUnavailable() from None
            return None

    def begin(
        self,
        *,
        plugin_id: str,
        operation: str,
        metadata: Mapping[str, Any] | None = None,
        required: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> str | None:
        """Record an attempt, failing closed when ``required`` is true."""

        action = _ACTION_BY_OPERATION.get(operation)
        if action is None:
            return None
        recorder = self._resolve_recorder(required=required)
        if recorder is None:
            return None
        try:
            from src.services.security_audit_service import SecurityAuditService

            correlation_id = SecurityAuditService.new_correlation_id()
            execution_id = _bounded_identity(
                f"plugin-{plugin_id}-{operation}",
                fallback="plugin-lifecycle",
            )
            target_id = _bounded_identity(plugin_id, fallback="unknown-plugin")
            recorder.record_attempt(
                event_type=PLUGIN_LIFECYCLE_EVENT_TYPE,
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
                target_type=PLUGIN_TARGET_TYPE,
                target_id=target_id,
                correlation_id=correlation_id,
                metadata=_bounded_metadata(metadata),
            )
            return correlation_id
        except Exception as exc:  # broad-exception: fallback_recorded - caller selects fail-open startup or fail-closed operator semantics
            log_safe_exception(
                logger,
                "Plugin lifecycle audit attempt failed",
                exc,
                error_code="plugin_lifecycle_audit_attempt_failed",
                context={"plugin_id": plugin_id, "operation": operation},
            )
            if required:
                from src.services.security_audit_service import SecurityAuditUnavailable

                raise SecurityAuditUnavailable() from None
            return None

    def complete(
        self,
        *,
        plugin_id: str,
        operation: str,
        success: bool,
        correlation_id: str | None,
        error_code: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        required: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        """Record completion, failing closed when ``required`` is true."""

        if correlation_id is None:
            return
        action = _ACTION_BY_OPERATION.get(operation)
        if action is None:
            return
        recorder = self._resolve_recorder(required=required)
        if recorder is None:
            return
        try:
            execution_id = _bounded_identity(
                f"plugin-{plugin_id}-{operation}",
                fallback="plugin-lifecycle",
            )
            target_id = _bounded_identity(plugin_id, fallback="unknown-plugin")
            if success:
                outcome = "success"
                reason = f"plugin_{operation}_succeeded"
            else:
                outcome = "failure"
                reason = error_code or f"plugin_{operation}_failed"
            reason_code = _bounded_stable_name(reason, fallback="plugin_lifecycle_failed")
            payload = dict(metadata or {})
            if error_code:
                payload.setdefault("error_code", error_code)
            recorder.record_completion(
                event_type=PLUGIN_LIFECYCLE_EVENT_TYPE,
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
                target_type=PLUGIN_TARGET_TYPE,
                target_id=target_id,
                outcome=outcome,
                reason_code=reason_code,
                correlation_id=correlation_id,
                metadata=_bounded_metadata(payload),
            )
        except Exception as exc:  # broad-exception: fallback_recorded - completion failure is surfaced for operator mutations
            log_safe_exception(
                logger,
                "Plugin lifecycle audit completion failed",
                exc,
                error_code="plugin_lifecycle_audit_completion_failed",
                context={
                    "plugin_id": plugin_id,
                    "operation": operation,
                    "error_code": error_code,
                },
            )
            if required:
                from src.services.security_audit_service import SecurityAuditUnavailable

                raise SecurityAuditUnavailable() from None
