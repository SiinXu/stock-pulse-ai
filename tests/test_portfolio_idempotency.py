# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persistent idempotency coverage for portfolio money mutations."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.services.portfolio_import_service import PortfolioImportService
from src.services.portfolio_service import (
    PortfolioIdempotencyConflictError,
    PortfolioService,
)
from src.storage import (
    DatabaseManager,
    PortfolioAccount,
    PortfolioCashLedger,
    PortfolioCorporateAction,
    PortfolioDailySnapshot,
    PortfolioIdempotencyRecord,
    PORTFOLIO_LEGACY_IDEMPOTENCY_GUARD_TRIGGER,
    PortfolioTrade,
)

MIGRATION_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "schema_migrations"
    / "v3_26_3.sql"
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
        self.previous_replay_window = os.environ.pop(
            "PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS",
            None,
        )
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
        os.environ.pop("PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS", None)
        if self.previous_replay_window is not None:
            os.environ[
                "PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS"
            ] = self.previous_replay_window
        self.temp_dir.cleanup()

    @staticmethod
    def _csv_bytes(price: int = 100) -> bytes:
        return (
            "成交日期,证券代码,买卖标志,成交数量,成交均价,成交编号,手续费,印花税\n"
            f"2026-01-02,600519,买入,10,{price},HT-IDEMPOTENT-001,1,0\n"
        ).encode("utf-8")

    def _age_idempotency_records(self, *, days: int = 8) -> None:
        with DatabaseManager.get_instance().get_session() as session:
            session.query(PortfolioIdempotencyRecord).update(
                {PortfolioIdempotencyRecord.created_at: datetime.now() - timedelta(days=days)}
            )
            session.commit()

    def _set_idempotency_created_at(
        self,
        *,
        operation_id: str,
        created_at: datetime,
    ) -> None:
        with DatabaseManager.get_instance().get_session() as session:
            record = session.execute(
                select(PortfolioIdempotencyRecord).where(
                    PortfolioIdempotencyRecord.client_operation_id == operation_id
                )
            ).scalar_one()
            record.created_at = created_at
            session.commit()

    def _seed_cash_operation(self, operation_id: str) -> tuple[dict, dict]:
        request = {
            "account_id": self.account_id,
            "event_date": date(2026, 1, 1),
            "direction": "in",
            "amount": 1000,
            "operation_id": operation_id,
        }
        return request, self.service.record_cash_ledger(**request)

    def _table_count(self, model: type) -> int:
        with DatabaseManager.get_instance().get_session() as session:
            return int(session.execute(select(func.count()).select_from(model)).scalar_one())

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

    def test_trade_operation_id_rejects_different_payload(self) -> None:
        operation_id = "trade-conflict-1"
        request = {
            "account_id": self.account_id,
            "symbol": "600519",
            "trade_date": date(2026, 1, 2),
            "side": "buy",
            "quantity": 10,
            "price": 100,
            "market": "cn",
            "currency": "CNY",
            "operation_id": operation_id,
        }
        self.service.record_trade(**request)

        with self.assertRaisesRegex(
            PortfolioIdempotencyConflictError,
            rf"^operation_id already used for a different request: {operation_id}$",
        ):
            PortfolioService().record_trade(**{**request, "price": 101})

        self.assertEqual(
            self.service.list_trade_events(account_id=self.account_id)["total"],
            1,
        )

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

    def test_same_operation_id_is_isolated_between_mutation_types(self) -> None:
        cash_result = self.service.record_cash_ledger(
            account_id=self.account_id,
            event_date=date(2026, 1, 1),
            direction="in",
            amount=1000,
            operation_id="cross-type-operation-1",
        )

        action_result = self.service.record_corporate_action(
            account_id=self.account_id,
            symbol="600519",
            effective_date=date(2026, 1, 3),
            action_type="cash_dividend",
            cash_dividend_per_share=1,
            operation_id="cross-type-operation-1",
        )

        self.assertEqual(cash_result, {"id": 1})
        self.assertEqual(action_result, {"id": 1})
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            1,
        )
        self.assertEqual(
            self.service.list_corporate_action_events(account_id=self.account_id)["total"],
            1,
        )

    def test_same_operation_id_is_isolated_between_accounts_and_owners(self) -> None:
        second_account_id = self.service.create_account(
            name="Secondary",
            broker="Demo",
            market="cn",
            base_currency="CNY",
            owner_id="owner-b",
        )["id"]
        self.service.update_account(self.account_id, owner_id="owner-a")

        first = self.service.record_cash_ledger(
            account_id=self.account_id,
            event_date=date(2026, 1, 1),
            direction="in",
            amount=1000,
            operation_id="cross-account-operation-1",
        )
        second = self.service.record_cash_ledger(
            account_id=second_account_id,
            event_date=date(2026, 1, 1),
            direction="in",
            amount=1000,
            operation_id="cross-account-operation-1",
        )

        self.assertNotEqual(first, second)
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            1,
        )
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=second_account_id)["total"],
            1,
        )
        with DatabaseManager.get_instance().get_session() as session:
            records = session.execute(
                select(PortfolioIdempotencyRecord).where(
                    PortfolioIdempotencyRecord.client_operation_id
                    == "cross-account-operation-1"
                )
            ).scalars().all()
        self.assertEqual(
            {(record.scope_account_id, record.scope_owner_id) for record in records},
            {(self.account_id, "owner-a"), (second_account_id, "owner-b")},
        )

    def test_same_operation_id_is_isolated_after_owner_transfer(self) -> None:
        self.service.update_account(self.account_id, owner_id="owner-before")
        first = self.service.record_cash_ledger(
            account_id=self.account_id,
            event_date=date(2026, 1, 1),
            direction="in",
            amount=1000,
            operation_id="owner-transfer-operation-1",
        )
        self.service.update_account(self.account_id, owner_id="owner-after")

        second = self.service.record_cash_ledger(
            account_id=self.account_id,
            event_date=date(2026, 1, 1),
            direction="in",
            amount=1000,
            operation_id="owner-transfer-operation-1",
        )

        self.assertNotEqual(first, second)
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            2,
        )

    def test_expired_operation_id_can_be_reused_and_replaces_stale_record(self) -> None:
        first = self.service.record_cash_ledger(
            account_id=self.account_id,
            event_date=date(2026, 1, 1),
            direction="in",
            amount=1000,
            operation_id="expired-operation-1",
        )
        self._age_idempotency_records()

        second = PortfolioService().record_cash_ledger(
            account_id=self.account_id,
            event_date=date(2026, 1, 2),
            direction="in",
            amount=2000,
            operation_id="expired-operation-1",
        )

        self.assertNotEqual(first, second)
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            2,
        )
        self.assertEqual(self._table_count(PortfolioIdempotencyRecord), 1)

    def test_replay_window_includes_record_just_inside_cutoff(self) -> None:
        fixed_now = datetime(2026, 7, 16, 12, 0, 0)
        request, first = self._seed_cash_operation("window-just-inside-1")
        self._set_idempotency_created_at(
            operation_id=request["operation_id"],
            created_at=fixed_now - timedelta(days=7) + timedelta(microseconds=1),
        )

        replay = PortfolioService(
            repo=self.service.repo,
            now_provider=lambda: fixed_now,
        ).record_cash_ledger(**request)

        self.assertEqual(replay, first)
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            1,
        )

    def test_replay_window_includes_record_at_exact_cutoff(self) -> None:
        fixed_now = datetime(2026, 7, 16, 12, 0, 0)
        request, first = self._seed_cash_operation("window-exact-cutoff-1")
        self._set_idempotency_created_at(
            operation_id=request["operation_id"],
            created_at=fixed_now - timedelta(days=7),
        )

        replay = PortfolioService(
            repo=self.service.repo,
            now_provider=lambda: fixed_now,
        ).record_cash_ledger(**request)

        self.assertEqual(replay, first)
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            1,
        )

    def test_replay_window_expires_record_just_outside_cutoff(self) -> None:
        fixed_now = datetime(2026, 7, 16, 12, 0, 0)
        request, first = self._seed_cash_operation("window-just-outside-1")
        self._set_idempotency_created_at(
            operation_id=request["operation_id"],
            created_at=fixed_now - timedelta(days=7) - timedelta(microseconds=1),
        )

        second = PortfolioService(
            repo=self.service.repo,
            now_provider=lambda: fixed_now,
        ).record_cash_ledger(**request)

        self.assertNotEqual(second, first)
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            2,
        )
        self.assertEqual(self._table_count(PortfolioIdempotencyRecord), 1)

    def test_three_day_override_drives_runtime_cleanup(self) -> None:
        fixed_now = datetime(2026, 7, 16, 12, 0, 0)
        request, first = self._seed_cash_operation("window-override-1")
        self._set_idempotency_created_at(
            operation_id=request["operation_id"],
            created_at=fixed_now - timedelta(days=4),
        )
        os.environ["PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS"] = "3"
        Config.reset_instance()
        try:
            second = PortfolioService(
                repo=self.service.repo,
                now_provider=lambda: fixed_now,
            ).record_cash_ledger(**request)
        finally:
            os.environ.pop("PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS", None)
            Config.reset_instance()

        self.assertNotEqual(second, first)
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            2,
        )
        self.assertEqual(self._table_count(PortfolioIdempotencyRecord), 1)

    def test_retained_trigger_rolls_back_simulated_baseline_duplicate(self) -> None:
        operation_id = "rollback-trigger-guard-1"
        _request, _first = self._seed_cash_operation(operation_id)

        with self.assertRaises(IntegrityError):
            with self.service.repo.portfolio_write_session() as session:
                scoped_record = session.execute(
                    select(PortfolioIdempotencyRecord).where(
                        PortfolioIdempotencyRecord.client_operation_id == operation_id
                    )
                ).scalar_one()
                duplicate = self.service.repo.add_cash_ledger_in_session(
                    session=session,
                    account_id=self.account_id,
                    event_date=date(2026, 1, 1),
                    direction="in",
                    amount=1000,
                    currency="CNY",
                    note=None,
                )
                session.add(
                    PortfolioIdempotencyRecord(
                        operation_id=operation_id,
                        operation_type=scoped_record.operation_type,
                        request_hash=scoped_record.request_hash,
                        response_json=json.dumps({"id": int(duplicate.id)}),
                        created_at=datetime.now(),
                    )
                )
                session.flush()

        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            1,
        )
        self.assertEqual(self._table_count(PortfolioIdempotencyRecord), 1)

    def test_persistent_guard_trigger_blocks_conflicting_legacy_insert(self) -> None:
        operation_id = "rollback-reupgrade-1"
        request, first = self._seed_cash_operation(operation_id)

        with DatabaseManager.get_instance().get_session() as session:
            scoped_record = session.execute(
                select(PortfolioIdempotencyRecord).where(
                    PortfolioIdempotencyRecord.client_operation_id == operation_id
                )
            ).scalar_one()
            operation_type = scoped_record.operation_type
            request_hash = scoped_record.request_hash

        # The migration-created guard trigger persists as a database object, so a
        # reverted runtime that writes a raw legacy key duplicating the scoped
        # operation is blocked at the database itself, without any self-healing
        # startup DDL re-creating the trigger.
        with self.assertRaises(IntegrityError):
            with DatabaseManager.get_instance().get_session() as session:
                session.add(
                    PortfolioIdempotencyRecord(
                        operation_id=operation_id,
                        operation_type=operation_type,
                        request_hash=request_hash,
                        response_json=json.dumps({"id": 999}),
                        created_at=datetime.now(),
                    )
                )
                session.commit()

        # A non-conflicting raw legacy key is accepted and stays unscoped.
        with DatabaseManager.get_instance().get_session() as session:
            session.add(
                PortfolioIdempotencyRecord(
                    operation_id="unrelated-legacy-key",
                    operation_type=operation_type,
                    request_hash=request_hash,
                    response_json=json.dumps({"id": 1}),
                    created_at=datetime.now(),
                )
            )
            session.commit()

        # Idempotency replay still returns the original response.
        replay = self.service.record_cash_ledger(**request)
        self.assertEqual(replay, first)

        with DatabaseManager.get_instance().get_session() as session:
            scoped = session.execute(
                select(PortfolioIdempotencyRecord).where(
                    PortfolioIdempotencyRecord.client_operation_id == operation_id
                )
            ).scalar_one()
            raw = session.execute(
                select(PortfolioIdempotencyRecord).where(
                    PortfolioIdempotencyRecord.operation_id == "unrelated-legacy-key"
                )
            ).scalar_one()
            trigger_name = session.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'trigger' AND name = :trigger_name"
                ),
                {"trigger_name": PORTFOLIO_LEGACY_IDEMPOTENCY_GUARD_TRIGGER},
            ).scalar_one_or_none()

        self.assertIsNotNone(scoped.scope_key)
        self.assertIsNone(raw.scope_key)
        self.assertIsNone(raw.scope_account_id)
        self.assertIsNone(raw.scope_owner_id)
        self.assertEqual(trigger_name, PORTFOLIO_LEGACY_IDEMPOTENCY_GUARD_TRIGGER)

    def test_lazy_cleanup_preserves_ledger_events_and_snapshots(self) -> None:
        self.service.record_trade(
            account_id=self.account_id,
            symbol="600519",
            trade_date=date(2026, 1, 2),
            side="buy",
            quantity=10,
            price=100,
            operation_id="cleanup-trade-1",
        )
        self.service.record_cash_ledger(
            account_id=self.account_id,
            event_date=date(2026, 1, 1),
            direction="in",
            amount=5000,
            operation_id="cleanup-cash-1",
        )
        self.service.record_corporate_action(
            account_id=self.account_id,
            symbol="600519",
            effective_date=date(2026, 1, 3),
            action_type="cash_dividend",
            cash_dividend_per_share=1,
            operation_id="cleanup-action-1",
        )
        self.service.get_portfolio_snapshot(
            account_id=self.account_id,
            as_of=date(2026, 1, 5),
            include_realtime=False,
        )
        self._age_idempotency_records()

        self.service.record_cash_ledger(
            account_id=self.account_id,
            event_date=date(2026, 2, 1),
            direction="in",
            amount=100,
            operation_id="cleanup-trigger-1",
        )

        self.assertEqual(self._table_count(PortfolioTrade), 1)
        self.assertEqual(self._table_count(PortfolioCashLedger), 2)
        self.assertEqual(self._table_count(PortfolioCorporateAction), 1)
        self.assertEqual(self._table_count(PortfolioDailySnapshot), 1)
        self.assertEqual(self._table_count(PortfolioIdempotencyRecord), 1)

    def test_concurrent_expired_reuse_and_cleanup_writes_once(self) -> None:
        self.service.record_cash_ledger(
            account_id=self.account_id,
            event_date=date(2026, 1, 1),
            direction="in",
            amount=1000,
            operation_id="cleanup-race-1",
        )
        self._age_idempotency_records()
        barrier = threading.Barrier(3)
        responses: list[dict] = []
        errors: list[Exception] = []

        def _worker() -> None:
            barrier.wait()
            try:
                responses.append(
                    PortfolioService().record_cash_ledger(
                        account_id=self.account_id,
                        event_date=date(2026, 1, 2),
                        direction="in",
                        amount=2000,
                        operation_id="cleanup-race-1",
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
            2,
        )
        self.assertEqual(self._table_count(PortfolioIdempotencyRecord), 1)

    def test_replay_window_defaults_to_seven_days(self) -> None:
        self.assertEqual(Config.get_instance().portfolio_idempotency_replay_window_days, 7)

    def test_replay_window_accepts_existing_config_override(self) -> None:
        os.environ["PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS"] = "3"
        Config.reset_instance()
        try:
            self.assertEqual(Config.get_instance().portfolio_idempotency_replay_window_days, 3)
        finally:
            os.environ.pop("PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS", None)
            Config.reset_instance()

    def test_legacy_unscoped_row_does_not_replay_without_a_proven_scope(self) -> None:
        request = {
            "account_id": self.account_id,
            "event_date": date(2026, 1, 1),
            "direction": "in",
            "amount": 1000,
            "operation_id": "legacy-unscoped-operation-1",
        }
        first = self.service.record_cash_ledger(**request)
        with DatabaseManager.get_instance().get_session() as session:
            record = session.execute(
                select(PortfolioIdempotencyRecord).where(
                    PortfolioIdempotencyRecord.client_operation_id
                    == "legacy-unscoped-operation-1"
                )
            ).scalar_one()
            record.operation_id = "legacy-unscoped-operation-1"
            record.client_operation_id = None
            record.scope_key = None
            record.scope_account_id = None
            record.scope_owner_id = None
            session.commit()

        second = PortfolioService().record_cash_ledger(**request)

        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(
            self.service.list_cash_ledger_events(account_id=self.account_id)["total"],
            2,
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

    def test_corporate_action_operation_id_rejects_different_payload(self) -> None:
        operation_id = "corporate-conflict-1"
        request = {
            "account_id": self.account_id,
            "symbol": "600519",
            "effective_date": date(2026, 1, 3),
            "action_type": "cash_dividend",
            "cash_dividend_per_share": 1,
            "operation_id": operation_id,
        }
        self.service.record_corporate_action(**request)

        with self.assertRaisesRegex(
            PortfolioIdempotencyConflictError,
            rf"^operation_id already used for a different request: {operation_id}$",
        ):
            PortfolioService().record_corporate_action(
                **{**request, "cash_dividend_per_share": 2}
            )

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

    def test_openapi_documents_idempotency_scope_and_replay_window(self) -> None:
        schema = self.client.get("/openapi.json").json()
        operation_schema = schema["components"]["schemas"][
            "PortfolioCashLedgerCreateRequest"
        ]["properties"]["operation_id"]
        header_parameter = next(
            parameter
            for parameter in schema["paths"]["/api/v1/portfolio/cash-ledger"]["post"][
                "parameters"
            ]
            if parameter["name"] == "Idempotency-Key"
        )

        for description in (
            operation_schema["description"],
            header_parameter["description"],
        ):
            self.assertIn("operation type", description)
            self.assertIn("account owner", description)
            self.assertIn("PORTFOLIO_IDEMPOTENCY_REPLAY_WINDOW_DAYS", description)


class PortfolioIdempotencyMigrationTestCase(unittest.TestCase):
    def test_legacy_table_upgrade_is_additive_and_leaves_scope_unproven(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(temp_dir.name) / "legacy_portfolio_idempotency.db"
        try:
            with sqlite3.connect(db_path) as connection:
                connection.executescript(
                    MIGRATION_FIXTURE.read_text(encoding="utf-8")
                )
                connection.execute("DROP TABLE portfolio_idempotency_records")
                connection.execute(
                    """CREATE TABLE portfolio_idempotency_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_id VARCHAR(128) NOT NULL UNIQUE,
                    operation_type VARCHAR(32) NOT NULL,
                    request_hash VARCHAR(64) NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at DATETIME NOT NULL
                    )"""
                )
                connection.execute(
                    "INSERT INTO portfolio_accounts "
                    "(id, owner_id, name, market, base_currency, is_active) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (42, "legacy-owner", "Legacy", "cn", "CNY", 1),
                )
                connection.execute(
                    "INSERT INTO portfolio_cash_ledger "
                    "(id, account_id, event_date, direction, amount, currency) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (1, 42, "2026-01-01", "in", 100.0, "CNY"),
                )
                connection.execute(
                    """INSERT INTO portfolio_idempotency_records (
                    operation_id, operation_type, request_hash, response_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)""",
                    (
                        "legacy-schema-operation-1",
                        "cash_ledger.create",
                        "a" * 64,
                        '{"id":1}',
                        datetime.now().isoformat(sep=" "),
                    ),
                )

            DatabaseManager.reset_instance()
            Config.reset_instance()
            DatabaseManager(db_url=f"sqlite:///{db_path}")

            with sqlite3.connect(db_path) as connection:
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(portfolio_idempotency_records)"
                    ).fetchall()
                }
                row = connection.execute(
                    """SELECT operation_id, client_operation_id, scope_key,
                    scope_account_id, scope_owner_id
                    FROM portfolio_idempotency_records"""
                ).fetchone()

            self.assertTrue(
                {
                    "client_operation_id",
                    "scope_key",
                    "scope_account_id",
                    "scope_owner_id",
                }.issubset(columns)
            )
            self.assertEqual(row[0], "legacy-schema-operation-1")
            self.assertEqual(row[1], "legacy-schema-operation-1")
            self.assertIsNone(row[2])
            self.assertEqual(row[3:], (None, None))
        finally:
            DatabaseManager.reset_instance()
            Config.reset_instance()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
