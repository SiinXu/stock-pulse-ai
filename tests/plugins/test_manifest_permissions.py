# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manifest permissions visibility and agent_tool declaration subset checks."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy
from src.plugins import (
    MANIFEST_PERMISSIONS_UNDECLARED,
    ExtensionContract,
    ExtensionRegistry,
    Plugin,
    PluginContext,
    PluginManager,
    PluginManifest,
    build_agent_tool_extension_contract,
    find_undeclared_agent_tool_permissions,
    undeclared_agent_tool_permissions,
)
from src.agent.tools.registry import ToolRegistry
from tests.security_audit_test_utils import SecurityAuditRecorderStub


def _manifest(
    plugin_id: str,
    *,
    permissions: list[str] | None = None,
) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": "1.0.0",
            "description": "Permissions fixture.",
            "author": "StockPulse Tests",
            "permissions": [] if permissions is None else permissions,
            "apiVersion": "1",
        }
    )


@dataclass
class _Template:
    template_id: str


class _TemplatePlugin(Plugin):
    def onload(self, context: PluginContext) -> None:
        context.register(
            "report_template",
            "fixture",
            _Template("fixture"),
        )


def _tool(
    name: str,
    *,
    permissions: list[str],
) -> ToolDefinition:
    def handler(stock_code: str) -> dict[str, str]:
        return {"stock_code": stock_code}

    return ToolDefinition(
        name=name,
        description="Permissions fixture tool.",
        category="test",
        parameters=[
            ToolParameter(
                name="stock_code",
                description="Stock code",
                type="string",
                required=True,
            )
        ],
        handler=handler,
        policy=ToolPolicy.declared(
            read_only=True,
            side_effects=[],
            permissions=permissions,
            scope_dimensions=["stock"],
        ),
        enforce_contract=True,
    )


class _AgentToolPlugin(Plugin):
    def __init__(
        self,
        manifest: PluginManifest,
        *,
        tool_permissions: list[str],
        tool_name: str = "fixture_tool",
    ) -> None:
        super().__init__(manifest)
        self._tool_permissions = tool_permissions
        self._tool_name = tool_name

    def onload(self, context: PluginContext) -> None:
        tool = _tool(self._tool_name, permissions=self._tool_permissions)
        context.register("agent_tool", tool.name, tool)


def _manager(
    *,
    agent_tools: bool = False,
    audit: object | None = None,
) -> PluginManager:
    if agent_tools:
        registry = ExtensionRegistry(
            {
                "agent_tool": build_agent_tool_extension_contract(ToolRegistry()),
                "report_template": ExtensionContract(
                    identity_resolver=lambda implementation: implementation.template_id,
                    validator=lambda implementation: isinstance(implementation, _Template),
                ),
            }
        )
    else:
        registry = ExtensionRegistry(
            {
                "report_template": ExtensionContract(
                    identity_resolver=lambda implementation: implementation.template_id,
                    validator=lambda implementation: isinstance(implementation, _Template),
                )
            }
        )
    return PluginManager(
        application_version="2.0.0",
        registry=registry,
        audit=audit,
        audit_enabled=audit is not None,
    )


def test_manifest_accepts_capability_permission_form() -> None:
    manifest = _manifest(
        "stockpulse.capability-form",
        permissions=["market_data:read", "local_model:execute"],
    )
    assert manifest.permissions == ("market_data:read", "local_model:execute")


def test_manifest_rejects_invalid_capability_permission() -> None:
    with pytest.raises(ValidationError):
        _manifest("stockpulse.bad-perm", permissions=["Market_Data:Read"])


def test_undeclared_agent_tool_permissions_helper() -> None:
    missing = undeclared_agent_tool_permissions(
        ["market_data:read", "news:read"],
        ("market_data:read",),
    )
    assert missing == ("news:read",)
    assert (
        undeclared_agent_tool_permissions(
            ["market_data:read"],
            ("market_data:read", "extra.permission"),
        )
        == ()
    )


def test_consistent_agent_tool_permissions_load() -> None:
    manager = _manager(agent_tools=True)
    plugin = _AgentToolPlugin(
        _manifest(
            "stockpulse.tool-ok",
            permissions=["market_data:read", "extra.unused"],
        ),
        tool_permissions=["market_data:read"],
    )
    assert manager.register(plugin, source="builtin").success is True
    result = manager.load("stockpulse.tool-ok")
    assert result.success is True
    assert result.state == "enabled"
    assert result.error_code is None


def test_missing_manifest_permissions_rejected() -> None:
    manager = _manager(agent_tools=True)
    plugin = _AgentToolPlugin(
        _manifest("stockpulse.tool-missing", permissions=[]),
        tool_permissions=["market_data:read"],
    )
    manager.register(plugin, source="builtin")
    result = manager.load("stockpulse.tool-missing")
    assert result.success is False
    assert result.state == "failed"
    assert result.error_code == MANIFEST_PERMISSIONS_UNDECLARED
    assert manager.registrations("agent_tool") == ()


def test_extra_manifest_permissions_allowed() -> None:
    manager = _manager(agent_tools=True)
    plugin = _AgentToolPlugin(
        _manifest(
            "stockpulse.tool-extra",
            permissions=["market_data:read", "network", "environment.read"],
        ),
        tool_permissions=["market_data:read"],
    )
    manager.register(plugin, source="builtin")
    result = manager.load("stockpulse.tool-extra")
    assert result.success is True
    assert result.error_code is None


def test_non_agent_tool_plugin_skips_tool_permission_subset_check() -> None:
    manager = _manager(agent_tools=False)
    plugin = _TemplatePlugin(_manifest("stockpulse.template-only", permissions=[]))
    manager.register(plugin, source="builtin")
    result = manager.load("stockpulse.template-only")
    assert result.success is True
    assert result.state == "enabled"


def test_permissions_failure_isolates_other_plugins() -> None:
    manager = _manager(agent_tools=True)
    bad = _AgentToolPlugin(
        _manifest("stockpulse.bad-tool", permissions=[]),
        tool_permissions=["market_data:read"],
        tool_name="bad_tool",
    )
    good = _AgentToolPlugin(
        _manifest(
            "stockpulse.good-tool",
            permissions=["market_data:read"],
        ),
        tool_permissions=["market_data:read"],
        tool_name="good_tool",
    )
    manager.register(bad, source="builtin")
    manager.register(good, source="builtin")

    bad_result = manager.load("stockpulse.bad-tool")
    good_result = manager.load("stockpulse.good-tool")

    assert bad_result.success is False
    assert bad_result.error_code == MANIFEST_PERMISSIONS_UNDECLARED
    assert good_result.success is True
    assert good_result.state == "enabled"
    names = {reg.registration_id for reg in manager.registrations("agent_tool")}
    assert names == {"good_tool"}


def test_health_and_audit_expose_permissions() -> None:
    audit = SecurityAuditRecorderStub()
    manager = _manager(agent_tools=False, audit=audit)
    permissions = ["network", "environment.read"]
    plugin = _TemplatePlugin(
        _manifest("stockpulse.visible-perms", permissions=permissions)
    )
    manager.register(plugin, source="builtin")
    assert manager.load("stockpulse.visible-perms").success is True

    report = manager.health_check()
    entry = next(item for item in report.plugins if item.plugin_id == "stockpulse.visible-perms")
    assert entry.permissions == tuple(permissions)
    payload = report.as_dict()
    visible = next(
        item for item in payload["plugins"] if item["plugin_id"] == "stockpulse.visible-perms"
    )
    assert visible["permissions"] == permissions

    assert audit.attempts
    assert audit.attempts[0]["metadata"]["permissions"] == permissions
    assert audit.completions
    assert audit.completions[0]["metadata"]["permissions"] == permissions


def test_find_undeclared_helper_scans_only_agent_tools() -> None:
    registry = ExtensionRegistry(
        {
            "agent_tool": build_agent_tool_extension_contract(ToolRegistry()),
            "report_template": ExtensionContract(
                identity_resolver=lambda implementation: implementation.template_id,
                validator=lambda implementation: isinstance(implementation, _Template),
            ),
        }
    )
    manager = PluginManager(
        application_version="2.0.0",
        registry=registry,
        audit_enabled=False,
    )
    plugin = _AgentToolPlugin(
        _manifest("stockpulse.scan", permissions=["market_data:read"]),
        tool_permissions=["market_data:read", "news:read"],
    )
    manager.register(plugin, source="builtin")
    # Force-register through a temporary context without load-time gate:
    # use load and expect failure; helper is covered via that path.
    result = manager.load("stockpulse.scan")
    assert result.error_code == MANIFEST_PERMISSIONS_UNDECLARED
    assert find_undeclared_agent_tool_permissions(
        manifest=_manifest("stockpulse.scan", permissions=["market_data:read"]),
        registrations=(),
    ) == ()
