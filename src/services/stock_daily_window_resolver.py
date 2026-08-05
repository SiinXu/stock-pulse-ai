# -*- coding: utf-8 -*-
"""Resolve authoritative, coherent local daily-bar windows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Sequence, Tuple

from src.core.trading_calendar import MARKET_EXCHANGE
from src.repositories.stock_repo import StockRepository
from src.storage import StockDaily
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

# Bound prior-session fallback for halted/suspended stocks (and local bar gaps).
# Prefer session-aware bounds when a market calendar is available; otherwise use
# a calendar-day window large enough to cover ~10 trading sessions.
PRIOR_SESSION_MAX_LOOKBACK_SESSIONS = 10
PRIOR_SESSION_CALENDAR_DAY_FALLBACK = 21


@dataclass(frozen=True)
class StockDailyWindow:
    """A start bar and its forward bars from one stored stock-code shape."""

    code: str
    start_bar: StockDaily
    forward_bars: List[StockDaily]
    used_prior_session_start: bool = False


def resolve_stock_daily_window(
    *,
    stock_repo: StockRepository,
    code_candidates: Sequence[str],
    expected_start_date: date,
    eval_window_days: int,
    market: Optional[str] = None,
) -> Optional[StockDailyWindow]:
    """Choose one same-code window anchored to the authoritative start date.

    Prefer an exact bar on ``expected_start_date``. When that bar is missing
    (common for A-share suspensions/halts or local gaps), fall back to the
    nearest previous bar within a bounded lookback. Start and forward bars are
    never combined across code shapes.
    """
    if isinstance(eval_window_days, bool) or not isinstance(eval_window_days, int):
        raise ValueError("eval_window_days must be a positive integer")
    if eval_window_days <= 0:
        raise ValueError("eval_window_days must be a positive integer")

    min_prior_date = _prior_session_lookback_floor(
        market=market,
        expected_start_date=expected_start_date,
    )

    best_window: Optional[StockDailyWindow] = None
    # Prefer exact-date starts over prior-session fallback, then complete
    # windows, then longer forward coverage, then earlier candidate rank.
    best_key: Optional[Tuple[bool, bool, int, int]] = None
    for rank, code in enumerate(dict.fromkeys(code_candidates)):
        if not code:
            continue
        start_bar = stock_repo.get_daily_on_date(
            code=code,
            target_date=expected_start_date,
        )
        used_prior = False
        if start_bar is None or start_bar.close is None:
            start_bar = stock_repo.get_nearest_daily_on_or_before(
                code=code,
                target_date=expected_start_date,
                min_date=min_prior_date,
            )
            if start_bar is None or start_bar.close is None:
                continue
            if start_bar.date != expected_start_date:
                used_prior = True

        forward_bars = stock_repo.get_forward_bars(
            code=code,
            analysis_date=start_bar.date,
            eval_window_days=eval_window_days,
        )
        key = (
            not used_prior,
            len(forward_bars) >= eval_window_days,
            len(forward_bars),
            -rank,
        )
        if best_key is None or key > best_key:
            best_key = key
            best_window = StockDailyWindow(
                code=code,
                start_bar=start_bar,
                forward_bars=forward_bars,
                used_prior_session_start=used_prior,
            )

    return best_window


def _prior_session_lookback_floor(
    *,
    market: Optional[str],
    expected_start_date: date,
) -> date:
    """Return the earliest date allowed for prior-session start-bar fallback."""
    floor = expected_start_date - timedelta(days=PRIOR_SESSION_CALENDAR_DAY_FALLBACK)
    normalized_market = str(market or "").strip().lower()
    if normalized_market not in MARKET_EXCHANGE:
        return floor

    try:
        import exchange_calendars as xcals

        calendar = xcals.get_calendar(MARKET_EXCHANGE[normalized_market])
        session = calendar.date_to_session(expected_start_date, direction="previous")
        for _ in range(PRIOR_SESSION_MAX_LOOKBACK_SESSIONS):
            session = calendar.previous_session(session)
        return session.date()
    except Exception as exc:  # broad-exception: fallback_recorded - calendar unavailable uses day bound.
        log_safe_exception(
            logger,
            "Prior-session lookback floor fell back to calendar days",
            exc,
            error_code="prior_session_lookback_floor_failed",
            context={
                "market": normalized_market,
                "expected_start_date": expected_start_date.isoformat(),
            },
        )
        return floor


def resolve_historical_daily_bar_date(
    market: Optional[str],
    target_date: date,
    phase: Optional[str],
) -> Optional[date]:
    """Resolve the completed daily bar consumable by a historical phase."""
    normalized_market = str(market or "").strip().lower()
    if normalized_market not in MARKET_EXCHANGE:
        return None

    normalized_phase = str(phase or "").strip().lower()
    if normalized_phase not in {
        "premarket",
        "intraday",
        "lunch_break",
        "closing_auction",
        "postmarket",
        "non_trading",
    }:
        return None

    try:
        import exchange_calendars as xcals

        calendar = xcals.get_calendar(MARKET_EXCHANGE[normalized_market])
        is_session = bool(calendar.is_session(target_date))
        if normalized_phase in {
            "premarket",
            "intraday",
            "lunch_break",
            "closing_auction",
        }:
            if not is_session:
                return None
            session = calendar.date_to_session(target_date, direction="previous")
            return calendar.previous_session(session).date()
        if normalized_phase == "postmarket":
            return target_date if is_session else None
        if is_session:
            return None
        return calendar.date_to_session(target_date, direction="previous").date()
    except Exception as exc:  # broad-exception: fallback_recorded - Backtests fail closed when calendar resolution is unavailable.
        log_safe_exception(
            logger,
            "Historical daily-bar date resolution failed closed",
            exc,
            error_code="historical_daily_bar_date_resolution_failed",
            context={
                "market": normalized_market,
                "target_date": target_date.isoformat(),
                "phase": normalized_phase,
            },
        )
        return None
