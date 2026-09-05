# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for market-overview extraction."""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

import src.data_provider.base as base
import src.data_provider.manager_parts.market_overview_methods as market_overview
from src.data_provider.base import BaseFetcher, DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "market_overview_methods.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def test_market_overview_methods_remain_on_data_fetcher_manager_facade() -> None:
    for name in market_overview.EXPECTED_MARKET_OVERVIEW_METHOD_NAMES:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_public_market_overview_signatures_are_unchanged() -> None:
    indices = inspect.signature(DataFetcherManager.get_main_indices)
    assert list(indices.parameters) == ["self", "region"]
    region = indices.parameters["region"]
    assert region.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert region.default == "cn"

    stats = inspect.signature(DataFetcherManager.get_market_stats)
    assert list(stats.parameters) == ["self", "purpose"]
    purpose = stats.parameters["purpose"]
    assert purpose.kind is inspect.Parameter.KEYWORD_ONLY
    assert purpose.default == "unspecified"


def test_moved_names_are_not_validation_wrapped() -> None:
    for name in market_overview.EXPECTED_MARKET_OVERVIEW_METHOD_NAMES:
        method = DataFetcherManager.__dict__[name]
        assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_owner_module_exists_for_market_overview_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "market_overview_methods" in source
    assert "bind_market_overview_methods_facade" in source
    assert "get_main_indices = None" in source
    assert "get_market_stats = None" in source
    importlib.import_module("src.data_provider.manager_parts.market_overview_methods")


def test_market_overview_bodies_leave_manager_and_stay_on_base_fetcher() -> None:
    tree = ast.parse(BASE_PATH.read_text(encoding="utf-8"))
    manager_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "DataFetcherManager"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in market_overview.EXPECTED_MARKET_OVERVIEW_METHOD_NAMES:
        assert name not in manager_defs, name

    base_fetcher_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "BaseFetcher"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in market_overview.EXPECTED_MARKET_OVERVIEW_METHOD_NAMES:
        assert name not in base_fetcher_defs, name


def test_base_fetcher_provider_methods_are_untouched() -> None:
    for name in market_overview.EXPECTED_MARKET_OVERVIEW_METHOD_NAMES:
        assert name in vars(BaseFetcher), name
        function = _descriptor_function(vars(BaseFetcher)[name])
        assert function.__qualname__ == f"BaseFetcher.{name}", name
        assert function.__module__ == "src.data_provider.base", name

    indices = inspect.signature(BaseFetcher.get_main_indices)
    assert list(indices.parameters) == ["self", "region"]
    stats = inspect.signature(BaseFetcher.get_market_stats)
    assert list(stats.parameters) == ["self"]


def test_market_overview_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(market_overview._MarketOverviewMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == market_overview.__name__
    assert tuple(source_names) == market_overview.EXPECTED_MARKET_OVERVIEW_METHOD_NAMES


def test_market_overview_placeholders_preserve_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    assert names.index("batch_get_stock_names") < names.index("get_main_indices")
    assert names.index("get_main_indices") < names.index("get_market_stats")
    assert names.index("get_market_stats") < names.index("_run_with_timeout")


def test_bind_returns_expected_names_in_class_body_order() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    bound = market_overview.bind_market_overview_methods_facade(
        dummy,
        vars(base),
    )
    assert bound == market_overview.EXPECTED_MARKET_OVERVIEW_METHOD_NAMES


def test_assemble_raises_import_error_on_expected_name_mismatch() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    extra = staticmethod(lambda self: [])
    market_overview._MarketOverviewMethods._extra_overview = extra
    try:
        bound = market_overview.bind_market_overview_methods_facade(
            dummy,
            vars(base),
        )
        with pytest.raises(
            ImportError,
            match="Unexpected DataFetcherManager market-overview methods",
        ):
            if bound != market_overview.EXPECTED_MARKET_OVERVIEW_METHOD_NAMES:
                raise ImportError(
                    "Unexpected DataFetcherManager market-overview methods: "
                    f"{bound!r}"
                )
        assert "_extra_overview" in bound
    finally:
        delattr(market_overview._MarketOverviewMethods, "_extra_overview")


def test_owner_module_declares_expected_names_only() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_MarketOverviewMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(market_overview.EXPECTED_MARKET_OVERVIEW_METHOD_NAMES)


def test_owner_module_has_zero_bare_get_config_and_forbidden_imports() -> None:
    source = OWNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_prefixes = (
        "src.config",
        "src.core",
        "src.services",
        "src.data_provider.base",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "get_config"
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            assert not any(
                node.module == prefix or node.module.startswith(prefix + ".")
                for prefix in forbidden_prefixes
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == prefix or alias.name.startswith(prefix + ".")
                    for prefix in forbidden_prefixes
                )


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.market_overview_methods as market_overview",
                    "",
                    "names = market_overview.EXPECTED_MARKET_OVERVIEW_METHOD_NAMES",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    original = getattr(",
                    "        descriptor,",
                    "        '_stockpulse_data_validation_original',",
                    "        None,",
                    "    )",
                    "    return original if original is not None else descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    facade = {}",
                    "    for name in names:",
                    "        source[name] = descriptor_function(",
                    "            vars(market_overview._MarketOverviewMethods)[name]",
                    "        )",
                    "        facade[name] = descriptor_function(",
                    "            vars(base.DataFetcherManager)[name]",
                    "        )",
                    "        assert facade[name] is not source[name]",
                    "        assert facade[name].__code__ is source[name].__code__",
                    "        assert facade[name].__globals__ is vars(base)",
                    "        assert facade[name].__module__ == 'src.data_provider.base'",
                    "        assert facade[name].__qualname__ == f'DataFetcherManager.{name}'",
                    "    return source, facade",
                    "",
                    body,
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_owner_reload_rebinds_loaded_facade() -> None:
    _run_reload_contract(
        """
old_class = base.DataFetcherManager
before_source, before_facade = bindings()
market_overview = importlib.reload(market_overview)
assert base.DataFetcherManager is old_class
after_source, after_facade = bindings()
for name in names:
    assert after_source[name] is not before_source[name]
    assert after_facade[name] is not before_facade[name]
    assert after_facade[name].__code__ is after_source[name].__code__
"""
    )


def test_facade_then_owner_reload_keeps_one_current_contract() -> None:
    _run_reload_contract(
        """
old_class = base.DataFetcherManager
before_source, before_facade = bindings()
base = importlib.reload(base)
assert base.DataFetcherManager is not old_class
after_base_source, after_base_facade = bindings()
for name in names:
    assert after_base_source[name] is before_source[name]
    assert after_base_facade[name] is not before_facade[name]
reloaded_class = base.DataFetcherManager
market_overview = importlib.reload(market_overview)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_package_export_still_exposes_data_fetcher_manager() -> None:
    from src.data_provider import DataFetcherManager as PackageManager

    assert PackageManager is DataFetcherManager
    assert inspect.isclass(PackageManager)
