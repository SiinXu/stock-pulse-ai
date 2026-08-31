# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and reload characterization for the yfinance indices slice.

Issue #1068: the main-index methods moved into
``src/data_provider/yfinance_parts/main_indices.py`` and are rebound onto the
public ``YfinanceFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

import src.data_provider.yfinance_fetcher as yfinance_mod
import src.data_provider.yfinance_parts.main_indices as indices_mod
from src.data_provider.yfinance_fetcher import YfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "yfinance_fetcher.py"
OWNER_PATH = (
    REPO_ROOT / "src" / "data_provider" / "yfinance_parts" / "main_indices.py"
)

MOVED = (
    "_fetch_yf_ticker_data",
    "get_main_indices",
    "_get_us_main_indices",
    "_get_hk_main_indices",
    "_get_jp_main_indices",
    "_get_kr_main_indices",
    "_get_tw_main_indices",
)

# Pre-slice shapes, read from origin/main before the move.
METHOD_SIGNATURES = {
    "_fetch_yf_ticker_data": ["self", "yf", "yf_code", "name", "return_code"],
    "get_main_indices": ["self", "region"],
    "_get_us_main_indices": ["self", "yf"],
    "_get_hk_main_indices": ["self", "yf"],
    "_get_jp_main_indices": ["self", "yf"],
    "_get_kr_main_indices": ["self", "yf"],
    "_get_tw_main_indices": ["self", "yf"],
}

# Methods the slice does NOT own; a later slice may move them, but not silently.
UNMOVED_FACADE_METHODS = (
    "get_realtime_quote",
    "_convert_stock_code",
    "_normalize_data",
    "_fetch_raw_data",
)


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(YfinanceFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = YfinanceFetcher.__dict__[name]
    assert method.__module__ == "src.data_provider.yfinance_fetcher", name
    assert method.__qualname__ == f"YfinanceFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    method = YfinanceFetcher.__dict__[name]
    assert method.__globals__ is vars(yfinance_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(YfinanceFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "YfinanceFetcher"
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_owner_module_declares_exactly_the_slice() -> None:
    assert set(indices_mod.EXPECTED_MAIN_INDEX_METHOD_NAMES) == set(MOVED)
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_MainIndicesMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(MOVED)


def test_bodies_no_longer_live_in_the_facade_class() -> None:
    defined = _facade_class_methods()
    for name in MOVED:
        assert name not in defined, name


@pytest.mark.parametrize("name", UNMOVED_FACADE_METHODS)
def test_unmoved_methods_stay_on_the_facade(name) -> None:
    assert name in _facade_class_methods(), name


def test_shared_ticker_fetch_travels_with_the_cluster() -> None:
    """All six regional methods call it; leaving it behind would add a cross-module hop."""

    assert "_fetch_yf_ticker_data" in indices_mod.EXPECTED_MAIN_INDEX_METHOD_NAMES
    source = OWNER_PATH.read_text(encoding="utf-8")
    assert "def _fetch_yf_ticker_data(" in source


def test_moved_bodies_still_reach_a_patched_facade_global() -> None:
    sentinel = object()
    original = yfinance_mod.get_us_index_yf_symbol
    try:
        yfinance_mod.get_us_index_yf_symbol = lambda *a, **k: sentinel
        method = YfinanceFetcher.__dict__["_get_us_main_indices"]
        assert method.__globals__["get_us_index_yf_symbol"]("^GSPC") is sentinel
    finally:
        yfinance_mod.get_us_index_yf_symbol = original


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("yfinance_fetcher" in module for module in imported)


def test_facade_bind_is_a_re_export_not_a_copy() -> None:
    """#1612 consolidated these helpers; this package must not add a copy."""

    from src.data_provider._facade_bind import bind_methods_from_class as shared
    from src.data_provider.yfinance_parts.facade_bind import bind_methods_from_class

    assert bind_methods_from_class is shared


def test_owner_reload_rebinds_onto_the_facade() -> None:
    importlib.reload(indices_mod)
    for name in MOVED:
        method = YfinanceFetcher.__dict__[name]
        assert method.__globals__ is vars(yfinance_mod), name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.yfinance_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_main_indices(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(yfinance_mod), expected_names=MOVED,
        )
