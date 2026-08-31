# -*- coding: utf-8 -*-
"""Tushare realtime quote methods: Pro quote plus legacy-symbol fallback.

Method bodies are rebound onto ``TushareFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.tushare_fetcher``. Mirrors the domain split of
``efinance_parts.realtime``.

No sibling method moves. Chip distribution, ``get_trade_time``, and the
trade-calendar helpers stay on the facade. The rate-limited API client
(``_api``, ``_check_rate_limit``, ``_call_api_with_rate_limit``) and the
symbol converters (``_detect_exchange_hint``, ``_convert_stock_code``) are
reached through ``self`` / ``cls`` at call time.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Tuple, Type

from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.tushare_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.tushare_fetcher")
UnifiedRealtimeQuote = None  # type: ignore[assignment]
_is_hk_market = None  # type: ignore[assignment]
is_bse_code = None  # type: ignore[assignment]
normalize_stock_code = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _RealtimeMethods:
    """Source descriptors rebound onto ``TushareFetcher``."""

    @classmethod
    def _get_legacy_realtime_symbol(cls, stock_code: str) -> str:
        """Build the legacy tushare symbol while preserving explicit SH/SZ hints."""
        code = normalize_stock_code(stock_code)
        exchange_hint = cls._detect_exchange_hint(stock_code)

        if code == '000001' and exchange_hint == 'SH':
            return 'sh000001'
        if code == '399001':
            return 'sz399001'
        if code == '399006':
            return 'sz399006'
        if code == '000300':
            return 'sh000300'
        if is_bse_code(code):
            return f"bj{code}"
        return code

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取实时行情

        策略：
        1. 优先尝试 Pro 接口（需要2000积分）：数据全，稳定性高
        2. 失败降级到旧版接口：门槛低，数据较少

        Args:
            stock_code: 股票代码

        Returns:
            UnifiedRealtimeQuote 对象，失败返回 None
        """
        if self._api is None:
            return None

        # HK stocks not supported by Tushare
        if _is_hk_market(stock_code):
            logger.debug(f"TushareFetcher 跳过港股实时行情 {stock_code}")
            return None

        normalized_code = normalize_stock_code(stock_code)

        from .realtime_types import (
            RealtimeSource,
            safe_float, safe_int
        )

        # Rate limit check.
        self._check_rate_limit()

        # Try Pro interface
        try:
            ts_code = self._convert_stock_code(stock_code)
            # Attempt to call Pro real-time interface (requires points)
            df = self._api.quotation(ts_code=ts_code)

            if df is not None and not df.empty:
                row = df.iloc[0]
                logger.debug(f"Tushare Pro 实时行情获取成功: {stock_code}")

                return UnifiedRealtimeQuote(
                    code=normalized_code,
                    name=str(row.get('name', '')),
                    source=RealtimeSource.TUSHARE,
                    price=safe_float(row.get('price')),
                    change_pct=safe_float(row.get('pct_chg')),  # The Pro interface usually directly returns percentage change
                    change_amount=safe_float(row.get('change')),
                    volume=safe_int(row.get('vol')),
                    amount=safe_float(row.get('amount')),
                    high=safe_float(row.get('high')),
                    low=safe_float(row.get('low')),
                    open_price=safe_float(row.get('open')),
                    pre_close=safe_float(row.get('pre_close')),
                    turnover_rate=safe_float(row.get('turnover_ratio')), # The Pro interface may have turnover rates
                    pe_ratio=safe_float(row.get('pe')),
                    pb_ratio=safe_float(row.get('pb')),
                    total_mv=safe_float(row.get('total_mv')),
                )
        except Exception as e:
            # Log at debug level and continue to the fallback interface
            log_safe_exception(
                logger,
                "Tushare Pro realtime quote unavailable; trying legacy fallback",
                e,
                error_code="tushare_pro_realtime_quote_unavailable",
                level=logging.DEBUG,
                context={"symbol": stock_code},
            )

        # Fallback: try the legacy interface
        try:
            import tushare as ts

            symbol = self._get_legacy_realtime_symbol(stock_code)

            # Call the old real-time interface (ts.get_realtime_quotes)
            df = ts.get_realtime_quotes(symbol)

            if df is None or df.empty:
                return None

            row = df.iloc[0]

            # Calculate Percentage Change
            price = safe_float(row['price'])
            pre_close = safe_float(row['pre_close'])
            change_pct = 0.0
            change_amount = 0.0

            if price and pre_close and pre_close > 0:
                change_amount = price - pre_close
                change_pct = (change_amount / pre_close) * 100

            # Build unified object
            return UnifiedRealtimeQuote(
                code=normalized_code,
                name=str(row['name']),
                source=RealtimeSource.TUSHARE,
                price=price,
                change_pct=round(change_pct, 2),
                change_amount=round(change_amount, 2),
                volume=safe_int(row['volume']) // 100,  # Convert shares to lots
                amount=safe_float(row['amount']),
                high=safe_float(row['high']),
                low=safe_float(row['low']),
                open_price=safe_float(row['open']),
                pre_close=pre_close,
            )

        except Exception as e:
            log_safe_exception(
                logger,
                "Tushare legacy realtime quote failed",
                e,
                error_code="tushare_legacy_realtime_quote_failed",
                level=logging.WARNING,
                context={"symbol": stock_code},
            )
            return None


EXPECTED_REALTIME_METHOD_NAMES: Tuple[str, ...] = (
    "_get_legacy_realtime_symbol",
    "get_realtime_quote",
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
