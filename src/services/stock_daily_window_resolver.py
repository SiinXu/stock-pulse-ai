# -*- coding: utf-8 -*-
"""Resolve authoritative, coherent local daily-bar windows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Sequence, Tuple

from src.core.trading_calendar import MARKET_EXCHANGE
from src.repositories.stock_repo import StockRepository
from src.storage import StockDaily
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StockDailyWindow:
    """A start bar and its forward bars from one stored stock-code shape."""

    code: str
    start_bar: StockDaily
    forward_bars: List[StockDaily]


def resolve_stock_daily_window(
    *,
    stock_repo: StockRepository,
    code_candidates: Sequence[str],
    expected_start_date: date,
    eval_window_days: int,
) -> Optional[StockDailyWindow]:
    """Choose one same-code window anchored to the authoritative start date."""
    if isinstance(eval_window_days, bool) or not isinstance(eval_window_days, int):
        raise ValueError("eval_window_days must be a positive integer")
    if eval_window_days <= 0:
        raise ValueError("eval_window_days must be a positive integer")

    best_window: Optional[StockDailyWindow] = None
    best_key: Optional[Tuple[bool, int, int]] = None
    for rank, code in enumerate(dict.fromkeys(code_candidates)):
        if not code:
            continue
        start_bar = stock_repo.get_daily_on_date(
            code=code,
            target_date=expected_start_date,
        )
        if start_bar is None or start_bar.close is None:
            continue

        forward_bars = stock_repo.get_forward_bars(
            code=code,
            analysis_date=start_bar.date,
            eval_window_days=eval_window_days,
        )
        key = (
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
            )

    return best_window


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
