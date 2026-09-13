# -*- coding: utf-8 -*-
"""efinance symbol / market classifiers for ETF and US codes.

The helpers are cloned onto ``src.data_provider.efinance_fetcher`` globals
(ADR-006) so ``_is_etf_code``, ``_build_eastmoney_etf_secid``, and
``_is_us_code`` call sites and test patches stay on the compatibility facade.
The classifiers remain module-level functions, not class methods.
"""

from __future__ import annotations

import re
from typing import Callable, Optional, Tuple

from src.data_provider.base import (
    DataFetchError,
    normalize_stock_code,
    _is_etf_code as _is_a_share_etf_code,
)

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")

# Facade free-name anchors for flake8 F821 / independent owner callability.
# The cloned functions resolve ``_is_a_share_etf_code``, ``normalize_stock_code``,
# ``DataFetchError``, ``_is_etf_code``, ``re``, and the prefix tuples from
# ``src.data_provider.efinance_fetcher`` globals at runtime (ADR-006).
_ETF_SH_PREFIXES = ('51', '52', '56', '58')
_ETF_SZ_PREFIXES = ('15', '16', '18')


def _is_etf_code(stock_code: str) -> bool:
    """
    判断代码是否为 ETF 基金
    
    ETF 代码规则：
    - 上交所 ETF: 51xxxx, 52xxxx, 56xxxx, 58xxxx
    - 深交所 ETF: 15xxxx, 16xxxx, 18xxxx
    
    Args:
        stock_code: 股票/基金代码
        
    Returns:
        True 表示是 ETF 代码，False 表示是普通股票代码
    """
    return _is_a_share_etf_code(stock_code)


def _build_eastmoney_etf_secid(stock_code: str) -> str:
    """Build Eastmoney secid for A-share ETF historical K-line queries."""
    code = normalize_stock_code(stock_code)
    if not _is_etf_code(code):
        raise DataFetchError(f"无法识别 ETF 代码 {stock_code}")
    if code.startswith(_ETF_SH_PREFIXES):
        return f"1.{code}"
    if code.startswith(_ETF_SZ_PREFIXES):
        return f"0.{code}"
    raise DataFetchError(f"无法确定 ETF {stock_code} 的 Eastmoney 市场前缀")


def _is_us_code(stock_code: str) -> bool:
    """
    判断代码是否为美股
    
    美股代码规则：
    - 1-5个大写字母，如 'AAPL', 'TSLA'
    - 可能包含 '.'，如 'BRK.B'
    """
    code = stock_code.strip().upper()
    return bool(re.match(r'^[A-Z]{1,5}(\.[A-Z])?$', code))


EXPECTED_SYMBOL_NAMES: Tuple[str, ...] = (
    "_is_etf_code",
    "_build_eastmoney_etf_secid",
    "_is_us_code",
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
