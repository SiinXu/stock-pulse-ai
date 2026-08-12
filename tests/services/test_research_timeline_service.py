# -*- coding: utf-8 -*-
"""Tests for per-symbol research timeline aggregation."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from src.config import Config
from src.services.research_timeline_service import (
    ResearchTimelineService,
    ResearchTimelineValidationError,
)
from src.storage import (
    AnalysisHistory,
    ConversationMessage,
    DatabaseManager,
    DecisionSignalRecord,
)
import src.auth as auth


class ResearchTimelineServiceTestCase(unittest.TestCase):
    """Cursor merge of analysis / chat / signal / hypothesis for one symbol."""

    def setUp(self) -> None:
        auth._auth_enabled = False
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "research_timeline.db")
        self._original_env = {
            key: os.environ.get(key)
            for key in ("ENV_FILE", "DATABASE_PATH")
        }
        self._env_path = os.path.join(self._temp_dir.name, ".env")
        with open(self._env_path, "w", encoding="utf-8") as env_file:
            env_file.write("STOCK_LIST=600519\n")
        os.environ["ENV_FILE"] = self._env_path
        os.environ["DATABASE_PATH"] = self._db_path
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()
        self.service = ResearchTimelineService(self.db)

    def tearDown(self) -> None:
        Config._instance = None
        DatabaseManager.reset_instance()
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._temp_dir.cleanup()

    def _add_analysis(
        self,
        *,
        code: str = "600519",
        created_at: Optional[datetime] = None,
        advice: str = "持有",
        trend: str = "看多",
        summary: str = "基本面稳健",
        sentiment: int = 72,
        query_id: str = "q1",
    ) -> int:
        with self.db.session_scope() as session:
            row = AnalysisHistory(
                query_id=query_id,
                code=code,
                name="贵州茅台",
                report_type="detailed",
                sentiment_score=sentiment,
                operation_advice=advice,
                trend_prediction=trend,
                analysis_summary=summary,
                created_at=created_at or datetime.now(),
            )
            session.add(row)
            session.flush()
            return int(row.id)

    def _add_chat(
        self,
        *,
        session_id: str = "sess-1",
        content: str = "How is 600519 looking?",
        stock_code: str = "600519",
        turn_id: Optional[str] = "turn-1",
        created_at: Optional[datetime] = None,
        agent_mode: Optional[str] = None,
    ) -> int:
        context: Dict[str, Any] = {"stock_code": stock_code}
        if agent_mode:
            context["agent_mode"] = agent_mode
        with self.db.session_scope() as session:
            row = ConversationMessage(
                session_id=session_id,
                role="user",
                content=content,
                turn_id=turn_id,
                context_json=json.dumps(context, ensure_ascii=False),
                created_at=created_at or datetime.now(),
            )
            session.add(row)
            session.flush()
            return int(row.id)

    def _add_signal(
        self,
        *,
        stock_code: str = "600519",
        action: str = "hold",
        action_label: str = "Hold",
        confidence: float = 0.8,
        status: str = "active",
        created_at: Optional[datetime] = None,
        reason: str = "Stable demand",
    ) -> int:
        with self.db.session_scope() as session:
            row = DecisionSignalRecord(
                stock_code=stock_code,
                stock_name="贵州茅台",
                market="cn",
                source_type="analysis",
                trigger_source="api",
                action=action,
                action_label=action_label,
                confidence=confidence,
                reason=reason,
                status=status,
                plan_quality="unknown",
                created_at=created_at or datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=created_at or datetime.now(timezone.utc).replace(tzinfo=None),
            )
            session.add(row)
            session.flush()
            return int(row.id)

    def test_empty_symbol_is_honest_with_hypothesis_unavailable(self) -> None:
        page = self.service.list_timeline("600519", limit=10)
        self.assertEqual(page.stock_code, "600519")
        self.assertEqual(page.items, [])
        self.assertFalse(page.has_more)
        self.assertIsNone(page.next_cursor)
        self.assertEqual(page.sources["analysis_run"], "empty")
        self.assertEqual(page.sources["chat"], "empty")
        self.assertEqual(page.sources["signal"], "empty")
        self.assertEqual(page.sources["hypothesis"], "unavailable")

    def test_rejects_invalid_stock_code(self) -> None:
        with self.assertRaises(ResearchTimelineValidationError) as raised:
            self.service.list_timeline("!!!")
        self.assertEqual(raised.exception.error_code, "invalid_stock_code")

    def test_multi_day_nodes_are_time_ordered_with_deep_links(self) -> None:
        t0 = datetime(2026, 8, 1, 10, 0, 0)
        t1 = datetime(2026, 8, 2, 11, 0, 0)
        t2 = datetime(2026, 8, 3, 12, 0, 0)
        analysis_id = self._add_analysis(
            created_at=t0,
            advice="买入",
            trend="看多",
            sentiment=80,
            query_id="q-day1",
        )
        chat_id = self._add_chat(
            created_at=t1,
            content="Follow-up on valuation?",
            turn_id="turn-day2",
            agent_mode="research",
        )
        signal_id = self._add_signal(created_at=t2, action="buy", action_label="Buy")

        page = self.service.list_timeline("600519", limit=10)
        self.assertEqual(len(page.items), 3)
        kinds = [item.kind for item in page.items]
        self.assertEqual(kinds, ["signal", "chat", "analysis_run"])

        signal_node = page.items[0]
        self.assertEqual(signal_node.link["type"], "decision_signal")
        self.assertEqual(signal_node.link["signal_id"], signal_id)
        self.assertEqual(signal_node.direction, "Buy")

        chat_node = page.items[1]
        self.assertEqual(chat_node.link["type"], "chat_session")
        self.assertEqual(chat_node.link["message_id"], chat_id)
        self.assertEqual(chat_node.link["turn_id"], "turn-day2")
        self.assertEqual(chat_node.title, "Deep research chat")

        analysis_node = page.items[2]
        self.assertEqual(analysis_node.link["type"], "analysis_history")
        self.assertEqual(analysis_node.link["record_id"], analysis_id)
        self.assertEqual(analysis_node.direction, "看多")
        self.assertAlmostEqual(analysis_node.confidence or 0.0, 0.8, places=3)

        other = self.service.list_timeline("AAPL", limit=10)
        self.assertEqual(other.items, [])

    def test_cursor_pagination_does_not_require_full_load(self) -> None:
        base = datetime(2026, 7, 1, 9, 0, 0)
        for index in range(5):
            self._add_analysis(
                created_at=base + timedelta(days=index),
                query_id=f"q-{index}",
                advice=f"run-{index}",
                summary=f"summary-{index}",
            )

        first = self.service.list_timeline("600519", limit=2)
        self.assertEqual(len(first.items), 2)
        self.assertTrue(first.has_more)
        self.assertIsNotNone(first.next_cursor)
        self.assertEqual(first.items[0].meta.get("operation_advice"), "run-4")
        self.assertEqual(first.items[1].meta.get("operation_advice"), "run-3")

        second = self.service.list_timeline(
            "600519",
            limit=2,
            cursor=first.next_cursor,
        )
        self.assertEqual(len(second.items), 2)
        self.assertTrue(second.has_more)
        self.assertEqual(second.items[0].meta.get("operation_advice"), "run-2")
        self.assertEqual(second.items[1].meta.get("operation_advice"), "run-1")

        third = self.service.list_timeline(
            "600519",
            limit=2,
            cursor=second.next_cursor,
        )
        self.assertEqual(len(third.items), 1)
        self.assertFalse(third.has_more)
        self.assertIsNone(third.next_cursor)
        self.assertEqual(third.items[0].meta.get("operation_advice"), "run-0")

        seen = {item.id for item in first.items + second.items + third.items}
        self.assertEqual(len(seen), 5)

    def test_invalid_cursor_fails_closed(self) -> None:
        with self.assertRaises(ResearchTimelineValidationError) as raised:
            self.service.list_timeline("600519", cursor="not-a-cursor")
        self.assertEqual(raised.exception.error_code, "invalid_cursor")

    def test_kind_filter_limits_sources(self) -> None:
        self._add_analysis(query_id="only-analysis")
        self._add_chat(turn_id="only-chat")
        self._add_signal()

        page = self.service.list_timeline("600519", kinds=["analysis_run"], limit=10)
        self.assertEqual(len(page.items), 1)
        self.assertEqual(page.items[0].kind, "analysis_run")
        self.assertEqual(page.sources["analysis_run"], "ok")
        self.assertEqual(page.sources["chat"], "empty")
        self.assertEqual(page.sources["signal"], "empty")

    def test_chat_without_stock_context_is_excluded(self) -> None:
        with self.db.session_scope() as session:
            session.add(
                ConversationMessage(
                    session_id="sess-plain",
                    role="user",
                    content="general question",
                    context_json=None,
                    created_at=datetime.now(),
                )
            )
            session.flush()
        page = self.service.list_timeline("600519", kinds=["chat"], limit=10)
        self.assertEqual(page.items, [])
        self.assertEqual(page.sources["chat"], "empty")


    def test_exact_page_size_does_not_false_positive_has_more(self) -> None:
        """A source that returns exactly `limit` rows and is exhausted must not claim more."""
        base = datetime(2026, 6, 1, 9, 0, 0)
        for index in range(2):
            self._add_analysis(
                created_at=base + timedelta(days=index),
                query_id=f"exact-{index}",
                advice=f"exact-{index}",
            )
        page = self.service.list_timeline("600519", limit=2)
        self.assertEqual(len(page.items), 2)
        self.assertFalse(page.has_more)
        self.assertIsNone(page.next_cursor)


if __name__ == "__main__":
    unittest.main()
