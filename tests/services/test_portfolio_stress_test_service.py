# -*- coding: utf-8 -*-
"""Known-answer and boundary tests for portfolio stress testing."""

from __future__ import annotations

import os
import tempfile
import textwrap
from datetime import date
from pathlib import Path
from typing import Any, Dict
from unittest import TestCase
from unittest.mock import MagicMock

from src.config import Config
from src.services.portfolio_service import PortfolioService
from src.services.portfolio_stress_scenarios import (
    MAX_CATALOG_BYTES,
    ScenarioCatalogUnavailableError,
    active_scenarios,
    activate_scenario_catalog,
    get_scenario,
    load_scenarios,
)
from src.services.portfolio_stress_test_service import PortfolioStressTestService


class ScenarioCatalogTests(TestCase):
    def _tmp_yaml(self, text: str) -> Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        path = Path(handle.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_builtin_catalog_discloses_parameterized_sector_template(self) -> None:
        scenarios = load_scenarios(scenarios_path="")
        by_id = {item["id"]: item for item in scenarios}
        self.assertEqual(by_id["sector_down_30"]["availability"], "requires_parameters")
        self.assertEqual(len(by_id["market_down_10"]["scenario_hash"]), 64)

    def test_yaml_override_merges_and_last_known_good_survives_invalid_reload(self) -> None:
        path = self._tmp_yaml(
            textwrap.dedent(
                """
                scenarios:
                  - id: custom_oil_shock
                    name: Oil -25
                    category: custom
                    shocks:
                      - factor: market
                        value_pct: -25
                """
            )
        )
        first = load_scenarios(scenarios_path=str(path))
        self.assertIn("custom_oil_shock", {item["id"] for item in first})
        path.write_text("scenarios: [not: valid: yaml", encoding="utf-8")
        os.utime(path, None)
        second = load_scenarios(scenarios_path=str(path))
        self.assertEqual(first, second)

    def test_atomic_activation_keeps_previous_catalog_for_invalid_reload(self) -> None:
        valid_path = self._tmp_yaml(
            "scenarios:\n  - id: active_custom\n    shocks:\n      - factor: market\n        value_pct: -7\n"
        )
        first = activate_scenario_catalog(scenarios_path=str(valid_path))
        valid_path.write_text("scenarios: [not: valid: yaml", encoding="utf-8")
        os.utime(valid_path, None)
        retained = activate_scenario_catalog(scenarios_path=str(valid_path))
        self.assertEqual(retained, first)
        self.assertEqual(
            active_scenarios(scenarios_path=str(valid_path)), first
        )

    def test_config_construction_warms_catalog_and_reload_is_last_known_good(self) -> None:
        path = self._tmp_yaml(
            "scenarios:\n  - id: config_warmed\n    shocks:\n      - factor: market\n        value_pct: -6\n"
        )
        Config(portfolio_stress_scenarios_path=str(path))
        first = active_scenarios(scenarios_path=str(path))
        self.assertIn("config_warmed", {item["id"] for item in first})

        path.write_text("scenarios: [not: valid: yaml", encoding="utf-8")
        os.utime(path, None)
        Config(portfolio_stress_scenarios_path=str(path))
        self.assertEqual(active_scenarios(scenarios_path=str(path)), first)

    def test_catalog_limits_and_public_error_do_not_expose_path(self) -> None:
        path = self._tmp_yaml("x" * (MAX_CATALOG_BYTES + 1))
        with self.assertRaises(ScenarioCatalogUnavailableError) as caught:
            load_scenarios(scenarios_path=str(path))
        self.assertEqual(str(caught.exception), "Configured scenario catalog is unavailable")
        self.assertNotIn(str(path), str(caught.exception))

    def test_shock_shape_is_strict_and_bounded(self) -> None:
        path = self._tmp_yaml(
            "scenarios:\n  - id: invalid\n    shocks:\n      - factor: rate\n        value_pct: 10\n"
        )
        with self.assertRaises(ScenarioCatalogUnavailableError):
            load_scenarios(scenarios_path=str(path))

    def test_get_scenario_market_down_20_shape(self) -> None:
        scenario = get_scenario("market_down_20", scenarios_path="")
        self.assertEqual(scenario["shocks"][0]["value_pct"], -20.0)


class PortfolioStressTestServiceTests(TestCase):
    @staticmethod
    def _position(
        symbol: str,
        market_value: float,
        *,
        currency: str = "CNY",
        available: bool = True,
        stale: bool = False,
    ) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "market": "US" if currency == "USD" else "CN",
            "currency": currency,
            "quantity": 10,
            "market_value_base": market_value,
            "valuation_currency": "CNY",
            "price_source": "daily_close",
            "price_provider": "test_provider",
            "price_date": "2026-06-01",
            "price_stale": stale,
            "price_available": available,
            "data_quality": "ok",
            "limitations": [],
        }

    @classmethod
    def _snapshot(cls, *, stale: bool = False) -> Dict[str, Any]:
        return {
            "as_of": "2026-06-01",
            "cost_method": "fifo",
            "currency": "CNY",
            "total_market_value": 10000.0,
            "fx_stale": stale,
            "data_quality": "partial" if stale else "ok",
            "limitations": ["stale test data"] if stale else [],
            "accounts": [
                {
                    "account_id": 1,
                    "base_currency": "CNY",
                    "positions": [cls._position("AAA", 6000), cls._position("BBB", 4000)],
                }
            ],
        }

    def _service(self, snapshot: Dict[str, Any]) -> PortfolioStressTestService:
        portfolio = MagicMock()
        portfolio.preview_portfolio_snapshot.return_value = snapshot

        def convert(*, amount: float, from_currency: str, to_currency: str, as_of_date: date):
            rate = 7.2 if (from_currency, to_currency) == ("USD", "CNY") else 1.0
            method = "direct_rate" if rate != 1.0 else "identity"
            return {
                "converted_amount": amount * rate,
                "rate": rate,
                "is_stale": False,
                "method": method,
                "source": "test_fx_feed" if rate != 1.0 else "identity",
                "rate_date": date(2026, 5, 30) if rate != 1.0 else None,
            }

        portfolio.convert_amount_with_provenance.side_effect = convert
        return PortfolioStressTestService(portfolio_service=portfolio, scenarios_path="")

    def test_empty_portfolio_uses_read_only_snapshot(self) -> None:
        snapshot = {
            "currency": "CNY",
            "total_market_value": 0,
            "accounts": [],
            "limitations": [],
        }
        service = self._service(snapshot)
        result = service.run_stress_test(as_of=date(2026, 1, 15), scenario_id="market_down_10")
        self.assertEqual(result["status"], "empty_portfolio")
        service.portfolio_service.preview_portfolio_snapshot.assert_called_once_with(
            account_id=None,
            as_of=date(2026, 1, 15),
            cost_method="fifo",
            include_realtime=False,
        )

    def test_market_known_answer_and_provenance(self) -> None:
        result = self._service(self._snapshot()).run_stress_test(
            as_of=date(2026, 6, 1),
            scenario_id="market_down_10",
            betas={"AAA": 1.5, "BBB": 0.5},
        )
        self.assertEqual(result["status"], "ok")
        self.assertAlmostEqual(result["portfolio_pnl"], -1100.0)
        self.assertAlmostEqual(result["portfolio_pnl_pct"], -11.0)
        self.assertEqual(len(result["snapshot_id"]), 64)
        self.assertEqual(result["scenario"]["source"], "built_in")
        self.assertEqual(result["assumptions"]["formula_version"], "portfolio_stress_linear_v2")
        self.assertEqual([row["symbol"] for row in result["top_losers"]], ["AAA", "BBB"])
        self.assertEqual(result["top_winners"], [])
        self.assertIsNone(result["position_impacts"][0]["beta_as_of"])

    def test_account_values_are_converted_before_weights_and_same_symbol_is_preserved(self) -> None:
        snapshot = {
            "currency": "CNY",
            "total_market_value": 14200,
            "fx_stale": False,
            "data_quality": "ok",
            "limitations": [],
            "accounts": [
                {"account_id": 1, "base_currency": "CNY", "positions": [self._position("SAME", 7000)]},
                {"account_id": 2, "base_currency": "USD", "positions": [self._position("SAME", 1000, currency="USD")]},
            ],
        }
        result = self._service(snapshot).run_stress_test(
            as_of=date(2026, 6, 1), scenario_id="market_down_10", betas={"SAME": 1}
        )
        self.assertEqual(result["portfolio_value"], 14200)
        self.assertEqual(result["reconciliation_delta"], 0)
        self.assertEqual(len(result["position_impacts"]), 2)
        self.assertEqual(len({item["position_key"] for item in result["position_impacts"]}), 2)
        self.assertEqual(
            sum(item["market_value"] for item in result["position_impacts"]),
            result["portfolio_value"],
        )
        self.assertEqual(
            sum(item["pnl"] for item in result["position_impacts"]),
            result["portfolio_pnl"],
        )
        values = sorted(item["market_value"] for item in result["position_impacts"])
        self.assertEqual(values, [7000, 7200])
        usd_position = next(
            item for item in result["position_impacts"] if item["account_id"] == 2
        )
        self.assertEqual(usd_position["fx_rate_source"], "test_fx_feed")
        self.assertEqual(usd_position["fx_rate_method"], "direct_rate")
        self.assertEqual(usd_position["fx_as_of"], date(2026, 5, 30))

    def test_instrument_to_account_fx_provenance_is_preserved_separately(self) -> None:
        position = self._position("FOREIGN", 7000, currency="USD")
        position.update(
            {
                "valuation_fx_rate_to_account_base": 7.0,
                "valuation_fx_rate_source": "cached_daily_fx",
                "valuation_fx_rate_method": "direct_rate",
                "valuation_fx_as_of": date(2026, 5, 29),
                "valuation_fx_stale": True,
            }
        )
        snapshot = {
            "currency": "CNY",
            "total_market_value": 7000,
            "fx_stale": True,
            "data_quality": "partial",
            "limitations": ["stale FX"],
            "accounts": [
                {
                    "account_id": 1,
                    "base_currency": "CNY",
                    "positions": [position],
                }
            ],
        }
        result = self._service(snapshot).run_stress_test(
            as_of=date(2026, 6, 1), scenario_id="fx_down_5"
        )
        impact = result["position_impacts"][0]
        self.assertEqual(impact["valuation_fx_rate_to_account_base"], 7.0)
        self.assertEqual(impact["valuation_fx_rate_source"], "cached_daily_fx")
        self.assertEqual(impact["valuation_fx_as_of"], date(2026, 5, 29))
        self.assertTrue(impact["valuation_fx_stale"])
        self.assertEqual(impact["fx_rate_method"], "identity")
        self.assertIsNone(impact["fx_as_of"])

    def test_fx_shock_uses_instrument_currency_not_account_base(self) -> None:
        snapshot = {
            "currency": "CNY",
            "total_market_value": 10000,
            "fx_stale": False,
            "data_quality": "ok",
            "limitations": [],
            "accounts": [
                {
                    "account_id": 1,
                    "base_currency": "CNY",
                    "positions": [
                        self._position("FOREIGN", 4000, currency="USD"),
                        self._position("LOCAL", 6000, currency="CNY"),
                    ],
                }
            ],
        }
        result = self._service(snapshot).run_stress_test(
            as_of=date(2026, 6, 1), scenario_id="fx_down_5"
        )
        by_symbol = {item["symbol"]: item for item in result["position_impacts"]}
        self.assertEqual(by_symbol["FOREIGN"]["shock_pct"], -5)
        self.assertEqual(by_symbol["LOCAL"]["shock_pct"], 0)
        self.assertEqual(result["portfolio_pnl"], -200)

    def test_sector_template_requires_complete_caller_path(self) -> None:
        service = self._service(self._snapshot())
        with self.assertRaisesRegex(ValueError, "POST must provide sector_map"):
            service.run_stress_test(
                as_of=date(2026, 6, 1),
                scenario_id="sector_down_30",
                target_sector="banks",
            )
        result = service.run_stress_test(
            as_of=date(2026, 6, 1),
            scenario_id="sector_down_30",
            target_sector="banks",
            sector_map={"AAA": "Banks", "BBB": "Tech"},
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["portfolio_pnl"], -1800)
        self.assertTrue(
            all(
                item["classification_as_of"] is None
                for item in result["position_impacts"]
                if item["sector"] is not None
            )
        )

    def test_unavailable_price_remains_visible_and_does_not_become_empty(self) -> None:
        snapshot = {
            "currency": "CNY",
            "total_market_value": 0,
            "fx_stale": False,
            "data_quality": "partial",
            "limitations": ["price unavailable"],
            "accounts": [
                {"account_id": 1, "base_currency": "CNY", "positions": [self._position("HELD", 0, available=False)]}
            ],
        }
        result = self._service(snapshot).run_stress_test(
            as_of=date(2026, 6, 1), scenario_id="market_down_10"
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["excluded_position_count"], 1)
        self.assertEqual(result["excluded_positions"][0]["reason"], "price_unavailable")
        self.assertEqual(result["excluded_unknown_value_count"], 1)
        self.assertEqual(result["excluded_known_market_value"], 0)
        self.assertEqual(result["excluded_positions"][0]["value_status"], "unknown")

    def test_snapshot_and_direct_map_limits_fail_before_calculation(self) -> None:
        snapshot = self._snapshot()
        snapshot["accounts"][0]["positions"] = [
            self._position(f"P{index}", 1) for index in range(513)
        ]
        service = self._service(snapshot)
        with self.assertRaisesRegex(ValueError, "at most 512 positions"):
            service.run_stress_test(
                as_of=date(2026, 6, 1), scenario_id="market_down_10"
            )
        with self.assertRaisesRegex(ValueError, "betas must contain at most 256"):
            service.run_stress_test(
                as_of=date(2026, 6, 1),
                scenario_id="market_down_10",
                betas={f"P{index}": 1.0 for index in range(257)},
            )

    def test_stale_snapshot_propagates_partial(self) -> None:
        result = self._service(self._snapshot(stale=True)).run_stress_test(
            as_of=date(2026, 6, 1), scenario_id="fx_down_5"
        )
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["snapshot_fx_stale"])
        self.assertEqual(result["snapshot_data_quality"], "partial")

    def test_winners_and_losers_are_strict_disjoint_sign_filters(self) -> None:
        result = self._service(self._snapshot()).run_stress_test(
            as_of=date(2026, 6, 1),
            custom_shocks=[{"factor": "market", "value_pct": -10}],
            betas={"AAA": 1, "BBB": -1},
        )
        self.assertEqual([item["symbol"] for item in result["top_losers"]], ["AAA"])
        self.assertEqual([item["symbol"] for item in result["top_winners"]], ["BBB"])
        zero = self._service(self._snapshot()).run_stress_test(
            as_of=date(2026, 6, 1),
            custom_shocks=[{"factor": "market", "value_pct": -10}],
            betas={"AAA": 0, "BBB": 0},
        )
        self.assertEqual(zero["top_losers"], [])
        self.assertEqual(zero["top_winners"], [])

    def test_rankings_are_capped_at_five_with_deterministic_ties(self) -> None:
        symbols = [f"S{index}" for index in range(6)]
        snapshot = {
            "currency": "CNY",
            "total_market_value": 600,
            "fx_stale": False,
            "data_quality": "ok",
            "limitations": [],
            "accounts": [
                {
                    "account_id": 1,
                    "base_currency": "CNY",
                    "positions": [self._position(symbol, 100) for symbol in symbols],
                }
            ],
        }
        service = self._service(snapshot)
        losses = service.run_stress_test(
            as_of=date(2026, 6, 1),
            scenario_id="market_down_10",
            betas={symbol: 1 for symbol in symbols},
        )
        self.assertEqual([item["symbol"] for item in losses["top_losers"]], symbols[:5])
        self.assertEqual(losses["top_winners"], [])

        wins = service.run_stress_test(
            as_of=date(2026, 6, 1),
            scenario_id="market_down_10",
            betas={symbol: -1 for symbol in symbols},
        )
        self.assertEqual([item["symbol"] for item in wins["top_winners"]], symbols[:5])
        self.assertEqual(wins["top_losers"], [])

    def test_composed_return_below_minus_one_hundred_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "below -100"):
            self._service(self._snapshot()).run_stress_test(
                as_of=date(2026, 6, 1),
                custom_shocks=[
                    {"factor": "market", "value_pct": -100},
                    {"factor": "rate", "value_bp": 100},
                ],
                betas={"AAA": 1, "BBB": 1},
            )


class PortfolioSnapshotReadOnlyTests(TestCase):
    def test_preview_does_not_materialize_snapshot_rows(self) -> None:
        repo = MagicMock()
        account = MagicMock(id=7, base_currency="CNY")
        repo.list_accounts.return_value = [account]
        service = PortfolioService(repo=repo)
        replay = {
            "public": {"account_id": 7, "base_currency": "CNY", "limitations": []},
            "total_cash": 0.0,
            "total_market_value": 0.0,
            "total_equity": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "fee_total": 0.0,
            "tax_total": 0.0,
            "fx_stale": False,
        }
        service._replay_account = MagicMock(return_value=replay)  # type: ignore[method-assign]
        result = service.preview_portfolio_snapshot(as_of=date(2026, 6, 1))
        self.assertEqual(result["account_count"], 1)
        repo.replace_positions_lots_and_snapshot.assert_not_called()

    def test_conversion_provenance_keeps_cached_source_and_rate_date(self) -> None:
        repo = MagicMock()
        repo.get_latest_fx_rate.return_value = MagicMock(
            rate=7.2,
            is_stale=False,
            source="manual_import",
            rate_date=date(2026, 5, 30),
        )
        service = PortfolioService(repo=repo)
        conversion = service.convert_amount_with_provenance(
            amount=100,
            from_currency="USD",
            to_currency="CNY",
            as_of_date=date(2026, 6, 1),
        )
        self.assertEqual(conversion["converted_amount"], 720)
        self.assertEqual(conversion["rate"], 7.2)
        self.assertEqual(conversion["source"], "manual_import")
        self.assertEqual(conversion["rate_date"], date(2026, 5, 30))
        self.assertEqual(conversion["method"], "direct_rate")
