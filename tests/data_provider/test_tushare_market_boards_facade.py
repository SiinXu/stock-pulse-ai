# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and reload characterization for the Tushare boards slice.

Issue #1068: the market-wide board methods moved into
``src/data_provider/tushare_parts/market_boards.py`` and are rebound onto the
public ``TushareFetcher`` class.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

import src.data_provider.tushare_fetcher as tushare_mod
import src.data_provider.tushare_parts.market_boards as boards_mod
from src.data_provider.tushare_fetcher import TushareFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "tushare_fetcher.py"
OWNER_PATH = (
    REPO_ROOT / "src" / "data_provider" / "tushare_parts" / "market_boards.py"
)

MOVED = (
    "get_main_indices",
    "get_market_stats",
    "_calc_market_stats",
    "get_sector_rankings",
)

# Pre-slice shapes, read from origin/main before the move.
METHOD_SIGNATURES = {
    "get_main_indices": ["self", "region"],
    "get_market_stats": ["self"],
    "_calc_market_stats": ["self", "df"],
    "get_sector_rankings": ["self", "n"],
}

# Reached through `self` by the moved bodies; chip stays on the facade class body.
# Trade-calendar helpers are rebound from tushare_parts.trade_time, not this owner.
FACADE_SIBLINGS = (
    "get_chip_distribution",
    "compute_cyq_metrics",
    "is_available",
    "_determine_priority",
)

# Domains this package already owned before the slice; binding must still work.
PRE_EXISTING_BOUND = ("get_daily_data", "_convert_stock_code", "get_trade_time")


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    assert callable(getattr(TushareFetcher, name))


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    method = TushareFetcher.__dict__[name]
    assert method.__module__ == "src.data_provider.tushare_fetcher", name
    assert method.__qualname__ == f"TushareFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    method = TushareFetcher.__dict__[name]
    assert method.__globals__ is vars(tushare_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(TushareFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


def _facade_class_methods() -> set:
    tree = ast.parse(FACADE_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TushareFetcher"
    )
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


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
    defined = _facade_class_methods()
    for name in MOVED:
        assert name not in defined, name


@pytest.mark.parametrize("sibling", FACADE_SIBLINGS)
def test_chip_and_availability_helpers_stay_on_the_facade(sibling) -> None:
    """Boards still reach trade-calendar through `self`; chip stays on the class body."""

    assert sibling in _facade_class_methods(), sibling


def test_rate_limited_client_state_stays_on_the_facade() -> None:
    source = FACADE_PATH.read_text(encoding="utf-8")
    for attribute in ("_api", "_check_rate_limit", "_call_api_with_rate_limit"):
        assert attribute in source, attribute


@pytest.mark.parametrize("name", PRE_EXISTING_BOUND)
def test_previously_bound_domains_are_not_disturbed(name) -> None:
    """This package already had four owner modules; adding a fifth must not clobber them."""

    method = getattr(TushareFetcher, name, None)
    assert callable(method), name


def test_moved_bodies_still_reach_a_patched_facade_global() -> None:
    sentinel = object()
    original = tushare_mod.normalize_stock_code
    try:
        tushare_mod.normalize_stock_code = lambda code: sentinel
        method = TushareFetcher.__dict__["get_sector_rankings"]
        assert method.__globals__["normalize_stock_code"]("600519") is sentinel
    finally:
        tushare_mod.normalize_stock_code = original


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("tushare_fetcher" in module for module in imported)


def test_owner_reload_rebinds_and_leaves_other_domains_intact() -> None:
    importlib.reload(boards_mod)
    for name in MOVED:
        assert TushareFetcher.__dict__[name].__globals__ is vars(tushare_mod), name
    for name in PRE_EXISTING_BOUND:
        assert callable(getattr(TushareFetcher, name, None)), name


def test_expected_names_mismatch_is_an_import_error() -> None:
    from src.data_provider.tushare_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def get_main_indices(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial, _Target, vars(tushare_mod), expected_names=MOVED,
        )
