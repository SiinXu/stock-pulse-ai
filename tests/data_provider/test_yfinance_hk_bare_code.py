"""Regression coverage for bare Hong Kong Yahoo Finance symbols."""

from data_provider.yfinance_fetcher import YfinanceFetcher


def test_bare_five_digit_hk_code_uses_hk_suffix() -> None:
    fetcher = YfinanceFetcher()

    assert fetcher._convert_stock_code("02513") == "02513.HK"


def test_existing_a_share_and_us_conversions_are_unchanged() -> None:
    fetcher = YfinanceFetcher()

    assert fetcher._convert_stock_code("600519") == "600519.SS"
    assert fetcher._convert_stock_code("000001") == "000001.SZ"
    assert fetcher._convert_stock_code("AAPL") == "AAPL"
