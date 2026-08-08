# -*- coding: utf-8 -*-
"""API contract tests for /api/v1/calculators/* (issue #240)."""

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


class CalculatorsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "calculators_api_test.db"
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

    def test_compound_growth_ok(self) -> None:
        resp = self.client.post(
            "/api/v1/calculators/compound-growth",
            json={
                "principal": 1000,
                "annual_rate": 0.12,
                "years": 1,
                "contribution_per_period": 0,
                "periods_per_year": 12,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "ok")
        self.assertAlmostEqual(payload["final_value"], 1000.0 * (1.01 ** 12), places=6)
        self.assertEqual(len(payload["series"]), 13)

    def test_compound_growth_rejects_non_finite(self) -> None:
        resp = self.client.post(
            "/api/v1/calculators/compound-growth",
            json={
                "principal": "NaN",
                "annual_rate": 0.05,
                "years": 1,
                "contribution_per_period": 0,
                "periods_per_year": 12,
            },
        )
        # Pydantic may reject before service; either 400 or 422 is acceptable.
        self.assertIn(resp.status_code, (400, 422), resp.text)

    def test_target_contribution_ok(self) -> None:
        resp = self.client.post(
            "/api/v1/calculators/target-contribution",
            json={
                "target": 5000,
                "principal": 1000,
                "annual_rate": 0.0,
                "years": 2,
                "periods_per_year": 12,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "ok")
        self.assertAlmostEqual(payload["contribution_per_period"], 4000.0 / 24.0, places=6)

    def test_target_duration_unreachable(self) -> None:
        resp = self.client.post(
            "/api/v1/calculators/target-duration",
            json={
                "target": 5000,
                "principal": 1000,
                "annual_rate": 0.0,
                "contribution_per_period": 0,
                "periods_per_year": 12,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "unreachable")
        self.assertIsNone(payload["period_count"])
        self.assertIsInstance(payload["message"], str)
        self.assertNotIn("inf", payload["message"].lower())

    def test_target_duration_ok(self) -> None:
        resp = self.client.post(
            "/api/v1/calculators/target-duration",
            json={
                "target": 5000,
                "principal": 1000,
                "annual_rate": 0.0,
                "contribution_per_period": 100,
                "periods_per_year": 12,
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["period_count"], 40)


if __name__ == "__main__":
    unittest.main()
