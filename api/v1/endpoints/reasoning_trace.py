# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in reasoning-trace export endpoint (Issue #135 / T03).

Default-off. When enabled, exports a redacted ``reasoning-trace-v1`` package
built from persisted analysis history diagnostics. No Web UI.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from api.deps import get_database_manager, require_security_audit_service
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.reasoning_trace import ReasoningTraceExportResponse
from src.application_services import get_application_services
from src.auth import COOKIE_NAME, is_auth_enabled, verify_session
from src.services.history_service import HistoryService
from src.services.reasoning_trace_export_service import (
    ReasoningTraceExportDisabled,
    ReasoningTraceExportService,
    ReasoningTraceNotFound,
)
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    SecurityAuditUnavailable,
)
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


def _audit_target_id(record_id: str) -> str:
    """Return a bounded audit identity without persisting arbitrary route text."""
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,119}", record_id):
        return record_id
    return f"sha256:{hashlib.sha256(record_id.encode('utf-8')).hexdigest()[:24]}"


def _record_export_audit(
    security_audit: SecurityAuditRecorder,
    *,
    phase: Literal["attempt", "completion"],
    correlation_id: str,
    record_id: str,
    format: str,
    include_markdown: bool,
    outcome: Literal["success", "denied", "failure"] = "success",
    reason_code: str = "export_completed",
) -> None:
    common = {
        "event_type": "reasoning_trace.export",
        "actor_type": "administrator",
        "actor_id": "admin_session",
        "execution_id": correlation_id,
        "action": "reasoning_trace.export",
        "target_type": "analysis_history",
        "target_id": _audit_target_id(record_id),
        "correlation_id": correlation_id,
        "metadata": {
            "format": format,
            "include_markdown": include_markdown,
        },
    }
    try:
        if phase == "attempt":
            security_audit.record_attempt(**common)
        else:
            security_audit.record_completion(
                **common,
                outcome=outcome,
                reason_code=reason_code,
            )
    except SecurityAuditUnavailable:
        raise api_error(
            503,
            "security_audit_unavailable",
            "Security audit storage is unavailable",
        ) from None


def _download_headers(result, *, record_id: str, extension: str) -> dict[str, str]:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", record_id)[:80] or "record"
    return {
        "Cache-Control": "private, no-store",
        "Pragma": "no-cache",
        "Content-Disposition": f'attachment; filename="reasoning-trace-{safe_id}.{extension}"',
        "X-Content-Type-Options": "nosniff",
        "X-Reasoning-Trace-Schema": result.schema_version,
        "X-Reasoning-Trace-Truncated": "1" if result.truncated else "0",
    }


def _require_export_access(request: Request) -> None:
    """Fail-closed admin gate for export (mirrors security-audit sensitivity).

    Reasoning traces may contain full decision context. When administrator
    authentication is disabled, refuse export rather than exposing the package
    without a session boundary.
    """
    if not is_auth_enabled():
        raise api_error(
            403,
            "reasoning_trace_auth_required",
            "Reasoning trace export requires enabled administrator authentication",
        )
    session_cookie = request.cookies.get(COOKIE_NAME)
    if not session_cookie or not verify_session(session_cookie):
        raise api_error(401, "unauthorized", "Administrator authentication required")


@router.get(
    "/{record_id}",
    response_model=ReasoningTraceExportResponse,
    responses={
        200: {
            "description": "Strict JSON trace package or inert Markdown export",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ReasoningTraceExportResponse"}
                },
                "text/markdown": {"schema": {"type": "string"}},
            },
        },
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="Export multi-agent reasoning trace for an analysis history record",
    description=(
        "Builds a redacted reasoning-trace-v1 package from already-recorded "
        "diagnostics and dashboard synthesis fields. Disabled by default "
        "(REASONING_TRACE_EXPORT_ENABLED=false). Supported credential and local-path "
        "classes are redacted; operators must still treat exports as sensitive."
    ),
    operation_id="exportReasoningTrace",
)
def export_reasoning_trace(
    request: Request,
    record_id: str,
    format: Literal["json", "markdown"] = Query(
        "json",
        description="json returns the package envelope; markdown returns text/markdown body",
    ),
    include_markdown: bool = Query(
        False,
        description="When format=json, also embed a redacted markdown companion field",
    ),
    db_manager: DatabaseManager = Depends(get_database_manager),
    security_audit: SecurityAuditRecorder = Depends(require_security_audit_service),
) -> Response:
    config = get_application_services().config
    if not bool(getattr(config, "reasoning_trace_export_enabled", False)):
        raise api_error(
            404,
            "reasoning_trace_export_disabled",
            "Reasoning trace export is not enabled",
        )

    _require_export_access(request)

    correlation_id = SecurityAuditService.new_correlation_id()
    _record_export_audit(
        security_audit,
        phase="attempt",
        correlation_id=correlation_id,
        record_id=record_id,
        format=format,
        include_markdown=include_markdown,
    )

    history = HistoryService(db_manager)
    service = ReasoningTraceExportService(history_service=history, config=config)
    try:
        result = service.export_for_record(
            record_id,
            format=format,
            include_markdown=include_markdown or format == "markdown",
        )
    except ReasoningTraceExportDisabled:
        _record_export_audit(
            security_audit,
            phase="completion",
            correlation_id=correlation_id,
            record_id=record_id,
            format=format,
            include_markdown=include_markdown,
            outcome="denied",
            reason_code="export_disabled",
        )
        raise api_error(
            404,
            "reasoning_trace_export_disabled",
            "Reasoning trace export is not enabled",
        )
    except ReasoningTraceNotFound:
        _record_export_audit(
            security_audit,
            phase="completion",
            correlation_id=correlation_id,
            record_id=record_id,
            format=format,
            include_markdown=include_markdown,
            outcome="denied",
            reason_code="record_not_found",
        )
        raise api_error(404, "not_found", "Analysis history record not found")
    except ValueError as exc:
        _record_export_audit(
            security_audit,
            phase="completion",
            correlation_id=correlation_id,
            record_id=record_id,
            format=format,
            include_markdown=include_markdown,
            outcome="failure",
            reason_code="invalid_diagnostic_payload",
        )
        raise api_error(400, "validation_error", str(exc) or "Invalid diagnostic payload")
    except Exception as exc:  # broad-exception: fallback_recorded - Map unexpected export failures to a sanitized 500.
        log_safe_exception(
            logger,
            "Reasoning trace export failed",
            exc,
            error_code="reasoning_trace_export_failed",
            context={"record_id": record_id},
        )
        _record_export_audit(
            security_audit,
            phase="completion",
            correlation_id=correlation_id,
            record_id=record_id,
            format=format,
            include_markdown=include_markdown,
            outcome="failure",
            reason_code="export_failed",
        )
        raise api_error(500, "internal_error", "Reasoning trace export failed")

    try:
        ReasoningTraceExportResponse.model_validate(result.package)
    except ValueError as exc:
        _record_export_audit(
            security_audit,
            phase="completion",
            correlation_id=correlation_id,
            record_id=record_id,
            format=format,
            include_markdown=include_markdown,
            outcome="failure",
            reason_code="response_contract_invalid",
        )
        log_safe_exception(
            logger,
            "Reasoning trace response contract validation failed",
            exc,
            error_code="reasoning_trace_response_invalid",
            context={"record_id": record_id},
        )
        raise api_error(500, "internal_error", "Reasoning trace export failed")

    _record_export_audit(
        security_audit,
        phase="completion",
        correlation_id=correlation_id,
        record_id=record_id,
        format=format,
        include_markdown=include_markdown,
        outcome="success",
        reason_code="export_completed",
    )

    if format == "markdown":
        return Response(
            content=result.markdown or "",
            media_type="text/markdown; charset=utf-8",
            headers=_download_headers(result, record_id=record_id, extension="md"),
        )

    return Response(
        content=result.to_json_text(),
        media_type="application/json",
        headers=_download_headers(result, record_id=record_id, extension="json"),
    )
