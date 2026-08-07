# -*- coding: utf-8 -*-
"""Deterministic known-answer tests for portfolio risk metrics (issue #239 V0)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Dict, List
from unittest import TestCase
from unittest.mock import MagicMock

import numpy as np

from src.services.portfolio_risk_metrics_service import (
    MIN_RETURN_OBSERVATIONS,
    PortfolioRiskMetricsService,
    align_simple_returns,
    build_portfolio_returns,
    compute_concentration_metrics,
    compute_historical_var_block,
    historical_var_pct,
    pearson_correlation_matrix,
)


class PureMathRiskMetricsTests(TestCase):
    def test_historical_var_known_answer_seeded_returns(self) -> None:
        # 100 observations; 5th percentile under linear interpolation is exact for this grid.
        rng = np.random.default_rng(42)
        returns = rng.normal(loc=0.001, scale=0.02, size=100).tolist()
        confidence = 0.95
        expected = max(0.0, -float(np.percentile(returns, 5.0, method="linear")))
        actual = historical_var_pct(returns, confidence)
        self.assertAlmostEqual(actual, expected, places=12)
        self.assertGreater(actual, 0.0)

    def test_historical_var_block_scales_with_sqrt_horizon(self) -> None:
        returns = [-0.10 + 0.001 * i for i in range(80)]
        one = compute_historical_var_block(
            portfolio_returns=returns,
            portfolio_value=100_000.0,
            confidence=0.95,
            horizon_days=1,
            min_observations=60,
            observation_count=len(returns),
        )
        multi = compute_historical_var_block(
            portfolio_returns=returns,
            portfolio_value=100_000.0,
            confidence=0.95,
            horizon_days=4,
            min_observations=60,
            observation_count=len(returns),
        )
        self.assertEqual(one["status"], "ok")
        self.assertEqual(multi["status"], "ok")
        assert one["var_pct"] is not None
        assert multi["var_pct"] is not None
        self.assertAlmostEqual(multi["var_pct"], one["var_pct"] * 2.0, places=6)

    def test_historical_var_insufficient_history_never_silent_zero(self) -> None:
        block = compute_historical_var_block(
            portfolio_returns=[-0.01, 0.02, -0.03],
            portfolio_value=10_000.0,
            confidence=0.95,
            horizon_days=1,
            min_observations=MIN_RETURN_OBSERVATIONS,
            observation_count=3,
        )
        self.assertEqual(block["status"], "insufficient_history")
        self.assertIsNone(block["var_pct"])
        self.assertIsNone(block["var_value"])
        self.assertIn("Need at least", block["status_message"] or "")

    def test_equal_weight_two_asset_correlation_and_concentration(self) -> None:
        # Perfect positive correlation known answer.
        a = [0.01, -0.02, 0.03, -0.01, 0.02]
        b = [0.02, -0.04, 0.06, -0.02, 0.04]  # 2x a → corr = 1
        matrix = pearson_correlation_matrix({"AAA": a, "BBB": b}, ["AAA", "BBB"])
        self.assertAlmostEqual(matrix[0][1] or 0.0, 1.0, places=8)
        self.assertAlmostEqual(matrix[1][0] or 0.0, 1.0, places=8)
        self.assertEqual(matrix[0][0], 1.0)

        conc = compute_concentration_metrics({"AAA": 0.5, "BBB": 0.5})
        self.assertEqual(conc["status"], "ok")
        self.assertAlmostEqual(conc["hhi"] or 0.0, 0.5, places=8)
        self.assertAlmostEqual(conc["effective_n"] or 0.0, 2.0, places=6)
        self.assertAlmostEqual(conc["diversification_score"] or 0.0, 1.0, places=6)
        self.assertAlmostEqual(conc["top_weight_pct"] or 0.0, 50.0, places=6)

    def test_single_position_diversification_is_zero(self) -> None:
        conc = compute_concentration_metrics({"ONLY": 1.0})
        self.assertEqual(conc["status"], "ok")
        self.assertAlmostEqual(conc["hhi"] or 0.0, 1.0, places=8)
        self.assertAlmostEqual(conc["diversification_score"] or 0.0, 0.0, places=6)
        self.assertAlmostEqual(conc["effective_n"] or 0.0, 1.0, places=6)

    def test_align_and_portfolio_returns_known_answer(self) -> None:
        d0 = date(2024, 1, 1)
        dates = [d0 + timedelta(days=i) for i in range(5)]
        # AAA: 100, 110, 99, 108.9, 98.01 → returns +10%, -10%, +10%, -10%
        aaa = {dates[0]: 100.0, dates[1]: 110.0, dates[2]: 99.0, dates[3]: 108.9, dates[4]: 98.01}
        # BBB flat: zero returns
        bbb = {d: 50.0 for d in dates}
        return_dates, matrix, symbols = align_simple_returns(
            {"AAA": aaa, "BBB": bbb},
            lookback_trading_days=5,
        )
        self.assertEqual(symbols, ["AAA", "BBB"])
        self.assertEqual(len(return_dates), 4)
        self.assertEqual(len(matrix["AAA"]), 4)
        portfolio = build_portfolio_returns(matrix, symbols, {"AAA": 0.5, "BBB": 0.5})
        self.assertEqual(len(portfolio), 4)
        self.assertAlmostEqual(portfolio[0], 0.05, places=8)
        self.assertAlmostEqual(portfolio[1], -0.05, places=8)


class PortfolioRiskMetricsServiceTests(TestCase):
    def _service_with(
        self,
        *,
        snapshot: dict,
        closes_by_symbol: Dict[str, List[SimpleNamespace]],
    ) -> PortfolioRiskMetricsService:
        portfolio_service = MagicMock()
        portfolio_service.get_portfolio_snapshot.return_value = snapshot
        stock_repo = MagicMock()

        def _get_range(code: str, start: date, end: date):
            return closes_by_symbol.get(code, [])

        stock_repo.get_range.side_effect = _get_range
        return PortfolioRiskMetricsService(
            portfolio_service=portfolio_service,
            stock_repo=stock_repo,
        )

    @staticmethod
    def _close_rows(symbol: str, start: date, count: int, returns: List[float]) -> List[SimpleNamespace]:
        """Build count closes starting at 100 using the given returns (len = count-1)."""
        assert len(returns) == count - 1
        price = 100.0
        rows = [SimpleNamespace(date=start, close=price, code=symbol)]
        for i, ret in enumerate(returns, start=1):
            price = price * (1.0 + ret)
            rows.append(SimpleNamespace(date=start + timedelta(days=i), close=price, code=symbol))
        return rows

    def test_empty_portfolio_status(self) -> None:
        service = self._service_with(
            snapshot={"currency": "CNY", "accounts": []},
            closes_by_symbol={},
        )
        result = service.get_risk_metrics(as_of=date(2026, 1, 15))
        self.assertEqual(result["status"], "empty_portfolio")
        self.assertEqual(result["var"]["status"], "unavailable")
        self.assertIsNone(result["var"]["var_pct"])
        self.assertEqual(result["correlation"]["status"], "unavailable")
        self.assertEqual(result["concentration"]["status"], "empty_portfolio")
        self.assertFalse(result["assumptions"]["provider_calls_on_hot_path"])

    def test_insufficient_history_never_returns_zero_var(self) -> None:
        as_of = date(2026, 3, 1)
        start = as_of - timedelta(days=20)
        # Only ~10 returns — below MIN_RETURN_OBSERVATIONS.
        returns = [0.01 if i % 2 == 0 else -0.01 for i in range(10)]
        rows_a = self._close_rows("AAA", start, 11, returns)
        rows_b = self._close_rows("BBB", start, 11, returns)
        snapshot = {
            "currency": "CNY",
            "accounts": [
                {
                    "positions": [
                        {"symbol": "AAA", "market_value_base": 5000.0},
                        {"symbol": "BBB", "market_value_base": 5000.0},
                    ]
                }
            ],
        }
        service = self._service_with(
            snapshot=snapshot,
            closes_by_symbol={"AAA": rows_a, "BBB": rows_b},
        )
        result = service.get_risk_metrics(
            as_of=as_of,
            lookback_trading_days=MIN_RETURN_OBSERVATIONS,
        )
        self.assertEqual(result["status"], "insufficient_history")
        self.assertEqual(result["var"]["status"], "insufficient_history")
        self.assertIsNone(result["var"]["var_pct"])
        self.assertIsNone(result["var"]["var_value"])
        self.assertEqual(result["concentration"]["status"], "ok")
        self.assertAlmostEqual(result["concentration"]["top_weight_pct"], 50.0, places=4)

    def test_full_metrics_known_answer_with_seeded_prices(self) -> None:
        as_of = date(2026, 6, 1)
        # 70 trading closes → 69 returns (> 60).
        n_closes = 70
        start = as_of - timedelta(days=n_closes - 1)
        rng = np.random.default_rng(7)
        ret_a = rng.normal(0.0, 0.015, size=n_closes - 1).tolist()
        ret_b = rng.normal(0.0, 0.02, size=n_closes - 1).tolist()
        rows_a = self._close_rows("AAA", start, n_closes, ret_a)
        rows_b = self._close_rows("BBB", start, n_closes, ret_b)
        snapshot = {
            "currency": "CNY",
            "accounts": [
                {
                    "positions": [
                        {"symbol": "AAA", "market_value_base": 6000.0},
                        {"symbol": "BBB", "market_value_base": 4000.0},
                    ]
                }
            ],
        }
        service = self._service_with(
            snapshot=snapshot,
            closes_by_symbol={"AAA": rows_a, "BBB": rows_b},
        )
        result = service.get_risk_metrics(
            as_of=as_of,
            confidence=0.95,
            horizon_days=1,
            lookback_trading_days=70,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["var"]["status"], "ok")
        self.assertIsNotNone(result["var"]["var_pct"])
        self.assertGreater(result["var"]["var_pct"], 0.0)
        self.assertAlmostEqual(
            result["var"]["var_value"],
            result["var"]["var_pct"] / 100.0 * 10000.0,
            places=4,
        )
        self.assertEqual(result["correlation"]["status"], "ok")
        self.assertEqual(result["correlation"]["symbols"], ["AAA", "BBB"])
        self.assertEqual(len(result["correlation"]["matrix"]), 2)
        self.assertEqual(result["correlation"]["matrix"][0][0], 1.0)
        self.assertEqual(result["concentration"]["position_count"], 2)
        self.assertAlmostEqual(result["concentration"]["top_weight_pct"], 60.0, places=4)

        # Recompute pure known-answer VaR independently.
        _, matrix, symbols = align_simple_returns(
            {
                "AAA": {r.date: r.close for r in rows_a},
                "BBB": {r.date: r.close for r in rows_b},
            },
            lookback_trading_days=70,
        )
        portfolio = build_portfolio_returns(
            matrix,
            symbols,
            {"AAA": 0.6, "BBB": 0.4},
        )
        expected_var_pct = historical_var_pct(portfolio, 0.95) * 100.0
        self.assertAlmostEqual(result["var"]["var_pct"], expected_var_pct, places=6)

        # Hot path must use include_realtime=False.
        service.portfolio_service.get_portfolio_snapshot.assert_called()
        kwargs = service.portfolio_service.get_portfolio_snapshot.call_args.kwargs
        self.assertFalse(kwargs.get("include_realtime", True))
