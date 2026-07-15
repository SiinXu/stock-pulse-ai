# -*- coding: utf-8 -*-
"""Shared helpers for the stable API error envelope."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse


def error_body(
    error: str,
    message: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    details: Any = None,
    trace_id: Optional[str] = None,
    detail: Any = None,
) -> dict[str, Any]:
    """Build the canonical error envelope.

    ``detail`` remains an input-only compatibility alias for existing endpoint
    callers. Responses always expose the canonical plural ``details`` field.
    """
    if details is not None and detail is not None:
        raise ValueError("Pass either details or legacy detail, not both")
    resolved_details = details if details is not None else detail
    body: dict[str, Any] = {
        "error": str(error or "unknown_error").strip() or "unknown_error",
        "message": str(message or "Request failed").strip() or "Request failed",
        "params": dict(params or {}),
        "details": {} if resolved_details is None else resolved_details,
    }
    if trace_id:
        body["trace_id"] = str(trace_id)
    return body


def api_error(
    status_code: int,
    error: str,
    message: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    details: Any = None,
    detail: Any = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=error_body(
            error,
            message,
            params=params,
            details=details,
            detail=detail,
        ),
    )


def error_json_response(
    status_code: int,
    error: str,
    message: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    details: Any = None,
    trace_id: Optional[str] = None,
    detail: Any = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_body(
            error,
            message,
            params=params,
            details=details,
            trace_id=trace_id,
            detail=detail,
        ),
    )
