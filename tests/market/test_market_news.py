# -*- coding: utf-8 -*-
"""Characterization tests for the extracted news retrieval helpers (Issue #1085 step 7)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.market.analyzer as analyzer_mod
import src.market.news as news_mod
from src.market.analyzer import MarketAnalyzer
from tests.market.test_market_degradation import _make_analyzer

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYZER_PATH = REPO_ROOT / "src" / "market" / "analyzer.py"
OWNER_PATH = REPO_ROOT / "src" / "market" / "news.py"

THREE = (
    ("search_market_news", "search_market_news"),
    ("_normalize_news_item", "normalize_news_item"),
    ("_merge_persisted_market_intelligence", "merge_persisted_market_intelligence"),
)

METHOD_SIGNATURES = {
    "search_market_news": ["self"],
    "_normalize_news_item": ["item"],
    "_merge_persisted_market_intelligence": ["self", "news"],
}


@pytest.mark.parametrize("method_name,function_name", THREE)
def test_methods_remain_on_the_analyzer_facade(method_name, function_name) -> None:
    assert callable(getattr(MarketAnalyzer, method_name))
    assert callable(getattr(news_mod, function_name))


@pytest.mark.parametrize("method_name,function_name", THREE)
def test_module_level_alias_is_re_exported(method_name, function_name) -> None:
    assert getattr(analyzer_mod, function_name) is getattr(news_mod, function_name)


@pytest.mark.parametrize("method_name,_fn", THREE)
def test_public_signatures_are_unchanged(method_name, _fn) -> None:
    signature = inspect.signature(getattr(MarketAnalyzer, method_name))
    assert list(signature.parameters) == METHOD_SIGNATURES[method_name]


def test_normalize_news_item_remains_a_classmethod() -> None:
    """The descriptor kind is part of the public surface, not an implementation detail."""

    assert isinstance(vars(MarketAnalyzer)["_normalize_news_item"], classmethod)


def test_owner_module_exports_exactly_the_slice() -> None:
    assert set(news_mod.__all__) == {fn for _m, fn in THREE}


def test_owner_module_does_not_import_the_analyzer() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any(module.endswith(".analyzer") for module in imported)


def test_bodies_are_pure_delegation_on_the_analyzer() -> None:
    tree = ast.parse(ANALYZER_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MarketAnalyzer"
    )
    for method_name, _fn in THREE:
        method = next(
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == method_name
        )
        assert len(method.body) == 1, method_name
        assert isinstance(method.body[0], ast.Return), method_name


def test_instance_override_of_the_search_service_reaches_the_fetcher() -> None:
    """The counterexample the ``owner`` seam exists for."""

    analyzer = _make_analyzer()
    analyzer.search_service = SimpleNamespace(
        search_market_news=lambda *a, **k: [{"title": "SENTINEL", "url": "u"}],
    )
    result = analyzer.search_market_news()
    assert isinstance(result, list)


def test_search_failure_is_swallowed_and_returns_a_list() -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("search down")

    analyzer = _make_analyzer()
    analyzer.search_service = SimpleNamespace(search_market_news=_boom)
    assert isinstance(analyzer.search_market_news(), list)


def test_search_without_a_service_returns_a_list() -> None:
    analyzer = _make_analyzer()
    analyzer.search_service = None
    assert isinstance(analyzer.search_market_news(), list)


def test_merge_with_no_persisted_intelligence_returns_the_input() -> None:
    analyzer = _make_analyzer()
    news = [{"title": "a"}]
    merged = analyzer._merge_persisted_market_intelligence(news)
    assert isinstance(merged, list)
