# -*- coding: utf-8 -*-
"""Prediction ``resolve_after`` policy using per-market exchange calendars.

Issue #1109 (Agent Evolution A6). Converts a prediction horizon into a UTC
timestamp that marks when verification may run.

This module reuses ``src.core.trading_calendar`` (exchange codes, timezones,
effective session selection). It does **not** approximate trading days with
natural calendar days: when the exchange calendar is unavailable or the market
is unsupported, computation fails closed so callers can mark
``data_unavailable`` / retry instead of fabricating a due time.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Union
from zoneinfo import ZoneInfo

import pandas as pd

from src.core.trading_calendar import (
    MARKET_EXCHANGE,
    MARKET_TIMEZONE,
    _XCALS_AVAILABLE,
    _as_market_datetime,
    get_effective_trading_date,
    get_market_for_stock,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

# Prediction verification horizons expressed as N exchange sessions after the
# completed as-of bar. Aligns with DecisionSignal outcome bar counting (N forward
# trading bars after the anchor session).
_HORIZON_SESSION_RE = re.compile(r"^([1-9][0-9]*)d$", re.IGNORECASE)
# Bound parsing and calendar traversal before converting attacker-controlled
# digit strings to int. A1 currently emits at most 20d; this broader ceiling
# leaves room for future typed horizons without permitting unbounded work.
MAX_TRADING_SESSIONS_FORWARD = 2520
MAX_HORIZON_INPUT_CHARS = 128

# Primary markets for the forecast verification track (Issue #1109).
# Other exchange-calendar markets remain callable when registered in
# MARKET_EXCHANGE / MARKET_TIMEZONE, but docs and acceptance focus on these.
PRIMARY_RESOLVE_MARKETS = frozenset({"cn", "hk", "us"})

HorizonInput = Union[str, int, datetime, date]


class AsOfPolicy(str, Enum):
    """When the prediction becomes eligible for scoring."""

    TRADING_DAY_CLOSE = "trading_day_close"
    EXPLICIT_TIMESTAMP = "explicit_timestamp"


class ResolveAfterError(ValueError):
    """Base error for resolve_after computation failures."""

    def __init__(self, message: str, *, error_code: str, meta: Optional[Mapping[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code
        self.meta: Dict[str, Any] = dict(meta or {})


class CalendarUnavailableError(ResolveAfterError):
    """Exchange calendar missing or lookup failed; never approximate with natural days."""


class UnsupportedMarketError(ResolveAfterError):
    """Market has no registered exchange calendar for trading-day horizons."""


class InvalidHorizonError(ResolveAfterError):
    """Horizon string/value cannot be interpreted under the requested policy."""


class CrossMarketMismatchError(ResolveAfterError):
    """Optional stock_code implies a different market than the explicit market field."""


@dataclass(frozen=True)
class ResolveAfterResult:
    """UTC resolve timestamp plus transparent session metadata for persistence."""

    resolve_after: datetime
    market: str
    horizon: str
    as_of_policy: str
    exchange: str
    timezone: str
    anchor_session: date
    target_session: date
    session_close_local: datetime
    is_early_close: bool
    trading_sessions_forward: int
    calendar_approx: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe projection for persistence metadata or diagnostics."""
        return {
            "resolve_after": self.resolve_after.isoformat(),
            "market": self.market,
            "horizon": self.horizon,
            "as_of_policy": self.as_of_policy,
            "exchange": self.exchange,
            "timezone": self.timezone,
            "anchor_session": self.anchor_session.isoformat(),
            "target_session": self.target_session.isoformat(),
            "session_close_local": self.session_close_local.isoformat(),
            "is_early_close": self.is_early_close,
            "trading_sessions_forward": self.trading_sessions_forward,
            "calendar_approx": self.calendar_approx,
            "meta": dict(self.meta),
        }


def compute_resolve_after(
    market: str,
    created_at: datetime,
    horizon: HorizonInput,
    as_of_policy: Union[str, AsOfPolicy] = AsOfPolicy.TRADING_DAY_CLOSE,
    *,
    stock_code: Optional[str] = None,
    allow_cross_market: bool = False,
) -> ResolveAfterResult:
    """Compute UTC ``resolve_after`` for a pending prediction.

    Args:
        market: Exchange region key (``cn`` / ``hk`` / ``us`` / …). Authoritative
            for session math; not inferred from wall-clock timezone alone.
        created_at: Prediction creation time. Timezone-aware values are
            converted correctly; naive values are treated as **UTC** (prediction
            storage contract).
        horizon: ``Nd`` trading-session horizon (e.g. ``1d``, ``5d``, ``20d``),
            a positive integer session count, or an absolute timestamp/date when
            ``as_of_policy=explicit_timestamp``.
        as_of_policy: ``trading_day_close`` (default) or ``explicit_timestamp``.
        stock_code: Optional symbol used only to detect market mismatches.
        allow_cross_market: When False (default), a stock_code that maps to a
            different market than ``market`` raises ``CrossMarketMismatchError``.

    Returns:
        ``ResolveAfterResult`` with timezone-aware UTC ``resolve_after``.

    Raises:
        CalendarUnavailableError: exchange-calendars missing or session lookup failed.
        UnsupportedMarketError: market not registered for trading calendars.
        InvalidHorizonError: bad horizon / policy combination.
        CrossMarketMismatchError: stock_code market disagrees with ``market``.
    """
    policy = _normalize_policy(as_of_policy)
    created_utc = _as_utc(created_at)

    # explicit_timestamp does not need an exchange calendar, so accept free-form
    # market keys (including crypto). trading_day_close stays strict.
    if policy is AsOfPolicy.EXPLICIT_TIMESTAMP:
        market_key = str(market or "").strip().lower() or "unknown"
        _maybe_reject_cross_market(
            market_key=market_key,
            stock_code=stock_code,
            allow_cross_market=allow_cross_market,
            require_registered_market=False,
        )
        return _resolve_explicit(
            market=market_key,
            created_at=created_utc,
            horizon=horizon,
        )

    market_key = _normalize_market(market)
    _maybe_reject_cross_market(
        market_key=market_key,
        stock_code=stock_code,
        allow_cross_market=allow_cross_market,
        require_registered_market=True,
    )

    # trading_day_close — absolute timestamps must use explicit_timestamp policy.
    if isinstance(horizon, datetime) or type(horizon) is date:
        raise InvalidHorizonError(
            "datetime/date horizon requires as_of_policy='explicit_timestamp'",
            error_code="horizon_requires_explicit_policy",
            meta={"as_of_policy": policy.value},
        )

    sessions_forward = _parse_session_horizon(horizon)
    return _resolve_trading_day_close(
        market=market_key,
        created_at=created_utc,
        sessions_forward=sessions_forward,
        horizon_label=_format_horizon_label(horizon, sessions_forward),
    )


def _maybe_reject_cross_market(
    *,
    market_key: str,
    stock_code: Optional[str],
    allow_cross_market: bool,
    require_registered_market: bool,
) -> None:
    """Optionally reject stock_code market mismatches.

    When ``require_registered_market`` is False (explicit timestamps), skip the
    check if the declared market is not a known exchange region so callers can
    pass free-form labels such as ``crypto``.
    """
    if not stock_code:
        return
    if not require_registered_market and market_key not in MARKET_EXCHANGE:
        return
    inferred = get_market_for_stock(stock_code)
    if (
        inferred
        and inferred not in {None, "crypto"}
        and inferred != market_key
        and not allow_cross_market
    ):
        raise CrossMarketMismatchError(
            f"stock_code market {inferred!r} disagrees with market {market_key!r}",
            error_code="cross_market_mismatch",
            meta={
                "market": market_key,
                "stock_code_market": inferred,
                "stock_code": str(stock_code).strip().upper(),
            },
        )


def _normalize_policy(as_of_policy: Union[str, AsOfPolicy]) -> AsOfPolicy:
    if isinstance(as_of_policy, AsOfPolicy):
        return as_of_policy
    raw = str(as_of_policy or "").strip().lower()
    try:
        return AsOfPolicy(raw)
    except ValueError as exc:
        allowed = ", ".join(p.value for p in AsOfPolicy)
        raise InvalidHorizonError(
            f"as_of_policy must be one of: {allowed}",
            error_code="invalid_as_of_policy",
            meta={"as_of_policy": raw},
        ) from exc


def _normalize_market(market: str) -> str:
    key = str(market or "").strip().lower()
    if not key:
        raise UnsupportedMarketError(
            "market is required for resolve_after",
            error_code="market_required",
        )
    if key == "crypto":
        raise UnsupportedMarketError(
            "crypto is 24/7 and has no exchange trading-day resolve_after policy; "
            "use as_of_policy='explicit_timestamp'",
            error_code="crypto_unsupported_for_trading_day_close",
            meta={"market": key},
        )
    if key not in MARKET_EXCHANGE or key not in MARKET_TIMEZONE:
        raise UnsupportedMarketError(
            f"market {key!r} has no registered exchange calendar",
            error_code="unsupported_market",
            meta={"market": key, "supported": sorted(MARKET_EXCHANGE)},
        )
    return key


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise InvalidHorizonError(
            "created_at must be a datetime",
            error_code="invalid_created_at",
        )
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_session_horizon(horizon: HorizonInput) -> int:
    if isinstance(horizon, bool):
        raise InvalidHorizonError(
            "horizon must not be a boolean",
            error_code="invalid_horizon",
        )
    if isinstance(horizon, int):
        if horizon <= 0 or horizon > MAX_TRADING_SESSIONS_FORWARD:
            raise InvalidHorizonError(
                "horizon session count must be between 1 and "
                f"{MAX_TRADING_SESSIONS_FORWARD}",
                error_code="invalid_horizon",
                meta={
                    "horizon": horizon,
                    "max_sessions": MAX_TRADING_SESSIONS_FORWARD,
                },
            )
        return horizon

    text = str(horizon or "").strip()
    if not text:
        raise InvalidHorizonError(
            "horizon is required",
            error_code="invalid_horizon",
        )
    if len(text) > MAX_HORIZON_INPUT_CHARS:
        raise InvalidHorizonError(
            "horizon input is too long",
            error_code="invalid_horizon",
            meta={"max_chars": MAX_HORIZON_INPUT_CHARS},
        )

    # Reject ISO timestamps under trading_day_close (caller must switch policy).
    if "T" in text or text.endswith("Z") or "+" in text[1:]:
        raise InvalidHorizonError(
            "timestamp horizon requires as_of_policy='explicit_timestamp'",
            error_code="horizon_requires_explicit_policy",
            meta={"horizon": text},
        )

    match = _HORIZON_SESSION_RE.fullmatch(text)
    if not match:
        raise InvalidHorizonError(
            "horizon must look like '1d', '5d', '20d' (trading sessions) "
            "or a positive integer session count",
            error_code="invalid_horizon",
            meta={"horizon": text},
        )
    digits = match.group(1)
    max_digits = len(str(MAX_TRADING_SESSIONS_FORWARD))
    if len(digits) > max_digits:
        raise InvalidHorizonError(
            "horizon session count must be between 1 and "
            f"{MAX_TRADING_SESSIONS_FORWARD}",
            error_code="invalid_horizon",
            meta={"max_sessions": MAX_TRADING_SESSIONS_FORWARD},
        )
    count = int(digits)
    if count > MAX_TRADING_SESSIONS_FORWARD:
        raise InvalidHorizonError(
            "horizon session count must be between 1 and "
            f"{MAX_TRADING_SESSIONS_FORWARD}",
            error_code="invalid_horizon",
            meta={
                "horizon": text,
                "max_sessions": MAX_TRADING_SESSIONS_FORWARD,
            },
        )
    return count


def _format_horizon_label(horizon: HorizonInput, sessions_forward: int) -> str:
    if isinstance(horizon, str) and _HORIZON_SESSION_RE.fullmatch(horizon.strip()):
        return horizon.strip().lower()
    return f"{sessions_forward}d"


def _resolve_explicit(
    *,
    market: str,
    created_at: datetime,
    horizon: HorizonInput,
) -> ResolveAfterResult:
    resolve_at = _coerce_explicit_timestamp(horizon)
    if resolve_at < created_at:
        raise InvalidHorizonError(
            "explicit resolve_after must be >= created_at",
            error_code="explicit_before_created_at",
            meta={
                "created_at": created_at.isoformat(),
                "resolve_after": resolve_at.isoformat(),
            },
        )

    tz_name = MARKET_TIMEZONE.get(market, "UTC")
    exchange = MARKET_EXCHANGE.get(market, "")
    market_tz = ZoneInfo(tz_name)
    local = resolve_at.astimezone(market_tz)

    return ResolveAfterResult(
        resolve_after=resolve_at,
        market=market,
        horizon=resolve_at.isoformat(),
        as_of_policy=AsOfPolicy.EXPLICIT_TIMESTAMP.value,
        exchange=exchange,
        timezone=tz_name,
        anchor_session=created_at.astimezone(market_tz).date(),
        target_session=local.date(),
        session_close_local=local,
        is_early_close=False,
        trading_sessions_forward=0,
        calendar_approx=False,
        meta={
            "calendar_approx": False,
            "policy": AsOfPolicy.EXPLICIT_TIMESTAMP.value,
            "note": "explicit timestamp; exchange session math not applied",
        },
    )


def _coerce_explicit_timestamp(horizon: HorizonInput) -> datetime:
    if isinstance(horizon, datetime):
        return _as_utc(horizon)
    if type(horizon) is date:
        # Interpret bare dates as 00:00 UTC. Callers that need session close
        # should use trading_day_close with an Nd horizon instead.
        return datetime(horizon.year, horizon.month, horizon.day, tzinfo=timezone.utc)

    text = str(horizon or "").strip()
    if not text:
        raise InvalidHorizonError(
            "explicit horizon timestamp is required",
            error_code="invalid_horizon",
        )
    if len(text) > MAX_HORIZON_INPUT_CHARS:
        raise InvalidHorizonError(
            "explicit horizon timestamp is too long",
            error_code="invalid_horizon",
            meta={"max_chars": MAX_HORIZON_INPUT_CHARS},
        )
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise InvalidHorizonError(
            f"cannot parse explicit horizon timestamp: {horizon!r}",
            error_code="invalid_horizon",
            meta={"horizon": str(horizon)},
        ) from exc
    return _as_utc(parsed)


def _resolve_trading_day_close(
    *,
    market: str,
    created_at: datetime,
    sessions_forward: int,
    horizon_label: str,
) -> ResolveAfterResult:
    if not _XCALS_AVAILABLE:
        raise CalendarUnavailableError(
            "exchange-calendars is not installed; refuse natural-day approximation "
            "for prediction resolve_after (calendar_approx is never set true)",
            error_code="calendar_unavailable",
            meta={
                "market": market,
                "calendar_approx": False,
                "hint": "pip install exchange-calendars",
            },
        )

    exchange = MARKET_EXCHANGE[market]
    tz_name = MARKET_TIMEZONE[market]

    try:
        import exchange_calendars as xcals

        calendar = xcals.get_calendar(exchange)
    except Exception as exc:  # broad-exception: fallback_recorded - Calendar load failures fail closed without natural-day approx.
        log_safe_exception(
            logger,
            "Prediction resolve_after calendar load failed closed",
            exc,
            error_code="prediction_resolve_after_calendar_load_failed",
            level=logging.WARNING,
            context={"market": market, "exchange": exchange},
        )
        raise CalendarUnavailableError(
            f"failed to load exchange calendar {exchange} for market {market}",
            error_code="calendar_load_failed",
            meta={"market": market, "exchange": exchange, "calendar_approx": False},
        ) from exc

    # Last completed session as of created_at (same contract as analysis bars).
    try:
        anchor_session = get_effective_trading_date(market, current_time=created_at)
    except Exception as exc:  # broad-exception: fallback_recorded - Anchor session lookup failures fail closed without natural-day approx.
        log_safe_exception(
            logger,
            "Prediction resolve_after anchor session failed closed",
            exc,
            error_code="prediction_resolve_after_anchor_failed",
            level=logging.WARNING,
            context={"market": market},
        )
        raise CalendarUnavailableError(
            "failed to resolve anchor trading session",
            error_code="anchor_session_failed",
            meta={"market": market, "calendar_approx": False},
        ) from exc

    # If effective-date helper fail-opened to a natural date (calendar gap),
    # re-check strictly so we never advance by natural days.
    try:
        if not calendar.is_session(anchor_session):
            # Map natural fallback onto the previous true session when possible.
            anchor_ts = calendar.date_to_session(anchor_session, direction="previous")
            anchor_session = (
                anchor_ts.date() if hasattr(anchor_ts, "date") else pd.Timestamp(anchor_ts).date()
            )
    except Exception as exc:  # broad-exception: fallback_recorded - Non-session anchors fail closed instead of natural-day advancement.
        log_safe_exception(
            logger,
            "Prediction resolve_after anchor session normalize failed closed",
            exc,
            error_code="prediction_resolve_after_anchor_normalize_failed",
            level=logging.WARNING,
            context={"market": market, "anchor_session": str(anchor_session)},
        )
        raise CalendarUnavailableError(
            "anchor session is not on the exchange calendar",
            error_code="anchor_not_on_calendar",
            meta={
                "market": market,
                "anchor_session": anchor_session.isoformat(),
                "calendar_approx": False,
            },
        ) from exc

    try:
        anchor_ts = calendar.date_to_session(anchor_session, direction="previous")
        target_ts = calendar.session_offset(anchor_ts, sessions_forward)
        target_session = (
            target_ts.date() if hasattr(target_ts, "date") else pd.Timestamp(target_ts).date()
        )
        close_raw = calendar.session_close(target_ts)
        close_local = _as_market_datetime(close_raw, tz_name)
        if close_local is None:
            raise CalendarUnavailableError(
                "session close timestamp missing",
                error_code="session_close_missing",
                meta={
                    "market": market,
                    "target_session": target_session.isoformat(),
                    "calendar_approx": False,
                },
            )
        is_early = _session_is_early_close(calendar, target_ts)
    except ResolveAfterError:
        raise
    except Exception as exc:  # broad-exception: fallback_recorded - Session advance failures fail closed without natural-day approx.
        log_safe_exception(
            logger,
            "Prediction resolve_after session advance failed closed",
            exc,
            error_code="prediction_resolve_after_session_advance_failed",
            level=logging.WARNING,
            context={
                "market": market,
                "anchor_session": str(anchor_session),
                "sessions_forward": sessions_forward,
            },
        )
        raise CalendarUnavailableError(
            "failed to advance trading sessions for resolve_after",
            error_code="session_advance_failed",
            meta={
                "market": market,
                "anchor_session": anchor_session.isoformat(),
                "sessions_forward": sessions_forward,
                "calendar_approx": False,
            },
        ) from exc

    resolve_utc = close_local.astimezone(timezone.utc)
    meta = {
        "calendar_approx": False,
        "policy": AsOfPolicy.TRADING_DAY_CLOSE.value,
        "anchor_rule": "effective_completed_session",
        "count_rule": "n_sessions_after_anchor",
        "exchange": exchange,
        "primary_market_track": market in PRIMARY_RESOLVE_MARKETS,
    }

    return ResolveAfterResult(
        resolve_after=resolve_utc,
        market=market,
        horizon=horizon_label,
        as_of_policy=AsOfPolicy.TRADING_DAY_CLOSE.value,
        exchange=exchange,
        timezone=tz_name,
        anchor_session=anchor_session,
        target_session=target_session,
        session_close_local=close_local,
        is_early_close=is_early,
        trading_sessions_forward=sessions_forward,
        calendar_approx=False,
        meta=meta,
    )


def _session_is_early_close(calendar: Any, session_ts: Any) -> bool:
    """Return True when exchange-calendars marks the session as an early close."""
    early_closes = getattr(calendar, "early_closes", None)
    if early_closes is None:
        return False
    try:
        if session_ts in early_closes:
            return True
    except (TypeError, ValueError, KeyError):
        # Membership against non-index-like early_closes is optional metadata.
        pass
    try:
        session_date = (
            session_ts.date() if hasattr(session_ts, "date") else pd.Timestamp(session_ts).date()
        )
        for item in early_closes:
            item_ts = pd.Timestamp(item)
            if item_ts.date() == session_date:
                return True
    except (TypeError, ValueError, AttributeError):
        # Timestamp coercion failures leave is_early_close as false.
        return False
    return False
