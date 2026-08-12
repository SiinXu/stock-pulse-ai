# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Registration tests for the built-in Agent Web Search plugin (issue #432)."""

from __future__ import annotations

from types import SimpleNamespace
from src.agent.tools.registry import ToolRegistry
from src.agent.tools.search_tools import (
    ALL_SEARCH_TOOLS,
    build_search_tools,
    search_comprehensive_intel_tool,
    search_stock_news_tool,
)
from src.plugins import PluginManager, build_agent_tool_extension_registry
from src.plugins.agent_tools import validate_agent_tool_definition
from src.plugins.builtin import get_configured_builtin_plugins
from src.plugins.builtin.web_search import WebSearchAgentToolPlugin
from src.application_services import ApplicationServices


SEARCH_TOOL_NAMES = (
    search_stock_news_tool.name,
    search_comprehensive_intel_tool.name,
)


def test_builtin_catalog_always_includes_web_search_plugin() -> None:
    plugins = get_configured_builtin_plugins(
        SimpleNamespace(kronos_enabled=False, ocr_agent_tool_enabled=False)
    )
    assert any(isinstance(plugin, WebSearchAgentToolPlugin) for plugin in plugins)


def test_search_tool_definitions_satisfy_agent_tool_contract() -> None:
    for tool in build_search_tools():
        assert tool.enforce_contract is True
        assert validate_agent_tool_definition(tool) is True
    assert {tool.name for tool in ALL_SEARCH_TOOLS} == set(SEARCH_TOOL_NAMES)


def test_plugin_registers_both_search_tools_on_tool_registry() -> None:
    registry = ToolRegistry()
    manager = PluginManager(
        application_version="3.26.3",
        registry=build_agent_tool_extension_registry(registry),
    )
    plugin = WebSearchAgentToolPlugin()
    assert plugin.manifest.id == "builtin.web_search"
    assert set(plugin.manifest.permissions) == {"news:read", "intel:read"}
    assert manager.register(plugin, source="builtin").success is True
    assert manager.load(plugin.manifest.id).success is True

    for name in SEARCH_TOOL_NAMES:
        tool = registry.get(name)
        assert tool is not None
        assert tool.category == "search"

    assert manager.disable(plugin.manifest.id).success is True
    for name in SEARCH_TOOL_NAMES:
        assert registry.get(name) is None


def test_plugin_registration_matches_module_level_tool_identity() -> None:
    """Zero-behavior: plugin registers the same ToolDefinition objects."""

    registry = ToolRegistry()
    manager = PluginManager(
        application_version="3.26.3",
        registry=build_agent_tool_extension_registry(registry),
    )
    plugin = WebSearchAgentToolPlugin()
    assert manager.register(plugin, source="builtin").success is True
    assert manager.load(plugin.manifest.id).success is True

    assert registry.get("search_stock_news") is search_stock_news_tool
    assert registry.get("search_comprehensive_intel") is search_comprehensive_intel_tool


def test_application_services_registers_search_tools_on_process_registry(
    monkeypatch,
) -> None:
    registry = ToolRegistry()
    monkeypatch.setattr(
        "src.agent.runtime_assembly.get_tool_registry",
        lambda: registry,
    )
    services = ApplicationServices(
        config=SimpleNamespace(kronos_enabled=False, ocr_agent_tool_enabled=False),
        builtin_plugins=(WebSearchAgentToolPlugin(),),
        plugins_dir="",
    )
    results = services.start_plugins()
    assert results[0].success is True
    for name in SEARCH_TOOL_NAMES:
        assert registry.get(name) is not None
    services.close()
    for name in SEARCH_TOOL_NAMES:
        assert registry.get(name) is None


def test_get_tool_registry_includes_search_tools_after_composition_root() -> None:
    """Default composition root + process registry still expose search tools."""

    import src.agent.runtime_assembly as runtime_assembly
    from src.application_services import (
        get_application_services,
        set_application_services,
    )

    original_registry = runtime_assembly._TOOL_REGISTRY
    original_services = None
    try:
        # Reset process cache so this test owns construction.
        runtime_assembly._TOOL_REGISTRY = None
        set_application_services(None)
        services = get_application_services()
        # start_plugins runs during install; ensure search tools land on cache.
        registry = runtime_assembly.get_tool_registry()
        for name in SEARCH_TOOL_NAMES:
            assert registry.get(name) is not None, name
        # Same object after plugins attached.
        assert runtime_assembly.get_tool_registry() is registry
    finally:
        runtime_assembly._TOOL_REGISTRY = original_registry
        set_application_services(None)
