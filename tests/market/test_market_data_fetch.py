# -*- coding: utf-8 -*-
"""Characterization tests for the extracted market-overview fetch helpers (Issue #1085 step 6).

Groups mirror the step-5 slice contract:
A. facade / patch-seam parity, B. instance-override dispatch counterexamples,
C. the circular-import anchor, D. edge-case characterization.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.market.analyzer as analyzer_mod
import src.market.market_data as market_data_mod
from src.market.analyzer import MarketAnalyzer
from tests.market.test_market_degradation import _cn_overview, _make_analyzer

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYZER_PATH = REPO_ROOT / "src" / "market" / "analyzer.py"
OWNER_PATH = REPO_ROOT / "src" / "market" / "market_data.py"

# (analyzer method name, market_data function name)
FOUR = (
    ("_get_main_indices", "get_main_indices"),
    ("_get_market_statistics", "get_market_statistics"),
    ("_get_sector_rankings", "get_sector_rankings"),
    ("_get_concept_rankings", "get_concept_rankings"),
)

# Pre-slice shapes, read from origin/main before the move.
METHOD_SIGNATURES = {
    "_get_main_indices": ["self"],
    "_get_market_statistics": ["self", "overview"],
    "_get_sector_rankings": ["self", "overview"],
    "_get_concept_rankings": ["self", "overview"],
}


# --- A. facade / patch-seam parity -------------------------------------------------


@pytest.mark.parametrize("method_name,function_name", FOUR)
def test_methods_remain_on_the_analyzer_facade(method_name, function_name) -> None:
    assert callable(getattr(MarketAnalyzer, method_name))
    assert callable(getattr(market_data_mod, function_name))


@pytest.mark.parametrize("method_name,function_name", FOUR)
def test_module_level_alias_is_re_exported(method_name, function_name) -> None:
    assert getattr(analyzer_mod, function_name) is getattr(market_data_mod, function_name)


@pytest.mark.parametrize("method_name,_fn", FOUR)
def test_public_signatures_are_unchanged(method_name, _fn) -> None:
    signature = inspect.signature(getattr(MarketAnalyzer, method_name))
    assert list(signature.parameters) == METHOD_SIGNATURES[method_name]


def test_owner_module_exports_exactly_the_slice() -> None:
    assert set(market_data_mod.__all__) == {fn for _m, fn in FOUR}


def test_owner_module_does_not_import_the_analyzer() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert "src.market.analyzer" not in imported
    assert not any(module.endswith(".analyzer") for module in imported)


def test_bodies_are_pure_delegation_on_the_analyzer() -> None:
    tree = ast.parse(ANALYZER_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MarketAnalyzer"
    )
    for method_name, _fn in FOUR:
        method = next(
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == method_name
        )
        assert len(method.body) == 1, method_name
        assert isinstance(method.body[0], ast.Return), method_name


# --- B. instance-override dispatch counterexamples ---------------------------------


def test_instance_override_of_the_data_manager_reaches_the_fetcher() -> None:
    """The counterexample the ``owner`` seam exists for."""

    analyzer = _make_analyzer()
    top = [{"name": "SENTINEL", "change_pct": 1.0}]
    bottom = [{"name": "OTHER", "change_pct": -1.0}]
    analyzer.data_manager = SimpleNamespace(
        get_sector_rankings=lambda *a, **k: (top, bottom),
    )
    overview = _cn_overview()
    analyzer._get_sector_rankings(overview)
    assert overview.top_sectors == top
    assert overview.bottom_sectors == bottom


def test_calling_the_free_function_with_an_explicit_owner_matches_the_method() -> None:
    analyzer = _make_analyzer()
    analyzer.data_manager = SimpleNamespace(
        get_concept_rankings=lambda *a, **k: (
            [{"name": "X", "change_pct": 1.0}],
            [{"name": "Y", "change_pct": -1.0}],
        ),
    )
    first = _cn_overview()
    second = _cn_overview()
    analyzer._get_concept_rankings(first)
    market_data_mod.get_concept_rankings(analyzer, second)
    assert first.top_concepts == second.top_concepts


# --- C. the circular-import anchor -------------------------------------------------


def test_market_index_anchor_is_injected_by_the_analyzer() -> None:
    """``market_data`` cannot import ``MarketIndex``; the analyzer injects it."""

    assert market_data_mod.MarketIndex is analyzer_mod.MarketIndex
    assert market_data_mod.MarketIndex is not None


def test_reimporting_the_owner_module_keeps_the_facade_wired() -> None:
    importlib.reload(market_data_mod)
    importlib.reload(analyzer_mod)
    assert analyzer_mod.get_main_indices is not None
    assert analyzer_mod._market_data.MarketIndex is analyzer_mod.MarketIndex


# --- D. edge cases ------------------------------------------------------------------


def test_fetch_failure_is_swallowed_and_leaves_the_overview_usable() -> None:
    """A provider error must not escape; the previous bodies logged and moved on."""

    def _boom(*args, **kwargs):
        raise RuntimeError("provider down")

    analyzer = _make_analyzer()
    analyzer.data_manager = SimpleNamespace(
        get_sector_rankings=_boom,
        get_concept_rankings=_boom,
        get_market_stats=_boom,
    )
    overview = _cn_overview()
    analyzer._get_sector_rankings(overview)
    analyzer._get_concept_rankings(overview)
    assert isinstance(overview.top_sectors, list)
    assert isinstance(overview.top_concepts, list)


def test_main_indices_returns_a_list_when_the_manager_is_missing() -> None:
    analyzer = _make_analyzer()
    analyzer.data_manager = None
    assert isinstance(analyzer._get_main_indices(), list)


# --- Direct unit tests of the extracted functions (Issue #1085 acceptance) ----------
#
# The tests above exercise the functions through MarketAnalyzer. These call
# src.market.market_data directly with an explicit owner, so a regression in the
# extracted unit is caught without depending on facade wiring.
#
# The owner contract is exactly three attributes: data_manager, region,
# _log_context. Anything more would be over-specifying the seam.


def _owner(manager=None):
    return SimpleNamespace(
        data_manager=manager,
        region="cn",
        _log_context=lambda: "region=cn",
    )


def test_get_main_indices_returns_a_list_without_a_manager() -> None:
    assert market_data_mod.get_main_indices(_owner()) == []


def test_get_main_indices_swallows_provider_errors() -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("provider down")

    assert market_data_mod.get_main_indices(
        _owner(SimpleNamespace(get_main_indices=_boom))
    ) == []


def test_get_sector_rankings_writes_both_sides_onto_the_overview() -> None:
    top = [{"name": "T", "change_pct": 1.0}]
    bottom = [{"name": "B", "change_pct": -1.0}]
    overview = _cn_overview()
    market_data_mod.get_sector_rankings(
        _owner(SimpleNamespace(get_sector_rankings=lambda *a, **k: (top, bottom))),
        overview,
    )
    assert overview.top_sectors == top
    assert overview.bottom_sectors == bottom


def test_get_sector_rankings_leaves_the_overview_untouched_on_empty_result() -> None:
    overview = _cn_overview()
    before_top = list(overview.top_sectors)
    market_data_mod.get_sector_rankings(
        _owner(SimpleNamespace(get_sector_rankings=lambda *a, **k: ([], []))),
        overview,
    )
    assert overview.top_sectors == before_top


def test_get_concept_rankings_writes_both_sides_onto_the_overview() -> None:
    top = [{"name": "CT", "change_pct": 2.0}]
    bottom = [{"name": "CB", "change_pct": -2.0}]
    overview = _cn_overview()
    market_data_mod.get_concept_rankings(
        _owner(SimpleNamespace(get_concept_rankings=lambda *a, **k: (top, bottom))),
        overview,
    )
    assert overview.top_concepts == top
    assert overview.bottom_concepts == bottom


def test_get_market_statistics_swallows_provider_errors() -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("stats down")

    overview = _cn_overview()
    market_data_mod.get_market_statistics(
        _owner(SimpleNamespace(get_market_stats=_boom)), overview
    )
    assert overview.up_count is not None


def test_owner_contract_is_only_three_attributes() -> None:
    """Guard against the seam quietly growing: adding a fourth owner attribute
    would break every caller that builds a minimal owner, including this test."""

    import ast
    import re

    source = OWNER_PATH.read_text(encoding="utf-8")
    accessed = set(re.findall(r"owner\.(\w+)", source))
    assert accessed == {"data_manager", "region", "_log_context"}
    ast.parse(source)
