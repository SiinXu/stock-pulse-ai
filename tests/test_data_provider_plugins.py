# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Behavior-preserving contracts for pluggable data providers."""

from __future__ import annotations

import os
from threading import Event, Thread
from types import SimpleNamespace
from typing import Callable
from unittest.mock import patch

import pandas as pd
import pytest

from data_provider import (
    BaseFetcher,
    DataFetcherManager,
    DataProvider,
    DataProviderRegistration,
)
from data_provider.realtime_types import UnifiedRealtimeQuote
from src.plugins import Plugin, PluginContext, PluginManager, PluginManifest


_BUILTIN_IDENTITIES = {
    "EfinanceFetcher": "efinance",
    "TencentFetcher": "tencent",
    "AkshareFetcher": "akshare",
    "TushareFetcher": "tushare",
    "TickFlowFetcher": "tickflow",
    "PytdxFetcher": "pytdx",
    "BaostockFetcher": "baostock",
    "YfinanceFetcher": "yfinance",
    "LongbridgeFetcher": "longbridge",
    "FinnhubFetcher": "finnhub",
    "AlphaVantageFetcher": "alphavantage",
}


def _daily_frame(value: float = 10.2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-07-21"],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "close": [value],
            "volume": [1000],
            "amount": [value * 1000],
            "pct_chg": [2.0],
        }
    )


class _DailyProvider(DataProvider):
    def __init__(
        self,
        name: str,
        priority: int,
        outcome: pd.DataFrame | BaseException,
    ) -> None:
        self.name = name
        self.priority = priority
        self.outcome = outcome
        self.calls = 0

    def get_daily_data(
        self,
        stock_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 30,
    ) -> pd.DataFrame:
        del stock_code, start_date, end_date, days
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome.copy(deep=True)

    def get_realtime_quote(self, stock_code: str):
        del stock_code
        return None


def _manifest(plugin_id: str) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": "1.0.0",
            "description": "Data provider plugin test.",
            "author": "StockPulse Tests",
            "permissions": [],
        }
    )


class _ProviderPlugin(Plugin):
    def __init__(
        self,
        plugin_id: str,
        registration: DataProviderRegistration,
        *,
        priority: int,
    ) -> None:
        super().__init__(_manifest(plugin_id))
        self.registration = registration
        self.priority = priority
        self.unload_count = 0

    def onload(self, context: PluginContext) -> None:
        context.register(
            "data_provider",
            self.registration.provider_id,
            self.registration,
            priority=self.priority,
        )

    def onunload(self) -> None:
        self.unload_count += 1


class _RenamingProviderPlugin(_ProviderPlugin):
    def __init__(
        self,
        plugin_id: str,
        registration: DataProviderRegistration,
        provider: DataProvider,
        *,
        priority: int,
    ) -> None:
        super().__init__(plugin_id, registration, priority=priority)
        self.provider = provider

    def onunload(self) -> None:
        super().onunload()
        self.provider.name = "RenamedDuringUnloadFetcher"


def _registration(
    provider_id: str,
    factory: Callable[[], DataProvider],
    *,
    markets: set[str] | frozenset[str] = frozenset({"cn"}),
    capabilities: set[str] | frozenset[str] = frozenset({"daily_data"}),
) -> DataProviderRegistration:
    return DataProviderRegistration(
        provider_id=provider_id,
        factory=factory,
        markets=markets,
        capabilities=capabilities,
    )


@pytest.fixture(autouse=True)
def _deterministic_provider_policy() -> None:
    environment = {
        "PROVIDER_ADAPTIVE_PRIORITY_ENABLED": "false",
        "PROVIDER_CIRCUIT_BREAKER_ENABLED": "false",
        "PROVIDER_DAILY_CACHE_ENABLED": "false",
    }
    with patch.dict(os.environ, environment, clear=False):
        DataFetcherManager.reset_daily_source_health()
        yield
        DataFetcherManager.reset_daily_source_health()


def _plugin_manager(manager: DataFetcherManager) -> PluginManager:
    return PluginManager(
        application_version="2.0.0",
        registry=manager.plugin_registry,
    )


def test_base_fetcher_remains_compatible_with_stable_data_provider_contract() -> None:
    assert issubclass(BaseFetcher, DataProvider)

    provider = _DailyProvider("CommunityFetcher", 9, _daily_frame())
    registration = _registration(
        "community",
        lambda: provider,
        markets={"cn", "hk"},
    )

    assert registration.provider_id == "community"
    assert registration.markets == frozenset({"cn", "hk"})
    assert registration.capabilities == frozenset({"daily_data"})


def test_default_providers_are_registered_without_order_or_name_drift() -> None:
    assert DataFetcherManager._BUILTIN_DATA_PROVIDER_IDS == _BUILTIN_IDENTITIES

    config = SimpleNamespace(
        tushare_token="",
        tickflow_api_key="",
        longbridge_app_key="",
        longbridge_app_secret="",
        longbridge_access_token="",
        longbridge_oauth_client_id="",
        finnhub_api_key="",
        alphavantage_api_key="",
    )
    providers = {
        "EfinanceFetcher": _DailyProvider("EfinanceFetcher", 0, _daily_frame()),
        "TencentFetcher": _DailyProvider("TencentFetcher", 0, _daily_frame()),
        "AkshareFetcher": _DailyProvider("AkshareFetcher", 1, _daily_frame()),
        "PytdxFetcher": _DailyProvider("PytdxFetcher", 2, _daily_frame()),
        "BaostockFetcher": _DailyProvider("BaostockFetcher", 3, _daily_frame()),
        "YfinanceFetcher": _DailyProvider("YfinanceFetcher", 4, _daily_frame()),
    }

    with patch("src.config.get_config", return_value=config), patch(
        "data_provider.efinance_fetcher.EfinanceFetcher",
        return_value=providers["EfinanceFetcher"],
    ), patch(
        "data_provider.tencent_fetcher.TencentFetcher",
        return_value=providers["TencentFetcher"],
    ), patch(
        "data_provider.akshare_fetcher.AkshareFetcher",
        return_value=providers["AkshareFetcher"],
    ), patch(
        "data_provider.pytdx_fetcher.PytdxFetcher",
        return_value=providers["PytdxFetcher"],
    ), patch(
        "data_provider.baostock_fetcher.BaostockFetcher",
        return_value=providers["BaostockFetcher"],
    ), patch(
        "data_provider.yfinance_fetcher.YfinanceFetcher",
        return_value=providers["YfinanceFetcher"],
    ), patch(
        "data_provider.longbridge_fetcher.LongbridgeFetcher.has_configured_credentials",
        return_value=False,
    ):
        manager = DataFetcherManager()

    expected_names = list(providers)
    registrations = manager.plugin_registry.registrations("data_provider")

    assert manager.available_fetchers == expected_names
    assert [item.registration_id for item in registrations] == [
        "efinance",
        "tencent",
        "akshare",
        "pytdx",
        "baostock",
        "yfinance",
    ]
    assert [item.priority for item in registrations] == [0, 0, 1, 2, 3, 4]
    assert {item.plugin_id for item in registrations} == {
        "stockpulse.builtin.data-providers"
    }


def test_dynamic_registration_priority_and_exact_unload_control_fallback() -> None:
    fallback = _DailyProvider("FallbackFetcher", 50, _daily_frame(20.0))
    plugin_provider = _DailyProvider("CommunityFetcher", 999, _daily_frame(30.0))
    manager = DataFetcherManager(fetchers=[fallback])
    plugins = _plugin_manager(manager)
    plugin = _ProviderPlugin(
        "community-plugin",
        _registration("community", lambda: plugin_provider),
        priority=10,
    )

    assert plugins.register(plugin, source="external").success is True
    assert plugins.load("community-plugin").success is True

    assert manager.available_fetchers == ["CommunityFetcher", "FallbackFetcher"]
    frame, source = manager.get_daily_data("600519")
    assert source == "CommunityFetcher"
    assert frame.iloc[-1]["close"] == 30.0
    assert fallback.calls == 0

    disabled = plugins.disable("community-plugin")
    assert disabled.success is True
    assert plugin.unload_count == 1
    assert manager.available_fetchers == ["FallbackFetcher"]

    frame, source = manager.get_daily_data("600519")
    assert source == "FallbackFetcher"
    assert frame.iloc[-1]["close"] == 20.0


def test_plugin_market_and_capability_declarations_filter_before_routing() -> None:
    fallback = _DailyProvider("FallbackFetcher", 20, _daily_frame(20.0))
    hk_provider = _DailyProvider("HongKongPluginFetcher", 999, _daily_frame(30.0))
    nondaily_provider = _DailyProvider("RealtimeOnlyFetcher", 1, _daily_frame(40.0))
    manager = DataFetcherManager(fetchers=[fallback])
    plugins = _plugin_manager(manager)
    plugins.register(
        _ProviderPlugin(
            "hk-plugin",
            _registration("hong-kong", lambda: hk_provider, markets={"hk"}),
            priority=1,
        ),
        source="external",
    )
    plugins.register(
        _ProviderPlugin(
            "realtime-plugin",
            _registration(
                "realtime-only",
                lambda: nondaily_provider,
                capabilities={"realtime_quote"},
            ),
            priority=0,
        ),
        source="external",
    )
    results = plugins.load_all()
    assert [result.success for result in results] == [True, True]

    _, cn_source = manager.get_daily_data("600519")
    _, hk_source = manager.get_daily_data("HK00700")

    assert cn_source == "FallbackFetcher"
    assert hk_source == "HongKongPluginFetcher"
    assert nondaily_provider.calls == 0


def test_us_named_route_stays_ahead_of_plugin_priority_then_uses_plugin_fallback() -> None:
    yfinance = _DailyProvider(
        "YfinanceFetcher",
        4,
        TimeoutError("built-in route failed"),
    )
    plugin_provider = _DailyProvider("CommunityUSFetcher", 999, _daily_frame(30.0))
    manager = DataFetcherManager(fetchers=[yfinance])
    plugins = _plugin_manager(manager)
    plugin = _ProviderPlugin(
        "us-plugin",
        _registration("community-us", lambda: plugin_provider, markets={"us"}),
        priority=-100,
    )
    plugins.register(plugin, source="external")
    assert plugins.load("us-plugin").success is True

    _, source = manager.get_daily_data("AAPL")

    assert source == "CommunityUSFetcher"
    assert yfinance.calls == 1
    assert plugin_provider.calls == 1


def test_realtime_plugin_runs_only_after_the_configured_builtin_route() -> None:
    fallback = _DailyProvider("FallbackFetcher", 50, _daily_frame())
    plugin_provider = _DailyProvider("CommunityRealtimeFetcher", 999, _daily_frame())
    realtime_calls = 0

    def realtime_quote(stock_code: str) -> UnifiedRealtimeQuote:
        nonlocal realtime_calls
        realtime_calls += 1
        return UnifiedRealtimeQuote(
            code=stock_code,
            name="Community Quote",
            price=12.5,
        )

    plugin_provider.get_realtime_quote = realtime_quote  # type: ignore[method-assign]
    manager = DataFetcherManager(fetchers=[fallback])
    plugins = _plugin_manager(manager)
    plugin = _ProviderPlugin(
        "realtime-tail-plugin",
        _registration(
            "community-realtime",
            lambda: plugin_provider,
            capabilities={"realtime_quote"},
        ),
        priority=-100,
    )
    plugins.register(plugin, source="external")
    assert plugins.load("realtime-tail-plugin").success is True

    config = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance",
        realtime_cache_ttl=600,
    )
    with patch("src.config.get_config", return_value=config):
        quote = manager.get_realtime_quote("600519")

    assert quote is not None
    assert quote.code == "600519"
    assert quote.price == 12.5
    assert quote.fallback_from == "efinance"
    assert realtime_calls == 1


def test_provider_id_and_runtime_name_collisions_are_rejected() -> None:
    manager = DataFetcherManager(
        fetchers=[_DailyProvider("FallbackFetcher", 50, _daily_frame())]
    )
    plugins = _plugin_manager(manager)
    first_provider = _DailyProvider("CommunityFetcher", 10, _daily_frame())
    first = _ProviderPlugin(
        "first-plugin",
        _registration("community", lambda: first_provider),
        priority=10,
    )
    duplicate_factory_calls = 0

    def duplicate_factory() -> DataProvider:
        nonlocal duplicate_factory_calls
        duplicate_factory_calls += 1
        return _DailyProvider("UnusedFetcher", 20, _daily_frame())

    duplicate_id = _ProviderPlugin(
        "duplicate-id-plugin",
        _registration("community", duplicate_factory),
        priority=20,
    )
    duplicate_name = _ProviderPlugin(
        "duplicate-name-plugin",
        _registration(
            "other-community",
            lambda: _DailyProvider("CommunityFetcher", 30, _daily_frame()),
        ),
        priority=30,
    )
    for plugin in (first, duplicate_id, duplicate_name):
        assert plugins.register(plugin, source="external").success is True

    assert plugins.load("first-plugin").success is True
    id_result = plugins.load("duplicate-id-plugin")
    name_result = plugins.load("duplicate-name-plugin")

    assert id_result.success is False
    assert id_result.error_code == "extension_registration_conflict"
    assert duplicate_factory_calls == 0
    assert name_result.success is False
    assert name_result.error_code == "native_registry_registration_failed"
    assert manager.available_fetchers == ["CommunityFetcher", "FallbackFetcher"]


@pytest.mark.parametrize(
    ("provider_name", "provider_id"),
    tuple(_BUILTIN_IDENTITIES.items()),
)
def test_inactive_builtin_provider_ids_remain_reserved(
    provider_name: str,
    provider_id: str,
) -> None:
    manager = DataFetcherManager(
        fetchers=[_DailyProvider("FallbackFetcher", 50, _daily_frame())]
    )
    plugins = _plugin_manager(manager)
    factory_calls = 0

    def factory() -> DataProvider:
        nonlocal factory_calls
        factory_calls += 1
        return _DailyProvider(f"External{provider_name}", 10, _daily_frame())

    plugin = _ProviderPlugin(
        f"reserved-id-{provider_id}",
        _registration(provider_id, factory),
        priority=10,
    )
    assert plugins.register(plugin, source="external").success is True

    result = plugins.load(plugin.manifest.id)

    assert result.success is False
    assert result.error_code == "native_registration_conflict"
    assert factory_calls == 0
    assert manager.available_fetchers == ["FallbackFetcher"]


@pytest.mark.parametrize(
    ("provider_name", "provider_id"),
    tuple(_BUILTIN_IDENTITIES.items()),
)
def test_inactive_builtin_runtime_names_remain_reserved(
    provider_name: str,
    provider_id: str,
) -> None:
    manager = DataFetcherManager(
        fetchers=[_DailyProvider("FallbackFetcher", 50, _daily_frame())]
    )
    plugins = _plugin_manager(manager)
    plugin = _ProviderPlugin(
        f"reserved-name-{provider_id}",
        _registration(
            f"external-{provider_id}",
            lambda: _DailyProvider(provider_name, 10, _daily_frame()),
        ),
        priority=10,
    )
    assert plugins.register(plugin, source="external").success is True

    result = plugins.load(plugin.manifest.id)

    assert result.success is False
    assert result.error_code == "native_registry_registration_failed"
    assert manager.available_fetchers == ["FallbackFetcher"]


def test_unload_uses_captured_runtime_name_and_retains_call_guard() -> None:
    fallback = _DailyProvider("FallbackFetcher", 50, _daily_frame())
    first_provider = _DailyProvider("MutableFetcher", 10, _daily_frame())
    manager = DataFetcherManager(fetchers=[fallback])
    plugins = _plugin_manager(manager)
    first = _RenamingProviderPlugin(
        "mutable-provider-one",
        _registration("mutable-one", lambda: first_provider),
        first_provider,
        priority=10,
    )
    assert plugins.register(first, source="external").success is True
    assert plugins.load(first.manifest.id).success is True
    routed_first_provider = manager._get_fetcher_by_name("MutableFetcher")
    assert routed_first_provider is not None
    assert routed_first_provider is not first_provider
    original_call_guard = manager._get_fetcher_call_lock(routed_first_provider)

    assert plugins.disable(first.manifest.id).success is True
    assert manager.available_fetchers == ["FallbackFetcher"]
    assert (
        manager._get_fetcher_call_lock(routed_first_provider)
        is original_call_guard
    )

    second_provider = _DailyProvider("MutableFetcher", 10, _daily_frame())
    second = _ProviderPlugin(
        "mutable-provider-two",
        _registration("mutable-two", lambda: second_provider),
        priority=10,
    )
    assert plugins.register(second, source="external").success is True
    assert plugins.load(second.manifest.id).success is True
    assert manager.available_fetchers == ["MutableFetcher", "FallbackFetcher"]


def test_unloaded_snapshot_retains_registration_priority() -> None:
    fallback = _DailyProvider("FallbackFetcher", 50, _daily_frame())
    provider = _DailyProvider("PinnedPriorityFetcher", -100, _daily_frame())
    manager = DataFetcherManager(fetchers=[fallback])
    plugins = _plugin_manager(manager)
    plugin = _ProviderPlugin(
        "pinned-priority-provider",
        _registration("pinned-priority-provider", lambda: provider),
        priority=25,
    )
    assert plugins.register(plugin, source="external").success is True
    assert plugins.load(plugin.manifest.id).success is True
    adapter = manager._get_fetcher_by_name("PinnedPriorityFetcher")

    assert adapter is not None
    assert manager._provider_priority(adapter) == 25
    assert plugins.disable(plugin.manifest.id).success is True
    assert manager.available_fetchers == ["FallbackFetcher"]
    assert manager._provider_priority(adapter) == 25


def test_reenabled_plugin_reuses_call_guard_for_same_factory_instance() -> None:
    fallback = _DailyProvider("FallbackFetcher", 50, _daily_frame())
    shared_provider = _DailyProvider("SharedProvider", 10, _daily_frame())
    manager = DataFetcherManager(fetchers=[fallback])
    plugins = _plugin_manager(manager)
    plugin = _ProviderPlugin(
        "shared-provider-plugin",
        _registration("shared-provider", lambda: shared_provider),
        priority=10,
    )
    assert plugins.register(plugin, source="external").success is True
    assert plugins.load(plugin.manifest.id).success is True
    first_adapter = manager._get_fetcher_by_name("SharedProvider")
    assert first_adapter is not None
    first_guard = manager._get_fetcher_call_lock(first_adapter)

    assert plugins.disable(plugin.manifest.id).success is True
    assert manager.available_fetchers == ["FallbackFetcher"]
    assert plugins.enable(plugin.manifest.id).success is True
    second_adapter = manager._get_fetcher_by_name("SharedProvider")

    assert second_adapter is not None
    assert second_adapter is not first_adapter
    assert manager._get_fetcher_call_lock(second_adapter) is first_guard


def test_enabled_plugin_runtime_name_is_pinned_before_fixed_route_lookup() -> None:
    yfinance = _DailyProvider("YfinanceFetcher", 4, _daily_frame(20.0))
    plugin_provider = _DailyProvider("MutablePluginFetcher", 999, _daily_frame(30.0))
    manager = DataFetcherManager(fetchers=[yfinance])
    plugins = _plugin_manager(manager)
    plugin = _ProviderPlugin(
        "mutable-active-provider",
        _registration(
            "mutable-active-provider",
            lambda: plugin_provider,
            markets={"cn", "us"},
        ),
        priority=-100,
    )
    assert plugins.register(plugin, source="external").success is True
    assert plugins.load(plugin.manifest.id).success is True

    plugin_provider.name = "YfinanceFetcher"

    assert manager.available_fetchers == [
        "MutablePluginFetcher",
        "YfinanceFetcher",
    ]
    assert manager._get_fetcher_by_name("YfinanceFetcher") is yfinance
    routed_plugin = manager._get_fetcher_by_name("MutablePluginFetcher")
    assert routed_plugin is not None
    assert routed_plugin is not plugin_provider

    plugin_frame, plugin_source = manager.get_daily_data("600519")

    assert plugin_source == "MutablePluginFetcher"
    assert plugin_frame.iloc[-1]["close"] == 30.0
    assert manager._daily_health_key(routed_plugin, "cn") == (
        "daily_data:cn:MutablePluginFetcher"
    )

    frame, source = manager.get_daily_data("AAPL")

    assert source == "YfinanceFetcher"
    assert frame.iloc[-1]["close"] == 20.0
    assert yfinance.calls == 1
    assert plugin_provider.calls == 1


def test_realtime_route_calls_selected_market_eligible_snapshot_after_reload() -> None:
    fallback = _DailyProvider("FallbackFetcher", 50, _daily_frame())
    us_provider = _DailyProvider("SharedRealtimeFetcher", 10, _daily_frame())
    cn_provider = _DailyProvider("SharedRealtimeFetcher", 10, _daily_frame())
    us_calls = 0
    cn_calls = 0

    def us_quote(stock_code: str) -> UnifiedRealtimeQuote:
        nonlocal us_calls
        us_calls += 1
        return UnifiedRealtimeQuote(code=stock_code, name="US", price=11.0)

    def cn_quote(stock_code: str) -> UnifiedRealtimeQuote:
        nonlocal cn_calls
        cn_calls += 1
        return UnifiedRealtimeQuote(code=stock_code, name="CN", price=22.0)

    us_provider.get_realtime_quote = us_quote  # type: ignore[method-assign]
    cn_provider.get_realtime_quote = cn_quote  # type: ignore[method-assign]
    manager = DataFetcherManager(fetchers=[fallback])
    plugins = _plugin_manager(manager)
    us_plugin = _ProviderPlugin(
        "shared-realtime-us",
        _registration(
            "shared-realtime-us",
            lambda: us_provider,
            markets={"us"},
            capabilities={"realtime_quote"},
        ),
        priority=10,
    )
    cn_plugin = _ProviderPlugin(
        "shared-realtime-cn",
        _registration(
            "shared-realtime-cn",
            lambda: cn_provider,
            markets={"cn"},
            capabilities={"realtime_quote"},
        ),
        priority=10,
    )
    for plugin in (us_plugin, cn_plugin):
        assert plugins.register(plugin, source="external").success is True
    assert plugins.load(us_plugin.manifest.id).success is True

    selected = Event()
    resume = Event()
    route_result: dict[str, object] = {}
    original_try_quote = manager._try_fetcher_quote

    def delayed_try_quote(stock_code: str, fetcher_name: str, **kwargs):
        selected.set()
        assert resume.wait(timeout=2)
        return original_try_quote(stock_code, fetcher_name, **kwargs)

    def route_us_quote() -> None:
        try:
            route_result["value"] = manager._try_plugin_realtime_quote(
                "AAPL",
                "us",
            )
        except BaseException as exc:
            route_result["error"] = exc

    with patch.object(
        manager,
        "_try_fetcher_quote",
        side_effect=delayed_try_quote,
    ):
        route_thread = Thread(target=route_us_quote)
        route_thread.start()
        try:
            assert selected.wait(timeout=2)
            assert plugins.disable(us_plugin.manifest.id).success is True
            assert manager.available_fetchers == ["FallbackFetcher"]
            assert plugins.load(cn_plugin.manifest.id).success is True
            assert manager.available_fetchers == [
                "SharedRealtimeFetcher",
                "FallbackFetcher",
            ]
        finally:
            resume.set()
            route_thread.join(timeout=2)

    assert route_thread.is_alive() is False
    assert "error" not in route_result
    quote, provider_name = route_result["value"]
    assert quote is not None
    assert quote.price == 11.0
    assert provider_name == "SharedRealtimeFetcher"
    assert us_calls == 1
    assert cn_calls == 0


def _route_while_unload_precedes_eligibility_filter(
    manager: DataFetcherManager,
    plugins: PluginManager,
    plugin_id: str,
    route: Callable[[], object],
) -> object:
    captured = Event()
    resume = Event()
    result: dict[str, object] = {}
    original_snapshot = manager._get_fetchers_snapshot

    def delayed_snapshot():
        snapshot = original_snapshot()
        captured.set()
        assert resume.wait(timeout=2)
        return snapshot

    def invoke_route() -> None:
        try:
            result["value"] = route()
        except BaseException as exc:
            result["error"] = exc

    with patch.object(
        manager,
        "_get_fetchers_snapshot",
        side_effect=delayed_snapshot,
    ):
        route_thread = Thread(target=invoke_route)
        route_thread.start()
        try:
            assert captured.wait(timeout=2)
            assert plugins.disable(plugin_id).success is True
            manager._sync_registered_data_providers()
        finally:
            resume.set()
            route_thread.join(timeout=2)

    assert route_thread.is_alive() is False
    assert "error" not in result
    return result["value"]


def test_provider_snapshot_retains_market_eligibility_during_unload() -> None:
    fallback = _DailyProvider("FallbackFetcher", 50, _daily_frame(9.0))
    cn_provider = _DailyProvider("CnOnlyFetcher", 10, _daily_frame(33.0))
    manager = DataFetcherManager(fetchers=[fallback])
    plugins = _plugin_manager(manager)
    plugin = _ProviderPlugin(
        "cn-only-snapshot",
        _registration(
            "cn-only-snapshot",
            lambda: cn_provider,
            markets={"cn"},
        ),
        priority=10,
    )
    assert plugins.register(plugin, source="external").success is True
    assert plugins.load(plugin.manifest.id).success is True

    _, source = _route_while_unload_precedes_eligibility_filter(
        manager,
        plugins,
        plugin.manifest.id,
        lambda: manager.get_daily_data("HK00700"),
    )

    assert source == "FallbackFetcher"
    assert cn_provider.calls == 0
    assert fallback.calls == 1


def test_provider_snapshot_retains_capability_eligibility_during_unload() -> None:
    fallback = _DailyProvider("FallbackFetcher", 50, _daily_frame())
    plugin_provider = _DailyProvider("DailyOnlyFetcher", 10, _daily_frame())
    hot_stock_calls = 0

    def plugin_hot_stocks(n: int):
        nonlocal hot_stock_calls
        hot_stock_calls += 1
        return [{"code": "600519", "rank": 1}][:n]

    fallback.get_hot_stocks = lambda n: []  # type: ignore[attr-defined]
    plugin_provider.get_hot_stocks = plugin_hot_stocks  # type: ignore[attr-defined]
    manager = DataFetcherManager(fetchers=[fallback])
    plugins = _plugin_manager(manager)
    plugin = _ProviderPlugin(
        "daily-only-snapshot",
        _registration(
            "daily-only-snapshot",
            lambda: plugin_provider,
            capabilities={"daily_data"},
        ),
        priority=10,
    )
    assert plugins.register(plugin, source="external").success is True
    assert plugins.load(plugin.manifest.id).success is True

    rows = _route_while_unload_precedes_eligibility_filter(
        manager,
        plugins,
        plugin.manifest.id,
        lambda: manager.get_hot_stocks(5),
    )

    assert rows == []
    assert hot_stock_calls == 0


def test_stock_list_plugin_enforces_market_before_call_and_result_acceptance() -> None:
    fallback = _DailyProvider("FallbackFetcher", 50, _daily_frame())
    hk_provider = _DailyProvider("HongKongStockListFetcher", 10, _daily_frame())
    stock_list_calls = 0

    def get_stock_list() -> pd.DataFrame:
        nonlocal stock_list_calls
        stock_list_calls += 1
        return pd.DataFrame(
            {
                "code": ["HK00700", "600519"],
                "name": ["Tencent", "Plugin CN Name"],
            }
        )

    hk_provider.get_stock_list = get_stock_list  # type: ignore[attr-defined]
    manager = DataFetcherManager(fetchers=[fallback])
    plugins = _plugin_manager(manager)
    plugin = _ProviderPlugin(
        "hong-kong-stock-list",
        _registration(
            "hong-kong-stock-list",
            lambda: hk_provider,
            markets={"hk"},
            capabilities={"stock_list"},
        ),
        priority=10,
    )
    assert plugins.register(plugin, source="external").success is True
    assert plugins.load(plugin.manifest.id).success is True

    with patch.object(manager, "get_stock_name", return_value=""):
        assert manager.batch_get_stock_names(["600519"]) == {}
    assert stock_list_calls == 0

    with patch.object(manager, "get_stock_name", return_value="Fallback CN Name"):
        result = manager.batch_get_stock_names(["600519", "HK00700"])

    assert stock_list_calls == 1
    assert result == {
        "HK00700": "Tencent",
        "600519": "Fallback CN Name",
    }
    assert manager._stock_name_cache == {"HK00700": "Tencent"}


def test_factory_failure_isolated_while_later_plugin_remains_available() -> None:
    fallback = _DailyProvider("FallbackFetcher", 50, _daily_frame())
    healthy_provider = _DailyProvider("HealthyPluginFetcher", 10, _daily_frame(30.0))
    manager = DataFetcherManager(fetchers=[fallback])
    plugins = _plugin_manager(manager)

    def failing_factory() -> DataProvider:
        raise RuntimeError("token=factory-secret")

    failing = _ProviderPlugin(
        "failing-provider-plugin",
        _registration("failing-provider", failing_factory),
        priority=1,
    )
    healthy = _ProviderPlugin(
        "healthy-provider-plugin",
        _registration("healthy-provider", lambda: healthy_provider),
        priority=10,
    )
    plugins.register(failing, source="external")
    plugins.register(healthy, source="external")

    results = plugins.load_all()

    assert [result.success for result in results] == [False, True]
    assert results[0].error_code == "native_registry_registration_failed"
    assert manager.available_fetchers == ["HealthyPluginFetcher", "FallbackFetcher"]
    _, source = manager.get_daily_data("600519")
    assert source == "HealthyPluginFetcher"
