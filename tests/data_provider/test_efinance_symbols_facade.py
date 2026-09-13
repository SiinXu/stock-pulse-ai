# -*- coding: utf-8 -*-
"""Facade identity, clone, patch, reload, and characterization tests for efinance symbols.

Issue #1068: the module-level ``_is_etf_code``, ``_build_eastmoney_etf_secid``,
and ``_is_us_code`` helpers moved into ``src/data_provider/efinance_parts/symbols.py``
and are cloned onto the public ``efinance_fetcher`` module.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.data_provider.efinance_fetcher as efinance_mod
import src.data_provider.efinance_parts.symbols as symbols_mod
from src.data_provider.base import DataFetchError
from src.data_provider.efinance_fetcher import EfinanceFetcher
from src.data_provider.symbol_normalization import _is_etf_code as base_is_etf_code

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_parts" / "symbols.py"

MOVED = ("_is_etf_code", "_build_eastmoney_etf_secid", "_is_us_code")


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EfinanceFetcher"
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


def _make_fetcher() -> EfinanceFetcher:
    with patch(
        "src.data_provider.efinance_fetcher.get_config",
        return_value=SimpleNamespace(enable_eastmoney_patch=False),
    ):
        return EfinanceFetcher(sleep_min=0, sleep_max=0)


@pytest.mark.parametrize("name", MOVED)
def test_classifier_remains_callable_on_the_facade_module(name: str) -> None:
    assert callable(getattr(efinance_mod, name))


@pytest.mark.parametrize("name", MOVED)
def test_classifier_is_not_a_class_method(name: str) -> None:
    assert name not in _facade_class_methods()
    assert name not in EfinanceFetcher.__dict__


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name: str) -> None:
    helper = getattr(efinance_mod, name)
    assert helper.__module__ == "src.data_provider.efinance_fetcher"
    assert helper.__qualname__ == name
    assert helper.__name__ == name


def test_signatures_are_unchanged() -> None:
    etf = inspect.signature(efinance_mod._is_etf_code)
    assert list(etf.parameters) == ["stock_code"]
    assert "str" in str(etf.parameters["stock_code"].annotation)
    assert "bool" in str(etf.return_annotation)

    secid = inspect.signature(efinance_mod._build_eastmoney_etf_secid)
    assert list(secid.parameters) == ["stock_code"]
    assert "str" in str(secid.parameters["stock_code"].annotation)
    assert "str" in str(secid.return_annotation)

    us = inspect.signature(efinance_mod._is_us_code)
    assert list(us.parameters) == ["stock_code"]
    assert "str" in str(us.parameters["stock_code"].annotation)
    assert "bool" in str(us.return_annotation)


def test_free_names_resolve_through_the_facade_globals() -> None:
    for name in MOVED:
        helper = getattr(efinance_mod, name)
        assert helper.__globals__ is vars(efinance_mod)
    assert "_is_a_share_etf_code" in efinance_mod._is_etf_code.__globals__
    assert "normalize_stock_code" in efinance_mod._build_eastmoney_etf_secid.__globals__
    assert "DataFetchError" in efinance_mod._build_eastmoney_etf_secid.__globals__
    assert "_ETF_SH_PREFIXES" in efinance_mod._build_eastmoney_etf_secid.__globals__
    assert "_ETF_SZ_PREFIXES" in efinance_mod._build_eastmoney_etf_secid.__globals__
    assert "re" in efinance_mod._is_us_code.__globals__


def test_cloned_helpers_are_not_the_owner_objects() -> None:
    for name in MOVED:
        cloned = getattr(efinance_mod, name)
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
    for name in MOVED:
        assert name in defined


def test_body_no_longer_lives_as_facade_module_function() -> None:
    defined = _facade_module_functions()
    for name in MOVED:
        assert name not in defined


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("efinance_fetcher" in module for module in imported)


def test_facade_bind_is_a_re_export_not_a_copy() -> None:
    """#1612 consolidated these helpers; this package must not add a copy."""

    from src.data_provider._facade_bind import (
        _clone_facade_function as shared_clone,
        bind_methods_from_class as shared_bind,
    )
    from src.data_provider.efinance_parts.facade_bind import (
        _clone_facade_function,
        bind_methods_from_class,
    )

    assert bind_methods_from_class is shared_bind
    assert _clone_facade_function is shared_clone


def test_production_imports_stay_on_the_facade() -> None:
    src_root = REPO_ROOT / "src"
    offenders = []
    for path in src_root.rglob("*.py"):
        if "efinance_parts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "efinance_parts.symbols" in text and path.name != "efinance_fetcher.py":
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_owner_module_does_not_trip_efinance_realtime_import_grep() -> None:
    """Sibling efinance production-import guards substring-match this token."""

    text = OWNER_PATH.read_text(encoding="utf-8")
    assert "efinance_parts.realtime" not in text


def test_owner_reload_re_clones_onto_the_facade() -> None:
    importlib.reload(symbols_mod)
    for name in MOVED:
        helper = getattr(efinance_mod, name)
        owner = getattr(symbols_mod, name)
        assert callable(helper)
        assert helper.__globals__ is vars(efinance_mod)
        assert helper.__module__ == "src.data_provider.efinance_fetcher"
        assert helper.__qualname__ == name
        assert helper is not owner
        assert helper.__code__ is owner.__code__


def test_cloned_etf_classifier_follows_patched_base_wrap() -> None:
    original = efinance_mod._is_a_share_etf_code
    try:
        efinance_mod._is_a_share_etf_code = lambda code: code == "sentinel"
        assert efinance_mod._is_etf_code("sentinel") is True
        assert efinance_mod._is_etf_code("510300") is False
    finally:
        efinance_mod._is_a_share_etf_code = original


def test_cloned_secid_builder_follows_patched_etf_classifier() -> None:
    original = efinance_mod._is_etf_code
    try:
        efinance_mod._is_etf_code = lambda code: False
        with pytest.raises(DataFetchError, match=r"无法识别 ETF 代码 510300"):
            efinance_mod._build_eastmoney_etf_secid("510300")
        efinance_mod._is_etf_code = lambda code: True
        with pytest.raises(DataFetchError, match=r"无法确定 ETF 600519 的 Eastmoney 市场前缀"):
            efinance_mod._build_eastmoney_etf_secid("600519")
    finally:
        efinance_mod._is_etf_code = original


def test_cloned_us_classifier_follows_patched_re() -> None:
    original = efinance_mod.re
    seen = {}

    class FakeRe:
        @staticmethod
        def match(pattern, code):
            seen["pattern"] = pattern
            seen["code"] = code
            return object() if code == "SENTINEL" else None

    try:
        efinance_mod.re = FakeRe
        assert efinance_mod._is_us_code("sentinel") is True
        assert seen["pattern"] == r"^[A-Z]{1,5}(\.[A-Z])?$"
        assert seen["code"] == "SENTINEL"
        assert efinance_mod._is_us_code("nope") is False
    finally:
        efinance_mod.re = original


def test_cloned_secid_builder_looks_up_facade_prefix_tuples() -> None:
    original_etf = efinance_mod._is_etf_code
    original_sh = efinance_mod._ETF_SH_PREFIXES
    original_sz = efinance_mod._ETF_SZ_PREFIXES
    try:
        efinance_mod._is_etf_code = lambda code: True
        efinance_mod._ETF_SH_PREFIXES = ("60",)
        efinance_mod._ETF_SZ_PREFIXES = ()
        assert efinance_mod._build_eastmoney_etf_secid("600519") == "1.600519"
        efinance_mod._ETF_SH_PREFIXES = ()
        efinance_mod._ETF_SZ_PREFIXES = ("60",)
        assert efinance_mod._build_eastmoney_etf_secid("600519") == "0.600519"
    finally:
        efinance_mod._is_etf_code = original_etf
        efinance_mod._ETF_SH_PREFIXES = original_sh
        efinance_mod._ETF_SZ_PREFIXES = original_sz


@pytest.mark.parametrize(
    ("code", "is_etf", "is_us", "secid"),
    [
        ("510300", True, False, "1.510300"),
        ("159919", True, False, "0.159919"),
        ("512400", True, False, "1.512400"),
        ("588000", True, False, "1.588000"),
        ("159915", True, False, "0.159915"),
        ("563230", True, False, "1.563230"),
        ("518800", True, False, "1.518800"),
        ("160000", True, False, "0.160000"),
        ("sh510300", True, False, "1.510300"),
        ("510300.SH", True, False, "1.510300"),
    ],
)
def test_etf_and_secid_characterization(
    code: str,
    is_etf: bool,
    is_us: bool,
    secid: str,
) -> None:
    assert efinance_mod._is_etf_code(code) is is_etf
    assert base_is_etf_code(code) is is_etf
    assert efinance_mod._is_us_code(code) is is_us
    assert efinance_mod._build_eastmoney_etf_secid(code) == secid


@pytest.mark.parametrize(
    "code",
    ["AAPL", "SPX", "QQQ", "BRK.B", "BRK.A", "brk.b", "GOOGL", "A"],
)
def test_us_regex_characterization_including_index_like_tickers(code: str) -> None:
    assert efinance_mod._is_us_code(code) is True
    assert efinance_mod._is_etf_code(code) is False


@pytest.mark.parametrize(
    "code",
    ["XXXXXX", "12345", "hk00700", "00700", "15", "501001", "600519"],
)
def test_non_us_non_etf_or_plain_stock_characterization(code: str) -> None:
    assert efinance_mod._is_us_code(code) is False


def test_unrecognized_etf_uses_original_stock_code_in_error() -> None:
    with pytest.raises(DataFetchError, match=r"无法识别 ETF 代码 600519$"):
        efinance_mod._build_eastmoney_etf_secid("600519")
    with pytest.raises(DataFetchError, match=r"无法识别 ETF 代码 AAPL$"):
        efinance_mod._build_eastmoney_etf_secid("AAPL")
    with pytest.raises(DataFetchError, match=r"无法识别 ETF 代码 15$"):
        efinance_mod._build_eastmoney_etf_secid("15")
    with pytest.raises(DataFetchError, match=r"无法识别 ETF 代码 501001$"):
        efinance_mod._build_eastmoney_etf_secid("501001")


def test_patched_prefix_miss_uses_original_stock_code_in_error() -> None:
    original = efinance_mod._is_etf_code
    try:
        efinance_mod._is_etf_code = lambda code: True
        with pytest.raises(DataFetchError, match=r"无法确定 ETF 600519 的 Eastmoney 市场前缀$"):
            efinance_mod._build_eastmoney_etf_secid("600519")
    finally:
        efinance_mod._is_etf_code = original


def test_fetch_etf_data_sees_patched_facade_secid_builder() -> None:
    sentinel = object()
    original = efinance_mod._build_eastmoney_etf_secid
    try:
        efinance_mod._build_eastmoney_etf_secid = lambda code: sentinel
        method = EfinanceFetcher.__dict__["_fetch_etf_data"]
        assert method.__globals__["_build_eastmoney_etf_secid"]("510300") is sentinel
    finally:
        efinance_mod._build_eastmoney_etf_secid = original


def test_realtime_quote_sees_patched_facade_etf_classifier() -> None:
    original = efinance_mod._is_etf_code
    try:
        efinance_mod._is_etf_code = lambda code: True
        method = EfinanceFetcher.__dict__["get_realtime_quote"]
        assert method.__globals__["_is_etf_code"]("600519") is True
    finally:
        efinance_mod._is_etf_code = original


def test_fetcher_instantiates_after_symbols_bind() -> None:
    assert not EfinanceFetcher.__abstractmethods__
    fetcher = _make_fetcher()
    assert isinstance(fetcher, EfinanceFetcher)
    assert fetcher.sleep_min == 0
    assert fetcher.sleep_max == 0
