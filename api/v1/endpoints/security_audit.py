# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Administrator-only query endpoint for durable security audit events."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from api.deps import get_security_audit_service
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from src.auth import COOKIE_NAME, is_auth_enabled, verify_session
from src.schemas.security_audit import (
    SECURITY_AUDIT_MAX_PAGE_SIZE,
    SecurityAuditEventPage,
)
from src.services.security_audit_service import (
    SecurityAuditService,
    SecurityAuditUnavailable,
)


router = APIRouter()


@router.get(
    "/audit-events",
    response_model=SecurityAuditEventPage,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="List privileged-operation security audit events",
)
def list_security_audit_events(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=SECURITY_AUDIT_MAX_PAGE_SIZE),
    event_type: str | None = Query(None, min_length=1, max_length=64),
    outcome: Literal[
        "pending",
        "success",
        "denied",
        "failure",
        "accepted",
        "rejected",
    ]
    | None = Query(None),
    correlation_id: str | None = Query(None, min_length=16, max_length=64),
    occurred_from: datetime | None = Query(None),
    occurred_to: datetime | None = Query(None),
    service: SecurityAuditService = Depends(get_security_audit_service),
) -> SecurityAuditEventPage:
    """Return a bounded page only to an authenticated administrator session."""
    if not is_auth_enabled():
        raise api_error(
            403,
            "security_audit_auth_required",
            "Security audit access requires enabled administrator authentication",
        )
    session_cookie = request.cookies.get(COOKIE_NAME)
    if not session_cookie or not verify_session(session_cookie):
        raise api_error(401, "unauthorized", "Administrator authentication required")
    for value in (occurred_from, occurred_to):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise api_error(
                400,
                "validation_error",
                "Security audit timestamps must include a timezone",
            )
    if occurred_from is not None and occurred_to is not None and occurred_from > occurred_to:
        raise api_error(
            400,
            "validation_error",
            "Security audit time range is invalid",
        )
    try:
        return service.list_events(
            page=page,
            page_size=page_size,
            event_type=event_type,
            outcome=outcome,
            correlation_id=correlation_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )
    except SecurityAuditUnavailable:
        raise api_error(
            503,
            "security_audit_unavailable",
            "Security audit storage is unavailable",
        )
