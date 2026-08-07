# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic known-answer tests for DCF and relative valuation."""

from __future__ import annotations

import pytest

from src.services.valuation_service import (
    INSUFFICIENT_FUNDAMENTALS,
    VALUATION_DISCLAIMER,
    VALUATION_SCHEMA_VERSION,
    ValuationService,
    build_dcf_sensitivity,
    compute_dcf,
    compute_relative_valuation,
)


def test_compute_dcf_hand_computed_fixture() -> None:
    """Hand-checked Gordon-growth DCF (base=100, g=5%, r=10%, n=5, g_term=2%)."""
    result = compute_dcf(
        100.0,
        growth_rate=0.05,
        discount_rate=0.10,
        projection_years=5,
        terminal_growth_rate=0.02,
    )

    assert result["status"] == "ok"
    assert len(result["projections"]) == 5
    assert result["projections"][0]["fcf"] == pytest.approx(105.0)
    # Service rounds present values to 6 decimal places for stable JSON output.
    assert result["projections"][0]["present_value"] == pytest.approx(
        round(105.0 / 1.1, 6), abs=1e-9
    )
    assert result["projections"][4]["fcf"] == pytest.approx(
        round(100.0 * (1.05**5), 6), abs=1e-9
    )

    # Terminal value on year-5 FCF with g_term=2%, r=10%.
    fcf5 = 100.0 * (1.05**5)
    terminal = fcf5 * 1.02 / (0.10 - 0.02)
    assert result["terminal_value"] == pytest.approx(round(terminal, 6), abs=1e-9)

    expected_ev = 1446.2118899836075
    assert result["enterprise_value"] == pytest.approx(expected_ev, rel=1e-9)
    assert result["equity_value"] == pytest.approx(expected_ev, rel=1e-9)


def test_compute_dcf_rejects_terminal_above_discount() -> None:
    with pytest.raises(ValueError, match="terminal_growth_rate"):
        compute_dcf(
            100.0,
            growth_rate=0.05,
            discount_rate=0.08,
            terminal_growth_rate=0.09,
        )


def test_compute_dcf_rejects_non_positive_base() -> None:
    with pytest.raises(ValueError, match="base_fcf"):
        compute_dcf(
            0.0,
            growth_rate=0.05,
            discount_rate=0.10,
        )


def test_dcf_sensitivity_bounds_cover_base_case() -> None:
    base = compute_dcf(
        100.0,
        growth_rate=0.05,
        discount_rate=0.10,
        projection_years=5,
        terminal_growth_rate=0.02,
    )
    table = build_dcf_sensitivity(
        100.0,
        growth_rate=0.05,
        discount_rate=0.10,
        projection_years=5,
        terminal_growth_rate=0.02,
    )
    assert table["rows"]
    assert table["equity_value_low"] <= base["equity_value"] <= table["equity_value_high"]
    assert table["equity_value_mid"] is not None


def test_relative_valuation_hand_computed_fixture() -> None:
    result = compute_relative_valuation(
        target_pe=20.0,
        target_pb=4.0,
        current_price=100.0,
        peer_pe_values=[10.0, 15.0, 20.0],
        peer_pb_values=[2.0, 3.0, 4.0],
    )
    assert result["status"] == "ok"
    # EPS = 100/20 = 5; peer PE median = 15 → implied 75
    assert result["implied_prices"]["pe_based"] == pytest.approx(75.0)
    # Book/share = 100/4 = 25; peer PB median = 3 → implied 75
    assert result["implied_prices"]["pb_based"] == pytest.approx(75.0)
    assert result["premium_discount"]["pe_vs_peers_pct"] == pytest.approx(
        ((20.0 / 15.0) - 1.0) * 100.0
    )


def test_relative_valuation_missing_peers_is_insufficient() -> None:
    result = compute_relative_valuation(
        target_pe=20.0,
        target_pb=3.0,
        current_price=50.0,
        peer_pe_values=[],
        peer_pb_values=[],
    )
    assert result["status"] == INSUFFICIENT_FUNDAMENTALS
    assert "peer_multiples" in result["missing_inputs"]
    assert result["implied_prices"] == {}


def test_service_dcf_with_injected_fundamentals() -> None:
    fundamentals = {
        "status": "ok",
        "valuation": {
            "status": "ok",
            "data": {"pe_ratio": 18.0, "pb_ratio": 3.0, "total_mv": 1_800.0},
        },
        "growth": {
            "status": "ok",
            "data": {"revenue_yoy": 8.0, "net_profit_yoy": 6.0},
        },
        "earnings": {
            "status": "ok",
            "data": {
                "operating_cash_flow": 100.0,
                "net_profit_parent": 80.0,
            },
        },
    }
    quote = {"price": 18.0, "pe_ratio": 18.0, "pb_ratio": 3.0, "total_mv": 1_800.0}

    service = ValuationService(
        fundamental_provider=lambda _code: fundamentals,
        quote_provider=lambda _code: quote,
    )
    result = service.estimate(
        "TEST",
        growth_rate=0.05,
        discount_rate=0.10,
        terminal_growth_rate=0.02,
        projection_years=5,
        peer_codes=["MSFT", "GOOG"],
    )

    assert result["schema_version"] == VALUATION_SCHEMA_VERSION
    assert result["disclaimer"] == VALUATION_DISCLAIMER
    assert result["dcf"]["status"] == "ok"
    assert result["dcf"]["assumptions"]["cash_flow_source"] == "operating_cash_flow"
    assert result["dcf"]["assumptions"]["growth_source"] == "caller_override"
    assert result["dcf"]["equity_value"] == pytest.approx(1446.2118899836075, rel=1e-9)
    assert result["dcf"]["intrinsic_value_per_share"] == pytest.approx(
        round(1446.2118899836075 / (1800.0 / 18.0), 6),
        abs=1e-9,
    )
    assert result["dcf"]["sensitivity"]["equity_value_low"] is not None
    # Peers return empty by default provider → relative insufficient unless we
    # inject peer fundamentals via the same provider.
    assert "assumptions" in result["relative"]


def test_service_peer_relative_with_shared_provider() -> None:
    def provider(code: str):
        table = {
            "AAPL": {
                "status": "ok",
                "valuation": {"data": {"pe_ratio": 20.0, "pb_ratio": 4.0}},
                "growth": {"data": {}},
                "earnings": {"data": {"operating_cash_flow": 50.0}},
            },
            "MSFT": {
                "status": "ok",
                "valuation": {"data": {"pe_ratio": 15.0, "pb_ratio": 3.0}},
                "growth": {"data": {}},
                "earnings": {"data": {"operating_cash_flow": 40.0}},
            },
            "GOOG": {
                "status": "ok",
                "valuation": {"data": {"pe_ratio": 10.0, "pb_ratio": 2.0}},
                "growth": {"data": {}},
                "earnings": {"data": {"operating_cash_flow": 30.0}},
            },
        }
        return table[code]

    def quote_provider(code: str):
        prices = {"AAPL": 100.0, "MSFT": 200.0, "GOOG": 150.0}
        return {"price": prices[code]}

    service = ValuationService(
        fundamental_provider=provider,
        quote_provider=quote_provider,
    )
    result = service.estimate("AAPL", peer_codes=["MSFT", "GOOG"])
    assert result["relative"]["status"] == "ok"
    assert result["relative"]["implied_prices"]["pe_based"] == pytest.approx(62.5)
    assert result["relative"]["peers"]["pe_median"] == pytest.approx(12.5)


def test_service_missing_cash_flow_is_insufficient_not_fabricated() -> None:
    fundamentals = {
        "status": "partial",
        "valuation": {"data": {"pe_ratio": 12.0}},
        "growth": {"data": {}},
        "earnings": {"data": {"operating_cash_flow": None, "net_profit_parent": -5.0}},
    }
    service = ValuationService(
        fundamental_provider=lambda _code: fundamentals,
        quote_provider=lambda _code: {"price": 10.0},
    )
    result = service.estimate("600519")
    assert result["dcf"]["status"] == INSUFFICIENT_FUNDAMENTALS
    # Honesty: never fabricate an equity value when cash-flow inputs are missing.
    assert "equity_value" not in result["dcf"]
    assert "enterprise_value" not in result["dcf"]
    assert result["dcf"]["reason"] == INSUFFICIENT_FUNDAMENTALS
    assert VALUATION_DISCLAIMER in result["disclaimer"]
    assert result["status"] in {INSUFFICIENT_FUNDAMENTALS, "partial"}


def test_service_uses_net_profit_proxy_when_ocf_missing() -> None:
    fundamentals = {
        "status": "ok",
        "valuation": {"data": {}},
        "growth": {"data": {"revenue_yoy": 10.0}},
        "earnings": {"data": {"net_profit_parent": 100.0}},
    }
    service = ValuationService(
        fundamental_provider=lambda _code: fundamentals,
        quote_provider=lambda _code: {},
    )
    result = service.estimate(
        "000001",
        growth_rate=0.05,
        discount_rate=0.10,
        terminal_growth_rate=0.02,
        projection_years=5,
    )
    assert result["dcf"]["status"] == "ok"
    assert result["dcf"]["assumptions"]["cash_flow_source"] == "net_profit_parent_proxy"
    assert result["dcf"]["equity_value"] == pytest.approx(1446.2118899836075, rel=1e-9)
