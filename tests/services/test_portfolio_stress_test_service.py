# -*- coding: utf-8 -*-
"""Deterministic known-answer tests for portfolio stress testing (issue #158)."""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path
from typing import Any, Dict
from unittest import TestCase
from unittest.mock import MagicMock

from src.services.portfolio_stress_scenarios import (
    DEFAULT_EQUITY_RATE_SENSITIVITY_PCT_PER_100BP,
    get_scenario,
    load_scenarios,
)
from src.services.portfolio_stress_test_service import PortfolioStressTestService


class ScenarioCatalogTests(TestCase):
    def test_builtin_scenarios_include_required_presets(self) -> None:
        ids = {item["id"] for item in load_scenarios(scenarios_path="")}
        self.assertIn("market_down_10", ids)
        self.assertIn("market_down_20", ids)
        self.assertIn("sector_down_30", ids)
        self.assertIn("fx_up_5", ids)
        self.assertIn("fx_down_5", ids)
        self.assertIn("rate_up_100bp", ids)

    def test_yaml_override_merges_by_id(self) -> None:
        yaml_text = textwrap.dedent(
            """
            scenarios:
              - id: market_down_10
                name: Overridden market -10
                description: custom override
                category: market
                shocks:
                  - factor: market
                    value_pct: -10.0
              - id: custom_oil_shock
                name: Oil -25
                description: custom
                category: custom
                shocks:
                  - factor: market
                    value_pct: -25.0
            """
        ).strip()
        path = Path(self._tmp_yaml(yaml_text))
        scenarios = load_scenarios(scenarios_path=str(path))
        by_id = {item["id"]: item for item in scenarios}
        self.assertEqual(by_id["market_down_10"]["name"], "Overridden market -10")
        self.assertIn("custom_oil_shock", by_id)
        self.assertIn("market_down_20", by_id)  # builtins retained

    def _tmp_yaml(self, text: str) -> str:
        import tempfile

        handle = tempfile.NamedTemporaryFile(
            "w",
            suffix=".yaml",
            delete=False,
            encoding="utf-8",
        )
        handle.write(text)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name


class PortfolioStressTestServiceTests(TestCase):
    def _service(self, snapshot: Dict[str, Any]) -> PortfolioStressTestService:
        portfolio_service = MagicMock()
        portfolio_service.get_portfolio_snapshot.return_value = snapshot
        return PortfolioStressTestService(portfolio_service=portfolio_service)

    @staticmethod
    def _two_name_snapshot(
        *,
        aaa_mv: float = 6000.0,
        bbb_mv: float = 4000.0,
        aaa_ccy: str = "CNY",
        bbb_ccy: str = "CNY",
        aaa_sector: str | None = None,
        bbb_sector: str | None = None,
    ) -> Dict[str, Any]:
        return {
            "currency": "CNY",
            "accounts": [
                {
                    "base_currency": "CNY",
                    "positions": [
                        {
                            "symbol": "AAA",
                            "market_value_base": aaa_mv,
                            "valuation_currency": aaa_ccy,
                            "sector": aaa_sector,
                        },
                        {
                            "symbol": "BBB",
                            "market_value_base": bbb_mv,
                            "valuation_currency": bbb_ccy,
                            "sector": bbb_sector,
                        },
                    ],
                }
            ],
        }

    def test_empty_portfolio_status(self) -> None:
        service = self._service({"currency": "CNY", "accounts": []})
        result = service.run_stress_test(
            as_of=date(2026, 1, 15),
            scenario_id="market_down_10",
        )
        self.assertEqual(result["status"], "empty_portfolio")
        self.assertIsNone(result["portfolio_pnl"])
        self.assertEqual(result["missing_data"], ["positions"])
        self.assertEqual(result["simulation_method"], "deterministic_factor_shock")
        self.assertFalse(result["historical_replay_available"])
        service.portfolio_service.get_portfolio_snapshot.assert_called()
        kwargs = service.portfolio_service.get_portfolio_snapshot.call_args.kwargs
        self.assertFalse(kwargs.get("include_realtime", True))

    def test_market_shock_unit_beta_is_partial_and_known_answer(self) -> None:
        service = self._service(self._two_name_snapshot())
        result = service.run_stress_test(
            as_of=date(2026, 6, 1),
            scenario_id="market_down_10",
        )
        # With unit beta: both names -10% → portfolio -10% of 10000 = -1000
        self.assertEqual(result["status"], "partial")
        self.assertIn("beta", result["missing_data"])
        self.assertIn("unit_beta_default", result["assumptions"]["simplified_assumptions"])
        self.assertAlmostEqual(result["portfolio_pnl"], -1000.0, places=6)
        self.assertAlmostEqual(result["portfolio_pnl_pct"], -10.0, places=6)
        self.assertAlmostEqual(result["stressed_portfolio_value"], 9000.0, places=6)
        self.assertEqual(result["positions_used"], 2)
        self.assertEqual(result["concentration"]["status"], "ok")
        self.assertAlmostEqual(result["concentration"]["top_weight_pct"], 60.0, places=4)

    def test_market_shock_with_provided_betas_is_ok(self) -> None:
        service = self._service(self._two_name_snapshot())
        result = service.run_stress_test(
            as_of=date(2026, 6, 1),
            scenario_id="market_down_10",
            betas={"AAA": 1.5, "BBB": 0.5},
        )
        # AAA: 6000 * 1.5 * -10% = -900; BBB: 4000 * 0.5 * -10% = -200; total -1100
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["missing_data"], [])
        self.assertAlmostEqual(result["portfolio_pnl"], -1100.0, places=6)
        self.assertAlmostEqual(result["portfolio_pnl_pct"], -11.0, places=6)
        by_symbol = {row["symbol"]: row for row in result["position_impacts"]}
        self.assertEqual(by_symbol["AAA"]["beta_source"], "provided")
        self.assertAlmostEqual(by_symbol["AAA"]["beta_used"], 1.5, places=6)
        self.assertAlmostEqual(by_symbol["AAA"]["pnl"], -900.0, places=6)
        self.assertAlmostEqual(by_symbol["BBB"]["pnl"], -200.0, places=6)
        # Top loser should be AAA
        self.assertEqual(result["top_losers"][0]["symbol"], "AAA")

    def test_sector_shock_missing_classification_is_partial_not_fabricated(self) -> None:
        service = self._service(self._two_name_snapshot())
        result = service.run_stress_test(
            as_of=date(2026, 6, 1),
            scenario_id="sector_down_30",
            target_sector="banks",
        )
        self.assertEqual(result["status"], "partial")
        self.assertIn("sector", result["missing_data"])
        # No classification → sector factor does not invent a hit; PnL stays 0.
        self.assertAlmostEqual(result["portfolio_pnl"], 0.0, places=6)
        self.assertIsNotNone(result["status_message"])
        self.assertIn("sector", (result["status_message"] or "").lower())

    def test_sector_shock_applies_only_to_matching_names(self) -> None:
        service = self._service(
            self._two_name_snapshot(aaa_sector="Banks", bbb_sector="Tech")
        )
        result = service.run_stress_test(
            as_of=date(2026, 6, 1),
            scenario_id="sector_down_30",
            target_sector="Banks",
            sector_map={"AAA": "Banks", "BBB": "Tech"},
        )
        self.assertEqual(result["status"], "ok")
        # Only AAA hit by -30%: 6000 * -0.3 = -1800
        self.assertAlmostEqual(result["portfolio_pnl"], -1800.0, places=6)
        by_symbol = {row["symbol"]: row for row in result["position_impacts"]}
        self.assertAlmostEqual(by_symbol["AAA"]["shock_pct"], -30.0, places=6)
        self.assertAlmostEqual(by_symbol["BBB"]["shock_pct"], 0.0, places=6)

    def test_sector_scenario_requires_target_sector(self) -> None:
        service = self._service(self._two_name_snapshot())
        with self.assertRaises(ValueError) as ctx:
            service.run_stress_test(scenario_id="sector_down_30")
        self.assertIn("target_sector", str(ctx.exception))

    def test_fx_shock_only_foreign_currency_positions(self) -> None:
        service = self._service(
            self._two_name_snapshot(aaa_ccy="CNY", bbb_ccy="USD")
        )
        result = service.run_stress_test(
            as_of=date(2026, 6, 1),
            scenario_id="fx_down_5",
            betas={"AAA": 1.0, "BBB": 1.0},  # irrelevant for FX
        )
        # Only BBB (-5% of 4000) = -200
        self.assertEqual(result["status"], "ok")
        self.assertAlmostEqual(result["portfolio_pnl"], -200.0, places=6)
        by_symbol = {row["symbol"]: row for row in result["position_impacts"]}
        self.assertAlmostEqual(by_symbol["AAA"]["shock_pct"], 0.0, places=6)
        self.assertAlmostEqual(by_symbol["BBB"]["shock_pct"], -5.0, places=6)

    def test_rate_shock_uses_documented_sensitivity(self) -> None:
        service = self._service(self._two_name_snapshot())
        result = service.run_stress_test(
            as_of=date(2026, 6, 1),
            scenario_id="rate_up_100bp",
            rate_sensitivity_pct_per_100bp=DEFAULT_EQUITY_RATE_SENSITIVITY_PCT_PER_100BP,
        )
        # +100bp * -2.0 pct/100bp = -2% on full book → -200
        self.assertIn(
            "uniform_equity_rate_sensitivity",
            result["assumptions"]["simplified_assumptions"],
        )
        self.assertAlmostEqual(result["portfolio_pnl"], -200.0, places=6)
        self.assertAlmostEqual(result["portfolio_pnl_pct"], -2.0, places=6)
        self.assertFalse(result["assumptions"]["historical_replay"])
        self.assertTrue(result["assumptions"]["provider_calls_on_hot_path"] is False)

    def test_custom_shocks_path(self) -> None:
        service = self._service(self._two_name_snapshot())
        result = service.run_stress_test(
            as_of=date(2026, 6, 1),
            custom_shocks=[{"factor": "market", "value_pct": -5.0}],
            betas={"AAA": 1.0, "BBB": 1.0},
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["scenario"]["id"], "custom")
        self.assertAlmostEqual(result["portfolio_pnl"], -500.0, places=6)

    def test_unknown_scenario_raises(self) -> None:
        service = self._service(self._two_name_snapshot())
        with self.assertRaises(ValueError):
            service.run_stress_test(scenario_id="not_a_real_scenario")

    def test_get_scenario_market_down_20_shape(self) -> None:
        scenario = get_scenario("market_down_20", scenarios_path="")
        self.assertEqual(scenario["shocks"][0]["value_pct"], -20.0)
