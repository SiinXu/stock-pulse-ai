# -*- coding: utf-8 -*-
"""Authentication and JSON-RPC protocol tests (required acceptance gates)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.mcp_server.auth_gate import McpAuthError, require_mcp_auth
from src.mcp_server.config import McpServerConfig
from src.mcp_server.errors import JSONRPC_UNAUTHORIZED
from src.mcp_server.handlers import McpToolHandlers
from src.mcp_server.protocol import McpProtocolServer
from src.mcp_server.tools import call_tool


def _config(**overrides) -> McpServerConfig:
    base = dict(
        enabled=True,
        transport="stdio",
        host="127.0.0.1",
        port=8765,
        session_token=None,
        analysis_timeout_seconds=120,
        analysis_max_stocks=5,
    )
    base.update(overrides)
    return McpServerConfig(**base)


class TestAuthGate:
    def test_auth_disabled_allows_without_token(self, monkeypatch):
        monkeypatch.setattr(
            "src.mcp_server.auth_gate.is_auth_enabled", lambda: False
        )
        ctx = require_mcp_auth(config=_config())
        assert ctx.authenticated is True
        assert ctx.auth_enabled is False

    def test_auth_enabled_rejects_missing_token(self, monkeypatch):
        monkeypatch.setattr(
            "src.mcp_server.auth_gate.is_auth_enabled", lambda: True
        )
        monkeypatch.setattr(
            "src.mcp_server.auth_gate.verify_session", lambda _t: False
        )
        with pytest.raises(McpAuthError) as exc_info:
            require_mcp_auth(config=_config())
        assert exc_info.value.error == "unauthorized"

    def test_auth_enabled_accepts_valid_bearer(self, monkeypatch):
        monkeypatch.setattr(
            "src.mcp_server.auth_gate.is_auth_enabled", lambda: True
        )
        monkeypatch.setattr(
            "src.mcp_server.auth_gate.verify_session",
            lambda token: token == "good-session",
        )
        ctx = require_mcp_auth(
            config=_config(),
            headers={"Authorization": "Bearer good-session"},
        )
        assert ctx.authenticated is True

    def test_auth_enabled_accepts_env_session_token(self, monkeypatch):
        monkeypatch.setattr(
            "src.mcp_server.auth_gate.is_auth_enabled", lambda: True
        )
        monkeypatch.setattr(
            "src.mcp_server.auth_gate.verify_session",
            lambda token: token == "env-session",
        )
        ctx = require_mcp_auth(config=_config(session_token="env-session"))
        assert ctx.authenticated is True

    def test_auth_enabled_rejects_invalid_token(self, monkeypatch):
        monkeypatch.setattr(
            "src.mcp_server.auth_gate.is_auth_enabled", lambda: True
        )
        monkeypatch.setattr(
            "src.mcp_server.auth_gate.verify_session", lambda _t: False
        )
        with pytest.raises(McpAuthError):
            require_mcp_auth(
                config=_config(),
                headers={"Authorization": "Bearer bad"},
            )


class TestProtocolAuth:
    def _server(self, monkeypatch, *, auth_enabled: bool) -> McpProtocolServer:
        monkeypatch.setattr(
            "src.mcp_server.auth_gate.is_auth_enabled", lambda: auth_enabled
        )
        if auth_enabled:
            monkeypatch.setattr(
                "src.mcp_server.auth_gate.verify_session",
                lambda token: token == "valid",
            )
        stock = MagicMock()
        stock.get_realtime_quote.return_value = {
            "stock_code": "600519",
            "current_price": 100.0,
        }
        handlers = McpToolHandlers(
            config=_config(),
            stock_service=stock,
        )
        return McpProtocolServer(config=_config(), handlers=handlers)

    def test_tools_list_rejected_without_auth(self, monkeypatch):
        server = self._server(monkeypatch, auth_enabled=True)
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
        assert response is not None
        assert "error" in response
        assert response["error"]["code"] == JSONRPC_UNAUTHORIZED
        assert response["error"]["data"]["error"] == "unauthorized"

    def test_tools_call_rejected_without_auth(self, monkeypatch):
        server = self._server(monkeypatch, auth_enabled=True)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "get_realtime_quote",
                    "arguments": {"stock_code": "600519"},
                },
            }
        )
        assert response is not None
        assert response["error"]["code"] == JSONRPC_UNAUTHORIZED

    def test_tools_call_succeeds_with_auth(self, monkeypatch):
        server = self._server(monkeypatch, auth_enabled=True)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_realtime_quote",
                    "arguments": {"stock_code": "600519"},
                },
            },
            headers={"Authorization": "Bearer valid"},
        )
        assert response is not None
        assert "result" in response
        assert response["result"]["isError"] is False

    def test_initialize_does_not_require_auth(self, monkeypatch):
        server = self._server(monkeypatch, auth_enabled=True)
        response = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
            }
        )
        assert response is not None
        assert response["result"]["serverInfo"]["name"] == "stock-pulse-ai"

    def test_tools_list_when_auth_disabled(self, monkeypatch):
        server = self._server(monkeypatch, auth_enabled=False)
        response = server.handle_message(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/list"}
        )
        assert "result" in response
        names = {t["name"] for t in response["result"]["tools"]}
        assert "get_realtime_quote" in names
        assert "trigger_analysis" in names
        # Admin tools must never appear
        assert "update_system_config" not in names


class TestToolDispatch:
    def test_unknown_tool_is_error_not_exception(self):
        handlers = McpToolHandlers(config=_config())
        result = call_tool(handlers, "update_system_config", {})
        assert result["isError"] is True
        assert result["structuredContent"]["error"] == "validation_error"
