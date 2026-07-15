# -*- coding: utf-8 -*-
"""Portfolio write idempotency contract tests."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import func, select

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.services.portfolio_service import PortfolioService
from src.storage import (
    DatabaseManager,
    PortfolioCashLedger,
    PortfolioCorporateAction,
    PortfolioIdempotencyRecord,
    PortfolioTrade,
)


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


class PortfolioIdempotencyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        data_dir = Path(self.temp_dir.name)
        self.env_path = data_dir / ".env"
        self.db_path = data_dir / "portfolio_idempotency.db"
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

        self.db = DatabaseManager.get_instance()
        self.service = PortfolioService()
        self.client = TestClient(create_app(static_dir=data_dir / "empty-static"))
        self.account_id = self.service.create_account(
            name="Main",
            broker="Demo",
            market="cn",
            base_currency="CNY",
        )["id"]

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def _count(self, model: type) -> int:
        with self.db.get_session() as session:
            return int(session.execute(select(func.count()).select_from(model)).scalar_one())

    def test_trade_api_replays_first_response_and_rejects_reused_key_with_new_payload(self) -> None:
        payload = {
            "account_id": self.account_id,
            "symbol": "600519",
            "trade_date": "2026-01-02",
            "side": "buy",
            "quantity": 10,
            "price": 100,
        }
        headers = {"Idempotency-Key": "trade-timeout-retry"}

        first = self.client.post("/api/v1/portfolio/trades", json=payload, headers=headers)
        replay = self.client.post("/api/v1/portfolio/trades", json=payload, headers=headers)
        changed = self.client.post(
            "/api/v1/portfolio/trades",
            json={**payload, "quantity": 11},
            headers=headers,
        )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(self._count(PortfolioTrade), 1)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(changed.json()["error"], "idempotency_key_reused")

    def test_cash_body_operation_id_is_supported_and_durable(self) -> None:
        payload = {
            "account_id": self.account_id,
            "event_date": "2026-01-02",
            "direction": "in",
            "amount": 1000,
            "operation_id": "cash-body-operation",
        }

        first = self.client.post("/api/v1/portfolio/cash-ledger", json=payload)
        replay = self.client.post("/api/v1/portfolio/cash-ledger", json=payload)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(self._count(PortfolioCashLedger), 1)
        self.assertEqual(self._count(PortfolioIdempotencyRecord), 1)

    def test_concurrent_cash_retries_create_one_ledger_row(self) -> None:
        ready = threading.Barrier(2)

        def submit() -> dict:
            ready.wait(timeout=2)
            return PortfolioService().record_cash_ledger(
                account_id=self.account_id,
                event_date=date(2026, 1, 2),
                direction="in",
                amount=250.0,
                operation_id="cash-concurrent-retry",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: submit(), range(2)))

        self.assertEqual(responses[0], responses[1])
        self.assertEqual(self._count(PortfolioCashLedger), 1)
        self.assertEqual(self._count(PortfolioIdempotencyRecord), 1)

    def test_corporate_action_replay_uses_the_original_row_id(self) -> None:
        payload = {
            "account_id": self.account_id,
            "symbol": "600519",
            "effective_date": "2026-01-03",
            "action_type": "cash_dividend",
            "cash_dividend_per_share": 1.5,
        }
        headers = {"Idempotency-Key": "corporate-timeout-retry"}

        first = self.client.post("/api/v1/portfolio/corporate-actions", json=payload, headers=headers)
        replay = self.client.post("/api/v1/portfolio/corporate-actions", json=payload, headers=headers)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(self._count(PortfolioCorporateAction), 1)

    def test_csv_commit_replays_first_result_without_duplicate_rows(self) -> None:
        content = (
            "成交日期,证券代码,买卖标志,成交数量,成交均价,手续费,印花税\n"
            "2026-01-02,600519,买入,10,100,1,0\n"
        ).encode("utf-8")
        headers = {"Idempotency-Key": "csv-timeout-retry"}
        request = {
            "data": {
                "account_id": str(self.account_id),
                "broker": "huatai",
                "dry_run": "false",
            },
            "files": {"file": ("trades.csv", content, "text/csv")},
            "headers": headers,
        }

        first = self.client.post("/api/v1/portfolio/imports/csv/commit", **request)
        replay = self.client.post("/api/v1/portfolio/imports/csv/commit", **request)
        changed_content = content.replace(b",10,100,", b",11,100,")
        changed = self.client.post(
            "/api/v1/portfolio/imports/csv/commit",
            data=request["data"],
            files={"file": ("trades.csv", changed_content, "text/csv")},
            headers=headers,
        )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(first.json()["inserted_count"], 1)
        self.assertEqual(self._count(PortfolioTrade), 1)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(changed.json()["error"], "idempotency_key_reused")


if __name__ == "__main__":
    unittest.main()
