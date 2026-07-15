# -*- coding: utf-8 -*-
"""
===================================
Global exception handling middleware
===================================

Responsibilities:
1. Catch unhandled exceptions.
2. Normalize error response envelopes.
3. Record diagnostic logs.
"""

import logging
import re
import traceback
import uuid
from typing import Any, Callable, Dict, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.v1.errors import error_body

logger = logging.getLogger(__name__)

_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_STABLE_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CANONICAL_ERROR_KEYS = {
    "error",
    "code",
    "message",
    "params",
    "details",
    "detail",
    "trace_id",
}


def _request_trace_id(request: Request) -> str:
    candidate = (
        request.headers.get("x-request-id")
        or request.headers.get("x-trace-id")
        or ""
    ).strip()
    if candidate and _TRACE_ID_RE.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def _merge_diagnostic_details(payload: Dict[str, Any]) -> Any:
    explicit = payload.get("details", payload.get("detail"))
    extras = {
        key: value
        for key, value in payload.items()
        if key not in _CANONICAL_ERROR_KEYS
    }
    if explicit is None:
        return extras
    if isinstance(explicit, dict):
        return {**extras, **explicit}
    if extras:
        return {**extras, "value": explicit}
    return explicit


def _normalise_http_error(detail: Any, status_code: int, trace_id: str) -> Dict[str, Any]:
    if status_code >= 500:
        code = "internal_error"
        if isinstance(detail, dict):
            candidate = detail.get("error") or detail.get("code")
            if isinstance(candidate, str):
                normalized_candidate = candidate.strip()
                if _STABLE_ERROR_CODE_RE.fullmatch(normalized_candidate):
                    code = normalized_candidate
        return error_body(
            code,
            "Internal server error",
            trace_id=trace_id,
        )

    if isinstance(detail, dict):
        code = str(detail.get("error") or detail.get("code") or "legacy_http_error")
        message = str(detail.get("message") or "Request failed")
        params = detail.get("params") if isinstance(detail.get("params"), dict) else {}
        return error_body(
            code,
            message,
            params=params,
            details=_merge_diagnostic_details(detail),
            trace_id=trace_id,
        )

    details = {}
    if detail is not None and str(detail).strip():
        details = {"legacy_message": str(detail).strip()}
    return error_body(
        "legacy_http_error",
        "Request failed",
        details=details,
        trace_id=trace_id,
    )


def _error_response(
    *,
    status_code: int,
    content: Dict[str, Any],
    trace_id: str,
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    response_headers = dict(headers or {})
    response_headers["X-Trace-ID"] = trace_id
    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=response_headers,
    )


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return the canonical error envelope."""
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: Callable
    ) -> Response:
        """Run the next request handler and normalize unexpected failures."""
        try:
            response = await call_next(request)
            return response
            
        except Exception as e:
            trace_id = _request_trace_id(request)
            # Keep full diagnostics in server logs; the client receives only a trace ID.
            logger.error(
                f"Unhandled exception [trace_id={trace_id}]: {e}\n"
                f"Request path: {request.url.path}\n"
                f"Request method: {request.method}\n"
                f"Stack trace: {traceback.format_exc()}"
            )
            
            return _error_response(
                status_code=500,
                content=error_body(
                    "internal_error",
                    "Internal server error",
                    trace_id=trace_id,
                ),
                trace_id=trace_id,
            )


def add_error_handlers(app) -> None:
    """Register canonical exception handlers on a FastAPI application."""
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Normalize both current and legacy HTTPException payloads."""
        trace_id = _request_trace_id(request)
        return _error_response(
            status_code=exc.status_code,
            content=_normalise_http_error(exc.detail, exc.status_code, trace_id),
            trace_id=trace_id,
            headers=exc.headers,
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Return structured field diagnostics for request validation failures."""
        trace_id = _request_trace_id(request)
        validation_errors = [
            {
                "loc": list(error.get("loc") or []),
                "msg": str(error.get("msg") or "Invalid value"),
                "type": str(error.get("type") or "validation_error"),
            }
            for error in exc.errors()
        ]
        return _error_response(
            status_code=422,
            content=error_body(
                "validation_error",
                "Request validation failed",
                details={"validation_errors": validation_errors},
                trace_id=trace_id,
            ),
            trace_id=trace_id,
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Redact an unhandled application exception behind a trace ID."""
        trace_id = _request_trace_id(request)
        logger.error(
            f"Unhandled exception [trace_id={trace_id}]: {exc}\n"
            f"Request path: {request.url.path}\n"
            f"Stack trace: {traceback.format_exc()}"
        )
        return _error_response(
            status_code=500,
            content=error_body(
                "internal_error",
                "Internal server error",
                trace_id=trace_id,
            ),
            trace_id=trace_id,
        )
