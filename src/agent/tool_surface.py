# -*- coding: utf-8 -*-
"""Compatibility import target for the Agent ToolSurface.

Canonical implementation: ``src.agent.tools.surface``. Production callers
and historical patch targets may keep importing this module.
"""

from src.agent.tools.surface import (  # noqa: F401
    NEW_TOOL_CHECKLIST,
    ToolDispatchRejection,
    ToolSurface,
    build_tool_error_result,
    tool_surface_dispatch_authorized,
    validate_outbound_url,
    validate_tool_parameter_value,
)

__all__ = [
    "NEW_TOOL_CHECKLIST",
    "ToolDispatchRejection",
    "ToolSurface",
    "build_tool_error_result",
    "tool_surface_dispatch_authorized",
    "validate_outbound_url",
    "validate_tool_parameter_value",
]
