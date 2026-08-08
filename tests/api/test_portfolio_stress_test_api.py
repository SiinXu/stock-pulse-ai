# -*- coding: utf-8 -*-
"""API contract tests for portfolio stress-test endpoints (issue #158)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.storage import DatabaseManager


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


class PortfolioStressTestApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "stress_api_test.db"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        app = create_app(static_dir=self.data_dir / "empty-static")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def test_list_scenarios(self) -> None:
        resp = self.client.get("/api/v1/portfolio/stress-test/scenarios")
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertFalse(payload["historical_replay_available"])
        self.assertEqual(payload["simulation_method"], "deterministic_factor_shock")
        ids = {item["id"] for item in payload["scenarios"]}
        self.assertIn("market_down_10", ids)
        self.assertIn("sector_down_30", ids)

    def test_empty_portfolio_get(self) -> None:
        resp = self.client.get(
            "/api/v1/portfolio/stress-test",
            params={"scenario_id": "market_down_10", "as_of": "2026-01-15"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "empty_portfolio")
        self.assertIsNone(payload["portfolio_pnl"])
        self.assertFalse(payload["assumptions"]["provider_calls_on_hot_path"])
        self.assertFalse(payload["assumptions"]["historical_replay"])
        self.assertIn(
            "deterministic_instantaneous_factor_shock",
            payload["assumptions"]["simplified_assumptions"],
        )

    def test_missing_scenario_id_rejected(self) -> None:
        resp = self.client.get("/api/v1/portfolio/stress-test")
        self.assertEqual(resp.status_code, 422)

    def test_sector_without_target_returns_400(self) -> None:
        resp = self.client.get(
            "/api/v1/portfolio/stress-test",
            params={"scenario_id": "sector_down_30"},
        )
        self.assertEqual(resp.status_code, 400, resp.text)

    @patch(
        "src.services.portfolio_stress_test_service.PortfolioStressTestService.run_stress_test"
    )
    def test_post_custom_shocks_payload_shape(self, mock_run: MagicMock) -> None:
        mock_run.return_value = {
            "as_of": "2026-06-01",
            "account_id": 1,
            "cost_method": "fifo",
            "currency": "CNY",
            "status": "ok",
            "status_message": "Deterministic factor shock applied to current holdings.",
            "portfolio_value": 10000.0,
            "positions_used": 2,
            "simulation_method": "deterministic_factor_shock",
            "historical_replay_available": False,
            "scenario": {
                "id": "custom",
                "name": "Custom scenario",
                "description": "Caller-supplied deterministic factor shocks.",
                "category": "custom",
                "shocks": [{"factor": "market", "value_pct": -8.0}],
                "target_sector": None,
            },
            "assumptions": {
                "simulation_method": "deterministic_factor_shock",
                "historical_replay": False,
                "linear_factor_additivity": True,
                "instantaneous_shock": True,
                "cash_excluded": True,
                "weight_basis": "market_value_base",
                "provider_calls_on_hot_path": False,
                "beta_policy": "caller_provided_betas",
                "sector_policy": "position_sector_field_or_missing",
                "fx_policy": (
                    "apply_only_when_valuation_currency_differs_from_portfolio_base"
                ),
                "rate_policy": "equity_return_pct = -rate_sensitivity_pct_per_100bp * (value_bp / 100)",
                "rate_sensitivity_pct_per_100bp": 2.0,
                "reuses_risk_metrics_concentration": True,
                "data_source": "portfolio_holdings_snapshot_only",
                "simplified_assumptions": ["deterministic_instantaneous_factor_shock"],
                "scenario_category": "custom",
            },
            "missing_data": [],
            "portfolio_pnl": -800.0,
            "portfolio_pnl_pct": -8.0,
            "stressed_portfolio_value": 9200.0,
            "position_impacts": [
                {
                    "symbol": "AAA",
                    "market_value": 6000.0,
                    "weight_pct": 60.0,
                    "shock_pct": -8.0,
                    "pnl": -480.0,
                    "stressed_market_value": 5520.0,
                    "beta_used": 1.0,
                    "beta_source": "provided",
                    "sector": None,
                    "valuation_currency": "CNY",
                }
            ],
            "top_losers": [],
            "top_winners": [],
            "concentration": {
                "status": "ok",
                "hhi": 0.52,
                "effective_n": 1.923077,
                "diversification_score": 0.96,
                "top_weight_pct": 60.0,
                "position_count": 2,
                "weights": [
                    {"symbol": "AAA", "weight_pct": 60.0},
                    {"symbol": "BBB", "weight_pct": 40.0},
                ],
            },
        }
        resp = self.client.post(
            "/api/v1/portfolio/stress-test",
            json={
                "as_of": "2026-06-01",
                "account_id": 1,
                "custom_shocks": [{"factor": "market", "value_pct": -8.0}],
                "betas": {"AAA": 1.0, "BBB": 1.0},
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "ok")
        self.assertAlmostEqual(payload["portfolio_pnl"], -800.0, places=4)
        mock_run.assert_called_once()
        kwargs = mock_run.call_args.kwargs
        self.assertEqual(kwargs["custom_shocks"][0]["factor"], "market")
        self.assertEqual(kwargs["betas"]["AAA"], 1.0)
