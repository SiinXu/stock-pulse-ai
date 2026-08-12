# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Pure domain types for prediction-scoring actuals snapshots (Issue #1110).

These records are intentionally free of provider I/O so ClaimScorer and
PredictionResolver can consume fixed fixtures without importing data_provider.
"""

from __future__ import annotations

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
