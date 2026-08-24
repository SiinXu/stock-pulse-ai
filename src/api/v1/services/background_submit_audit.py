# -*- coding: utf-8 -*-
"""HTTP background-submit security-audit helpers (#1062 DAG-6).

Production callers are the HTTP adapters that call ``submit_background_task``.
TaskQueue itself, discovery cancel, CLI/GHA, and ``analysis.submit`` are not
this event.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any, NoReturn

from fastapi import HTTPException

from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    SecurityAuditUnavailable,
    require_security_audit_recorder,
)
from src.utils.sanitize import redact_sensitive_data

BACKGROUND_SUBMIT_EVENT_TYPE = "background.submit"
BACKGROUND_SUBMIT_ACTION = "submit"
BACKGROUND_SUBMIT_TARGET_TYPE = "background_task"
DEFAULT_BACKGROUND_SUBMIT_ACTOR_TYPE = "api_client"
DEFAULT_BACKGROUND_SUBMIT_ACTOR_ID = "background_submitter"

KIND_MARKET_REVIEW = "market_review"
KIND_CANDIDATE_DISCOVERY = "candidate_discovery"
KIND_ALPHASIFT_SCREEN = "alphasift_screen"
BACKGROUND_SUBMIT_KINDS = frozenset(
    {KIND_MARKET_REVIEW, KIND_CANDIDATE_DISCOVERY, KIND_ALPHASIFT_SCREEN}
)

_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_MAX_METADATA_KEYS = 16
_MAX_METADATA_STRING = 256
_ALLOWED_METADATA_KEYS = frozenset(
    {
        "kind",
        "report_type",
        "stock_code",
        "region",
        "send_notification",
        "universe",
        "page",
        "page_size",
        "max_results",
        "max_provider_calls",
        "use_llm",
        "strategy",
        "market",
    }
)
_KIND_OPTIONAL_KEYS = {
    KIND_MARKET_REVIEW: frozenset({"region", "send_notification"}),
    KIND_CANDIDATE_DISCOVERY: frozenset(
        {"universe", "page", "page_size", "max_results", "max_provider_calls", "use_llm"}
    ),
    KIND_ALPHASIFT_SCREEN: frozenset({"strategy", "market", "max_results"}),
}


class BackgroundSubmitAuditCompletionUnavailable(RuntimeError):
    """Raised when the queue already accepted but audit completion could not be stored."""

    def __init__(self, *, task_id: str, kind: str, status: str) -> None:
        super().__init__("security_audit_unavailable")
        self.task_id = task_id
        self.kind = kind
        self.status = status


def bounded_submit_identity(value: Any, *, fallback: str) -> str:
    candidate = value.strip() if type(value) is str else ""
    if candidate and _IDENTITY_PATTERN.fullmatch(candidate) is not None:
        return candidate[:128]
    return fallback


def status_text(value: Any) -> str:
    raw = getattr(value, "value", value)
    if type(raw) is str and raw.strip():
        return raw.strip()[:64]
    return "unknown"


def bounded_submit_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    out: dict[str, Any] = {}
    for key, raw in list(metadata.items())[:_MAX_METADATA_KEYS]:
        if type(key) is not str or key not in _ALLOWED_METADATA_KEYS:
            continue
        if raw is None or type(raw) is bool:
            out[key] = raw
            continue
        if type(raw) is int:
            out[key] = raw
            continue
        if type(raw) is str:
            out[key] = raw[:_MAX_METADATA_STRING]
            continue
    redacted = redact_sensitive_data(out)
    return redacted if isinstance(redacted, dict) else {}


def background_submit_metadata(kind: str, **fields: Any) -> dict[str, Any]:
    kind_token = kind if kind in BACKGROUND_SUBMIT_KINDS else ""
    if not kind_token:
        kind_token = bounded_submit_identity(kind, fallback="unknown")
        if kind_token not in BACKGROUND_SUBMIT_KINDS:
            kind_token = "unknown"
    payload: dict[str, Any] = {
        "kind": kind_token,
        "report_type": kind_token,
        "stock_code": kind_token,
    }
    for key in _KIND_OPTIONAL_KEYS.get(kind_token, ()):
        if key not in fields:
            continue
        payload[key] = fields[key]
    return bounded_submit_metadata(payload)


def record_background_submit_audit(
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
        event_type=BACKGROUND_SUBMIT_EVENT_TYPE,
        actor_type=DEFAULT_BACKGROUND_SUBMIT_ACTOR_TYPE,
        actor_id=DEFAULT_BACKGROUND_SUBMIT_ACTOR_ID,
        execution_id=correlation_id,
        action=BACKGROUND_SUBMIT_ACTION,
        target_type=BACKGROUND_SUBMIT_TARGET_TYPE,
        target_id=bounded_submit_identity(task_id, fallback="unknown-task"),
        correlation_id=correlation_id,
        metadata=bounded_submit_metadata(metadata),
    )
    if phase == "attempt":
        service.record_attempt(**common)
        return
    service.record_completion(
        **common,
        outcome=outcome,
        reason_code=reason_code,
    )


def record_background_submit_completion_best_effort(
    recorder: SecurityAuditRecorder,
    *,
    task_id: str,
    correlation_id: str,
    metadata: Mapping[str, Any] | None = None,
    outcome: str,
    reason_code: str,
) -> None:
    try:
        record_background_submit_audit(
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


def background_submit_audit_unavailable(
    exc: BaseException | None = None,
    *,
    operation_completed: bool = False,
) -> HTTPException:
    """Return the isolated TestClient 503 shape for background-submit audit outages."""
    completed = operation_completed
    extra: dict[str, object] = {}
    if isinstance(exc, BackgroundSubmitAuditCompletionUnavailable):
        completed = True
        extra = {
            "task_id": exc.task_id,
            "kind": exc.kind,
            "status": exc.status,
        }
    elif isinstance(exc, SecurityAuditUnavailable):
        completed = False
    detail = {
        "error": "security_audit_unavailable",
        "message": (
            "Background task was accepted, but audit completion could not be persisted"
            if completed
            else "Security audit storage is unavailable"
        ),
        "operation_completed": completed,
    }
    detail.update(extra)
    return HTTPException(status_code=503, detail=detail)


def raise_background_submit_audit_unavailable(
    exc: BaseException | None = None,
    *,
    operation_completed: bool = False,
) -> NoReturn:
    raise background_submit_audit_unavailable(
        exc,
        operation_completed=operation_completed,
    ) from None


def map_background_submit_audit_exception(exc: BaseException) -> None:
    """Re-raise audit unavailability as HTTP 503; ignore other exceptions."""
    if isinstance(
        exc,
        (SecurityAuditUnavailable, BackgroundSubmitAuditCompletionUnavailable),
    ):
        raise_background_submit_audit_unavailable(exc)


def run_background_submit_with_audit(
    recorder: SecurityAuditRecorder,
    *,
    kind: str,
    task_id: str,
    metadata: Mapping[str, Any] | None,
    submit: Callable[[], Any],
    on_submit_exception: Callable[[BaseException], None] | None = None,
) -> Any:
    """Record attempt, call submit, then record accepted completion.

    Attempt-store failure raises ``SecurityAuditUnavailable`` before submit.
    After the queue accepts, completion-store failure raises
    ``BackgroundSubmitAuditCompletionUnavailable`` and does not roll back.
    Submit exceptions record failure best-effort, run ``on_submit_exception``,
    then re-raise the original error.
    """
    correlation_id = SecurityAuditService.new_correlation_id()
    bounded = background_submit_metadata(kind, **dict(metadata or {}))
    record_background_submit_audit(
        recorder,
        phase="attempt",
        task_id=task_id,
        correlation_id=correlation_id,
        metadata=bounded,
    )
    try:
        task = submit()
    except Exception as exc:
        record_background_submit_completion_best_effort(
            recorder,
            task_id=task_id,
            correlation_id=correlation_id,
            metadata=bounded,
            outcome="failure",
            reason_code="submit_failed",
        )
        if on_submit_exception is not None:
            on_submit_exception(exc)
        raise
    queued_id = bounded_submit_identity(getattr(task, "task_id", task_id), fallback=task_id)
    queued_status = status_text(getattr(task, "status", None))
    try:
        record_background_submit_audit(
            recorder,
            phase="completion",
            task_id=queued_id,
            correlation_id=correlation_id,
            metadata=bounded,
            outcome="accepted",
            reason_code="accepted",
        )
    except SecurityAuditUnavailable:
        raise BackgroundSubmitAuditCompletionUnavailable(
            task_id=queued_id,
            kind=bounded.get("kind") if type(bounded.get("kind")) is str else kind,
            status=queued_status,
        ) from None
    return task


def audited_market_review_submit(
    recorder: SecurityAuditRecorder,
    *,
    task_id: str,
    metadata: Mapping[str, Any] | None,
    acquire_lock: Callable[[], Any],
    submit: Callable[[Any], Any],
    release_lock: Callable[[Any], None],
    duplicate_error: Callable[[], BaseException],
) -> Any:
    """Market-review order: attempt, then lock, then queue, then accepted completion."""
    correlation_id = SecurityAuditService.new_correlation_id()
    bounded = background_submit_metadata(KIND_MARKET_REVIEW, **dict(metadata or {}))
    record_background_submit_audit(
        recorder,
        phase="attempt",
        task_id=task_id,
        correlation_id=correlation_id,
        metadata=bounded,
    )
    lock_token = acquire_lock()
    if lock_token is None:
        record_background_submit_completion_best_effort(
            recorder,
            task_id=task_id,
            correlation_id=correlation_id,
            metadata=bounded,
            outcome="rejected",
            reason_code="duplicate_market_review",
        )
        raise duplicate_error()
    try:
        task = submit(lock_token)
    except Exception as exc:
        record_background_submit_completion_best_effort(
            recorder,
            task_id=task_id,
            correlation_id=correlation_id,
            metadata=bounded,
            outcome="failure",
            reason_code="submit_failed",
        )
        release_lock(lock_token)
        raise exc
    queued_id = bounded_submit_identity(getattr(task, "task_id", task_id), fallback=task_id)
    queued_status = status_text(getattr(task, "status", None))
    try:
        record_background_submit_audit(
            recorder,
            phase="completion",
            task_id=queued_id,
            correlation_id=correlation_id,
            metadata=bounded,
            outcome="accepted",
            reason_code="accepted",
        )
    except SecurityAuditUnavailable:
        raise BackgroundSubmitAuditCompletionUnavailable(
            task_id=queued_id,
            kind=KIND_MARKET_REVIEW,
            status=queued_status,
        ) from None
    return task
