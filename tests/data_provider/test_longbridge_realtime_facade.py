# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and reload characterization for the Longbridge realtime slice.

Issue #1068: the realtime methods moved into
``src/data_provider/longbridge_parts/realtime.py`` and are rebound onto the
public ``LongbridgeFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

import src.data_provider.longbridge_fetcher as longbridge_mod
import src.data_provider.longbridge_parts.realtime as realtime_mod
from src.data_provider.longbridge_fetcher import LongbridgeFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "longbridge_fetcher.py"
OWNER_PATH = (
    REPO_ROOT / "src" / "data_provider" / "longbridge_parts" / "realtime.py"
)

MOVED = (
    "_ts_sort_key",
    "_compute_volume_ratio",
    "_get_static_info",
    "get_stock_name",
    "get_realtime_quote",
)

# Pre-slice shapes, read from origin/main before the move.
METHOD_SIGNATURES = {
    "_ts_sort_key": ["self", "candle"],
    "_compute_volume_ratio": ["self", "symbol", "today_volume"],
    "_get_static_info": ["self", "symbol"],
    "get_stock_name": ["self", "stock_code"],
    "get_realtime_quote": ["self", "stock_code"],
}

# Connection ownership stays on the facade — see the config-access note below.
CONNECTION_STAYS = (
    "_get_ctx",
    "_is_available",
    "is_available_for_request",
    "_is_connection_error",
    "_mark_connection_cooldown",
    "_invalidate_ctx",
)


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(LongbridgeFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    function = LongbridgeFetcher.__dict__[name]
    assert function.__module__ == "src.data_provider.longbridge_fetcher", name
    assert function.__qualname__ == f"LongbridgeFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    function = LongbridgeFetcher.__dict__[name]
    assert function.__globals__ is vars(longbridge_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(LongbridgeFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


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


@pytest.mark.parametrize("name", CONNECTION_STAYS)
def test_connection_methods_stay_on_the_facade(name) -> None:
    """Reached through `self`; moving them would widen the slice."""

    assert name in _facade_class_methods(), name


def test_owner_module_introduces_no_bare_get_config_call() -> None:
    """The reason connection ownership stayed behind.

    ``_get_ctx`` and ``_is_available`` read application config directly. Moving
    them would add bare ``get_config()`` sites to a new module, which
    ``scripts/check_config_access.py`` bans. This test records that boundary so
    a later slice does not reintroduce the violation by accident.
    """

    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_config"
    ]
    assert calls == [], "owner module must not call get_config() directly"


def test_static_cache_state_stays_on_the_facade() -> None:
    source = FACADE_PATH.read_text(encoding="utf-8")
    assert "_static_cache" in source
    assert "_static_cache_lock" in source


def test_moved_bodies_still_reach_a_patched_facade_global() -> None:
    sentinel = object()
    original = longbridge_mod._to_longbridge_symbol
    try:
        longbridge_mod._to_longbridge_symbol = lambda *a, **k: sentinel
        function = LongbridgeFetcher.__dict__["get_realtime_quote"]
        assert function.__globals__["_to_longbridge_symbol"]("700.HK") is sentinel
    finally:
        longbridge_mod._to_longbridge_symbol = original


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("longbridge_fetcher" in module for module in imported)


def test_facade_bind_is_a_re_export_not_a_copy() -> None:
    from src.data_provider._facade_bind import bind_methods_from_class as shared
    from src.data_provider.longbridge_parts.facade_bind import bind_methods_from_class

    assert bind_methods_from_class is shared


def test_owner_reload_rebinds_onto_the_facade() -> None:
    importlib.reload(realtime_mod)
    for name in MOVED:
        function = LongbridgeFetcher.__dict__[name]
        assert function.__globals__ is vars(longbridge_mod), name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.longbridge_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_realtime_quote(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(longbridge_mod), expected_names=MOVED,
        )
