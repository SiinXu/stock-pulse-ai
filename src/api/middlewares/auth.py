# -*- coding: utf-8 -*-
"""
Auth middleware: protect /api/v1/* when admin auth is enabled.
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect

from src.api.v1.errors import error_body
from src.auth import COOKIE_NAME, is_auth_enabled, verify_session
from src.capability_registry.write_audit import (
    CAPABILITY_DENIED_ACTOR_ID,
    CAPABILITY_DENIED_ACTOR_TYPE,
    CAPABILITY_DENIED_REASON_CODE,
    DENIED_BODY_PEEK_BYTES,
    UNKNOWN_CAPABILITY_ID,
    CapabilityWriteAuditor,
    classify_capability_write,
    peek_register_capability_id,
)
from src.services.security_audit_service import SecurityAuditUnavailable

logger = logging.getLogger(__name__)

EXEMPT_PATHS = frozenset({
    "/api/v1/auth/login",
    "/api/v1/auth/status",
    "/api/health",
    "/api/v1/health",
    "/api/v1/scorecard",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
})


def _path_exempt(path: str) -> bool:
    """Check if path is exempt from auth."""
    normalized = path.rstrip("/") or "/"
    return normalized in EXEMPT_PATHS


def _unauthorized_response() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content=error_body("unauthorized", "Login required"),
    )


def _audit_unavailable_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=error_body(
            "security_audit_unavailable",
            "Security audit storage is unavailable",
        ),
    )


async def _bounded_request_body(request: Request, max_bytes: int) -> bytes:
    """Read a size-capped body without copying it into audit metadata.

    Declared Content-Length above the cap is rejected without reading.
    Missing or chunked bodies are streamed and stopped at ``max_bytes``
    so the process never joins an unbounded payload.
    """
    header = request.headers.get("content-length")
    if header is not None:
        try:
            declared = int(header.strip())
        except ValueError:
            return b""
        if declared < 0 or declared > max_bytes:
            return b""
    chunks: list[bytes] = []
    total = 0
    try:
        async for chunk in request.stream():
            if type(chunk) is not bytes:
                return b""
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                return b""
            chunks.append(chunk)
    except ClientDisconnect:
        return b""
    return b"".join(chunks)


async def _denied_capability_write_response(request: Request) -> JSONResponse:
    """Audit a privileged write denial at the auth boundary, then return 401.

    Capability write routes are not added to EXEMPT_PATHS. If the denial
    cannot be persisted, fail closed with 503 so the registry is not mutated.
    """
    mutation = classify_capability_write(request.method, request.url.path)
    if mutation is None:
        return _unauthorized_response()
    capability_id = mutation.path_capability_id
    if mutation.operation == "register" and not capability_id:
        capability_id = peek_register_capability_id(
            await _bounded_request_body(request, DENIED_BODY_PEEK_BYTES),
        )
    try:
        CapabilityWriteAuditor().record_denied(
            capability_id=capability_id or UNKNOWN_CAPABILITY_ID,
            operation=mutation.operation,
            reason_code=CAPABILITY_DENIED_REASON_CODE,
            actor_type=CAPABILITY_DENIED_ACTOR_TYPE,
            actor_id=CAPABILITY_DENIED_ACTOR_ID,
            metadata={"denial_source": "auth_middleware"},
        )
    except SecurityAuditUnavailable:
        return _audit_unavailable_response()
    return _unauthorized_response()


class AuthMiddleware(BaseHTTPMiddleware):
    """Require valid session for /api/v1/* when auth is enabled."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ):
        if not is_auth_enabled():
            return await call_next(request)

        path = request.url.path
        if _path_exempt(path):
            return await call_next(request)

        if not path.startswith("/api/v1/"):
            return await call_next(request)

        cookie_val = request.cookies.get(COOKIE_NAME)
        if cookie_val and verify_session(cookie_val):
            return await call_next(request)

        if classify_capability_write(request.method, path) is not None:
            return await _denied_capability_write_response(request)

        return _unauthorized_response()


def add_auth_middleware(app):
    """Add auth middleware to protect API routes.

    The middleware is always registered; whether auth is enforced is determined
    at request time by is_auth_enabled() so the decision stays consistent across
    any runtime configuration reload.
    """
    app.add_middleware(AuthMiddleware)
