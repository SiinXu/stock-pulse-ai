# -*- coding: utf-8 -*-
"""Configurable technical-indicator period resolution (Issue #172).

Defaults match the historical hard-coded periods used by StockTrendAnalyzer:
MA 5/10/20/60, MACD 12/26/9, RSI 6/12/24.

Explicit invalid values are rejected consistently by environment loading,
Settings validation, imports, and runtime construction. Only absent values use
the historical defaults.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

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


class IndicatorPeriodValidationError(ValueError):
    """Actionable validation error for one indicator-period field."""

    def __init__(self, field_name: str, message: str) -> None:
        self.field_name = field_name
        self.detail = message
        super().__init__(f"{field_name}: {message}")


@dataclass(frozen=True)
class IndicatorPeriodConfig:
    """Resolved, validated indicator periods used by the trend analyzer."""

    ma_periods: Tuple[int, ...] = DEFAULT_MA_PERIODS
    macd_fast: int = DEFAULT_MACD_FAST
    macd_slow: int = DEFAULT_MACD_SLOW
    macd_signal: int = DEFAULT_MACD_SIGNAL
    rsi_periods: Tuple[int, ...] = DEFAULT_RSI_PERIODS
    source: str = "defaults"

    def __post_init__(self) -> None:
        ma_periods = _validate_period_tuple(
            self.ma_periods,
            field_name="INDICATOR_MA_PERIODS",
            min_items=3,
            max_items=16,
            maximum=MAX_MA_PERIOD,
        )
        rsi_periods = _validate_period_tuple(
            self.rsi_periods,
            field_name="INDICATOR_RSI_PERIODS",
            min_items=1,
            max_items=8,
            maximum=MAX_RSI_PERIOD,
        )
        macd_values = {}
        for field_name, value in (
            ("INDICATOR_MACD_FAST", self.macd_fast),
            ("INDICATOR_MACD_SLOW", self.macd_slow),
            ("INDICATOR_MACD_SIGNAL", self.macd_signal),
        ):
            macd_values[field_name] = _validate_bounded_int(
                value,
                field_name=field_name,
                minimum=MIN_PERIOD,
                maximum=MAX_MACD_PERIOD,
            )
        if macd_values["INDICATOR_MACD_FAST"] >= macd_values["INDICATOR_MACD_SLOW"]:
            raise IndicatorPeriodValidationError(
                "INDICATOR_MACD_FAST",
                "must be less than INDICATOR_MACD_SLOW",
            )
        if not isinstance(self.source, str) or not self.source.strip() or len(self.source) > 80:
            raise IndicatorPeriodValidationError(
                "indicator_period_source",
                "must be a non-empty string no longer than 80 characters",
            )
        object.__setattr__(self, "ma_periods", ma_periods)
        object.__setattr__(self, "rsi_periods", rsi_periods)
        object.__setattr__(self, "macd_fast", macd_values["INDICATOR_MACD_FAST"])
        object.__setattr__(self, "macd_slow", macd_values["INDICATOR_MACD_SLOW"])
        object.__setattr__(self, "macd_signal", macd_values["INDICATOR_MACD_SIGNAL"])
        object.__setattr__(self, "source", self.source.strip())

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


def _validate_bounded_int(
    value: object,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool):
        raise IndicatorPeriodValidationError(field_name, "must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise IndicatorPeriodValidationError(field_name, "must be an integer") from exc
    if str(value).strip() != str(parsed):
        raise IndicatorPeriodValidationError(field_name, "must be an integer")
    if parsed < minimum or parsed > maximum:
        raise IndicatorPeriodValidationError(
            field_name,
            f"must be between {minimum} and {maximum}",
        )
    return parsed


def _validate_period_tuple(
    values: Sequence[int],
    *,
    field_name: str,
    min_items: int,
    max_items: int,
    maximum: int,
) -> Tuple[int, ...]:
    parsed = tuple(
        _validate_bounded_int(
            value,
            field_name=field_name,
            minimum=MIN_PERIOD,
            maximum=maximum,
        )
        for value in values
    )
    if len(parsed) < min_items or len(parsed) > max_items:
        raise IndicatorPeriodValidationError(
            field_name,
            f"must contain between {min_items} and {max_items} periods",
        )
    if len(set(parsed)) != len(parsed):
        raise IndicatorPeriodValidationError(field_name, "must not contain duplicate periods")
    return parsed


def parse_positive_int_list(
    raw: Optional[str],
    *,
    default: Sequence[int],
    field_name: str,
    min_items: int = 1,
    max_items: int = 16,
    maximum: int = MAX_MA_PERIOD,
) -> Tuple[int, ...]:
    """Parse a comma-separated list; absent values alone use *default*."""
    default_tuple = tuple(int(x) for x in default)
    if raw is None or not str(raw).strip():
        return default_tuple

    parts = [part.strip() for part in str(raw).split(",")]
    if any(not part for part in parts):
        raise IndicatorPeriodValidationError(field_name, "must not contain empty entries")
    return _validate_period_tuple(
        parts,
        field_name=field_name,
        min_items=min_items,
        max_items=max_items,
        maximum=maximum,
    )


def _parse_bounded_int(
    raw: Optional[str],
    *,
    default: int,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int:
    """Parse a single bounded integer; absent values alone use the default."""
    if raw is None or not str(raw).strip():
        return int(default)
    return _validate_bounded_int(
        str(raw).strip(),
        field_name=field_name,
        minimum=minimum,
        maximum=maximum,
    )


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
        raise IndicatorPeriodValidationError(
            "INDICATOR_MACD_FAST",
            "must be less than INDICATOR_MACD_SLOW",
        )
    return fast, slow, signal


def resolve_indicator_periods(
    *,
    ma_periods: Optional[Sequence[int]] = None,
    macd_fast: Optional[int] = None,
    macd_slow: Optional[int] = None,
    macd_signal: Optional[int] = None,
    rsi_periods: Optional[Sequence[int]] = None,
    source: str = "runtime",
) -> IndicatorPeriodConfig:
    """Build a period config from already-parsed integers (or defaults)."""
    ma = tuple(ma_periods) if ma_periods is not None else DEFAULT_MA_PERIODS
    rsi = tuple(rsi_periods) if rsi_periods is not None else DEFAULT_RSI_PERIODS
    return IndicatorPeriodConfig(
        ma_periods=ma,
        macd_fast=macd_fast if macd_fast is not None else DEFAULT_MACD_FAST,
        macd_slow=macd_slow if macd_slow is not None else DEFAULT_MACD_SLOW,
        macd_signal=macd_signal if macd_signal is not None else DEFAULT_MACD_SIGNAL,
        rsi_periods=rsi,
        source=source,
    )


def periods_from_config(config: object) -> IndicatorPeriodConfig:
    """Read indicator periods from a Config-like object."""
    def explicit_value(name: str) -> object:
        """Read a genuinely declared attribute without dynamic-proxy fabrication."""
        try:
            attributes = vars(config)
        except TypeError:
            attributes = {}
        if name in attributes:
            return attributes[name]
        sentinel = object()
        static_value = inspect.getattr_static(config, name, sentinel)
        if static_value is sentinel:
            return None
        return getattr(config, name)

    ma_periods = explicit_value("indicator_ma_periods")
    macd_fast = explicit_value("indicator_macd_fast")
    macd_slow = explicit_value("indicator_macd_slow")
    macd_signal = explicit_value("indicator_macd_signal")
    rsi_periods = explicit_value("indicator_rsi_periods")
    source = explicit_value("indicator_period_source")
    has_explicit_periods = any(
        value is not None
        for value in (ma_periods, macd_fast, macd_slow, macd_signal, rsi_periods)
    )
    return resolve_indicator_periods(
        ma_periods=ma_periods,
        macd_fast=macd_fast,
        macd_slow=macd_slow,
        macd_signal=macd_signal,
        rsi_periods=rsi_periods,
        source=source or ("global_settings" if has_explicit_periods else "defaults"),
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
    try:
        parse_positive_int_list(
            raw,
            default=(),
            field_name="period list",
            min_items=min_items,
            max_items=max_items,
            maximum=maximum,
        )
    except IndicatorPeriodValidationError as exc:
        return False, exc.detail
    return True, ""


def validate_indicator_env_map(values: Mapping[str, object]) -> IndicatorPeriodConfig:
    """Validate raw env/Settings values through the authoritative contract."""
    ma = parse_positive_int_list(
        values.get("INDICATOR_MA_PERIODS"),
        default=DEFAULT_MA_PERIODS,
        field_name="INDICATOR_MA_PERIODS",
        min_items=3,
        max_items=16,
        maximum=MAX_MA_PERIOD,
    )
    rsi = parse_positive_int_list(
        values.get("INDICATOR_RSI_PERIODS"),
        default=DEFAULT_RSI_PERIODS,
        field_name="INDICATOR_RSI_PERIODS",
        min_items=1,
        max_items=8,
        maximum=MAX_RSI_PERIOD,
    )
    fast, slow, signal = parse_macd_periods(
        fast_raw=values.get("INDICATOR_MACD_FAST"),
        slow_raw=values.get("INDICATOR_MACD_SLOW"),
        signal_raw=values.get("INDICATOR_MACD_SIGNAL"),
    )
    explicit = any(value is not None and str(value).strip() for value in values.values())
    return IndicatorPeriodConfig(
        ma_periods=ma,
        macd_fast=fast,
        macd_slow=slow,
        macd_signal=signal,
        rsi_periods=rsi,
        source="global_settings" if explicit else "defaults",
    )
