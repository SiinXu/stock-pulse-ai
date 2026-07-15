# -*- coding: utf-8 -*-
"""Persistent idempotency coverage for portfolio money mutations."""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.services.portfolio_import_service import PortfolioImportService
from src.services.portfolio_service import (
    PortfolioIdempotencyConflictError,
    PortfolioService,
)
from src.storage import DatabaseManager


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
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "portfolio_idempotency_test.db"
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
        self.service = PortfolioService()
        self.account_id = self.service.create_account(
            name="Main",
            broker="Demo",
            market="cn",
            base_currency="CNY",
        )["id"]
        self.client = TestClient(create_app(static_dir=self.data_dir / "empty-static"))

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    @staticmethod
    def _csv_bytes(price: int = 100) -> bytes:
        return (
            "成交日期,证券代码,买卖标志,成交数量,成交均价,成交编号,手续费,印花税\n"
            f"2026-01-02,600519,买入,10,{price},HT-IDEMPOTENT-001,1,0\n"
        ).encode("utf-8")

    def test_timeout_after_commit_replays_trade_response_from_new_service(self) -> None:
        request = {
            "account_id": self.account_id,
            "symbol": "600519",
            "trade_date": date(2026, 1, 2),
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "market": "cn",
            "currency": "CNY",
            "operation_id": "trade-timeout-after-commit-1",
        }

        first = self.service.record_trade(**request)
        replay = PortfolioService().record_trade(**request)

        self.assertEqual(replay, first)
        events = self.service.list_trade_events(account_id=self.account_id)
        self.assertEqual(events["total"], 1)

    def test_same_operation_id_with_different_payload_is_stable_conflict(self) -> None:
        self.service.record_cash_ledger(
            account_id=self.account_id,
            event_date=date(2026, 1, 1),
            direction="in",
            amount=1000,
            operation_id="cash-conflict-1",
        )

        with self.assertRaises(PortfolioIdempotencyConflictError):
            PortfolioService().record_cash_ledger(
                account_id=self.account_id,
                event_date=date(2026, 1, 1),
                direction="in",
                amount=2000,
                operation_id="cash-conflict-1",
            )
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            1,
        )

    def test_same_operation_id_cannot_move_between_mutation_types(self) -> None:
        self.service.record_cash_ledger(
            account_id=self.account_id,
            event_date=date(2026, 1, 1),
            direction="in",
            amount=1000,
            operation_id="cross-type-operation-1",
        )

        with self.assertRaises(PortfolioIdempotencyConflictError):
            self.service.record_corporate_action(
                account_id=self.account_id,
                symbol="600519",
                effective_date=date(2026, 1, 3),
                action_type="cash_dividend",
                cash_dividend_per_share=1,
                operation_id="cross-type-operation-1",
            )

    def test_corporate_action_retry_replays_first_response(self) -> None:
        request = {
            "account_id": self.account_id,
            "symbol": "600519",
            "effective_date": date(2026, 1, 3),
            "action_type": "cash_dividend",
            "cash_dividend_per_share": 1,
            "operation_id": "corporate-timeout-after-commit-1",
        }

        first = self.service.record_corporate_action(**request)
        replay = PortfolioService().record_corporate_action(**request)

        self.assertEqual(replay, first)
        self.assertEqual(
            self.service.list_corporate_action_events(account_id=self.account_id)["total"],
            1,
        )

    def test_concurrent_same_cash_operation_writes_once(self) -> None:
        barrier = threading.Barrier(3)
        responses: list[dict] = []
        errors: list[Exception] = []

        def _worker() -> None:
            barrier.wait()
            try:
                responses.append(
                    PortfolioService().record_cash_ledger(
                        account_id=self.account_id,
                        event_date=date(2026, 1, 1),
                        direction="in",
                        amount=1000,
                        operation_id="cash-concurrent-1",
                    )
                )
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=_worker, daemon=True) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0], responses[1])
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            1,
        )

    def test_csv_retry_replays_first_commit_summary(self) -> None:
        importer = PortfolioImportService()
        parsed = importer.parse_trade_csv(broker="huatai", content=self._csv_bytes())
        request = {
            "account_id": self.account_id,
            "broker": parsed["broker"],
            "records": parsed["records"],
            "dry_run": False,
            "operation_id": "csv-timeout-after-commit-1",
        }

        first = importer.commit_trade_records(**request)
        replay = PortfolioImportService().commit_trade_records(**request)

        self.assertEqual(first["inserted_count"], 1)
        self.assertEqual(replay, first)
        self.assertEqual(
            self.service.list_trade_events(account_id=self.account_id)["total"],
            1,
        )

    def test_csv_operation_id_rejects_different_file_payload(self) -> None:
        importer = PortfolioImportService()
        first_records = importer.parse_trade_csv(
            broker="huatai",
            content=self._csv_bytes(price=100),
        )["records"]
        changed_records = importer.parse_trade_csv(
            broker="huatai",
            content=self._csv_bytes(price=101),
        )["records"]
        importer.commit_trade_records(
            account_id=self.account_id,
            broker="huatai",
            records=first_records,
            operation_id="csv-conflict-1",
        )

        with self.assertRaises(PortfolioIdempotencyConflictError):
            PortfolioImportService().commit_trade_records(
                account_id=self.account_id,
                broker="huatai",
                records=changed_records,
                operation_id="csv-conflict-1",
            )
        self.assertEqual(
            self.service.list_trade_events(account_id=self.account_id)["total"],
            1,
        )

    def test_concurrent_csv_commit_writes_once_and_replays_first_summary(self) -> None:
        records = PortfolioImportService().parse_trade_csv(
            broker="huatai",
            content=self._csv_bytes(),
        )["records"]
        barrier = threading.Barrier(3)
        responses: list[dict] = []
        errors: list[Exception] = []

        def _worker() -> None:
            barrier.wait()
            try:
                responses.append(
                    PortfolioImportService().commit_trade_records(
                        account_id=self.account_id,
                        broker="huatai",
                        records=records,
                        operation_id="csv-concurrent-1",
                    )
                )
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=_worker, daemon=True) for _ in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0], responses[1])
        self.assertEqual(responses[0]["inserted_count"], 1)
        self.assertEqual(
            self.service.list_trade_events(account_id=self.account_id)["total"],
            1,
        )

    def test_api_accepts_header_key_and_returns_conflict_for_changed_payload(self) -> None:
        payload = {
            "account_id": self.account_id,
            "event_date": "2026-01-01",
            "direction": "in",
            "amount": 1000,
        }
        headers = {"Idempotency-Key": "cash-api-header-1"}

        first = self.client.post("/api/v1/portfolio/cash-ledger", json=payload, headers=headers)
        replay = self.client.post("/api/v1/portfolio/cash-ledger", json=payload, headers=headers)
        conflict = self.client.post(
            "/api/v1/portfolio/cash-ledger",
            json={**payload, "amount": 2000},
            headers=headers,
        )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json().get("error"), "idempotency_conflict")

    def test_api_rejects_mismatched_body_and_header_operation_ids(self) -> None:
        response = self.client.post(
            "/api/v1/portfolio/cash-ledger",
            json={
                "operation_id": "body-operation-1",
                "account_id": self.account_id,
                "event_date": "2026-01-01",
                "direction": "in",
                "amount": 1000,
            },
            headers={"Idempotency-Key": "header-operation-1"},
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json().get("error"), "operation_id_mismatch")


if __name__ == "__main__":
    unittest.main()
