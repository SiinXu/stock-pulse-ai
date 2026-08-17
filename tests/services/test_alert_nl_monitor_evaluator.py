# -*- coding: utf-8 -*-
"""NL monitor compiler -> real evaluator/worker contract (issue #1133)."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd

from src.config import Config
from src.notification import ChannelAttemptResult, NotificationDispatchResult
from src.services.alert_rule_nl_compiler import compile_alert_rule_nl
from src.services.alert_service import AlertService
from src.services.alert_worker import AlertWorker
from src.storage import DatabaseManager


class AlertNlMonitorEvaluatorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "alert_nl_monitor_test.db"
        self.env_path.write_text(
            "\n".join([
                "STOCK_LIST=AAPL",
                "GEMINI_API_KEY=test",
                "ADMIN_AUTH_ENABLED=false",
                f"DATABASE_PATH={self.db_path}",
            ])
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.service = AlertService()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def _config(self) -> SimpleNamespace:
        return SimpleNamespace(
            agent_event_monitor_enabled=True,
            agent_event_alert_rules_json="",
            agent_event_impact_context_enabled=False,
            trading_day_check_enabled=False,
            report_language="en",
            stock_list=["AAPL"],
            refresh_stock_list=lambda: None,
        )

    def _notifier(self) -> MagicMock:
        notifier = MagicMock()
        notifier.send_with_results.return_value = NotificationDispatchResult(
            dispatched=True,
            success=True,
            status="sent",
            channel_results=[
                ChannelAttemptResult(channel="custom", success=True, error_code=None, retryable=False),
            ],
        )
        return notifier

    def _persist_compiled(self, text: str) -> dict:
        compiled = compile_alert_rule_nl(text)
        self.assertEqual(compiled.outcome, "success")
        self.assertIsNotNone(compiled.rule)
        return self.service.create_rule(compiled.rule)

    def test_compiled_phrase_fires_through_real_evaluator_and_notifies(self) -> None:
        created = self._persist_compiled("AAPL price above 200")
        notifier = self._notifier()
        evaluate_calls = {"count": 0}
        original_evaluate = self.service._evaluate_rule

        async def _wrapped_evaluate(rule, monitor, daily_cache=None):
            evaluate_calls["count"] += 1
            return await original_evaluate(rule, monitor, daily_cache=daily_cache)

        worker = AlertWorker(
            config_provider=lambda: self._config(),
            service=self.service,
            notifier=notifier,
        )
        with patch.object(self.service, "_evaluate_rule", new=_wrapped_evaluate), patch(
            "src.agent.events.EventMonitor._get_realtime_quote",
            new=AsyncMock(return_value=SimpleNamespace(price=201.0)),
        ):
            stats = worker.run_once()

        self.assertEqual(evaluate_calls["count"], 1)
        self.assertEqual(stats["triggered"], 1)
        self.assertEqual(stats["notified"], 1)
        self.assertEqual(stats["paused"], 0)
        triggers = self.service.list_triggers(page_size=10, rule_id=created["id"])["items"]
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0]["status"], "triggered")
        self.assertEqual(triggers[0]["observed_value"], 201.0)
        self.assertEqual(triggers[0]["threshold"], 200.0)
        notifier.send_with_results.assert_called_once()
        self.assertEqual(notifier.send_with_results.call_args.kwargs["route_type"], "alert")

    def test_compiled_cooldown_is_enforced_by_real_worker(self) -> None:
        created = self._persist_compiled("AAPL price above 200 cooldown 1 hour")
        self.assertEqual(created["cooldown_policy"], {"cooldown_seconds": 3600})
        notifier = self._notifier()
        now = {"value": 1_000.0}
        worker = AlertWorker(
            config_provider=lambda: self._config(),
            service=self.service,
            notifier=notifier,
            now_provider=lambda: now["value"],
        )
        with patch(
            "src.agent.events.EventMonitor._get_realtime_quote",
            new=AsyncMock(return_value=SimpleNamespace(price=201.0)),
        ):
            first = worker.run_once()
            now["value"] += 30
            second = worker.run_once()

        self.assertEqual(first["triggered"], 1)
        self.assertEqual(first["notified"], 1)
        self.assertEqual(second["triggered"], 1)
        self.assertEqual(second["notified"], 0)
        self.assertEqual(second["cooldown_suppressed"], 1)
        self.assertEqual(notifier.send_with_results.call_count, 1)

    def test_provider_failure_pauses_rule_instead_of_notifying(self) -> None:
        created = self._persist_compiled("AAPL price above 200")
        notifier = self._notifier()
        worker = AlertWorker(
            config_provider=lambda: self._config(),
            service=self.service,
            notifier=notifier,
        )

        async def _raise(_monitor, _stock_code):
            raise RuntimeError("provider unavailable")

        with patch("src.agent.events.EventMonitor._get_realtime_quote", new=_raise):
            stats = worker.run_once()

        self.assertEqual(stats["failed"], 1)
        self.assertEqual(stats["paused"], 1)
        self.assertEqual(stats["notified"], 0)
        notifier.send_with_results.assert_not_called()
        paused = self.service.get_rule(created["id"])
        self.assertFalse(paused["enabled"])
        self.assertEqual(paused["notification_policy"]["paused_reason"], "data_failure")
        self.assertEqual(paused["notification_policy"]["paused_record_status"], "failed")

        second = worker.run_once()
        self.assertEqual(second["loaded"], 0)
        self.assertEqual(second["evaluated"], 0)
        notifier.send_with_results.assert_not_called()

    def test_skipped_missing_quote_does_not_pause_or_notify(self) -> None:
        created = self._persist_compiled("AAPL price above 200")
        notifier = self._notifier()
        worker = AlertWorker(
            config_provider=lambda: self._config(),
            service=self.service,
            notifier=notifier,
        )
        with patch(
            "src.agent.events.EventMonitor._get_realtime_quote",
            new=AsyncMock(return_value=None),
        ):
            stats = worker.run_once()

        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(stats["paused"], 0)
        self.assertEqual(stats["notified"], 0)
        notifier.send_with_results.assert_not_called()
        still_enabled = self.service.get_rule(created["id"])
        self.assertTrue(still_enabled["enabled"])

    def test_degraded_daily_data_does_not_pause_or_notify(self) -> None:
        created = self._persist_compiled("300750 成交量异动 2.5倍")
        notifier = self._notifier()
        manager = MagicMock()
        manager.get_daily_data.return_value = None

        async def _run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        worker = AlertWorker(
            config_provider=lambda: self._config(),
            service=self.service,
            notifier=notifier,
        )
        with patch("data_provider.DataFetcherManager", return_value=manager), patch(
            "src.services.alert_service.asyncio.to_thread",
            new=_run_inline,
        ):
            stats = worker.run_once()

        self.assertEqual(stats["degraded"], 1)
        self.assertEqual(stats["paused"], 0)
        self.assertEqual(stats["notified"], 0)
        notifier.send_with_results.assert_not_called()
        still_enabled = self.service.get_rule(created["id"])
        self.assertTrue(still_enabled["enabled"])
        self.assertEqual(still_enabled["alert_type"], "volume_spike")

    def test_compiled_rsi_short_history_stays_enabled(self) -> None:
        created = self._persist_compiled("AAPL RSI above 70")
        notifier = self._notifier()
        manager = MagicMock()
        manager.get_daily_data.return_value = (
            pd.DataFrame({
                "date": [date(2026, 5, 13), date(2026, 5, 14), date(2026, 5, 15)],
                "close": [10, 9, 12],
            }),
            "unit-test",
        )

        async def _run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        worker = AlertWorker(
            config_provider=lambda: self._config(),
            service=self.service,
            notifier=notifier,
        )
        with patch("data_provider.DataFetcherManager", return_value=manager), patch(
            "src.services.alert_service.asyncio.to_thread",
            new=_run_inline,
        ):
            stats = worker.run_once()

        self.assertEqual(stats["degraded"], 1)
        self.assertEqual(stats["paused"], 0)
        self.assertEqual(stats["notified"], 0)
        notifier.send_with_results.assert_not_called()
        still_enabled = self.service.get_rule(created["id"])
        self.assertTrue(still_enabled["enabled"])
        self.assertEqual(still_enabled["alert_type"], "rsi_threshold")
