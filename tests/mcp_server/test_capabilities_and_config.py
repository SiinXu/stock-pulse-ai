"""Capability inventory, strict schema, and fail-closed startup configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.mcp_server.capabilities import CAPABILITY_INVENTORY, exposed_tool_names, not_exposed_capabilities
from src.mcp_server.config import DEFAULT_HOST, McpConfigError, is_mcp_server_enabled, load_mcp_server_config
from src.mcp_server.server import McpServerDisabledError, ensure_enabled
from src.mcp_server.tools import list_tool_definitions, validate_tool_arguments


def _clear_mcp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MCP_SERVER_ENABLED",
        "MCP_SERVER_TRANSPORT",
        "MCP_SERVER_HOST",
        "MCP_SERVER_PORT",
        "MCP_STDIO_SCOPES",
        "MCP_STDIO_PRINCIPAL",
        "MCP_HTTP_SCOPES",
        "MCP_HTTP_SESSION_TOKEN_SHA256",
        "MCP_HTTP_ALLOWED_HOSTS",
        "MCP_HTTP_ALLOWED_ORIGINS",
        "MCP_RATE_LIMIT_PER_MINUTE",
        "MCP_ANALYSIS_MAX_STOCKS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_inventory_and_advertised_tools_match() -> None:
    tool_names = {tool["name"] for tool in list_tool_definitions()}
    assert tool_names == set(exposed_tool_names())
    assert {tool["name"] for tool in list_tool_definitions(frozenset({"market.read"}))} == {
        "get_realtime_quote",
        "get_stock_history",
    }
    blocked = {entry.name for entry in not_exposed_capabilities()}
    assert {"system_config_read_write", "secret_and_api_key_management", "security_audit_admin"} <= blocked
    assert all(entry.reason.strip() for entry in CAPABILITY_INVENTORY)


def test_every_schema_forbids_extra_properties() -> None:
    for tool in list_tool_definitions():
        assert tool["inputSchema"]["additionalProperties"] is False
        assert tool["_meta"]["io.stockpulse/scope"]


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("get_portfolio_snapshot", {"include_realtime": "false"}),
        ("get_stock_history", {"stock_code": "AAPL", "period": "weekly"}),
        ("get_stock_history", {"stock_code": "AAPL", "days": 0}),
        ("get_portfolio_snapshot", {"cost_method": "average"}),
        ("get_realtime_quote", {"stock_code": "AAPL", "extra": True}),
        ("trigger_analysis", {"stock_codes": ["AAPL", "AAPL"]}),
        ("trigger_analysis", {"stock_code": "AAPL", "async_mode": False}),
    ],
)
def test_strict_tool_schema_rejects_coercion_and_invalid_values(tool: str, arguments: dict) -> None:
    with pytest.raises(ValidationError):
        validate_tool_arguments(tool, arguments)


def test_default_off_has_no_transport_side_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_mcp_env(monkeypatch)
    assert is_mcp_server_enabled() is False
    config = load_mcp_server_config()
    assert config.host == DEFAULT_HOST
    assert config.transport == "stdio"
    with pytest.raises(McpServerDisabledError):
        ensure_enabled(config)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MCP_SERVER_TRANSPORT", "htp"),
        ("MCP_SERVER_PORT", "zero"),
        ("MCP_SERVER_PORT", "0"),
        ("MCP_RATE_LIMIT_PER_MINUTE", "0"),
        ("MCP_ANALYSIS_MAX_STOCKS", "51"),
        ("MCP_HTTP_SCOPES", "admin.write"),
    ],
)
def test_explicit_invalid_config_never_defaults_or_clamps(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    _clear_mcp_env(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(McpConfigError):
        load_mcp_server_config()


def test_enabled_stdio_requires_explicit_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_mcp_env(monkeypatch)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    with pytest.raises(McpConfigError, match="MCP_STDIO_SCOPES"):
        load_mcp_server_config()


def test_enabled_http_requires_scopes_and_pinned_session(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_mcp_env(monkeypatch)
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    monkeypatch.setenv("MCP_SERVER_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_HTTP_SCOPES", "market.read")
    with pytest.raises(McpConfigError, match="MCP_HTTP_SESSION_TOKEN_SHA256"):
        load_mcp_server_config()


def test_http_alias_is_explicit_streamable_http(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_mcp_env(monkeypatch)
    monkeypatch.setenv("MCP_SERVER_TRANSPORT", "http")
    assert load_mcp_server_config().transport == "streamable-http"
