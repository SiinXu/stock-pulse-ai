# -*- coding: utf-8 -*-
"""Tests for event calendar model, certainty grades, and disabled fetch (issue #153)."""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest import TestCase
from unittest.mock import MagicMock

from src.services.event_calendar_fetcher import EventCalendarFetcher
from src.services.event_calendar_models import (
    CERTAINTY_LEVELS,
    EVENT_TYPES,
    CalendarEvent,
    normalize_certainty,
    normalize_event_type,
)
from src.services.event_calendar_service import (
    EventCalendarService,
    is_event_calendar_enabled,
    market_coverage_table,
)


class EventCalendarModelTests(TestCase):
    def test_certainty_levels_are_distinct_and_required(self) -> None:
        self.assertEqual(
            set(CERTAINTY_LEVELS),
            {"confirmed", "scheduled", "estimated"},
        )
        for level in CERTAINTY_LEVELS:
            self.assertEqual(normalize_certainty(level), level)
        with self.assertRaises(ValueError):
            normalize_certainty("maybe")
        with self.assertRaises(ValueError):
            CalendarEvent(
                event_id="x",
                event_type="earnings",
                event_date=date(2026, 8, 10),
                certainty="tentative",  # not a valid grade
                symbol="600519",
                title="test",
            )

    def test_event_types_and_serialization_preserve_certainty(self) -> None:
        self.assertIn("earnings", EVENT_TYPES)
        event = CalendarEvent(
            event_id="earnings:cn:600519:20260630:2026-08-20",
            event_type="earnings",
            event_date=date(2026, 8, 20),
            certainty="scheduled",
            symbol="600519",
            title="600519 earnings disclosure",
            market="CN",
            source="test",
            fetched_at=datetime(2026, 8, 9, 12, 0, 0),
        )
        payload = event.to_dict()
        self.assertEqual(payload["certainty"], "scheduled")
        self.assertEqual(payload["event_date"], "2026-08-20")
        self.assertEqual(payload["fetched_at"], "2026-08-09T12:00:00")
        self.assertNotEqual(payload["certainty"], "confirmed")

        confirmed = CalendarEvent(
            event_id="ex:1",
            event_type="ex_dividend",
            event_date=date(2026, 9, 1),
            certainty="confirmed",
            symbol="000001",
            title="ex-div",
        )
        estimated = CalendarEvent(
            event_id="macro:1",
            event_type="macro",
            event_date=date(2026, 9, 2),
            certainty="estimated",
            symbol="000001",
            title="macro",
        )
        grades = {
            event.certainty,
            confirmed.certainty,
            estimated.certainty,
        }
        self.assertEqual(grades, {"scheduled", "confirmed", "estimated"})

    def test_normalize_event_type_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            normalize_event_type("split")


class EventCalendarEnabledGateTests(TestCase):
    def test_default_disabled_env(self) -> None:
        self.assertFalse(is_event_calendar_enabled(env={}))
        self.assertFalse(
            is_event_calendar_enabled(env={"EVENT_CALENDAR_ENABLED": "false"})
        )
        self.assertTrue(
            is_event_calendar_enabled(env={"EVENT_CALENDAR_ENABLED": "true"})
        )

    def test_disabled_service_never_calls_fetcher(self) -> None:
        fetcher = MagicMock(spec=EventCalendarFetcher)
        config = SimpleNamespace(stock_list=["600519"], refresh_stock_list=lambda: None)
        portfolio = MagicMock()
        portfolio.get_portfolio_snapshot.return_value = {"accounts": []}
        service = EventCalendarService(
            fetcher=fetcher,
            portfolio_service=portfolio,
            config=config,
            enabled_override=False,
        )
        result = service.get_calendar(
            as_of=date(2026, 8, 9),
            date_from=date(2026, 8, 9),
            date_to=date(2026, 9, 9),
        )
        self.assertFalse(result["enabled"])
        self.assertFalse(result["fetch_attempted"])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["event_count"], 0)
        fetcher.fetch_events.assert_not_called()
        self.assertIn("EVENT_CALENDAR_ENABLED is false", result["coverage_notes"][0])

    def test_enabled_service_uses_fetcher_and_certainty(self) -> None:
        sample = CalendarEvent(
            event_id="earnings:cn:600519:20260630:2026-08-20",
            event_type="earnings",
            event_date=date(2026, 8, 20),
            certainty="scheduled",
            symbol="600519",
            title="600519 earnings",
            market="CN",
            source="fixture",
            fetched_at=datetime(2026, 8, 9, 8, 0, 0),
        )
        fetcher = MagicMock(spec=EventCalendarFetcher)
        fetcher.fetch_events.return_value = {
            "events": [sample],
            "fetched_at": datetime(2026, 8, 9, 8, 0, 0),
            "sources_attempted": ["fixture"],
            "errors": [],
            "coverage_notes": [],
        }
        config = SimpleNamespace(stock_list=["600519"], refresh_stock_list=lambda: None)
        portfolio = MagicMock()
        portfolio.get_portfolio_snapshot.return_value = {"accounts": []}
        service = EventCalendarService(
            fetcher=fetcher,
            portfolio_service=portfolio,
            config=config,
            enabled_override=True,
        )
        result = service.get_calendar(
            as_of=date(2026, 8, 9),
            date_from=date(2026, 8, 9),
            date_to=date(2026, 10, 9),
            include_impact=True,
            report_language="en",
        )
        self.assertTrue(result["enabled"])
        self.assertTrue(result["fetch_attempted"])
        self.assertTrue(result["reuses_build_impact_context"])
        self.assertEqual(result["event_count"], 1)
        event = result["events"][0]
        self.assertEqual(event["certainty"], "scheduled")
        self.assertNotEqual(event["certainty"], "confirmed")
        self.assertEqual(event["event_type"], "earnings")
        self.assertIsNotNone(event.get("impact_preview"))
        self.assertEqual(
            event["impact_preview"].get("source"),
            "event_alerts.build_impact_context",
        )
        fetcher.fetch_events.assert_called_once()

    def test_market_coverage_table_lists_gaps(self) -> None:
        rows = market_coverage_table()
        markets = {row["market"] for row in rows}
        self.assertIn("CN A-share", markets)
        self.assertIn("US", markets)
        self.assertIn("HK", markets)
        us = next(row for row in rows if row["market"] == "US")
        self.assertIn("not covered", us["earnings"])


class EventCalendarFetcherCertaintyTests(TestCase):
    def test_yysj_appointment_is_scheduled_actual_is_confirmed(self) -> None:
        def yysj_loader(period: str) -> List[Dict[str, Any]]:
            return [
                {
                    "股票代码": "600519",
                    "股票简称": "贵州茅台",
                    "首次预约时间": "2026-08-25",
                    "实际披露时间": "",
                },
                {
                    "股票代码": "000001",
                    "股票简称": "平安银行",
                    "首次预约时间": "2026-08-18",
                    "实际披露时间": "2026-08-18",
                },
            ]

        fetcher = EventCalendarFetcher(
            yysj_loader=yysj_loader,
            fhps_loader=lambda period: [],
            unlock_loader=lambda code: [],
            clock=lambda: datetime(2026, 8, 9, 10, 0, 0),
        )
        result = fetcher.fetch_events(
            ["600519", "000001"],
            date_from=date(2026, 8, 1),
            date_to=date(2026, 9, 30),
            event_types=["earnings"],
        )
        events = result["events"]
        by_symbol = {e.symbol: e for e in events}
        self.assertEqual(by_symbol["600519"].certainty, "scheduled")
        self.assertEqual(by_symbol["000001"].certainty, "confirmed")
        self.assertEqual(by_symbol["600519"].event_type, "earnings")

    def test_ex_dividend_and_unlock_are_confirmed(self) -> None:
        def fhps_loader(period: str) -> List[Dict[str, Any]]:
            return [
                {
                    "代码": "600519",
                    "名称": "贵州茅台",
                    "除权除息日": "2026-09-05",
                    "送转股份-送转总比例": "10派20",
                }
            ]

        def unlock_loader(code: str) -> List[Dict[str, Any]]:
            return [{"解禁时间": "2026-09-10", "解禁数量": 1000000}]

        fetcher = EventCalendarFetcher(
            yysj_loader=lambda period: [],
            fhps_loader=fhps_loader,
            unlock_loader=unlock_loader,
            clock=lambda: datetime(2026, 8, 9, 10, 0, 0),
        )
        result = fetcher.fetch_events(
            ["600519"],
            date_from=date(2026, 8, 1),
            date_to=date(2026, 9, 30),
            event_types=["ex_dividend", "unlock"],
        )
        types = {e.event_type: e for e in result["events"]}
        self.assertEqual(types["ex_dividend"].certainty, "confirmed")
        self.assertEqual(types["unlock"].certainty, "confirmed")
