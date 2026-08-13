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

from api.v1.errors import error_body
from src.auth import COOKIE_NAME, is_auth_enabled, verify_session

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


def _is_capability_write_mutation(method: str, path: str) -> bool:
    """Write mutations record their own unauthorized denial audit.

    AuthMiddleware still protects other /api/v1/* routes. Register / update /
    retire must reach the endpoint so ``_require_write_access`` can persist a
    ``capability.write`` denied completion before returning 401.
    """
    normalized = path.rstrip("/") or "/"
    prefix = "/api/v1/capabilities/registry"
    if method == "POST" and normalized == prefix:
        return True
    if not normalized.startswith(prefix + "/"):
        return False
    if method == "PUT":
        return True
    return method == "POST" and normalized.endswith("/retire")


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
        if not cookie_val or not verify_session(cookie_val):
            if _is_capability_write_mutation(request.method, path):
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content=error_body("unauthorized", "Login required"),
            )

        return await call_next(request)


def add_auth_middleware(app):
    """Add auth middleware to protect API routes.

    The middleware is always registered; whether auth is enforced is determined
    at request time by is_auth_enabled() so the decision stays consistent across
    any runtime configuration reload.
    """
    app.add_middleware(AuthMiddleware)
