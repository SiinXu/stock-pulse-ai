# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and reload characterization for the TickFlow boards slice.

Issue #1068: the market-wide board methods moved into
``src/data_provider/tickflow_parts/market_boards.py`` and are rebound onto the
public ``TickFlowFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

import src.data_provider.tickflow_fetcher as tickflow_mod
import src.data_provider.tickflow_parts.market_boards as boards_mod
from src.data_provider.tickflow_fetcher import TickFlowFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "tickflow_fetcher.py"
OWNER_PATH = (
    REPO_ROOT / "src" / "data_provider" / "tickflow_parts" / "market_boards.py"
)

MOVED = ("get_main_indices", "get_market_stats", "get_sector_rankings")

# Pre-slice shapes, read from origin/main before the move.
METHOD_SIGNATURES = {
    "get_main_indices": ["self", "region"],
    "get_market_stats": ["self"],
    "get_sector_rankings": ["self", "n"],
}

# Sibling methods the moved bodies reach through ``self``; all stay on the facade.
FACADE_SIBLINGS = (
    "_capability_available",
    "_extract_name",
    "_extract_universe_symbols",
    "_get_client",
    "_get_limit_ratio",
    "_is_cn_equity_symbol",
    "_is_universe_permission_error",
    "_mark_capability",
    "_ratio_to_percent",
    "_round_limit_price",
    "_safe_float",
)


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(TickFlowFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = TickFlowFetcher.__dict__[name]
    assert method.__module__ == "src.data_provider.tickflow_fetcher", name
    assert method.__qualname__ == f"TickFlowFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    method = TickFlowFetcher.__dict__[name]
    assert method.__globals__ is vars(tickflow_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(TickFlowFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


def test_owner_module_declares_exactly_the_slice() -> None:
    assert boards_mod.EXPECTED_MARKET_BOARD_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_MarketBoardsMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(MOVED)


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TickFlowFetcher"
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_bodies_no_longer_live_in_the_facade_class() -> None:
    defined = _facade_class_methods()
    for name in MOVED:
        assert name not in defined, name


@pytest.mark.parametrize("sibling", FACADE_SIBLINGS)
def test_sibling_helpers_stay_on_the_facade(sibling) -> None:
    """The moved bodies reach these through ``self``; moving any would widen the slice."""

    assert sibling in _facade_class_methods(), sibling


def test_sector_rankings_cache_attributes_stay_on_the_facade() -> None:
    source = FACADE_PATH.read_text(encoding="utf-8")
    assert "_sector_rankings_cache" in source
    assert "_sector_rankings_cache_lock" in source


def test_moved_bodies_still_reach_a_patched_facade_global() -> None:
    sentinel = object()
    original = tickflow_mod.normalize_stock_code
    try:
        tickflow_mod.normalize_stock_code = lambda code: sentinel
        method = TickFlowFetcher.__dict__["get_sector_rankings"]
        assert method.__globals__["normalize_stock_code"]("600519") is sentinel
    finally:
        tickflow_mod.normalize_stock_code = original


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("tickflow_fetcher" in module for module in imported)


def test_owner_reload_rebinds_onto_the_facade() -> None:
    importlib.reload(boards_mod)
    for name in MOVED:
        method = TickFlowFetcher.__dict__[name]
        assert method.__globals__ is vars(tickflow_mod), name
        assert method.__qualname__ == f"TickFlowFetcher.{name}", name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.tickflow_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_main_indices(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial,
            _Target,
            vars(tickflow_mod),
            expected_names=MOVED,
        )
