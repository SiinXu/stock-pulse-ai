# -*- coding: utf-8 -*-
"""API tests for Futu portfolio import endpoints."""

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
from data_provider.futu_position_fetcher import FutuPosition, FutuPositionFetchError
from src.config import Config
from src.storage import DatabaseManager


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


class FutuImportApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "futu_api.db"
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

    def _create_account(self) -> int:
        resp = self.client.post(
            "/api/v1/portfolio/accounts",
            json={
                "name": "Futu API",
                "broker": "Futu",
                "market": "us",
                "base_currency": "USD",
            },
        )
        self.assertEqual(resp.status_code, 200)
        return int(resp.json()["id"])

    def test_preview_and_commit_import(self) -> None:
        account_id = self._create_account()
        positions = [
            FutuPosition(
                futu_acc_id=9,
                futu_code="US.AAPL",
                symbol="AAPL",
                market="US",
                quantity=3.0,
                cost_price=180.0,
                currency="USD",
            )
        ]
        with patch(
            "src.services.portfolio_import_service.fetch_futu_positions",
            return_value=positions,
        ):
            preview = self.client.post(
                "/api/v1/portfolio/imports/futu/preview",
                params={"as_of": "2026-08-06"},
            )
            self.assertEqual(preview.status_code, 200)
            body = preview.json()
            self.assertEqual(body["broker"], "futu")
            self.assertEqual(body["record_count"], 1)
            self.assertEqual(body["records"][0]["symbol"], "AAPL")

            commit = self.client.post(
                "/api/v1/portfolio/imports/futu",
                json={
                    "account_id": account_id,
                    "dry_run": False,
                    "as_of": "2026-08-06",
                },
            )
            self.assertEqual(commit.status_code, 200)
            self.assertEqual(commit.json()["inserted_count"], 1)

            again = self.client.post(
                "/api/v1/portfolio/imports/futu",
                json={
                    "account_id": account_id,
                    "dry_run": False,
                    "as_of": "2026-08-06",
                },
            )
            self.assertEqual(again.status_code, 200)
            self.assertEqual(again.json()["duplicate_count"], 1)
            self.assertEqual(again.json()["inserted_count"], 0)

    def test_unreachable_opend_returns_503(self) -> None:
        account_id = self._create_account()
        with patch(
            "src.services.portfolio_import_service.fetch_futu_positions",
            side_effect=FutuPositionFetchError("Futu OpenD is unreachable"),
        ):
            resp = self.client.post(
                "/api/v1/portfolio/imports/futu",
                json={"account_id": account_id, "dry_run": True},
            )
        self.assertEqual(resp.status_code, 503)
        payload = resp.json()
        error = payload.get("error")
        if error is None and isinstance(payload.get("detail"), dict):
            error = payload["detail"].get("error")
        self.assertEqual(error, "futu_opend_unavailable")


if __name__ == "__main__":
    unittest.main()
