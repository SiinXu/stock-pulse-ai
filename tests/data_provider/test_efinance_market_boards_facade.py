# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and reload characterization for the efinance boards slice.

Issue #1068: the market-wide board methods moved into
``src/data_provider/efinance_parts/market_boards.py`` and are rebound onto the
public ``EfinanceFetcher`` class.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
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


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


@pytest.mark.parametrize("name", MOVED)
def test_signatures_are_unchanged(name) -> None:
    signature = inspect.signature(getattr(EfinanceFetcher, name))
    assert list(signature.parameters) == METHOD_SIGNATURES[name]
    if name == "get_main_indices":
        assert signature.parameters["region"].default == "cn"
    if name == "get_sector_rankings":
        assert signature.parameters["n"].default == 5


def test_source_and_facade_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(boards_mod._MarketBoardsMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(EfinanceFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == boards_mod.__name__
    assert tuple(source_names) == boards_mod.EXPECTED_MARKET_BOARD_METHOD_NAMES == MOVED


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


def test_expected_names_mismatch_is_an_import_error() -> None:
    """An incomplete rebind must fail loudly instead of leaving ``None``."""

    from src.data_provider.efinance_parts.facade_bind import bind_methods_from_class

    class _Partial:
        def not_the_board(self):  # pragma: no cover - shape only
            return None

    class _Target:
        pass

    with pytest.raises(ImportError):
        bind_methods_from_class(
            _Partial,
            _Target,
            vars(efinance_mod),
            expected_names=boards_mod.EXPECTED_MARKET_BOARD_METHOD_NAMES,
        )


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.efinance_fetcher as facade",
                    "import src.data_provider.efinance_parts.etf as etf",
                    "import src.data_provider.efinance_parts.market_boards as boards",
                    "import src.data_provider.efinance_parts.realtime as realtime",
                    "",
                    "etf_names = etf.EXPECTED_ETF_METHOD_NAMES",
                    "realtime_names = realtime.EXPECTED_REALTIME_METHOD_NAMES",
                    "boards_names = boards.EXPECTED_MARKET_BOARD_METHOD_NAMES",
                    "owners = (",
                    "    (etf_names, lambda: etf._EtfMethods),",
                    "    (realtime_names, lambda: realtime._RealtimeMethods),",
                    "    (boards_names, lambda: boards._MarketBoardsMethods),",
                    ")",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    return descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    bound = {}",
                    "    for names, owner in owners:",
                    "        for name in names:",
                    "            source[name] = descriptor_function(vars(owner())[name])",
                    "            bound[name] = descriptor_function(",
                    "                vars(facade.EfinanceFetcher)[name]",
                    "            )",
                    "            assert bound[name] is not source[name]",
                    "            assert bound[name].__code__ is source[name].__code__",
                    "            assert bound[name].__globals__ is vars(facade)",
                    "            assert bound[name].__module__ == (",
                    "                'src.data_provider.efinance_fetcher'",
                    "            )",
                    "            assert bound[name].__qualname__ == (",
                    "                f'EfinanceFetcher.{name}'",
                    "            )",
                    "    return source, bound",
                    "",
                    body,
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_reloading_boards_rereads_and_rebinds_all_owners() -> None:
    _run_reload_contract(
        """
old_class = facade.EfinanceFetcher
before_source, before_bound = bindings()
boards = importlib.reload(boards)
assert facade.EfinanceFetcher is old_class
after_source, after_bound = bindings()
for name in boards_names:
    assert after_source[name] is not before_source[name]
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
for name in (*etf_names, *realtime_names):
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
    assert after_bound[name].__globals__ is vars(facade)
"""
    )


def test_reloading_realtime_also_rebinds_boards() -> None:
    _run_reload_contract(
        """
old_class = facade.EfinanceFetcher
before_source, before_bound = bindings()
realtime = importlib.reload(realtime)
assert facade.EfinanceFetcher is old_class
after_source, after_bound = bindings()
assert after_source['get_realtime_quote'] is not before_source['get_realtime_quote']
assert after_bound['get_realtime_quote'] is not before_bound['get_realtime_quote']
for name in boards_names:
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
for name in etf_names:
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
"""
    )


def test_reloading_etf_also_rebinds_boards() -> None:
    _run_reload_contract(
        """
old_class = facade.EfinanceFetcher
before_source, before_bound = bindings()
etf = importlib.reload(etf)
assert facade.EfinanceFetcher is old_class
after_source, after_bound = bindings()
for name in etf_names:
    assert after_source[name] is not before_source[name]
    assert after_bound[name] is not before_bound[name]
for name in (*boards_names, *realtime_names):
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
"""
    )
