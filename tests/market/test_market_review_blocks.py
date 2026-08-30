# -*- coding: utf-8 -*-
"""Characterization tests for the extracted markdown block builders (Issue #1085 step 5).

Groups mirror the step-4 slice contract:
A. facade / patch-seam parity, B. instance-override dispatch counterexamples,
C. byte parity on already-rendered surfaces, D. edge-case characterization.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

import src.market.analyzer as analyzer_mod
import src.market.blocks as blocks_mod
from src.market.analyzer import MarketAnalyzer
from tests.market.test_market_degradation import _cn_overview, _make_analyzer

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYZER_PATH = REPO_ROOT / "src" / "market" / "analyzer.py"
BLOCKS_PATH = REPO_ROOT / "src" / "market" / "blocks.py"

# (analyzer method name, blocks function name)
FIVE = (
    ("_build_stats_block", "build_stats_block"),
    ("_build_indices_block", "build_indices_block"),
    ("_build_sector_block", "build_sector_block"),
    ("_build_sector_analysis_block", "build_sector_analysis_block"),
    ("_build_news_block", "build_news_block"),
)

# Pre-slice shapes, hard-coded on purpose.
METHOD_SIGNATURES = {
    "_build_stats_block": ["self", "overview"],
    "_build_indices_block": ["self", "overview"],
    "_build_sector_block": ["self", "overview"],
    "_build_sector_analysis_block": ["self", "overview"],
    "_build_news_block": ["self", "news"],
}


# --- A. facade / patch-seam parity -------------------------------------------------


@pytest.mark.parametrize("method_name,function_name", FIVE)
def test_methods_remain_on_the_analyzer_facade(method_name, function_name) -> None:
    assert callable(getattr(MarketAnalyzer, method_name))
    assert callable(getattr(blocks_mod, function_name))


@pytest.mark.parametrize("method_name,function_name", FIVE)
def test_module_level_alias_is_re_exported(method_name, function_name) -> None:
    """Patching ``analyzer.<name>`` stays a valid seam for existing callers."""

    assert getattr(analyzer_mod, function_name) is getattr(blocks_mod, function_name)


@pytest.mark.parametrize("method_name,_fn", FIVE)
def test_public_signatures_are_unchanged(method_name, _fn) -> None:
    signature = inspect.signature(getattr(MarketAnalyzer, method_name))
    assert list(signature.parameters) == METHOD_SIGNATURES[method_name]


def test_blocks_module_exports_exactly_the_slice() -> None:
    assert set(blocks_mod.__all__) == {function_name for _m, function_name in FIVE}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    return imported


def test_blocks_module_does_not_import_the_analyzer() -> None:
    """The owner seam exists so this module never needs MarketAnalyzer."""

    imported = _imported_modules(BLOCKS_PATH)
    assert "src.market.analyzer" not in imported
    assert not any(module.endswith(".analyzer") for module in imported)


def test_blocks_module_does_not_import_the_sector_analysis_facade() -> None:
    """CI counterexample: new production code must not import the legacy facade."""

    imported = _imported_modules(BLOCKS_PATH)
    assert "src.market_sector_analysis" not in imported
    assert not any("market_sector_analysis" in module for module in imported)


def test_bodies_no_longer_live_in_the_analyzer_class() -> None:
    tree = ast.parse(ANALYZER_PATH.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MarketAnalyzer"
    )
    for method_name, _fn in FIVE:
        method = next(
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == method_name
        )
        # A pure delegation is exactly one `return <fn>(self, <arg>)` statement.
        assert len(method.body) == 1, method_name
        assert isinstance(method.body[0], ast.Return), method_name


# --- B. instance-override dispatch counterexamples ---------------------------------


def test_instance_override_of_a_sibling_helper_still_reaches_the_builder() -> None:
    """The counterexample the ``owner`` seam exists for.

    If the builder captured helpers at import time instead of resolving them
    through ``owner``, this override would be silently ignored.
    """

    analyzer = _make_analyzer()
    overview = _cn_overview()
    baseline = analyzer._build_indices_block(overview)

    analyzer._format_optional_pct = lambda value: "SENTINEL_PCT"
    overridden = analyzer._build_indices_block(overview)

    assert overridden != baseline
    assert "SENTINEL_PCT" in overridden


def test_subclass_override_of_a_sibling_helper_reaches_the_builder() -> None:
    class Loud(MarketAnalyzer):
        def _format_signed_pct(self, value):  # type: ignore[override]
            return "SENTINEL_SIGNED"

    analyzer = _make_analyzer()
    analyzer.__class__ = Loud
    rendered = analyzer._build_sector_block(_cn_overview())

    assert "SENTINEL_SIGNED" in rendered


def test_calling_the_free_function_with_an_explicit_owner_matches_the_method() -> None:
    analyzer = _make_analyzer()
    overview = _cn_overview()
    assert blocks_mod.build_stats_block(analyzer, overview) == analyzer._build_stats_block(
        overview
    )


def test_analyzer_renderer_patch_reaches_the_sector_analysis_block(monkeypatch) -> None:
    """Pre-slice patch target ``src.market.analyzer.render_sector_analysis_markdown``."""

    analyzer = _make_analyzer()
    overview = _cn_overview()
    monkeypatch.setattr(
        analyzer_mod,
        "render_sector_analysis_markdown",
        lambda *args, **kwargs: "SENTINEL_RENDERER",
    )
    assert analyzer._build_sector_analysis_block(overview) == "SENTINEL_RENDERER"
    assert (
        blocks_mod.build_sector_analysis_block(
            analyzer,
            overview,
            renderer=analyzer_mod.render_sector_analysis_markdown,
        )
        == "SENTINEL_RENDERER"
    )


# --- C. byte parity on rendered surfaces -------------------------------------------


@pytest.mark.parametrize(
    "method_name,argument_factory",
    [
        ("_build_stats_block", _cn_overview),
        ("_build_indices_block", _cn_overview),
        ("_build_sector_block", _cn_overview),
        ("_build_sector_analysis_block", _cn_overview),
    ],
)
def test_blocks_render_deterministically(method_name, argument_factory) -> None:
    analyzer = _make_analyzer()
    argument = argument_factory()
    first = getattr(analyzer, method_name)(argument)
    second = getattr(analyzer, method_name)(argument)
    assert first == second
    assert isinstance(first, str)


def test_indices_block_contains_the_expected_rows() -> None:
    rendered = _make_analyzer()._build_indices_block(_cn_overview())
    for index_name in ("上证指数", "深证成指", "创业板指", "科创50", "北证50"):
        assert index_name in rendered


def test_stats_block_contains_the_breadth_counts() -> None:
    rendered = _make_analyzer()._build_stats_block(_cn_overview())
    assert "1200" in rendered
    assert "900" in rendered


# --- D. edge cases ------------------------------------------------------------------


def test_news_block_handles_an_empty_list() -> None:
    rendered = _make_analyzer()._build_news_block([])
    assert isinstance(rendered, str)


def test_news_block_handles_none() -> None:
    rendered = _make_analyzer()._build_news_block(None)
    assert isinstance(rendered, str)


def test_sector_block_handles_an_overview_without_sectors() -> None:
    overview = _cn_overview()
    overview.top_sectors = []
    overview.bottom_sectors = []
    overview.top_concepts = []
    overview.bottom_concepts = []
    rendered = _make_analyzer()._build_sector_block(overview)
    assert isinstance(rendered, str)
