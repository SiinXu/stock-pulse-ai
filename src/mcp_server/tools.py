# -*- coding: utf-8 -*-
"""MCP tool definitions and dispatch.

This registry is **not** the Agent ToolSurface registry
(``src.agent.tools.registry``). MCP tools and Agent tools remain separate.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional

from src.mcp_server.capabilities import exposed_tool_names
from src.mcp_server.errors import map_exception_to_tool_result, tool_success_result
from src.mcp_server.handlers import McpToolHandlers

ToolHandler = Callable[..., Any]


_TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "get_realtime_quote",
        "description": "Get a realtime quote for one stock code (read-only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stock_code": {
                    "type": "string",
                    "description": "Stock code, e.g. 600519, hk00700, AAPL",
                },
            },
            "required": ["stock_code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_stock_history",
        "description": "Get historical OHLCV bars for one stock (read-only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stock_code": {"type": "string"},
                "period": {
                    "type": "string",
                    "description": "Bar period (default daily)",
                    "default": "daily",
                },
                "days": {
                    "type": "integer",
                    "description": "Lookback days (1-3650)",
                    "default": 30,
                },
            },
            "required": ["stock_code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_analysis_history",
        "description": "List past analysis runs with optional filters (read-only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stock_code": {"type": "string"},
                "report_type": {"type": "string"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "page": {"type": "integer", "default": 1},
                "limit": {"type": "integer", "default": 20},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_analysis_detail",
        "description": "Get one analysis history record by id (read-only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string"},
            },
            "required": ["record_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_analysis_report",
        "description": "Get markdown report text for one analysis record (read-only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "record_id": {"type": "string"},
            },
            "required": ["record_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_portfolio_accounts",
        "description": "List portfolio accounts (read-only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_inactive": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_portfolio_snapshot",
        "description": "Get a portfolio snapshot (read-only; realtime quotes optional).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer"},
                "as_of": {"type": "string", "description": "YYYY-MM-DD"},
                "cost_method": {"type": "string", "default": "fifo"},
                "include_realtime": {"type": "boolean", "default": False},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_analysis_status",
        "description": "Get status of an async analysis task (read-only).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "trigger_analysis",
        "description": (
            "Trigger stock analysis (costly). Protected by a global analysis lock, "
            "max stock count, and async submission by default."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "stock_code": {"type": "string"},
                "stock_codes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "report_type": {
                    "type": "string",
                    "default": "detailed",
                    "description": "simple | detailed | full | brief",
                },
                "force_refresh": {"type": "boolean", "default": False},
                "async_mode": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
    },
]


def list_tool_definitions() -> List[Dict[str, Any]]:
    """Return MCP tool descriptors for tools/list."""
    allowed = set(exposed_tool_names())
    return [t for t in _TOOL_DEFINITIONS if t["name"] in allowed]


def _handler_map(handlers: McpToolHandlers) -> Mapping[str, ToolHandler]:
    return {
        "get_realtime_quote": handlers.get_realtime_quote,
        "get_stock_history": handlers.get_stock_history,
        "list_analysis_history": handlers.list_analysis_history,
        "get_analysis_detail": handlers.get_analysis_detail,
        "get_analysis_report": handlers.get_analysis_report,
        "list_portfolio_accounts": handlers.list_portfolio_accounts,
        "get_portfolio_snapshot": handlers.get_portfolio_snapshot,
        "get_analysis_status": handlers.get_analysis_status,
        "trigger_analysis": handlers.trigger_analysis,
    }


def call_tool(
    handlers: McpToolHandlers,
    name: str,
    arguments: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Dispatch a tools/call request to the matching handler."""
    allowed = set(exposed_tool_names())
    if name not in allowed:
        from src.mcp_server.errors import tool_error_result

        return tool_error_result(
            "validation_error",
            f"Unknown or non-exposed tool: {name}",
        )
    fn = _handler_map(handlers).get(name)
    if fn is None:
        from src.mcp_server.errors import tool_error_result

        return tool_error_result("validation_error", f"Tool not implemented: {name}")

    args = dict(arguments or {})
    try:
        payload = fn(**args)
        return tool_success_result(payload)
    except TypeError as exc:
        from src.mcp_server.errors import tool_error_result

        return tool_error_result("validation_error", str(exc) or "Invalid parameters")
    except Exception as exc:  # broad-exception: map to stable MCP/API error envelope
        return map_exception_to_tool_result(exc)
