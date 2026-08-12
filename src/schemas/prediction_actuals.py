# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Pure domain types for prediction-scoring actuals snapshots (Issue #1110).

These records are intentionally free of provider I/O so ClaimScorer and
PredictionResolver can consume fixed fixtures without importing data_provider.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, FrozenSet, Optional, Sequence, Tuple


# Terminal status vocabulary for ActualsFetcher results.
# Provider-path failures must never surface as fabricated ok prices.
ACTUALS_STATUS_OK = "ok"
ACTUALS_STATUS_EMPTY = "empty"
ACTUALS_STATUS_HALTED = "halted"
ACTUALS_STATUS_DELISTED = "delisted"
ACTUALS_STATUS_PROVIDER_DOWN = "provider_down"
ACTUALS_STATUS_DATA_UNAVAILABLE = "data_unavailable"

ACTUALS_STATUSES: FrozenSet[str] = frozenset(
    {
        ACTUALS_STATUS_OK,
        ACTUALS_STATUS_EMPTY,
        ACTUALS_STATUS_HALTED,
        ACTUALS_STATUS_DELISTED,
        ACTUALS_STATUS_PROVIDER_DOWN,
        ACTUALS_STATUS_DATA_UNAVAILABLE,
    }
)

# Outcome-layer aliases: any non-ok status is non-scoreable for hit/miss.
NON_SCOREABLE_ACTUALS_STATUSES: FrozenSet[str] = frozenset(
    ACTUALS_STATUSES - {ACTUALS_STATUS_OK}
)

# Requested projection fields. Cache keys include the field set so two
# projections never silently share a partial snapshot.
FIELD_OHLC = "ohlc"
FIELD_RETURN = "return"
FIELD_VOLUME = "volume"
SUPPORTED_FIELD_SET: FrozenSet[str] = frozenset(
    {FIELD_OHLC, FIELD_RETURN, FIELD_VOLUME}
)
DEFAULT_FIELD_SET: Tuple[str, ...] = (FIELD_OHLC, FIELD_RETURN, FIELD_VOLUME)

# Reason codes stay stable for resolver retry policy and diagnostics.
REASON_PROVIDER_FAILURE = "provider_failure"
REASON_PROVIDER_TIMEOUT = "provider_timeout"
REASON_EMPTY_FRAME = "empty_frame"
REASON_NO_BAR_FOR_AS_OF = "no_bar_for_as_of"
REASON_NO_BAR_FOR_END = "no_bar_for_end"
REASON_END_NOT_REACHED = "end_not_reached"
REASON_NON_FINITE = "non_finite_values"
REASON_INVALID_SYMBOL = "invalid_symbol"
REASON_INVALID_WINDOW = "invalid_window"
REASON_HALTED_SESSION = "halted_session"
REASON_DELISTED = "delisted"
REASON_LOCAL_DATA_MISSING = "local_data_missing"
REASON_UNEXPECTED = "unexpected_error"

RETRYABLE_REASONS: FrozenSet[str] = frozenset(
    {
        REASON_PROVIDER_FAILURE,
        REASON_PROVIDER_TIMEOUT,
        REASON_LOCAL_DATA_MISSING,
        REASON_NO_BAR_FOR_END,
        REASON_END_NOT_REACHED,
        REASON_UNEXPECTED,
    }
)


@dataclass(frozen=True)
class ActualsBar:
    """One normalized daily bar used for claim scoring."""

    trade_date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None

    def __post_init__(self) -> None:
        if not isinstance(self.trade_date, date) or isinstance(
            self.trade_date, datetime
        ):
            raise ValueError("trade_date must be a date")
        for name in ("open", "high", "low", "close", "volume"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not math.isfinite(float(value))
            ):
                raise ValueError(f"{name} must be finite when present")
        prices = [
            value
            for value in (self.open, self.high, self.low, self.close)
            if value is not None
        ]
        if any(float(value) <= 0.0 for value in prices):
            raise ValueError("prices must be positive when present")
        if self.volume is not None and float(self.volume) < 0.0:
            raise ValueError("volume must be non-negative when present")
        if None not in (self.open, self.high, self.low, self.close):
            assert self.open is not None
            assert self.high is not None
            assert self.low is not None
            assert self.close is not None
            if self.low > min(self.open, self.close) or self.high < max(
                self.open, self.close
            ):
                raise ValueError("OHLC values are inconsistent")
            if self.low > self.high:
                raise ValueError("low must not exceed high")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True)
class ActualsRequest:
    """One actuals fetch request (symbol + time window + projection)."""

    symbol: str
    as_of: date
    market: Optional[str] = None
    end: Optional[date] = None
    field_set: Sequence[str] = field(default_factory=lambda: DEFAULT_FIELD_SET)

    @property
    def effective_end(self) -> date:
        return self.end if self.end is not None else self.as_of


@dataclass(frozen=True)
class ActualsSnapshot:
    """Normalized actuals projection for one symbol/window.

    On failure statuses, all price fields stay ``None`` so callers cannot
    accidentally treat a degraded result as a scored hit.
    """

    symbol: str
    market: str
    as_of: date
    end: date
    status: str
    field_set: Tuple[str, ...]
    reason: Optional[str] = None
    retryable: bool = False
    as_of_bar: Optional[ActualsBar] = None
    end_bar: Optional[ActualsBar] = None
    return_pct: Optional[float] = None
    source: Optional[str] = None
    from_cache: bool = False
    fetched_at: Optional[datetime] = None
    cache_key: Optional[str] = None
    provider_failure_count: int = 0

    def __post_init__(self) -> None:
        for name in ("as_of", "end"):
            value = getattr(self, name)
            if not isinstance(value, date) or isinstance(value, datetime):
                raise ValueError(f"{name} must be a date")
        if self.end < self.as_of:
            raise ValueError("end must not precede as_of")
        if self.status not in ACTUALS_STATUSES:
            raise ValueError(f"unsupported actuals status: {self.status!r}")
        fields = frozenset(self.field_set)
        if not fields or not fields <= SUPPORTED_FIELD_SET:
            raise ValueError("field_set must contain supported projection fields")
        if self.return_pct is not None and (
            isinstance(self.return_pct, bool)
            or not math.isfinite(float(self.return_pct))
        ):
            raise ValueError("return_pct must be finite when present")
        if (
            isinstance(self.provider_failure_count, bool)
            or self.provider_failure_count < 0
        ):
            raise ValueError("provider_failure_count must be non-negative")

        if self.status != ACTUALS_STATUS_OK:
            if self.return_pct is not None:
                raise ValueError("non-ok actuals must not carry a scoreable return")
            if self.status != ACTUALS_STATUS_HALTED and (
                self.as_of_bar is not None or self.end_bar is not None
            ):
                raise ValueError("failure actuals must not carry price bars")
            return

        if self.as_of_bar is None or self.end_bar is None:
            raise ValueError("ok actuals require anchor and end bars")
        if FIELD_RETURN in fields and self.return_pct is None:
            raise ValueError("return projection requires return_pct")
        if FIELD_OHLC in fields:
            for bar in (self.as_of_bar, self.end_bar):
                if None in (bar.open, bar.high, bar.low, bar.close):
                    raise ValueError("OHLC projection requires complete OHLC bars")
        if FIELD_VOLUME in fields and (
            self.as_of_bar.volume is None or self.end_bar.volume is None
        ):
            raise ValueError("volume projection requires both volume values")

    @property
    def ok(self) -> bool:
        return self.status == ACTUALS_STATUS_OK

    @property
    def data_unavailable(self) -> bool:
        """True when the result must not be scored as hit/miss."""
        return self.status in NON_SCOREABLE_ACTUALS_STATUSES

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["as_of"] = self.as_of.isoformat()
        payload["end"] = self.end.isoformat()
        payload["field_set"] = list(self.field_set)
        if self.as_of_bar is not None:
            payload["as_of_bar"] = self.as_of_bar.to_dict()
        if self.end_bar is not None:
            payload["end_bar"] = self.end_bar.to_dict()
        if self.fetched_at is not None:
            payload["fetched_at"] = self.fetched_at.isoformat()
        payload["ok"] = self.ok
        payload["data_unavailable"] = self.data_unavailable
        return payload
