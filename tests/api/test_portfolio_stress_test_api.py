# -*- coding: utf-8 -*-
"""API contract tests for portfolio stress-test endpoints (issue #158)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

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

    def test_post_custom_shocks_payload_shape(self) -> None:
        resp = self.client.post(
            "/api/v1/portfolio/stress-test",
            json={
                "as_of": "2026-06-01",
                "custom_shocks": [{"factor": "market", "value_pct": -8.0}],
                "betas": {"AAA": 1.0, "BBB": 1.0},
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "empty_portfolio")
        self.assertEqual(payload["scenario"]["source"], "custom_api")
        self.assertEqual(payload["scenario"]["shocks"][0]["factor"], "market")

    def test_sector_get_is_not_a_false_ready_path(self) -> None:
        resp = self.client.get(
            "/api/v1/portfolio/stress-test",
            params={"scenario_id": "sector_down_30", "target_sector": "banks"},
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertIn("POST", resp.text)

    def test_request_union_and_numeric_bounds_are_strict(self) -> None:
        invalid_bodies = [
            {
                "scenario_id": "market_down_10",
                "custom_shocks": [{"factor": "market", "value_pct": -10}],
            },
            {"custom_shocks": [{"factor": "rate", "value_pct": 100}]},
            {"custom_shocks": [{"factor": "market", "value_pct": -101}]},
            {"custom_shocks": [{"factor": "market", "value_pct": -10, "unexpected": True}]},
            {
                "scenario_id": "market_down_10",
                "betas": {f"S{i}": 1 for i in range(257)},
            },
        ]
        for body in invalid_bodies:
            with self.subTest(body=body):
                response = self.client.post("/api/v1/portfolio/stress-test", json=body)
                self.assertEqual(response.status_code, 422, response.text)

        nonfinite = self.client.post(
            "/api/v1/portfolio/stress-test",
            content='{"custom_shocks":[{"factor":"market","value_pct":NaN}]}',
            headers={"content-type": "application/json"},
        )
        self.assertEqual(nonfinite.status_code, 422, nonfinite.text)

    def test_get_query_contract_is_bounded(self) -> None:
        too_long = self.client.get(
            "/api/v1/portfolio/stress-test", params={"scenario_id": "x" * 65}
        )
        self.assertEqual(too_long.status_code, 422)
        bad_rate = self.client.get(
            "/api/v1/portfolio/stress-test",
            params={"scenario_id": "rate_up_100bp", "rate_sensitivity_pct_per_100bp": 21},
        )
        self.assertEqual(bad_rate.status_code, 422)

    def test_invalid_configured_catalog_returns_sanitized_503(self) -> None:
        missing = self.data_dir / "secret-catalog-name.yaml"
        os.environ["PORTFOLIO_STRESS_SCENARIOS_PATH"] = str(missing)
        Config.reset_instance()
        try:
            response = self.client.get("/api/v1/portfolio/stress-test/scenarios")
        finally:
            os.environ.pop("PORTFOLIO_STRESS_SCENARIOS_PATH", None)
            Config.reset_instance()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn(str(missing), response.text)
