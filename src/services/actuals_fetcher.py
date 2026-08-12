# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""ActualsFetcher: server-path actuals for prediction scoring (Issue #1110).

Pulls real OHLC/volume through ``DataFetcherManager.get_daily_data`` (the
established data_provider governance path: fallback chain, cache, circuit,
validation). Never fabricates prices. Provider failures surface as typed
``provider_down`` / ``data_unavailable`` results so ClaimScorer cannot mark a
hit on missing market data.

In-process short-TTL cache + in-flight coalescing ensure the same
``(market, symbol, as_of, end, field_set)`` key is resolved once per tick group.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import Future
from datetime import date, datetime, timedelta, timezone
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

import pandas as pd

from data_provider.base import (
    CircuitOpenError,
    DataFetchError,
    DataSourceUnavailableError,
)
from data_provider.daily_cache import LocalDataMissingError
from data_provider.retry_policy import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    call_with_timeout,
)
from src.market.context import detect_market
from src.schemas.prediction_actuals import (
    ACTUALS_STATUS_DATA_UNAVAILABLE,
    ACTUALS_STATUS_DELISTED,
    ACTUALS_STATUS_EMPTY,
    ACTUALS_STATUS_HALTED,
    ACTUALS_STATUS_OK,
    ACTUALS_STATUS_PROVIDER_DOWN,
    DEFAULT_FIELD_SET,
    FIELD_OHLC,
    FIELD_RETURN,
    FIELD_VOLUME,
    REASON_DELISTED,
    REASON_EMPTY_FRAME,
    REASON_END_NOT_REACHED,
    REASON_HALTED_SESSION,
    REASON_INVALID_SYMBOL,
    REASON_INVALID_WINDOW,
    REASON_LOCAL_DATA_MISSING,
    REASON_NO_BAR_FOR_AS_OF,
    REASON_NO_BAR_FOR_END,
    REASON_NON_FINITE,
    REASON_PROVIDER_FAILURE,
    REASON_PROVIDER_TIMEOUT,
    REASON_UNEXPECTED,
    RETRYABLE_REASONS,
    SUPPORTED_FIELD_SET,
    ActualsBar,
    ActualsRequest,
    ActualsSnapshot,
)
from src.services.stock_code_utils import normalize_code, resolve_daily_stock_identity
from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text


logger = logging.getLogger(__name__)

DateLike = Union[date, datetime, str]

# Short process-local TTL for batch coalesce within a scheduler tick.
DEFAULT_CACHE_TTL_SECONDS = 60.0
DEFAULT_CACHE_MAX_ENTRIES = 512
# Manager already retries per provider; keep outer attempts minimal.
DEFAULT_MAX_ATTEMPTS = 2
# Calendar-day pad so weekend/holiday as_of still finds the prior session.
DEFAULT_LOOKBACK_CALENDAR_DAYS = 10
# Upper bound on the as_of→end window pulled from providers.
MAX_WINDOW_CALENDAR_DAYS = 120

_PRICE_COLUMNS = ("open", "high", "low", "close")


class ActualsFetcher:
    """Fetch normalized actuals through the server data_provider path."""

    def __init__(
        self,
        *,
        manager: Any = None,
        manager_factory: Optional[Callable[[], Any]] = None,
        cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        lookback_calendar_days: int = DEFAULT_LOOKBACK_CALENDAR_DAYS,
        clock: Optional[Callable[[], float]] = None,
        now_utc: Optional[Callable[[], datetime]] = None,
    ) -> None:
        cache_ttl_value = float(cache_ttl_seconds)
        cache_max_value = float(cache_max_entries)
        timeout_value = float(request_timeout_seconds)
        attempts_value = float(max_attempts)
        lookback_value = float(lookback_calendar_days)
        if (
            isinstance(cache_ttl_seconds, bool)
            or not math.isfinite(cache_ttl_value)
            or cache_ttl_value <= 0
        ):
            raise ValueError("cache_ttl_seconds must be positive")
        if (
            isinstance(cache_max_entries, bool)
            or not math.isfinite(cache_max_value)
            or cache_max_value <= 0
            or not cache_max_value.is_integer()
        ):
            raise ValueError("cache_max_entries must be positive")
        if (
            isinstance(request_timeout_seconds, bool)
            or not math.isfinite(timeout_value)
            or timeout_value <= 0
        ):
            raise ValueError("request_timeout_seconds must be positive")
        if (
            isinstance(max_attempts, bool)
            or not math.isfinite(attempts_value)
            or attempts_value < 1
            or not attempts_value.is_integer()
        ):
            raise ValueError("max_attempts must be >= 1")
        if (
            isinstance(lookback_calendar_days, bool)
            or not math.isfinite(lookback_value)
            or lookback_value < 0
            or not lookback_value.is_integer()
        ):
            raise ValueError("lookback_calendar_days must be >= 0")

        self._manager = manager
        self._manager_factory = manager_factory
        self._cache_ttl_seconds = cache_ttl_value
        self._cache_max_entries = int(cache_max_value)
        self._request_timeout_seconds = timeout_value
        self._max_attempts = int(attempts_value)
        self._lookback_calendar_days = int(lookback_value)
        self._clock = clock or time.monotonic
        self._now_utc = now_utc or (lambda: datetime.now(timezone.utc))

        self._lock = threading.RLock()
        # cache_key -> (expires_at_monotonic, snapshot)
        self._cache: Dict[str, Tuple[float, ActualsSnapshot]] = {}
        # cache_key -> in-flight Future shared by concurrent waiters
        self._inflight: Dict[str, Future] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(
        self,
        *,
        symbol: str,
        as_of: DateLike,
        market: Optional[str] = None,
        end: Optional[DateLike] = None,
        field_set: Optional[Sequence[str]] = None,
    ) -> ActualsSnapshot:
        """Fetch one actuals snapshot for ``symbol`` over ``[as_of, end]``."""
        try:
            request = ActualsRequest(
                symbol=symbol,
                market=market,
                as_of=self._coerce_date(as_of, field_name="as_of"),
                end=(
                    None
                    if end is None
                    else self._coerce_date(end, field_name="end")
                ),
                field_set=(
                    tuple(field_set) if field_set is not None else DEFAULT_FIELD_SET
                ),
            )
        except (TypeError, ValueError):
            fallback = self._now_utc().date()
            return self._failure_snapshot(
                symbol=str(symbol or "").strip(),
                market=str(market or "").strip().lower() or "unknown",
                as_of=fallback,
                end=fallback,
                field_set=DEFAULT_FIELD_SET,
                status=ACTUALS_STATUS_DATA_UNAVAILABLE,
                reason=REASON_INVALID_WINDOW,
                retryable=False,
                cache_key=None,
            )
        return self._fetch_request(request)

    def fetch_many(
        self,
        requests: Sequence[Union[ActualsRequest, Mapping[str, Any]]],
    ) -> List[ActualsSnapshot]:
        """Fetch many requests, coalescing identical cache keys to one provider call."""
        key_to_request: Dict[str, ActualsRequest] = {}
        ordered_keys: List[Optional[str]] = []
        early_results: Dict[int, ActualsSnapshot] = {}

        for index, item in enumerate(requests):
            try:
                request = self._normalize_request(item)
            except (TypeError, ValueError):
                fallback = self._now_utc().date()
                raw = item if isinstance(item, Mapping) else {}
                early_results[index] = self._failure_snapshot(
                    symbol=str(raw.get("symbol") or "").strip(),
                    market=str(raw.get("market") or "").strip().lower()
                    or "unknown",
                    as_of=fallback,
                    end=fallback,
                    field_set=self._safe_field_set(raw.get("field_set")),
                    status=ACTUALS_STATUS_DATA_UNAVAILABLE,
                    reason=REASON_INVALID_WINDOW,
                    retryable=False,
                    cache_key=None,
                )
                ordered_keys.append(None)
                continue
            try:
                prepared = self._prepare_request(request)
            except _ActualsPrepError as exc:
                as_of_fallback = (
                    request.as_of
                    if isinstance(request.as_of, date)
                    and not isinstance(request.as_of, datetime)
                    else self._now_utc().date()
                )
                end_fallback = (
                    request.end
                    if isinstance(request.end, date)
                    and not isinstance(request.end, datetime)
                    else as_of_fallback
                )
                if end_fallback < as_of_fallback:
                    end_fallback = as_of_fallback
                early_results[index] = self._failure_snapshot(
                    symbol=str(request.symbol or "").strip(),
                    market=str(request.market or "").strip().lower() or "unknown",
                    as_of=as_of_fallback,
                    end=end_fallback,
                    field_set=self._safe_field_set(request.field_set),
                    status=exc.status,
                    reason=exc.reason,
                    retryable=exc.retryable,
                    cache_key=None,
                )
                ordered_keys.append(None)
                continue

            cache_key, prepared_request = prepared
            ordered_keys.append(cache_key)
            key_to_request.setdefault(cache_key, prepared_request)

        key_results: Dict[str, ActualsSnapshot] = {}
        for cache_key, prepared_request in key_to_request.items():
            key_results[cache_key] = self._fetch_prepared(cache_key, prepared_request)

        results: List[ActualsSnapshot] = []
        for index, cache_key in enumerate(ordered_keys):
            if cache_key is None:
                results.append(early_results[index])
            else:
                results.append(key_results[cache_key])
        return results

    def clear_cache(self) -> None:
        """Drop the process-local actuals cache (tests and forced refresh)."""
        with self._lock:
            self._cache.clear()

    def cache_stats(self) -> Dict[str, int]:
        """Return bounded cache diagnostics."""
        with self._lock:
            return {
                "entries": len(self._cache),
                "inflight": len(self._inflight),
                "max_entries": self._cache_max_entries,
            }

    # ------------------------------------------------------------------
    # Core fetch path
    # ------------------------------------------------------------------

    def _fetch_request(self, request: ActualsRequest) -> ActualsSnapshot:
        try:
            cache_key, prepared = self._prepare_request(request)
        except _ActualsPrepError as exc:
            as_of_fallback = (
                request.as_of
                if isinstance(getattr(request, "as_of", None), date)
                and not isinstance(getattr(request, "as_of", None), datetime)
                else self._now_utc().date()
            )
            end_fallback = (
                request.end
                if isinstance(getattr(request, "end", None), date)
                and not isinstance(getattr(request, "end", None), datetime)
                else as_of_fallback
            )
            if end_fallback < as_of_fallback:
                end_fallback = as_of_fallback
            return self._failure_snapshot(
                symbol=str(request.symbol or "").strip(),
                market=str(request.market or "").strip().lower() or "unknown",
                as_of=as_of_fallback,
                end=end_fallback,
                field_set=self._safe_field_set(request.field_set),
                status=exc.status,
                reason=exc.reason,
                retryable=exc.retryable,
                cache_key=None,
            )
        return self._fetch_prepared(cache_key, prepared)

    def _fetch_prepared(
        self,
        cache_key: str,
        request: ActualsRequest,
    ) -> ActualsSnapshot:
        cached = self._cache_get(cache_key)
        if cached is not None:
            return self._clone_with_cache_hit(cached)

        future, is_owner = self._begin_inflight(cache_key)
        if not is_owner:
            try:
                return future.result()
            except Exception as exc:  # broad-exception: fallback_recorded - waiter maps shared failure to typed data_unavailable
                log_safe_exception(
                    logger,
                    "ActualsFetcher in-flight wait failed",
                    exc,
                    error_code="actuals_fetcher_inflight_wait_failed",
                    level=logging.WARNING,
                    context={"cache_key": cache_key},
                )
                return self._failure_snapshot(
                    symbol=request.symbol,
                    market=str(request.market or "unknown"),
                    as_of=request.as_of,
                    end=request.effective_end,
                    field_set=tuple(request.field_set),
                    status=ACTUALS_STATUS_DATA_UNAVAILABLE,
                    reason=REASON_UNEXPECTED,
                    retryable=True,
                    cache_key=cache_key,
                )

        try:
            snapshot = self._resolve_from_provider(request, cache_key=cache_key)
            # Cache every typed result for the short TTL. This is also the
            # retry cooldown: call_with_timeout cannot kill a hung provider
            # thread, so immediately reissuing would create a stampede.
            self._cache_put(cache_key, snapshot)
            future.set_result(snapshot)
            return snapshot
        except Exception as exc:  # broad-exception: fallback_recorded - owner never raises fabricated prices to waiters
            log_safe_exception(
                logger,
                "ActualsFetcher provider resolve failed unexpectedly",
                exc,
                error_code="actuals_fetcher_resolve_unexpected",
                level=logging.ERROR,
                context={"cache_key": cache_key, "symbol": request.symbol},
            )
            snapshot = self._failure_snapshot(
                symbol=request.symbol,
                market=str(request.market or "unknown"),
                as_of=request.as_of,
                end=request.effective_end,
                field_set=tuple(request.field_set),
                status=ACTUALS_STATUS_DATA_UNAVAILABLE,
                reason=REASON_UNEXPECTED,
                retryable=True,
                cache_key=cache_key,
            )
            self._cache_put(cache_key, snapshot)
            future.set_result(snapshot)
            return snapshot
        finally:
            self._end_inflight(cache_key, future)

    def _resolve_from_provider(
        self,
        request: ActualsRequest,
        *,
        cache_key: str,
    ) -> ActualsSnapshot:
        symbol = request.symbol
        market = str(request.market or detect_market(symbol)).strip().lower()
        field_set = tuple(request.field_set)
        as_of = request.as_of
        end = request.effective_end

        start_date = as_of - timedelta(days=self._lookback_calendar_days)
        end_date = end
        days = max((end_date - start_date).days + 1, self._lookback_calendar_days + 1)

        last_error: Optional[BaseException] = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                frame, source = self._call_manager_daily(
                    symbol=symbol,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    days=days,
                )
                return self._project_frame(
                    frame=frame,
                    source=source,
                    symbol=symbol,
                    market=market,
                    as_of=as_of,
                    end=end,
                    field_set=field_set,
                    cache_key=cache_key,
                )
            except LocalDataMissingError as exc:
                last_error = exc
                return self._failure_snapshot(
                    symbol=symbol,
                    market=market,
                    as_of=as_of,
                    end=end,
                    field_set=field_set,
                    status=ACTUALS_STATUS_DATA_UNAVAILABLE,
                    reason=REASON_LOCAL_DATA_MISSING,
                    retryable=True,
                    cache_key=cache_key,
                )
            except TimeoutError as exc:
                last_error = exc
                # The timeout helper returns promptly but cannot kill its
                # worker. Never start another overlapping outer attempt.
                return self._failure_snapshot(
                    symbol=symbol,
                    market=market,
                    as_of=as_of,
                    end=end,
                    field_set=field_set,
                    status=ACTUALS_STATUS_DATA_UNAVAILABLE,
                    reason=REASON_PROVIDER_TIMEOUT,
                    retryable=True,
                    cache_key=cache_key,
                )
            except (CircuitOpenError, DataSourceUnavailableError, DataFetchError) as exc:
                last_error = exc
                provider_failure_count = int(
                    getattr(exc, "provider_failure_count", 0) or 0
                )
                # Provider-chain exhaustion is terminal for this tick.
                return self._failure_snapshot(
                    symbol=symbol,
                    market=market,
                    as_of=as_of,
                    end=end,
                    field_set=field_set,
                    status=ACTUALS_STATUS_PROVIDER_DOWN,
                    reason=REASON_PROVIDER_FAILURE,
                    retryable=True,
                    cache_key=cache_key,
                    provider_failure_count=provider_failure_count,
                )
            except Exception as exc:  # broad-exception: fallback_recorded - unknown provider errors become data_unavailable
                last_error = exc
                log_safe_exception(
                    logger,
                    "ActualsFetcher provider call failed",
                    exc,
                    error_code="actuals_fetcher_provider_call_failed",
                    level=logging.WARNING,
                    context={
                        "symbol": sanitize_diagnostic_text(symbol, max_length=80),
                        "market": market,
                        "attempt": attempt,
                    },
                )
                if attempt < self._max_attempts:
                    continue
                return self._failure_snapshot(
                    symbol=symbol,
                    market=market,
                    as_of=as_of,
                    end=end,
                    field_set=field_set,
                    status=ACTUALS_STATUS_DATA_UNAVAILABLE,
                    reason=REASON_UNEXPECTED,
                    retryable=True,
                    cache_key=cache_key,
                )

        log_safe_exception(
            logger,
            "ActualsFetcher exhausted attempts without result",
            last_error or RuntimeError("no_result"),
            error_code="actuals_fetcher_exhausted",
            level=logging.ERROR,
            context={"symbol": symbol, "market": market},
        )
        return self._failure_snapshot(
            symbol=symbol,
            market=market,
            as_of=as_of,
            end=end,
            field_set=field_set,
            status=ACTUALS_STATUS_DATA_UNAVAILABLE,
            reason=REASON_UNEXPECTED,
            retryable=True,
            cache_key=cache_key,
        )

    def _call_manager_daily(
        self,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        days: int,
    ) -> Tuple[pd.DataFrame, str]:
        manager = self._get_manager()

        def _invoke() -> Tuple[pd.DataFrame, str]:
            return manager.get_daily_data(
                symbol,
                start_date=start_date,
                end_date=end_date,
                days=days,
            )

        return call_with_timeout(
            _invoke,
            timeout=self._request_timeout_seconds,
            call_name="actuals_fetcher.get_daily_data",
        )

    def _get_manager(self) -> Any:
        if self._manager is not None:
            return self._manager
        with self._lock:
            if self._manager is not None:
                return self._manager
            if self._manager_factory is not None:
                self._manager = self._manager_factory()
            else:
                from data_provider import DataFetcherManager

                self._manager = DataFetcherManager()
            return self._manager

    # ------------------------------------------------------------------
    # Projection / validation
    # ------------------------------------------------------------------

    def _project_frame(
        self,
        *,
        frame: Any,
        source: str,
        symbol: str,
        market: str,
        as_of: date,
        end: date,
        field_set: Tuple[str, ...],
        cache_key: str,
    ) -> ActualsSnapshot:
        if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
            return self._failure_snapshot(
                symbol=symbol,
                market=market,
                as_of=as_of,
                end=end,
                field_set=field_set,
                status=ACTUALS_STATUS_EMPTY,
                reason=REASON_EMPTY_FRAME,
                retryable=False,
                cache_key=cache_key,
                source=source or None,
            )

        normalized = self._normalize_daily_frame(frame)
        if normalized.empty:
            return self._failure_snapshot(
                symbol=symbol,
                market=market,
                as_of=as_of,
                end=end,
                field_set=field_set,
                status=ACTUALS_STATUS_EMPTY,
                reason=REASON_EMPTY_FRAME,
                retryable=False,
                cache_key=cache_key,
                source=source or None,
            )

        as_of_row = self._select_bar_on_or_before(normalized, as_of)
        if as_of_row is None:
            return self._failure_snapshot(
                symbol=symbol,
                market=market,
                as_of=as_of,
                end=end,
                field_set=field_set,
                status=ACTUALS_STATUS_EMPTY,
                reason=REASON_NO_BAR_FOR_AS_OF,
                retryable=False,
                cache_key=cache_key,
                source=source or None,
            )

        end_row = self._select_bar_on_or_before(normalized, end)
        if end_row is None or (
            end > as_of and self._coerce_bar_date(end_row.get("date")) != end
        ):
            return self._failure_snapshot(
                symbol=symbol,
                market=market,
                as_of=as_of,
                end=end,
                field_set=field_set,
                status=ACTUALS_STATUS_DATA_UNAVAILABLE,
                reason=REASON_NO_BAR_FOR_END,
                retryable=True,
                cache_key=cache_key,
                source=source or None,
            )

        if self._looks_delisted(normalized, as_of_row):
            return self._failure_snapshot(
                symbol=symbol,
                market=market,
                as_of=as_of,
                end=end,
                field_set=field_set,
                status=ACTUALS_STATUS_DELISTED,
                reason=REASON_DELISTED,
                retryable=False,
                cache_key=cache_key,
                source=source or None,
            )

        if self._looks_halted(as_of_row) or self._looks_halted(end_row):
            as_of_bar, end_bar, return_pct, finite_ok = self._build_bars(
                as_of_row=as_of_row,
                end_row=end_row,
                field_set=field_set,
            )
            if not finite_ok:
                return self._failure_snapshot(
                    symbol=symbol,
                    market=market,
                    as_of=as_of,
                    end=end,
                    field_set=field_set,
                    status=ACTUALS_STATUS_DATA_UNAVAILABLE,
                    reason=REASON_NON_FINITE,
                    retryable=False,
                    cache_key=cache_key,
                    source=source or None,
                )
            return ActualsSnapshot(
                symbol=symbol,
                market=market,
                as_of=as_of,
                end=end,
                status=ACTUALS_STATUS_HALTED,
                field_set=field_set,
                reason=REASON_HALTED_SESSION,
                retryable=False,
                as_of_bar=as_of_bar,
                end_bar=end_bar,
                return_pct=None,
                source=source or None,
                from_cache=False,
                fetched_at=self._now_utc(),
                cache_key=cache_key,
            )

        as_of_bar, end_bar, return_pct, finite_ok = self._build_bars(
            as_of_row=as_of_row,
            end_row=end_row,
            field_set=field_set,
        )
        if not finite_ok:
            return self._failure_snapshot(
                symbol=symbol,
                market=market,
                as_of=as_of,
                end=end,
                field_set=field_set,
                status=ACTUALS_STATUS_DATA_UNAVAILABLE,
                reason=REASON_NON_FINITE,
                retryable=False,
                cache_key=cache_key,
                source=source or None,
            )

        if FIELD_OHLC in field_set:
            if as_of_bar is None or as_of_bar.close is None:
                return self._failure_snapshot(
                    symbol=symbol,
                    market=market,
                    as_of=as_of,
                    end=end,
                    field_set=field_set,
                    status=ACTUALS_STATUS_DATA_UNAVAILABLE,
                    reason=REASON_NON_FINITE,
                    retryable=False,
                    cache_key=cache_key,
                    source=source or None,
                )

        return ActualsSnapshot(
            symbol=symbol,
            market=market,
            as_of=as_of,
            end=end,
            status=ACTUALS_STATUS_OK,
            field_set=field_set,
            reason=None,
            retryable=False,
            as_of_bar=as_of_bar,
            end_bar=end_bar,
            return_pct=return_pct,
            source=source or None,
            from_cache=False,
            fetched_at=self._now_utc(),
            cache_key=cache_key,
        )

    def _build_bars(
        self,
        *,
        as_of_row: pd.Series,
        end_row: pd.Series,
        field_set: Tuple[str, ...],
    ) -> Tuple[Optional[ActualsBar], Optional[ActualsBar], Optional[float], bool]:
        include_ohlc = FIELD_OHLC in field_set
        include_volume = FIELD_VOLUME in field_set
        include_return = FIELD_RETURN in field_set

        as_of_bar = self._row_to_bar(
            as_of_row,
            include_ohlc=include_ohlc or include_return,
            require_complete_ohlc=include_ohlc,
            include_volume=include_volume,
        )
        end_bar = self._row_to_bar(
            end_row,
            include_ohlc=include_ohlc or include_return,
            require_complete_ohlc=include_ohlc,
            include_volume=include_volume,
        )
        if as_of_bar is None or end_bar is None:
            return None, None, None, False

        return_pct: Optional[float] = None
        if include_return:
            if as_of_bar.close is None or end_bar.close is None:
                return None, None, None, False
            if as_of_bar.close == 0.0:
                return None, None, None, False
            raw_return = (end_bar.close - as_of_bar.close) / as_of_bar.close * 100.0
            if not self._is_finite_number(raw_return):
                return None, None, None, False
            return_pct = float(raw_return)

        if not include_ohlc:
            as_of_bar = ActualsBar(
                trade_date=as_of_bar.trade_date,
                close=as_of_bar.close if include_return else None,
                volume=as_of_bar.volume if include_volume else None,
            )
            end_bar = ActualsBar(
                trade_date=end_bar.trade_date,
                close=end_bar.close if include_return else None,
                volume=end_bar.volume if include_volume else None,
            )

        return as_of_bar, end_bar, return_pct, True

    def _row_to_bar(
        self,
        row: pd.Series,
        *,
        include_ohlc: bool,
        require_complete_ohlc: bool,
        include_volume: bool,
    ) -> Optional[ActualsBar]:
        trade_date = self._coerce_bar_date(row.get("date"))
        if trade_date is None:
            return None

        open_v = high_v = low_v = close_v = None
        if include_ohlc:
            open_v = self._finite_or_none(row.get("open"))
            high_v = self._finite_or_none(row.get("high"))
            low_v = self._finite_or_none(row.get("low"))
            close_v = self._finite_or_none(row.get("close"))
            if close_v is None or (
                require_complete_ohlc
                and None in (open_v, high_v, low_v, close_v)
            ):
                return None
            for column in ("open", "high", "low"):
                raw = row.get(column)
                if raw is not None and not (isinstance(raw, float) and math.isnan(raw)):
                    if self._finite_or_none(raw) is None and not self._is_missing(raw):
                        return None
            assert close_v is not None
            prices = [
                value
                for value in (open_v, high_v, low_v, close_v)
                if value is not None
            ]
            if min(prices) <= 0.0:
                return None
            if None not in (open_v, high_v, low_v, close_v):
                assert open_v is not None
                assert high_v is not None
                assert low_v is not None
                if low_v > min(open_v, close_v) or high_v < max(open_v, close_v):
                    return None
                if low_v > high_v:
                    return None

        volume_v = None
        if include_volume:
            volume_v = self._finite_or_none(row.get("volume"))
            raw_volume = row.get("volume")
            if (
                raw_volume is not None
                and not self._is_missing(raw_volume)
                and volume_v is None
            ):
                return None
            if volume_v is None or volume_v < 0.0:
                return None

        return ActualsBar(
            trade_date=trade_date,
            open=open_v,
            high=high_v,
            low=low_v,
            close=close_v,
            volume=volume_v,
        )

    def _normalize_daily_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        working = frame.copy()
        rename_map: Dict[str, str] = {}
        lower_cols = {str(col).strip().lower(): col for col in working.columns}
        aliases = {
            "date": ("date", "trade_date", "datetime", "day"),
            "open": ("open", "o"),
            "high": ("high", "h"),
            "low": ("low", "l"),
            "close": ("close", "c", "price"),
            "volume": ("volume", "vol", "v"),
        }
        for canonical, names in aliases.items():
            if canonical in working.columns:
                continue
            for name in names:
                if name in lower_cols:
                    rename_map[lower_cols[name]] = canonical
                    break
        if rename_map:
            working = working.rename(columns=rename_map)

        if "date" not in working.columns or "close" not in working.columns:
            return pd.DataFrame()

        working["date"] = working["date"].map(self._coerce_bar_date)
        working = working[working["date"].notna()].copy()
        if working.empty:
            return working

        for column in _PRICE_COLUMNS + ("volume",):
            if column in working.columns:
                working[column] = pd.to_numeric(working[column], errors="coerce")

        working = working.sort_values(by="date", kind="stable").drop_duplicates(
            subset=["date"], keep="last"
        )
        return working.reset_index(drop=True)

    def _select_bar_on_or_before(
        self,
        frame: pd.DataFrame,
        target: date,
    ) -> Optional[pd.Series]:
        eligible = frame[frame["date"] <= target]
        if eligible.empty:
            return None
        return eligible.iloc[-1]

    @staticmethod
    def _looks_halted(row: pd.Series) -> bool:
        """Conservative halt heuristic: zero volume with flat OHLC when present."""
        volume = row.get("volume")
        try:
            vol_num = float(volume) if volume is not None else None
        except (TypeError, ValueError):
            vol_num = None
        if vol_num is None or not math.isfinite(vol_num) or vol_num > 0:
            return False

        prices = []
        for column in _PRICE_COLUMNS:
            if column not in row.index:
                continue
            value = row.get(column)
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                prices.append(number)
        if len(prices) < 2:
            return False
        return max(prices) == min(prices)

    @staticmethod
    def _looks_delisted(frame: pd.DataFrame, row: pd.Series) -> bool:
        """Return True only on explicit delisting markers; never guess from gaps."""
        markers = ("退市", "delisted", "delisting")
        for value in row.index:
            text = str(row.get(value) or "").lower()
            if any(marker.lower() in text for marker in markers):
                return True
        for column in frame.columns:
            name = str(column).lower()
            if "status" not in name and "name" not in name:
                continue
            sample = frame[column].astype(str).str.lower()
            if sample.str.contains("退市|delisted|delisting", regex=True).any():
                return True
        return False

    # ------------------------------------------------------------------
    # Request preparation / cache keys
    # ------------------------------------------------------------------

    def _normalize_request(
        self,
        item: Union[ActualsRequest, Mapping[str, Any]],
    ) -> ActualsRequest:
        if isinstance(item, ActualsRequest):
            return item
        if not isinstance(item, Mapping):
            raise TypeError("requests must be ActualsRequest or mapping")
        as_of = item.get("as_of")
        end = item.get("end")
        return ActualsRequest(
            symbol=str(item.get("symbol") or ""),
            market=item.get("market"),
            as_of=self._coerce_date(as_of, field_name="as_of")
            if as_of is not None
            else date.min,
            end=None if end is None else self._coerce_date(end, field_name="end"),
            field_set=tuple(item.get("field_set") or DEFAULT_FIELD_SET),
        )

    def _prepare_request(
        self,
        request: ActualsRequest,
    ) -> Tuple[str, ActualsRequest]:
        raw_symbol = str(request.symbol or "").strip()
        if not raw_symbol:
            raise _ActualsPrepError(
                ACTUALS_STATUS_DATA_UNAVAILABLE,
                REASON_INVALID_SYMBOL,
                retryable=False,
            )

        market_hint = str(request.market or "").strip().lower() or None
        identity = resolve_daily_stock_identity(raw_symbol, market_hint=market_hint)
        if identity is not None:
            symbol = identity.normalized_code
            market = identity.market
        else:
            normalized = normalize_code(raw_symbol)
            symbol = normalized or raw_symbol
            market = market_hint or detect_market(symbol)

        try:
            as_of = self._coerce_date(request.as_of, field_name="as_of")
            end = (
                None
                if request.end is None
                else self._coerce_date(request.end, field_name="end")
            )
        except ValueError as exc:
            raise _ActualsPrepError(
                ACTUALS_STATUS_DATA_UNAVAILABLE,
                REASON_INVALID_WINDOW,
                retryable=False,
            ) from exc

        if as_of == date.min:
            raise _ActualsPrepError(
                ACTUALS_STATUS_DATA_UNAVAILABLE,
                REASON_INVALID_WINDOW,
                retryable=False,
            )
        effective_end = end if end is not None else as_of
        if effective_end < as_of:
            raise _ActualsPrepError(
                ACTUALS_STATUS_DATA_UNAVAILABLE,
                REASON_INVALID_WINDOW,
                retryable=False,
            )
        if (effective_end - as_of).days > MAX_WINDOW_CALENDAR_DAYS:
            raise _ActualsPrepError(
                ACTUALS_STATUS_DATA_UNAVAILABLE,
                REASON_INVALID_WINDOW,
                retryable=False,
            )
        if effective_end > self._now_utc().date():
            raise _ActualsPrepError(
                ACTUALS_STATUS_DATA_UNAVAILABLE,
                REASON_END_NOT_REACHED,
                retryable=True,
            )

        field_set = self._normalize_field_set(request.field_set)
        prepared = ActualsRequest(
            symbol=symbol,
            market=market,
            as_of=as_of,
            end=effective_end,
            field_set=field_set,
        )
        cache_key = self.build_cache_key(
            market=market,
            symbol=symbol,
            as_of=as_of,
            end=effective_end,
            field_set=field_set,
        )
        return cache_key, prepared

    @staticmethod
    def build_cache_key(
        *,
        market: str,
        symbol: str,
        as_of: date,
        end: date,
        field_set: Sequence[str],
    ) -> str:
        fields = ",".join(sorted({str(item).strip().lower() for item in field_set}))
        return (
            f"actuals:{str(market).strip().lower()}:"
            f"{str(symbol).strip().upper()}:"
            f"{as_of.isoformat()}:{end.isoformat()}:{fields}"
        )

    @staticmethod
    def _normalize_field_set(field_set: Optional[Sequence[str]]) -> Tuple[str, ...]:
        if field_set is None:
            return DEFAULT_FIELD_SET
        cleaned: List[str] = []
        for item in field_set:
            name = str(item or "").strip().lower()
            if not name:
                continue
            if name not in SUPPORTED_FIELD_SET:
                raise _ActualsPrepError(
                    ACTUALS_STATUS_DATA_UNAVAILABLE,
                    REASON_INVALID_WINDOW,
                    retryable=False,
                )
            if name not in cleaned:
                cleaned.append(name)
        if not cleaned:
            return DEFAULT_FIELD_SET
        return tuple(sorted(cleaned))

    @staticmethod
    def _safe_field_set(field_set: Optional[Sequence[str]]) -> Tuple[str, ...]:
        try:
            return ActualsFetcher._normalize_field_set(field_set)
        except _ActualsPrepError:
            return DEFAULT_FIELD_SET

    # ------------------------------------------------------------------
    # Cache / in-flight
    # ------------------------------------------------------------------

    def _cache_get(self, cache_key: str) -> Optional[ActualsSnapshot]:
        now = self._clock()
        with self._lock:
            item = self._cache.get(cache_key)
            if item is None:
                return None
            expires_at, snapshot = item
            if expires_at <= now:
                self._cache.pop(cache_key, None)
                return None
            return snapshot

    def _cache_put(self, cache_key: str, snapshot: ActualsSnapshot) -> None:
        expires_at = self._clock() + self._cache_ttl_seconds
        with self._lock:
            if len(self._cache) >= self._cache_max_entries and cache_key not in self._cache:
                oldest = next(iter(self._cache), None)
                if oldest is not None:
                    self._cache.pop(oldest, None)
            self._cache[cache_key] = (expires_at, snapshot)

    def _begin_inflight(self, cache_key: str) -> Tuple[Future, bool]:
        with self._lock:
            existing = self._inflight.get(cache_key)
            if existing is not None:
                return existing, False
            future: Future = Future()
            self._inflight[cache_key] = future
            return future, True

    def _end_inflight(self, cache_key: str, future: Future) -> None:
        with self._lock:
            current = self._inflight.get(cache_key)
            if current is future:
                self._inflight.pop(cache_key, None)

    @staticmethod
    def _clone_with_cache_hit(snapshot: ActualsSnapshot) -> ActualsSnapshot:
        return ActualsSnapshot(
            symbol=snapshot.symbol,
            market=snapshot.market,
            as_of=snapshot.as_of,
            end=snapshot.end,
            status=snapshot.status,
            field_set=snapshot.field_set,
            reason=snapshot.reason,
            retryable=snapshot.retryable,
            as_of_bar=snapshot.as_of_bar,
            end_bar=snapshot.end_bar,
            return_pct=snapshot.return_pct,
            source=snapshot.source,
            from_cache=True,
            fetched_at=snapshot.fetched_at,
            cache_key=snapshot.cache_key,
            provider_failure_count=snapshot.provider_failure_count,
        )

    # ------------------------------------------------------------------
    # Failure / helpers
    # ------------------------------------------------------------------

    def _failure_snapshot(
        self,
        *,
        symbol: str,
        market: str,
        as_of: date,
        end: date,
        field_set: Tuple[str, ...],
        status: str,
        reason: str,
        retryable: bool,
        cache_key: Optional[str],
        source: Optional[str] = None,
        provider_failure_count: int = 0,
    ) -> ActualsSnapshot:
        # Epic #1107: provider failure → data_unavailable/retry semantics for
        # scoring; prices stay unset so no fabricated hit is possible.
        effective_retryable = bool(retryable) or reason in RETRYABLE_REASONS
        return ActualsSnapshot(
            symbol=symbol,
            market=market,
            as_of=as_of,
            end=end,
            status=status,
            field_set=field_set,
            reason=reason,
            retryable=effective_retryable,
            as_of_bar=None,
            end_bar=None,
            return_pct=None,
            source=source,
            from_cache=False,
            fetched_at=self._now_utc(),
            cache_key=cache_key,
            provider_failure_count=provider_failure_count,
        )

    @staticmethod
    def _coerce_date(value: DateLike, *, field_name: str) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field_name} is required")
        try:
            return date.fromisoformat(text[:10])
        except ValueError as exc:
            raise ValueError(f"invalid {field_name}: {text!r}") from exc

    @staticmethod
    def _coerce_bar_date(value: Any) -> Optional[date]:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if hasattr(value, "to_pydatetime"):
            try:
                return value.to_pydatetime().date()
            except (TypeError, ValueError, AttributeError, OverflowError):
                pass
        if hasattr(value, "date") and callable(value.date):
            try:
                coerced = value.date()
                if isinstance(coerced, date):
                    return coerced
            except (TypeError, ValueError, AttributeError, OverflowError):
                pass
        text = str(value).strip()
        if not text or text.lower() in {"nat", "nan", "none"}:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    @staticmethod
    def _is_finite_number(value: Any) -> bool:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        return math.isfinite(number)

    @staticmethod
    def _is_missing(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, float) and math.isnan(value):
            return True
        if isinstance(value, str) and value.strip().lower() in {
            "",
            "-",
            "--",
            "n/a",
            "na",
            "none",
            "null",
            "nan",
        }:
            return True
        return False

    @classmethod
    def _finite_or_none(cls, value: Any) -> Optional[float]:
        if cls._is_missing(value):
            return None
        if not cls._is_finite_number(value):
            return None
        return float(value)


class _ActualsPrepError(Exception):
    """Internal preparation failure mapped to a typed ActualsSnapshot."""

    def __init__(self, status: str, reason: str, *, retryable: bool) -> None:
        self.status = status
        self.reason = reason
        self.retryable = retryable
        super().__init__(f"{status}:{reason}")
