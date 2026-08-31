# -*- coding: utf-8 -*-
"""Longbridge realtime methods: quote routing, static-info cache, volume ratio.

Method bodies are rebound onto ``LongbridgeFetcher`` by the compatibility
facade (ADR-006) so free-name lookups and test patches stay on
``src.data_provider.longbridge_fetcher``. Mirrors the parts layout of the other
provider packages.

Connection ownership deliberately stays on the facade. ``_get_ctx`` and
``_is_available`` read application config directly, and moving them would
introduce bare ``get_config()`` call sites into a new module, which
``scripts/check_config_access.py`` bans. The realtime cluster reaches them —
plus ``is_available_for_request``, ``_is_connection_error``,
``_mark_connection_cooldown``, and the static-info cache attributes — through
``self`` at call time.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple, Type

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.longbridge_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.longbridge_fetcher")
RealtimeSource = None  # type: ignore[assignment]
UnifiedRealtimeQuote = None  # type: ignore[assignment]
_static_info_ttl_seconds = None  # type: ignore[assignment]
_to_longbridge_symbol = None  # type: ignore[assignment]
safe_float = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _RealtimeMethods:
    """Source descriptors rebound onto ``LongbridgeFetcher``."""

    def _ts_sort_key(self, candle: Any) -> float:
        """Monotonic sort key for a candle timestamp (UTC seconds or datetime)."""
        ts = getattr(candle, "timestamp", None)
        if ts is None:
            return 0.0
        if hasattr(ts, "timestamp"):
            return float(ts.timestamp())
        return float(int(ts))

    def _compute_volume_ratio(self, symbol: str, today_volume: int) -> Optional[float]:
        """Compute volume_ratio = today_volume / avg(recent completed daily volumes).

        Uses the most recent daily bar as \"today/incomplete\" reference window: average
        volume of the next 5 older daily bars. Avoids local `date.today()` matching, which
        breaks for US symbols when the shell runs in CN timezone.
        """
        if not today_volume or today_volume <= 0:
            return None
        ctx = self._get_ctx()
        if ctx is None:
            return None
        try:
            from longbridge.openapi import Period, AdjustType

            # Keyword arguments keep this call compatible with Longbridge SDK
            # versions whose positional ``time`` and ``count`` order differs.
            candles = ctx.history_candlesticks_by_offset(
                symbol=symbol,
                period=Period.Day,
                adjust_type=AdjustType.NoAdjust,
                forward=False,
                time=datetime.now(),
                count=6,
            )
            if not candles or len(candles) < 2:
                return None

            ordered = sorted(candles, key=self._ts_sort_key, reverse=True)
            past_vols: list = []
            for c in ordered[1:6]:
                vol = int(getattr(c, "volume", 0) or 0)
                if vol > 0:
                    past_vols.append(vol)

            if not past_vols:
                return None

            avg_vol = sum(past_vols) / len(past_vols)
            if avg_vol <= 0:
                return None

            return round(today_volume / avg_vol, 2)
        except Exception as e:  # broad-exception: fallback_recorded - Safe diagnostics preserve the optional volume-ratio fallback.
            log_safe_exception(
                logger,
                "Longbridge volume ratio calculation failed",
                e,
                error_code="longbridge_volume_ratio_calculation_failed",
                level=logging.DEBUG,
                context={"symbol": symbol},
            )
            return None

    def _get_static_info(self, symbol: str) -> Optional[Any]:
        """Fetch static info (shares, EPS, BPS, name) with optional in-process TTL cache."""
        ttl = _static_info_ttl_seconds()
        now = time.time()
        if ttl > 0:
            with self._static_cache_lock:
                cached = self._static_cache.get(symbol)
                if cached and (now - cached[1]) < ttl:
                    return cached[0]

        ctx = self._get_ctx()
        if ctx is None:
            return None
        try:
            infos = ctx.static_info([symbol])
            if infos:
                info = infos[0]
                if ttl > 0:
                    with self._static_cache_lock:
                        self._static_cache[symbol] = (info, now)
                return info
        except Exception as e:
            log_safe_exception(
                logger,
                "Longbridge static info lookup failed",
                e,
                error_code="longbridge_static_info_lookup_failed",
                level=logging.DEBUG,
                context={"symbol": symbol},
            )
            if self._is_connection_error(e):
                self._mark_connection_cooldown(e)
        return None

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """Return stock name from Longbridge static_info (name_cn or name_en)."""
        symbol = _to_longbridge_symbol(stock_code)
        if symbol is None:
            return None
        info = self._get_static_info(symbol)
        if info is None:
            return None
        name = getattr(info, "name_cn", "") or getattr(info, "name_en", "") or ""
        return name.strip() or None

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """Fetch realtime quote from Longbridge, computing derived fields."""
        if not self.is_available_for_request("realtime_quote"):
            return None

        symbol = _to_longbridge_symbol(stock_code)
        if symbol is None:
            logger.debug(f"[Longbridge] 无法转换代码: {stock_code}")
            return None

        ctx = self._get_ctx()
        if ctx is None:
            return None

        try:
            quotes = ctx.quote([symbol])
            if not quotes:
                return None
            q = quotes[0]
        except Exception as e:
            log_safe_exception(
                logger,
                "Longbridge realtime quote request failed",
                e,
                error_code="longbridge_realtime_quote_failed",
                level=logging.INFO,
                context={"symbol": symbol},
            )
            if self._is_connection_error(e):
                self._mark_connection_cooldown(e)
            return None

        price = safe_float(getattr(q, "last_done", None))
        if price is None or price <= 0:
            return None

        prev_close = safe_float(getattr(q, "prev_close", None))
        open_price = safe_float(getattr(q, "open", None))
        high = safe_float(getattr(q, "high", None))
        low = safe_float(getattr(q, "low", None))
        volume = int(getattr(q, "volume", 0) or 0)
        turnover = safe_float(getattr(q, "turnover", None))

        change_amount = None
        change_pct = None
        amplitude = None
        if prev_close and prev_close > 0:
            change_amount = round(price - prev_close, 4)
            change_pct = round((price - prev_close) / prev_close * 100, 2)
            if high is not None and low is not None:
                amplitude = round((high - low) / prev_close * 100, 2)

        # Fetch static info for derived fields
        static = self._get_static_info(symbol)

        turnover_rate = None
        pe_ratio = None
        pb_ratio = None
        total_mv = None
        circ_mv = None
        name = ""

        if static is not None:
            name = getattr(static, "name_cn", "") or getattr(static, "name_en", "") or ""
            circulating = int(getattr(static, "circulating_shares", 0) or 0)
            total_shares = int(getattr(static, "total_shares", 0) or 0)
            eps_ttm = safe_float(getattr(static, "eps_ttm", None))
            eps_plain = safe_float(getattr(static, "eps", None))
            bps = safe_float(getattr(static, "bps", None))

            # US names often report circulating_shares=0 while total_shares is set — use total for turnover.
            shares_for_turnover = circulating if circulating > 0 else total_shares
            if shares_for_turnover > 0 and volume > 0:
                turnover_rate = round(volume / shares_for_turnover * 100, 4)
            elif volume > 0:
                logger.debug(
                    "[Longbridge] %s 无法计算换手率: volume=%s circulating=%s total_shares=%s",
                    symbol,
                    volume,
                    circulating,
                    total_shares,
                )

            eps_for_pe = None
            if eps_ttm is not None and eps_ttm > 0:
                eps_for_pe = eps_ttm
            elif eps_plain is not None and eps_plain > 0:
                eps_for_pe = eps_plain
            if eps_for_pe:
                pe_ratio = round(price / eps_for_pe, 2)

            if bps is not None and bps > 0:
                pb_ratio = round(price / bps, 2)
            if total_shares > 0:
                total_mv = round(price * total_shares, 2)
            if circulating > 0:
                circ_mv = round(price * circulating, 2)

        volume_ratio = self._compute_volume_ratio(symbol, volume)

        quote = UnifiedRealtimeQuote(
            code=stock_code,
            name=name,
            source=RealtimeSource.LONGBRIDGE,
            price=price,
            change_pct=change_pct,
            change_amount=change_amount,
            volume=volume if volume > 0 else None,
            amount=turnover,
            volume_ratio=volume_ratio,
            turnover_rate=turnover_rate,
            amplitude=amplitude,
            open_price=open_price,
            high=high,
            low=low,
            pre_close=prev_close,
            pe_ratio=pe_ratio,
            pb_ratio=pb_ratio,
            total_mv=total_mv,
            circ_mv=circ_mv,
        )

        logger.info(
            f"[Longbridge] {symbol} 行情获取成功: "
            f"价格={price}, 量比={volume_ratio}, 换手率={turnover_rate}"
        )
        return quote

EXPECTED_REALTIME_METHOD_NAMES: Tuple[str, ...] = (
    "_ts_sort_key",
    "_compute_volume_ratio",
    "_get_static_info",
    "get_stock_name",
    "get_realtime_quote",
)


def bind_realtime_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind realtime descriptors without changing the fetcher API."""

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
