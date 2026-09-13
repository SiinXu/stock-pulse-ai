# -*- coding: utf-8 -*-
"""TickFlow realtime quote methods: single-quote fetch and mapping.

Method bodies are rebound onto ``TickFlowFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.tickflow_fetcher``. Mirrors the yfinance and Tushare
realtime owner split without importing those packages.

No tenacity wrapper and no sibling method moves. Symbol conversion, quote
cache helpers, ``_get_realtime_cache_ttl``, client access, and mapping
helpers stay on the facade; the rebind resolves free names from the facade
globals and sibling methods through ``self`` at call time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple, Type

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.tickflow_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.tickflow_fetcher")
normalize_stock_code = None  # type: ignore[assignment]
UnifiedRealtimeQuote = None  # type: ignore[assignment]
RealtimeSource = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _RealtimeMethods:
    """Source descriptors rebound onto ``TickFlowFetcher``."""

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        symbol = self._to_tickflow_symbol(stock_code)
        if not symbol:
            return None

        quote_ttl = self._get_realtime_cache_ttl()
        quote = self._get_cached_quote(symbol, quote_ttl)
        if quote is None:
            client = self._get_client()
            if client is None:
                return None
            try:
                quotes = client.quotes.get(symbols=[symbol])
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "TickFlow realtime quote request failed",
                    exc,
                    error_code="tickflow_realtime_quote_failed",
                    level=logging.WARNING,
                    context={"symbol": symbol},
                )
                return None
            self._store_quotes(quotes)
            quote = self._get_cached_quote(symbol, quote_ttl)

        if not quote:
            return None
        return self._quote_to_unified_quote(stock_code, quote)

    def _quote_to_unified_quote(
        self,
        stock_code: str,
        quote: Dict[str, Any],
    ) -> Optional[UnifiedRealtimeQuote]:
        symbol = str(quote.get("symbol") or self._to_tickflow_symbol(stock_code) or "").upper()
        code = normalize_stock_code(stock_code or symbol)
        current = self._safe_float(quote.get("last_price"))
        if current is None:
            current = self._safe_float(quote.get("price"))
        if current is None:
            return None

        ext = quote.get("ext") or {}
        prev_close = self._safe_float(quote.get("prev_close"))
        open_price = self._safe_float(quote.get("open"))
        high = self._safe_float(quote.get("high"))
        low = self._safe_float(quote.get("low"))
        volume = self._cn_lots_to_shares(quote.get("volume"), default=0)
        amount = self._safe_float(quote.get("amount")) or 0.0
        change_amount = self._safe_float(ext.get("change_amount"))
        if change_amount is None and prev_close is not None:
            change_amount = current - prev_close

        change_pct = self._ratio_to_percent(ext.get("change_pct"))
        if change_pct is None and prev_close and prev_close > 0:
            change_pct = (current - prev_close) / prev_close * 100.0

        timestamp = quote.get("timestamp") or quote.get("time") or quote.get("ts")
        provider_timestamp = self._format_provider_timestamp(timestamp)

        return UnifiedRealtimeQuote(
            code=code,
            name=self._extract_name(quote),
            price=current,
            change_pct=change_pct,
            change_amount=change_amount,
            volume=volume,
            amount=amount,
            open_price=open_price,
            high=high,
            low=low,
            pre_close=prev_close,
            source=RealtimeSource.TICKFLOW,
            provider_timestamp=provider_timestamp,
            turnover_rate=self._ratio_to_percent(ext.get("turnover_rate")),
            amplitude=self._ratio_to_percent(ext.get("amplitude")),
        )

    @staticmethod
    def _format_provider_timestamp(value: Any) -> Optional[str]:
        if value in (None, ""):
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return str(value)
        if numeric <= 0:
            return None
        if numeric > 10_000_000_000:
            numeric = numeric / 1000.0
        return datetime.fromtimestamp(numeric, timezone.utc).isoformat()


EXPECTED_REALTIME_METHOD_NAMES: Tuple[str, ...] = (
    "get_realtime_quote",
    "_quote_to_unified_quote",
    "_format_provider_timestamp",
)


def bind_realtime_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind realtime-quote descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _RealtimeMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_REALTIME_METHOD_NAMES,
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
