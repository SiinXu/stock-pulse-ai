# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and reload characterization for the efinance ETF slice.

Issue #1068: ``_fetch_etf_data`` and ``_get_etf_realtime_quote`` moved into
``src/data_provider/efinance_parts/etf.py`` and are rebound onto the public
``EfinanceFetcher`` class. Everything a caller or test could observe must be
unchanged.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

import src.data_provider.efinance_fetcher as efinance_mod
import src.data_provider.efinance_parts.etf as etf_mod
from src.data_provider.efinance_fetcher import EfinanceFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
FACADE_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_fetcher.py"
OWNER_PATH = REPO_ROOT / "src" / "data_provider" / "efinance_parts" / "etf.py"

MOVED = ("_fetch_etf_data", "_get_etf_realtime_quote")

# Pre-slice shapes, hard-coded on purpose.
METHOD_SIGNATURES = {
    "_fetch_etf_data": ["self", "stock_code", "start_date", "end_date"],
    "_get_etf_realtime_quote": ["self", "stock_code"],
}


@pytest.mark.parametrize("name", MOVED)
def test_moved_methods_remain_on_the_public_fetcher(name) -> None:
    method = getattr(EfinanceFetcher, name)
    assert callable(method)
    assert method is not None


@pytest.mark.parametrize("name", MOVED)
def test_module_and_qualname_still_point_at_the_facade(name) -> None:
    """ADR-006: the rebound body must not advertise the owner module."""

    method = EfinanceFetcher.__dict__[name]
    assert method.__module__ == "src.data_provider.efinance_fetcher", name
    assert method.__qualname__ == f"EfinanceFetcher.{name}", name


@pytest.mark.parametrize("name", MOVED)
def test_free_names_resolve_through_the_facade_globals(name) -> None:
    """The patch seam that makes ``patch("...efinance_fetcher.X")`` still work."""

    method = EfinanceFetcher.__dict__[name]
    assert method.__globals__ is vars(efinance_mod), name


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(EfinanceFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]


def test_owner_module_declares_exactly_the_slice() -> None:
    assert etf_mod.EXPECTED_ETF_METHOD_NAMES == MOVED
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_EtfMethods"
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


def test_module_level_helpers_stay_on_the_facade() -> None:
    """No module-level helper travels with the slice.

    The rebind resolves free names from the facade globals at call time, so the
    moved bodies still reach these without owning them.
    """

    for helper in ("_is_etf_code", "_is_us_code", "_ef_call_with_timeout",
                   "_build_eastmoney_etf_secid"):
        assert callable(getattr(efinance_mod, helper)), helper


def test_moved_bodies_still_reach_a_patched_facade_helper() -> None:
    """The patch seam, exercised rather than asserted structurally."""

    sentinel = object()
    original = efinance_mod._build_eastmoney_etf_secid
    try:
        efinance_mod._build_eastmoney_etf_secid = lambda code: sentinel
        method = EfinanceFetcher.__dict__["_fetch_etf_data"]
        assert method.__globals__["_build_eastmoney_etf_secid"]("510300") is sentinel
    finally:
        efinance_mod._build_eastmoney_etf_secid = original


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
    importlib.reload(etf_mod)
    for name in MOVED:
        method = EfinanceFetcher.__dict__[name]
        assert method.__globals__ is vars(efinance_mod), name
        assert method.__qualname__ == f"EfinanceFetcher.{name}", name


def test_expected_names_mismatch_is_an_import_error() -> None:
    """An incomplete rebind must fail loudly instead of leaving ``None``."""

    from src.data_provider.efinance_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def _fetch_etf_data(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial,
            _Target,
            vars(efinance_mod),
            expected_names=MOVED,
        )
