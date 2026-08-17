# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only research API for stratified conclusions (Issue #1143).

Default-off. Mounted on the main FastAPI app under ``/api/v1/research`` so it
reuses the same session auth middleware, security audit storage, and sliding-
window rate-limit pattern as the MCP governed surface — no separate ungoverned
port.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Security
from fastapi.security import APIKeyCookie

from src.api.deps import (
    get_config_dep,
    require_security_audit_service,
)
from src.api.v1.errors import api_error
from src.api.v1.schemas.common import ErrorResponse
from src.api.v1.schemas.research import ResearchConclusionResponse
from src.auth import COOKIE_NAME
from src.config import Config
from src.security.sliding_window_rate_limit import (
    RateLimitExceeded,
    SlidingWindowRateLimiter,
)
from src.services.research_api_service import (
    ResearchApiNotFoundError,
    ResearchApiService,
    ResearchApiValidationError,
)
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    SecurityAuditUnavailable,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

admin_session_cookie = APIKeyCookie(
    name=COOKIE_NAME,
    scheme_name="AdminSessionCookie",
    auto_error=False,
)
router = APIRouter(dependencies=[Security(admin_session_cookie)])

AUTH_RESPONSE = {
    401: {
        "model": ErrorResponse,
        "description": "Login required when ADMIN_AUTH_ENABLED=true",
    },
}

_RATE_LIMITER_LOCK = threading.Lock()
_RATE_LIMITER: SlidingWindowRateLimiter | None = None
_RATE_LIMITER_LIMIT: int | None = None

_ACTION_GET_BY_ID = "research.conclusions.get"
_ACTION_GET_LATEST = "research.conclusions.latest"


def _research_enabled(config: Config) -> bool:
    return bool(getattr(config, "research_api_enabled", False))


def _require_enabled(config: Config) -> None:
    if not _research_enabled(config):
        raise api_error(
            404,
            "not_found",
            "Read-only research API is not enabled",
        )


def _principal_id(request: Request) -> str:
    cookie = request.cookies.get(COOKIE_NAME) or ""
    if cookie:
        digest = hashlib.sha256(cookie.encode("utf-8")).hexdigest()[:16]
        return f"session:{digest}"
    client = request.client.host if request.client else "unknown"
    return f"ip:{client}"


def _get_rate_limiter(config: Config) -> SlidingWindowRateLimiter:
    global _RATE_LIMITER, _RATE_LIMITER_LIMIT
    limit = int(getattr(config, "research_api_rate_limit_per_minute", 60) or 60)
    with _RATE_LIMITER_LOCK:
        if _RATE_LIMITER is None or _RATE_LIMITER_LIMIT != limit:
            _RATE_LIMITER = SlidingWindowRateLimiter(limit_per_minute=limit)
            _RATE_LIMITER_LIMIT = limit
        return _RATE_LIMITER


def reset_research_rate_limiter_for_tests() -> None:
    """Test helper: drop the process-local limiter state."""
    global _RATE_LIMITER, _RATE_LIMITER_LIMIT
    with _RATE_LIMITER_LOCK:
        _RATE_LIMITER = None
        _RATE_LIMITER_LIMIT = None


def _get_research_service() -> ResearchApiService:
    return ResearchApiService()


def _audit_fields(
    *,
    actor_id: str,
    action: str,
    target_id: str,
    correlation_id: str,
    metadata: dict | None = None,
) -> dict:
    return {
        "event_type": "research_api.request",
        "actor_type": "admin_session" if actor_id.startswith("session:") else "anonymous",
        "actor_id": actor_id,
        "execution_id": correlation_id,
        "action": action,
        "target_type": "research_conclusion",
        "target_id": target_id[:128],
        "correlation_id": correlation_id,
        "metadata": metadata or {},
    }


def _record_attempt(audit: SecurityAuditRecorder, **fields: object) -> str:
    correlation_id = str(fields.get("correlation_id") or SecurityAuditService.new_correlation_id())
    payload = dict(fields)
    payload["correlation_id"] = correlation_id
    audit.record_attempt(**payload)  # type: ignore[arg-type]
    return correlation_id


def _record_completion(
    audit: SecurityAuditRecorder,
    *,
    outcome: str,
    reason_code: str,
    **fields: object,
) -> None:
    audit.record_completion(outcome=outcome, reason_code=reason_code, **fields)  # type: ignore[arg-type]


def _serve_conclusion(
    *,
    request: Request,
    config: Config,
    audit: SecurityAuditRecorder,
    action: str,
    target_id: str,
    builder,
) -> ResearchConclusionResponse:
    _require_enabled(config)
    actor_id = _principal_id(request)
    correlation_id = SecurityAuditService.new_correlation_id()
    base = _audit_fields(
        actor_id=actor_id,
        action=action,
        target_id=target_id,
        correlation_id=correlation_id,
        metadata={"path": request.url.path, "method": request.method},
    )
    try:
        _record_attempt(audit, **base)
    except SecurityAuditUnavailable:
        raise api_error(
            503,
            "security_audit_unavailable",
            "Security audit storage is unavailable",
        )

    try:
        _get_rate_limiter(config).consume(actor_id, action)
        payload = builder()
        _record_completion(
            audit,
            outcome="success",
            reason_code="completed",
            **base,
        )
        return ResearchConclusionResponse(**payload)
    except RateLimitExceeded as exc:
        try:
            _record_completion(
                audit,
                outcome="rejected",
                reason_code="rate_limited",
                **base,
            )
        except SecurityAuditUnavailable:
            raise api_error(
                503,
                "security_audit_unavailable",
                "Security audit storage is unavailable",
            )
        raise api_error(429, "rate_limited", str(exc) or "Rate limit exceeded")
    except ResearchApiValidationError as exc:
        try:
            _record_completion(
                audit,
                outcome="rejected",
                reason_code="validation_error",
                **base,
            )
        except SecurityAuditUnavailable:
            raise api_error(
                503,
                "security_audit_unavailable",
                "Security audit storage is unavailable",
            )
        raise api_error(400, "validation_error", str(exc))
    except ResearchApiNotFoundError as exc:
        try:
            _record_completion(
                audit,
                outcome="denied",
                reason_code="not_found",
                **base,
            )
        except SecurityAuditUnavailable:
            raise api_error(
                503,
                "security_audit_unavailable",
                "Security audit storage is unavailable",
            )
        raise api_error(404, "not_found", str(exc))
    except SecurityAuditUnavailable:
        raise api_error(
            503,
            "security_audit_unavailable",
            "Security audit storage is unavailable",
        )
    except Exception as exc:  # broad-exception: fallback_recorded - keep research surface fail-closed with sanitized 500
        log_safe_exception(
            logger,
            "Research API conclusion projection failed",
            exc,
            error_code="research_api_internal_error",
            context={"action": action, "target_id": target_id},
        )
        try:
            _record_completion(
                audit,
                outcome="failure",
                reason_code="internal_error",
                **base,
            )
        except SecurityAuditUnavailable:
            raise api_error(
                503,
                "security_audit_unavailable",
                "Security audit storage is unavailable",
            )
        raise api_error(500, "internal_error", "Research conclusion projection failed")


@router.get(
    "/conclusions/{record_id}",
    response_model=ResearchConclusionResponse,
    responses={
        **AUTH_RESPONSE,
        400: {"model": ErrorResponse, "description": "Invalid mode or record_id"},
        404: {
            "model": ErrorResponse,
            "description": "Feature disabled or analysis record not found",
        },
        429: {"model": ErrorResponse, "description": "Per-principal rate limit exceeded"},
        503: {
            "model": ErrorResponse,
            "description": "Security audit storage unavailable (fail-closed)",
        },
        500: {"model": ErrorResponse},
    },
    summary="Get stratified research conclusion by history record id",
    description=(
        "Authenticated read-only projection of stratified conclusions "
        "(brief / standard / research) plus metadata (as-of, confidence, "
        "evidence counts and refs). Default-off via RESEARCH_API_ENABLED; "
        "no write methods; reuses session auth, security audit, and sliding-window "
        "rate limits on the main API port."
    ),
    operation_id="getResearchConclusionByRecordId",
)
def get_research_conclusion_by_record_id(
    record_id: int,
    request: Request,
    mode: Literal["brief", "standard", "research"] = Query(
        "standard",
        description="Presentation density: brief | standard | research",
    ),
    language: Optional[str] = Query(
        None,
        description="Optional report language override (zh/en/ko)",
        max_length=16,
    ),
    config: Config = Depends(get_config_dep),
    audit: SecurityAuditRecorder = Depends(require_security_audit_service),
    service: ResearchApiService = Depends(_get_research_service),
) -> ResearchConclusionResponse:
    audit = require_security_audit_service(audit)
    return _serve_conclusion(
        request=request,
        config=config,
        audit=audit,
        action=_ACTION_GET_BY_ID,
        target_id=str(record_id),
        builder=lambda: service.get_conclusion_by_record_id(
            record_id,
            mode=mode,
            language=language,
        ),
    )

@router.get(
    "/conclusions",
    response_model=ResearchConclusionResponse,
    responses={
        **AUTH_RESPONSE,
        400: {"model": ErrorResponse, "description": "Missing stock_code or invalid mode"},
        404: {
            "model": ErrorResponse,
            "description": "Feature disabled or no history for stock_code",
        },
        429: {"model": ErrorResponse, "description": "Per-principal rate limit exceeded"},
        503: {
            "model": ErrorResponse,
            "description": "Security audit storage unavailable (fail-closed)",
        },
        500: {"model": ErrorResponse},
    },
    summary="Get latest stratified research conclusion for a stock code",
    description=(
        "Returns the newest analysis history row for stock_code as a mode-filtered "
        "stratified conclusion. Same governance as GET by record id. Default-off."
    ),
    operation_id="getLatestResearchConclusion",
)
def get_latest_research_conclusion(
    request: Request,
    stock_code: str = Query(..., min_length=1, max_length=64, description="Stock code"),
    mode: Literal["brief", "standard", "research"] = Query(
        "standard",
        description="Presentation density: brief | standard | research",
    ),
    language: Optional[str] = Query(
        None,
        description="Optional report language override (zh/en/ko)",
        max_length=16,
    ),
    config: Config = Depends(get_config_dep),
    audit: SecurityAuditRecorder = Depends(require_security_audit_service),
    service: ResearchApiService = Depends(_get_research_service),
) -> ResearchConclusionResponse:
    audit = require_security_audit_service(audit)
    return _serve_conclusion(
        request=request,
        config=config,
        audit=audit,
        action=_ACTION_GET_LATEST,
        target_id=stock_code,
        builder=lambda: service.get_latest_conclusion_for_stock(
            stock_code,
            mode=mode,
            language=language,
        ),
    )
