# -*- coding: utf-8 -*-
"""Configurable technical-indicator period resolution (Issue #172).

Defaults match the historical hard-coded periods used by StockTrendAnalyzer:
MA 5/10/20/60, MACD 12/26/9, RSI 6/12/24.

Invalid env values fall back to defaults with a warning so the process always
starts; Settings/registry validation rejects invalid values on write.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MA_PERIODS: Tuple[int, ...] = (5, 10, 20, 60)
DEFAULT_MACD_FAST = 12
DEFAULT_MACD_SLOW = 26
DEFAULT_MACD_SIGNAL = 9
DEFAULT_RSI_PERIODS: Tuple[int, ...] = (6, 12, 24)

# Upper bounds protect against pathological configs that would demand years of
# history or starve performance on every analysis run.
MAX_MA_PERIOD = 500
MAX_MACD_PERIOD = 200
MAX_RSI_PERIOD = 250
MIN_PERIOD = 1

# Calendar-day expansion used when mapping trading-day periods to date ranges.
# Matches history_loader style: ~1.8x trading days + margin for long holidays.
_CALENDAR_DAY_FACTOR = 1.8
_CALENDAR_DAY_MARGIN = 10


@dataclass(frozen=True)
class IndicatorPeriodConfig:
    """Resolved, validated indicator periods used by the trend analyzer."""

    ma_periods: Tuple[int, ...] = DEFAULT_MA_PERIODS
    macd_fast: int = DEFAULT_MACD_FAST
    macd_slow: int = DEFAULT_MACD_SLOW
    macd_signal: int = DEFAULT_MACD_SIGNAL
    rsi_periods: Tuple[int, ...] = DEFAULT_RSI_PERIODS

    @property
    def ma_short(self) -> int:
        return self.ma_periods[0]

    @property
    def ma_mid(self) -> int:
        return self.ma_periods[1] if len(self.ma_periods) > 1 else self.ma_periods[0]

    @property
    def ma_long(self) -> int:
        return self.ma_periods[2] if len(self.ma_periods) > 2 else self.ma_mid

    @property
    def ma_trend(self) -> Optional[int]:
        """Optional fourth slot historically exposed as ma60."""
        return self.ma_periods[3] if len(self.ma_periods) > 3 else None

    @property
    def max_ma_period(self) -> int:
        return max(self.ma_periods)

    @property
    def max_required_trading_days(self) -> int:
        """Minimum trading bars needed to compute every configured indicator."""
        candidates = [
            self.max_ma_period,
            self.macd_slow + self.macd_signal,
            max(self.rsi_periods),
        ]
        return max(candidates)

    def required_history_calendar_days(self) -> int:
        """Calendar-day lookback covering max required trading bars."""
        return trading_days_to_calendar_days(self.max_required_trading_days)


def trading_days_to_calendar_days(trading_days: int) -> int:
    """Expand trading-day demand into a calendar lookback window."""
    days = max(int(trading_days), 1)
    return int(days * _CALENDAR_DAY_FACTOR) + _CALENDAR_DAY_MARGIN


def parse_positive_int_list(
    raw: Optional[str],
    *,
    default: Sequence[int],
    field_name: str,
    min_items: int = 1,
    max_items: int = 16,
    maximum: int = MAX_MA_PERIOD,
) -> Tuple[int, ...]:
    """Parse a comma-separated positive-int list; fall back to *default* on error."""
    default_tuple = tuple(int(x) for x in default)
    if raw is None or not str(raw).strip():
        return default_tuple

    parts = [part.strip() for part in str(raw).split(",") if part.strip()]
    if not parts:
        logger.warning("%s is empty; falling back to %s", field_name, default_tuple)
        return default_tuple

    parsed: list[int] = []
    seen = set()
    for part in parts:
        try:
            value = int(part)
        except (TypeError, ValueError):
            logger.warning(
                "%s=%r contains non-integer %r; falling back to %s",
                field_name,
                raw,
                part,
                default_tuple,
            )
            return default_tuple
        if value < MIN_PERIOD or value > maximum:
            logger.warning(
                "%s=%r has out-of-range period %s (allowed %s..%s); falling back to %s",
                field_name,
                raw,
                value,
                MIN_PERIOD,
                maximum,
                default_tuple,
            )
            return default_tuple
        if value not in seen:
            seen.add(value)
            parsed.append(value)

    if len(parsed) < min_items or len(parsed) > max_items:
        logger.warning(
            "%s=%r must have between %s and %s unique periods; falling back to %s",
            field_name,
            raw,
            min_items,
            max_items,
            default_tuple,
        )
        return default_tuple

    return tuple(parsed)


def _parse_bounded_int(
    raw: Optional[str],
    *,
    default: int,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int:
    """Parse a single bounded integer with warning + fallback (leaf helper)."""
    if raw is None or not str(raw).strip():
        return int(default)
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning(
            "%s=%r is not a valid integer; falling back to %s",
            field_name,
            raw,
            default,
        )
        return int(default)
    if parsed < minimum:
        logger.warning(
            "%s=%r is below minimum %s; clamping to %s",
            field_name,
            parsed,
            minimum,
            minimum,
        )
        return minimum
    if parsed > maximum:
        logger.warning(
            "%s=%r is above maximum %s; clamping to %s",
            field_name,
            parsed,
            maximum,
            maximum,
        )
        return maximum
    return parsed


def parse_macd_periods(
    *,
    fast_raw: Optional[str],
    slow_raw: Optional[str],
    signal_raw: Optional[str],
) -> Tuple[int, int, int]:
    """Parse MACD fast/slow/signal with defaults and mutual constraints."""
    fast = _parse_bounded_int(
        fast_raw,
        default=DEFAULT_MACD_FAST,
        field_name="INDICATOR_MACD_FAST",
        minimum=MIN_PERIOD,
        maximum=MAX_MACD_PERIOD,
    )
    slow = _parse_bounded_int(
        slow_raw,
        default=DEFAULT_MACD_SLOW,
        field_name="INDICATOR_MACD_SLOW",
        minimum=MIN_PERIOD,
        maximum=MAX_MACD_PERIOD,
    )
    signal = _parse_bounded_int(
        signal_raw,
        default=DEFAULT_MACD_SIGNAL,
        field_name="INDICATOR_MACD_SIGNAL",
        minimum=MIN_PERIOD,
        maximum=MAX_MACD_PERIOD,
    )
    if fast >= slow:
        logger.warning(
            "INDICATOR_MACD_FAST=%s must be < INDICATOR_MACD_SLOW=%s; "
            "falling back to %s/%s/%s",
            fast,
            slow,
            DEFAULT_MACD_FAST,
            DEFAULT_MACD_SLOW,
            DEFAULT_MACD_SIGNAL,
        )
        return DEFAULT_MACD_FAST, DEFAULT_MACD_SLOW, DEFAULT_MACD_SIGNAL
    return fast, slow, signal


def resolve_indicator_periods(
    *,
    ma_periods: Optional[Sequence[int]] = None,
    macd_fast: Optional[int] = None,
    macd_slow: Optional[int] = None,
    macd_signal: Optional[int] = None,
    rsi_periods: Optional[Sequence[int]] = None,
) -> IndicatorPeriodConfig:
    """Build a period config from already-parsed integers (or defaults)."""
    ma = tuple(ma_periods) if ma_periods else DEFAULT_MA_PERIODS
    rsi = tuple(rsi_periods) if rsi_periods else DEFAULT_RSI_PERIODS
    return IndicatorPeriodConfig(
        ma_periods=ma if ma else DEFAULT_MA_PERIODS,
        macd_fast=int(macd_fast) if macd_fast is not None else DEFAULT_MACD_FAST,
        macd_slow=int(macd_slow) if macd_slow is not None else DEFAULT_MACD_SLOW,
        macd_signal=int(macd_signal) if macd_signal is not None else DEFAULT_MACD_SIGNAL,
        rsi_periods=rsi if rsi else DEFAULT_RSI_PERIODS,
    )


def periods_from_config(config: object) -> IndicatorPeriodConfig:
    """Read indicator periods from a Config-like object."""
    return resolve_indicator_periods(
        ma_periods=getattr(config, "indicator_ma_periods", None),
        macd_fast=getattr(config, "indicator_macd_fast", None),
        macd_slow=getattr(config, "indicator_macd_slow", None),
        macd_signal=getattr(config, "indicator_macd_signal", None),
        rsi_periods=getattr(config, "indicator_rsi_periods", None),
    )


def format_ma_label(period: int) -> str:
    """Canonical label for a moving-average period (e.g. MA60)."""
    return f"MA{int(period)}"


def insufficient_data_note(period: int, available: int) -> str:
    """User-visible annotation when a period exceeds available bars."""
    return (
        f"{format_ma_label(period)}: insufficient data "
        f"(need {period} bars, got {available})"
    )


def validate_period_list_string(
    raw: str,
    *,
    min_items: int = 1,
    max_items: int = 16,
    maximum: int = MAX_MA_PERIOD,
) -> Tuple[bool, str]:
    """Strict validation for Settings writes (no silent fallback)."""
    if raw is None or not str(raw).strip():
        return False, "period list must not be empty"
    parts = [part.strip() for part in str(raw).split(",") if part.strip()]
    if len(parts) < min_items or len(parts) > max_items:
        return False, f"period list must have between {min_items} and {max_items} values"
    seen = set()
    for part in parts:
        try:
            value = int(part)
        except (TypeError, ValueError):
            return False, f"period values must be integers, got {part!r}"
        if value < MIN_PERIOD or value > maximum:
            return False, f"period {value} out of range {MIN_PERIOD}..{maximum}"
        if value in seen:
            return False, f"duplicate period {value}"
        seen.add(value)
    return True, ""


def iter_named_ma_slots(periods: Sequence[int]) -> Iterable[Tuple[str, int]]:
    """Map ordered periods onto legacy result field names ma5/ma10/ma20/ma60.

    Slot names are historical compatibility labels; the period integers come
    from configuration. Only the first four periods are mapped to named slots.
    """
    slot_names = ("ma5", "ma10", "ma20", "ma60")
    for name, period in zip(slot_names, periods):
        yield name, int(period)
