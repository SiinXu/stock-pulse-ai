# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Administrator-only security diagnostics: audit events and outbound activity."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from api.deps import SecurityAuditQueryService, require_security_audit_query_service
from api.v1.errors import api_error
from api.v1.schemas.common import ErrorResponse
from src.auth import COOKIE_NAME, is_auth_enabled, verify_session
from src.schemas.outbound_activity import (
    OUTBOUND_ACTIVITY_MAX_PAGE_SIZE,
    LocalOnlyModeStatus,
    OutboundActivityItem,
    OutboundActivityPage,
)
from src.schemas.security_audit import (
    SECURITY_AUDIT_MAX_PAGE_SIZE,
    SecurityAuditEventPage,
)
from src.security.outbound_policy import (
    LOCAL_ONLY_MODE_ENV,
    OUTBOUND_ACTIVITY_MAX_RECORDS,
    get_outbound_activity,
    is_local_only_mode,
)
from src.services.security_audit_service import SecurityAuditUnavailable


router = APIRouter()


def _require_security_read_access(request: Request, *, auth_required_code: str) -> None:
    if not is_auth_enabled():
        if auth_required_code == "security_audit_auth_required":
            raise api_error(
                403,
                auth_required_code,
                "Security audit access requires enabled administrator authentication",
            )
        return
    session_cookie = request.cookies.get(COOKIE_NAME)
    if not session_cookie or not verify_session(session_cookie):
        raise api_error(401, "unauthorized", "Administrator authentication required")


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
        "pending", "success", "denied", "failure", "accepted", "rejected",
    ] | None = Query(None),
    correlation_id: str | None = Query(None, min_length=16, max_length=64),
    occurred_from: datetime | None = Query(None),
    occurred_to: datetime | None = Query(None),
    service: SecurityAuditQueryService = Depends(require_security_audit_query_service),
) -> SecurityAuditEventPage:
    service = require_security_audit_query_service(service)
    _require_security_read_access(request, auth_required_code="security_audit_auth_required")
    for value in (occurred_from, occurred_to):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise api_error(400, "validation_error", "Security audit timestamps must include a timezone")
    if occurred_from is not None and occurred_to is not None and occurred_from > occurred_to:
        raise api_error(400, "validation_error", "Security audit time range is invalid")
    try:
        return service.list_events(
            page=page, page_size=page_size, event_type=event_type, outcome=outcome,
            correlation_id=correlation_id, occurred_from=occurred_from, occurred_to=occurred_to,
        )
    except SecurityAuditUnavailable:
        raise api_error(503, "security_audit_unavailable", "Security audit storage is unavailable")


@router.get("/local-only", response_model=LocalOnlyModeStatus, responses={401: {"model": ErrorResponse}}, summary="Read LOCAL_ONLY_MODE enforcement status")
def get_local_only_mode_status(request: Request) -> LocalOnlyModeStatus:
    _require_security_read_access(request, auth_required_code="outbound_activity_auth_required")
    return LocalOnlyModeStatus(
        enabled=is_local_only_mode(),
        env_key=LOCAL_ONLY_MODE_ENV,
        policy="non_loopback_denied",
        allowed_destination_classes=["loopback"],
        blocked_error_reason="local_only_mode_blocked",
    )


@router.get("/outbound-activity", response_model=OutboundActivityPage, responses={401: {"model": ErrorResponse}}, summary="List recent outbound HTTP policy decisions")
def list_outbound_activity(request: Request, limit: int = Query(50, ge=1, le=OUTBOUND_ACTIVITY_MAX_PAGE_SIZE)) -> OutboundActivityPage:
    _require_security_read_access(request, auth_required_code="outbound_activity_auth_required")
    records = get_outbound_activity(limit=limit)
    items = [
        OutboundActivityItem(
            occurred_at=record.occurred_at,
            decision="allowed" if record.decision == "allowed" else "blocked",
            destination_class=record.destination_class,
            scheme=record.scheme,
            host_type=record.host_type,
            reason=record.reason,
            correlation_id=record.correlation_id,
            local_only_mode=record.local_only_mode,
            allowlisted=record.allowlisted,
        )
        for record in records
    ]
    return OutboundActivityPage(
        local_only_mode=is_local_only_mode(),
        items=items,
        limit=limit,
        returned=len(items),
        max_retained=OUTBOUND_ACTIVITY_MAX_RECORDS,
    )
