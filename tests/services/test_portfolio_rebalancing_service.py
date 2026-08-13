# -*- coding: utf-8 -*-
"""Deterministic known-answer tests for portfolio rebalancing / position bands.

Issues #237 and #126. Model output is not the source of numbers under test.
"""

from __future__ import annotations

import math
import unittest
from typing import Any, Dict, List, Mapping, Optional
from unittest.mock import MagicMock

from src.services.portfolio_rebalancing_service import (
    DISCLAIMER,
    PortfolioRebalancingService,
    avg_pairwise_correlation,
    build_breaches,
    build_rebalance_suggestions,
    compute_position_band,
    effective_single_name_cap_pct,
    weights_from_snapshot,
)


def _snapshot(positions: Mapping[str, float], *, currency: str = "CNY") -> Dict[str, Any]:
    return {
        "currency": currency,
        "accounts": [
            {
                "positions": [
                    {"symbol": symbol, "market_value_base": mv}
                    for symbol, mv in positions.items()
                ]
            }
        ],
    }


def _ok_risk(
    *,
    weights: Mapping[str, float],
    var_pct: float = 2.0,
    hhi: Optional[float] = None,
    correlation_status: str = "ok",
    var_status: str = "ok",
    overall: str = "ok",
) -> Dict[str, Any]:
    weight_items = [
        {"symbol": s, "weight_pct": round(w * 100.0, 6)}
        for s, w in sorted(weights.items())
    ]
    total_hhi = hhi if hhi is not None else sum(w * w for w in weights.values())
    n = len(weights) or 1
    symbols = sorted(weights.keys())
    matrix: List[List[Optional[float]]] = [
        [1.0 if i == j else 0.1 for j in range(n)] for i in range(n)
    ]
    return {
        "status": overall,
        "currency": "CNY",
        "portfolio_value": 100_000.0,
        "var": {
            "status": var_status,
            "var_pct": var_pct if var_status == "ok" else None,
            "status_message": None if var_status == "ok" else "insufficient",
        },
        "correlation": {
            "status": correlation_status,
            "symbols": symbols if correlation_status == "ok" else [],
            "matrix": matrix if correlation_status == "ok" else [],
        },
        "concentration": {
            "status": "ok",
            "hhi": total_hhi,
            "effective_n": (1.0 / total_hhi) if total_hhi > 0 else 0.0,
            "diversification_score": 0.5,
            "top_weight_pct": max((w * 100 for w in weights.values()), default=0.0),
            "position_count": n,
            "weights": weight_items,
        },
    }


class PureMathRebalancingTests(unittest.TestCase):
    def test_weights_from_snapshot_cross_currency_uses_base_only(self) -> None:
        snap = _snapshot({"AAPL": 40_000.0, "0700.HK": 60_000.0}, currency="CNY")
        weights, total, currency = weights_from_snapshot(snap)
        self.assertEqual(currency, "CNY")
        self.assertAlmostEqual(total, 100_000.0, places=6)
        self.assertAlmostEqual(weights["AAPL"], 0.4, places=8)
        self.assertAlmostEqual(weights["0700.HK"], 0.6, places=8)

    def test_weights_reject_non_finite_market_value(self) -> None:
        snap = _snapshot({"AAA": float("nan")})
        with self.assertRaises(ValueError):
            weights_from_snapshot(snap)

    def test_effective_cap_is_min_of_band_and_soft(self) -> None:
        self.assertAlmostEqual(
            effective_single_name_cap_pct(
                risk_tolerance="moderate", soft_max_weight=0.15
            ),
            15.0,
            places=6,
        )
        self.assertAlmostEqual(
            effective_single_name_cap_pct(
                risk_tolerance="aggressive", soft_max_weight=0.50
            ),
            40.0,
            places=6,
        )

    def test_single_name_overload_trim_known_answer(self) -> None:
        # Only AAA breaches the 25% cap; BBB stays inside.
        weights_pct = {"AAA": 60.0, "BBB": 20.0, "CCC": 20.0}
        breaches = build_breaches(
            weights_pct=weights_pct,
            risk_tolerance="moderate",
            concentration={"hhi": 0.44, "effective_n": 2.27},
            var_pct=2.0,
            soft_max_weight=0.25,
        )
        self.assertTrue(any(b["kind"] == "single_name_cap" and b["symbol"] == "AAA" for b in breaches))
        self.assertFalse(any(b.get("symbol") == "BBB" for b in breaches if b["kind"] == "single_name_cap"))
        suggestions = build_rebalance_suggestions(
            weights_pct=weights_pct,
            portfolio_value=100_000.0,
            risk_tolerance="moderate",
            drift_threshold_pct=5.0,
            breaches=breaches,
            soft_max_weight=0.25,
        )
        aaa = [s for s in suggestions if s["symbol"] == "AAA"]
        self.assertEqual(len(aaa), 1)
        s0 = aaa[0]
        self.assertEqual(s0["action"], "trim")
        self.assertAlmostEqual(s0["from_weight_pct"], 60.0, places=6)
        self.assertAlmostEqual(s0["to_weight_pct"], 25.0, places=6)
        self.assertAlmostEqual(s0["delta_weight_pct"], -35.0, places=6)
        self.assertAlmostEqual(s0["approx_notional"], -35_000.0, places=4)
        self.assertIn("25.00%", s0["rationale"])
        self.assertFalse(s0["auto_execute"])
        self.assertTrue(s0["is_suggestion_only"])
        self.assertTrue(s0["assumptions"])

    def test_within_band_no_suggestions(self) -> None:
        weights_pct = {"A": 25.0, "B": 25.0, "C": 25.0, "D": 25.0}
        breaches = build_breaches(
            weights_pct=weights_pct,
            risk_tolerance="moderate",
            concentration={"hhi": 0.25, "effective_n": 4.0},
            var_pct=2.0,
            soft_max_weight=0.25,
        )
        suggestions = build_rebalance_suggestions(
            weights_pct=weights_pct,
            portfolio_value=100_000.0,
            risk_tolerance="moderate",
            drift_threshold_pct=5.0,
            breaches=breaches,
            soft_max_weight=0.25,
        )
        self.assertEqual(suggestions, [])

    def test_correlation_sort_is_deterministic(self) -> None:
        weights_pct = {"AAA": 30.0, "BBB": 30.0, "CCC": 40.0}
        matrix = [
            [1.0, 0.9, 0.1],
            [0.9, 1.0, 0.1],
            [0.1, 0.1, 1.0],
        ]
        symbols = ["AAA", "BBB", "CCC"]
        avg_aaa = avg_pairwise_correlation(symbol="AAA", symbols=symbols, matrix=matrix)
        avg_bbb = avg_pairwise_correlation(symbol="BBB", symbols=symbols, matrix=matrix)
        self.assertIsNotNone(avg_aaa)
        self.assertIsNotNone(avg_bbb)
        self.assertAlmostEqual(avg_aaa or 0.0, avg_bbb or 0.0, places=6)

        breaches = build_breaches(
            weights_pct=weights_pct,
            risk_tolerance="moderate",
            concentration={"hhi": 0.34, "effective_n": 2.9},
            var_pct=4.0,
            soft_max_weight=0.40,
        )
        suggestions = build_rebalance_suggestions(
            weights_pct=weights_pct,
            portfolio_value=100_000.0,
            risk_tolerance="moderate",
            drift_threshold_pct=5.0,
            breaches=breaches,
            correlation={"status": "ok", "symbols": symbols, "matrix": matrix},
            soft_max_weight=0.40,
        )
        self.assertGreaterEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["symbol"], "CCC")

    def test_position_band_held_vs_unheld(self) -> None:
        held = compute_position_band(
            symbol="AAA",
            current_weight_pct_value=20.0,
            risk_tolerance="moderate",
            signal="buy",
            soft_max_weight=0.15,
            portfolio_aware_enabled=True,
            has_portfolio=True,
        )
        unheld = compute_position_band(
            symbol="AAA",
            current_weight_pct_value=0.0,
            risk_tolerance="moderate",
            signal="buy",
            soft_max_weight=0.15,
            portfolio_aware_enabled=True,
            has_portfolio=True,
        )
        self.assertEqual(held["action"], "reduce")
        self.assertEqual(unheld["action"], "add")
        self.assertLess(held["target_weight_pct_high"], 20.0 + 1e-9)
        self.assertIn("effective_cap", held["rationale"])
        self.assertFalse(held["auto_execute"])

    def test_stock_only_fallback_without_portfolio(self) -> None:
        band = compute_position_band(
            symbol="ZZZ",
            current_weight_pct_value=0.0,
            risk_tolerance="conservative",
            signal="hold",
            soft_max_weight=0.15,
            portfolio_aware_enabled=True,
            has_portfolio=False,
        )
        self.assertEqual(band["mode"], "stock_only_fallback")
        self.assertGreater(band["target_weight_pct_high"], 0.0)
        self.assertIn("not investment advice", DISCLAIMER.lower())

    def test_position_band_cap_applies_soft_max_when_sizing_disabled(self) -> None:
        band = compute_position_band(
            symbol="AAA",
            current_weight_pct_value=20.0,
            risk_tolerance="moderate",
            signal="hold",
            soft_max_weight=0.15,
            portfolio_aware_enabled=False,
            has_portfolio=True,
        )
        self.assertEqual(band["mode"], "sizing_disabled")
        self.assertAlmostEqual(band["effective_cap_pct"], 15.0, places=6)
        self.assertLessEqual(band["target_weight_pct_high"], 15.0 + 1e-9)
        self.assertIn("min(risk_band, soft_max)", band["assumptions"][-1])

    def test_position_band_cap_applies_soft_max_in_stock_only_fallback(self) -> None:
        band = compute_position_band(
            symbol="AAA",
            current_weight_pct_value=0.0,
            risk_tolerance="moderate",
            signal="hold",
            soft_max_weight=0.15,
            portfolio_aware_enabled=True,
            has_portfolio=False,
        )
        self.assertEqual(band["mode"], "stock_only_fallback")
        self.assertAlmostEqual(band["effective_cap_pct"], 15.0, places=6)
        self.assertLessEqual(band["target_weight_pct_high"], 15.0 + 1e-9)

    def test_position_band_rejects_non_finite_current(self) -> None:
        with self.assertRaises(ValueError):
            compute_position_band(
                symbol="AAA",
                current_weight_pct_value=float("inf"),
                risk_tolerance="moderate",
            )


class PortfolioRebalancingServiceTests(unittest.TestCase):
    def _service(
        self,
        snapshot: Dict[str, Any],
        risk: Dict[str, Any],
    ) -> PortfolioRebalancingService:
        portfolio = MagicMock()
        portfolio.get_portfolio_snapshot.return_value = snapshot
        risk_svc = MagicMock()
        risk_svc.get_risk_metrics.return_value = risk
        return PortfolioRebalancingService(
            portfolio_service=portfolio,
            risk_metrics_service=risk_svc,
        )

    def test_empty_portfolio_refuses(self) -> None:
        service = self._service(_snapshot({}), _ok_risk(weights={}))
        result = service.get_recommendations(risk_tolerance="moderate", soft_max_weight=0.25)
        self.assertEqual(result["status"], "empty_portfolio")
        self.assertEqual(result["suggestions"], [])
        self.assertTrue(result["is_suggestion_only"])
        self.assertFalse(result["auto_execute"])
        self.assertIn("not investment advice", result["disclaimer"].lower())

    def test_insufficient_history_refuses_suggestions(self) -> None:
        weights = {"AAA": 0.6, "BBB": 0.4}
        risk = _ok_risk(weights=weights, var_status="insufficient_history", overall="insufficient_history")
        service = self._service(_snapshot({"AAA": 60_000, "BBB": 40_000}), risk)
        result = service.get_recommendations(risk_tolerance="moderate", soft_max_weight=0.25)
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["suggestions"], [])
        self.assertTrue(result["position_bands"])

    def test_overload_produces_explainable_trim(self) -> None:
        weights = {"AAA": 0.6, "BBB": 0.4}
        risk = _ok_risk(weights=weights, var_pct=2.0, hhi=0.52)
        service = self._service(_snapshot({"AAA": 60_000, "BBB": 40_000}), risk)
        result = service.get_recommendations(
            risk_tolerance="moderate",
            soft_max_weight=0.25,
            stock_signals={"AAA": "hold", "BBB": "buy"},
        )
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(len(result["suggestions"]), 1)
        trim = result["suggestions"][0]
        self.assertEqual(trim["symbol"], "AAA")
        self.assertEqual(trim["action"], "trim")
        self.assertIn("cap", trim["rationale"].lower())
        self.assertTrue(all(math.isfinite(float(trim[k])) for k in (
            "from_weight_pct", "to_weight_pct", "delta_weight_pct", "approx_notional"
        )))
        self.assertTrue(result["position_bands"])
        for band in result["position_bands"]:
            self.assertIn("rationale", band)
            self.assertFalse(band["auto_execute"])

    def test_suggest_position_for_symbol_fallback_without_snapshot(self) -> None:
        portfolio = MagicMock()
        portfolio.get_portfolio_snapshot.side_effect = RuntimeError("no db")
        service = PortfolioRebalancingService(
            portfolio_service=portfolio,
            risk_metrics_service=MagicMock(),
        )
        result = service.suggest_position_for_symbol(
            symbol="600519",
            signal="buy",
            risk_tolerance="moderate",
            soft_max_weight=0.15,
        )
        self.assertFalse(result["has_portfolio"])
        self.assertEqual(result["mode"], "stock_only_fallback")
        self.assertAlmostEqual(result["effective_cap_pct"], 15.0, places=6)
        self.assertLessEqual(result["target_weight_pct_high"], 15.0 + 1e-9)
        self.assertIn("not investment advice", result["disclaimer"].lower())
        self.assertFalse(result["auto_execute"])


if __name__ == "__main__":
    unittest.main()
