# -*- coding: utf-8 -*-
"""Characterization tests for the extracted news retrieval helpers (Issue #1085 step 7)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.market.analyzer as analyzer_mod
import src.market.news as news_mod
from src.market.analyzer import MarketAnalyzer
from src.services.intelligence_service import IntelligenceService
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
    response = SimpleNamespace(results=[{"title": "SENTINEL", "url": "u"}])
    analyzer.search_service = SimpleNamespace(
        search_stock_news=lambda *a, **k: response,
    )
    result = analyzer.search_market_news()
    assert any(item.get("title") == "SENTINEL" for item in result)


def test_search_failure_is_swallowed_and_returns_a_list() -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("search down")

    analyzer = _make_analyzer()
    analyzer.search_service = SimpleNamespace(search_stock_news=_boom)
    assert isinstance(analyzer.search_market_news(), list)


def test_search_without_a_service_returns_a_list() -> None:
    analyzer = _make_analyzer()
    analyzer.search_service = None
    assert isinstance(analyzer.search_market_news(), list)


def test_merge_with_no_persisted_intelligence_returns_the_input() -> None:
    analyzer = _make_analyzer()
    news = [{"title": "a"}]
    with patch("src.market.analyzer.IntelligenceService", side_effect=RuntimeError("intel down")):
        merged = analyzer._merge_persisted_market_intelligence(news)
    assert isinstance(merged, list)
    assert any(item.get("title") == "a" for item in merged)


# --- Direct unit tests of the extracted functions (Issue #1085 acceptance) ----------
#
# The tests above exercise the functions through MarketAnalyzer. These call
# src.market.news directly with an explicit owner, so a regression in the
# extracted unit is caught without depending on facade wiring.


def _owner(**overrides):
    """Minimal duck-typed owner: only what the news functions actually read."""

    def _field(item, field):
        if isinstance(item, dict):
            return str(item.get(field, "") or "")
        return str(getattr(item, field, "") or "")

    base = {
        "search_service": None,
        "config": SimpleNamespace(market_review_news_count=5),
        "profile": SimpleNamespace(name="CN", news_queries=["A股 大盘"]),
        "region": "cn",
        "_log_context": lambda: "region=cn",
        "_get_review_language": lambda: "zh",
        "_get_news_field": _field,
        "_compact_news_text": lambda value, *, limit: str(value)[:limit],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_search_market_news_returns_a_list_without_a_service() -> None:
    assert news_mod.search_market_news(_owner()) == []


def test_search_market_news_swallows_provider_errors() -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("search down")

    owner = _owner(search_service=SimpleNamespace(search_stock_news=_boom))
    assert news_mod.search_market_news(owner) == []


def test_search_market_news_passes_through_returned_items() -> None:
    items = [{"title": "t1", "url": "u1"}, {"title": "t2", "url": "u2"}]
    response = SimpleNamespace(results=items)
    owner = _owner(
        search_service=SimpleNamespace(search_stock_news=lambda *a, **k: response),
    )
    result = news_mod.search_market_news(owner)
    assert isinstance(result, list)
    assert result, "a successful search must surface its results"


def test_normalize_news_item_maps_a_dict_item() -> None:
    normalized = news_mod.normalize_news_item(_owner(), {"title": "t", "url": "u"})
    assert isinstance(normalized, dict)


def test_normalize_news_item_tolerates_a_non_dict_item() -> None:
    normalized = news_mod.normalize_news_item(_owner(), SimpleNamespace(title="t", url="u"))
    assert isinstance(normalized, dict)


def test_news_module_binds_the_real_intelligence_service() -> None:
    assert news_mod.IntelligenceService is IntelligenceService
    assert analyzer_mod.IntelligenceService is IntelligenceService


def test_analyzer_intelligence_service_patch_reaches_merge() -> None:
    """Facade patches on ``src.market.analyzer.IntelligenceService`` must still fire."""

    analyzer = _make_analyzer()
    analyzer.config.get_effective_news_window_days = lambda: 3
    with patch("src.market.analyzer.IntelligenceService") as service_cls:
        service = service_cls.return_value
        service.refresh_auto_sources.return_value = {"ok": True}
        service.list_items.return_value = {
            "items": [
                {
                    "title": "PATCHED-LOCAL",
                    "summary": "from facade patch",
                    "url": "https://example.com/patched",
                    "source": "test",
                    "published_at": "2026-08-31",
                }
            ],
            "total": 1,
        }
        merged = analyzer._merge_persisted_market_intelligence([])
    service_cls.assert_called_once_with(config=analyzer.config)
    assert any(item.get("title") == "PATCHED-LOCAL" for item in merged)


def test_news_module_intelligence_service_patch_reaches_duck_typed_owner() -> None:
    with patch.object(news_mod, "IntelligenceService") as service_cls:
        service = service_cls.return_value
        service.refresh_auto_sources.return_value = {"ok": True}
        service.list_items.return_value = {
            "items": [
                {
                    "title": "OWNER-LOCAL",
                    "summary": "from news-module binding",
                    "url": "https://example.com/owner-local",
                }
            ],
            "total": 1,
        }
        owner = _owner()
        owner.config.get_effective_news_window_days = lambda: 3
        merged = news_mod.merge_persisted_market_intelligence(owner, [])
    service_cls.assert_called_once_with(config=owner.config)
    assert any(item.get("title") == "OWNER-LOCAL" for item in merged)


def test_merge_persisted_market_intelligence_returns_a_list_for_empty_input() -> None:
    with patch.object(news_mod, "IntelligenceService", side_effect=RuntimeError("intel down")):
        assert isinstance(news_mod.merge_persisted_market_intelligence(_owner(), []), list)


def test_merge_persisted_market_intelligence_preserves_input_items() -> None:
    news = [{"title": "keep-me", "url": "u"}]
    with patch.object(news_mod, "IntelligenceService", side_effect=RuntimeError("intel down")):
        merged = news_mod.merge_persisted_market_intelligence(_owner(), news)
    assert isinstance(merged, list)
    assert any(item.get("title") == "keep-me" for item in merged if isinstance(item, dict))
