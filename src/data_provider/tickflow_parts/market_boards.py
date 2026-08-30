# -*- coding: utf-8 -*-
"""TickFlow market-wide board methods: indices, market stats, sector rankings.

Method bodies are rebound onto ``TickFlowFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.tickflow_fetcher``. Mirrors the domain split of
``akshare_parts.market_boards`` and ``efinance_parts.market_boards``.

No module-level helper and no sibling method moves. Capability probing, client
access, symbol/name extraction, and the sector-rankings cache attributes all
stay on the facade; the rebind resolves free names from the facade globals and
sibling methods through ``self`` at call time.
"""

from __future__ import annotations

import logging
import math
from time import monotonic
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.tickflow_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.tickflow_fetcher")
_CN_MAIN_INDEX_QUOTES = ()  # type: ignore[assignment]
_CN_UNIVERSE_ID = ""  # type: ignore[assignment]
_MAX_SYMBOLS_PER_QUOTE_REQUEST = 0  # type: ignore[assignment]
_SECTOR_RANKINGS_CACHE_TTL_SECONDS = 0.0  # type: ignore[assignment]
normalize_stock_code = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _MarketBoardsMethods:
    """Source descriptors rebound onto ``TickFlowFetcher``."""

    def get_main_indices(self, region: str = "cn") -> Optional[List[Dict[str, Any]]]:
        """Fetch main A-share indices via TickFlow quotes."""
        if region != "cn":
            return None

        client = self._get_client()
        if client is None:
            return None

        symbols = [symbol for symbol, _, _ in _CN_MAIN_INDEX_QUOTES]
        quotes: List[Dict[str, Any]] = []
        for offset in range(0, len(symbols), _MAX_SYMBOLS_PER_QUOTE_REQUEST):
            batch_symbols = symbols[offset : offset + _MAX_SYMBOLS_PER_QUOTE_REQUEST]
            batch_quotes = client.quotes.get(symbols=batch_symbols)
            if batch_quotes:
                quotes.extend(batch_quotes)
        if not quotes:
            logger.warning("[TickFlowFetcher] empty index quotes")
            return None

        quotes_by_symbol = {
            str(item.get("symbol", "")).upper(): item for item in quotes if item
        }
        results: List[Dict[str, Any]] = []

        for symbol, code, name in _CN_MAIN_INDEX_QUOTES:
            quote = quotes_by_symbol.get(symbol)
            if not quote:
                continue

            ext = quote.get("ext") or {}
            current = self._safe_float(quote.get("last_price")) or 0.0
            prev_close = self._safe_float(quote.get("prev_close")) or 0.0
            change = self._safe_float(ext.get("change_amount"))
            if change is None:
                change = current - prev_close if current or prev_close else 0.0
            amplitude = self._ratio_to_percent(ext.get("amplitude"))
            if amplitude is None and prev_close > 0:
                high = self._safe_float(quote.get("high")) or 0.0
                low = self._safe_float(quote.get("low")) or 0.0
                amplitude = (high - low) / prev_close * 100

            results.append(
                {
                    "code": code,
                    "name": name,
                    "current": current,
                    "change": change,
                    "change_pct": self._ratio_to_percent(ext.get("change_pct")) or 0.0,
                    "open": self._safe_float(quote.get("open")) or 0.0,
                    "high": self._safe_float(quote.get("high")) or 0.0,
                    "low": self._safe_float(quote.get("low")) or 0.0,
                    "prev_close": prev_close,
                    "volume": self._safe_float(quote.get("volume")) or 0.0,
                    "amount": self._safe_float(quote.get("amount")) or 0.0,
                    "amplitude": amplitude or 0.0,
                }
            )

        if len(results) != len(_CN_MAIN_INDEX_QUOTES):
            logger.warning(
                "[TickFlowFetcher] incomplete index quotes: %s/%s",
                len(results),
                len(_CN_MAIN_INDEX_QUOTES),
            )
            return None

        return results or None

    def get_market_stats(self) -> Optional[Dict[str, Any]]:
        """Calculate A-share market breadth from TickFlow universe quotes."""
        client = self._get_client()
        if client is None:
            return None

        if not self._capability_available("universe_quotes"):
            return None

        try:
            quotes = client.quotes.get(universes=[_CN_UNIVERSE_ID])
            self._mark_capability("universe_quotes", True)
        except Exception as exc:  # broad-exception: fallback_recorded - Permission denials failover after a top-level record; other errors re-raise.
            log_safe_exception(
                logger,
                "TickFlow universe quotes failed",
                exc,
                error_code="tickflow_universe_quotes_failed",
                level=logging.ERROR,
                context={"capability": "universe_quotes"},
            )
            if self._is_universe_permission_error(exc):
                self._mark_capability("universe_quotes", False)
                logger.info(
                    "[TickFlowFetcher] universe quotes are not available; fallback to existing market stats sources"
                )
                return None
            raise
        if not quotes:
            logger.warning("[TickFlowFetcher] empty market stats quotes")
            return None

        stats = {
            "up_count": 0,
            "down_count": 0,
            "flat_count": 0,
            "limit_up_count": 0,
            "limit_down_count": 0,
            "total_amount": 0.0,
        }
        valid_rows = 0

        for quote in quotes:
            if not quote:
                continue

            symbol = str(quote.get("symbol") or "").strip().upper()
            if not self._is_cn_equity_symbol(symbol):
                continue

            amount = self._safe_float(quote.get("amount"))
            if amount is not None and amount > 0:
                stats["total_amount"] += amount / 1e8

            pure_code = normalize_stock_code(symbol)
            last_price = self._safe_float(quote.get("last_price"))
            prev_close = self._safe_float(quote.get("prev_close"))

            if last_price is None or prev_close is None or amount is None or amount <= 0:
                continue

            name = self._extract_name(quote)
            ratio = self._get_limit_ratio(pure_code, name)
            limit_up = self._round_limit_price(prev_close, ratio)
            limit_down = math.floor(prev_close * (1 - ratio) * 100 + 0.5) / 100.0
            limit_up_tolerance = round(abs(prev_close * (1 + ratio) - limit_up), 10)
            limit_down_tolerance = round(
                abs(prev_close * (1 - ratio) - limit_down), 10
            )

            valid_rows += 1

            if abs(last_price - limit_up) <= limit_up_tolerance:
                stats["limit_up_count"] += 1
            if abs(last_price - limit_down) <= limit_down_tolerance:
                stats["limit_down_count"] += 1

            if last_price > prev_close:
                stats["up_count"] += 1
            elif last_price < prev_close:
                stats["down_count"] += 1
            else:
                stats["flat_count"] += 1

        if valid_rows == 0:
            logger.warning("[TickFlowFetcher] no valid A-share rows for market stats")
            return None

        return stats

    def get_sector_rankings(self, n: int = 5) -> Optional[Tuple[List[Dict], List[Dict]]]:
        """Build SW1 industry rankings from TickFlow universes and A-share quotes."""
        try:
            limit = max(1, int(n))
        except (TypeError, ValueError):
            limit = 5

        now = monotonic()
        with self._sector_rankings_cache_lock:
            cached = self._sector_rankings_cache
            if cached and cached[0] > now:
                return [dict(row) for row in cached[1][:limit]], [dict(row) for row in cached[2][:limit]]

        client = self._get_client()
        if client is None or not self._capability_available("universe_quotes"):
            return None

        try:
            universes = client.universes.list()
            sw1_ids = [
                str(item.get("id"))
                for item in universes or []
                if isinstance(item, dict)
                and str(item.get("id") or "").startswith("CN_Equity_SW1_")
            ]
            if not sw1_ids:
                return None
            details = client.universes.batch(sw1_ids)
            quotes = client.quotes.get(universes=[_CN_UNIVERSE_ID])
            self._mark_capability("universe_quotes", True)
        except Exception as exc:  # broad-exception: fallback_recorded - Permission denials failover after a top-level record; other errors re-raise.
            log_safe_exception(
                logger,
                "TickFlow sector rankings fetch failed",
                exc,
                error_code="tickflow_sector_rankings_failed",
                level=logging.ERROR,
                context={"capability": "universe_quotes"},
            )
            if self._is_universe_permission_error(exc):
                self._mark_capability("universe_quotes", False)
                logger.info("[TickFlowFetcher] SW1 sector rankings are unavailable for current plan")
                return None
            raise

        quote_changes: Dict[str, float] = {}
        for quote in quotes or []:
            if not isinstance(quote, dict):
                continue
            symbol = str(quote.get("symbol") or "").strip().upper()
            ext = quote.get("ext") or {}
            change_pct = self._ratio_to_percent(ext.get("change_pct"))
            if change_pct is None:
                last_price = self._safe_float(quote.get("last_price"))
                prev_close = self._safe_float(quote.get("prev_close"))
                if last_price is not None and prev_close and prev_close > 0:
                    change_pct = (last_price - prev_close) / prev_close * 100
            if symbol and change_pct is not None:
                quote_changes[symbol] = change_pct

        industry_symbols: Dict[str, set[str]] = {}
        universe_by_id = {
            str(item.get("id")): item
            for item in universes or []
            if isinstance(item, dict) and item.get("id")
        }
        for universe_id, detail in (details or {}).items():
            summary = universe_by_id.get(str(universe_id), {})
            name = str(summary.get("name") or "").strip()
            if name.startswith("SW1"):
                name = name[3:].strip()
            if not name:
                continue
            industry_symbols.setdefault(name, set()).update(self._extract_universe_symbols(detail))

        rows: List[Dict[str, Any]] = []
        for name, symbols in industry_symbols.items():
            changes = [quote_changes[symbol] for symbol in symbols if symbol in quote_changes]
            if changes:
                rows.append(
                    {
                        "name": name,
                        "change_pct": round(sum(changes) / len(changes), 4),
                        "source": "tickflow_sw1",
                        "constituent_count": len(changes),
                    }
                )
        if not rows:
            return None

        descending = sorted(rows, key=lambda row: row["change_pct"], reverse=True)
        ascending = sorted(rows, key=lambda row: row["change_pct"])
        with self._sector_rankings_cache_lock:
            self._sector_rankings_cache = (
                now + _SECTOR_RANKINGS_CACHE_TTL_SECONDS,
                descending,
                ascending,
            )
        return [dict(row) for row in descending[:limit]], [dict(row) for row in ascending[:limit]]

EXPECTED_MARKET_BOARD_METHOD_NAMES: Tuple[str, ...] = (
    "get_main_indices",
    "get_market_stats",
    "get_sector_rankings",
)


def bind_market_boards_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind market-board descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _MarketBoardsMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_MARKET_BOARD_METHOD_NAMES,
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
