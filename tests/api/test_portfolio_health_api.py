"""API contracts for stored GET and explicit portfolio-health refresh."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import text

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
        for key in (
            "ENV_FILE",
            "DATABASE_PATH",
            "PORTFOLIO_HEALTH_WEIGHT_RISK_EXPOSURE",
        ):
            os.environ.pop(key, None)
        self.temp_dir.cleanup()

    def _health_row_count(self) -> int:
        database = DatabaseManager.get_instance()
        with database.get_session() as session:
            value = session.execute(
                text("SELECT COUNT(*) FROM portfolio_health_snapshots")
            ).scalar_one()
        return int(value)

    def test_get_is_read_only_and_returns_not_found_before_refresh(self) -> None:
        before = self._health_row_count()
        response = self.client.get(
            "/api/v1/portfolio/health",
            params={"as_of": "2026-01-15"},
        )
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["error"], "portfolio_health_not_found")
        self.assertEqual(self._health_row_count(), before)

    def test_preview_zero_writes_then_refresh_round_trips_through_get(self) -> None:
        preview = self.client.post(
            "/api/v1/portfolio/health/refresh",
            params={"as_of": "2026-01-15", "persist": "false"},
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertFalse(preview.json()["persisted"])
        self.assertEqual(preview.json()["status"], "empty_portfolio")
        self.assertEqual(self._health_row_count(), 0)

        refresh = self.client.post(
            "/api/v1/portfolio/health/refresh",
            params={"as_of": "2026-01-15", "persist": "true"},
        )
        self.assertEqual(refresh.status_code, 200, refresh.text)
        self.assertTrue(refresh.json()["persisted"])
        self.assertEqual(self._health_row_count(), 1)

        stored = self.client.get(
            "/api/v1/portfolio/health",
            params={"as_of": "2026-01-15"},
        )
        self.assertEqual(stored.status_code, 200, stored.text)
        self.assertEqual(stored.json(), refresh.json())

    def test_missing_migration_is_stable_503_and_not_recreated(self) -> None:
        database = DatabaseManager.get_instance()
        with database.get_session() as session:
            session.execute(text("DROP TABLE portfolio_health_snapshots"))
            session.commit()
        response = self.client.get(
            "/api/v1/portfolio/health",
            params={"as_of": "2026-01-15"},
        )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            response.json()["error"], "portfolio_health_migration_required"
        )
        with database.get_session() as session:
            names = set(
                session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).scalars()
            )
        self.assertNotIn("portfolio_health_snapshots", names)

    def test_non_finite_operator_config_fails_closed(self) -> None:
        os.environ["PORTFOLIO_HEALTH_WEIGHT_RISK_EXPOSURE"] = "NaN"
        Config.reset_instance()
        response = self.client.post(
            "/api/v1/portfolio/health/refresh",
            params={"as_of": "2026-01-15", "persist": "false"},
        )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"], "portfolio_health_input_invalid")


if __name__ == "__main__":
    unittest.main()
