# -*- coding: utf-8 -*-
"""Characterization tests for the extracted pure report formatters (Issue #1085 step 4).

Groups mirror the frozen slice contract:
A. facade / patch-seam parity, B. ``cls``/instance dispatch counterexamples,
C. byte parity on already-rendered surfaces, D. edge-case characterization.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import src.market.analyzer as analyzer_mod
import src.market.formatters as formatters_mod
from src.core.market_profile import CN_PROFILE
from src.core.market_strategy import get_market_strategy_blueprint
from src.market.analyzer import MarketAnalyzer, MarketOverview
from tests.market.test_market_degradation import (
    CN_ZH_GOLDEN,
    FrozenDateTime,
    _cn_overview,
    _make_analyzer,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYZER_PATH = REPO_ROOT / "src" / "market" / "analyzer.py"
FORMATTERS_PATH = REPO_ROOT / "src" / "market" / "formatters.py"

# (analyzer method name, formatters function name, descriptor type)
NINE = (
    ("_get_news_field", "get_news_field", staticmethod),
    ("_format_news_catalyst_line", "format_news_catalyst_line", classmethod),
    ("_compact_news_text", "compact_news_text", staticmethod),
    ("_format_optional_number", "format_optional_number", staticmethod),
    ("_format_optional_pct", "format_optional_pct", staticmethod),
    ("_format_signed_pct", "format_signed_pct", staticmethod),
    ("_format_ranking_summary", "format_ranking_summary", classmethod),
    ("_escape_markdown_link_label", "escape_markdown_link_label", staticmethod),
    ("_describe_turnover", "describe_turnover", staticmethod),
)

# Pre-slice shapes, hard-coded on purpose: (parameter names, keyword-only names, defaults).
METHOD_SIGNATURES = {
    "_get_news_field": (["item", "field"], [], {}),
    "_format_news_catalyst_line": (["idx", "item", "language"], ["language"], {"language": "zh"}),
    "_compact_news_text": (["value", "limit"], ["limit"], {}),
    "_format_optional_number": (["value"], [], {}),
    "_format_optional_pct": (["value"], [], {}),
    "_format_signed_pct": (["value"], [], {}),
    "_format_ranking_summary": (["rows", "limit"], [], {"limit": 3}),
    "_escape_markdown_link_label": (["value"], [], {}),
    "_describe_turnover": (["total_amount"], [], {}),
}

FUNCTION_SIGNATURES = {
    "get_news_field": (["item", "field"], [], {}),
    "format_news_catalyst_line": (["owner", "idx", "item", "language"], ["language"], {"language": "zh"}),
    "compact_news_text": (["value", "limit"], ["limit"], {}),
    "format_optional_number": (["value"], [], {}),
    "format_optional_pct": (["value"], [], {}),
    "format_signed_pct": (["value"], [], {}),
    "format_ranking_summary": (["owner", "rows", "limit"], [], {"limit": 3}),
    "escape_markdown_link_label": (["value"], [], {}),
    "describe_turnover": (["total_amount"], [], {}),
}


def _imported_modules(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
    return names


def _imported_names(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }


def _source_function_names(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "MarketAnalyzer":
            names.update(
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return names


def _signature_shape(target) -> tuple:
    signature = inspect.signature(target)
    params = list(signature.parameters.values())
    return (
        [p.name for p in params],
        [p.name for p in params if p.kind is inspect.Parameter.KEYWORD_ONLY],
        {p.name: p.default for p in params if p.default is not inspect.Parameter.empty},
    )


def _rendering_analyzer(*, report_language: str = "zh", region: str = "cn") -> MarketAnalyzer:
    ma = MarketAnalyzer.__new__(MarketAnalyzer)
    ma.config = SimpleNamespace(report_language=report_language, market_review_color_scheme="green_up")
    ma.region = region
    ma.profile = CN_PROFILE
    ma.strategy = get_market_strategy_blueprint("cn")
    ma.analyzer = None
    return ma


# --- Group A: facade / patch seam parity (assertions 1-7) ------------------


def test_module_level_aliases_are_identical_objects() -> None:
    """A1: src.market.analyzer.<name> is src.market.formatters.<name> for all nine."""
    for _, pure_name, _ in NINE:
        assert getattr(analyzer_mod, pure_name) is getattr(formatters_mod, pure_name), pure_name


def test_delegators_keep_descriptor_types() -> None:
    """A2: seven staticmethods and two classmethods survive the move."""
    for method_name, _, descriptor in NINE:
        raw = vars(MarketAnalyzer)[method_name]
        assert isinstance(raw, descriptor), (method_name, type(raw))


def test_signature_parity_against_pre_slice_shapes() -> None:
    """A3: parameter names, keyword-only markers, and defaults are unchanged."""
    for method_name, pure_name, _ in NINE:
        assert _signature_shape(getattr(MarketAnalyzer, method_name)) == METHOD_SIGNATURES[method_name], method_name
        assert _signature_shape(getattr(formatters_mod, pure_name)) == FUNCTION_SIGNATURES[pure_name], pure_name


def test_module_and_qualname_attribution_both_directions() -> None:
    """A4: delegators stay owned by the analyzer module; pure functions by formatters."""
    for method_name, pure_name, _ in NINE:
        bound = getattr(MarketAnalyzer, method_name)
        assert bound.__module__ == "src.market.analyzer", method_name
        assert bound.__name__ == method_name
        assert bound.__qualname__ == f"MarketAnalyzer.{method_name}"
        pure = getattr(formatters_mod, pure_name)
        assert pure.__module__ == "src.market.formatters", pure_name
        assert pure.__qualname__ == pure_name
        assert pure.__globals__ is vars(formatters_mod), pure_name


def test_module_seam_patch_reaches_class_and_sector_block() -> None:
    """A5: patching the analyzer-module alias is behaviourally effective."""
    with patch.object(analyzer_mod, "format_signed_pct", return_value="SEAM") as patched:
        assert MarketAnalyzer._format_signed_pct(1.5) == "SEAM"
        ma = _rendering_analyzer()
        overview = MarketOverview(date="2026-05-06", top_sectors=[{"name": "半导体", "change_pct": 2.35}])
        assert "| 1 | 半导体 | SEAM |" in ma._build_sector_block(overview)
    assert patched.called
    assert MarketAnalyzer._format_signed_pct(1.5) == "+1.50%"


def test_ast_ownership_of_names() -> None:
    """A6: delegators stay in analyzer.py; orchestration never leaks into formatters.py."""
    analyzer_names = _source_function_names(ANALYZER_PATH)
    formatter_names = _source_function_names(FORMATTERS_PATH)
    for method_name, pure_name, _ in NINE:
        assert method_name in analyzer_names, method_name
        assert pure_name in formatter_names, pure_name
    for leaked in ("generate_market_review", "_build_news_block", "_build_stats_block"):
        assert leaked not in formatter_names, leaked


def test_one_way_import_direction() -> None:
    """A7: formatters.py must not reach back into analyzer.py."""
    formatters_imports = _imported_modules(FORMATTERS_PATH)
    assert "src.market.analyzer" not in formatters_imports
    assert not any(name.startswith("src.market.analyzer") for name in formatters_imports)
    assert "MarketAnalyzer" not in _imported_names(FORMATTERS_PATH)
    assert "src.market.formatters" in _imported_modules(ANALYZER_PATH)


# --- Group B: dispatch-preservation counterexamples (assertions 8-11) -----


def test_class_override_of_compact_news_text_reaches_catalyst_line() -> None:
    """B8: cls dispatch into _compact_news_text is not flattened."""
    item = {"title": "chip rally", "source": "东方财富", "published_date": "2026-05-06"}
    baseline = MarketAnalyzer._format_news_catalyst_line(1, item)
    with patch.object(MarketAnalyzer, "_compact_news_text", return_value="X"):
        overridden = MarketAnalyzer._format_news_catalyst_line(1, item)
    assert overridden != baseline
    assert overridden == "- 1. [X](X)（X / X）"


@pytest.mark.parametrize(
    "method_name,return_value,expected",
    [
        ("_escape_markdown_link_label", "ESC", "- 1. [ESC](https://example.com/a)（东方财富 / 2026-05-06）"),
        ("_get_news_field", "F", "- 1. [F](F)（F / F）"),
    ],
)
def test_class_override_of_escape_and_field_reach_catalyst_line(
    method_name: str, return_value: str, expected: str
) -> None:
    """B9: cls dispatch into _escape_markdown_link_label and _get_news_field survives."""
    item = {
        "title": "chip rally",
        "source": "东方财富",
        "published_date": "2026-05-06",
        "url": "https://example.com/a",
    }
    with patch.object(MarketAnalyzer, method_name, return_value=return_value):
        assert MarketAnalyzer._format_news_catalyst_line(1, item) == expected


def test_class_override_of_signed_pct_reaches_ranking_summary() -> None:
    """B10: cls dispatch into _format_signed_pct is not flattened."""
    rows = [{"name": "半导体", "change_pct": 2.35}]
    assert MarketAnalyzer._format_ranking_summary(rows) == "半导体(+2.35%)"
    with patch.object(MarketAnalyzer, "_format_signed_pct", return_value="Z"):
        assert MarketAnalyzer._format_ranking_summary(rows) == "半导体(Z)"


def test_instance_override_of_describe_turnover_reaches_stats_block_and_report() -> None:
    """B11: instance dispatch survives, including through the degradation owner chain."""
    ma = _make_analyzer(region="cn", report_language="zh")
    overview = _cn_overview()
    with patch.object(ma, "_describe_turnover", return_value="OVERRIDE"):
        stats_block = ma._build_stats_block(overview)
        with patch("src.market.analyzer.datetime", FrozenDateTime):
            report = ma._generate_template_review(overview, [])
    assert "| 两市成交额 | 12345 亿 | OVERRIDE |" in stats_block
    assert "| 两市成交额 | 12345 亿 | OVERRIDE |" in report
    assert "中等活跃" not in report


# --- Group C: byte parity on already-rendered surfaces (assertions 12-15) --


def test_news_block_byte_parity_zh_link_and_metadata() -> None:
    """C12a: zh link + full metadata form is unchanged."""
    ma = _rendering_analyzer()
    result = ma._build_news_block([
        {
            "title": "A股收评：科创50指数放量反弹涨5.47% 两市成交额重回3万亿元",
            "snippet": "复盘必读 2026-05-06 综合描述 A 股三大指数今日集体反弹，成交额放大。",
            "source": "东方财富",
            "published_date": "2026-05-06",
            "url": "https://example.com/news/1",
        }
    ])
    assert (
        "- 1. [A股收评：科创50指数放量反弹涨5.47% 两市成交额重回3万亿元]"
        "(https://example.com/news/1)（东方财富 / 2026-05-06）"
    ) in result
    assert "成交额放大" not in result


def test_news_block_byte_parity_missing_metadata() -> None:
    """C12b: missing-metadata form emits no bracket and no parentheses."""
    ma = _rendering_analyzer()
    result = ma._build_news_block([{"title": "政策利好带动板块活跃", "snippet": "相关主题成交放大"}])
    assert "- 1. 政策利好带动板块活跃" in result
    assert "相关主题成交放大" not in result
    assert "（" not in result.split("- 1. ")[1]


def test_news_block_byte_parity_english_punctuation() -> None:
    """C12c: en metadata punctuation stays ASCII."""
    ma = _rendering_analyzer(report_language="en", region="us")
    result = ma._build_news_block([
        {
            "title": "Chip stocks rally as AI demand improves",
            "source": "Reuters",
            "published_date": "2026-05-06",
            "url": "https://example.com/news/2",
        }
    ])
    assert (
        "- 1. [Chip stocks rally as AI demand improves](https://example.com/news/2)"
        " (Reuters / 2026-05-06)"
    ) in result
    assert "（Reuters" not in result


def test_ranking_summary_rendered_form_in_prompt() -> None:
    """C13: prompt-side ranking summaries keep their rendered form."""
    ma = _rendering_analyzer()
    ma.analyzer = SimpleNamespace(generate_text=MagicMock(return_value="review"))
    overview = MarketOverview(
        date="2026-05-06",
        top_sectors=[{"name": "半导体", "change_pct": 2.35}],
        top_concepts=[{"name": "机器人概念", "change_pct": 4.2}],
    )
    prompt = ma._build_review_prompt(overview, [])
    assert "行业领涨: 半导体(+2.35%)" in prompt
    assert "概念领涨: 机器人概念(+4.20%)" in prompt


def test_review_prompt_still_caps_news_url_context() -> None:
    """C14: the 180-char URL cap in the prompt builder is unchanged."""
    ma = _rendering_analyzer()
    ma.analyzer = SimpleNamespace(generate_text=MagicMock(return_value="review"))
    long_url = "https://example.com/redirect?" + "utm_campaign=" + ("x" * 420)
    prompt = ma._build_review_prompt(
        MarketOverview(date="2026-05-06"),
        [
            {
                "title": "A股收评：指数放量反弹",
                "snippet": "科技成长方向领涨",
                "source": "测试来源",
                "published_date": "2026-05-06",
                "url": long_url,
            }
        ],
    )
    assert long_url not in prompt
    assert "URL: https://example.com/redirect?" in prompt
    assert ("x" * 220) not in prompt


def test_full_template_report_is_byte_identical_to_existing_golden() -> None:
    """C15: reuse the merged degradation golden rather than duplicating it."""
    ma = _make_analyzer(region="cn", report_language="zh")
    with patch("src.market.analyzer.datetime", FrozenDateTime):
        report = ma._generate_template_review(_cn_overview(), [])
    assert report == CN_ZH_GOLDEN
    # The golden already byte-covers _describe_turnover, _format_optional_number,
    # _format_optional_pct, and _format_signed_pct in one rendered surface.
    assert "| 两市成交额 | 12345 亿 | 中等活跃 |" in report
    assert "| 上证指数 | 3200.12 | 🟢 +0.64% | N/A | N/A | N/A | N/A | N/A |" in report
    assert "| 1 | 半导体 | +2.35% |" in report


# --- Group D: edge-case characterization (assertions 16-24) ---------------


def test_escape_markdown_link_label_escapes_backslash_first() -> None:
    """D16: backslash-then-bracket order is load-bearing."""
    assert MarketAnalyzer._escape_markdown_link_label("a\\b[c]d") == "a\\\\b\\[c\\]d"
    assert formatters_mod.escape_markdown_link_label("[\\]") == "\\[\\\\\\]"
    assert MarketAnalyzer._escape_markdown_link_label("plain") == "plain"


@pytest.mark.parametrize(
    "value,expected",
    [(None, "N/A"), (False, "N/A"), (0, "N/A"), (0.0, "N/A"), (0.001, "0.00"), (-1.5, "-1.50"), (3200.125, "3200.12")],
)
def test_format_optional_number_quirks(value, expected: str) -> None:
    """D17: the ``value in (None, 0, 0.0)`` quirk is frozen, including False."""
    assert MarketAnalyzer._format_optional_number(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [(None, "N/A"), (0.0, "N/A"), (False, "N/A"), (0.004, "0.00%"), (-0.21, "-0.21%"), (1.25, "1.25%")],
)
def test_format_optional_pct_quirks(value, expected: str) -> None:
    """D18: percentage variant shares the same falsy-zero quirk."""
    assert MarketAnalyzer._format_optional_pct(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, "N/A"),
        ("", "N/A"),
        ("abc", "N/A"),
        ([], "N/A"),
        ("1.5", "+1.50%"),
        (True, "+1.00%"),
        (0, "+0.00%"),
        (-1.1, "-1.10%"),
    ],
)
def test_format_signed_pct_quirks(value, expected: str) -> None:
    """D19: bare float() in a (TypeError, ValueError) guard, so True -> +1.00%."""
    assert MarketAnalyzer._format_signed_pct(value) == expected


def test_format_signed_pct_returns_na_for_arbitrary_object() -> None:
    assert MarketAnalyzer._format_signed_pct(object()) == "N/A"


def test_compact_news_text_whitespace_and_limits() -> None:
    """D20: whitespace collapse, uncapped limits, and rstrip before the ellipsis."""
    assert MarketAnalyzer._compact_news_text("a\n b\t\tc  d", limit=0) == "a b c d"
    assert MarketAnalyzer._compact_news_text("a\n b\t\tc  d", limit=-5) == "a b c d"
    assert MarketAnalyzer._compact_news_text(None, limit=10) == ""
    assert MarketAnalyzer._compact_news_text("0123456789", limit=5) == "01..."
    assert MarketAnalyzer._compact_news_text("ab defghij", limit=6) == "ab..."
    assert MarketAnalyzer._compact_news_text("0123456789", limit=10) == "0123456789"
    assert MarketAnalyzer._compact_news_text("0123456789", limit=2) == "..."


@pytest.mark.parametrize(
    "total_amount,expected",
    [
        (15000, "高活跃度"),
        (14999.99, "中等活跃"),
        (9000, "中等活跃"),
        (8999.99, "缩量观望"),
        (0.01, "缩量观望"),
        (0, "暂无数据"),
        (-1, "暂无数据"),
    ],
)
def test_describe_turnover_boundaries(total_amount, expected: str) -> None:
    """D21: thresholds and the hardcoded Chinese labels stay as-is (no i18n in this slice)."""
    assert MarketAnalyzer._describe_turnover(total_amount) == expected


def test_get_news_field_precedence_and_coercion() -> None:
    """D22: attribute wins over mapping; missing or None becomes an empty string."""
    assert MarketAnalyzer._get_news_field(SimpleNamespace(title="  attr  "), "title") == "attr"
    assert MarketAnalyzer._get_news_field(SimpleNamespace(title=None), "title") == ""
    assert MarketAnalyzer._get_news_field({"title": " dict "}, "title") == "dict"
    assert MarketAnalyzer._get_news_field({"title": None}, "title") == ""
    assert MarketAnalyzer._get_news_field(object(), "title") == ""
    assert MarketAnalyzer._get_news_field({"title": 123}, "title") == "123"

    class Both(dict):
        title = "from-attribute"

    assert MarketAnalyzer._get_news_field(Both(title="from-mapping"), "title") == "from-attribute"


def test_format_ranking_summary_filtering_and_limits() -> None:
    """D23: None rows, non-dict rows, and blank names are skipped; limit truncates."""
    assert MarketAnalyzer._format_ranking_summary(None) == ""
    assert MarketAnalyzer._format_ranking_summary([]) == ""
    assert MarketAnalyzer._format_ranking_summary(["not-a-dict", 7]) == ""
    assert MarketAnalyzer._format_ranking_summary([{"name": "   ", "change_pct": 1.0}]) == ""
    rows = [{"name": f"s{i}", "change_pct": float(i)} for i in range(5)]
    assert MarketAnalyzer._format_ranking_summary(rows) == "s0(+0.00%), s1(+1.00%), s2(+2.00%)"
    assert MarketAnalyzer._format_ranking_summary(rows, 1) == "s0(+0.00%)"
    assert MarketAnalyzer._format_ranking_summary(rows, limit=0) == ""
    assert MarketAnalyzer._format_ranking_summary([{"change_pct": 1.0}]) == ""


def test_format_news_catalyst_line_fallbacks_and_punctuation() -> None:
    """D24: language fallback titles, no-URL path, and meta punctuation per language."""
    assert MarketAnalyzer._format_news_catalyst_line(1, {}) == "- 1. 未命名线索"
    assert MarketAnalyzer._format_news_catalyst_line(2, {}, language="en") == "- 2. Untitled catalyst"
    no_url = MarketAnalyzer._format_news_catalyst_line(3, {"title": "t", "source": "s"})
    assert no_url == "- 3. t（s）"
    assert "](" not in no_url
    assert (
        MarketAnalyzer._format_news_catalyst_line(
            4, {"title": "t", "source": "s", "published_date": "d"}, language="en"
        )
        == "- 4. t (s / d)"
    )
    assert (
        MarketAnalyzer._format_news_catalyst_line(5, {"title": "t", "url": "https://e/x"})
        == "- 5. [t](https://e/x)"
    )
