# -*- coding: utf-8 -*-
"""yfinance Yahoo symbol conversion and US/JP/KR/TW suffix classifiers.

Method bodies are rebound onto ``YfinanceFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.yfinance_fetcher``. Mirrors ``tushare_parts.symbols`` and
the domain split of ``history`` / ``realtime`` / ``main_indices`` in this
package.

The HTTP guard stays on the facade; this cluster never calls it. History and
realtime keep reaching conversion through ``self`` at call time. No sibling
method moves.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Tuple, Type

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.yfinance_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.yfinance_fetcher")
get_us_index_yf_symbol = None  # type: ignore[assignment]
is_us_stock_code = None  # type: ignore[assignment]
is_bse_code = None  # type: ignore[assignment]
is_suffix_market_symbol = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _SymbolMethods:
    """Source descriptors rebound onto ``YfinanceFetcher``."""

    @staticmethod
    def _is_jp_kr_suffix_stock(stock_code: str) -> bool:
        """Return True for supported JP/KR suffix-only Yahoo symbols."""
        return is_suffix_market_symbol(stock_code, "jp") or is_suffix_market_symbol(stock_code, "kr")

    @staticmethod
    def _is_tw_suffix_stock(stock_code: str) -> bool:
        """Return True for supported Taiwan suffix-only Yahoo symbols (TWSE `.TW` / TPEx `.TWO`).

        Taiwan base codes are 4-6 digits (common stocks 4, ETFs/others up to 6,
        e.g. 00878 / 006208), wider than the JP `.T` range.
        """
        return is_suffix_market_symbol(stock_code, "tw")

    def _convert_stock_code(self, stock_code: str) -> str:
        """
        转换股票代码为 Yahoo Finance 格式

        Yahoo Finance 代码格式：
        - A股沪市：600519.SS (Shanghai Stock Exchange)
        - A股深市：000001.SZ (Shenzhen Stock Exchange)
        - 港股：0700.HK (Hong Kong Stock Exchange)
        - 美股：AAPL, TSLA, GOOGL (无需后缀)

        Args:
            stock_code: 原始代码，如 '600519', 'hk00700', 'AAPL'

        Returns:
            Yahoo Finance 格式代码

        Examples:
            >>> fetcher._convert_stock_code('600519')
            '600519.SS'
            >>> fetcher._convert_stock_code('hk00700')
            '0700.HK'
            >>> fetcher._convert_stock_code('AAPL')
            'AAPL'
        """
        code = stock_code.strip().upper()

        # U.S. stocks indices: map to Yahoo Finance symbols (e.g., SPX -> ^GSPC)
        yf_symbol, _ = get_us_index_yf_symbol(code)
        if yf_symbol:
            logger.debug(f"识别为美股指数: {code} -> {yf_symbol}")
            return yf_symbol

        # U.S. stocks: 1-5 uppercase letters (optional .X suffix)
        if is_us_stock_code(code):
            logger.debug(f"识别为美股代码: {code}")
            return code

        # Japanese/Korean/Taiwan stocks MVP: Explicit Yahoo Finance suffix-only code, pass through to Yahoo as is.
        if self._is_jp_kr_suffix_stock(code) or self._is_tw_suffix_stock(code):
            logger.debug(f"识别为日韩台 Yahoo suffix 代码: {code}")
            return code

        # Hong Kong stocks: hk prefix -> .HK suffix
        if code.startswith('HK'):
            hk_code = code[2:].lstrip('0') or '0'  # Remove leading0, But retain at least one0
            hk_code = hk_code.zfill(4)  # Pad to 4 digits.
            logger.debug(f"转换港股代码: {stock_code} -> {hk_code}.HK")
            return f"{hk_code}.HK"

        # Bare Hong Kong codes use four or five digits. A-share and BSE codes
        # are six digits, so this branch cannot shadow their market routing.
        if code.isdigit() and 4 <= len(code) <= 5:
            hk_code = (code.lstrip('0') or '0').zfill(4)
            logger.debug(f"识别裸港股代码: {stock_code} -> {hk_code}.HK")
            return f"{hk_code}.HK"

        # Case with suffix already included
        if '.SS' in code or '.SZ' in code or '.HK' in code or '.BJ' in code:
            return code

        # Remove possible '.SH' suffix
        code = code.replace('.SH', '')

        # ETF: Shanghai ETF (51xx, 52xx, 56xx, 58xx) -> .SS; Shenzhen ETF (15xx, 16xx, 18xx) -> .SZ
        if len(code) == 6:
            if code.startswith(('51', '52', '56', '58')):
                return f"{code}.SS"
            if code.startswith(('15', '16', '18')):
                return f"{code}.SZ"

        # BSE (Beijing Stock Exchange): 8xxxxx, 4xxxxx, 920xxx
        if is_bse_code(code):
            base = code.split('.')[0] if '.' in code else code
            return f"{base}.BJ"

        # A-shares: Determine the market based on code prefix
        if code.startswith(('600', '601', '603', '688')):
            return f"{code}.SS"
        elif code.startswith(('000', '002', '300')):
            return f"{code}.SZ"
        else:
            logger.warning(f"无法确定股票 {code} 的市场，默认使用深市")
            return f"{code}.SZ"

    def _is_us_stock(self, stock_code: str) -> bool:
        """
        判断代码是否为美股股票（排除美股指数）。

        委托给 us_index_mapping 模块的 is_us_stock_code()。
        """
        return is_us_stock_code(stock_code)


EXPECTED_SYMBOL_METHOD_NAMES: Tuple[str, ...] = (
    "_is_jp_kr_suffix_stock",
    "_is_tw_suffix_stock",
    "_convert_stock_code",
    "_is_us_stock",
)


def bind_symbol_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind symbol-conversion descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _SymbolMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_SYMBOL_METHOD_NAMES,
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
