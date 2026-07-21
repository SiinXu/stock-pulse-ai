# -*- coding: utf-8 -*-
"""
===================================
A-shares Watchlist Analysis System - News intelligence storage unit test
===================================

Responsibilities:
1. Verification of saving and deduplication logic for news intelligence
2. Fallback deduplication key in case of no URL
"""

import os
import sqlite3
import tempfile
import unittest

from datetime import datetime
from unittest.mock import patch

from sqlalchemy.exc import OperationalError

from src.config import Config
from src.storage import DatabaseManager, NewsIntel
from src.search_service import SearchResponse, SearchResult


class NewsIntelStorageTestCase(unittest.TestCase):
    """News intelligence storage test"""

    def setUp(self) -> None:
        """Initialize independent databases for each use case"""
        self._temp_dir = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._temp_dir.name, "test_news_intel.db")
        os.environ["DATABASE_PATH"] = self._db_path

        # Reset configuration and database singleton, ensure using temporary library
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        """Clean resources"""
        DatabaseManager.reset_instance()
        self._temp_dir.cleanup()

    def _build_response(self, results) -> SearchResponse:
        """Construct a quick function for SearchResponse"""
        return SearchResponse(
            query="贵州茅台 最新消息",
            results=results,
            provider="Bocha",
            success=True,
        )

    def test_save_news_intel_with_url_dedup(self) -> None:
        """URL deduplication, only keep one record"""
        result = SearchResult(
            title="茅台发布新产品",
            snippet="公司发布新品...",
            url="https://news.example.com/a",
            source="example.com",
            published_date="2025-01-02"
        )
        response = self._build_response([result])

        query_context = {
            "query_id": "task_001",
            "query_source": "bot",
            "requester_platform": "feishu",
            "requester_user_id": "u_123",
            "requester_user_name": "测试用户",
            "requester_chat_id": "c_456",
            "requester_message_id": "m_789",
            "requester_query": "/analyze 600519",
        }

        saved_first = self.db.save_news_intel(
            code="600519",
            name="贵州茅台",
            dimension="latest_news",
            query=response.query,
            response=response,
            query_context=query_context
        )
        saved_second = self.db.save_news_intel(
            code="600519",
            name="贵州茅台",
            dimension="latest_news",
            query=response.query,
            response=response,
            query_context=query_context
        )

        self.assertEqual(saved_first, 1)
        self.assertEqual(saved_second, 0)

        with self.db.get_session() as session:
            total = session.query(NewsIntel).count()
            row = session.query(NewsIntel).first()
        self.assertEqual(total, 1)
        if row is None:
            self.fail("未找到保存的新闻记录")
        self.assertEqual(row.query_id, "task_001")
        self.assertEqual(row.requester_user_name, "测试用户")

    def test_save_news_intel_without_url_fallback_key(self) -> None:
        """Use the fallback-key deduplication when there is no URL"""
        result = SearchResult(
            title="茅台业绩预告",
            snippet="业绩大幅增长...",
            url="",
            source="example.com",
            published_date="2025-01-03"
        )
        response = self._build_response([result])

        saved_first = self.db.save_news_intel(
            code="600519",
            name="贵州茅台",
            dimension="earnings",
            query=response.query,
            response=response
        )
        saved_second = self.db.save_news_intel(
            code="600519",
            name="贵州茅台",
            dimension="earnings",
            query=response.query,
            response=response
        )

        self.assertEqual(saved_first, 1)
        self.assertEqual(saved_second, 0)

        with self.db.get_session() as session:
            row = session.query(NewsIntel).first()
            if row is None:
                self.fail("未找到保存的新闻记录")
            self.assertTrue(row.url.startswith("no-url:"))

    def test_get_recent_news(self) -> None:
        """Can query latest news by time range."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = SearchResult(
            title="茅台股价震荡",
            snippet="盘中波动较大...",
            url="https://news.example.com/b",
            source="example.com",
            published_date=now
        )
        response = self._build_response([result])

        self.db.save_news_intel(
            code="600519",
            name="贵州茅台",
            dimension="market_analysis",
            query=response.query,
            response=response
        )

        recent_news = self.db.get_recent_news(code="600519", days=7, limit=10)
        self.assertEqual(len(recent_news), 1)
        self.assertEqual(recent_news[0].title, "茅台股价震荡")

    def test_save_news_intel_retries_on_sqlite_locked_execute(self) -> None:
        result = SearchResult(
            title="茅台锁竞争重试",
            snippet="模拟 SQLite locked...",
            url="https://news.example.com/retry",
            source="example.com",
            published_date="2025-01-05",
        )
        response = self._build_response([result])

        first_session = self.db.get_session()
        second_session = self.db.get_session()
        stmt_exc = OperationalError(
            "COMMIT",
            None,
            sqlite3.OperationalError("database is locked"),
        )

        with patch.object(self.db, "get_session", side_effect=[first_session, second_session]):
            with patch.object(first_session, "execute", side_effect=stmt_exc):
                with patch("src.storage.time.sleep") as mock_sleep:
                    saved_count = self.db.save_news_intel(
                        code="600519",
                        name="贵州茅台",
                        dimension="latest_news",
                        query=response.query,
                        response=response,
                    )

        self.assertEqual(saved_count, 1)
        self.assertEqual(mock_sleep.call_count, 1)
        self.assertAlmostEqual(mock_sleep.call_args.args[0], self.db._sqlite_write_retry_base_delay, places=6)

        with self.db.get_session() as session:
            total = session.query(NewsIntel).count()
        self.assertEqual(total, 1)


if __name__ == "__main__":
    unittest.main()
