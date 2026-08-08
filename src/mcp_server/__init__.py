# -*- coding: utf-8 -*-
"""Optional MCP (Model Context Protocol) server adapter for StockPulse.

This package is a thin adapter over existing services. It is disabled by default
and never starts from the main API process unless an operator explicitly runs
``python -m src.mcp_server`` with ``MCP_SERVER_ENABLED=true``.

MCP tools registered here are intentionally separate from Agent ToolSurface
(``src.agent.tools.registry``).
"""

from __future__ import annotations

__all__ = [
    "MCP_PROTOCOL_VERSION",
    "SERVER_NAME",
    "SERVER_VERSION",
]

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "stock-pulse-ai"
SERVER_VERSION = "0.1.0"
