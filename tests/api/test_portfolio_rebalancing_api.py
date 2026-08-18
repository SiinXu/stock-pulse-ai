# -*- coding: utf-8 -*-
"""API contract tests for GET /api/v1/portfolio/rebalancing-recommendations."""

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
from src.api.app import create_app
from src.config import Config
from src.storage import DatabaseManager


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


class PortfolioRebalancingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "rebalancing_api_test.db"
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

    def test_empty_portfolio_endpoint(self) -> None:
        resp = self.client.get(
            "/api/v1/portfolio/rebalancing-recommendations",
            params={"as_of": "2026-01-15", "risk_tolerance": "moderate"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "empty_portfolio")
        self.assertEqual(payload["suggestions"], [])
        self.assertTrue(payload["is_suggestion_only"])
        self.assertFalse(payload["auto_execute"])
        self.assertIn("not investment advice", payload["disclaimer"].lower())
        self.assertFalse(payload["assumptions"]["provider_calls_on_hot_path"])
        self.assertEqual(payload["assumptions"]["method"], "risk_band_drift_v1")

    def test_invalid_risk_tolerance_rejected(self) -> None:
        resp = self.client.get(
            "/api/v1/portfolio/rebalancing-recommendations",
            params={"risk_tolerance": "yolo"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_service_result_round_trips_schema(self) -> None:
        fake = {
            "as_of": "2026-01-15",
            "account_id": None,
            "cost_method": "fifo",
            "currency": "CNY",
            "status": "ok",
            "status_message": "1 rebalancing suggestion(s) for human review (not auto-executed).",
            "disclaimer": "Research aid only — not investment advice.",
            "risk_tolerance": "moderate",
            "is_suggestion_only": True,
            "auto_execute": False,
            "target_model": {
                "name": "risk_band_v1",
                "description": "test",
                "max_single_weight_pct": 25.0,
                "band_max_single_weight_pct": 25.0,
                "soft_max_single_name_weight": 0.25,
                "min_effective_n": 4.0,
                "max_hhi": 0.35,
                "target_var_pct_ceiling": 3.5,
                "notes": [],
            },
            "current": {
                "portfolio_value": 100000.0,
                "weights": [{"symbol": "AAA", "weight_pct": 60.0}],
                "risk_status": "ok",
                "var_pct": 2.0,
                "hhi": 0.52,
                "effective_n": 1.92,
                "diversification_score": 0.2,
            },
            "drift": {
                "max_abs_weight_drift_pct": 35.0,
                "breaches": [
                    {
                        "kind": "single_name_cap",
                        "symbol": "AAA",
                        "current_pct": 60.0,
                        "limit_pct": 25.0,
                        "drift_pct": 35.0,
                    }
                ],
            },
            "suggestions": [
                {
                    "action": "trim",
                    "symbol": "AAA",
                    "from_weight_pct": 60.0,
                    "to_weight_pct": 25.0,
                    "delta_weight_pct": -35.0,
                    "approx_notional": -35000.0,
                    "rationale": "Trim AAA: weight 60% exceeds cap 25%.",
                    "assumptions": ["suggestion only"],
                    "is_suggestion_only": True,
                    "auto_execute": False,
                }
            ],
            "position_bands": [
                {
                    "symbol": "AAA",
                    "action": "reduce",
                    "current_weight_pct": 60.0,
                    "target_weight_pct_low": 10.0,
                    "target_weight_pct_mid": 13.75,
                    "target_weight_pct_high": 17.5,
                    "effective_cap_pct": 25.0,
                    "signal": "hold",
                    "mode": "portfolio_aware",
                    "rationale": "AAA band",
                    "assumptions": ["suggestion only"],
                    "is_suggestion_only": True,
                    "auto_execute": False,
                }
            ],
            "assumptions": {
                "method": "risk_band_drift_v1",
                "uses_risk_metrics": True,
                "risk_metrics_source": "PortfolioRiskMetricsService",
                "provider_calls_on_hot_path": False,
                "tax_and_transaction_costs": "not_modeled_v1",
                "recommendation_honesty": "explicit_refusal_when_insufficient_data",
                "weight_basis": "market_value_base",
                "cross_currency": "normalized_via_portfolio_snapshot_market_value_base",
                "portfolio_aware_sizing_enabled": True,
                "drift_threshold_pct": 5.0,
            },
            "risk_metrics_summary": {
                "status": "ok",
                "var_status": "ok",
                "correlation_status": "ok",
                "concentration_status": "ok",
            },
        }
        with patch(
            "src.api.v1.endpoints.portfolio_rebalancing.PortfolioRebalancingService"
        ) as svc_cls:
            svc_cls.return_value.get_recommendations.return_value = fake
            resp = self.client.get("/api/v1/portfolio/rebalancing-recommendations")
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["suggestions"][0]["action"], "trim")
        self.assertFalse(payload["auto_execute"])
        self.assertEqual(payload["position_bands"][0]["symbol"], "AAA")


if __name__ == "__main__":
    unittest.main()
