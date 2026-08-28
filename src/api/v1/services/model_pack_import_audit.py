# -*- coding: utf-8 -*-
"""HTTP Model Pack import security-audit helpers (#1062 DAG-7).

Production callers are the HTTP adapter ``import_model_pack``.
Worker completion, desktop activation, GET status, and raw TaskQueue
submit are not this event. Do not fold this into ``background.submit``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any, NoReturn

from fastapi import HTTPException

from src.api.v1.services.system_config_write_audit import (
    system_config_write_audit_actor_id,
)
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    SecurityAuditUnavailable,
    require_security_audit_recorder,
)
from src.utils.sanitize import redact_sensitive_data

MODEL_PACK_IMPORT_EVENT_TYPE = "model_pack.import"
MODEL_PACK_IMPORT_ACTION = "import"
MODEL_PACK_IMPORT_TARGET_TYPE = "model_pack_import_task"
MODEL_PACK_IMPORT_KIND = "model_pack_import"
MODEL_PACK_IMPORT_ACTOR_TYPE = "administrator"
UNKNOWN_IMPORT_TARGET_ID = "unknown-import"

_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_MAX_METADATA_KEYS = 16
_MAX_METADATA_STRING = 256
_ALLOWED_METADATA_KEYS = frozenset({"kind", "suffix", "byte_length", "status"})
_ALLOWED_SUFFIXES = frozenset({".modelpack", ".zip"})


class ModelPackImportAuditCompletionUnavailable(RuntimeError):
    """Raised when the queue already accepted but audit completion could not be stored."""

    def __init__(self, *, task_id: str, kind: str, status: str) -> None:
        super().__init__("security_audit_unavailable")
        self.task_id = task_id
        self.kind = kind
        self.status = status


def bounded_import_identity(value: Any, *, fallback: str) -> str:
    candidate = value.strip() if type(value) is str else ""
    if candidate and _IDENTITY_PATTERN.fullmatch(candidate) is not None:
        return candidate[:128]
    return fallback


def status_text(value: Any) -> str:
    raw = getattr(value, "value", value)
    if type(raw) is str and raw.strip():
        return raw.strip()[:64]
    return "unknown"


def bounded_import_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
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


def model_pack_import_metadata(
    *,
    suffix: str,
    byte_length: int,
    status: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"kind": MODEL_PACK_IMPORT_KIND}
    suffix_token = suffix if type(suffix) is str else ""
    if suffix_token in _ALLOWED_SUFFIXES:
        payload["suffix"] = suffix_token
    if type(byte_length) is int:
        payload["byte_length"] = byte_length
    if type(status) is str and status.strip():
        payload["status"] = status.strip()[:64]
    return bounded_import_metadata(payload)


def record_model_pack_import_audit(
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
        event_type=MODEL_PACK_IMPORT_EVENT_TYPE,
        actor_type=MODEL_PACK_IMPORT_ACTOR_TYPE,
        actor_id=system_config_write_audit_actor_id(),
        execution_id=correlation_id,
        action=MODEL_PACK_IMPORT_ACTION,
        target_type=MODEL_PACK_IMPORT_TARGET_TYPE,
        target_id=bounded_import_identity(
            task_id, fallback=UNKNOWN_IMPORT_TARGET_ID
        ),
        correlation_id=correlation_id,
        metadata=bounded_import_metadata(metadata),
    )
    if phase == "attempt":
        service.record_attempt(**common)
        return
    service.record_completion(
        **common,
        outcome=outcome,
        reason_code=reason_code,
    )


def record_model_pack_import_completion_best_effort(
    recorder: SecurityAuditRecorder,
    *,
    task_id: str,
    correlation_id: str,
    metadata: Mapping[str, Any] | None = None,
    outcome: str,
    reason_code: str,
) -> None:
    try:
        record_model_pack_import_audit(
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


def model_pack_import_audit_unavailable(
    exc: BaseException | None = None,
    *,
    operation_completed: bool = False,
) -> HTTPException:
    """Return the isolated TestClient 503 shape for import-audit outages."""
    completed = operation_completed
    extra: dict[str, object] = {}
    if isinstance(exc, ModelPackImportAuditCompletionUnavailable):
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
            "Model Pack import was accepted, but audit completion could not be persisted"
            if completed
            else "Security audit storage is unavailable"
        ),
        "operation_completed": completed,
    }
    detail.update(extra)
    return HTTPException(status_code=503, detail=detail)


def raise_model_pack_import_audit_unavailable(
    exc: BaseException | None = None,
    *,
    operation_completed: bool = False,
) -> NoReturn:
    raise model_pack_import_audit_unavailable(
        exc,
        operation_completed=operation_completed,
    ) from None


def map_model_pack_import_audit_exception(exc: BaseException) -> None:
    """Re-raise audit unavailability as HTTP 503; ignore other exceptions."""
    if isinstance(
        exc,
        (SecurityAuditUnavailable, ModelPackImportAuditCompletionUnavailable),
    ):
        raise_model_pack_import_audit_unavailable(exc)


def run_model_pack_import_with_audit(
    recorder: SecurityAuditRecorder,
    *,
    suffix: str,
    byte_length: int,
    start_import: Callable[[], Any],
) -> Any:
    """Record attempt, call start_import, then record accepted completion.

    Attempt-store failure raises ``SecurityAuditUnavailable`` before queue.
    After the queue accepts, completion-store failure raises
    ``ModelPackImportAuditCompletionUnavailable`` and does not roll back.
    Queue exceptions record failure best-effort, then re-raise the original error.
    """
    correlation_id = SecurityAuditService.new_correlation_id()
    bounded = model_pack_import_metadata(
        suffix=suffix,
        byte_length=byte_length,
    )
    record_model_pack_import_audit(
        recorder,
        phase="attempt",
        task_id=UNKNOWN_IMPORT_TARGET_ID,
        correlation_id=correlation_id,
        metadata=bounded,
    )
    try:
        task = start_import()
    except Exception:
        record_model_pack_import_completion_best_effort(
            recorder,
            task_id=UNKNOWN_IMPORT_TARGET_ID,
            correlation_id=correlation_id,
            metadata=bounded,
            outcome="failure",
            reason_code="submit_failed",
        )
        raise
    queued_id = bounded_import_identity(
        getattr(task, "task_id", None),
        fallback=UNKNOWN_IMPORT_TARGET_ID,
    )
    queued_status = status_text(getattr(task, "status", None))
    accepted = model_pack_import_metadata(
        suffix=suffix,
        byte_length=byte_length,
        status=queued_status,
    )
    try:
        record_model_pack_import_audit(
            recorder,
            phase="completion",
            task_id=queued_id,
            correlation_id=correlation_id,
            metadata=accepted,
            outcome="accepted",
            reason_code="accepted",
        )
    except SecurityAuditUnavailable:
        raise ModelPackImportAuditCompletionUnavailable(
            task_id=queued_id,
            kind=MODEL_PACK_IMPORT_KIND,
            status=queued_status,
        ) from None
    return task
