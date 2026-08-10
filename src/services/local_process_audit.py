# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed security-audit helper for privileged local process invocations.

Covers real local-process boundaries that accept or reject work before/while a
subprocess or worker process runs (offline OCR, local CLI generation backends).
Payloads are redacted and size-bounded by ``SecurityAuditService``.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    SecurityAuditUnavailable,
    get_security_audit_service,
    require_security_audit_recorder,
)
from src.utils.sanitize import log_safe_exception, redact_sensitive_data


logger = logging.getLogger(__name__)

LOCAL_PROCESS_EVENT_TYPE = "local_process.execute"
LOCAL_PROCESS_TARGET_TYPE = "local_process"
LOCAL_PROCESS_ACTOR_TYPE = "system"
LOCAL_PROCESS_ACTOR_ID = "local_process"

_STABLE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_MAX_METADATA_KEYS = 16
_MAX_STRING = 256

_ACTION_BY_KIND = {
    "ocr": "local_process.ocr",
    "local_cli": "local_process.cli",
}


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


class LocalProcessAuditor:
    """Record attempt/completion pairs for local process privilege boundaries."""

    def __init__(
        self,
        recorder: SecurityAuditRecorder | None = None,
        *,
        actor_type: str = LOCAL_PROCESS_ACTOR_TYPE,
        actor_id: str = LOCAL_PROCESS_ACTOR_ID,
    ) -> None:
        self._recorder = recorder
        self._actor_type = _bounded_stable_name(actor_type, fallback=LOCAL_PROCESS_ACTOR_TYPE)
        self._actor_id = _bounded_identity(actor_id, fallback=LOCAL_PROCESS_ACTOR_ID)

    def bind_recorder(self, recorder: SecurityAuditRecorder | None) -> None:
        self._recorder = recorder

    def _resolve_recorder(self) -> SecurityAuditRecorder:
        if self._recorder is not None:
            return require_security_audit_recorder(self._recorder)
        try:
            resolved = require_security_audit_recorder(get_security_audit_service())
            self._recorder = resolved
            return resolved
        except SecurityAuditUnavailable:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - normalize any factory failure
            log_safe_exception(
                logger,
                "Local process audit service unavailable",
                exc,
                error_code="local_process_audit_unavailable",
            )
            raise SecurityAuditUnavailable() from None

    def begin(
        self,
        *,
        kind: str,
        target_id: str,
        execution_id: str,
        metadata: Mapping[str, Any] | None = None,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> str:
        """Persist an attempt before a local process is accepted or rejected."""
        action = _ACTION_BY_KIND.get(kind)
        if action is None:
            raise ValueError(f"unsupported local process kind: {kind!r}")
        recorder = self._resolve_recorder()
        correlation_id = SecurityAuditService.new_correlation_id()
        try:
            recorder.record_attempt(
                event_type=LOCAL_PROCESS_EVENT_TYPE,
                actor_type=_bounded_stable_name(
                    actor_type or self._actor_type,
                    fallback=self._actor_type,
                ),
                actor_id=_bounded_identity(
                    actor_id or self._actor_id,
                    fallback=self._actor_id,
                ),
                execution_id=_bounded_identity(execution_id, fallback=f"local-{kind}"),
                action=action,
                target_type=LOCAL_PROCESS_TARGET_TYPE,
                target_id=_bounded_identity(target_id, fallback=kind),
                correlation_id=correlation_id,
                metadata=_bounded_metadata(metadata),
            )
        except SecurityAuditUnavailable:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - keep stable unavailable contract
            log_safe_exception(
                logger,
                "Local process audit attempt failed",
                exc,
                error_code="local_process_audit_attempt_failed",
                context={"kind": kind, "target_id": target_id},
            )
            raise SecurityAuditUnavailable() from None
        return correlation_id

    def complete(
        self,
        *,
        kind: str,
        target_id: str,
        execution_id: str,
        correlation_id: str,
        outcome: str,
        reason_code: str,
        metadata: Mapping[str, Any] | None = None,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        """Persist a completion after a local process decision."""
        action = _ACTION_BY_KIND.get(kind)
        if action is None:
            raise ValueError(f"unsupported local process kind: {kind!r}")
        recorder = self._resolve_recorder()
        try:
            recorder.record_completion(
                event_type=LOCAL_PROCESS_EVENT_TYPE,
                actor_type=_bounded_stable_name(
                    actor_type or self._actor_type,
                    fallback=self._actor_type,
                ),
                actor_id=_bounded_identity(
                    actor_id or self._actor_id,
                    fallback=self._actor_id,
                ),
                execution_id=_bounded_identity(execution_id, fallback=f"local-{kind}"),
                action=action,
                target_type=LOCAL_PROCESS_TARGET_TYPE,
                target_id=_bounded_identity(target_id, fallback=kind),
                outcome=outcome,
                reason_code=_bounded_stable_name(reason_code, fallback="local_process_failed"),
                correlation_id=correlation_id,
                metadata=_bounded_metadata(metadata),
            )
        except SecurityAuditUnavailable:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - keep stable unavailable contract
            log_safe_exception(
                logger,
                "Local process audit completion failed",
                exc,
                error_code="local_process_audit_completion_failed",
                context={"kind": kind, "target_id": target_id, "outcome": outcome},
            )
            raise SecurityAuditUnavailable() from None


_default_auditor: Optional[LocalProcessAuditor] = None


def get_local_process_auditor() -> LocalProcessAuditor:
    """Process-wide default auditor (tests may replace via ``bind_recorder``)."""
    global _default_auditor
    if _default_auditor is None:
        _default_auditor = LocalProcessAuditor()
    return _default_auditor


def reset_local_process_auditor_for_tests() -> None:
    """Clear the process-wide auditor (tests only)."""
    global _default_auditor
    _default_auditor = None
