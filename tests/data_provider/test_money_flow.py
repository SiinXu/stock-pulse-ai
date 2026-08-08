# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline tests for money_flow capability, normalization, and feature gate."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from data_provider.base import DataFetcherManager
from data_provider.money_flow_akshare import (
    SOURCE_ID,
    normalize_eastmoney_fund_flow_df,
    resolve_cn_exchange_market,
    fetch_akshare_individual_money_flow,
)
from data_provider.money_flow_types import (
    EASTMONEY_EM_ORDER_BUCKET_DEFINITION,
    MoneyFlowSnapshot,
    is_meaningful_money_flow,
)
from data_provider.plugin_registry import DATA_PROVIDER_CAPABILITY_METHODS
from src.services.smartmoney_flow_service import (
    fetch_money_flow,
    is_smartmoney_enabled,
    money_flow_to_context,
)


def _fixture_fund_flow_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-08-01", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-08"],
            "收盘价": [10.0, 10.1, 10.2, 10.3, 10.4, 10.5],
            "涨跌幅": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
            "主力净流入-净额": [1e6, 2e6, -5e5, 3e6, 1.5e6, 4e6],
            "主力净流入-净占比": [1.0, 2.0, -0.5, 3.0, 1.5, 4.0],
            "超大单净流入-净额": [5e5, 1e6, -2e5, 1.5e6, 8e5, 2e6],
            "超大单净流入-净占比": [0.5, 1.0, -0.2, 1.5, 0.8, 2.0],
            "大单净流入-净额": [5e5, 1e6, -3e5, 1.5e6, 7e5, 2e6],
            "大单净流入-净占比": [0.5, 1.0, -0.3, 1.5, 0.7, 2.0],
            "中单净流入-净额": [-1e5, -2e5, 1e5, -3e5, -1e5, -4e5],
            "中单净流入-净占比": [-0.1, -0.2, 0.1, -0.3, -0.1, -0.4],
            "小单净流入-净额": [-9e5, -1.8e6, 4e5, -2.7e6, -1.4e6, -3.6e6],
            "小单净流入-净占比": [-0.9, -1.8, 0.4, -2.7, -1.4, -3.6],
        }
    )


def test_capability_table_includes_money_flow():
    assert DATA_PROVIDER_CAPABILITY_METHODS["money_flow"] == "get_money_flow"
    # Existing capabilities remain intact (backward compatible table extension).
    assert DATA_PROVIDER_CAPABILITY_METHODS["daily_data"] == "get_daily_data"
    assert DATA_PROVIDER_CAPABILITY_METHODS["chip_distribution"] == "get_chip_distribution"


def test_resolve_cn_exchange_market():
    assert resolve_cn_exchange_market("600519") == "sh"
    assert resolve_cn_exchange_market("000001") == "sz"
    assert resolve_cn_exchange_market("300750") == "sz"
    assert resolve_cn_exchange_market("AAPL") is None
    assert resolve_cn_exchange_market("hk00700") is None


def test_normalize_eastmoney_fund_flow_df_fixture():
    snapshot = normalize_eastmoney_fund_flow_df(
        _fixture_fund_flow_df(),
        stock_code="600519",
        history_days=5,
    )
    assert snapshot is not None
    assert snapshot.code == "600519"
    assert snapshot.date == "2026-08-08"
    assert snapshot.source == SOURCE_ID
    assert snapshot.bucket_definition == EASTMONEY_EM_ORDER_BUCKET_DEFINITION
    assert snapshot.main_net_inflow == pytest.approx(4e6)
    assert snapshot.super_large_net_inflow == pytest.approx(2e6)
    assert snapshot.large_net_inflow == pytest.approx(2e6)
    assert snapshot.main_net_inflow_5d == pytest.approx(2e6 - 5e5 + 3e6 + 1.5e6 + 4e6)
    assert snapshot.main_net_inflow_10d is None  # only 6 rows in fixture
    assert is_meaningful_money_flow(snapshot)
    assert snapshot.attitude() == "inflow"
    assert "eastmoney_em_order_size_buckets" in snapshot.bucket_definition


def test_normalize_rejects_empty_frame():
    assert normalize_eastmoney_fund_flow_df(pd.DataFrame(), stock_code="600519") is None


def test_fetch_akshare_skips_non_cn_without_network():
    class _Boom:
        def stock_individual_fund_flow(self, *args, **kwargs):
            raise AssertionError("must not call network for non-CN symbols")

    assert fetch_akshare_individual_money_flow("AAPL", ak_module=_Boom()) is None
    assert fetch_akshare_individual_money_flow("hk00700", ak_module=_Boom()) is None


def test_fetch_akshare_uses_injected_module_fixture():
    class _FakeAk:
        def stock_individual_fund_flow(self, stock: str, market: str):
            assert stock == "600519"
            assert market == "sh"
            return _fixture_fund_flow_df()

    snapshot = fetch_akshare_individual_money_flow(
        "600519",
        ak_module=_FakeAk(),
    )
    assert snapshot is not None
    assert snapshot.main_net_inflow == pytest.approx(4e6)


class _MoneyFlowFetcher:
    def __init__(self, name: str, priority: int, result, tracker=None):
        self.name = name
        self.priority = priority
        self._result = result
        self.calls = 0
        self._tracker = tracker

    def get_money_flow(self, stock_code: str, days: int = 5):
        self.calls += 1
        if self._tracker is not None:
            self._tracker.append((self.name, stock_code, days))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_manager_disabled_makes_zero_provider_calls(monkeypatch):
    calls = []
    valid = MoneyFlowSnapshot(
        code="600519",
        main_net_inflow=1e6,
        source="fixture",
        bucket_definition="test",
    )
    manager = DataFetcherManager(
        fetchers=[_MoneyFlowFetcher("FlowFetcher", 0, valid, tracker=calls)]
    )
    monkeypatch.delenv("SMARTMONEY_ENABLED", raising=False)
    assert manager.get_money_flow("600519") is None
    assert calls == []
    assert manager._fetchers[0].calls == 0


def test_manager_enabled_returns_meaningful_snapshot(monkeypatch):
    valid = MoneyFlowSnapshot(
        code="600519",
        main_net_inflow=1e6,
        source="fixture",
        bucket_definition="test",
    )
    manager = DataFetcherManager(
        fetchers=[_MoneyFlowFetcher("FlowFetcher", 0, valid)]
    )
    monkeypatch.setenv("SMARTMONEY_ENABLED", "true")
    result = manager.get_money_flow("600519")
    assert result is valid


def test_manager_skips_provider_without_method(monkeypatch):
    class _NoMoneyFlow:
        name = "NoMoney"
        priority = 0

        def get_daily_data(self, *args, **kwargs):
            raise AssertionError("unused")

    valid = MoneyFlowSnapshot(
        code="600519",
        main_net_inflow=2e6,
        source="fixture",
        bucket_definition="test",
    )
    manager = DataFetcherManager(
        fetchers=[
            _NoMoneyFlow(),
            _MoneyFlowFetcher("FlowFetcher", 1, valid),
        ]
    )
    monkeypatch.setenv("SMARTMONEY_ENABLED", "true")
    result = manager.get_money_flow("600519")
    assert result is valid


def test_manager_falls_back_after_empty_and_error(monkeypatch):
    empty = MoneyFlowSnapshot(code="600519")  # no amounts
    valid = MoneyFlowSnapshot(
        code="600519",
        main_net_inflow=3e6,
        source="fixture",
        bucket_definition="test",
    )
    manager = DataFetcherManager(
        fetchers=[
            _MoneyFlowFetcher("Empty", 0, empty),
            _MoneyFlowFetcher("Boom", 1, RuntimeError("upstream down")),
            _MoneyFlowFetcher("Good", 2, valid),
        ]
    )
    monkeypatch.setenv("SMARTMONEY_ENABLED", "true")
    result = manager.get_money_flow("600519")
    assert result is valid


def test_service_respects_disabled_flag():
    class _Manager:
        def __init__(self):
            self.calls = 0

        def get_money_flow(self, stock_code: str, days: int = 5):
            self.calls += 1
            return MoneyFlowSnapshot(code=stock_code, main_net_inflow=1.0)

    manager = _Manager()
    assert (
        fetch_money_flow(
            "600519",
            manager=manager,
            config=SimpleNamespace(smartmoney_enabled=False),
        )
        is None
    )
    assert manager.calls == 0
    assert is_smartmoney_enabled(SimpleNamespace(smartmoney_enabled=False)) is False


def test_money_flow_to_context_includes_calibration():
    snapshot = MoneyFlowSnapshot(
        code="600519",
        main_net_inflow=-1e6,
        source=SOURCE_ID,
        bucket_definition=EASTMONEY_EM_ORDER_BUCKET_DEFINITION,
    )
    ctx = money_flow_to_context(snapshot)
    assert ctx is not None
    assert ctx["attitude"] == "outflow"
    assert ctx["bucket_definition"] == EASTMONEY_EM_ORDER_BUCKET_DEFINITION
    assert "calibration_note" in ctx
