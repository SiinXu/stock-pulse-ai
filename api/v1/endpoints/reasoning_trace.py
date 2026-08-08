# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Opt-in reasoning-trace export endpoint (Issue #135 / T03).

Default-off. When enabled, exports a redacted ``reasoning-trace-v1`` package
built from persisted analysis history diagnostics. No Web UI.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response

from api.deps import get_database_manager
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
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


def _require_export_access(request: Request) -> None:
    """Mirror security-audit style admin gate when authentication is enabled."""
    if not is_auth_enabled():
        return
    session_cookie = request.cookies.get(COOKIE_NAME)
    if not session_cookie or not verify_session(session_cookie):
        raise api_error(401, "unauthorized", "Administrator authentication required")


@router.get(
    "/{record_id}",
    response_model=ReasoningTraceExportResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Export multi-agent reasoning trace for an analysis history record",
    description=(
        "Builds a redacted reasoning-trace-v1 package from already-recorded "
        "diagnostics and dashboard synthesis fields. Disabled by default "
        "(REASONING_TRACE_EXPORT_ENABLED=false). Secrets are never exported."
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
) -> Response | ReasoningTraceExportResponse:
    config = get_application_services().config
    if not bool(getattr(config, "reasoning_trace_export_enabled", False)):
        raise api_error(
            404,
            "reasoning_trace_export_disabled",
            "Reasoning trace export is not enabled",
        )

    _require_export_access(request)

    history = HistoryService(db_manager)
    service = ReasoningTraceExportService(history_service=history, config=config)
    try:
        result = service.export_for_record(
            record_id,
            format=format,
            include_markdown=include_markdown or format == "markdown",
        )
    except ReasoningTraceExportDisabled:
        raise api_error(
            404,
            "reasoning_trace_export_disabled",
            "Reasoning trace export is not enabled",
        )
    except ReasoningTraceNotFound:
        raise api_error(404, "not_found", "Analysis history record not found")
    except ValueError as exc:
        raise api_error(400, "validation_error", str(exc) or "Invalid diagnostic payload")
    except Exception as exc:  # broad-exception: fallback_recorded - Map unexpected export failures to a sanitized 500.
        log_safe_exception(
            logger,
            "Reasoning trace export failed",
            exc,
            error_code="reasoning_trace_export_failed",
            context={"record_id": record_id},
        )
        raise api_error(500, "internal_error", "Reasoning trace export failed")

    if format == "markdown":
        return Response(
            content=result.markdown or "",
            media_type="text/markdown; charset=utf-8",
            headers={
                "X-Reasoning-Trace-Schema": result.schema_version,
                "X-Reasoning-Trace-Truncated": "1" if result.truncated else "0",
            },
        )

    payload = dict(result.package)
    if include_markdown:
        payload["markdown"] = result.markdown
    return ReasoningTraceExportResponse.model_validate(payload)
