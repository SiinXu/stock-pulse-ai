# -*- coding: utf-8 -*-
"""Sandbox isolation policy and simulation labels (Issues #247 / #202 / #442).

Sandbox owns environment isolation and safety. Backtest owns historical
validation methodology. These policies never grant production authority.
"""

from __future__ import annotations

from typing import Any, Dict

SANDBOX_MODE = "sandbox"
SIMULATION_LABEL = "SIMULATION"

SIMULATION_BANNER_EN = (
    "[SIMULATION] Sandbox run only. Results are isolated, labeled simulated, "
    "and never write production decision records, signals, or notifications."
)
SIMULATION_BANNER_ZH = (
    "[模拟] 沙箱运行。结果已隔离并标注为模拟，"
    "不会写入生产决策记录、信号或真实通知。"
)

# Hard isolation contract. Values are intentional and must stay fail-closed.
# Enforcement in batch-1 (see docs/agent-sandbox.md):
# - persist_analysis_history / persist_decision_signal / send_real_notifications
#   are wired at authoritative production write entry points.
# - persist_agent_memory / place_real_orders / write_production_portfolio are
#   declared intent for promotion receipts; write fences land in later batches.
# - FakeClock is context-local, not a process-wide wall-clock patch.
SANDBOX_ISOLATION_POLICY: Dict[str, Any] = {
    "mode": SANDBOX_MODE,
    "label": SIMULATION_LABEL,
    "persist_analysis_history": False,
    "persist_decision_signal": False,
    "persist_decision_memory": False,
    "persist_agent_memory": False,
    "send_real_notifications": False,
    "place_real_orders": False,
    "write_production_portfolio": False,
    "auto_promote_to_production": False,
    "enforced_in_batch1": (
        "persist_analysis_history",
        "persist_decision_signal",
        "send_real_notifications",
        "auto_promote_to_production",
    ),
    "declared_not_yet_enforced": (
        "persist_agent_memory",
        "place_real_orders",
        "write_production_portfolio",
    ),
}


def get_sandbox_isolation_policy() -> Dict[str, Any]:
    """Return a copy of the hard isolation policy for sandbox runs."""
    return dict(SANDBOX_ISOLATION_POLICY)


def simulation_markers(*, language: str = "en") -> Dict[str, str]:
    """Return human-visible simulation markers for the requested language."""
    lang = (language or "en").strip().lower()
    banner = SIMULATION_BANNER_ZH if lang.startswith("zh") else SIMULATION_BANNER_EN
    return {
        "mode": SANDBOX_MODE,
        "label": SIMULATION_LABEL,
        "banner": banner,
    }
