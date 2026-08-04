# -*- coding: utf-8 -*-
"""Contract tests for authoritative, coherent daily-window resolution."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.services.stock_daily_window_resolver import (
    resolve_historical_daily_bar_date,
    resolve_stock_daily_window,
)


def _bar(day: date, close: float = 100.0):
    return SimpleNamespace(date=day, close=close)


class _FakeStockRepository:
    def __init__(self, starts, forwards):
        self.starts = starts
        self.forwards = forwards
        self.selected_start_dates = {}

    def get_daily_on_date(self, *, code, target_date):
        start = self.starts.get(code)
        if start is None or start.date != target_date:
            return None
        self.selected_start_dates[code] = start.date
        return start

    def get_forward_bars(self, *, code, analysis_date, eval_window_days):
        assert self.selected_start_dates[code] == analysis_date
        return list(self.forwards.get(code, ()))[:eval_window_days]


class _FakeCalendar:
    def __init__(self, sessions):
        self.sessions = tuple(sorted(sessions))

    def is_session(self, target_date):
        return target_date in self.sessions

    def date_to_session(self, target_date, *, direction):
        assert direction == "previous"
        return datetime.combine(
            max(session for session in self.sessions if session <= target_date),
            datetime.min.time(),
        )

    def previous_session(self, session):
        session_date = session.date()
        return datetime.combine(
            max(candidate for candidate in self.sessions if candidate < session_date),
            datetime.min.time(),
        )


def _resolve(starts, forwards, *, days=1):
    return resolve_stock_daily_window(
        stock_repo=_FakeStockRepository(starts, forwards),
        code_candidates=("first", "second"),
        expected_start_date=date(2024, 1, 5),
        eval_window_days=days,
    )


def test_candidates_without_exact_start_return_none() -> None:
    window = _resolve(
        starts={
            "first": _bar(date(2020, 1, 2), 50.0),
            "second": _bar(date(2021, 1, 4), 60.0),
        },
        forwards={
            "first": [_bar(date(2024, 1, 8), 55.0)],
            "second": [_bar(date(2024, 1, 8), 65.0)],
        },
    )

    assert window is None


def test_complete_same_code_window_outranks_partial_window() -> None:
    window = _resolve(
        starts={
            "first": _bar(date(2024, 1, 5)),
            "second": _bar(date(2024, 1, 5)),
        },
        forwards={
            "first": [],
            "second": [_bar(date(2024, 1, 8))],
        },
    )

    assert window is not None
    assert window.code == "second"


def test_equal_windows_preserve_candidate_order() -> None:
    window = _resolve(
        starts={
            "first": _bar(date(2024, 1, 5)),
            "second": _bar(date(2024, 1, 5)),
        },
        forwards={
            "first": [_bar(date(2024, 1, 8))],
            "second": [_bar(date(2024, 1, 8))],
        },
    )

    assert window is not None
    assert window.code == "first"


@pytest.mark.parametrize("days", [0, -1, 1.5, True, "1", "invalid"])
def test_invalid_window_length_fails_closed(days) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        _resolve(
            starts={"first": _bar(date(2024, 1, 5))},
            forwards={"first": []},
            days=days,
        )


def _resolve_historical_date(target_date: date, phase: str | None):
    calendar = _FakeCalendar(
        (date(2024, 1, 5), date(2024, 1, 8)),
    )
    with patch("exchange_calendars.get_calendar", return_value=calendar):
        return resolve_historical_daily_bar_date("cn", target_date, phase)


@pytest.mark.parametrize(
    "phase",
    ["premarket", "intraday", "lunch_break", "closing_auction"],
)
def test_open_session_phases_use_previous_completed_session(phase) -> None:
    assert _resolve_historical_date(date(2024, 1, 8), phase) == date(2024, 1, 5)


def test_postmarket_uses_current_completed_session() -> None:
    assert _resolve_historical_date(date(2024, 1, 8), "postmarket") == date(
        2024,
        1,
        8,
    )


def test_non_trading_phase_uses_previous_session_only_off_session() -> None:
    assert _resolve_historical_date(date(2024, 1, 7), "non_trading") == date(
        2024,
        1,
        5,
    )
    assert _resolve_historical_date(date(2024, 1, 8), "non_trading") is None


@pytest.mark.parametrize("phase", [None, "unknown", "postmarket"])
def test_unprovable_non_session_phase_fails_closed(phase) -> None:
    assert _resolve_historical_date(date(2024, 1, 7), phase) is None


def test_calendar_error_is_safe_logged_and_fails_closed() -> None:
    with patch(
        "exchange_calendars.get_calendar",
        side_effect=RuntimeError("calendar unavailable"),
    ), patch(
        "src.services.stock_daily_window_resolver.log_safe_exception",
    ) as safe_log:
        result = resolve_historical_daily_bar_date(
            "cn",
            date(2024, 1, 8),
            "postmarket",
        )

    assert result is None
    safe_log.assert_called_once()
