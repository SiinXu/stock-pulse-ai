# -*- coding: utf-8 -*-
"""TickFlow daily K-line and realtime quote prefetch methods.

Method bodies are rebound onto ``TickFlowFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.tickflow_fetcher``.

No tenacity wrapper and no sibling method moves. Client access, capability
helpers, daily-cache/history helpers, quote-cache/TTL, ``_dedupe_symbols``,
and universe parse stay on the facade; the rebind resolves free names from
the facade globals and sibling methods through ``self`` at call time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Type

import pandas as pd

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.tickflow_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.tickflow_fetcher")
DataFetchError = Exception  # type: ignore[assignment,misc]
_MAX_DAILY_PREFETCH_LOOKBACK_DAYS = 0  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _PrefetchMethods:
    """Source descriptors rebound onto ``TickFlowFetcher``."""

    def prefetch_daily_klines(
        self,
        stock_codes: Iterable[str],
        *,
        days: int = 30,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        """Batch-prefetch daily K-lines into the per-process raw cache.

        Args:
            stock_codes: Project stock codes to prefetch.
            days: Target trading days to cover. When start_date is omitted,
                up to days * 2 calendar days are fetched, capped at 730 days.
            start_date: Optional YYYY-MM-DD lower bound.
            end_date: Optional YYYY-MM-DD upper bound.
        """
        if not self.batch_daily_enabled or not self._capability_available("batch_daily"):
            return 0

        try:
            requested_days = int(days)
        except (TypeError, ValueError):
            logger.info(
                "[TickFlowFetcher] skip daily K-line prefetch because days is invalid: %r",
                days,
            )
            return 0
        if requested_days <= 0:
            logger.info(
                "[TickFlowFetcher] skip daily K-line prefetch because days must be positive: %r",
                days,
            )
            return 0

        client = self._get_client()
        if client is None:
            return 0

        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            lookback_days = min(requested_days * 2, _MAX_DAILY_PREFETCH_LOOKBACK_DAYS)
            start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=lookback_days)
            start_date = start_dt.strftime("%Y-%m-%d")

        symbols = self._dedupe_symbols(stock_codes)
        if not symbols:
            return 0

        batch_count = (len(symbols) + self.batch_size - 1) // self.batch_size
        cached_count = 0
        for offset in range(0, len(symbols), self.batch_size):
            batch_symbols = symbols[offset : offset + self.batch_size]
            try:
                request_count = self._daily_kline_count(start_date, end_date)
                batch_result = client.klines.batch(
                    batch_symbols,
                    period="1d",
                    count=request_count,
                    start_time=self._date_to_ms(start_date),
                    end_time=self._date_to_ms(end_date, end_of_day=True),
                    adjust=self.kline_adjust,
                    as_dataframe=True,
                )
                self._mark_capability("batch_daily", True)
            except Exception as exc:
                if self._is_permission_error(exc):
                    self._mark_capability("batch_daily", False)
                    logger.info(
                        "[TickFlowFetcher] batch daily K-line is not available; fallback to single requests"
                    )
                    logger.info(
                        "[TickFlowFetcher] batch daily prefetch complete: cached=%d total=%d batches=%d",
                        cached_count,
                        len(symbols),
                        batch_count,
                    )
                    return cached_count
                log_safe_exception(
                    logger,
                    "TickFlow batch daily K-line request failed",
                    exc,
                    error_code="tickflow_batch_daily_kline_failed",
                    level=logging.WARNING,
                )
                continue

            for symbol, df in self._iter_batch_frames(batch_result):
                if not symbol:
                    continue
                cache_key = self._daily_cache_key(symbol, start_date, end_date)
                try:
                    frame = self._prepare_daily_frame(
                        df,
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                        count=request_count,
                        context="batch",
                    )
                except DataFetchError:
                    continue
                if frame.empty:
                    continue
                self._set_daily_cache(cache_key, frame)
                cached_count += 1

        logger.info(
            "[TickFlowFetcher] batch daily prefetch complete: cached=%d total=%d batches=%d",
            cached_count,
            len(symbols),
            batch_count,
        )
        return cached_count

    @staticmethod
    def _iter_batch_frames(batch_result: Any) -> Iterable[Tuple[str, Any]]:
        if isinstance(batch_result, dict):
            for symbol, df in batch_result.items():
                yield str(symbol).upper(), df
            return

        if isinstance(batch_result, pd.DataFrame):
            if "symbol" not in batch_result.columns:
                return
            for symbol, group in batch_result.groupby("symbol"):
                yield str(symbol).upper(), group.reset_index(drop=True)
            return

        if isinstance(batch_result, list):
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for item in batch_result:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol") or "").upper()
                if not symbol:
                    continue
                grouped.setdefault(symbol, []).append(item)
            for symbol, rows in grouped.items():
                yield symbol, pd.DataFrame(rows)


class _RealtimePrefetchMethods:
    """Realtime quote prefetch descriptors rebound onto ``TickFlowFetcher``."""

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


EXPECTED_PREFETCH_METHOD_NAMES: Tuple[str, ...] = (
    "prefetch_daily_klines",
    "_iter_batch_frames",
)

EXPECTED_REALTIME_PREFETCH_METHOD_NAMES: Tuple[str, ...] = (
    "prefetch_realtime_quotes",
)


def bind_prefetch_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind daily-prefetch descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _PrefetchMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_PREFETCH_METHOD_NAMES,
    )


def bind_realtime_prefetch_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind realtime-prefetch descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _RealtimePrefetchMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_REALTIME_PREFETCH_METHOD_NAMES,
    )


def _install_facade_reload_hook(hook: Callable[[], None]) -> None:
    """Register the loaded facade assembly callback for owner reloads."""

    global _FACADE_RELOAD_HOOK
    _FACADE_RELOAD_HOOK = hook


def _rebind_loaded_facade() -> None:
    """Refresh a registered facade after this owner module is reloaded."""

    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
