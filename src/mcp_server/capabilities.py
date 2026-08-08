# -*- coding: utf-8 -*-
"""Capability inventory for the MCP server surface.

This inventory is the design product of issue #244: only a curated subset of
StockPulse capabilities is exposed. Management-plane operations are never
registered as MCP tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Optional, Sequence

Exposure = Literal["exposed", "not_exposed"]
RiskLevel = Literal["read", "write_costly", "admin"]


@dataclass(frozen=True)
class CapabilityEntry:
    """One capability decision with rationale."""

    name: str
    exposure: Exposure
    risk_level: RiskLevel
    reason: str
    mcp_tool: Optional[str] = None


CAPABILITY_INVENTORY: Sequence[CapabilityEntry] = (
    CapabilityEntry(
        name="realtime_quote",
        exposure="exposed",
        risk_level="read",
        reason="Read-only market quote lookup via existing StockService.",
        mcp_tool="get_realtime_quote",
    ),
    CapabilityEntry(
        name="history_bars",
        exposure="exposed",
        risk_level="read",
        reason="Read-only OHLCV history via existing StockService.",
        mcp_tool="get_stock_history",
    ),
    CapabilityEntry(
        name="analysis_history_list",
        exposure="exposed",
        risk_level="read",
        reason="Read-only analysis run list via existing HistoryService.",
        mcp_tool="list_analysis_history",
    ),
    CapabilityEntry(
        name="analysis_history_detail",
        exposure="exposed",
        risk_level="read",
        reason="Read-only analysis detail via existing HistoryService.",
        mcp_tool="get_analysis_detail",
    ),
    CapabilityEntry(
        name="analysis_markdown_report",
        exposure="exposed",
        risk_level="read",
        reason="Read-only markdown report projection via existing HistoryService.",
        mcp_tool="get_analysis_report",
    ),
    CapabilityEntry(
        name="portfolio_accounts",
        exposure="exposed",
        risk_level="read",
        reason="Read-only portfolio account list via existing PortfolioService.",
        mcp_tool="list_portfolio_accounts",
    ),
    CapabilityEntry(
        name="portfolio_snapshot",
        exposure="exposed",
        risk_level="read",
        reason="Read-only portfolio snapshot via existing PortfolioService.",
        mcp_tool="get_portfolio_snapshot",
    ),
    CapabilityEntry(
        name="analysis_task_status",
        exposure="exposed",
        risk_level="read",
        reason="Read-only task status from the existing task queue.",
        mcp_tool="get_analysis_status",
    ),
    CapabilityEntry(
        name="trigger_analysis",
        exposure="exposed",
        risk_level="write_costly",
        reason=(
            "Triggers analysis through AnalysisApiService with global analysis lock, "
            "timeout, and max-stock bounds. Costly LLM path; not unlimited."
        ),
        mcp_tool="trigger_analysis",
    ),
    CapabilityEntry(
        name="system_config_read_write",
        exposure="not_exposed",
        risk_level="admin",
        reason=(
            "System configuration can change auth, providers, and secrets. "
            "Exposing it via MCP would open the management plane to external agents."
        ),
    ),
    CapabilityEntry(
        name="auth_password_session_admin",
        exposure="not_exposed",
        risk_level="admin",
        reason=(
            "Password and session administration must stay on the dedicated auth API; "
            "MCP reuses sessions but never manages credentials."
        ),
    ),
    CapabilityEntry(
        name="secret_and_api_key_management",
        exposure="not_exposed",
        risk_level="admin",
        reason="API keys and provider secrets must not be discoverable or writable via MCP tools.",
    ),
    CapabilityEntry(
        name="security_audit_admin",
        exposure="not_exposed",
        risk_level="admin",
        reason="Security audit records and admin controls are out of scope for external agents.",
    ),
    CapabilityEntry(
        name="plugin_load_and_install",
        exposure="not_exposed",
        risk_level="admin",
        reason="Plugin loading is process-level code execution; not an MCP tool surface.",
    ),
    CapabilityEntry(
        name="watchlist_mutation",
        exposure="not_exposed",
        risk_level="admin",
        reason=(
            "Mutating STOCK_LIST changes durable operator configuration; "
            "kept off MCP to avoid silent portfolio/watchlist drift from agents."
        ),
    ),
    CapabilityEntry(
        name="portfolio_trade_mutation",
        exposure="not_exposed",
        risk_level="write_costly",
        reason=(
            "Recording trades/cash/corporate actions mutates financial state; "
            "MCP V0 exposes snapshots only."
        ),
    ),
    CapabilityEntry(
        name="agent_chat_and_tools",
        exposure="not_exposed",
        risk_level="write_costly",
        reason=(
            "Internal Agent chat/tools use a separate registry (ToolSurface). "
            "MCP tools must not alias or re-export that registry."
        ),
    ),
)


def exposed_capabilities() -> List[CapabilityEntry]:
    """Return capabilities that map to registered MCP tools."""
    return [c for c in CAPABILITY_INVENTORY if c.exposure == "exposed"]


def not_exposed_capabilities() -> List[CapabilityEntry]:
    """Return capabilities deliberately withheld from MCP."""
    return [c for c in CAPABILITY_INVENTORY if c.exposure == "not_exposed"]


def exposed_tool_names() -> List[str]:
    """Return MCP tool names that must be advertised."""
    return [c.mcp_tool for c in exposed_capabilities() if c.mcp_tool]


def inventory_as_dicts() -> List[dict]:
    """Serialize inventory for docs/tests/diagnostics."""
    return [
        {
            "name": c.name,
            "exposure": c.exposure,
            "risk_level": c.risk_level,
            "reason": c.reason,
            "mcp_tool": c.mcp_tool,
        }
        for c in CAPABILITY_INVENTORY
    ]
