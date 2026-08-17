# -*- coding: utf-8 -*-
"""
Agent tools package.

Provides ToolRegistry, @tool decorator, and wrapped tools
for the stock analysis agent.
"""

from src.agent.tools.registry import ToolRegistry, ToolDefinition, ToolParameter, ToolPolicy, tool
from src.agent.tools.surface import (
    NEW_TOOL_CHECKLIST,
    ToolSurface,
    build_tool_error_result,
    tool_surface_dispatch_authorized,
)

__all__ = [
    "NEW_TOOL_CHECKLIST",
    "ToolDefinition",
    "ToolParameter",
    "ToolPolicy",
    "ToolRegistry",
    "ToolSurface",
    "build_tool_error_result",
    "tool",
    "tool_surface_dispatch_authorized",
]
