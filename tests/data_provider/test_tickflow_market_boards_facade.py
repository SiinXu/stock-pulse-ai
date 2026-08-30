# -*- coding: utf-8 -*-
"""Facade identity, patch-seam, and reload characterization for the TickFlow boards slice.

Issue #1068: the market-wide board methods moved into
``src/data_provider/tickflow_parts/market_boards.py`` and are rebound onto the
public ``TickFlowFetcher`` class.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import src.data_provider.tickflow_fetcher as tickflow_mod
import src.data_provider.tickflow_parts.market_boards as boards_mod
from src.data_provider.tickflow_fetcher import TickFlowFetcher
from src.data_provider.tickflow_parts.facade_bind import _descriptor_function
from tests.test_tickflow_fetcher import _FakeClient, _quote

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
        facade_function = _descriptor_function(vars(TickFlowFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == boards_mod.__name__
    assert tuple(source_names) == boards_mod.EXPECTED_MARKET_BOARD_METHOD_NAMES == MOVED


def test_tickflow_facade_bind_is_the_shared_helper() -> None:
    from src.data_provider._facade_bind import bind_methods_from_class as shared
    from src.data_provider.tickflow_parts.facade_bind import (
        bind_methods_from_class as shim,
    )

    assert shim is shared


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


def test_get_market_stats_calls_patched_facade_normalize_stock_code() -> None:
    """Moved get_market_stats must hit the facade patch seam in the quote loop."""

    fetcher = TickFlowFetcher(api_key="sk-test")
    fetcher._client = _FakeClient(universe_data=[_quote("600519.SH", amount=2000.0)])
    original = tickflow_mod.normalize_stock_code
    seen: list[str] = []

    def recording(code):
        seen.append(code)
        return original(code)

    with patch(
        "src.data_provider.tickflow_fetcher.normalize_stock_code",
        side_effect=recording,
    ):
        stats = fetcher.get_market_stats()

    assert stats is not None
    assert stats["up_count"] == 1
    loop_calls = [code for code in seen if code == "600519.SH"]
    assert len(loop_calls) >= 2, seen


def test_owner_module_does_not_import_the_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("tickflow_fetcher" in module for module in imported)


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.tickflow_fetcher as facade",
                    "import src.data_provider.tickflow_parts.market_boards as boards",
                    "",
                    "boards_names = boards.EXPECTED_MARKET_BOARD_METHOD_NAMES",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    return descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    bound = {}",
                    "    owner = boards._MarketBoardsMethods",
                    "    for name in boards_names:",
                    "        source[name] = descriptor_function(vars(owner)[name])",
                    "        bound[name] = descriptor_function(",
                    "            vars(facade.TickFlowFetcher)[name]",
                    "        )",
                    "        assert bound[name] is not source[name]",
                    "        assert bound[name].__code__ is source[name].__code__",
                    "        assert bound[name].__globals__ is vars(facade)",
                    "        assert bound[name].__module__ == (",
                    "            'src.data_provider.tickflow_fetcher'",
                    "        )",
                    "        assert bound[name].__qualname__ == (",
                    "            f'TickFlowFetcher.{name}'",
                    "        )",
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


def test_reloading_boards_rereads_and_rebinds_the_owner() -> None:
    _run_reload_contract(
        """
old_class = facade.TickFlowFetcher
before_source, before_bound = bindings()
boards = importlib.reload(boards)
assert facade.TickFlowFetcher is old_class
after_source, after_bound = bindings()
for name in boards_names:
    assert after_source[name] is not before_source[name]
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
    assert after_bound[name].__globals__ is vars(facade)
    assert after_bound[name].__module__ == 'src.data_provider.tickflow_fetcher'
"""
    )


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
