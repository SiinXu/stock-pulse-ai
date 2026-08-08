# -*- coding: utf-8 -*-
"""API contract tests for GET /api/v1/portfolio/health (issue #151)."""

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


class PortfolioHealthApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "health_api_test.db"
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
            "/api/v1/portfolio/health",
            params={"as_of": "2026-01-15", "persist": "false"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "empty_portfolio")
        self.assertIsNone(payload["score"])
        self.assertEqual(payload["score_source"], "rules")
        self.assertFalse(payload["llm_can_modify_score"])
        self.assertIn("not investment advice", payload["disclaimer"].lower())

    def test_endpoint_returns_partial_path_fields(self) -> None:
        fake = {
            "as_of": "2026-03-01",
            "account_id": None,
            "cost_method": "fifo",
            "currency": "CNY",
            "status": "partial",
            "status_message": "unavailable risk_exposure",
            "score": 72.5,
            "band": "fair",
            "disclaimer": (
                "Portfolio health is a structural portfolio metric, not investment advice. "
                "Scores are deterministic and fully recomputable from documented formulas."
            ),
            "score_source": "rules",
            "llm_can_modify_score": False,
            "formula_version": "portfolio_health_v1",
            "weights": {
                "concentration": 0.25,
                "risk_exposure": 0.25,
                "diversification": 0.20,
                "pnl": 0.15,
                "cash_ratio": 0.15,
            },
            "effective_weights": {
                "concentration": 0.333333,
                "diversification": 0.266667,
                "pnl": 0.2,
                "cash_ratio": 0.2,
            },
            "bands": [],
            "dimensions": {
                "risk_exposure": {"status": "unavailable", "score": None},
            },
            "unavailable_dimensions": ["risk_exposure"],
            "insights": [],
            "data_quality": {
                "status": "partial",
                "fx_stale": False,
                "snapshot_data_quality": "ok",
                "limitations": [],
                "missing_price_symbols": [],
                "risk_metrics_status": "insufficient_history",
                "partial_reasons": ["risk_exposure_insufficient_history"],
            },
            "inputs": {
                "top_weight_pct": 20.0,
                "var_pct": None,
                "diversification_score": 0.9,
                "unrealized_pnl_pct": 5.0,
                "cash_pct": 10.0,
                "total_equity": 100000.0,
                "total_cash": 10000.0,
                "total_market_value": 90000.0,
            },
            "persisted": False,
        }
        with patch(
            "api.v1.endpoints.portfolio_health.PortfolioHealthService"
        ) as mock_cls:
            mock_cls.return_value.get_health.return_value = fake
            resp = self.client.get(
                "/api/v1/portfolio/health",
                params={"as_of": "2026-03-01", "persist": "false"},
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "partial")
        self.assertIn("risk_exposure", payload["unavailable_dimensions"])
        self.assertFalse(payload["llm_can_modify_score"])
        self.assertEqual(payload["score_source"], "rules")
        self.assertIsNone(payload["inputs"]["var_pct"])


if __name__ == "__main__":
    unittest.main()
