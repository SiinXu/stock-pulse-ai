# -*- coding: utf-8 -*-
"""Portfolio-level multi-symbol analysis tests (issue #128)."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Dict, List, Optional
from unittest import TestCase
from unittest.mock import MagicMock

import numpy as np

from src.services.portfolio_health_service import PortfolioHealthService
from src.services.portfolio_level_analysis_service import (
    MAX_SYMBOLS,
    PortfolioLevelAnalysisService,
)
from src.services.portfolio_risk_metrics_service import (
    MIN_RETURN_OBSERVATIONS,
    PortfolioRiskMetricsService,
)
from src.services.portfolio_stress_test_service import PortfolioStressTestService


class PortfolioLevelAnalysisServiceTests(TestCase):
    @staticmethod
    def _close_rows(
        symbol: str,
        start: date,
        count: int,
        returns: List[float],
    ) -> List[SimpleNamespace]:
        assert len(returns) == count - 1
        price = 100.0
        rows = [SimpleNamespace(date=start, close=price, code=symbol)]
        for i, ret in enumerate(returns, start=1):
            price = price * (1.0 + ret)
            rows.append(
                SimpleNamespace(date=start + timedelta(days=i), close=price, code=symbol)
            )
        return rows

    def _build_service(
        self,
        *,
        closes_by_symbol: Dict[str, List[SimpleNamespace]],
        stance_items: Optional[List[dict]] = None,
        include_real_stress: bool = True,
    ) -> PortfolioLevelAnalysisService:
        stock_repo = MagicMock()

        def _get_range(code: str, start: date, end: date):
            return closes_by_symbol.get(code, [])

        stock_repo.get_range.side_effect = _get_range

        risk = PortfolioRiskMetricsService(
            portfolio_service=MagicMock(),
            stock_repo=stock_repo,
        )
        health = PortfolioHealthService(
            portfolio_service=MagicMock(),
            risk_metrics_service=risk,
            health_repo=MagicMock(),
        )

        if include_real_stress:
            portfolio = MagicMock()

            def convert(*, amount: float, from_currency: str, to_currency: str, as_of_date: date):
                return {
                    "converted_amount": amount,
                    "rate": 1.0,
                    "is_stale": False,
                    "method": "identity",
                    "source": "identity",
                    "rate_date": None,
                }

            portfolio.convert_amount_with_provenance.side_effect = convert
            stress = PortfolioStressTestService(
                portfolio_service=portfolio,
                scenarios_path="",
            )
        else:
            stress = MagicMock()
            stress.run_stress_test.side_effect = RuntimeError("stress boom")

        watchlist = MagicMock()
        watchlist.score_symbols.return_value = {
            "formula_version": "watchlist_score_v1",
            "items": stance_items
            or [
                {
                    "stock_code": "AAA",
                    "status": "scored",
                    "score": 70,
                    "operation_advice": "buy",
                    "freshness": "recent",
                },
                {
                    "stock_code": "BBB",
                    "status": "scored",
                    "score": 40,
                    "operation_advice": "hold",
                    "freshness": "recent",
                },
            ],
        }

        return PortfolioLevelAnalysisService(
            stock_repo=stock_repo,
            risk_metrics_service=risk,
            health_service=health,
            stress_service=stress,
            watchlist_score_service=watchlist,
        )

    def test_rejects_over_limit_with_clear_message(self) -> None:
        service = self._build_service(closes_by_symbol={})
        codes = [f"S{i:02d}" for i in range(MAX_SYMBOLS + 1)]
        with self.assertRaises(ValueError) as caught:
            service.analyze(codes)
        message = str(caught.exception)
        self.assertIn(str(MAX_SYMBOLS), message)
        self.assertIn("limit", message.lower())

    def test_partial_degradation_when_one_symbol_missing_price(self) -> None:
        as_of = date(2026, 6, 1)
        n_closes = MIN_RETURN_OBSERVATIONS + 10
        start = as_of - timedelta(days=n_closes - 1)
        rng = np.random.default_rng(11)
        returns_a = rng.normal(0.0, 0.01, size=n_closes - 1).tolist()
        returns_b = rng.normal(0.0, 0.012, size=n_closes - 1).tolist()
        rows_a = self._close_rows("AAA", start, n_closes, returns_a)
        rows_b = self._close_rows("BBB", start, n_closes, returns_b)
        # CCC intentionally has no close history.
        service = self._build_service(
            closes_by_symbol={"AAA": rows_a, "BBB": rows_b},
            stance_items=[
                {
                    "stock_code": "AAA",
                    "status": "scored",
                    "score": 80,
                    "operation_advice": "buy",
                    "freshness": "today",
                },
                {
                    "stock_code": "BBB",
                    "status": "unanalyzed",
                    "score": None,
                    "operation_advice": None,
                    "freshness": "none",
                },
                {
                    "stock_code": "CCC",
                    "status": "unanalyzed",
                    "score": None,
                    "operation_advice": None,
                    "freshness": "none",
                },
            ],
        )

        result = service.analyze(
            ["AAA", "BBB", "CCC"],
            as_of=as_of,
            include_stress=True,
            scenario_id="market_down_10",
        )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["symbols_used"], ["AAA", "BBB"])
        self.assertEqual(len(result["degraded_symbols"]), 1)
        self.assertEqual(result["degraded_symbols"][0]["stock_code"], "CCC")
        self.assertEqual(result["degraded_symbols"][0]["reason"], "price_unavailable")
        self.assertEqual(result["concentration"]["position_count"], 2)
        # Equal-weight over usable names only.
        self.assertAlmostEqual(result["weights"][0]["weight_pct"], 50.0, places=4)
        self.assertAlmostEqual(result["weights"][1]["weight_pct"], 50.0, places=4)
        self.assertIn(result["correlation"]["status"], {"ok", "insufficient_history", "partial"})
        self.assertEqual(result["stance_distribution"]["status"], "partial")
        self.assertIsNotNone(result["health"])
        self.assertIsNotNone(result["stress"])
        # Whole request succeeded despite CCC missing data.
        self.assertNotEqual(result["status"], "unavailable")

    def test_all_missing_prices_returns_unavailable_not_exception(self) -> None:
        service = self._build_service(closes_by_symbol={})
        result = service.analyze(["AAA", "BBB"], as_of=date(2026, 1, 1), include_stress=False)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["symbols_used_count"], 0)
        self.assertEqual(len(result["degraded_symbols"]), 2)
        self.assertEqual(result["correlation"]["status"], "unavailable")

    def test_equal_weight_full_basket_has_portfolio_blocks(self) -> None:
        as_of = date(2026, 6, 1)
        n_closes = MIN_RETURN_OBSERVATIONS + 15
        start = as_of - timedelta(days=n_closes - 1)
        # Highly correlated series for highlight detection.
        base = [0.01 if i % 2 == 0 else -0.01 for i in range(n_closes - 1)]
        rows_a = self._close_rows("AAA", start, n_closes, base)
        rows_b = self._close_rows("BBB", start, n_closes, [x * 1.1 for x in base])
        service = self._build_service(
            closes_by_symbol={"AAA": rows_a, "BBB": rows_b},
        )
        result = service.analyze(
            ["AAA", "BBB"],
            as_of=as_of,
            include_stress=True,
            high_correlation_threshold=0.5,
            sector_map={"AAA": "Consumer", "BBB": "Consumer"},
        )
        self.assertIn(result["status"], {"ok", "partial"})
        self.assertEqual(result["symbols_used_count"], 2)
        self.assertEqual(result["weighting_mode"], "equal_weight")
        self.assertEqual(result["concentration"]["status"], "ok")
        self.assertAlmostEqual(result["concentration"]["top_weight_pct"], 50.0, places=4)
        if result["correlation"]["status"] == "ok":
            self.assertTrue(
                result["correlation_highlights"] or result["shared_risk_exposures"]
            )
        kinds = {item["kind"] for item in result["shared_risk_exposures"]}
        self.assertTrue(
            "sector_concentration" in kinds
            or "high_correlation_cluster" in kinds
            or "name_concentration" in kinds
            or result["correlation"]["status"] != "ok"
        )
        self.assertEqual(result["stress"]["status"] in {"ok", "partial", "unavailable"}, True)

    def test_custom_weights_rebase_after_degradation(self) -> None:
        as_of = date(2026, 6, 1)
        n_closes = MIN_RETURN_OBSERVATIONS + 5
        start = as_of - timedelta(days=n_closes - 1)
        returns = [0.001] * (n_closes - 1)
        service = self._build_service(
            closes_by_symbol={
                "AAA": self._close_rows("AAA", start, n_closes, returns),
                "BBB": self._close_rows("BBB", start, n_closes, returns),
            }
        )
        result = service.analyze(
            ["AAA", "BBB", "CCC"],
            weights={"AAA": 1.0, "BBB": 3.0, "CCC": 6.0},
            as_of=as_of,
            include_stress=False,
        )
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["weighting_mode"], "custom_weight")
        by_symbol = {row["symbol"]: row["weight_pct"] for row in result["weights"]}
        self.assertAlmostEqual(by_symbol["AAA"], 25.0, places=4)
        self.assertAlmostEqual(by_symbol["BBB"], 75.0, places=4)
        self.assertNotIn("CCC", by_symbol)

    def test_stress_failure_does_not_fail_whole_analysis(self) -> None:
        as_of = date(2026, 6, 1)
        n_closes = MIN_RETURN_OBSERVATIONS + 5
        start = as_of - timedelta(days=n_closes - 1)
        returns = [0.0] * (n_closes - 1)
        service = self._build_service(
            closes_by_symbol={
                "AAA": self._close_rows("AAA", start, n_closes, returns),
                "BBB": self._close_rows("BBB", start, n_closes, returns),
            },
            include_real_stress=False,
        )
        result = service.analyze(["AAA", "BBB"], as_of=as_of, include_stress=True)
        self.assertIn(result["status"], {"ok", "partial"})
        self.assertEqual(result["stress"]["status"], "unavailable")
        self.assertTrue(any("Stress overlay unavailable" in a for a in result["annotations"]))
