# -*- coding: utf-8 -*-
"""Regression coverage for A-share ETF analysis semantics (Issue #173)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from src.services.etf_analysis import (
    ETF_ANALYSIS_SCHEMA_VERSION,
    LIQUID_A_SHARE_ETF_TRACKING,
    build_etf_analysis_context,
    classify_instrument_type,
    compute_premium_discount,
    format_etf_analysis_prompt_section,
    format_etf_focus_points,
    format_etf_metric_display,
    infer_holdings_exposure,
    infer_tracking_target,
    is_a_share_etf_code,
    is_etf_instrument,
    is_market_index_code,
)


# Representative liquid A-share ETFs from the issue acceptance set.
LIQUID_ETFS = (
    ("510300", "沪深300ETF"),
    ("510050", "上证50ETF"),
    ("159915", "创业板ETF"),
    ("159919", "沪深300ETF"),
    ("512880", "证券ETF"),
)


@pytest.mark.parametrize("code,name", LIQUID_ETFS)
def test_liquid_a_share_etfs_are_identified(code: str, name: str) -> None:
    assert is_a_share_etf_code(code) is True
    assert is_etf_instrument(code, name) is True


def test_equity_codes_are_not_etf() -> None:
    assert is_a_share_etf_code("600519") is False
    assert is_etf_instrument("600519", "贵州茅台") is False
    assert classify_instrument_type("600519", "贵州茅台") == "equity"


def test_pure_index_is_not_labeled_etf() -> None:
    assert is_market_index_code("SPX") is True
    assert is_etf_instrument("SPX", "S&P 500") is False
    assert classify_instrument_type("SPX", "S&P 500", is_index_etf=True) == "index"
    ctx = build_etf_analysis_context("SPX", "S&P 500", is_index_etf=True)
    assert ctx["status"] == "ok"
    assert ctx["instrument_type"] == "index"
    assert ctx["is_etf"] is False
    assert ctx["is_index"] is True
    assert ctx["premium_discount"]["status"] == "not_applicable"
    section = format_etf_analysis_prompt_section(ctx, report_language="en")
    assert "INDEX Analysis Path" in section
    assert "Instrument type: **INDEX**" in section


@pytest.mark.parametrize(
    "code,expected",
    [
        ("510300", "沪深300"),
        ("510050", "上证50"),
        ("159915", "创业板指"),
        ("512880", "证券公司"),
        ("588000", "科创50"),
    ],
)
def test_tracking_target_from_liquid_bootstrap(code: str, expected: str) -> None:
    tracking = infer_tracking_target(code, "")
    assert tracking["status"] == "ok"
    assert tracking["label"] == expected
    assert tracking["source"] == "liquid_bootstrap"


def test_tracking_target_from_name_heuristic() -> None:
    tracking = infer_tracking_target("159999", "华夏中证机器人ETF")
    assert tracking["status"] == "ok"
    assert "机器人" in str(tracking["label"])
    assert tracking["source"] == "name_heuristic"


def test_premium_discount_from_iopv() -> None:
    premium = compute_premium_discount(price=1.02, iopv=1.0)
    assert premium["status"] == "ok"
    assert premium["premium_discount_pct"] == 2.0
    assert premium["reference_kind"] == "iopv"


def test_premium_discount_missing_without_reference() -> None:
    premium = compute_premium_discount(price=1.02)
    assert premium["status"] == "not_available"
    assert premium["premium_discount_pct"] is None


def test_holdings_exposure_classifies_broad_and_sector() -> None:
    broad = infer_holdings_exposure("510300", "沪深300ETF", {"label": "沪深300"})
    assert broad["exposure_class"] == "broad_index"
    assert broad["constituents_status"] == "not_available"

    sector = infer_holdings_exposure("512880", "证券ETF", {"label": "证券公司"})
    assert sector["exposure_class"] == "sector_theme"


def test_build_etf_analysis_context_for_liquid_etf() -> None:
    ctx = build_etf_analysis_context(
        "510300",
        "沪深300ETF",
        realtime={"price": 4.12, "iopv": 4.10},
    )
    assert ctx["schema_version"] == ETF_ANALYSIS_SCHEMA_VERSION
    assert ctx["status"] == "ok"
    assert ctx["is_etf"] is True
    assert ctx["instrument_type"] == "etf"
    assert ctx["is_a_share_etf"] is True
    assert ctx["tracking_target"]["label"] == "沪深300"
    assert ctx["premium_discount"]["status"] == "ok"
    assert ctx["equity_metrics"]["pe_ratio"] == "not_applicable"
    assert ctx["equity_metrics"]["financial_report"] == "not_applicable"
    assert ctx["report_structure"] == "shared_with_equity_dashboard"
    assert "holdings_constituents" in ctx["data_quality"]["missing_fields"]


def test_build_etf_analysis_context_for_equity_is_not_applicable() -> None:
    ctx = build_etf_analysis_context("600519", "贵州茅台")
    assert ctx["status"] == "not_applicable"
    assert ctx["is_etf"] is False
    assert ctx["instrument_type"] == "equity"


def test_format_metric_display_marks_pe_not_applicable_for_etf() -> None:
    assert "not_applicable" in format_etf_metric_display(
        "pe_ratio", 12.3, is_etf=True, language="en"
    )
    assert "不适用" in format_etf_metric_display(
        "pe_ratio", 12.3, is_etf=True, language="zh"
    )
    # Equity path keeps the raw value.
    assert format_etf_metric_display("pe_ratio", 12.3, is_etf=False, language="zh") == "12.3"


def test_enhance_context_passes_iopv_into_premium_path() -> None:
    """Realtime IOPV must reach etf_analysis_context for premium computation."""
    pytest.importorskip("litellm")
    from src.core.stages.analysis_context import _AnalysisContextStageMixin
    from data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote

    class _Harness(_AnalysisContextStageMixin):
        def __init__(self) -> None:
            self.fetcher_manager = SimpleNamespace(
                build_failed_fundamental_context=lambda code, msg: {
                    "status": "failed",
                    "code": code,
                    "message": msg,
                }
            )
            self.config = SimpleNamespace(report_language="zh")
            self.search_service = SimpleNamespace(news_window_days=3)

    quote = UnifiedRealtimeQuote(
        code="510300",
        name="沪深300ETF",
        source=RealtimeSource.AKSHARE_EM,
        price=4.12,
        iopv=4.10,
        nav=4.09,
    )
    harness = _Harness()
    enhanced = harness._enhance_context(
        {"code": "510300", "today": {"close": 4.1}},
        realtime_quote=quote,
        chip_data=None,
        trend_result=None,
        stock_name="沪深300ETF",
    )
    assert enhanced["realtime"]["iopv"] == 4.10
    assert enhanced["realtime"]["nav"] == 4.09
    premium = enhanced["etf_analysis_context"]["premium_discount"]
    assert premium["status"] == "ok"
    assert premium["premium_discount_pct"] == pytest.approx(0.4878, rel=1e-3)


def test_prompt_section_contains_etf_path_and_na_metrics() -> None:
    ctx = build_etf_analysis_context("510300", "沪深300ETF")
    zh = format_etf_analysis_prompt_section(ctx, report_language="zh")
    en = format_etf_analysis_prompt_section(ctx, report_language="en")
    assert "ETF 专属分析路径" in zh
    assert "跟踪标的" in zh
    assert "not_applicable" in zh or "不适用" in zh
    assert "决策仪表盘" in zh or "共用" in zh
    assert "ETF Analysis Path" in en
    assert "not_applicable" in en
    assert format_etf_analysis_prompt_section(
        build_etf_analysis_context("600519", "贵州茅台"),
        report_language="zh",
    ) == ""


def test_focus_points_are_etf_specific() -> None:
    zh = format_etf_focus_points("zh")
    assert "跟踪" in zh
    assert "溢价" in zh or "折价" in zh
    assert "持仓" in zh


def test_liquid_bootstrap_covers_acceptance_codes() -> None:
    for code, _name in LIQUID_ETFS:
        assert code in LIQUID_A_SHARE_ETF_TRACKING


def test_enhance_context_attaches_etf_analysis_context() -> None:
    """Pipeline context enrichment must set instrument_type=etf for liquid ETFs."""
    pytest.importorskip("litellm")
    from src.core.stages.analysis_context import _AnalysisContextStageMixin

    class _Harness(_AnalysisContextStageMixin):
        def __init__(self) -> None:
            self.fetcher_manager = SimpleNamespace(
                build_failed_fundamental_context=lambda code, msg: {
                    "status": "failed",
                    "code": code,
                    "message": msg,
                }
            )
            self.config = SimpleNamespace(report_language="zh")
            self.search_service = SimpleNamespace(news_window_days=3)

    harness = _Harness()
    enhanced = harness._enhance_context(
        {"code": "510300", "today": {"close": 4.1}},
        realtime_quote=None,
        chip_data=None,
        trend_result=None,
        stock_name="沪深300ETF",
    )
    assert enhanced["is_index_etf"] is True
    assert enhanced["instrument_type"] == "etf"
    assert isinstance(enhanced.get("etf_analysis_context"), dict)
    assert enhanced["etf_analysis_context"]["is_etf"] is True
    assert enhanced["etf_analysis_context"]["tracking_target"]["label"] == "沪深300"


def test_format_prompt_uses_etf_path_and_marks_pe_na() -> None:
    """Analyzer prompt for ETF must use ETF path and mark PE as not applicable."""
    pytest.importorskip("litellm")
    from src.analyzer import GeminiAnalyzer

    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer._get_skill_prompt_sections = MagicMock(return_value=("", "", True))
    analyzer._format_volume = lambda v: str(v) if v is not None else "N/A"
    analyzer._format_amount = lambda v: str(v) if v is not None else "N/A"

    etf_ctx = build_etf_analysis_context(
        "510300",
        "沪深300ETF",
        realtime={"price": 4.1, "pe_ratio": 99.0, "pb_ratio": 1.2},
    )
    context: Dict[str, Any] = {
        "code": "510300",
        "stock_name": "沪深300ETF",
        "date": "2026-08-12",
        "today": {"close": 4.1, "pct_chg": 0.5, "volume": 1000, "amount": 4000},
        "is_index_etf": True,
        "instrument_type": "etf",
        "etf_analysis_context": etf_ctx,
        "realtime": {
            "price": 4.1,
            "volume_ratio": 1.0,
            "turnover_rate": 0.5,
            "pe_ratio": 99.0,
            "pb_ratio": 1.2,
        },
        "fundamental_context": {
            "earnings": {
                "data": {
                    "financial_report": {"revenue": 1, "roe": 0.1},
                    "dividend": {},
                }
            }
        },
        "news_window_days": 3,
    }
    prompt = analyzer._format_prompt(
        context,
        name="沪深300ETF",
        news_context=None,
        report_language="zh",
    )
    assert "品种类型" in prompt and "etf" in prompt
    assert "ETF 专属分析路径" in prompt or "专属分析路径" in prompt
    assert "不适用" in prompt
    assert "公司财报" in prompt or "口径" in prompt
    # Must not present the hard PE value as a usable equity multiple.
    assert "| 市盈率(动态) | 99.0 |" not in prompt
    assert "跟踪" in prompt
    assert "决策仪表盘" in prompt
    # Chip must not use equity health framing on the ETF path.
    assert "70-90%时警惕" not in prompt
    assert "筹码" in prompt and ("不适用" in prompt or "not_applicable" in prompt)


def test_format_prompt_marks_chip_na_for_index() -> None:
    pytest.importorskip("litellm")
    from src.analyzer import GeminiAnalyzer

    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer._get_skill_prompt_sections = MagicMock(return_value=("", "", True))
    analyzer._format_volume = lambda v: str(v) if v is not None else "N/A"
    analyzer._format_amount = lambda v: str(v) if v is not None else "N/A"
    idx_ctx = build_etf_analysis_context("SPX", "S&P 500", is_index_etf=True)
    context: Dict[str, Any] = {
        "code": "SPX",
        "stock_name": "S&P 500",
        "date": "2026-08-12",
        "today": {"close": 5000.0, "pct_chg": 0.1, "volume": 1, "amount": 1},
        "is_index_etf": True,
        "instrument_type": "index",
        "etf_analysis_context": idx_ctx,
        "chip": {
            "profit_ratio": 0.8,
            "avg_cost": 1.0,
            "concentration_90": 0.1,
            "concentration_70": 0.05,
            "chip_status": "集中",
        },
        "news_window_days": 3,
    }
    prompt = analyzer._format_prompt(context, name="S&P 500", report_language="zh")
    assert "品种类型" in prompt and "index" in prompt
    assert "70-90%时警惕" not in prompt
    assert "不适用" in prompt