# -*- coding: utf-8 -*-
"""Deterministic tests for portfolio health score (issue #151)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence
from unittest.mock import MagicMock

from src.repositories.portfolio_health_repo import PortfolioHealthRepository
from src.services.portfolio_health_service import (
    DEFAULT_WEIGHTS,
    PortfolioHealthService,
    aggregate_score,
    apply_llm_polish,
    band_for_score,
    build_rule_insights,
    resolve_weights,
    score_cash_ratio,
    score_concentration,
    score_diversification,
    score_pnl,
    score_risk_exposure,
)
from src.storage import DatabaseManager


class PureFormulaTests(unittest.TestCase):
    def test_concentration_anchors(self) -> None:
        self.assertAlmostEqual(score_concentration(10.0), 100.0, places=4)
        self.assertAlmostEqual(score_concentration(15.0), 100.0, places=4)
        self.assertAlmostEqual(score_concentration(50.0), 0.0, places=4)
        mid = score_concentration(32.5)  # midpoint 15..50
        self.assertAlmostEqual(mid, 50.0, places=4)

    def test_risk_var_anchors(self) -> None:
        self.assertAlmostEqual(score_risk_exposure(0.5), 100.0, places=4)
        self.assertAlmostEqual(score_risk_exposure(1.0), 100.0, places=4)
        self.assertAlmostEqual(score_risk_exposure(8.0), 0.0, places=4)
        self.assertAlmostEqual(score_risk_exposure(4.5), 50.0, places=4)

    def test_diversification_and_pnl_and_cash(self) -> None:
        self.assertAlmostEqual(score_diversification(1.0), 100.0, places=4)
        self.assertAlmostEqual(score_diversification(0.0), 0.0, places=4)
        self.assertAlmostEqual(score_pnl(10.0), 100.0, places=4)
        self.assertAlmostEqual(score_pnl(0.0), 70.0, places=4)
        self.assertAlmostEqual(score_pnl(-30.0), 0.0, places=4)
        self.assertAlmostEqual(score_cash_ratio(10.0), 100.0, places=4)
        self.assertAlmostEqual(score_cash_ratio(0.0), 0.0, places=4)
        self.assertAlmostEqual(score_cash_ratio(80.0), 0.0, places=4)

    def test_aggregate_reweights_when_dimension_missing(self) -> None:
        scores = {
            "concentration": 80.0,
            "risk_exposure": None,
            "diversification": 100.0,
            "pnl": 70.0,
            "cash_ratio": 100.0,
        }
        overall, unavailable, effective = aggregate_score(scores, DEFAULT_WEIGHTS)
        self.assertEqual(unavailable, ["risk_exposure"])
        self.assertNotIn("risk_exposure", effective)
        self.assertAlmostEqual(sum(effective.values()), 1.0, places=8)
        # Manual: remaining weights 0.25+0.20+0.15+0.15 = 0.75
        expected = (
            80.0 * (0.25 / 0.75)
            + 100.0 * (0.20 / 0.75)
            + 70.0 * (0.15 / 0.75)
            + 100.0 * (0.15 / 0.75)
        )
        self.assertAlmostEqual(overall or 0.0, expected, places=4)

    def test_band_for_score(self) -> None:
        self.assertEqual(band_for_score(95.0), "healthy")
        self.assertEqual(band_for_score(70.0), "fair")
        self.assertEqual(band_for_score(50.0), "caution")
        self.assertEqual(band_for_score(10.0), "poor")
        self.assertIsNone(band_for_score(None))

    def test_weights_sum_to_one(self) -> None:
        weights = resolve_weights()
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=9)

    def test_known_answer_full_score(self) -> None:
        """Third-party recomputation: equal-ish healthy portfolio."""
        dim = {
            "concentration": score_concentration(20.0),  # ~85.71
            "risk_exposure": score_risk_exposure(2.0),  # ~85.71
            "diversification": score_diversification(0.9),  # 90
            "pnl": score_pnl(5.0),  # 85
            "cash_ratio": score_cash_ratio(15.0),  # 100
        }
        overall, unavailable, _ = aggregate_score(dim, DEFAULT_WEIGHTS)
        self.assertEqual(unavailable, [])
        expected = (
            dim["concentration"] * 0.25
            + dim["risk_exposure"] * 0.25
            + dim["diversification"] * 0.20
            + dim["pnl"] * 0.15
            + dim["cash_ratio"] * 0.15
        )
        self.assertAlmostEqual(overall or 0.0, expected, places=4)
        self.assertEqual(band_for_score(overall), "healthy")


class InsightAndLlmContractTests(unittest.TestCase):
    def test_rule_insight_names_symbol_and_threshold(self) -> None:
        insights = build_rule_insights(
            concentration={
                "top_weight_pct": 42.0,
                "weights": [{"symbol": "AAA", "weight_pct": 42.0}],
            },
            risk_var_pct=1.0,
            diversification_score=0.8,
            cash_pct=10.0,
            unrealized_pnl_pct=2.0,
            concentration_alert_pct=35.0,
            cash_low_alert_pct=2.0,
            cash_high_alert_pct=50.0,
            var_alert_pct=5.0,
            diversification_alert=0.35,
            pnl_loss_alert_pct=-15.0,
        )
        conc = [i for i in insights if i["code"] == "concentration_top_name"]
        self.assertEqual(len(conc), 1)
        self.assertEqual(conc[0]["symbol"], "AAA")
        self.assertAlmostEqual(float(conc[0]["value"]), 42.0)
        self.assertAlmostEqual(float(conc[0]["threshold"]), 35.0)
        self.assertIn("42.0%", conc[0]["message"])
        self.assertIn("35.0%", conc[0]["message"])

    def test_llm_polish_cannot_change_metrics_or_inject_score(self) -> None:
        rules = [
            {
                "code": "concentration_top_name",
                "severity": "warning",
                "message": "Position AAA weight 42.0% exceeds concentration threshold 35.0%.",
                "symbol": "AAA",
                "metric": "top_weight_pct",
                "value": 42.0,
                "threshold": 35.0,
                "source": "rule",
            }
        ]
        polished = [
            {
                "code": "concentration_top_name",
                "severity": "info",  # attempt to soften
                "message": "Consider trimming AAA; it is oversized versus policy.",
                "symbol": "HACKED",
                "metric": "score",
                "value": 99.0,
                "threshold": 1.0,
                "source": "llm",
            },
            {
                "code": "fake_new",
                "message": "Injected",
                "value": 100.0,
            },
        ]
        merged = apply_llm_polish(rules, polished)
        self.assertEqual(len(merged), 1)
        row = merged[0]
        self.assertEqual(row["symbol"], "AAA")
        self.assertEqual(row["metric"], "top_weight_pct")
        self.assertAlmostEqual(float(row["value"]), 42.0)
        self.assertAlmostEqual(float(row["threshold"]), 35.0)
        self.assertEqual(row["severity"], "warning")
        self.assertIn("Consider trimming AAA", row["message"])
        self.assertEqual(row["source"], "rule+llm_polish")


class PortfolioHealthServiceTests(unittest.TestCase):
    def _service(
        self,
        *,
        snapshot: dict,
        risk: dict,
        llm_polisher=None,
        health_repo=None,
    ) -> PortfolioHealthService:
        portfolio_service = MagicMock()
        portfolio_service.get_portfolio_snapshot.return_value = snapshot
        risk_service = MagicMock()
        risk_service.get_risk_metrics.return_value = risk
        return PortfolioHealthService(
            portfolio_service=portfolio_service,
            risk_metrics_service=risk_service,
            health_repo=health_repo or MagicMock(),
            llm_polisher=llm_polisher,
        )

    @staticmethod
    def _ok_risk(*, top: float = 20.0, var_pct: float = 2.0, div: float = 0.9) -> dict:
        return {
            "status": "ok",
            "currency": "CNY",
            "concentration": {
                "status": "ok",
                "top_weight_pct": top,
                "diversification_score": div,
                "position_count": 3,
                "weights": [
                    {"symbol": "AAA", "weight_pct": top},
                    {"symbol": "BBB", "weight_pct": 100.0 - top - 10.0},
                    {"symbol": "CCC", "weight_pct": 10.0},
                ],
            },
            "var": {
                "status": "ok",
                "var_pct": var_pct,
                "status_message": "ok",
            },
        }

    @staticmethod
    def _ok_snapshot(
        *,
        equity: float = 100_000.0,
        cash: float = 10_000.0,
        mv: float = 90_000.0,
        unrealized: float = 5_000.0,
        fx_stale: bool = False,
        price_stale_symbol: str | None = None,
    ) -> dict:
        positions = [
            {
                "symbol": "AAA",
                "market_value_base": 40_000.0,
                "quantity": 100,
                "price_stale": price_stale_symbol == "AAA",
            },
            {
                "symbol": "BBB",
                "market_value_base": 40_000.0,
                "quantity": 50,
                "price_stale": price_stale_symbol == "BBB",
            },
            {
                "symbol": "CCC",
                "market_value_base": 10_000.0,
                "quantity": 20,
                "price_stale": price_stale_symbol == "CCC",
            },
        ]
        return {
            "currency": "CNY",
            "total_equity": equity,
            "total_cash": cash,
            "total_market_value": mv,
            "unrealized_pnl": unrealized,
            "fx_stale": fx_stale,
            "data_quality": "partial" if (fx_stale or price_stale_symbol) else "ok",
            "limitations": [],
            "accounts": [{"positions": positions}],
        }

    def test_empty_portfolio(self) -> None:
        service = self._service(
            snapshot={
                "currency": "CNY",
                "total_equity": 0.0,
                "total_cash": 0.0,
                "total_market_value": 0.0,
                "unrealized_pnl": 0.0,
                "fx_stale": False,
                "data_quality": "ok",
                "limitations": [],
                "accounts": [],
            },
            risk={
                "status": "empty_portfolio",
                "currency": "CNY",
                "concentration": {"status": "empty_portfolio", "position_count": 0},
                "var": {"status": "unavailable", "var_pct": None},
            },
        )
        result = service.get_health(as_of=date(2026, 1, 15), persist=False)
        self.assertEqual(result["status"], "empty_portfolio")
        self.assertIsNone(result["score"])
        self.assertEqual(result["score_source"], "rules")
        self.assertFalse(result["llm_can_modify_score"])

    def test_full_score_and_persist_idempotent(self) -> None:
        import os

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        db_path = Path(temp.name) / "health.db"
        prev_db = os.environ.get("DATABASE_PATH")
        os.environ["DATABASE_PATH"] = str(db_path)
        DatabaseManager.reset_instance()
        try:
            db = DatabaseManager.get_instance()
            repo = PortfolioHealthRepository(db_manager=db)

            service = self._service(
                snapshot=self._ok_snapshot(),
                risk=self._ok_risk(top=20.0, var_pct=2.0, div=0.9),
                health_repo=repo,
            )
            as_of = date(2026, 6, 1)
            first = service.get_health(account_id=1, as_of=as_of, persist=True)
            self.assertEqual(first["status"], "ok")
            self.assertIsNotNone(first["score"])
            self.assertTrue(0.0 <= float(first["score"]) <= 100.0)
            self.assertEqual(first["score_source"], "rules")
            self.assertFalse(first["llm_can_modify_score"])
            self.assertTrue(first["persisted"])

            # Recompute overwrites, does not append
            second = service.get_health(account_id=1, as_of=as_of, persist=True)
            self.assertAlmostEqual(float(second["score"]), float(first["score"]), places=4)
            stored = repo.get_snapshot(account_id=1, snapshot_date=as_of, cost_method="fifo")
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertAlmostEqual(float(stored["score"]), float(first["score"]), places=4)

            # Count rows == 1
            from sqlalchemy import text

            with db.get_session() as session:
                count = session.execute(
                    text("SELECT COUNT(*) FROM portfolio_health_snapshots")
                ).scalar()
            self.assertEqual(int(count or 0), 1)
        finally:
            DatabaseManager.reset_instance()
            if prev_db is None:
                os.environ.pop("DATABASE_PATH", None)
            else:
                os.environ["DATABASE_PATH"] = prev_db

    def test_partial_when_var_unavailable(self) -> None:
        risk = self._ok_risk()
        risk["status"] = "insufficient_history"
        risk["var"] = {
            "status": "insufficient_history",
            "var_pct": None,
            "status_message": "Need at least 60 observations",
        }
        service = self._service(snapshot=self._ok_snapshot(), risk=risk)
        result = service.get_health(as_of=date(2026, 3, 1), persist=False)
        self.assertEqual(result["status"], "partial")
        self.assertIn("risk_exposure", result["unavailable_dimensions"])
        self.assertIsNotNone(result["score"])
        self.assertEqual(
            result["dimensions"]["risk_exposure"]["status"], "unavailable"
        )
        # Score must not pretend VaR was 0
        self.assertIsNone(result["dimensions"]["risk_exposure"]["score"])
        self.assertIsNone(result["inputs"]["var_pct"])

    def test_partial_when_price_stale(self) -> None:
        service = self._service(
            snapshot=self._ok_snapshot(price_stale_symbol="AAA"),
            risk=self._ok_risk(),
        )
        result = service.get_health(as_of=date(2026, 3, 1), persist=False)
        self.assertEqual(result["status"], "partial")
        self.assertIn("AAA", result["data_quality"]["missing_price_symbols"])
        self.assertIn("pnl", result["unavailable_dimensions"])

    def test_llm_cannot_modify_score(self) -> None:
        """Even a malicious polisher cannot change the locked score."""

        def evil_polisher(
            insights: Sequence[Mapping[str, Any]],
        ) -> List[Dict[str, Any]]:
            return [
                {
                    **dict(insights[0]),
                    "message": "rewritten",
                    "value": 999.0,
                }
            ]

        service = self._service(
            snapshot=self._ok_snapshot(),
            risk=self._ok_risk(top=42.0),
            llm_polisher=evil_polisher,
        )
        # Capture pure rule score without LLM path for comparison
        pure = PortfolioHealthService(
            portfolio_service=service.portfolio_service,
            risk_metrics_service=service.risk_metrics_service,
            health_repo=MagicMock(),
            llm_polisher=None,
        ).get_health(as_of=date(2026, 4, 1), persist=False)

        with_llm = service.get_health(as_of=date(2026, 4, 1), persist=False)
        self.assertEqual(with_llm["score_source"], "rules")
        self.assertFalse(with_llm["llm_can_modify_score"])
        self.assertAlmostEqual(float(with_llm["score"]), float(pure["score"]), places=6)
        # Dimensions identical
        for key in pure["dimensions"]:
            self.assertEqual(
                pure["dimensions"][key].get("score"),
                with_llm["dimensions"][key].get("score"),
            )
        # Insight metrics unchanged
        for rule, polished in zip(pure["insights"], with_llm["insights"]):
            self.assertEqual(rule.get("value"), polished.get("value"))
            self.assertEqual(rule.get("threshold"), polished.get("threshold"))
            self.assertEqual(rule.get("symbol"), polished.get("symbol"))


if __name__ == "__main__":
    unittest.main()
