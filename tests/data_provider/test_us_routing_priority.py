# -*- coding: utf-8 -*-
"""US daily routing consumes live fetcher priorities on named builtin chains.

Default numeric priorities preserve the named US daily order. Pin-first keeps
YFinance first for US indexes and Longbridge first when preferred. Plugin
names stay on the unsorted tail. Realtime routing is out of scope.
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

if "litellm" not in sys.modules:
    sys.modules["litellm"] = MagicMock()
if "json_repair" not in sys.modules:
    sys.modules["json_repair"] = MagicMock()

from src.data_provider.base import DataFetcherManager
from src.data_provider.plugin_registry import DataProviderRegistration


US_STOCK_NAMES = [
    "FinnhubFetcher",
    "AlphaVantageFetcher",
    "YfinanceFetcher",
    "LongbridgeFetcher",
]
US_INDEX_NAMES = ["YfinanceFetcher", "FinnhubFetcher"]
US_STOCK_LB_NAMES = [
    "LongbridgeFetcher",
    "FinnhubFetcher",
    "AlphaVantageFetcher",
    "YfinanceFetcher",
]


def _daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-07-21"],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "close": [10.2],
            "volume": [1000],
            "amount": [10200],
            "pct_chg": [2.0],
        }
    )


class _DailyFetcher:
    def __init__(self, name: str, priority: int, frame: pd.DataFrame | None = None):
        self.name = name
        self.priority = priority
        self.frame = frame
        self.calls: list[str] = []

    def get_daily_data(self, **kwargs) -> pd.DataFrame | None:
        self.calls.append(str(kwargs.get("stock_code") or ""))
        if self.frame is None:
            return None
        return self.frame.copy(deep=True)

    def is_available_for_request(self, _capability: str) -> bool:
        return True


class _PluginDailyFetcher(_DailyFetcher):
    def __init__(
        self,
        name: str,
        priority: int,
        frame: pd.DataFrame | None = None,
    ):
        super().__init__(name, priority, frame=frame)
        self._registration = DataProviderRegistration(
            provider_id="plugin.us-daily-tail",
            factory=lambda: self,
            markets=frozenset({"us"}),
            capabilities=frozenset({"daily_data"}),
        )

    def _manager_plugin_registration(self):
        return self._registration


def _manager(fetchers: list[_DailyFetcher]) -> DataFetcherManager:
    return DataFetcherManager(fetchers=list(fetchers))


def _attempt_order(fetchers: list[_DailyFetcher]) -> list[str]:
    return [fetcher.name for fetcher in fetchers if fetcher.calls]


class TestUSDailyRoutingPriority(unittest.TestCase):
    """Public-manager counterexamples for US daily priority sort and pin-first."""

    def test_c1_default_priorities_preserve_named_us_stock_chain(self):
        fetchers = [
            _DailyFetcher("FinnhubFetcher", 2),
            _DailyFetcher("AlphaVantageFetcher", 3),
            _DailyFetcher("YfinanceFetcher", 4),
            _DailyFetcher("LongbridgeFetcher", 5),
        ]
        manager = _manager(fetchers)
        ordered = manager._order_us_sources_by_priority(
            list(US_STOCK_NAMES),
            pin_first=False,
        )
        self.assertEqual(ordered, US_STOCK_NAMES)

    def test_c2_yfinance_priority_zero_promotes_unpinned_us_stock(self):
        fetchers = [
            _DailyFetcher("FinnhubFetcher", 2),
            _DailyFetcher("AlphaVantageFetcher", 3),
            _DailyFetcher("YfinanceFetcher", 0),
            _DailyFetcher("LongbridgeFetcher", 5),
        ]
        manager = _manager(fetchers)
        ordered = manager._order_us_sources_by_priority(
            list(US_STOCK_NAMES),
            pin_first=False,
        )
        self.assertEqual(
            ordered,
            [
                "YfinanceFetcher",
                "FinnhubFetcher",
                "AlphaVantageFetcher",
                "LongbridgeFetcher",
            ],
        )

    def test_c3_longbridge_preferred_stays_pinned_first(self):
        fetchers = [
            _DailyFetcher("LongbridgeFetcher", 5),
            _DailyFetcher("FinnhubFetcher", 2),
            _DailyFetcher("AlphaVantageFetcher", 3),
            _DailyFetcher("YfinanceFetcher", 4),
        ]
        manager = _manager(fetchers)
        ordered = manager._order_us_sources_by_priority(
            list(US_STOCK_LB_NAMES),
            pin_first=True,
        )
        self.assertEqual(ordered, US_STOCK_LB_NAMES)

    def test_c3_remainder_sorts_under_longbridge_pin(self):
        fetchers = [
            _DailyFetcher("LongbridgeFetcher", 5),
            _DailyFetcher("FinnhubFetcher", 2),
            _DailyFetcher("AlphaVantageFetcher", 3),
            _DailyFetcher("YfinanceFetcher", 0),
        ]
        manager = _manager(fetchers)
        ordered = manager._order_us_sources_by_priority(
            list(US_STOCK_LB_NAMES),
            pin_first=True,
        )
        self.assertEqual(
            ordered,
            [
                "LongbridgeFetcher",
                "YfinanceFetcher",
                "FinnhubFetcher",
                "AlphaVantageFetcher",
            ],
        )

    def test_c4_us_index_keeps_yfinance_first_when_finnhub_priority_zero(self):
        fetchers = [
            _DailyFetcher("YfinanceFetcher", 4),
            _DailyFetcher("FinnhubFetcher", 0),
        ]
        manager = _manager(fetchers)
        ordered = manager._order_us_sources_by_priority(
            list(US_INDEX_NAMES),
            pin_first=True,
        )
        self.assertEqual(ordered, US_INDEX_NAMES)

    def test_c5_equal_priorities_keep_original_named_order(self):
        fetchers = [
            _DailyFetcher("FinnhubFetcher", 4),
            _DailyFetcher("AlphaVantageFetcher", 4),
            _DailyFetcher("YfinanceFetcher", 4),
            _DailyFetcher("LongbridgeFetcher", 4),
        ]
        manager = _manager(fetchers)
        ordered = manager._order_us_sources_by_priority(
            list(US_STOCK_NAMES),
            pin_first=False,
        )
        self.assertEqual(ordered, US_STOCK_NAMES)

    def test_empty_source_order_is_returned_unchanged(self):
        manager = _manager([_DailyFetcher("YfinanceFetcher", 4)])
        self.assertEqual(
            manager._order_us_sources_by_priority([], pin_first=False),
            [],
        )
        self.assertEqual(
            manager._order_us_sources_by_priority([], pin_first=True),
            [],
        )

    def test_c6_plugin_with_priority_zero_stays_after_builtins(self):
        frame = _daily_frame()
        builtins = [
            _DailyFetcher("FinnhubFetcher", 2),
            _DailyFetcher("AlphaVantageFetcher", 3),
            _DailyFetcher("YfinanceFetcher", 4),
        ]
        plugin = _PluginDailyFetcher("PluginZeroFetcher", 0, frame=frame)
        manager = _manager([*builtins, plugin])

        result_frame, source = manager._get_daily_data_from_providers("AAPL")

        self.assertEqual(source, "PluginZeroFetcher")
        self.assertEqual(list(result_frame["close"]), [10.2])
        self.assertEqual(
            _attempt_order([*builtins, plugin]),
            [
                "FinnhubFetcher",
                "AlphaVantageFetcher",
                "YfinanceFetcher",
                "PluginZeroFetcher",
            ],
        )

    def test_c7_public_spx_keeps_yfinance_first_despite_worse_priority(self):
        frame = _daily_frame()
        yfinance = _DailyFetcher("YfinanceFetcher", 99, frame=frame)
        finnhub = _DailyFetcher("FinnhubFetcher", 0, frame=frame)
        manager = _manager([yfinance, finnhub])

        result_frame, source = manager._get_daily_data_from_providers("SPX")

        self.assertEqual(source, "YfinanceFetcher")
        self.assertEqual(list(result_frame["close"]), [10.2])
        self.assertEqual(_attempt_order([yfinance, finnhub]), ["YfinanceFetcher"])
        self.assertEqual(finnhub.calls, [])

    def test_c8_public_aapl_promotes_yfinance_when_unpinned(self):
        frame = _daily_frame()
        finnhub = _DailyFetcher("FinnhubFetcher", 2, frame=frame)
        alphavantage = _DailyFetcher("AlphaVantageFetcher", 3, frame=frame)
        yfinance = _DailyFetcher("YfinanceFetcher", 0, frame=frame)
        manager = _manager([finnhub, alphavantage, yfinance])

        result_frame, source = manager._get_daily_data_from_providers("AAPL")

        self.assertEqual(source, "YfinanceFetcher")
        self.assertEqual(list(result_frame["close"]), [10.2])
        self.assertEqual(_attempt_order([finnhub, alphavantage, yfinance]), ["YfinanceFetcher"])
        self.assertEqual(finnhub.calls, [])
        self.assertEqual(alphavantage.calls, [])

    def test_c8_default_aapl_without_longbridge_keeps_finnhub_first(self):
        frame = _daily_frame()
        finnhub = _DailyFetcher("FinnhubFetcher", 2, frame=frame)
        alphavantage = _DailyFetcher("AlphaVantageFetcher", 3, frame=frame)
        yfinance = _DailyFetcher("YfinanceFetcher", 4, frame=frame)
        manager = _manager([finnhub, alphavantage, yfinance])

        _frame, source = manager._get_daily_data_from_providers("AAPL")

        self.assertEqual(source, "FinnhubFetcher")
        self.assertEqual(_attempt_order([finnhub, alphavantage, yfinance]), ["FinnhubFetcher"])

    def test_c9_non_us_daily_does_not_call_us_priority_helper(self):
        efinance = _DailyFetcher("EfinanceFetcher", 0, frame=_daily_frame())
        manager = _manager([efinance])
        with patch.object(
            DataFetcherManager,
            "_order_us_sources_by_priority",
            wraps=manager._order_us_sources_by_priority,
        ) as mocked:
            _frame, source = manager._get_daily_data_from_providers("600519")

        self.assertEqual(source, "EfinanceFetcher")
        mocked.assert_not_called()
        self.assertEqual(efinance.calls, ["600519"])


if __name__ == "__main__":
    unittest.main()
