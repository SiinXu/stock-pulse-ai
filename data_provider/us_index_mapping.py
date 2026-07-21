# -*- coding: utf-8 -*-
"""
===================================
Tool for U.S. stock index and code mapping
===================================

Provides:
1. U.S. stocks index mapping (e.g., SPX -> ^GSPC)
2. Recognition of U.S. stocks codes (AAPL, TSLA, etc.)

U.S. stocks indices in Yahoo Finance require the '^' prefix, which is different from stock codes.
"""

import re

# U.S. Stock code regex: 1-5 uppercase letters, optional .X suffix (e.g., BRK.B)
_US_STOCK_PATTERN = re.compile(r'^[A-Z]{1,5}(\.[A-Z])?$')


# User input -> (Yahoo Finance symbol, Chinese name)
US_INDEX_MAPPING = {
    # S&P 500
    'SPX': ('^GSPC', '标普500指数'),
    '^GSPC': ('^GSPC', '标普500指数'),
    'GSPC': ('^GSPC', '标普500指数'),
    # Dow Jones Industrial Average.
    'DJI': ('^DJI', '道琼斯工业指数'),
    '^DJI': ('^DJI', '道琼斯工业指数'),
    'DJIA': ('^DJI', '道琼斯工业指数'),
    # NASDAQ Composite Index
    'IXIC': ('^IXIC', '纳斯达克综合指数'),
    '^IXIC': ('^IXIC', '纳斯达克综合指数'),
    'NASDAQ': ('^IXIC', '纳斯达克综合指数'),
    # NASDAQ 100
    'NDX': ('^NDX', '纳斯达克100指数'),
    '^NDX': ('^NDX', '纳斯达克100指数'),
    # VIX volatility index
    'VIX': ('^VIX', 'VIX恐慌指数'),
    '^VIX': ('^VIX', 'VIX恐慌指数'),
    # Dow Jones 2000
    'RUT': ('^RUT', '罗素2000指数'),
    '^RUT': ('^RUT', '罗素2000指数'),
}


def is_us_index_code(code: str) -> bool:
    """
    Determine if the code is a U.S. stock index symbol.

    Args:
        code: stock/index code, such as 'SPX', 'DJI'

    Returns:
        True indicates a known US stock index symbol, otherwise False

    Examples:
        >>> is_us_index_code('SPX')
        True
        >>> is_us_index_code('AAPL')
        False
    """
    return (code or '').strip().upper() in US_INDEX_MAPPING


def is_us_stock_code(code: str) -> bool:
    """
    Determine if the code is a U.S. stock symbol (excluding U.S. indices).

    U.S. stocks codes are 1-5 uppercase letters, optionally followed by '.X' like BRK.B.
    U.S. stocks indices (SPX, DJI, etc.) are explicitly excluded.

    Args:
        code: Stock Code, If 'AAPL', 'TSLA', 'BRK.B'

    Returns:
        True indicates whether it is a U.S. stock symbol, otherwise False

    Examples:
        >>> is_us_stock_code('AAPL')
        True
        >>> is_us_stock_code('TSLA')
        True
        >>> is_us_stock_code('BRK.B')
        True
        >>> is_us_stock_code('SPX')
        False
        >>> is_us_stock_code('600519')
        False
    """
    normalized = (code or '').strip().upper()
    # U.S. stock indices are not stocks
    if normalized in US_INDEX_MAPPING:
        return False
    return bool(_US_STOCK_PATTERN.match(normalized))


def get_us_index_yf_symbol(code: str) -> tuple:
    """
    Get Yahoo Finance symbol and Chinese name for US stock indices.

    Args:
        code: User input, If 'SPX', '^GSPC', 'DJI'

    Returns:
        (yf_symbol, chinese_name) Tuple, Return when not found? (None, None).

    Examples:
        >>> get_us_index_yf_symbol('SPX')
        ('^GSPC', 'S&P 500 Index')
        >>> get_us_index_yf_symbol('AAPL')
        (None, None)
    """
    normalized = (code or '').strip().upper()
    return US_INDEX_MAPPING.get(normalized, (None, None))
