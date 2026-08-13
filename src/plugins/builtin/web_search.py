# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Built-in lifecycle wrapper for Agent Web Search tools (issue #432)."""

from __future__ import annotations

from typing import Any

from src.agent.tools.search_tools import build_search_tools
from src.plugins.constants import PLUGIN_APPLICATION_VERSION
from src.plugins.manifest import PluginManifest
from src.plugins.plugin import Plugin
from src.plugins.registry import PluginContext


class WebSearchAgentToolPlugin(Plugin):
    """Register core search tools through the agent_tool extension point.

    Search tools remain always-on by default (same as the former direct
    ToolRegistry path). Registration is ToolSurface-owned ToolDefinition only;
    handlers still execute through ToolSurface, not Plugin.execute.
    """

    def __init__(self) -> None:
        super().__init__(
            PluginManifest.model_validate(
                {
                    "id": "builtin.web_search",
                    "name": "Agent Web Search Tools",
                    "version": "1.0.0",
                    "minAppVersion": PLUGIN_APPLICATION_VERSION,
                    "description": (
                        "Built-in Agent tools for stock news and multi-dimensional "
                        "intelligence search (issue #432 migration)."
                    ),
                    "author": "StockPulse contributors",
                    # Must cover ToolPolicy.permissions on every registered tool
                    # (load-time subset check; not a process sandbox).
                    "permissions": ["news:read", "intel:read"],
                }
            )
        )
        self._tools: list[Any] = []

    def onload(self, context: PluginContext) -> None:
        tools = build_search_tools()
        for tool in tools:
            context.register(
                "agent_tool",
                tool.name,
                tool,
                metadata={
                    "builtin": True,
                    "capability": "web_search",
                    "category": tool.category,
                },
            )
        self._tools = list(tools)

    def onunload(self) -> None:
        self._tools = []
