# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract tests for the default-off valuation Agent Tool."""

from __future__ import annotations

from types import SimpleNamespace

from src.agent.tools.registry import ToolRegistry, validate_tool_capability_contract
from src.agent.tools.valuation_tools import (
    VALUATION_TOOL_NAME,
    build_valuation_tool,
    resolve_peer_code_sequence,
)
from src.services.valuation_service import ValuationService


def test_build_valuation_tool_default_off() -> None:
    tool = build_valuation_tool(SimpleNamespace(valuation_agent_tool_enabled=False))
    assert tool is None


def test_build_valuation_tool_registers_when_enabled() -> None:
    fundamentals = {
        "status": "ok",
        "valuation": {"data": {"pe_ratio": 20.0, "pb_ratio": 4.0, "total_mv": 2000.0}},
        "growth": {"data": {"revenue_yoy": 5.0}},
        "earnings": {"data": {"operating_cash_flow": 100.0}},
    }
    quotes = {"price": 20.0, "pe_ratio": 20.0, "pb_ratio": 4.0, "total_mv": 2000.0}

    def factory() -> ValuationService:
        return ValuationService(
            fundamental_provider=lambda _code: fundamentals,
            quote_provider=lambda _code: quotes,
        )

    tool = build_valuation_tool(
        SimpleNamespace(valuation_agent_tool_enabled=True),
        service_factory=factory,
    )
    assert tool is not None
    assert tool.name == VALUATION_TOOL_NAME
    assert tool.enforce_contract is True
    assert validate_tool_capability_contract(tool) is None
    assert "stock" in tool.policy.scope_dimensions

    registry = ToolRegistry()
    registry.register(tool)
    assert VALUATION_TOOL_NAME in registry

    payload = tool.handler(
        stock_code="AAPL",
        growth_rate=0.05,
        discount_rate=0.10,
        terminal_growth_rate=0.02,
        projection_years=5,
        peer_codes="",
    )
    assert payload["schema_version"] == "valuation-estimate-v1"
    assert "assumptions" in payload["dcf"]
    assert "sensitivity" in payload["dcf"]
    assert payload["disclaimer"]


def test_resolve_peer_code_sequence() -> None:
    assert resolve_peer_code_sequence("MSFT, GOOG;AMZN") == ["MSFT", "GOOG", "AMZN"]
    assert resolve_peer_code_sequence(["MSFT", " GOOG "]) == ["MSFT", "GOOG"]
    assert resolve_peer_code_sequence(None) == []
