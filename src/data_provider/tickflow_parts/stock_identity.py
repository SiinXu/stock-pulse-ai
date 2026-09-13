# -*- coding: utf-8 -*-
"""TickFlow stock identity methods: name lookup and universe list.

Method bodies are rebound onto ``TickFlowFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.tickflow_fetcher``. Mirrors the Tushare stock-name owner
split without importing that package.

No tenacity wrapper and no sibling method moves. Universe helpers, quote-cache
helpers, the default name-lookup TTL, client access, and name extraction stay
on the facade; the rebind resolves free names from the facade globals and
sibling methods through ``self`` at call time.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Tuple, Type

import pandas as pd

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.tickflow_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.tickflow_fetcher")
normalize_stock_code = None  # type: ignore[assignment]
_CN_UNIVERSE_ID = ""  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _StockIdentityMethods:
    """Source descriptors rebound onto ``TickFlowFetcher``."""

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        symbol = self._to_tickflow_symbol(stock_code)
        quote = self._get_cached_quote(symbol) if symbol else None
        name = self._extract_name(quote or {}) if quote else ""
        if name:
            return name

        client = self._get_client()
        if client is None or not symbol:
            return None

        try:
            quotes = client.quotes.get(symbols=[symbol])
            self._store_quotes(quotes)
            cached = self._get_cached_quote(symbol)
            name = self._extract_name(cached or {})
            if name:
                return name
        except Exception as exc:
            log_safe_exception(
                logger,
                "TickFlow quote name lookup failed",
                exc,
                error_code="tickflow_quote_name_lookup_failed",
                level=logging.DEBUG,
                context={"symbol": symbol},
            )

        try:
            instrument = client.instruments.get(symbol)
            return self._extract_instrument_name(instrument)
        except Exception as exc:
            log_safe_exception(
                logger,
                "TickFlow instrument lookup failed",
                exc,
                error_code="tickflow_instrument_lookup_failed",
                level=logging.DEBUG,
                context={"symbol": symbol},
            )
        return None

    @staticmethod
    def _extract_instrument_name(instrument: Any) -> Optional[str]:
        if isinstance(instrument, list):
            if not instrument:
                return None
            instrument = instrument[0]
        if not isinstance(instrument, dict):
            return None
        name = (
            instrument.get("name")
            or instrument.get("short_name")
            or instrument.get("display_name")
            or (instrument.get("ext") or {}).get("name")
        )
        return str(name).strip() if name else None

    def get_stock_list(self) -> pd.DataFrame:
        client = self._get_client()
        if client is None:
            return pd.DataFrame(columns=["code", "name", "industry", "area", "market"])

        try:
            universe = client.universes.get(_CN_UNIVERSE_ID)
            entries = self._extract_universe_entries(universe)
        except Exception as exc:
            if self._is_universe_permission_error(exc):
                logger.info("[TickFlowFetcher] universe list is not available for current plan")
                return pd.DataFrame(columns=["code", "name", "industry", "area", "market"])
            log_safe_exception(
                logger,
                "TickFlow stock universe lookup failed",
                exc,
                error_code="tickflow_stock_universe_lookup_failed",
                level=logging.WARNING,
                context={"universe": _CN_UNIVERSE_ID},
            )
            return pd.DataFrame(columns=["code", "name", "industry", "area", "market"])

        rows = []
        for entry in entries:
            symbol = entry["symbol"]
            if not self._is_cn_equity_symbol(symbol):
                continue
            rows.append(
                {
                    "code": normalize_stock_code(symbol),
                    "name": entry.get("name", ""),
                    "industry": "",
                    "area": "",
                    "market": symbol.rsplit(".", 1)[-1],
                }
            )
        return pd.DataFrame(rows, columns=["code", "name", "industry", "area", "market"])


EXPECTED_STOCK_IDENTITY_METHOD_NAMES: Tuple[str, ...] = (
    "get_stock_name",
    "_extract_instrument_name",
    "get_stock_list",
)


def bind_stock_identity_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind stock-identity descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _StockIdentityMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_STOCK_IDENTITY_METHOD_NAMES,
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
