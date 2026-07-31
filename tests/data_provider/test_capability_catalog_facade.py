# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Compatibility guards for the DataFetcherManager capability catalog facade."""

import __future__
import inspect
import subprocess
import sys
from types import SimpleNamespace

import data_provider
import data_provider._capability_catalog as capability_catalog
import data_provider.base as base


_MOVED_DESCRIPTOR_CONTRACT = {
    "plugin_registry": ("property", "(self) -> 'ExtensionRegistry'"),
    "_assign_fetcher_static_order_locked": (
        "function",
        "(self, fetcher: data_provider.base.DataProvider) -> None",
    ),
    "_provider_priority": (
        "function",
        "(self, fetcher: data_provider.base.DataProvider) -> int",
    ),
    "_sort_fetchers_locked": ("function", "(self) -> None"),
    "_remove_registered_fetcher_locked": (
        "function",
        "(self, fetcher: data_provider.base.DataProvider) -> None",
    ),
    "_sync_registered_data_providers": ("function", "(self) -> None"),
    "_get_fetchers_snapshot": (
        "function",
        "(self) -> List[data_provider.base.DataProvider]",
    ),
    "_provider_plugin_registration": (
        "staticmethod",
        "(fetcher: object) -> Optional[ForwardRef('DataProviderRegistration')]",
    ),
    "_provider_supports_capability": (
        "function",
        (
            "(self, fetcher: data_provider.base.DataProvider, capability: str, "
            "market: Optional[str] = None) -> bool"
        ),
    ),
    "_get_fetchers_for_capability": (
        "function",
        (
            "(self, capability: str, *, market: Optional[str] = None, "
            "plugins_only: bool = False) -> List[data_provider.base.DataProvider]"
        ),
    ),
    "_refresh_fetcher_indexes_locked": ("function", "(self) -> None"),
    "_get_fetcher_by_name": (
        "function",
        (
            "(self, fetcher_name: str, capability: str = '') -> "
            "Optional[data_provider.base.DataProvider]"
        ),
    ),
    "_call_availability_probe": (
        "staticmethod",
        (
            "(fetcher: data_provider.base.BaseFetcher, probe_name: str, "
            "capability: str) -> Optional[bool]"
        ),
    ),
    "_is_fetcher_available": (
        "classmethod",
        (
            "(cls, fetcher: data_provider.base.BaseFetcher, "
            "capability: str = '') -> bool"
        ),
    ),
    "_filter_daily_fetchers_for_market": (
        "function",
        (
            "(self, fetchers: List[data_provider.base.DataProvider], "
            "market: str) -> List[data_provider.base.DataProvider]"
        ),
    ),
    "_filter_fetchers_by_capability": (
        "function",
        (
            "(self, fetchers: List[data_provider.base.DataProvider], "
            "capability: str) -> List[data_provider.base.DataProvider]"
        ),
    ),
    "_register_builtin_data_provider": (
        "function",
        "(self, fetcher: object) -> None",
    ),
    "add_fetcher": (
        "function",
        "(self, fetcher: data_provider.base.DataProvider) -> None",
    ),
    "available_fetchers": ("property", "(self) -> List[str]"),
}


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__, type(descriptor).__name__
    if isinstance(descriptor, property):
        return descriptor.fget, "property"
    return descriptor, "function"


def test_capability_catalog_facade_preserves_import_and_reflection_contract() -> None:
    assert data_provider.DataFetcherManager is base.DataFetcherManager

    for name, (expected_kind, expected_signature) in (
        _MOVED_DESCRIPTOR_CONTRACT.items()
    ):
        descriptor = vars(base.DataFetcherManager)[name]
        function, kind = _descriptor_function(descriptor)

        assert kind == expected_kind
        assert str(inspect.signature(function)) == expected_signature
        assert function.__module__ == "data_provider.base"
        assert function.__qualname__ == f"DataFetcherManager.{name}"
        assert function.__globals__ is vars(base)
        assert not (
            function.__code__.co_flags
            & __future__.annotations.compiler_flag
        )


def test_private_catalog_owns_facade_implementations_and_inventory() -> None:
    for name in (
        "_DAILY_MARKET_FETCHER_SUPPORT",
        "_BUILTIN_DATA_PROVIDER_IDS",
        "_BUILTIN_DATA_PROVIDER_PLUGIN_ID",
        "_DAILY_MARKETS",
    ):
        assert getattr(base.DataFetcherManager, name) is getattr(
            capability_catalog,
            name,
        )

    source_names = []
    for name, source_descriptor in vars(
        capability_catalog._CapabilityCatalogMethods
    ).items():
        source_function, _kind = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function, _kind = _descriptor_function(
            vars(base.DataFetcherManager)[name]
        )

        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == capability_catalog.__name__

    assert tuple(source_names) == tuple(_MOVED_DESCRIPTOR_CONTRACT)


def test_capability_catalog_reload_rebuilds_mutable_inventory() -> None:
    code = r"""
import importlib
import data_provider._capability_catalog as capability_catalog
import data_provider.base as base

inventory_names = (
    "_DAILY_MARKET_FETCHER_SUPPORT",
    "_BUILTIN_DATA_PROVIDER_IDS",
    "_BUILTIN_DATA_PROVIDER_PLUGIN_ID",
    "_DAILY_MARKETS",
)
old_support = base.DataFetcherManager._DAILY_MARKET_FETCHER_SUPPORT
old_provider_ids = base.DataFetcherManager._BUILTIN_DATA_PROVIDER_IDS
old_support["MutatedFetcher"] = {"us"}
old_support["EfinanceFetcher"].add("us")
old_provider_ids["MutatedFetcher"] = "mutated"

assert capability_catalog._DAILY_MARKET_FETCHER_SUPPORT is old_support
assert capability_catalog._BUILTIN_DATA_PROVIDER_IDS is old_provider_ids

first = importlib.reload(base)
first_support = first.DataFetcherManager._DAILY_MARKET_FETCHER_SUPPORT
first_provider_ids = first.DataFetcherManager._BUILTIN_DATA_PROVIDER_IDS

assert first_support is not old_support
assert first_provider_ids is not old_provider_ids
assert "MutatedFetcher" not in first_support
assert "MutatedFetcher" not in first_provider_ids
assert first_support["EfinanceFetcher"] == {"cn"}
for name in inventory_names:
    assert getattr(first.DataFetcherManager, name) is getattr(
        capability_catalog,
        name,
    )

second = importlib.reload(first)
assert second.DataFetcherManager._DAILY_MARKET_FETCHER_SUPPORT is not first_support
assert second.DataFetcherManager._BUILTIN_DATA_PROVIDER_IDS is not first_provider_ids
for name in inventory_names:
    assert getattr(second.DataFetcherManager, name) is getattr(
        capability_catalog,
        name,
    )
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_capability_catalog_availability_probe_uses_base_patch_seam(
    monkeypatch,
) -> None:
    recorded = []
    fetcher = SimpleNamespace(
        name="UnavailableFetcher",
        is_available_for_request=lambda _capability: (_ for _ in ()).throw(
            RuntimeError("probe failed")
        ),
    )
    monkeypatch.setattr(
        base,
        "log_safe_exception",
        lambda *args, **kwargs: recorded.append((args, kwargs)),
    )

    assert (
        base.DataFetcherManager._call_availability_probe(
            fetcher,
            "is_available_for_request",
            "daily_data",
        )
        is False
    )
    assert len(recorded) == 1
    assert recorded[0][1]["context"] == {
        "provider": "UnavailableFetcher",
        "probe": "is_available_for_request",
        "capability": "daily_data",
    }


def test_capability_filtering_uses_manager_patch_seams(monkeypatch) -> None:
    manager = object.__new__(base.DataFetcherManager)
    first = SimpleNamespace(name="FirstFetcher")
    second = SimpleNamespace(name="SecondFetcher")
    capability_checks = []
    availability_checks = []

    monkeypatch.setattr(
        base.DataFetcherManager,
        "_provider_supports_capability",
        lambda self, fetcher, capability, market=None: (
            capability_checks.append((fetcher.name, capability, market))
            or fetcher is first
        ),
    )
    monkeypatch.setattr(
        base.DataFetcherManager,
        "_is_fetcher_available",
        classmethod(
            lambda cls, fetcher, capability="": (
                availability_checks.append((fetcher.name, capability))
                or True
            )
        ),
    )

    assert manager._filter_fetchers_by_capability(
        [first, second],
        "stock_list",
    ) == [first]
    assert capability_checks == [
        ("FirstFetcher", "stock_list", None),
        ("SecondFetcher", "stock_list", None),
    ]
    assert availability_checks == [("FirstFetcher", "stock_list")]
