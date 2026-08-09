# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline contract tests for the optional money-flow capability."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from data_provider.base import DataFetcherManager
from data_provider.money_flow_akshare import (
    SOURCE_ID,
    fetch_akshare_individual_money_flow,
    normalize_eastmoney_fund_flow_df,
    resolve_cn_exchange_market,
)
from data_provider.money_flow_types import (
    EASTMONEY_EM_ORDER_BUCKET_DEFINITION,
    MoneyFlowOutcome,
    MoneyFlowSnapshot,
    MoneyFlowStatus,
    is_meaningful_money_flow,
)
from data_provider.plugin_registry import DATA_PROVIDER_CAPABILITY_METHODS
from src.core.trading_calendar import get_effective_trading_date
from src.config import Config
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


def _snapshot(*, date: str | None = None, ratio: float | None = 1.0) -> MoneyFlowSnapshot:
    return MoneyFlowSnapshot(
        code="600519",
        date=date or get_effective_trading_date("cn").isoformat(),
        source="fixture",
        main_net_inflow_ratio=ratio,
        bucket_definition="fixture_v1;amount_unit=unknown;ratio_unit=percent",
        as_of=datetime.now(timezone.utc).isoformat(),
        requested_days=5,
        observed_days=5,
        completeness="complete",
    )


def test_capability_table_includes_money_flow_without_regressing_existing_entries():
    assert DATA_PROVIDER_CAPABILITY_METHODS["money_flow"] == "get_money_flow"
    assert DATA_PROVIDER_CAPABILITY_METHODS["daily_data"] == "get_daily_data"
    assert DATA_PROVIDER_CAPABILITY_METHODS["chip_distribution"] == "get_chip_distribution"


def test_resolve_cn_exchange_market():
    assert resolve_cn_exchange_market("600519") == "sh"
    assert resolve_cn_exchange_market("000001") == "sz"
    assert resolve_cn_exchange_market("AAPL") is None
    assert resolve_cn_exchange_market("hk00700") is None


def test_normalizer_omits_uncalibrated_amounts_but_preserves_ratios_and_window():
    snapshot = normalize_eastmoney_fund_flow_df(
        _fixture_fund_flow_df(), stock_code="600519", history_days=5
    )
    assert snapshot is not None
    assert snapshot.date == "2026-08-08"
    assert snapshot.source == SOURCE_ID
    assert snapshot.bucket_definition == EASTMONEY_EM_ORDER_BUCKET_DEFINITION
    assert snapshot.main_net_inflow is None
    assert snapshot.main_net_inflow_5d is None
    assert snapshot.main_net_inflow_ratio == pytest.approx(4.0)
    assert snapshot.requested_days == snapshot.observed_days == 5
    assert snapshot.unit == snapshot.amount_scale == "unknown"
    assert is_meaningful_money_flow(snapshot)


def test_normalizer_only_computes_rollups_with_authoritative_calibration():
    snapshot = normalize_eastmoney_fund_flow_df(
        _fixture_fund_flow_df(), stock_code="600519", history_days=5,
        amount_unit="CNY", amount_scale="yuan",
    )
    assert snapshot is not None
    assert snapshot.main_net_inflow == pytest.approx(4e6)
    assert snapshot.main_net_inflow_5d == pytest.approx(2e6 - 5e5 + 3e6 + 1.5e6 + 4e6)
    assert snapshot.main_net_inflow_10d is None


def test_history_days_controls_exact_slice_and_rollup_coverage():
    snapshot = normalize_eastmoney_fund_flow_df(
        _fixture_fund_flow_df(), stock_code="600519", history_days=1,
        amount_unit="CNY", amount_scale="yuan",
    )
    assert snapshot is not None
    assert snapshot.requested_days == snapshot.observed_days == 1
    assert snapshot.main_net_inflow_5d is None
    assert snapshot.main_net_inflow_10d is None
    with pytest.raises(ValueError):
        normalize_eastmoney_fund_flow_df(_fixture_fund_flow_df(), stock_code="600519", history_days=21)


def test_snapshot_rejects_nonfinite_ratio_and_uncalibrated_amount():
    with pytest.raises(ValueError, match="finite"):
        _snapshot(ratio=float("inf"))
    with pytest.raises(ValueError, match="uncalibrated"):
        MoneyFlowSnapshot(
            code="600519", date="2026-08-08", source="fixture",
            main_net_inflow=1.0, bucket_definition="fixture",
            as_of=datetime.now(timezone.utc).isoformat(), observed_days=1,
        )
    json.dumps(_snapshot().to_dict(), allow_nan=False)


def test_snapshot_rejects_malformed_currency_scale_and_identity():
    common = dict(
        code="600519", date="2026-08-08", source="fixture",
        main_net_inflow=1.0, bucket_definition="fixture",
        as_of=datetime.now(timezone.utc).isoformat(), requested_days=1,
        observed_days=1, completeness="complete",
    )
    with pytest.raises(ValueError, match="currency"):
        MoneyFlowSnapshot(**common, unit="yuan", amount_scale="yuan")
    with pytest.raises(ValueError, match="amount_scale"):
        MoneyFlowSnapshot(**common, unit="CNY", amount_scale="shares")
    with pytest.raises(ValueError, match="identity"):
        MoneyFlowSnapshot(**{**common, "code": "AAPL"}, unit="CNY", amount_scale="yuan")


def test_fetch_akshare_is_zero_io_for_non_cn_and_retries_timeout_once():
    class _Boom:
        def stock_individual_fund_flow(self, *args, **kwargs):
            raise AssertionError("must not call network for non-CN symbols")

    assert fetch_akshare_individual_money_flow("AAPL", ak_module=_Boom()) is None
    calls = []

    def timeout_runner(*args, **kwargs):
        calls.append(kwargs)
        raise TimeoutError("deadline")

    with pytest.raises(TimeoutError):
        fetch_akshare_individual_money_flow(
            "600519", ak_module=_Boom(), timeout_runner=timeout_runner, sleeper=lambda _: None
        )
    assert len(calls) == 2


def test_fetch_akshare_uses_one_versioned_signature():
    class _FakeAk:
        def stock_individual_fund_flow(self, stock: str, market: str):
            assert (stock, market) == ("600519", "sh")
            return _fixture_fund_flow_df()

    def direct_runner(function, **kwargs):
        kwargs.pop("timeout")
        kwargs.pop("call_name")
        return function(**kwargs)

    snapshot = fetch_akshare_individual_money_flow(
        "600519", ak_module=_FakeAk(), timeout_runner=direct_runner
    )
    assert snapshot is not None
    assert snapshot.main_net_inflow is None
    assert snapshot.main_net_inflow_ratio == 4.0


class _MoneyFlowFetcher:
    def __init__(self, name: str, priority: int, result):
        self.name = name
        self.priority = priority
        self._result = result
        self.calls = 0

    def get_money_flow(self, stock_code: str, days: int = 5):
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_service_gate_is_single_authority_and_disabled_is_zero_io(monkeypatch):
    fetcher = _MoneyFlowFetcher("FlowFetcher", 0, _snapshot())
    manager = DataFetcherManager(fetchers=[fetcher])
    monkeypatch.setenv("SMARTMONEY_ENABLED", "true")
    assert fetch_money_flow(
        "600519", manager=manager,
        config=SimpleNamespace(smartmoney_enabled=False),
    ) is None
    assert fetcher.calls == 0
    outcome = fetch_money_flow(
        "600519", manager=manager,
        config=SimpleNamespace(smartmoney_enabled=True),
    )
    assert outcome is not None and outcome.status == MoneyFlowStatus.PARTIAL
    assert fetcher.calls == 1


def test_environment_loaded_config_activates_the_same_manager_operation(monkeypatch):
    monkeypatch.setenv("SMARTMONEY_ENABLED", "true")
    config = Config._load_from_env()
    fetcher = _MoneyFlowFetcher("FlowFetcher", 0, _snapshot())
    manager = DataFetcherManager(fetchers=[fetcher])

    outcome = fetch_money_flow("600519", manager=manager, config=config)

    assert config.smartmoney_enabled is True
    assert outcome is not None and outcome.status == MoneyFlowStatus.PARTIAL
    assert fetcher.calls == 1


def test_gate_rejects_truthy_strings_and_invalid_environment(monkeypatch):
    with pytest.raises(TypeError):
        is_smartmoney_enabled(SimpleNamespace(smartmoney_enabled="false"))
    monkeypatch.setenv("SMARTMONEY_ENABLED", "sometimes")
    with pytest.raises(ValueError):
        is_smartmoney_enabled()


def test_manager_non_cn_is_explicit_and_zero_io():
    fetcher = _MoneyFlowFetcher("FlowFetcher", 0, _snapshot())
    outcome = DataFetcherManager(fetchers=[fetcher]).get_money_flow("AAPL")
    assert outcome.status == MoneyFlowStatus.NOT_SUPPORTED
    assert outcome.error_code == "money_flow_market_not_supported"
    assert fetcher.calls == 0


def test_manager_calls_internal_typeerror_provider_exactly_once():
    fetcher = _MoneyFlowFetcher("FlowFetcher", 0, TypeError("provider bug"))
    outcome = DataFetcherManager(fetchers=[fetcher]).get_money_flow("600519")
    assert outcome.status == MoneyFlowStatus.FETCH_FAILED
    assert fetcher.calls == 1
    assert outcome.source_chain[0]["error_code"] == "TypeError"


def test_manager_distinguishes_empty_from_fetch_failure():
    fetcher = _MoneyFlowFetcher("FlowFetcher", 0, _snapshot(ratio=None))
    outcome = DataFetcherManager(fetchers=[fetcher]).get_money_flow("600519")
    assert outcome.status == MoneyFlowStatus.EMPTY
    assert outcome.error_code == "money_flow_all_providers_empty"


def test_manager_cross_provider_fallback_retains_source_chain():
    failed = _MoneyFlowFetcher("FailedFlow", 0, TimeoutError("deadline"))
    healthy = _MoneyFlowFetcher("HealthyFlow", 1, _snapshot())
    outcome = DataFetcherManager(fetchers=[failed, healthy]).get_money_flow("600519")
    assert outcome.status == MoneyFlowStatus.PARTIAL
    assert [item["provider"] for item in outcome.source_chain] == ["FailedFlow", "HealthyFlow"]
    assert failed.calls == healthy.calls == 1


def test_money_flow_circuit_opens_after_bounded_failures():
    fetcher = _MoneyFlowFetcher("FailedFlow", 0, TimeoutError("deadline"))
    manager = DataFetcherManager(fetchers=[fetcher])
    assert manager.get_money_flow("600519").status == MoneyFlowStatus.FETCH_FAILED
    assert manager.get_money_flow("600519").status == MoneyFlowStatus.FETCH_FAILED
    third = manager.get_money_flow("600519")
    assert third.status == MoneyFlowStatus.FETCH_FAILED
    assert third.source_chain == [{"provider": "FailedFlow", "status": "circuit_open"}]
    assert fetcher.calls == 2


def test_manager_cache_hit_stats_and_invalidation():
    fetcher = _MoneyFlowFetcher("FlowFetcher", 0, _snapshot())
    manager = DataFetcherManager(fetchers=[fetcher])
    first = manager.get_money_flow("600519")
    second = manager.get_money_flow("600519")
    assert first.status == MoneyFlowStatus.PARTIAL
    assert second.cache_state == "fresh"
    assert fetcher.calls == 1
    assert manager.get_money_flow_cache_stats()["hits"] == 1
    assert manager.invalidate_money_flow_cache("600519") == 1


def test_manager_stale_provider_data_never_becomes_available():
    fetcher = _MoneyFlowFetcher("FlowFetcher", 0, _snapshot(date="2000-01-03"))
    outcome = DataFetcherManager(fetchers=[fetcher]).get_money_flow("600519")
    assert outcome.status == MoneyFlowStatus.STALE
    assert outcome.age_days and outcome.age_days > 0


def test_manager_uses_stale_cache_after_provider_failure():
    fetcher = _MoneyFlowFetcher("FlowFetcher", 0, _snapshot())
    manager = DataFetcherManager(fetchers=[fetcher])
    assert manager.get_money_flow("600519").snapshot is not None
    manager._MONEY_FLOW_CACHE_TTL_SECONDS = -1
    fetcher._result = RuntimeError("upstream down")
    fallback = manager.get_money_flow("600519")
    assert fallback.status == MoneyFlowStatus.FALLBACK
    assert fallback.cache_state == "stale"
    assert fallback.fallback_from == "provider_failure"


def test_money_flow_to_context_preserves_outcome_and_calibration():
    snapshot = _snapshot(ratio=-2.0)
    outcome = MoneyFlowOutcome(
        status=MoneyFlowStatus.PARTIAL, code="600519", market="cn",
        requested_days=5, fetched_at=datetime.now(timezone.utc).isoformat(),
        snapshot=snapshot, provider_date=snapshot.date, age_days=0,
        warnings=["uncalibrated"],
    )
    context = money_flow_to_context(outcome)
    assert context is not None
    assert context["status"] == "partial"
    assert context["snapshot"]["attitude"] == "outflow"
    assert "calibration_note" in context["snapshot"]


def test_service_closes_a_standalone_manager(monkeypatch):
    outcome = MoneyFlowOutcome(
        status=MoneyFlowStatus.PARTIAL, code="600519", market="cn",
        requested_days=5, fetched_at=datetime.now(timezone.utc).isoformat(),
        snapshot=_snapshot(), provider_date=get_effective_trading_date("cn").isoformat(),
        age_days=0,
    )

    class _OwnedManager:
        instance = None

        def __init__(self):
            self.closed = False
            _OwnedManager.instance = self

        def get_money_flow(self, stock_code: str, days: int = 5):
            return outcome

        def close(self):
            self.closed = True

    monkeypatch.setattr("data_provider.base.DataFetcherManager", _OwnedManager)
    assert fetch_money_flow("600519", config=SimpleNamespace(smartmoney_enabled=True)) is outcome
    assert _OwnedManager.instance is not None and _OwnedManager.instance.closed is True
