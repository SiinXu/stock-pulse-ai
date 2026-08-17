# -*- coding: utf-8 -*-
"""AkShare provider symbol / market classification helpers.

Pure helpers extracted from ``data_provider.akshare_fetcher`` (Issue #1068).
External callers must keep importing from ``data_provider.akshare_fetcher``.
"""

from __future__ import annotations

from src.data_provider.symbol_normalization import is_bse_code
from src.data_provider.us_index_mapping import is_us_stock_code


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
    etf_prefixes = ('51', '52', '56', '58', '15', '16', '18')
    code = stock_code.strip().split('.')[0]
    return code.startswith(etf_prefixes) and len(code) == 6


def _is_hk_code(stock_code: str) -> bool:
    """Return whether a symbol is a Hong Kong stock code.

    This provider-level check must match the manager and peer-provider market
    contract: explicit ``HK``/``.HK`` forms and four- to five-digit bare codes.

    Args:
        stock_code: 股票代码

    Returns:
        True 表示是港股代码，False 表示不是港股代码
    """
    # Remove possible 'hk' Prefix and check if it is a pure number
    code = stock_code.strip().lower()
    if code.endswith('.hk'):
        numeric_part = code[:-3]
        return numeric_part.isdigit() and 1 <= len(numeric_part) <= 5
    if code.startswith('hk'):
        # Any prefix with 'hk' must be Hong Kong stocks, remove the prefix and it should be a pure number (1-5 digits)
        numeric_part = code[2:]
        return numeric_part.isdigit() and 1 <= len(numeric_part) <= 5
    # Mainland and Beijing stock codes use six digits, so they do not overlap.
    return code.isdigit() and 4 <= len(code) <= 5


def is_hk_stock_code(stock_code: str) -> bool:
    """
    Public API: determine if a stock code is a Hong Kong stock.

    Delegates to _is_hk_code for internal compatibility.

    Args:
        stock_code: Stock code (e.g. '00700', 'hk00700')

    Returns:
        True if HK stock, False otherwise
    """
    return _is_hk_code(stock_code)


def _is_us_code(stock_code: str) -> bool:
    """
    判断代码是否为美股股票（不包括美股指数）。

    委托给 us_index_mapping 模块的 is_us_stock_code()。

    Args:
        stock_code: 股票代码

    Returns:
        True 表示是美股代码，False 表示不是美股代码

    Examples:
        >>> _is_us_code('AAPL')
        True
        >>> _is_us_code('TSLA')
        True
        >>> _is_us_code('SPX')
        False
        >>> _is_us_code('600519')
        False
    """
    return is_us_stock_code(stock_code)


def _to_sina_tx_symbol(stock_code: str) -> str:
    """Convert 6-digit A-share code to sh/sz/bj prefixed symbol for Sina/Tencent APIs."""
    base = (stock_code.strip().split(".")[0] if "." in stock_code else stock_code).strip()
    if is_bse_code(base):
        return f"bj{base}"
    # Shanghai: 60xxxx, 5xxxx (ETF), 90xxxx (B-shares)
    if base.startswith(("6", "5", "90")):
        return f"sh{base}"
    return f"sz{base}"

