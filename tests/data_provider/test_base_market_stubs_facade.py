# -*- coding: utf-8 -*-
"""Facade, inheritance, and reload characterization for BaseFetcher market stubs.

Issue #1067: the six default market-overview/rankings stubs moved into
``src/data_provider/base_parts/market_stubs.py`` and are rebound onto
``BaseFetcher``. Bodies stay ``return None``. Provider overrides stay in
their existing modules.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
from pathlib import Path

import pandas as pd
import pytest

import src.data_provider.base as base_mod
import src.data_provider.base_parts.market_stubs as stubs_mod
from src.data_provider.base import BaseFetcher, DataFetcherManager

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    REPO_ROOT / "src" / "data_provider" / "base_parts" / "market_stubs.py"
)

MOVED = (
    "get_main_indices",
    "get_market_stats",
    "get_sector_rankings",
    "get_concept_rankings",
    "get_hot_stocks",
    "get_limit_up_pool",
)

METHOD_SIGNATURES = {
    "get_main_indices": ["self", "region"],
    "get_market_stats": ["self"],
    "get_sector_rankings": ["self", "n"],
    "get_concept_rankings": ["self", "n"],
    "get_hot_stocks": ["self", "n"],
    "get_limit_up_pool": ["self", "date", "n"],
}

METHOD_DEFAULTS = {
    "get_main_indices": {"region": "cn"},
    "get_market_stats": {},
    "get_sector_rankings": {"n": 5},
    "get_concept_rankings": {"n": 5},
    "get_hot_stocks": {"n": 10},
    "get_limit_up_pool": {"date": None, "n": 20},
}

SUBCLASS_MODULES = (
    "akshare_fetcher",
    "efinance_fetcher",
    "longbridge_fetcher",
    "tushare_fetcher",
    "yfinance_fetcher",
    "baostock_fetcher",
    "tickflow_fetcher",
    "crypto_coingecko_fetcher",
    "tencent_fetcher",
    "alphavantage_fetcher",
    "pytdx_fetcher",
    "finnhub_fetcher",
)

OVERRIDDEN_BY_CLASS = {
    "AkshareFetcher": set(MOVED),
    "EfinanceFetcher": {"get_main_indices", "get_market_stats", "get_sector_rankings"},
    "TickFlowFetcher": {"get_main_indices", "get_market_stats", "get_sector_rankings"},
    "TushareFetcher": {"get_main_indices", "get_market_stats", "get_sector_rankings"},
    "YfinanceFetcher": {"get_main_indices"},
    "CryptoCoingeckoFetcher": {"get_limit_up_pool"},
}


def _descriptor_function(descriptor):
    return getattr(descriptor, "__func__", descriptor)


def _defining_class(cls: type, name: str) -> type | None:
    for candidate in cls.__mro__:
        if name in candidate.__dict__:
            return candidate
    return None


class _Probe(BaseFetcher):
    name = "ProbeFetcher"
    priority = 99

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str):
        del stock_code, start_date, end_date
        return pd.DataFrame()

    def _normalize_data(self, df, stock_code: str):
        del stock_code
        return df


def _production_subclasses() -> list[type]:
    found: list[type] = []
    for module_name in SUBCLASS_MODULES:
        module = importlib.import_module(f"src.data_provider.{module_name}")
        subclasses = [
            value
            for value in vars(module).values()
            if isinstance(value, type)
            and issubclass(value, BaseFetcher)
            and value is not BaseFetcher
        ]
        assert subclasses, module_name
        found.extend(subclasses)
    return found


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_base_class(name) -> None:
    assert callable(getattr(BaseFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    function = _descriptor_function(BaseFetcher.__dict__[name])
    assert function.__module__ == "src.data_provider.base", name
    assert function.__qualname__ == f"BaseFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    function = _descriptor_function(BaseFetcher.__dict__[name])
    assert function.__globals__ is vars(base_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_and_defaults_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(BaseFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]
    defaults = {
        parameter_name: parameter.default
        for parameter_name, parameter in signature.parameters.items()
        if parameter.default is not inspect.Parameter.empty
    }
    assert defaults == METHOD_DEFAULTS[name]


def test_public_imports_stay_on_the_facade() -> None:
    from src.data_provider import BaseFetcher as exported

    assert exported is BaseFetcher
    assert BaseFetcher.__module__ == "src.data_provider.base"
    assert not hasattr(stubs_mod, "BaseFetcher")


def test_owner_module_declares_exactly_the_slice() -> None:
    assert stubs_mod.EXPECTED_MARKET_STUB_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_MarketStubMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(MOVED)


def test_bodies_no_longer_live_in_the_facade_class() -> None:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BaseFetcher"
    )
    defined = {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assigns = {
        target.id
        for node in cls.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    for name in MOVED:
        assert name not in defined, name
        assert name in assigns, name
    source = FACADE_PATH.read_text(encoding="utf-8")
    for name in MOVED:
        assert f"    {name} = None" in source, name


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any(module.endswith("data_provider.base") for module in imported)


def test_facade_bind_is_reused_not_copied() -> None:
    from src.data_provider._facade_bind import bind_methods_from_class as shared
    from src.data_provider.base_parts.facade_bind import bind_methods_from_class

    assert bind_methods_from_class is shared
    assert stubs_mod.bind_methods_from_class is shared


def test_unoverridden_probe_returns_none() -> None:
    probe = _Probe()
    assert probe.get_main_indices() is None
    assert probe.get_main_indices(region="us") is None
    assert probe.get_market_stats() is None
    assert probe.get_sector_rankings() is None
    assert probe.get_concept_rankings(n=3) is None
    assert probe.get_hot_stocks() is None
    assert probe.get_limit_up_pool(date="20260101", n=5) is None


def test_every_production_subclass_is_inventoried() -> None:
    subclasses = _production_subclasses()
    names = {cls.__name__ for cls in subclasses}
    assert names == {
        "AkshareFetcher",
        "EfinanceFetcher",
        "LongbridgeFetcher",
        "TushareFetcher",
        "YfinanceFetcher",
        "BaostockFetcher",
        "TickFlowFetcher",
        "CryptoCoingeckoFetcher",
        "TencentFetcher",
        "AlphaVantageFetcher",
        "PytdxFetcher",
        "FinnhubFetcher",
    }


@pytest.mark.parametrize("module_name", SUBCLASS_MODULES)
def test_inherit_vs_override_across_production_subclasses(module_name) -> None:
    module = importlib.import_module(f"src.data_provider.{module_name}")
    subclasses = [
        value
        for value in vars(module).values()
        if isinstance(value, type)
        and issubclass(value, BaseFetcher)
        and value is not BaseFetcher
    ]
    assert subclasses, module_name
    for subclass in subclasses:
        overridden = OVERRIDDEN_BY_CLASS.get(subclass.__name__, set())
        for name in MOVED:
            owner = _defining_class(subclass, name)
            assert owner is not None, f"{subclass.__name__}.{name}"
            if name in overridden:
                assert owner is not BaseFetcher, f"{subclass.__name__}.{name}"
            else:
                assert owner is BaseFetcher, f"{subclass.__name__}.{name}"
                assert callable(getattr(subclass, name))


def test_crypto_limit_up_pool_override_returns_empty_list() -> None:
    from src.data_provider.crypto_coingecko_fetcher import CryptoCoingeckoFetcher

    result = CryptoCoingeckoFetcher.get_limit_up_pool(object(), date="20260101", n=5)
    assert result == []
    assert _Probe().get_limit_up_pool() is None


def test_manager_miss_path_skips_none_stubs() -> None:
    manager = DataFetcherManager(fetchers=[_Probe()])
    assert manager.get_main_indices(region="cn") == []
    assert manager.get_hot_stocks(n=10) == []
    assert manager.get_limit_up_pool(date=None, n=20) == []


def test_owner_reload_rebinds_onto_the_base_class() -> None:
    before = {
        name: _descriptor_function(BaseFetcher.__dict__[name])
        for name in MOVED
    }
    importlib.reload(stubs_mod)
    for name in MOVED:
        function = _descriptor_function(BaseFetcher.__dict__[name])
        assert function is not before[name], name
        assert function.__globals__ is vars(base_mod), name
        assert function.__qualname__ == f"BaseFetcher.{name}", name
    assert _Probe().get_market_stats() is None


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.base_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_main_indices(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(base_mod), expected_names=MOVED,
        )


def test_stub_bodies_match_origin_main_return_none() -> None:
    main_source = subprocess.check_output(
        ["git", "show", "origin/main:src/data_provider/base.py"],
        cwd=REPO_ROOT,
        text=True,
    )
    # Pin against the freeze start SHA when origin/main has moved past it.
    pin_source = subprocess.check_output(
        [
            "git",
            "show",
            "c5f321fde29f6f62b08b9c5ac3eff9675b742b5c:src/data_provider/base.py",
        ],
        cwd=REPO_ROOT,
        text=True,
    )
    del main_source  # freeze pin is the behavior source of truth
    main_tree = ast.parse(pin_source)
    main_cls = next(
        node
        for node in main_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BaseFetcher"
    )
    main_bodies = {
        node.name: ast.dump(node.body[0] if len(node.body) == 1 else ast.Module(body=node.body, type_ignores=[]))
        for node in main_cls.body
        if isinstance(node, ast.FunctionDef) and node.name in MOVED
    }
    owner_tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    owner_cls = next(
        node
        for node in owner_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "_MarketStubMethods"
    )
    owner_bodies = {
        node.name: ast.dump(node.body[0] if len(node.body) == 1 else ast.Module(body=node.body, type_ignores=[]))
        for node in owner_cls.body
        if isinstance(node, ast.FunctionDef) and node.name in MOVED
    }
    assert set(main_bodies) == set(MOVED)
    assert set(owner_bodies) == set(MOVED)
    for name in MOVED:
        assert "return None" in ast.unparse(
            next(
                node
                for node in owner_cls.body
                if isinstance(node, ast.FunctionDef) and node.name == name
            )
        )
        assert main_bodies[name] == owner_bodies[name], name
