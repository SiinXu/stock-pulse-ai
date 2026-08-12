# -*- coding: utf-8 -*-
"""Boundary tests for prediction resolve_after trading-calendar policy (#1109)."""

from __future__ import annotations

import json
import unittest
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from src.core import prediction_resolve_after as resolve_mod
from src.core import trading_calendar
from src.core.prediction_resolve_after import (
    AsOfPolicy,
    CalendarUnavailableError,
    CrossMarketMismatchError,
    InvalidHorizonError,
    UnsupportedMarketError,
    compute_resolve_after,
)


class _FakeCalendar:
    """Minimal exchange-calendars stand-in with early-close support."""

    def __init__(
        self,
        sessions,
        *,
        tz_name: str,
        close_time: time = time(15, 0),
        early_close_dates=None,
        early_close_time: time = time(13, 0),
    ):
        self._sessions = sorted(sessions)
        self._tz_name = tz_name
        self._close_time = close_time
        self._early_close_dates = set(early_close_dates or [])
        self._early_close_time = early_close_time
        self.early_closes = pd.DatetimeIndex(
            [pd.Timestamp(d) for d in sorted(self._early_close_dates)]
        )

    def is_session(self, check_date: date) -> bool:
        return check_date in self._sessions

    def date_to_session(self, check_date: date, direction: str = "previous") -> pd.Timestamp:
        if direction == "previous":
            candidates = [d for d in self._sessions if d <= check_date]
            if not candidates:
                raise ValueError(f"no previous session for {check_date}")
            return pd.Timestamp(candidates[-1])
        if direction == "next":
            candidates = [d for d in self._sessions if d >= check_date]
            if not candidates:
                raise ValueError(f"no next session for {check_date}")
            return pd.Timestamp(candidates[0])
        raise ValueError(f"unsupported direction: {direction}")

    def previous_session(self, session: pd.Timestamp) -> pd.Timestamp:
        session_date = session.date()
        index = self._sessions.index(session_date)
        if index == 0:
            raise ValueError("no previous session")
        return pd.Timestamp(self._sessions[index - 1])

    def session_offset(self, session: pd.Timestamp, offset: int) -> pd.Timestamp:
        session_date = session.date()
        index = self._sessions.index(session_date)
        target_index = index + offset
        if target_index < 0 or target_index >= len(self._sessions):
            raise ValueError("session offset out of range")
        return pd.Timestamp(self._sessions[target_index])

    def session_close(self, session: pd.Timestamp) -> pd.Timestamp:
        session_date = session.date()
        close_t = (
            self._early_close_time
            if session_date in self._early_close_dates
            else self._close_time
        )
        local_close = datetime.combine(
            session_date, close_t, tzinfo=ZoneInfo(self._tz_name)
        )
        return pd.Timestamp(local_close).tz_convert("UTC")


class ComputeResolveAfterUnitTestCase(unittest.TestCase):
    def test_cn_weekend_skips_to_next_sessions(self):
        """CN: Friday after close + 1d → Monday close (weekend skipped)."""
        sessions = [
            date(2026, 3, 26),  # Thu
            date(2026, 3, 27),  # Fri
            date(2026, 3, 30),  # Mon
            date(2026, 3, 31),  # Tue
        ]
        fake = _FakeCalendar(sessions, tz_name="Asia/Shanghai", close_time=time(15, 0))
        created = datetime(2026, 3, 27, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar, "xcals", SimpleNamespace(get_calendar=lambda _ex: fake), create=True
        ), patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar", lambda _ex: fake
        ):
            result = compute_resolve_after("cn", created, "1d")

        self.assertEqual(result.anchor_session, date(2026, 3, 27))
        self.assertEqual(result.target_session, date(2026, 3, 30))
        self.assertEqual(
            result.resolve_after,
            datetime(2026, 3, 30, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(
                timezone.utc
            ),
        )
        self.assertFalse(result.calendar_approx)
        self.assertEqual(result.as_of_policy, AsOfPolicy.TRADING_DAY_CLOSE.value)
        self.assertEqual(result.resolve_after.tzinfo, timezone.utc)

    def test_cn_national_day_holiday_skip(self):
        """CN: sessions jump across National Day holiday block."""
        sessions = [
            date(2025, 9, 30),
            date(2025, 10, 9),
            date(2025, 10, 10),
            date(2025, 10, 13),
        ]
        fake = _FakeCalendar(sessions, tz_name="Asia/Shanghai", close_time=time(15, 0))
        created = datetime(2025, 9, 30, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar, "xcals", SimpleNamespace(get_calendar=lambda _ex: fake), create=True
        ), patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar", lambda _ex: fake
        ):
            result = compute_resolve_after("cn", created, "2d")

        self.assertEqual(result.anchor_session, date(2025, 9, 30))
        self.assertEqual(result.target_session, date(2025, 10, 10))
        self.assertEqual(result.trading_sessions_forward, 2)

    def test_hk_christmas_holiday_and_weekend(self):
        """HK: Christmas closed; 1d after 24-Dec session lands on next open session."""
        sessions = [
            date(2024, 12, 23),
            date(2024, 12, 24),
            date(2024, 12, 27),
            date(2024, 12, 30),
        ]
        fake = _FakeCalendar(
            sessions,
            tz_name="Asia/Hong_Kong",
            close_time=time(16, 0),
            early_close_dates={date(2024, 12, 24)},
            early_close_time=time(12, 0),
        )
        created = datetime(2024, 12, 24, 13, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar, "xcals", SimpleNamespace(get_calendar=lambda _ex: fake), create=True
        ), patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar", lambda _ex: fake
        ):
            result = compute_resolve_after("hk", created, "1d")

        self.assertEqual(result.anchor_session, date(2024, 12, 24))
        self.assertEqual(result.target_session, date(2024, 12, 27))
        self.assertFalse(result.is_early_close)

    def test_hk_half_day_is_early_close_timestamp(self):
        """HK half-day: resolve_after uses early session_close, not regular 16:00."""
        sessions = [date(2024, 12, 23), date(2024, 12, 24)]
        fake = _FakeCalendar(
            sessions,
            tz_name="Asia/Hong_Kong",
            close_time=time(16, 0),
            early_close_dates={date(2024, 12, 24)},
            early_close_time=time(12, 0),
        )
        created = datetime(2024, 12, 23, 17, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar, "xcals", SimpleNamespace(get_calendar=lambda _ex: fake), create=True
        ), patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar", lambda _ex: fake
        ):
            result = compute_resolve_after("hk", created, "1d")

        self.assertEqual(result.target_session, date(2024, 12, 24))
        self.assertTrue(result.is_early_close)
        expected = datetime(2024, 12, 24, 12, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")).astimezone(
            timezone.utc
        )
        self.assertEqual(result.resolve_after, expected)

    def test_us_thanksgiving_holiday_skip(self):
        """US: Thanksgiving closed; Friday after is a session (often early close)."""
        sessions = [
            date(2024, 11, 26),
            date(2024, 11, 27),
            date(2024, 11, 29),
            date(2024, 12, 2),
        ]
        fake = _FakeCalendar(
            sessions,
            tz_name="America/New_York",
            close_time=time(16, 0),
            early_close_dates={date(2024, 11, 29)},
            early_close_time=time(13, 0),
        )
        created = datetime(2024, 11, 27, 17, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar, "xcals", SimpleNamespace(get_calendar=lambda _ex: fake), create=True
        ), patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar", lambda _ex: fake
        ):
            result = compute_resolve_after("us", created, "1d")

        self.assertEqual(result.anchor_session, date(2024, 11, 27))
        self.assertEqual(result.target_session, date(2024, 11, 29))
        self.assertTrue(result.is_early_close)
        self.assertEqual(
            result.resolve_after,
            datetime(2024, 11, 29, 13, 0, tzinfo=ZoneInfo("America/New_York")).astimezone(
                timezone.utc
            ),
        )

    def test_us_cross_timezone_created_at_utc(self):
        """US: UTC created_at maps through America/New_York session boundaries."""
        sessions = [
            date(2026, 3, 25),
            date(2026, 3, 26),
            date(2026, 3, 27),
        ]
        fake = _FakeCalendar(
            sessions, tz_name="America/New_York", close_time=time(16, 0)
        )
        # 2026-03-27 01:00 UTC = 2026-03-26 21:00 EDT (after close) → anchor 3/26
        created = datetime(2026, 3, 27, 1, 0, tzinfo=timezone.utc)

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar, "xcals", SimpleNamespace(get_calendar=lambda _ex: fake), create=True
        ), patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar", lambda _ex: fake
        ):
            result = compute_resolve_after("us", created, "1d")

        self.assertEqual(result.anchor_session, date(2026, 3, 26))
        self.assertEqual(result.target_session, date(2026, 3, 27))

    def test_us_dst_safe_utc_storage(self):
        """US spring-forward week: resolve_after is UTC-aware and matches local close."""
        sessions = [
            date(2026, 3, 6),
            date(2026, 3, 9),  # Monday after spring forward (US DST 2026-03-08)
            date(2026, 3, 10),
        ]
        fake = _FakeCalendar(
            sessions, tz_name="America/New_York", close_time=time(16, 0)
        )
        created = datetime(2026, 3, 6, 17, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar, "xcals", SimpleNamespace(get_calendar=lambda _ex: fake), create=True
        ), patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar", lambda _ex: fake
        ):
            result = compute_resolve_after("us", created, "1d")

        self.assertEqual(result.target_session, date(2026, 3, 9))
        self.assertIsNotNone(result.resolve_after.tzinfo)
        self.assertEqual(result.resolve_after.utcoffset().total_seconds(), 0)
        # 16:00 America/New_York on 2026-03-09 is EDT (UTC-4) → 20:00 UTC
        self.assertEqual(
            result.resolve_after,
            datetime(2026, 3, 9, 20, 0, tzinfo=timezone.utc),
        )

    def test_intraday_anchor_uses_previous_completed_session(self):
        sessions = [date(2026, 3, 26), date(2026, 3, 27), date(2026, 3, 30)]
        fake = _FakeCalendar(sessions, tz_name="Asia/Shanghai", close_time=time(15, 0))
        created = datetime(2026, 3, 27, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar, "xcals", SimpleNamespace(get_calendar=lambda _ex: fake), create=True
        ), patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar", lambda _ex: fake
        ):
            result = compute_resolve_after("cn", created, 1)

        self.assertEqual(result.anchor_session, date(2026, 3, 26))
        self.assertEqual(result.target_session, date(2026, 3, 27))

    def test_calendar_unavailable_never_approximates_natural_days(self):
        created = datetime(2026, 3, 27, 16, 0, tzinfo=timezone.utc)
        with patch.object(resolve_mod, "_XCALS_AVAILABLE", False):
            with self.assertRaises(CalendarUnavailableError) as ctx:
                compute_resolve_after("cn", created, "5d")
        self.assertEqual(ctx.exception.error_code, "calendar_unavailable")
        self.assertFalse(ctx.exception.meta.get("calendar_approx", True))

    def test_calendar_load_failure_is_typed_and_never_approximated(self):
        created = datetime(2026, 3, 27, 16, 0, tzinfo=timezone.utc)
        with patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar",
            side_effect=RuntimeError("calendar registry unavailable"),
        ):
            with self.assertRaises(CalendarUnavailableError) as ctx:
                compute_resolve_after("cn", created, "5d")
        self.assertEqual(ctx.exception.error_code, "calendar_load_failed")
        self.assertFalse(ctx.exception.meta.get("calendar_approx", True))

    def test_session_advance_failure_is_typed_and_never_approximated(self):
        sessions = [date(2026, 3, 26), date(2026, 3, 27)]
        fake = _FakeCalendar(
            sessions,
            tz_name="Asia/Shanghai",
            close_time=time(15, 0),
        )
        created = datetime(2026, 3, 27, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar,
            "xcals",
            SimpleNamespace(get_calendar=lambda _ex: fake),
            create=True,
        ), patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar", lambda _ex: fake
        ):
            with self.assertRaises(CalendarUnavailableError) as ctx:
                compute_resolve_after("cn", created, "1d")
        self.assertEqual(ctx.exception.error_code, "session_advance_failed")
        self.assertFalse(ctx.exception.meta.get("calendar_approx", True))

    def test_explicit_timestamp_policy(self):
        created = datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc)
        explicit = datetime(2026, 4, 1, 20, 0, tzinfo=timezone.utc)
        result = compute_resolve_after(
            "us",
            created,
            explicit,
            as_of_policy=AsOfPolicy.EXPLICIT_TIMESTAMP,
        )
        self.assertEqual(result.resolve_after, explicit)
        self.assertEqual(result.as_of_policy, AsOfPolicy.EXPLICIT_TIMESTAMP.value)
        self.assertFalse(result.calendar_approx)

    def test_oversized_explicit_timestamp_is_bounded_invalid_input(self):
        created = datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc)
        with self.assertRaises(InvalidHorizonError) as ctx:
            compute_resolve_after(
                "us",
                created,
                "2026-04-01T20:00:00+00:00" + "0" * 5000,
                as_of_policy=AsOfPolicy.EXPLICIT_TIMESTAMP,
            )
        self.assertEqual(ctx.exception.error_code, "invalid_horizon")
        self.assertLess(len(str(ctx.exception)), 128)
        self.assertNotIn("horizon", ctx.exception.meta)

    def test_cross_market_mismatch_rejected(self):
        created = datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc)
        with patch.object(resolve_mod, "get_market_for_stock", return_value="us"):
            with self.assertRaises(CrossMarketMismatchError):
                compute_resolve_after(
                    "cn",
                    created,
                    "1d",
                    stock_code="AAPL",
                )

    def test_cross_market_allowed_when_opted_in(self):
        sessions = [date(2026, 3, 26), date(2026, 3, 27), date(2026, 3, 30)]
        fake = _FakeCalendar(
            sessions, tz_name="America/New_York", close_time=time(16, 0)
        )
        created = datetime(2026, 3, 26, 17, 0, tzinfo=ZoneInfo("America/New_York"))
        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar, "xcals", SimpleNamespace(get_calendar=lambda _ex: fake), create=True
        ), patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar", lambda _ex: fake
        ), patch.object(resolve_mod, "get_market_for_stock", return_value="cn"):
            result = compute_resolve_after(
                "us",
                created,
                "1d",
                stock_code="600519",
                allow_cross_market=True,
            )
        self.assertEqual(result.market, "us")

    def test_crypto_explicit_timestamp_allowed(self):
        """crypto has no session calendar but explicit timestamps must still work."""
        created = datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc)
        explicit = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        result = compute_resolve_after(
            "crypto",
            created,
            explicit,
            as_of_policy=AsOfPolicy.EXPLICIT_TIMESTAMP,
        )
        self.assertEqual(result.resolve_after, explicit)
        self.assertEqual(result.market, "crypto")
        self.assertFalse(result.calendar_approx)

    def test_unsupported_market_and_invalid_horizon(self):
        created = datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc)
        with self.assertRaises(UnsupportedMarketError):
            compute_resolve_after("crypto", created, "1d")
        with self.assertRaises(InvalidHorizonError):
            compute_resolve_after("cn", created, "swing")
        with self.assertRaises(InvalidHorizonError):
            compute_resolve_after("cn", created, "0d")
        with self.assertRaises(InvalidHorizonError):
            compute_resolve_after("cn", created, "01d")
        with self.assertRaises(InvalidHorizonError):
            compute_resolve_after("cn", created, 2521)
        with self.assertRaises(InvalidHorizonError):
            compute_resolve_after("cn", created, "9" * 5000 + "d")
        with self.assertRaises(InvalidHorizonError) as ctx:
            compute_resolve_after("cn", created, "not-a-horizon" * 1000)
        self.assertLess(len(str(ctx.exception)), 128)
        self.assertNotIn("horizon", ctx.exception.meta)
        with self.assertRaises(InvalidHorizonError):
            compute_resolve_after(
                "cn",
                created,
                datetime(2026, 4, 1, tzinfo=timezone.utc),
                as_of_policy=AsOfPolicy.TRADING_DAY_CLOSE,
            )

    def test_to_dict_is_json_safe(self):
        sessions = [date(2026, 3, 26), date(2026, 3, 27)]
        fake = _FakeCalendar(sessions, tz_name="Asia/Shanghai", close_time=time(15, 0))
        created = datetime(2026, 3, 26, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch.object(trading_calendar, "_XCALS_AVAILABLE", True), patch.object(
            trading_calendar, "xcals", SimpleNamespace(get_calendar=lambda _ex: fake), create=True
        ), patch.object(resolve_mod, "_XCALS_AVAILABLE", True), patch(
            "exchange_calendars.get_calendar", lambda _ex: fake
        ):
            payload = compute_resolve_after("cn", created, "1d").to_dict()
        self.assertIn("resolve_after", payload)
        self.assertEqual(payload["calendar_approx"], False)
        self.assertIsInstance(payload["meta"], dict)
        json.dumps(payload)


@unittest.skipUnless(
    trading_calendar._XCALS_AVAILABLE,
    "exchange-calendars not installed",
)
class ComputeResolveAfterLiveCalendarTestCase(unittest.TestCase):
    """Real exchange-calendars fixtures for CN / HK / US boundary cases."""

    def test_cn_live_national_day_2025(self):
        created = datetime(2025, 9, 30, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        result = compute_resolve_after("cn", created, "1d")
        self.assertGreater(result.target_session, date(2025, 10, 1))
        self.assertEqual(result.exchange, "XSHG")
        self.assertFalse(result.calendar_approx)
        self.assertNotEqual(result.target_session, date(2025, 10, 1))

    def test_hk_live_christmas_2024(self):
        created = datetime(2024, 12, 24, 13, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))
        result = compute_resolve_after("hk", created, "1d")
        self.assertEqual(result.exchange, "XHKG")
        self.assertGreaterEqual(result.target_session, date(2024, 12, 27))
        self.assertNotEqual(result.target_session, date(2024, 12, 25))

    def test_us_live_july_3_early_close_2024(self):
        created = datetime(2024, 7, 2, 17, 0, tzinfo=ZoneInfo("America/New_York"))
        result = compute_resolve_after("us", created, "1d")
        self.assertEqual(result.target_session, date(2024, 7, 3))
        self.assertTrue(result.is_early_close)
        self.assertEqual(
            result.resolve_after, datetime(2024, 7, 3, 17, 0, tzinfo=timezone.utc)
        )

    def test_us_live_weekend_not_natural_days(self):
        created = datetime(2024, 11, 22, 17, 0, tzinfo=ZoneInfo("America/New_York"))
        result = compute_resolve_after("us", created, "1d")
        self.assertEqual(result.target_session, date(2024, 11, 25))  # Mon
        self.assertNotEqual(result.target_session, date(2024, 11, 23))

    def test_five_day_horizon_skips_holidays(self):
        created = datetime(2025, 9, 30, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        result = compute_resolve_after("cn", created, "5d")
        self.assertEqual(result.trading_sessions_forward, 5)
        self.assertGreater(result.target_session, date(2025, 10, 5))


if __name__ == "__main__":
    unittest.main()
