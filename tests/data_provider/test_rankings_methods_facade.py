# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for rankings extraction."""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import src.data_provider.base as base
import src.data_provider.manager_parts.rankings_methods as rankings
from src.data_provider.base import BaseFetcher, DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT / "src" / "data_provider" / "manager_parts" / "rankings_methods.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def test_rankings_methods_remain_on_data_fetcher_manager_facade() -> None:
    for name in rankings.EXPECTED_RANKINGS_METHOD_NAMES:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_copy_ranking_rows_remains_staticmethod() -> None:
    assert isinstance(vars(DataFetcherManager)["_copy_ranking_rows"], staticmethod)


def test_clear_concept_rankings_cache_for_tests_remains_classmethod() -> None:
    assert isinstance(
        vars(DataFetcherManager)["clear_concept_rankings_cache_for_tests"],
        classmethod,
    )


def test_public_rankings_signatures_are_unchanged() -> None:
    assert list(
        inspect.signature(DataFetcherManager.get_sector_rankings).parameters
    ) == ["self", "n"]
    assert list(
        inspect.signature(DataFetcherManager.get_concept_rankings).parameters
    ) == ["self", "n"]
    assert list(
        inspect.signature(DataFetcherManager.get_hot_stocks).parameters
    ) == ["self", "n"]


def test_base_fetcher_provider_methods_are_untouched() -> None:
    for name in ("get_sector_rankings", "get_concept_rankings", "get_hot_stocks",
                 "get_limit_up_pool"):
        assert name in vars(BaseFetcher), name
        function = _descriptor_function(vars(BaseFetcher)[name])
        assert function.__qualname__ == f"BaseFetcher.{name}", name


def test_rankings_bodies_no_longer_live_in_data_fetcher_manager() -> None:
    """Bodies leave ``DataFetcherManager`` only; ``BaseFetcher`` keeps its own."""

    tree = ast.parse(BASE_PATH.read_text(encoding="utf-8"))
    manager_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "DataFetcherManager"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in rankings.EXPECTED_RANKINGS_METHOD_NAMES:
        assert name not in manager_defs, name

    base_fetcher_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "BaseFetcher"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in ("get_sector_rankings", "get_concept_rankings", "get_hot_stocks",
                 "get_limit_up_pool"):
        assert name in base_fetcher_defs, name


def test_facade_reload_rebinds_rankings_methods() -> None:
    importlib.reload(rankings)
    for name in rankings.EXPECTED_RANKINGS_METHOD_NAMES:
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__globals__ is vars(base), name


def test_owner_module_declares_expected_names_only() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_RankingsMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(rankings.EXPECTED_RANKINGS_METHOD_NAMES)


def test_facade_keeps_main_indices_and_market_stats() -> None:
    """Slice 16 rebinds these names; bodies leave DataFetcherManager only."""

    tree = ast.parse(BASE_PATH.read_text(encoding="utf-8"))
    manager_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "DataFetcherManager"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "get_main_indices" not in manager_defs
    assert "get_market_stats" not in manager_defs

    base_fetcher_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "BaseFetcher"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "get_main_indices" in base_fetcher_defs
    assert "get_market_stats" in base_fetcher_defs

    source = BASE_PATH.read_text(encoding="utf-8")
    assert "    get_main_indices = None" in source
    assert "    get_market_stats = None" in source
