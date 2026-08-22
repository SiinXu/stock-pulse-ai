# -*- coding: utf-8 -*-
"""HTTP analysis-cancel security-audit helpers (#1062 DAG-3).

Production callers go through ``AnalysisApiService.cancel_analysis_task``.
Internal queue cancel, discovery cancel, and MCP cancel are not this event.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditUnavailable,
    require_security_audit_recorder,
)
from src.utils.sanitize import redact_sensitive_data

ANALYSIS_CANCEL_EVENT_TYPE = "analysis.cancel"
ANALYSIS_CANCEL_TARGET_TYPE = "analysis_task"
DEFAULT_ANALYSIS_CANCEL_ACTOR_TYPE = "api_client"
DEFAULT_ANALYSIS_CANCEL_ACTOR_ID = "analysis_canceller"
_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_MAX_METADATA_KEYS = 16
_MAX_METADATA_STRING = 256
_IDEMPOTENT_STATUSES = frozenset(
    {
        "cancel_requested",
        "cancelled",
        "completed",
        "failed",
        "interrupted",
    }
)


class AnalysisCancelAuditCompletionUnavailable(RuntimeError):
    """Raised when cancel already ran but audit completion could not be stored."""

    def __init__(self, *, task_id: str, status: str) -> None:
        super().__init__("security_audit_unavailable")
        self.task_id = task_id
        self.status = status


def bounded_cancel_identity(value: Any, *, fallback: str) -> str:
    candidate = value.strip() if type(value) is str else ""
    if candidate and _IDENTITY_PATTERN.fullmatch(candidate) is not None:
        return candidate[:128]
    return fallback


def status_text(value: Any) -> str:
    raw = getattr(value, "value", value)
    if type(raw) is str and raw.strip():
        return raw.strip()[:64]
    return "unknown"


def is_idempotent_status(status: str | None) -> bool:
    return type(status) is str and status in _IDEMPOTENT_STATUSES


def success_reason_code(status_after: str) -> str:
    if status_after == "cancel_requested":
        return "cancel_requested"
    if status_after == "cancelled":
        return "cancelled"
    if status_after in {"completed", "failed", "interrupted"}:
        return "already_terminal"
    return "cancel_requested"


def bounded_cancel_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    out: dict[str, Any] = {}
    for key, raw in list(metadata.items())[:_MAX_METADATA_KEYS]:
        if type(key) is not str or not key or len(key) > 64:
            continue
        if raw is None or type(raw) in {bool, int}:
            out[key] = raw
            continue
        if type(raw) is str:
            out[key] = raw[:_MAX_METADATA_STRING]
            continue
    redacted = redact_sensitive_data(out)
    return redacted if isinstance(redacted, dict) else {}


def cancel_metadata(
    task: Any,
    *,
    status_before: str | None = None,
    status_after: str | None = None,
    idempotent: bool | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    kind = getattr(task, "kind", None) if task is not None else None
    if type(kind) is str and kind:
        payload["kind"] = kind[:64]
    if type(status_before) is str and status_before:
        payload["status_before"] = status_before[:64]
    if type(status_after) is str and status_after:
        payload["status_after"] = status_after[:64]
    report_type = getattr(task, "report_type", None) if task is not None else None
    if type(report_type) is str and report_type:
        payload["report_type"] = report_type[:64]
    stock_code = getattr(task, "stock_code", None) if task is not None else None
    if type(stock_code) is str and stock_code:
        payload["stock_code"] = stock_code[:_MAX_METADATA_STRING]
    if idempotent is True:
        payload["idempotent"] = True
    return bounded_cancel_metadata(payload)


def record_analysis_cancel_audit(
    recorder: SecurityAuditRecorder,
    *,
    phase: str,
    task_id: str,
    correlation_id: str,
    metadata: Mapping[str, Any] | None = None,
    outcome: str = "pending",
    reason_code: str = "attempt_started",
) -> None:
    service = require_security_audit_recorder(recorder)
    common = dict(
        event_type=ANALYSIS_CANCEL_EVENT_TYPE,
        actor_type=DEFAULT_ANALYSIS_CANCEL_ACTOR_TYPE,
        actor_id=DEFAULT_ANALYSIS_CANCEL_ACTOR_ID,
        execution_id=correlation_id,
        action=ANALYSIS_CANCEL_EVENT_TYPE,
        target_type=ANALYSIS_CANCEL_TARGET_TYPE,
        target_id=bounded_cancel_identity(task_id, fallback="unknown-task"),
        correlation_id=correlation_id,
        metadata=bounded_cancel_metadata(metadata),
    )
    if phase == "attempt":
        service.record_attempt(**common)
        return
    service.record_completion(
        **common,
        outcome=outcome,
        reason_code=reason_code,
    )


def record_analysis_cancel_completion_best_effort(
    recorder: SecurityAuditRecorder,
    *,
    task_id: str,
    correlation_id: str,
    metadata: Mapping[str, Any] | None = None,
    outcome: str,
    reason_code: str,
) -> None:
    try:
        record_analysis_cancel_audit(
            recorder,
            phase="completion",
            task_id=task_id,
            correlation_id=correlation_id,
            metadata=metadata,
            outcome=outcome,
            reason_code=reason_code,
        )
    except SecurityAuditUnavailable:
        return


def record_analysis_cancel_audit_best_effort(
    recorder: SecurityAuditRecorder,
    *,
    task_id: str,
    correlation_id: str,
    metadata: Mapping[str, Any] | None = None,
    outcome: str,
    reason_code: str,
) -> None:
    try:
        record_analysis_cancel_audit(
            recorder,
            phase="attempt",
            task_id=task_id,
            correlation_id=correlation_id,
            metadata=metadata,
        )
    except SecurityAuditUnavailable:
        return
    record_analysis_cancel_completion_best_effort(
        recorder,
        task_id=task_id,
        correlation_id=correlation_id,
        metadata=metadata,
        outcome=outcome,
        reason_code=reason_code,
    )
