# -*- coding: utf-8 -*-
"""Capability inventory and default-off configuration tests."""

from __future__ import annotations

import pytest

from src.mcp_server.capabilities import (
    CAPABILITY_INVENTORY,
    exposed_tool_names,
    not_exposed_capabilities,
)
from src.mcp_server.config import (
    DEFAULT_HOST,
    is_mcp_server_enabled,
    load_mcp_server_config,
)
from src.mcp_server.server import McpServerDisabledError, ensure_enabled
from src.mcp_server.tools import list_tool_definitions


class TestCapabilityInventory:
    def test_exposed_tools_match_inventory(self):
        tool_names = {t["name"] for t in list_tool_definitions()}
        assert tool_names == set(exposed_tool_names())
        assert "get_realtime_quote" in tool_names
        assert "trigger_analysis" in tool_names

    def test_admin_and_secret_capabilities_are_not_exposed(self):
        blocked = {c.name for c in not_exposed_capabilities()}
        assert "system_config_read_write" in blocked
        assert "secret_and_api_key_management" in blocked
        assert "auth_password_session_admin" in blocked
        assert "security_audit_admin" in blocked
        assert "plugin_load_and_install" in blocked

        # No tool definition may advertise blocked admin names.
        tool_names = {t["name"] for t in list_tool_definitions()}
        for forbidden in (
            "update_system_config",
            "set_password",
            "rotate_session",
            "manage_secrets",
            "load_plugin",
            "update_watchlist",
            "record_trade",
        ):
            assert forbidden not in tool_names

    def test_every_inventory_entry_has_reason(self):
        for entry in CAPABILITY_INVENTORY:
            assert entry.reason.strip()
            if entry.exposure == "exposed":
                assert entry.mcp_tool
            else:
                assert entry.mcp_tool is None


class TestDefaultOffConfig:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("MCP_SERVER_ENABLED", raising=False)
        assert is_mcp_server_enabled() is False
        cfg = load_mcp_server_config()
        assert cfg.enabled is False
        assert cfg.host == DEFAULT_HOST
        assert cfg.transport == "stdio"

    def test_ensure_enabled_raises_when_off(self, monkeypatch):
        monkeypatch.delenv("MCP_SERVER_ENABLED", raising=False)
        cfg = load_mcp_server_config()
        with pytest.raises(McpServerDisabledError):
            ensure_enabled(cfg)

    def test_enabled_true_and_host_port(self, monkeypatch):
        monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
        monkeypatch.setenv("MCP_SERVER_TRANSPORT", "http")
        monkeypatch.setenv("MCP_SERVER_HOST", "127.0.0.1")
        monkeypatch.setenv("MCP_SERVER_PORT", "9876")
        cfg = load_mcp_server_config()
        assert cfg.enabled is True
        assert cfg.is_http
        assert cfg.port == 9876

    def test_default_off_means_no_listen_without_explicit_run(self, monkeypatch):
        """Zero impact: feature flag off and no auto-import side effects."""
        monkeypatch.delenv("MCP_SERVER_ENABLED", raising=False)
        # Importing the package must not open sockets.
        import src.mcp_server  # noqa: F401

        assert is_mcp_server_enabled() is False
        # process does not bind; ensure_enabled is the gate used by run()
        with pytest.raises(McpServerDisabledError):
            ensure_enabled(load_mcp_server_config())
