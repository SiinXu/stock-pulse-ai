# -*- coding: utf-8 -*-
"""API contract tests for GET /api/v1/portfolio/risk-metrics (issue #239 V0)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
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


class PortfolioRiskMetricsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "risk_metrics_api_test.db"
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
            "/api/v1/portfolio/risk-metrics",
            params={"as_of": "2026-01-15", "lookback_trading_days": 60},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "empty_portfolio")
        self.assertIsNone(payload["var"]["var_pct"])
        self.assertEqual(payload["var"]["status"], "unavailable")
        self.assertFalse(payload["assumptions"]["provider_calls_on_hot_path"])
        self.assertEqual(payload["assumptions"]["var_method"], "historical")

    def test_validation_rejects_bad_confidence(self) -> None:
        resp = self.client.get(
            "/api/v1/portfolio/risk-metrics",
            params={"confidence": 1.0},
        )
        self.assertEqual(resp.status_code, 422)

    @patch("src.services.portfolio_risk_metrics_service.PortfolioRiskMetricsService.get_risk_metrics")
    def test_ok_payload_shape(self, mock_get: MagicMock) -> None:
        mock_get.return_value = {
            "as_of": "2026-06-01",
            "account_id": 1,
            "cost_method": "fifo",
            "currency": "CNY",
            "status": "ok",
            "status_message": "Risk metrics computed from stored daily history.",
            "portfolio_value": 10000.0,
            "positions_used": 2,
            "assumptions": {
                "var_method": "historical",
                "confidence": 0.95,
                "horizon_days": 1,
                "lookback_trading_days": 252,
                "min_return_observations": 60,
                "min_correlation_observations": 30,
                "return_definition": "simple_close_to_close",
                "portfolio_aggregation": "static_current_market_value_weights",
                "cash_excluded": True,
                "weight_basis": "market_value_base",
                "horizon_scaling": "none",
                "distribution_assumption": "empirical",
                "correlation_method": "pearson",
                "concentration_metrics": "hhi_effective_n_normalized_diversification_score",
                "data_source": "stored_stock_daily_closes_and_portfolio_holdings",
                "provider_calls_on_hot_path": False,
            },
            "var": {
                "status": "ok",
                "status_message": "ok",
                "confidence": 0.95,
                "horizon_days": 1,
                "var_pct": 2.5,
                "var_value": 250.0,
                "observation_count": 100,
                "percentile_used": 0.05,
                "one_day_var_pct": 2.5,
            },
            "correlation": {
                "status": "ok",
                "status_message": "ok",
                "symbols": ["AAA", "BBB"],
                "matrix": [[1.0, 0.5], [0.5, 1.0]],
                "observation_count": 100,
            },
            "concentration": {
                "status": "ok",
                "hhi": 0.5,
                "effective_n": 2.0,
                "diversification_score": 1.0,
                "top_weight_pct": 50.0,
                "position_count": 2,
                "weights": [
                    {"symbol": "AAA", "weight_pct": 50.0},
                    {"symbol": "BBB", "weight_pct": 50.0},
                ],
            },
            "history": {
                "aligned_trading_days": 100,
                "lookback_trading_days_requested": 252,
                "price_series_symbols": ["AAA", "BBB"],
                "aligned_start": "2025-01-01",
                "aligned_end": "2026-06-01",
            },
        }
        resp = self.client.get(
            "/api/v1/portfolio/risk-metrics",
            params={"account_id": 1, "as_of": "2026-06-01"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["var"]["var_pct"], 2.5)
        self.assertEqual(payload["correlation"]["symbols"], ["AAA", "BBB"])
        self.assertEqual(payload["concentration"]["effective_n"], 2.0)

    @patch("api.v1.endpoints.portfolio_risk_metrics.PortfolioRiskMetricsService")
    def test_insufficient_history_surface(self, mock_cls: MagicMock) -> None:
        mock_cls.return_value.get_risk_metrics.return_value = {
            "as_of": "2026-06-01",
            "account_id": None,
            "cost_method": "fifo",
            "currency": "CNY",
            "status": "insufficient_history",
            "status_message": "Insufficient aligned trading-day history (10 < 60 required).",
            "portfolio_value": 10000.0,
            "positions_used": 2,
            "assumptions": {
                "var_method": "historical",
                "confidence": 0.95,
                "horizon_days": 1,
                "lookback_trading_days": 60,
                "min_return_observations": 60,
                "min_correlation_observations": 30,
                "return_definition": "simple_close_to_close",
                "portfolio_aggregation": "static_current_market_value_weights",
                "cash_excluded": True,
                "weight_basis": "market_value_base",
                "horizon_scaling": "none",
                "distribution_assumption": "empirical",
                "correlation_method": "pearson",
                "concentration_metrics": "hhi_effective_n_normalized_diversification_score",
                "data_source": "stored_stock_daily_closes_and_portfolio_holdings",
                "provider_calls_on_hot_path": False,
            },
            "var": {
                "status": "insufficient_history",
                "status_message": "Need at least 60 aligned portfolio return observations; have 10.",
                "confidence": 0.95,
                "horizon_days": 1,
                "var_pct": None,
                "var_value": None,
                "observation_count": 10,
                "percentile_used": 0.05,
            },
            "correlation": {
                "status": "insufficient_history",
                "status_message": "Need at least 30 aligned return observations for correlation; have 10.",
                "symbols": ["AAA", "BBB"],
                "matrix": [],
                "observation_count": 10,
            },
            "concentration": {
                "status": "ok",
                "hhi": 0.5,
                "effective_n": 2.0,
                "diversification_score": 1.0,
                "top_weight_pct": 50.0,
                "position_count": 2,
                "weights": [
                    {"symbol": "AAA", "weight_pct": 50.0},
                    {"symbol": "BBB", "weight_pct": 50.0},
                ],
            },
            "history": {
                "aligned_trading_days": 10,
                "lookback_trading_days_requested": 60,
                "price_series_symbols": ["AAA", "BBB"],
                "aligned_start": "2026-05-20",
                "aligned_end": "2026-06-01",
            },
        }
        resp = self.client.get("/api/v1/portfolio/risk-metrics")
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "insufficient_history")
        self.assertIsNone(payload["var"]["var_pct"])
        self.assertIsNone(payload["var"]["var_value"])
