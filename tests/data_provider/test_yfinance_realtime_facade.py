# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and reload characterization for the yfinance realtime slice.

Issue #1068: the realtime quote methods moved into
``src/data_provider/yfinance_parts/realtime.py`` and are rebound onto the
public ``YfinanceFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.data_provider.yfinance_fetcher as yfinance_mod
import src.data_provider.yfinance_parts.realtime as realtime_mod
from src.data_provider.yfinance_fetcher import YfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "yfinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "yfinance_parts" / "realtime.py"

MOVED = (
    "_get_us_stock_quote_from_stooq",
    "_get_us_index_realtime_quote",
    "get_realtime_quote",
)

METHOD_SIGNATURES = {
    "_get_us_stock_quote_from_stooq": ["self", "stock_code"],
    "_get_us_index_realtime_quote": ["self", "user_code", "yf_symbol", "index_name"],
    "get_realtime_quote": ["self", "stock_code"],
}

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
    assert realtime_mod.EXPECTED_REALTIME_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_RealtimeMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(MOVED)


def test_bodies_no_longer_live_in_the_facade_class() -> None:
    defined = _facade_class_methods()
    for name in MOVED:
        assert name not in defined, name


def test_remaining_facade_class_methods_are_only_init() -> None:
    assert _facade_class_methods() == {"__init__"}


def test_http_guard_remains_a_module_level_function() -> None:
    assert callable(yfinance_mod._yfinance_http_guard)
    assert "_yfinance_http_guard" not in _facade_class_methods()


def test_moved_bodies_still_reach_a_patched_facade_global() -> None:
    sentinel_symbol = "^SENTINEL"
    sentinel_name = "Sentinel Index"
    original = yfinance_mod.get_us_index_yf_symbol
    fetcher = YfinanceFetcher()
    quote = SimpleNamespace(source="not-fallback")
    try:
        yfinance_mod.get_us_index_yf_symbol = lambda *a, **k: (sentinel_symbol, sentinel_name)
        method = YfinanceFetcher.__dict__["get_realtime_quote"]
        assert method.__globals__["get_us_index_yf_symbol"]("SPX") == (
            sentinel_symbol,
            sentinel_name,
        )
        with patch.object(
            fetcher, "_get_us_index_realtime_quote", return_value=quote
        ) as mocked:
            result = fetcher.get_realtime_quote("SPX")
        mocked.assert_called_once_with(
            user_code="SPX",
            yf_symbol=sentinel_symbol,
            index_name=sentinel_name,
        )
        assert result is quote
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
    importlib.reload(realtime_mod)
    for name in MOVED:
        method = YfinanceFetcher.__dict__[name]
        assert method.__globals__ is vars(yfinance_mod), name
        assert method.__qualname__ == f"YfinanceFetcher.{name}", name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.yfinance_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_realtime_quote(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(yfinance_mod), expected_names=MOVED,
        )
