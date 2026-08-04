"""Regression coverage for the shared bare Hong Kong symbol contract."""

import pandas as pd

from data_provider.akshare_fetcher import _is_hk_code as akshare_is_hk_code
from data_provider.base import BaseFetcher, DataFetchError, DataFetcherManager, _is_hk_market
from data_provider.longbridge_fetcher import (
    _is_hk_code as longbridge_is_hk_code,
    _to_longbridge_symbol,
)
from data_provider.yfinance_fetcher import YfinanceFetcher


def test_bare_five_digit_hk_code_uses_hk_suffix() -> None:
    fetcher = YfinanceFetcher()

    assert fetcher._convert_stock_code("02513") == "2513.HK"
    assert fetcher._convert_stock_code("00700") == "0700.HK"


def test_bare_four_digit_hk_code_is_consistent_across_entry_points() -> None:
    fetcher = YfinanceFetcher()

    for code in ("0001", "0941"):
        assert _is_hk_market(code) is True
        assert akshare_is_hk_code(code) is True
        assert longbridge_is_hk_code(code) is True
        assert _to_longbridge_symbol(code) == f"{code}.HK"
        assert fetcher._convert_stock_code(code) == f"{code}.HK"


def test_existing_a_share_and_us_conversions_are_unchanged() -> None:
    fetcher = YfinanceFetcher()

    assert fetcher._convert_stock_code("600519") == "600519.SS"
    assert fetcher._convert_stock_code("000001") == "000001.SZ"
    assert fetcher._convert_stock_code("AAPL") == "AAPL"


class _RouteFetcher(BaseFetcher):
    """Small daily-provider stub for exercising the manager's real filter."""

    def __init__(self, name: str, *, should_fail: bool = False) -> None:
        self.name = name
        self.priority = {
            "EfinanceFetcher": 0,
            "AkshareFetcher": 1,
            "BaostockFetcher": 3,
            "YfinanceFetcher": 4,
        }.get(name, 5)
        self.should_fail = should_fail
        self.calls: list[str] = []

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        raise NotImplementedError

    def get_daily_data(self, stock_code, start_date=None, end_date=None, days=30):
        self.calls.append(stock_code)
        if self.should_fail:
            raise DataFetchError(f"{self.name} must not receive {stock_code}")
        return pd.DataFrame(
            {
                "date": [pd.Timestamp("2026-07-25")],
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [100],
                "amount": [100.0],
                "pct_chg": [0.0],
            }
        )


def test_manager_routes_four_digit_hk_away_from_cn_only_fetchers() -> None:
    efinance = _RouteFetcher("EfinanceFetcher", should_fail=True)
    baostock = _RouteFetcher("BaostockFetcher", should_fail=True)
    yfinance = _RouteFetcher("YfinanceFetcher")
    manager = DataFetcherManager(fetchers=[efinance, baostock, yfinance])

    frame, source = manager.get_daily_data("0001", start_date="2026-07-01", end_date="2026-07-25")

    assert not frame.empty
    assert source == "YfinanceFetcher"
    assert yfinance.calls == ["0001"]
    assert efinance.calls == []
    assert baostock.calls == []
