# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Authenticated administrator API for Human-in-the-Loop approvals."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from api.deps import get_approval_service
from api.v1.errors import api_error
from api.v1.schemas.approvals import (
    ApprovalDecisionRequest,
    ApprovalProposal,
    ApprovalProposalPage,
    ApprovalRule,
    ApprovalRuleUpdateRequest,
)
from api.v1.schemas.common import ErrorResponse
from src.auth import COOKIE_NAME, is_auth_enabled, verify_session
from src.schemas.approvals import ApprovalStatus
from src.services.approval_service import (
    ApprovalService,
    ApprovalServiceInvalidTransitionError,
    ApprovalServiceNotFoundError,
    ApprovalServiceVersionConflictError,
)
from src.services.security_audit_service import SecurityAuditUnavailable
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)
router = APIRouter()
_ERROR_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def require_approval_administrator(request: Request) -> None:
    """Require auth to be configured and a current administrator session."""
    if not is_auth_enabled():
        raise api_error(
            403,
            "approval_auth_required",
            "Approval access requires enabled administrator authentication",
        )
    session_cookie = request.cookies.get(COOKIE_NAME)
    if not session_cookie or not verify_session(session_cookie):
        raise api_error(401, "unauthorized", "Administrator authentication required")


def _translate_error(exc: Exception):
    if isinstance(exc, ApprovalServiceNotFoundError):
        raise api_error(404, exc.error_code, str(exc)) from exc
    if isinstance(exc, ApprovalServiceVersionConflictError):
        raise api_error(
            409,
            exc.error_code,
            str(exc),
            params={"current_version": exc.current_version},
        ) from exc
    if isinstance(exc, ApprovalServiceInvalidTransitionError):
        raise api_error(409, exc.error_code, str(exc)) from exc
    if isinstance(exc, SecurityAuditUnavailable):
        raise api_error(
            503,
            "security_audit_unavailable",
            "Required security audit storage is unavailable",
        ) from exc


def _execute(operation):
    try:
        return operation()
    except (
        ApprovalServiceNotFoundError,
        ApprovalServiceVersionConflictError,
        ApprovalServiceInvalidTransitionError,
        SecurityAuditUnavailable,
    ) as exc:
        _translate_error(exc)
    except Exception as exc:  # broad-exception: fallback_recorded - Stable API envelope without leaking storage details.
        log_safe_exception(
            logger,
            "Approval API operation failed",
            exc,
            error_code="approval_internal_error",
        )
        raise api_error(500, "internal_error", "Approval operation failed") from exc


@router.get(
    "/rules/risk-control-bypass",
    response_model=ApprovalRule,
    responses=_ERROR_RESPONSES,
    summary="Read the risk-control bypass approval rule",
)
def get_risk_control_bypass_rule(
    request: Request,
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalRule:
    require_approval_administrator(request)
    return _execute(service.get_rule)


@router.put(
    "/rules/risk-control-bypass",
    response_model=ApprovalRule,
    responses=_ERROR_RESPONSES,
    summary="Update the risk-control bypass approval rule with CAS",
)
def put_risk_control_bypass_rule(
    body: ApprovalRuleUpdateRequest,
    request: Request,
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalRule:
    require_approval_administrator(request)
    return _execute(
        lambda: service.put_rule(
            enabled=body.enabled,
            risk_sources=body.risk_sources,
            expires_in_seconds=body.expires_in_seconds,
            expected_version=body.expected_version,
        )
    )


@router.get(
    "",
    response_model=ApprovalProposalPage,
    responses=_ERROR_RESPONSES,
    summary="List owner-scoped approval proposals",
)
def list_approvals(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Literal[
        "pending",
        "approved",
        "rejected",
        "expired",
        "cancelled",
    ]
    | None = Query(None),
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalProposalPage:
    require_approval_administrator(request)
    parsed_status = ApprovalStatus(status) if status is not None else None
    return _execute(
        lambda: service.list_proposals(
            page=page,
            page_size=page_size,
            status=parsed_status,
        )
    )


@router.get(
    "/{proposal_id}",
    response_model=ApprovalProposal,
    responses=_ERROR_RESPONSES,
    summary="Read one owner-scoped approval proposal",
)
def get_approval(
    proposal_id: str,
    request: Request,
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalProposal:
    require_approval_administrator(request)
    return _execute(lambda: service.get_proposal(proposal_id))


@router.post(
    "/{proposal_id}/decision",
    response_model=ApprovalProposal,
    responses=_ERROR_RESPONSES,
    summary="Decide a pending approval proposal with CAS",
)
def decide_approval(
    proposal_id: str,
    body: ApprovalDecisionRequest,
    request: Request,
    service: ApprovalService = Depends(get_approval_service),
) -> ApprovalProposal:
    require_approval_administrator(request)
    return _execute(
        lambda: service.decide(
            proposal_id,
            decision=body.decision,
            expected_version=body.expected_version,
        )
    )
