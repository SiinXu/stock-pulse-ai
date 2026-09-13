# -*- coding: utf-8 -*-
"""
TickFlow data source adapter.

TickFlow is optional and fail-open in this project. The fetcher supports
general A-share daily K-lines/realtime quotes, keeps the existing market review
capability, and exposes advanced TickFlow-only helpers for future consumers.
"""

from __future__ import annotations

import logging
import math
import os
from datetime import datetime, timedelta, timezone
from threading import RLock
from time import monotonic
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from src.utils.sanitize import log_safe_exception

try:
    import exchange_calendars as xcals
except ImportError:  # pragma: no cover - optional dependency in lightweight installs.
    xcals = None

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - defensive fallback for old runtimes.
    ZoneInfo = None  # type: ignore

from .base import (
    BaseFetcher,
    DataFetchError,
    STANDARD_COLUMNS,
    is_bse_code,
    is_kc_cy_stock,
    is_st_stock,
    normalize_stock_code,
)
from .realtime_types import RealtimeSource, UnifiedRealtimeQuote, safe_int


logger = logging.getLogger(__name__)

_CN_MAIN_INDEX_QUOTES = (
    ("000001.SH", "000001", "\u4e0a\u8bc1\u6307\u6570"),
    ("399001.SZ", "399001", "\u6df1\u8bc1\u6210\u6307"),
    ("399006.SZ", "399006", "\u521b\u4e1a\u677f\u6307"),
    ("000688.SH", "000688", "\u79d1\u521b50"),
    ("000016.SH", "000016", "\u4e0a\u8bc150"),
    ("000300.SH", "000300", "\u6caa\u6df1300"),
)
_CN_UNIVERSE_ID = "CN_Equity_A"
_MAX_SYMBOLS_PER_QUOTE_REQUEST = 5
_CAPABILITY_NEGATIVE_CACHE_TTL_SECONDS = 900
_SECTOR_RANKINGS_CACHE_TTL_SECONDS = 300
_MAX_DAILY_PREFETCH_LOOKBACK_DAYS = 730
_MIN_DAILY_KLINE_COUNT = 30
_MAX_DAILY_KLINE_COUNT = 10000
_DAILY_KLINE_COUNT_MULTIPLIER = 1.8
_DAILY_KLINE_COUNT_BUFFER = 20
_SUPPORTED_KLINE_ADJUSTS = {
    "none",
    "forward",
    "backward",
    "forward_additive",
    "backward_additive",
}


def _parse_env_int(name: str, default: int, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not str(raw_value).strip():
        return default
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r; falling back to %s", name, raw_value, default)
        return default
    return max(minimum, parsed)


class TickFlowFetcher(BaseFetcher):
    """TickFlow-backed optional A-share fetcher."""

    name = "TickFlowFetcher"
    priority = 2

    def __init__(
        self,
        api_key: Optional[str],
        timeout: float = 30.0,
        *,
        kline_adjust: Optional[str] = None,
        batch_daily_enabled: Optional[bool] = None,
        batch_size: Optional[int] = None,
        priority: Optional[int] = None,
    ):
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        self.priority = self._normalize_priority(priority)
        self.kline_adjust = self._normalize_adjust(
            kline_adjust or os.getenv("TICKFLOW_KLINE_ADJUST", "none")
        )
        self.batch_daily_enabled = (
            self._parse_bool(os.getenv("TICKFLOW_BATCH_DAILY_ENABLED"), True)
            if batch_daily_enabled is None
            else bool(batch_daily_enabled)
        )
        self.batch_size = max(1, int(batch_size)) if batch_size is not None else _parse_env_int("TICKFLOW_BATCH_SIZE", 100)

        self._client = None
        self._client_lock = RLock()

        self._daily_cache: Dict[Tuple[str, str, str, str], pd.DataFrame] = {}
        self._daily_cache_lock = RLock()
        self._quote_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._quote_cache_lock = RLock()
        self._sector_rankings_cache: Optional[
            Tuple[float, List[Dict[str, Any]], List[Dict[str, Any]]]
        ] = None
        self._sector_rankings_cache_lock = RLock()

        self._capability_lock = RLock()
        self._capability_supported: Dict[str, Optional[bool]] = {
            "batch_daily": None,
            "universe_quotes": None,
        }
        self._capability_checked_at: Dict[str, float] = {}

    def close(self) -> None:
        """Close the underlying TickFlow client if it was created."""
        with self._client_lock:
            client = self._client
            self._client = None
        with self._capability_lock:
            for key in self._capability_supported:
                self._capability_supported[key] = None
            self._capability_checked_at.clear()
        if client is not None:
            try:
                client.close()
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "TickFlow client close failed",
                    exc,
                    error_code="tickflow_client_close_failed",
                    level=logging.DEBUG,
                )

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _build_client(self):
        from tickflow import TickFlow

        return TickFlow(api_key=self.api_key, timeout=self.timeout)

    def _get_client(self):
        if not self.api_key:
            return None
        if self._client is not None:
            return self._client

        with self._client_lock:
            if self._client is None:
                self._client = self._build_client()
            return self._client

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value in (None, "", "-"):
            return None
        try:
            numeric = float(value)
            if math.isnan(numeric):
                return None
            return numeric
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_bool(value: Optional[str], default: bool) -> bool:
        if value is None:
            return default
        normalized = value.strip().lower()
        if not normalized:
            return default
        return normalized not in {"0", "false", "no", "off"}

    @staticmethod
    def _normalize_priority(value: Optional[int]) -> int:
        if value is None:
            return _parse_env_int("TICKFLOW_PRIORITY", 2, minimum=0)
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            logger.warning("Invalid TickFlow priority=%r; falling back to 2", value)
            return 2

    @staticmethod
    def _normalize_adjust(value: Optional[str]) -> str:
        normalized = (value or "none").strip().lower()
        if normalized in _SUPPORTED_KLINE_ADJUSTS:
            return normalized
        logger.warning(
            "Invalid TICKFLOW_KLINE_ADJUST=%r; falling back to none",
            value,
        )
        return "none"

    @classmethod
    def _ratio_to_percent(cls, value: Any) -> Optional[float]:
        ratio = cls._safe_float(value)
        if ratio is None:
            return None
        return ratio * 100.0

    @classmethod
    def _ratio_series_to_percent(cls, series: pd.Series) -> pd.Series:
        return pd.to_numeric(series, errors="coerce") * 100.0

    @classmethod
    def _cn_lots_to_shares(cls, lots: Any, default: Optional[int] = None) -> Any:
        if isinstance(lots, pd.Series):
            return pd.to_numeric(lots, errors="coerce") * 100
        volume = safe_int(lots, default)
        if volume is None:
            return default
        return volume * 100

    @staticmethod
    def _extract_name(quote: Dict[str, Any]) -> str:
        ext = quote.get("ext") or {}
        name = ext.get("name") or quote.get("name") or ""
        return str(name).strip()

    @staticmethod
    def _is_permission_error(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        code = str(getattr(exc, "code", "") or "").upper()
        message = f"{getattr(exc, 'message', '')} {exc}".strip().lower()

        if status_code == 403:
            return True
        if code in {"PERMISSION_DENIED", "FORBIDDEN", "UNAUTHORIZED"}:
            return True
        return any(
            keyword in message
            for keyword in (
                "permission",
                "forbidden",
                "unauthorized",
                "not entitled",
                "no access",
                "\u6743\u9650",
                "\u65e0\u6743",
                "\u5957\u9910",
            )
        )

    @classmethod
    def _is_universe_permission_error(cls, exc: Exception) -> bool:
        message = f"{getattr(exc, 'message', '')} {exc}".strip().lower()
        return cls._is_permission_error(exc) or "universe" in message or "\u6807\u7684\u6c60" in message

    @staticmethod
    def _is_cn_equity_symbol(symbol: str) -> bool:
        normalized = normalize_stock_code(symbol)
        upper_symbol = (symbol or "").strip().upper()
        return (
            normalized.isdigit()
            and len(normalized) == 6
            and upper_symbol.endswith((".SH", ".SZ", ".BJ"))
        )

    @staticmethod
    def _round_limit_price(prev_close: float, ratio: float) -> float:
        return math.floor(prev_close * (1 + ratio) * 100 + 0.5) / 100.0

    @classmethod
    def _get_limit_ratio(cls, pure_code: str, name: str) -> float:
        if is_bse_code(pure_code):
            return 0.30
        if is_kc_cy_stock(pure_code):
            return 0.20
        if is_st_stock(name):
            return 0.05
        return 0.10

    @staticmethod
    def _coerce_frame(
        value: pd.DataFrame | list | dict | None,
    ) -> pd.DataFrame:
        if value is None:
            return pd.DataFrame()
        if isinstance(value, pd.DataFrame):
            return value.copy()
        if isinstance(value, list):
            return pd.DataFrame(value)
        if isinstance(value, dict):
            try:
                return pd.DataFrame(value)
            except ValueError as exc:
                if "all scalar values" in str(exc).lower():
                    return pd.DataFrame([value])
                raise
        return pd.DataFrame(value)

    @staticmethod
    def _exchange_from_code(stock_code: str) -> Optional[str]:
        upper = (stock_code or "").strip().upper()
        if upper.endswith(".SS"):
            return "SH"
        if upper.endswith((".SH", ".SZ", ".BJ")):
            return upper.rsplit(".", 1)[1]
        if upper.startswith(("SH.", "SS.")):
            return "SH"
        if upper.startswith("SZ."):
            return "SZ"
        if upper.startswith("BJ."):
            return "BJ"
        if upper.startswith("SH"):
            return "SH"
        if upper.startswith("SZ"):
            return "SZ"
        if upper.startswith("BJ"):
            return "BJ"
        return None

    @classmethod
    def _to_tickflow_symbol(cls, stock_code: str) -> Optional[str]:
        code = normalize_stock_code(stock_code)
        if not (code.isdigit() and len(code) == 6):
            return None

        exchange = cls._exchange_from_code(stock_code)
        if not exchange:
            if is_bse_code(code):
                exchange = "BJ"
            elif code.startswith(("6", "5")):
                exchange = "SH"
            elif code.startswith(("0", "1", "2", "3")):
                exchange = "SZ"
            else:
                return None
        return f"{code}.{exchange}"

    @staticmethod
    def _date_to_ms(date_str: str, *, end_of_day: bool = False) -> int:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if end_of_day:
            dt = dt + timedelta(days=1) - timedelta(milliseconds=1)
        if ZoneInfo is not None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        else:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
        return int(dt.timestamp() * 1000)

    @staticmethod
    def _extract_date_series(raw: pd.DataFrame) -> pd.Series:
        if "date" in raw.columns:
            return pd.to_datetime(raw["date"], errors="coerce").dt.normalize()
        if "trade_date" in raw.columns:
            return pd.to_datetime(raw["trade_date"], errors="coerce").dt.normalize()
        for column in ("timestamp", "time", "ts"):
            if column in raw.columns:
                numeric = pd.to_numeric(raw[column], errors="coerce")
                return pd.to_datetime(numeric, unit="ms", errors="coerce").dt.normalize()
        return pd.Series(pd.NaT, index=raw.index)

    @staticmethod
    def _daily_kline_count(start_date: str, end_date: str) -> int:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            calendar_days = max(1, (end - start).days + 1)
        except (TypeError, ValueError):
            calendar_days = 365
        estimated = int(calendar_days * _DAILY_KLINE_COUNT_MULTIPLIER) + _DAILY_KLINE_COUNT_BUFFER
        return max(_MIN_DAILY_KLINE_COUNT, min(_MAX_DAILY_KLINE_COUNT, estimated))

    @classmethod
    def _prepare_daily_frame(
        cls,
        value: pd.DataFrame | list | dict | None,
        *,
        symbol: str,
        start_date: str,
        end_date: str,
        count: int,
        context: str,
    ) -> pd.DataFrame:
        frame = cls._coerce_frame(value)
        if frame.empty:
            return frame

        dates = cls._extract_date_series(frame)
        valid_dates = dates.dropna()
        if valid_dates.empty:
            logger.warning(
                "[TickFlowFetcher] daily K-line response has no usable dates: symbol=%s context=%s rows=%d count=%d",
                symbol,
                context,
                len(frame),
                count,
            )
            return pd.DataFrame(columns=frame.columns)

        if cls._is_daily_frame_truncated(
            dates=valid_dates,
            start_date=start_date,
            end_date=end_date,
            count=count,
            returned_rows=len(frame),
        ):
            first_date = valid_dates.min().strftime("%Y-%m-%d")
            last_date = valid_dates.max().strftime("%Y-%m-%d")
            logger.warning(
                "[TickFlowFetcher] reject incomplete daily K-line response: symbol=%s context=%s "
                "start=%s end=%s first=%s last=%s rows=%d count=%d reason=count_cap",
                symbol,
                context,
                start_date,
                end_date,
                first_date,
                last_date,
                len(frame),
                count,
            )
            raise DataFetchError(
                "TickFlow daily K-line response may be truncated by count: "
                f"symbol={symbol} start={start_date} end={end_date} rows={len(frame)} count={count}"
            )

        start = pd.Timestamp(start_date).normalize()
        end = pd.Timestamp(end_date).normalize()
        in_range = dates.notna() & (dates >= start) & (dates <= end)
        if not in_range.any():
            return pd.DataFrame(columns=frame.columns)
        return frame.loc[in_range].reset_index(drop=True)

    @classmethod
    def _is_daily_frame_truncated(
        cls,
        *,
        dates: pd.Series,
        start_date: str,
        end_date: str,
        count: int,
        returned_rows: int,
    ) -> bool:
        if returned_rows < count:
            return False
        try:
            requested_start = datetime.strptime(start_date, "%Y-%m-%d")
        except (TypeError, ValueError):
            return False

        first_expected = cls._first_trading_date_on_or_after(requested_start)
        first_returned = dates.min().to_pydatetime().replace(tzinfo=None)
        return first_returned > first_expected

    @staticmethod
    def _first_trading_date_on_or_after(start_date: datetime) -> datetime:
        if xcals is not None:
            try:
                cal = xcals.get_calendar("XSHG")
                session = cal.date_to_session(start_date.date(), direction="next")
                return datetime.combine(session.date(), datetime.min.time())
            except Exception:
                pass
        current = start_date
        while current.weekday() >= 5:
            current += timedelta(days=1)
        return current

    def _daily_cache_key(self, symbol: str, start_date: str, end_date: str) -> Tuple[str, str, str, str]:
        return (symbol.upper(), start_date, end_date, self.kline_adjust)

    def _get_daily_cache(self, cache_key: Tuple[str, str, str, str]) -> Optional[pd.DataFrame]:
        with self._daily_cache_lock:
            cached = self._daily_cache.get(cache_key)
            if cached is not None:
                return cached.copy()
        return None

    def _set_daily_cache(self, cache_key: Tuple[str, str, str, str], df: pd.DataFrame) -> None:
        with self._daily_cache_lock:
            self._daily_cache[cache_key] = self._coerce_frame(df)

    def _capability_available(self, capability: str) -> bool:
        now = monotonic()
        with self._capability_lock:
            supported = self._capability_supported.get(capability)
            if supported is not False:
                return True
            checked_at = self._capability_checked_at.get(capability, 0.0)
            if now - checked_at >= _CAPABILITY_NEGATIVE_CACHE_TTL_SECONDS:
                self._capability_supported[capability] = None
                self._capability_checked_at.pop(capability, None)
                return True
            return False

    def _mark_capability(self, capability: str, supported: bool) -> None:
        with self._capability_lock:
            self._capability_supported[capability] = supported
            self._capability_checked_at[capability] = monotonic()

    @classmethod
    def _dedupe_symbols(cls, stock_codes: Iterable[str]) -> List[str]:
        symbols: List[str] = []
        seen = set()
        for stock_code in stock_codes:
            symbol = cls._to_tickflow_symbol(stock_code)
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            symbols.append(symbol)
        return symbols

    def prefetch_realtime_quotes(
        self,
        stock_codes: Iterable[str],
        *,
        batch_size: Optional[int] = None,
    ) -> int:
        """Batch-prefetch realtime quotes into the quote cache."""
        client = self._get_client()
        if client is None:
            return 0

        symbols = self._dedupe_symbols(stock_codes)
        if not symbols:
            return 0

        effective_batch_size = max(1, int(batch_size or self.batch_size))
        cached_count = 0
        for offset in range(0, len(symbols), effective_batch_size):
            batch_symbols = symbols[offset : offset + effective_batch_size]
            try:
                quotes = client.quotes.get(symbols=batch_symbols)
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "TickFlow batch realtime quote request failed",
                    exc,
                    error_code="tickflow_batch_realtime_quote_failed",
                    level=logging.WARNING,
                )
                continue
            cached_count += self._store_quotes(quotes)
        return cached_count

    def _store_quotes(self, quotes: Any) -> int:
        if not quotes:
            return 0
        if isinstance(quotes, dict):
            quotes_iter = [quotes]
        else:
            quotes_iter = list(quotes)
        stored = 0
        now = monotonic()
        with self._quote_cache_lock:
            for quote in quotes_iter:
                if not isinstance(quote, dict):
                    continue
                symbol = str(quote.get("symbol") or "").upper()
                if not symbol:
                    continue
                self._quote_cache[symbol] = (now, quote)
                stored += 1
        return stored

    def _get_cached_quote(self, symbol: str, ttl_seconds: Optional[int] = None) -> Optional[Dict[str, Any]]:
        ttl = 600 if ttl_seconds is None else max(0, int(ttl_seconds))
        now = monotonic()
        with self._quote_cache_lock:
            cached = self._quote_cache.get(symbol.upper())
            if not cached:
                return None
            cached_at, quote = cached
            if ttl and now - cached_at > ttl:
                self._quote_cache.pop(symbol.upper(), None)
                return None
            return dict(quote)

    @staticmethod
    def _get_realtime_cache_ttl() -> int:
        try:
            from src.config import get_config

            return int(get_config().realtime_cache_ttl)
        except Exception:
            return 600

    @staticmethod
    def _extract_universe_entries(universe: Any) -> List[Dict[str, str]]:
        if universe is None:
            return []
        if isinstance(universe, dict):
            raw_symbols = universe.get("symbols") or universe.get("data") or universe.get("items") or []
        else:
            raw_symbols = universe
        entries: List[Dict[str, str]] = []
        for item in raw_symbols:
            name = ""
            if isinstance(item, str):
                symbol = item
            elif isinstance(item, dict):
                symbol = item.get("symbol") or item.get("code") or ""
                ext = item.get("ext") or {}
                name = (
                    item.get("name")
                    or item.get("short_name")
                    or item.get("display_name")
                    or ext.get("name")
                    or ""
                )
            else:
                symbol = ""
            symbol = str(symbol).strip().upper()
            if symbol:
                entries.append({"symbol": symbol, "name": str(name).strip() if name else ""})
        return entries

    @staticmethod
    def _extract_universe_symbols(universe: Any) -> List[str]:
        return [entry["symbol"] for entry in TickFlowFetcher._extract_universe_entries(universe)]

    # Rebound from tickflow_parts.stock_identity after the class is built.
    get_stock_name = None

    _extract_instrument_name = None

    get_stock_list = None

    # Rebound from tickflow_parts.prefetch after the class is built.
    prefetch_daily_klines = None

    _iter_batch_frames = None

    # Rebound from tickflow_parts.market_boards after the class is built.
    get_main_indices = None

    get_market_stats = None

    get_sector_rankings = None

    # Rebound from tickflow_parts.history after the class is built.
    _fetch_raw_data = None

    _normalize_data = None

    # Rebound from tickflow_parts.realtime after the class is built.
    get_realtime_quote = None

    _quote_to_unified_quote = None

    _format_provider_timestamp = None


# Keep ``src.data_provider.tickflow_fetcher.TickFlowFetcher`` as the ADR-006
# compatibility facade while ``tickflow_parts`` owns market-board, daily
# history, realtime-quote, stock-identity, and daily-prefetch bodies. Rebinding
# preserves method globals so existing patches against this module continue to
# intercept moved implementations.
from .tickflow_parts import history as _history_module  # noqa: E402
from .tickflow_parts import market_boards as _market_boards_module  # noqa: E402
from .tickflow_parts import prefetch as _prefetch_module  # noqa: E402
from .tickflow_parts import realtime as _realtime_module  # noqa: E402
from .tickflow_parts import stock_identity as _stock_identity_module  # noqa: E402
from .tickflow_parts.history import _HistoryMethods  # noqa: E402
from .tickflow_parts.market_boards import _MarketBoardsMethods  # noqa: E402
from .tickflow_parts.prefetch import _PrefetchMethods  # noqa: E402
from .tickflow_parts.realtime import _RealtimeMethods  # noqa: E402
from .tickflow_parts.stock_identity import _StockIdentityMethods  # noqa: E402
from .tickflow_parts.facade_bind import bind_methods_from_class  # noqa: E402


def _assemble_tickflow_fetcher_facade() -> None:
    """Bind capability-domain method bodies onto the public fetcher class."""

    global _HistoryMethods, _MarketBoardsMethods, _PrefetchMethods, _RealtimeMethods, _StockIdentityMethods
    _MarketBoardsMethods = _market_boards_module._MarketBoardsMethods
    _HistoryMethods = _history_module._HistoryMethods
    _RealtimeMethods = _realtime_module._RealtimeMethods
    _StockIdentityMethods = _stock_identity_module._StockIdentityMethods
    _PrefetchMethods = _prefetch_module._PrefetchMethods
    bind_methods_from_class(
        _MarketBoardsMethods,
        TickFlowFetcher,
        globals(),
        expected_names=_market_boards_module.EXPECTED_MARKET_BOARD_METHOD_NAMES,
    )
    bind_methods_from_class(
        _HistoryMethods,
        TickFlowFetcher,
        globals(),
        expected_names=_history_module.EXPECTED_HISTORY_METHOD_NAMES,
    )
    bind_methods_from_class(
        _RealtimeMethods,
        TickFlowFetcher,
        globals(),
        expected_names=_realtime_module.EXPECTED_REALTIME_METHOD_NAMES,
    )
    bind_methods_from_class(
        _StockIdentityMethods,
        TickFlowFetcher,
        globals(),
        expected_names=_stock_identity_module.EXPECTED_STOCK_IDENTITY_METHOD_NAMES,
    )
    bind_methods_from_class(
        _PrefetchMethods,
        TickFlowFetcher,
        globals(),
        expected_names=_prefetch_module.EXPECTED_PREFETCH_METHOD_NAMES,
    )
    # Rebound methods are assigned after class body evaluation; clear ABC
    # abstracts that are now implemented so instantiation matches the legacy
    # monofile class (BaseFetcher marks _fetch_raw_data / _normalize_data).
    abstracts = set(getattr(TickFlowFetcher, "__abstractmethods__", ()))
    if abstracts:
        abstracts.difference_update(
            {
                name
                for name in (
                    "_fetch_raw_data",
                    "_normalize_data",
                    "get_daily_data",
                )
                if callable(getattr(TickFlowFetcher, name, None))
            }
        )
        abstracts = {
            name
            for name in abstracts
            if name not in TickFlowFetcher.__dict__
            or getattr(TickFlowFetcher.__dict__[name], "__isabstractmethod__", False)
        }
        TickFlowFetcher.__abstractmethods__ = frozenset(abstracts)


_assemble_tickflow_fetcher_facade()


def _install_part_reload_hooks() -> None:
    """Keep an owner reload able to rebuild and rebind both sides of the seam."""

    for module in (
        _market_boards_module,
        _history_module,
        _realtime_module,
        _stock_identity_module,
        _prefetch_module,
    ):
        module._FACADE_RELOAD_HOOK = _assemble_tickflow_fetcher_facade  # type: ignore[attr-defined]


_install_part_reload_hooks()
