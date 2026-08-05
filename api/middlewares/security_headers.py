# -*- coding: utf-8 -*-
"""
Security response headers for the FastAPI-served web app and API.

Defense-in-depth alongside react-markdown defaults: Content-Security-Policy,
X-Content-Type-Options, Referrer-Policy, and X-Frame-Options on every response
except the interactive OpenAPI UIs that load CDN assets.
"""

from __future__ import annotations

from typing import Callable, Iterable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# ---------------------------------------------------------------------------
# CSP policy derivation (built SPA + FastAPI static hosting)
# ---------------------------------------------------------------------------
#
# Sources inspected (not guessed):
# - apps/dsa-web/index.html: inline theme FOUC bootstrap <script>; Vite
#   production build emits /assets/*.js modules and /assets/*.css stylesheets
#   referenced from the same origin when FastAPI serves ``static/``.
# - apps/dsa-web/src/**: React ``style={{...}}`` props (report strategy tones,
#   chat textarea height, playground frame width, etc.) require style-src
#   'unsafe-inline'. No external font CDNs; index.css uses data:image SVG
#   backgrounds (img-src data:).
# - Share / export downloads: ShareImageButton, chatExport, ConfigBackupCard
#   call URL.createObjectURL → blob: object URLs for <a download>.
# - API traffic: apps/dsa-web/src/utils/constants.ts defaults API_BASE_URL to
#   same-origin ''; useTaskStream / agent stream use EventSource/fetch on
#   /api/v1/* under the page origin → connect-src 'self'.
# - Playground iframe loads same-origin playground-render routes → covered by
#   default-src 'self' (frame-src falls back to default-src).
# - object/plugin embeds and <base> hijacking are denied.
# - frame-ancestors 'none' (+ X-Frame-Options: DENY) blocks clickjacking.
#
# Intentionally NOT allowed:
# - Remote img/script/style hosts (blocks tracking pixels from LLM markdown
#   images and third-party script injection).
# - 'unsafe-eval' (no eval/new Function required by the production bundle).
#
# OpenAPI UI exception:
# - FastAPI Swagger/ReDoc load jsDelivr scripts/CSS and use inline bootstrapping.
# - Paths under /docs and /redoc omit Content-Security-Policy only; other
#   security headers still apply. Operators who expose /docs publicly should
#   put a reverse-proxy policy in front or disable the docs routes.

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)

SECURITY_HEADERS: dict[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
}

# Paths that load CDN-hosted OpenAPI UIs (see fastapi.openapi.docs).
_OPENAPI_UI_PREFIXES: tuple[str, ...] = ("/docs", "/redoc")


def _normalize_path(path: str) -> str:
    return path.rstrip("/") or "/"


def is_openapi_ui_path(path: str) -> bool:
    """Return True when CSP must be omitted so Swagger/ReDoc can load CDN assets."""
    normalized = _normalize_path(path)
    for prefix in _OPENAPI_UI_PREFIXES:
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            return True
    return False


def iter_security_headers(path: str) -> Iterable[tuple[str, str]]:
    """Yield security headers appropriate for the request path."""
    for name, value in SECURITY_HEADERS.items():
        if name == "Content-Security-Policy" and is_openapi_ui_path(path):
            continue
        yield name, value


def apply_security_headers(response: Response, path: str) -> Response:
    """Set security headers on ``response`` without overwriting existing values."""
    for name, value in iter_security_headers(path):
        # Preserve route-level overrides (e.g. history share-image already sets nosniff).
        if name not in response.headers:
            response.headers[name] = value
    return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach browser security headers to every response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        response = await call_next(request)
        return apply_security_headers(response, request.url.path)


def add_security_headers_middleware(app) -> None:
    """Register security-headers middleware (outermost so 401/error responses are covered)."""
    app.add_middleware(SecurityHeadersMiddleware)


__all__ = [
    "CONTENT_SECURITY_POLICY",
    "SECURITY_HEADERS",
    "SecurityHeadersMiddleware",
    "add_security_headers_middleware",
    "apply_security_headers",
    "is_openapi_ui_path",
    "iter_security_headers",
]
