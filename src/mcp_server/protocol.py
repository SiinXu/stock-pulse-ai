# -*- coding: utf-8 -*-
"""Minimal MCP JSON-RPC protocol surface (initialize / tools/list / tools/call).

Implements enough of the Model Context Protocol for discovery and tool invocation
without depending on the optional third-party ``mcp`` package.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Mapping, Optional

from src.mcp_server import MCP_PROTOCOL_VERSION, SERVER_NAME, SERVER_VERSION
from src.mcp_server.auth_gate import McpAuthError, require_mcp_auth
from src.mcp_server.capabilities import inventory_as_dicts
from src.mcp_server.config import McpServerConfig
from src.mcp_server.errors import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    JSONRPC_UNAUTHORIZED,
    jsonrpc_error,
    mcp_error_payload,
)
from src.mcp_server.handlers import McpToolHandlers
from src.mcp_server.tools import call_tool, list_tool_definitions

logger = logging.getLogger(__name__)


class _MethodNotFound(Exception):
    def __init__(self, method: str) -> None:
        self.method = method
        super().__init__(method)


class McpProtocolServer:
    """Stateful JSON-RPC handler for one MCP session."""

    def __init__(
        self,
        *,
        config: McpServerConfig,
        handlers: Optional[McpToolHandlers] = None,
    ) -> None:
        self.config = config
        self.handlers = handlers or McpToolHandlers(config=config)
        self._initialized = False

    def handle_raw(
        self,
        raw: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Optional[str]:
        """Parse one JSON-RPC message and return a JSON response string (or None)."""
        raw = (raw or "").strip()
        if not raw:
            return json.dumps(
                jsonrpc_error(None, JSONRPC_PARSE_ERROR, "Parse error: empty message"),
                ensure_ascii=False,
            )
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return json.dumps(
                jsonrpc_error(None, JSONRPC_PARSE_ERROR, "Parse error: invalid JSON"),
                ensure_ascii=False,
            )
        response = self.handle_message(message, headers=headers)
        if response is None:
            return None
        return json.dumps(response, ensure_ascii=False, default=str)

    def handle_message(
        self,
        message: Any,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Handle a parsed JSON-RPC request or notification."""
        if not isinstance(message, dict):
            return jsonrpc_error(
                None, JSONRPC_INVALID_REQUEST, "Invalid Request: expected object"
            )

        has_id = "id" in message
        request_id = message.get("id") if has_id else None
        method = message.get("method")
        params = message.get("params") if "params" in message else {}
        is_notification = not has_id

        if message.get("jsonrpc") != "2.0":
            if is_notification:
                return None
            return jsonrpc_error(
                request_id,
                JSONRPC_INVALID_REQUEST,
                "Invalid Request: jsonrpc must be 2.0",
            )
        if not isinstance(method, str) or not method:
            if is_notification:
                return None
            return jsonrpc_error(
                request_id,
                JSONRPC_INVALID_REQUEST,
                "Invalid Request: method required",
            )
        if params is None:
            params = {}
        if not isinstance(params, dict):
            if is_notification:
                return None
            return jsonrpc_error(
                request_id,
                JSONRPC_INVALID_PARAMS,
                "Invalid params: expected object",
            )

        try:
            result = self._dispatch(method, params, headers=headers)
        except _MethodNotFound as exc:
            if is_notification:
                return None
            return jsonrpc_error(
                request_id,
                JSONRPC_METHOD_NOT_FOUND,
                f"Method not found: {exc.method}",
            )
        except McpAuthError as exc:
            if is_notification:
                return None
            return jsonrpc_error(
                request_id,
                JSONRPC_UNAUTHORIZED,
                exc.message,
                data=mcp_error_payload(exc.error, exc.message),
            )
        except ValueError as exc:
            if is_notification:
                return None
            return jsonrpc_error(
                request_id,
                JSONRPC_INVALID_PARAMS,
                str(exc) or "Invalid params",
                data=mcp_error_payload("validation_error", str(exc) or "Invalid params"),
            )
        except Exception as exc:  # broad-exception: keep MCP session alive with stable error
            logger.exception("MCP method %s failed", method)
            if is_notification:
                return None
            return jsonrpc_error(
                request_id,
                JSONRPC_INTERNAL_ERROR,
                "Internal error",
                data=mcp_error_payload(
                    "internal_error",
                    "Internal server error",
                    details={"exception_type": type(exc).__name__},
                ),
            )

        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _dispatch(
        self,
        method: str,
        params: Dict[str, Any],
        *,
        headers: Optional[Mapping[str, str]],
    ) -> Any:
        if method == "initialize":
            return self._initialize(params)
        if method == "notifications/initialized":
            self._initialized = True
            return None
        if method == "ping":
            return {}
        if method == "tools/list":
            require_mcp_auth(config=self.config, headers=headers)
            return {"tools": list_tool_definitions()}
        if method == "tools/call":
            require_mcp_auth(config=self.config, headers=headers)
            name = params.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("tools/call requires params.name")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise ValueError("tools/call params.arguments must be an object")
            return call_tool(self.handlers, name.strip(), arguments)
        if method == "stockpulse/capabilities":
            require_mcp_auth(config=self.config, headers=headers)
            return {"capabilities": inventory_as_dicts()}
        raise _MethodNotFound(method)

    def _initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        _ = params
        self._initialized = True
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
            "instructions": (
                "StockPulse MCP adapter. Read-only market/history/portfolio tools plus "
                "a guarded trigger_analysis tool. Configuration, secrets, and admin "
                "operations are not exposed. When ADMIN_AUTH_ENABLED=true, provide a "
                "valid admin session via Authorization Bearer, X-DSA-Session, or "
                "MCP_SESSION_TOKEN."
            ),
        }
