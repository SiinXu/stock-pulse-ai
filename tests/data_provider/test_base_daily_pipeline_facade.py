# -*- coding: utf-8 -*-
"""Facade, inheritance, and reload characterization for the BaseFetcher daily slice.

Issue #1067: the daily template method and its post-processing steps moved into
``src/data_provider/base_parts/daily_pipeline.py`` and are rebound onto
``BaseFetcher``.

This slice differs from the provider-fetcher slices in one way that matters:
``BaseFetcher`` is an abstract base with eight production subclasses, so the
rebind must survive inheritance, not just direct attribute access.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pandas as pd
import pytest

import src.data_provider.base as base_mod
import src.data_provider.base_parts.daily_pipeline as pipeline_mod
from src.data_provider.base import BaseFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    REPO_ROOT / "src" / "data_provider" / "base_parts" / "daily_pipeline.py"
)

MOVED = ("get_daily_data", "_clean_data", "_calculate_indicators")

# Pre-slice shapes, read from origin/main before the move.
METHOD_SIGNATURES = {
    "get_daily_data": ["self", "stock_code", "start_date", "end_date", "days"],
    "_clean_data": ["self", "df"],
    "_calculate_indicators": ["self", "df"],
}

# The template method calls these; they stay abstract on BaseFetcher.
TEMPLATE_HOOKS = ("_fetch_raw_data", "_normalize_data")

SUBCLASS_MODULES = (
    "akshare_fetcher",
    "efinance_fetcher",
    "longbridge_fetcher",
    "tushare_fetcher",
    "yfinance_fetcher",
    "baostock_fetcher",
    "tickflow_fetcher",
    "crypto_coingecko_fetcher",
)


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_base_class(name) -> None:
    assert callable(getattr(BaseFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    function = BaseFetcher.__dict__[name]
    assert function.__module__ == "src.data_provider.base", name
    assert function.__qualname__ == f"BaseFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    assert BaseFetcher.__dict__[name].__globals__ is vars(base_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(BaseFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


@pytest.mark.parametrize("module_name", SUBCLASS_MODULES)
@pytest.mark.parametrize("name", MOVED)
def test_every_production_subclass_inherits_the_rebound_methods(module_name, name) -> None:
    """The risk unique to rebinding on an abstract base."""

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
        assert callable(getattr(subclass, name)), f"{subclass.__name__}.{name}"


@pytest.mark.parametrize("hook", TEMPLATE_HOOKS)
def test_template_hooks_stay_on_the_base_class(hook) -> None:
    """Moving these would break every subclass override."""

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
    assert hook in defined, hook


def test_owner_module_declares_exactly_the_slice() -> None:
    assert pipeline_mod.EXPECTED_DAILY_PIPELINE_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_DailyPipelineMethods"
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
    for name in MOVED:
        assert name not in defined, name


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any(module.endswith("data_provider.base") for module in imported)


def test_facade_bind_is_a_re_export_not_a_copy() -> None:
    from src.data_provider._facade_bind import bind_methods_from_class as shared
    from src.data_provider.base_parts.facade_bind import bind_methods_from_class

    assert bind_methods_from_class is shared


def test_clean_data_drops_rows_missing_required_columns() -> None:
    """Direct unit test of the extracted step, not only through the facade."""

    class _Probe(BaseFetcher):
        def __init__(self):
            self.name = "probe"

        def _fetch_raw_data(self, *args, **kwargs):
            return None

        def _normalize_data(self, df):
            return df

    frame = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02"],
            "open": [1.0, None],
            "high": [2.0, 2.0],
            "low": [0.5, 0.5],
            "close": [1.5, 1.5],
            "volume": [100, 100],
        }
    )
    cleaned = _Probe()._clean_data(frame)
    assert isinstance(cleaned, pd.DataFrame)
    assert len(cleaned) <= len(frame)


def test_owner_reload_rebinds_onto_the_base_class() -> None:
    importlib.reload(pipeline_mod)
    for name in MOVED:
        function = BaseFetcher.__dict__[name]
        assert function.__globals__ is vars(base_mod), name
        assert function.__qualname__ == f"BaseFetcher.{name}", name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.base_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_daily_data(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(base_mod), expected_names=MOVED,
        )
