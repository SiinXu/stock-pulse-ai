# -*- coding: utf-8 -*-
"""Facade identity, clone, patch, reload, and characterization tests for Longbridge symbols.

Issue #1068: the module-level ``_is_us_code``, ``_is_hk_code``, and
``_to_longbridge_symbol`` helpers moved into
``src/data_provider/longbridge_parts/symbols.py`` and are cloned onto the
public ``longbridge_fetcher`` module.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

import src.data_provider.longbridge_fetcher as longbridge_mod
import src.data_provider.longbridge_parts.symbols as symbols_mod
from src.data_provider.longbridge_fetcher import LongbridgeFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "longbridge_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "longbridge_parts" / "symbols.py"

MOVED = ("_is_us_code", "_is_hk_code", "_to_longbridge_symbol")

CONNECTION_STAYS = (
    "_get_ctx",
    "_is_available",
    "is_available_for_request",
    "_is_connection_error",
    "_mark_connection_cooldown",
    "_invalidate_ctx",
)

REALTIME_BOUND = (
    "_ts_sort_key",
    "_compute_volume_ratio",
    "_get_static_info",
    "get_stock_name",
    "get_realtime_quote",
)

HISTORY_BOUND = (
    "_fetch_raw_data",
    "_normalize_data",
)


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "LongbridgeFetcher"
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _facade_module_functions() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _facade_body(name: str):
    method = LongbridgeFetcher.__dict__[name]
    return getattr(method, "__wrapped__", method)


@pytest.mark.parametrize("name", MOVED)
def test_classifier_remains_callable_on_the_facade_module(name: str) -> None:
    assert callable(getattr(longbridge_mod, name))


@pytest.mark.parametrize("name", MOVED)
def test_classifier_is_not_a_class_method(name: str) -> None:
    assert name not in _facade_class_methods()
    assert name not in LongbridgeFetcher.__dict__


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name: str) -> None:
    helper = getattr(longbridge_mod, name)
    assert helper.__module__ == "src.data_provider.longbridge_fetcher"
    assert helper.__qualname__ == name
    assert helper.__name__ == name


def test_signatures_are_unchanged() -> None:
    us = inspect.signature(longbridge_mod._is_us_code)
    assert list(us.parameters) == ["stock_code"]
    assert "str" in str(us.parameters["stock_code"].annotation)
    assert "bool" in str(us.return_annotation)

    hk = inspect.signature(longbridge_mod._is_hk_code)
    assert list(hk.parameters) == ["stock_code"]
    assert "str" in str(hk.parameters["stock_code"].annotation)
    assert "bool" in str(hk.return_annotation)

    converter = inspect.signature(longbridge_mod._to_longbridge_symbol)
    assert list(converter.parameters) == ["stock_code"]
    assert "str" in str(converter.parameters["stock_code"].annotation)
    assert "str" in str(converter.return_annotation) or "Optional" in str(
        converter.return_annotation
    )


def test_free_names_resolve_through_the_facade_globals() -> None:
    for name in MOVED:
        helper = getattr(longbridge_mod, name)
        assert helper.__globals__ is vars(longbridge_mod)
    assert "is_us_stock_code" in longbridge_mod._is_us_code.__globals__
    assert "is_us_index_code" in longbridge_mod._is_us_code.__globals__
    assert "_is_us_code" in longbridge_mod._to_longbridge_symbol.__globals__
    assert "_is_hk_code" in longbridge_mod._to_longbridge_symbol.__globals__


def test_cloned_helpers_are_not_the_owner_objects() -> None:
    for name in MOVED:
        cloned = getattr(longbridge_mod, name)
        owner = getattr(symbols_mod, name)
        assert cloned is not owner
        assert cloned.__code__ is owner.__code__


def test_owner_module_declares_exactly_the_slice() -> None:
    assert symbols_mod.EXPECTED_SYMBOL_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    extra = defined - set(MOVED) - {
        "_install_facade_reload_hook",
        "_rebind_loaded_facade",
    }
    assert extra == set()
    for name in MOVED:
        assert name in defined


def test_body_no_longer_lives_as_facade_module_function() -> None:
    defined = _facade_module_functions()
    for name in MOVED:
        assert name not in defined


@pytest.mark.parametrize("name", CONNECTION_STAYS)
def test_connection_methods_stay_on_the_facade(name: str) -> None:
    assert name in _facade_class_methods(), name


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("longbridge_fetcher" in module for module in imported)


def test_owner_module_introduces_no_bare_get_config_call() -> None:
    source = OWNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "from src.config import get_config" not in source
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "get_config"
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module != "src.config"
            assert not (node.module or "").startswith("src.config.")


def test_facade_bind_is_a_re_export_not_a_copy() -> None:
    """#1612 consolidated these helpers; this package must not add a copy."""

    from src.data_provider._facade_bind import (
        _clone_facade_function as shared_clone,
        bind_methods_from_class as shared_bind,
    )
    from src.data_provider.longbridge_parts.facade_bind import (
        _clone_facade_function,
        bind_methods_from_class,
    )

    assert bind_methods_from_class is shared_bind
    assert _clone_facade_function is shared_clone


def test_production_imports_stay_on_the_facade() -> None:
    src_root = REPO_ROOT / "src"
    offenders = []
    for path in src_root.rglob("*.py"):
        if "longbridge_parts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "longbridge_parts.symbols" in text and path.name != "longbridge_fetcher.py":
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_owner_module_does_not_trip_sibling_realtime_import_grep() -> None:
    """Sibling production-import guards substring-match this token."""

    text = OWNER_PATH.read_text(encoding="utf-8")
    assert "longbridge_parts.realtime" not in text
    assert "longbridge_parts.history" not in text


def test_owner_reload_re_clones_onto_the_facade() -> None:
    importlib.reload(symbols_mod)
    for name in MOVED:
        helper = getattr(longbridge_mod, name)
        owner = getattr(symbols_mod, name)
        assert callable(helper)
        assert helper.__globals__ is vars(longbridge_mod)
        assert helper.__module__ == "src.data_provider.longbridge_fetcher"
        assert helper.__qualname__ == name
        assert helper is not owner
        assert helper.__code__ is owner.__code__
    for name in REALTIME_BOUND + HISTORY_BOUND:
        assert callable(getattr(LongbridgeFetcher, name)), name
        function = LongbridgeFetcher.__dict__[name]
        body = getattr(function, "__wrapped__", function)
        assert body.__globals__ is vars(longbridge_mod), name
    assert (
        _facade_body("_fetch_raw_data").__globals__["_to_longbridge_symbol"]
        is longbridge_mod._to_longbridge_symbol
    )


def test_cloned_us_classifier_follows_patched_index_helpers() -> None:
    original_stock = longbridge_mod.is_us_stock_code
    original_index = longbridge_mod.is_us_index_code
    try:
        longbridge_mod.is_us_stock_code = lambda code: code == "STOCK"
        longbridge_mod.is_us_index_code = lambda code: False
        assert longbridge_mod._is_us_code("stock") is True
        assert longbridge_mod._is_us_code("INDEX") is False
        longbridge_mod.is_us_stock_code = lambda code: False
        longbridge_mod.is_us_index_code = lambda code: code == "INDEX"
        assert longbridge_mod._is_us_code("index") is True
        assert longbridge_mod._is_us_code("STOCK") is False
    finally:
        longbridge_mod.is_us_stock_code = original_stock
        longbridge_mod.is_us_index_code = original_index


def test_cloned_converter_follows_patched_classifiers() -> None:
    original_us = longbridge_mod._is_us_code
    original_hk = longbridge_mod._is_hk_code
    try:
        longbridge_mod._is_us_code = lambda code: True
        longbridge_mod._is_hk_code = lambda code: False
        assert longbridge_mod._to_longbridge_symbol("ZZZZ") == "ZZZZ.US"
        longbridge_mod._is_us_code = lambda code: False
        longbridge_mod._is_hk_code = lambda code: True
        assert longbridge_mod._to_longbridge_symbol("HK1") == "0001.HK"
        longbridge_mod._is_us_code = lambda code: False
        longbridge_mod._is_hk_code = lambda code: False
        assert longbridge_mod._to_longbridge_symbol("ZZZZ") is None
        assert longbridge_mod._to_longbridge_symbol("AAPL.US") == "AAPL.US"
        assert longbridge_mod._to_longbridge_symbol("0700.HK") == "0700.HK"
    finally:
        longbridge_mod._is_us_code = original_us
        longbridge_mod._is_hk_code = original_hk


def test_fetch_raw_data_sees_patched_facade_symbol_converter() -> None:
    original = longbridge_mod._to_longbridge_symbol
    try:
        longbridge_mod._to_longbridge_symbol = lambda *a, **k: None
        assert (
            _facade_body("_fetch_raw_data").__globals__["_to_longbridge_symbol"]
            is longbridge_mod._to_longbridge_symbol
        )
    finally:
        longbridge_mod._to_longbridge_symbol = original


def test_realtime_quote_sees_patched_facade_symbol_converter() -> None:
    sentinel = object()
    original = longbridge_mod._to_longbridge_symbol
    try:
        longbridge_mod._to_longbridge_symbol = lambda *a, **k: sentinel
        function = LongbridgeFetcher.__dict__["get_realtime_quote"]
        assert function.__globals__["_to_longbridge_symbol"]("700.HK") is sentinel
    finally:
        longbridge_mod._to_longbridge_symbol = original


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("AAPL", "AAPL.US"),
        ("TSLA", "TSLA.US"),
        ("NVDA", "NVDA.US"),
        ("GLD", "GLD.US"),
        ("aapl", "AAPL.US"),
        ("SPX", "SPX.US"),
        ("AAPL.US", "AAPL.US"),
        ("HK00700", "0700.HK"),
        ("HK09988", "9988.HK"),
        ("HK01810", "1810.HK"),
        ("hk00700", "0700.HK"),
        ("00700", "0700.HK"),
        ("09988", "9988.HK"),
        ("0700.HK", "0700.HK"),
        ("600519", None),
        ("000001", None),
    ],
)
def test_symbol_conversion_characterization(code: str, expected) -> None:
    assert longbridge_mod._to_longbridge_symbol(code) == expected


@pytest.mark.parametrize(
    ("code", "is_us", "is_hk"),
    [
        ("AAPL", True, False),
        ("TSLA", True, False),
        ("SPX", True, False),
        ("600519", False, False),
        ("HK00700", False, True),
        ("00700", False, True),
        ("0700.HK", False, True),
        ("HK7", False, True),
        ("HK12345", False, True),
        ("HK123456", False, False),
        ("7.HK", False, True),
        ("12345.HK", False, True),
        ("123456.HK", False, False),
        ("123", False, False),
        ("123456", False, False),
    ],
)
def test_code_detection_characterization(code: str, is_us: bool, is_hk: bool) -> None:
    assert longbridge_mod._is_us_code(code) is is_us
    assert longbridge_mod._is_hk_code(code) is is_hk


def test_fetcher_instantiates_after_symbols_bind() -> None:
    assert not LongbridgeFetcher.__abstractmethods__
    fetcher = LongbridgeFetcher()
    assert isinstance(fetcher, LongbridgeFetcher)
