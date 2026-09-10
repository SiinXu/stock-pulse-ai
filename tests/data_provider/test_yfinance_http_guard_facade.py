# -*- coding: utf-8 -*-
"""Facade identity, clone, patch, reload, and Local Only tests for the yfinance HTTP guard.

Issue #1068: the Yahoo/Stooq outbound URL tuple and module-level
``_yfinance_http_guard`` factory moved into
``src/data_provider/yfinance_parts/http_guard.py`` and are cloned onto the
public ``yfinance_fetcher`` module.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import src.data_provider.yfinance_fetcher as yfinance_mod
import src.data_provider.yfinance_parts.http_guard as http_guard_mod
from src.data_provider.yfinance_fetcher import YfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "yfinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "yfinance_parts" / "http_guard.py"

EXPECTED_URLS = (
    "https://query1.finance.yahoo.com/",
    "https://query2.finance.yahoo.com/",
    "https://stooq.com/",
)


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


def _facade_module_functions() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_http_guard_remains_callable_on_the_facade_module() -> None:
    assert callable(yfinance_mod._yfinance_http_guard)


def test_http_guard_is_not_a_class_method() -> None:
    assert "_yfinance_http_guard" not in _facade_class_methods()
    assert "_yfinance_http_guard" not in YfinanceFetcher.__dict__


def test_module_and_qualname_still_point_at_the_facade() -> None:
    guard = yfinance_mod._yfinance_http_guard
    assert guard.__module__ == "src.data_provider.yfinance_fetcher"
    assert guard.__qualname__ == "_yfinance_http_guard"
    assert guard.__name__ == "_yfinance_http_guard"


def test_free_names_resolve_through_the_facade_globals() -> None:
    assert yfinance_mod._yfinance_http_guard.__globals__ is vars(yfinance_mod)


def test_cloned_guard_is_not_the_owner_object() -> None:
    cloned = yfinance_mod._yfinance_http_guard
    owner = http_guard_mod._yfinance_http_guard
    assert cloned is not owner
    assert cloned.__code__ is owner.__code__


def test_owner_module_declares_exactly_the_slice() -> None:
    assert http_guard_mod.EXPECTED_HTTP_GUARD_NAMES == (
        "_YFINANCE_OUTBOUND_URLS",
        "_yfinance_http_guard",
    )
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    assigned = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "_YFINANCE_OUTBOUND_URLS" in assigned
    assert "_yfinance_http_guard" in defined


def test_bodies_no_longer_live_as_facade_module_functions() -> None:
    assert "_yfinance_http_guard" not in _facade_module_functions()


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

    from src.data_provider._facade_bind import (
        _clone_facade_function as shared_clone,
        bind_methods_from_class as shared_bind,
    )
    from src.data_provider.yfinance_parts.facade_bind import (
        _clone_facade_function,
        bind_methods_from_class,
    )

    assert bind_methods_from_class is shared_bind
    assert _clone_facade_function is shared_clone


def test_owner_reload_re_clones_onto_the_facade() -> None:
    importlib.reload(http_guard_mod)
    guard = yfinance_mod._yfinance_http_guard
    assert callable(guard)
    assert guard.__globals__ is vars(yfinance_mod)
    assert guard.__module__ == "src.data_provider.yfinance_fetcher"
    assert guard.__qualname__ == "_yfinance_http_guard"
    assert guard is not http_guard_mod._yfinance_http_guard
    assert guard.__code__ is http_guard_mod._yfinance_http_guard.__code__


def test_cloned_guard_sees_patched_facade_guard_outbound_urls() -> None:
    seen = {"called": False}
    sentinel = object()

    def fake_guard(urls, strict_dns=True):
        seen["called"] = True
        seen["urls"] = urls
        seen["strict_dns"] = strict_dns
        return sentinel

    original = yfinance_mod.guard_outbound_urls
    try:
        yfinance_mod.guard_outbound_urls = fake_guard
        result = yfinance_mod._yfinance_http_guard()
        assert result is sentinel
        assert seen["called"] is True
        assert seen["strict_dns"] is False
        assert seen["urls"] is yfinance_mod._YFINANCE_OUTBOUND_URLS
    finally:
        yfinance_mod.guard_outbound_urls = original


def test_outbound_url_tuple_matches_the_three_hosts() -> None:
    assert yfinance_mod._YFINANCE_OUTBOUND_URLS == EXPECTED_URLS
    assert http_guard_mod._YFINANCE_OUTBOUND_URLS == EXPECTED_URLS
    assert yfinance_mod._YFINANCE_OUTBOUND_URLS is http_guard_mod._YFINANCE_OUTBOUND_URLS


def test_fetcher_instantiates_after_http_guard_bind() -> None:
    assert not YfinanceFetcher.__abstractmethods__
    fetcher = YfinanceFetcher()
    assert isinstance(fetcher, YfinanceFetcher)
