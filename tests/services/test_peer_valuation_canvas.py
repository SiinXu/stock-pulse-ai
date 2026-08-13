# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline tests for peer relative-value canvas (issue #1139)."""

from __future__ import annotations

from typing import Any, Mapping

import pytest

from src.services.peer_relative_claim_policy import evaluate_relative_claims
from src.services.peer_valuation_canvas import (
    PEER_CANVAS_SCHEMA_VERSION,
    PeerValuationCanvasService,
)
from src.services.valuation_service import ValuationService


def _fundamentals_table() -> dict[str, dict[str, Any]]:
    return {
        "600519": {
            "status": "ok",
            "belong_boards": [{"name": "白酒", "type": "行业"}],
            "valuation": {
                "data": {"pe_ratio": 30.0, "pb_ratio": 8.0, "total_mv": 2_000_000.0},
            },
            "growth": {"data": {}},
            "earnings": {
                "data": {
                    "operating_cash_flow": 100.0,
                    "currency": "CNY",
                }
            },
        },
        "000858": {
            "status": "ok",
            "valuation": {"data": {"pe_ratio": 20.0, "pb_ratio": 5.0, "total_mv": 800_000.0}},
            "growth": {"data": {}},
            "earnings": {"data": {"operating_cash_flow": 40.0, "currency": "CNY"}},
        },
        "000568": {
            "status": "ok",
            "valuation": {"data": {"pe_ratio": 25.0, "pb_ratio": 6.0, "total_mv": 600_000.0}},
            "growth": {"data": {}},
            "earnings": {"data": {"operating_cash_flow": 30.0, "currency": "CNY"}},
        },
        # Missing multiples — must remain on canvas as annotated missing.
        "000799": {
            "status": "partial",
            "valuation": {"data": {}},
            "growth": {"data": {}},
            "earnings": {"data": {}},
        },
        "AAPL": {
            "status": "ok",
            "valuation": {"data": {"pe_ratio": 28.0, "pb_ratio": 40.0, "total_mv": 3_000_000.0}},
            "growth": {"data": {}},
            "earnings": {"data": {"operating_cash_flow": 200.0, "currency": "USD"}},
        },
        "0700.HK": {
            "status": "ok",
            "valuation": {"data": {"pe_ratio": 18.0, "pb_ratio": 4.0, "total_mv": 1_500_000.0}},
            "growth": {"data": {}},
            "earnings": {
                "data": {
                    "operating_cash_flow": 80.0,
                    "financial_report": {"currency": "HKD"},
                }
            },
        },
    }


def _quote_table() -> dict[str, dict[str, Any]]:
    return {
        "600519": {"price": 1600.0, "currency": "CNY"},
        "000858": {"price": 120.0, "currency": "CNY"},
        "000568": {"price": 180.0, "currency": "CNY"},
        "000799": {"price": 50.0, "currency": "CNY"},
        "AAPL": {"price": 190.0, "currency": "USD"},
        "0700.HK": {"price": 320.0, "currency": "HKD"},
    }


def _providers():
    fund = _fundamentals_table()
    quotes = _quote_table()

    def fundamental_provider(code: str) -> Mapping[str, Any]:
        return fund.get(code, {"status": "empty", "valuation": {"data": {}}, "earnings": {"data": {}}, "growth": {"data": {}}})

    def quote_provider(code: str) -> Mapping[str, Any]:
        return quotes.get(code, {})

    return fundamental_provider, quote_provider


def _identity_fx(amount: float, from_currency: str, to_currency: str) -> dict[str, Any]:
    from_c = (from_currency or "").upper()
    to_c = (to_currency or "").upper()
    rates = {
        ("USD", "CNY"): 7.2,
        ("HKD", "CNY"): 0.92,
        ("CNY", "CNY"): 1.0,
        ("USD", "USD"): 1.0,
        ("HKD", "HKD"): 1.0,
    }
    if from_c == to_c:
        return {
            "converted_amount": float(amount),
            "rate": 1.0,
            "is_stale": False,
            "method": "identity",
            "source": "test",
            "rate_date": None,
        }
    rate = rates.get((from_c, to_c))
    if rate is None:
        return {
            "converted_amount": float(amount),
            "rate": 1.0,
            "is_stale": True,
            "method": "fx_unavailable_identity",
            "source": "unavailable",
            "rate_date": None,
        }
    return {
        "converted_amount": float(amount) * rate,
        "rate": rate,
        "is_stale": False,
        "method": "direct_rate",
        "source": "test_fixture",
        "rate_date": None,
    }


def _service() -> PeerValuationCanvasService:
    fundamental_provider, quote_provider = _providers()
    valuation = ValuationService(
        fundamental_provider=fundamental_provider,
        quote_provider=quote_provider,
    )
    return PeerValuationCanvasService(
        valuation_service=valuation,
        fx_convert=_identity_fx,
        fundamental_provider=fundamental_provider,
        quote_provider=quote_provider,
    )


def test_canvas_builds_for_sample_universe_custom_peers() -> None:
    service = _service()
    canvas = service.build(
        "600519",
        peer_source="custom",
        peer_codes=["000858", "000568", "000799"],
        base_currency="CNY",
    )
    assert canvas["schema_version"] == PEER_CANVAS_SCHEMA_VERSION
    assert canvas["status"] in {"ok", "partial"}
    # Missing-data peer may keep overall status partial; complete peers mark equity N/A.
    assert canvas["peer_set"]["source"] == "custom"
    assert "Caller-supplied" in canvas["peer_set"]["explanation"]
    codes = [row["stock_code"] for row in canvas["rows"]]
    assert codes == ["600519", "000858", "000568", "000799"]
    assert canvas["rows"][0]["role"] == "target"
    # Missing-data peer is kept, not dropped.
    missing_peer = next(row for row in canvas["rows"] if row["stock_code"] == "000799")
    assert missing_peer["data_status"] in {"missing", "partial"}
    assert "pe_ratio" in missing_peer["missing_metrics"]
    assert "000799" in canvas["peer_set"]["missing_data_codes"]
    # Medians come from valuation service (positive peers only).
    assert canvas["medians"]["pe_median"] == pytest.approx(22.5)
    assert canvas["heatmap_cells"]


def test_missing_peer_not_silently_dropped() -> None:
    service = _service()
    canvas = service.build(
        "600519",
        peer_source="custom",
        peer_codes=["MISSING1", "000858"],
    )
    peer_codes = [row["stock_code"] for row in canvas["rows"] if row["role"] == "peer"]
    assert peer_codes == ["MISSING1", "000858"]
    missing = next(row for row in canvas["rows"] if row["stock_code"] == "MISSING1")
    assert missing["data_status"] == "missing"
    assert missing["metrics"]["pe_ratio"]["status"] == "missing"
    assert missing["metrics"]["pe_ratio"]["missing_reason"] == "unavailable"


def test_industry_source_is_explainable() -> None:
    service = _service()
    canvas = service.build(
        "600519",
        peer_source="industry",
        peer_codes=["000858", "000568"],
    )
    assert canvas["peer_set"]["source"] == "industry"
    assert canvas["peer_set"]["industry_label"] == "白酒"
    assert "白酒" in canvas["peer_set"]["explanation"]
    assert canvas["peer_set"]["requested_codes"] == ["000858", "000568"]


def test_industry_without_label_does_not_invent_peers() -> None:
    fundamental_provider, quote_provider = _providers()

    def no_industry(code: str) -> Mapping[str, Any]:
        payload = dict(fundamental_provider(code))
        payload["belong_boards"] = []
        return payload

    valuation = ValuationService(
        fundamental_provider=no_industry,
        quote_provider=quote_provider,
    )
    service = PeerValuationCanvasService(
        valuation_service=valuation,
        fx_convert=_identity_fx,
        fundamental_provider=no_industry,
        quote_provider=quote_provider,
    )
    canvas = service.build(
        "AAPL",
        peer_source="industry",
        peer_codes=["MSFT"],
    )
    assert canvas["status"] == "insufficient_peers"
    assert canvas["reason"] == "industry_label_unavailable"
    assert canvas["rows"] == []


def test_cross_market_currency_normalization() -> None:
    service = _service()
    canvas = service.build(
        "AAPL",
        peer_source="custom",
        peer_codes=["0700.HK"],
        base_currency="CNY",
    )
    target = canvas["rows"][0]
    peer = canvas["rows"][1]
    assert canvas["base_currency"] == "CNY"
    # AAPL market cap 3_000_000 USD → CNY at 7.2
    assert target["metrics"]["market_cap"]["native_currency"] == "USD"
    assert target["metrics"]["market_cap"]["value"] == pytest.approx(3_000_000.0 * 7.2)
    assert target["metrics"]["market_cap"]["currency"] == "CNY"
    # Multiples stay unitless and unconverted.
    assert target["metrics"]["pe_ratio"]["currency"] is None
    assert target["metrics"]["pe_ratio"]["value"] == pytest.approx(28.0)
    assert peer["metrics"]["market_cap"]["native_currency"] == "HKD"
    assert peer["metrics"]["market_cap"]["value"] == pytest.approx(1_500_000.0 * 0.92)


def test_custom_source_requires_peers() -> None:
    service = _service()
    canvas = service.build("600519", peer_source="custom", peer_codes=[])
    assert canvas["status"] == "insufficient_peers"
    assert canvas["reason"] == "custom_peers_required"


def test_relative_claims_without_canvas_are_downgraded() -> None:
    decision = evaluate_relative_claims(
        text="The name is cheaper than peers on PE and trades at a discount to peers.",
        canvas=None,
    )
    assert decision["status"] == "downgraded"
    assert decision["reason"] == "relative_claims_without_canvas"
    assert decision["confidence_adjustment"] < 0


def test_relative_claims_with_canvas_but_no_citation_downgraded() -> None:
    service = _service()
    canvas = service.build(
        "600519",
        peer_source="custom",
        peer_codes=["000858"],
    )
    decision = evaluate_relative_claims(
        text="Premium to peers looks stretched on a relative basis.",
        canvas=canvas,
    )
    assert decision["status"] == "downgraded"
    assert decision["reason"] == "relative_claims_missing_canvas_citation"


def test_relative_claims_with_canvas_citation_allowed() -> None:
    service = _service()
    canvas = service.build(
        "600519",
        peer_source="custom",
        peer_codes=["000858"],
    )
    decision = evaluate_relative_claims(
        text=(
            "PE premium to peers is grounded in "
            "canvas.rows[0].metrics.pe_ratio versus peer median."
        ),
        canvas=canvas,
    )
    assert decision["status"] == "ok"
    assert decision["reason"] == "relative_claims_cite_canvas"
    assert decision["citations"]


def test_no_relative_language_is_ok_without_canvas() -> None:
    decision = evaluate_relative_claims(
        text="Operating cash flow improved year over year.",
        canvas=None,
    )
    assert decision["status"] == "ok"
    assert decision["action"] == "none"


def test_canvas_status_ok_when_core_metrics_present() -> None:
    """Review counterexample: healthy PE/PB peers must not stay forced-partial
    solely because peer equity_value is out of scope.
    """
    service = _service()
    canvas = service.build(
        "600519",
        peer_source="custom",
        peer_codes=["000858", "000568"],
        base_currency="CNY",
    )
    peer_rows = [row for row in canvas["rows"] if row["role"] == "peer"]
    assert peer_rows
    for row in peer_rows:
        assert row["metrics"]["equity_value"]["status"] == "not_applicable"
        assert "equity_value" not in row["missing_metrics"]
        assert "equity_value" in row["not_applicable_metrics"]
    # Core multiples + price/market_cap present for all rows in fixture → ok
    assert canvas["status"] == "ok"
    assert canvas["claim_policy"]["policy_version"] == "peer-relative-claim-policy-v1"


def test_industry_membership_is_caller_asserted() -> None:
    service = _service()
    canvas = service.build(
        "600519",
        peer_source="industry",
        peer_codes=["000858"],
    )
    assert canvas["peer_set"]["membership"] == "caller_asserted"
    assert "caller-asserted" in canvas["peer_set"]["explanation"]


def test_fx_converter_reuses_single_service_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review counterexample: PortfolioService must not be reconstructed per cell."""
    import sys
    import types

    calls = {"n": 0}

    class FakePortfolio:
        def __init__(self) -> None:
            calls["n"] += 1

        def convert_amount_with_provenance(self, **kwargs):  # type: ignore[no-untyped-def]
            amount = float(kwargs["amount"])
            return {
                "converted_amount": amount * 7.0,
                "rate": 7.0,
                "is_stale": False,
                "method": "direct_rate",
                "source": "test",
                "rate_date": None,
            }

    fake_mod = types.ModuleType("src.services.portfolio_service")
    fake_mod.PortfolioService = FakePortfolio  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.services.portfolio_service", fake_mod)

    from src.services.peer_valuation_canvas import _portfolio_fx_converter

    convert = _portfolio_fx_converter()
    first = convert(10.0, "USD", "CNY")
    second = convert(20.0, "HKD", "CNY")
    assert first["converted_amount"] == pytest.approx(70.0)
    assert second["converted_amount"] == pytest.approx(140.0)
    assert calls["n"] == 1, f"expected one PortfolioService, got {calls['n']}"

