# -*- coding: utf-8 -*-
"""Error mapping for MCP responses.

Uses the same stable error envelope shape as the HTTP API
(``error`` / ``message`` / ``params`` / ``details`` / ``detail`` / ``trace_id``)
without importing ``api.v1`` at module load time (avoids pulling the full API
router graph into the optional MCP process).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.utils.sanitize import redact_sensitive_data, redact_sensitive_text

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603
JSONRPC_APPLICATION_ERROR = -32000
JSONRPC_UNAUTHORIZED = -32001
JSONRPC_BUSY = -32002


def mcp_error_payload(
    error: str,
    message: str,
    *,
    details: Any = None,
    params: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the same error body shape as the HTTP API error_body helper."""
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
            redact_sensitive_text(trace_id) if trace_id is not None else None
        ),
    }


def tool_error_result(
    error: str,
    message: str,
    *,
    details: Any = None,
) -> Dict[str, Any]:
    """Return an MCP tools/call error content payload (isError=true)."""
    body = mcp_error_payload(error, message, details=details)
    return {
        "content": [
            {
                "type": "text",
                "text": f"{body['error']}: {body['message']}",
            }
        ],
        "isError": True,
        "structuredContent": body,
    }


def tool_success_result(payload: Any) -> Dict[str, Any]:
    """Return a successful tools/call result with JSON text content."""
    import json

    if isinstance(payload, str):
        text = payload
        structured: Any = {"text": payload}
    else:
        text = json.dumps(payload, ensure_ascii=False, default=str)
        structured = payload
    return {
        "content": [{"type": "text", "text": text}],
        "isError": False,
        "structuredContent": structured,
    }


def jsonrpc_error(
    request_id: Any,
    code: int,
    message: str,
    *,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a JSON-RPC 2.0 error response."""
    error_obj: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error_obj["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error_obj}


def map_exception_to_tool_result(exc: BaseException) -> Dict[str, Any]:
    """Map handler exceptions to MCP tool error results using API codes."""
    if isinstance(exc, ValueError):
        return tool_error_result("validation_error", str(exc) or "Invalid parameters")
    if isinstance(exc, PermissionError):
        return tool_error_result("unauthorized", str(exc) or "Login required")
    if isinstance(exc, TimeoutError):
        return tool_error_result("timeout", str(exc) or "Operation timed out")
    if type(exc).__name__ in {"McpBusyError"} or getattr(exc, "error", None) == "busy":
        return tool_error_result(
            "busy",
            str(exc) or "Analysis is already running",
        )
    return tool_error_result(
        "internal_error",
        "Internal server error",
        details={"exception_type": type(exc).__name__},
    )


class McpBusyError(Exception):
    """Raised when the global analysis lock cannot be acquired."""

    error = "busy"

    def __init__(self, message: str = "Analysis is already running") -> None:
        super().__init__(message)
