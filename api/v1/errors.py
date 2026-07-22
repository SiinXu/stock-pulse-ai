# -*- coding: utf-8 -*-
"""Shared helpers for stable API error responses."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from src.utils.sanitize import redact_sensitive_data, redact_sensitive_text


def error_body(
    error: str,
    message: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    details: Any = None,
    trace_id: Optional[str] = None,
    detail: Any = None,
) -> dict[str, Any]:
    """Build the version-one error envelope.

    ``details`` is authoritative. ``detail`` is emitted from that same value
    as a deprecated read-only compatibility alias for legacy clients.
    """
    if details is None and detail is not None:
        details = detail
    safe_params = redact_sensitive_data(params if params is not None else {})
    if not isinstance(safe_params, dict):
        safe_params = {}
    safe_details = redact_sensitive_data(details)
    safe_error = redact_sensitive_text(error)
    safe_message = redact_sensitive_text(message)
    return {
        "error": safe_error or "unknown_error",
        "message": safe_message or "Request failed",
        "params": safe_params,
        "details": safe_details,
        "detail": safe_details,
        "trace_id": (
            redact_sensitive_text(trace_id)
            if trace_id is not None
            else None
        ),
    }


def normalize_error_body(
    payload: Any,
    *,
    default_error: str,
    default_message: str,
    trace_id: Optional[str] = None,
) -> dict[str, Any]:
    """Adapt structured and legacy exception payloads to the stable envelope."""
    if not isinstance(payload, dict):
        return error_body(
            default_error,
            default_message,
            details={"legacy_message": str(payload)} if payload not in (None, "") else None,
            trace_id=trace_id,
        )

    error = str(payload.get("error") or payload.get("code") or default_error)
    raw_message = payload.get("message")
    message = str(raw_message) if raw_message not in (None, "") else default_message

    raw_params = payload.get("params")
    params = dict(raw_params) if isinstance(raw_params, dict) else {}
    canonical_keys = {"error", "code", "message", "params", "details", "detail", "trace_id"}
    # Older endpoints returned useful interpolation data (for example
    # ``existing_task_id``) beside error/message. Preserve it as params.
    for key, value in payload.items():
        if key not in canonical_keys and key not in params:
            params[key] = value

    details = payload.get("details", payload.get("detail"))
    resolved_trace_id = payload.get("trace_id") or trace_id
    return error_body(
        error,
        message,
        params=params,
        details=details,
        trace_id=str(resolved_trace_id) if resolved_trace_id else None,
    )


def api_error(
    status_code: int,
    error: str,
    message: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    details: Any = None,
    trace_id: Optional[str] = None,
    detail: Any = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=error_body(
            error,
            message,
            params=params,
            details=details,
            trace_id=trace_id,
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
