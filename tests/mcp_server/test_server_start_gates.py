# -*- coding: utf-8 -*-
"""Startup gates: disabled flag, public bind policy, stdio runner."""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

import pytest

from src.mcp_server.config import McpServerConfig, load_mcp_server_config
from src.mcp_server.handlers import McpToolHandlers
from src.mcp_server.server import (
    McpServerDisabledError,
    McpServerStartError,
    build_protocol_server,
    enforce_transport_security,
    main,
    run_stdio_server,
)
from src.security.http_bind import InsecurePublicBindError


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


class TestStartGates:
    def test_build_protocol_server_disabled(self, monkeypatch):
        monkeypatch.setenv("MCP_SERVER_ENABLED", "false")
        with pytest.raises(McpServerDisabledError):
            build_protocol_server(load_mcp_server_config())

    def test_http_public_bind_without_auth_fails(self, monkeypatch):
        monkeypatch.setattr(
            "src.mcp_server.server.enforce_http_bind_security",
            MagicMock(side_effect=InsecurePublicBindError("refused")),
        )
        with pytest.raises(McpServerStartError):
            enforce_transport_security(
                _config(transport="http", host="0.0.0.0")
            )

    def test_http_local_bind_ok(self, monkeypatch):
        monkeypatch.setattr(
            "src.mcp_server.server.enforce_http_bind_security",
            MagicMock(),
        )
        enforce_transport_security(_config(transport="http", host="127.0.0.1"))

    def test_main_exits_2_when_disabled(self, monkeypatch):
        monkeypatch.setenv("MCP_SERVER_ENABLED", "false")
        assert main([]) == 2

    def test_stdio_roundtrip(self, monkeypatch):
        monkeypatch.setattr(
            "src.mcp_server.auth_gate.is_auth_enabled", lambda: False
        )
        stock = MagicMock()
        stock.get_realtime_quote.return_value = {
            "stock_code": "600519",
            "current_price": 42.0,
        }
        handlers = McpToolHandlers(config=_config(), stock_service=stock)
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_realtime_quote",
                "arguments": {"stock_code": "600519"},
            },
        }
        stdin = io.StringIO(json.dumps(request) + "\n")
        stdout = io.StringIO()
        code = run_stdio_server(_config(), handlers=handlers, stdin=stdin, stdout=stdout)
        assert code == 0
        line = stdout.getvalue().strip()
        payload = json.loads(line)
        assert payload["id"] == 1
        assert payload["result"]["isError"] is False
