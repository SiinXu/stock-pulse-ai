# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and reload characterization for the efinance boards slice.

Issue #1068: the market-wide board methods moved into
``src/data_provider/efinance_parts/market_boards.py`` and are rebound onto the
public ``EfinanceFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

import src.data_provider.efinance_fetcher as efinance_mod
import src.data_provider.efinance_parts.market_boards as boards_mod
from src.data_provider.efinance_fetcher import EfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_fetcher.py"
OWNER_PATH = (
    REPO_ROOT / "src" / "data_provider" / "efinance_parts" / "market_boards.py"
)

MOVED = (
    "get_main_indices",
    "get_market_stats",
    "_calc_market_stats",
    "get_sector_rankings",
)

METHOD_SIGNATURES = {
    "get_main_indices": ["self", "region"],
    "get_market_stats": ["self"],
    "_calc_market_stats": ["self", "df"],
    "get_sector_rankings": ["self", "n"],
}


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(EfinanceFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = EfinanceFetcher.__dict__[name]
    assert method.__module__ == "src.data_provider.efinance_fetcher", name
    assert method.__qualname__ == f"EfinanceFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    method = EfinanceFetcher.__dict__[name]
    assert method.__globals__ is vars(efinance_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(EfinanceFetcher, name))
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


def test_bodies_no_longer_live_in_the_facade_class() -> None:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EfinanceFetcher"
    )
    defined = {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in MOVED:
        assert name not in defined, name


def test_per_symbol_lookup_stays_on_the_facade() -> None:
    """``get_belong_board`` is a per-symbol lookup, not a market-wide aggregate."""

    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EfinanceFetcher"
    )
    defined = {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "get_belong_board" in defined


def test_rate_limit_helpers_stay_on_the_facade() -> None:
    for helper in ("_enforce_rate_limit", "_set_random_user_agent"):
        assert helper in EfinanceFetcher.__dict__, helper


def test_moved_bodies_still_reach_a_patched_facade_helper() -> None:
    sentinel = object()
    original = efinance_mod._ef_call_with_timeout
    try:
        efinance_mod._ef_call_with_timeout = lambda *a, **k: sentinel
        method = EfinanceFetcher.__dict__["get_main_indices"]
        assert method.__globals__["_ef_call_with_timeout"]() is sentinel
    finally:
        efinance_mod._ef_call_with_timeout = original


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("efinance_fetcher" in module for module in imported)


def test_owner_reload_rebinds_onto_the_facade() -> None:
    importlib.reload(boards_mod)
    for name in MOVED:
        method = EfinanceFetcher.__dict__[name]
        assert method.__globals__ is vars(efinance_mod), name


def test_etf_slice_is_unaffected_by_this_reload() -> None:
    """Both owner modules share one assemble function; neither may clobber the other."""

    importlib.reload(boards_mod)
    for name in ("_fetch_etf_data", "_get_etf_realtime_quote"):
        method = EfinanceFetcher.__dict__[name]
        assert callable(method), name
        assert method.__globals__ is vars(efinance_mod), name
