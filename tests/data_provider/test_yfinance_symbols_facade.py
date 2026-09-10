# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, reload, and routing tests for the yfinance symbols slice.

Issue #1068: Yahoo symbol conversion and US/JP/KR/TW classifiers moved into
``src/data_provider/yfinance_parts/symbols.py`` and are rebound onto the
public ``YfinanceFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import logging
from pathlib import Path

import pytest

import src.data_provider.yfinance_fetcher as yfinance_mod
import src.data_provider.yfinance_parts.symbols as symbols_mod
from src.data_provider.yfinance_fetcher import YfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "yfinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "yfinance_parts" / "symbols.py"

MOVED = (
    "_is_jp_kr_suffix_stock",
    "_is_tw_suffix_stock",
    "_convert_stock_code",
    "_is_us_stock",
)

STATICMETHODS = (
    "_is_jp_kr_suffix_stock",
    "_is_tw_suffix_stock",
)

INSTANCE_METHODS = (
    "_convert_stock_code",
    "_is_us_stock",
)

METHOD_SIGNATURES = {
    "_is_jp_kr_suffix_stock": ["stock_code"],
    "_is_tw_suffix_stock": ["stock_code"],
    "_convert_stock_code": ["self", "stock_code"],
    "_is_us_stock": ["self", "stock_code"],
}

CONVERSION_CASES = (
    ("600519", "600519.SS"),
    ("000001", "000001.SZ"),
    ("hk00700", "0700.HK"),
    ("02513", "2513.HK"),
    ("00700", "0700.HK"),
    ("AAPL", "AAPL"),
    ("SPX", "^GSPC"),
    ("7203.T", "7203.T"),
    ("005930.KS", "005930.KS"),
    ("035720.KQ", "035720.KQ"),
    ("2330.TW", "2330.TW"),
    ("6505.TWO", "6505.TWO"),
    ("006208.TW", "006208.TW"),
    ("510300", "510300.SS"),
    ("159919", "159919.SZ"),
    ("920748", "920748.BJ"),
    ("600519.SH", "600519.SS"),
    ("999999", "999999.SZ"),
)


def _descriptor(name: str):
    return YfinanceFetcher.__dict__[name]


def _facade_body(name: str):
    method = _descriptor(name)
    if isinstance(method, staticmethod):
        return method.__func__
    return getattr(method, "__wrapped__", method)


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(YfinanceFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = _descriptor(name)
    assert method.__module__ == "src.data_provider.yfinance_fetcher", name
    assert method.__qualname__ == f"YfinanceFetcher.{name}", name


@pytest.mark.parametrize("name", INSTANCE_METHODS)
def test_instance_method_free_names_resolve_through_the_facade_globals(name) -> None:
    assert _descriptor(name).__globals__ is vars(yfinance_mod), name


@pytest.mark.parametrize("name", STATICMETHODS)
def test_staticmethod_free_names_resolve_through_the_facade_globals(name) -> None:
    method = _descriptor(name)
    assert isinstance(method, staticmethod), name
    assert method.__func__.__globals__ is vars(yfinance_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(YfinanceFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


@pytest.mark.parametrize("name", STATICMETHODS)
def test_suffix_helpers_remain_staticmethods(name) -> None:
    assert isinstance(_descriptor(name), staticmethod), name
    assert not isinstance(_descriptor("_convert_stock_code"), staticmethod)
    assert not isinstance(_descriptor("_is_us_stock"), staticmethod)


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
    assert symbols_mod.EXPECTED_SYMBOL_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_SymbolMethods"
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
    importlib.reload(symbols_mod)
    for name in MOVED:
        method = _descriptor(name)
        body = _facade_body(name)
        assert body.__globals__ is vars(yfinance_mod), name
        assert method.__qualname__ == f"YfinanceFetcher.{name}", name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.yfinance_parts.facade_bind import bind_methods_from_class

    class _Partial:
        @staticmethod
        def _is_jp_kr_suffix_stock(stock_code):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(yfinance_mod), expected_names=MOVED,
        )


def test_fetcher_instantiates_after_abstract_clearing() -> None:
    assert not YfinanceFetcher.__abstractmethods__
    fetcher = YfinanceFetcher()
    assert isinstance(fetcher, YfinanceFetcher)


@pytest.mark.parametrize("code, expected", CONVERSION_CASES)
def test_convert_stock_code_keeps_frozen_routing_table(code, expected) -> None:
    fetcher = YfinanceFetcher()
    assert fetcher._convert_stock_code(code) == expected


def test_unknown_six_digit_code_warns_and_defaults_to_shenzhen(caplog) -> None:
    fetcher = YfinanceFetcher()
    with caplog.at_level(logging.WARNING, logger="src.data_provider.yfinance_fetcher"):
        assert fetcher._convert_stock_code("999999") == "999999.SZ"
    assert any("999999" in record.getMessage() for record in caplog.records)


def test_suffix_and_us_classifiers_keep_call_styles() -> None:
    fetcher = YfinanceFetcher()
    assert YfinanceFetcher._is_jp_kr_suffix_stock("7203.T") is True
    assert fetcher._is_jp_kr_suffix_stock("7203.T") is True
    assert YfinanceFetcher._is_jp_kr_suffix_stock("AAPL") is False
    assert YfinanceFetcher._is_tw_suffix_stock("2330.TW") is True
    assert fetcher._is_tw_suffix_stock("6505.TWO") is True
    assert YfinanceFetcher._is_tw_suffix_stock("7203.T") is False
    assert fetcher._is_us_stock("AAPL") is True
    assert fetcher._is_us_stock("SPX") is False
    assert fetcher._is_us_stock("600519") is False


def test_convert_sees_patched_facade_get_us_index_yf_symbol() -> None:
    original = yfinance_mod.get_us_index_yf_symbol
    fetcher = YfinanceFetcher()
    try:
        yfinance_mod.get_us_index_yf_symbol = lambda *a, **k: ("^SENTINEL", "Sentinel")
        assert fetcher._convert_stock_code("SPX") == "^SENTINEL"
        assert _facade_body("_convert_stock_code").__globals__[
            "get_us_index_yf_symbol"
        ]("SPX") == ("^SENTINEL", "Sentinel")
    finally:
        yfinance_mod.get_us_index_yf_symbol = original


def test_is_us_stock_sees_patched_facade_is_us_stock_code() -> None:
    original = yfinance_mod.is_us_stock_code
    fetcher = YfinanceFetcher()
    try:
        yfinance_mod.is_us_stock_code = lambda *a, **k: True
        assert fetcher._is_us_stock("not-a-us-code") is True
    finally:
        yfinance_mod.is_us_stock_code = original


def test_suffix_staticmethods_see_patched_facade_is_suffix_market_symbol() -> None:
    original = yfinance_mod.is_suffix_market_symbol
    try:
        yfinance_mod.is_suffix_market_symbol = lambda *a, **k: True
        assert YfinanceFetcher._is_jp_kr_suffix_stock("anything") is True
        assert YfinanceFetcher._is_tw_suffix_stock("anything") is True
    finally:
        yfinance_mod.is_suffix_market_symbol = original
