# -*- coding: utf-8 -*-
"""
===================================
Report Engine - Report renderer tests
===================================

Tests for Jinja2 report rendering and fallback behavior.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from src.analyzer import AnalysisResult
from src.services.report_renderer import render


def _make_result(
    code: str = "600519",
    name: str = "贵州茅台",
    sentiment_score: int = 72,
    operation_advice: str = "持有",
    analysis_summary: str = "稳健",
    decision_type: str = "hold",
    dashboard: dict = None,
    report_language: str = "zh",
    model_used: str = None,
) -> AnalysisResult:
    if dashboard is None:
        dashboard = {
            "core_conclusion": {"one_sentence": "持有观望"},
            "intelligence": {"risk_alerts": []},
            "battle_plan": {"sniper_points": {"stop_loss": "110"}},
        }
    return AnalysisResult(
        code=code,
        name=name,
        trend_prediction="看多",
        sentiment_score=sentiment_score,
        operation_advice=operation_advice,
        analysis_summary=analysis_summary,
        decision_type=decision_type,
        dashboard=dashboard,
        report_language=report_language,
        model_used=model_used,
    )


def _make_renderer_config(show_llm_model: bool = True) -> MagicMock:
    config = MagicMock()
    config.report_templates_dir = "templates"
    config.report_language = "zh"
    config.report_show_llm_model = show_llm_model
    return config


def _with_decision_signal_summary(result: AnalysisResult) -> AnalysisResult:
    result.decision_signal_summary = {
        "action": "sell",
        "action_label": "卖出",
        "horizon": "1d",
        "reason": "技术面走弱",
    }
    return result


class TestReportRenderer(unittest.TestCase):
    """Report renderer tests."""

    def test_render_markdown_summary_only(self) -> None:
        """Markdown platform renders with summary_only."""
        r = _make_result()
        out = render("markdown", [r], summary_only=True)
        self.assertIsNotNone(out)
        self.assertIn("决策仪表盘", out)
        self.assertIn("贵州茅台", out)
        self.assertIn("买入", out)
        self.assertIn("🟢买入:1", out)

    def test_render_markdown_preserves_guardrailed_neutral_action(self) -> None:
        r = _make_result(
            dashboard={
                "core_conclusion": {"one_sentence": "等待确认"},
                "decision_stability": {"applied": True, "reason": "等待回踩确认"},
            }
        )

        out = render("markdown", [r], summary_only=True)

        self.assertIsNotNone(out)
        self.assertIn("持有", out)
        self.assertIn("🟡观望:1", out)

    def test_render_markdown_uses_explicit_avoid_and_alert_text(self) -> None:
        avoid = _make_result(
            code="AVOID",
            name="Avoid Corp",
            sentiment_score=90,
            operation_advice="Buy",
            report_language="en",
        )
        avoid.action = "avoid"
        avoid.action_label = "Avoid"
        alert = _make_result(
            code="ALERT",
            name="Alert Corp",
            sentiment_score=85,
            operation_advice="Buy",
            report_language="en",
        )
        alert.action = "alert"
        alert.action_label = "Alert"

        out = render("markdown", [avoid, alert], summary_only=True)

        self.assertIsNotNone(out)
        self.assertIn("🟡 **Avoid Corp(AVOID)**: Avoid | Score 90", out)
        self.assertIn("🔴 **Alert Corp(ALERT)**: Alert | Score 85", out)
        self.assertIn("**Avoid Corp(AVOID)**: Avoid | Score 90", out)
        self.assertIn("**Alert Corp(ALERT)**: Alert | Score 85", out)
        self.assertNotIn("**Avoid Corp(AVOID)**: Buy", out)
        self.assertNotIn("**Alert Corp(ALERT)**: Buy", out)

    def test_render_markdown_full(self) -> None:
        """Markdown platform renders full report."""
        r = _make_result()
        out = render("markdown", [r], summary_only=False)
        self.assertIsNotNone(out)
        self.assertIn("核心结论", out)
        self.assertIn("作战计划", out)
        self.assertNotIn("盘中决策护栏", out)

    def test_render_markdown_includes_exact_configured_indicator_evidence(self) -> None:
        r = _make_result()
        r.indicator_snapshot = {
            "indicator_period_source": "global_settings",
            "indicator_bar_count": 250,
            "indicator_as_of": "2026-03-27",
            "ma_readings": {
                "30": {
                    "label": "MA30",
                    "value": 101.25,
                    "available": True,
                    "reason": None,
                },
                "250": {
                    "label": "MA250",
                    "value": None,
                    "available": False,
                    "reason": "insufficient_history:need=250,got=120",
                },
            },
            "rsi_readings": {},
            "macd_reading": {
                "label": "MACD(8,17,5)",
                "dif": 0.1234,
                "dea": 0.1111,
                "bar": 0.0246,
                "available": True,
                "reason": None,
            },
        }

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertIn("配置指标", out)
        self.assertIn("MA30", out)
        self.assertIn("101.25", out)
        self.assertIn("MA250", out)
        self.assertIn("insufficient_history:need=250,got=120", out)
        self.assertIn("MACD(8,17,5)", out)
        self.assertIn("DIF=0.1234", out)

    def test_render_markdown_omits_decision_signal_excerpt(self) -> None:
        """Markdown reports omit the duplicated DecisionSignal excerpt."""
        r = _with_decision_signal_summary(_make_result())

        summary_out = render("markdown", [r], summary_only=True)
        self.assertIsNotNone(summary_out)
        self.assertNotIn("AI 决策信号", summary_out)

        full_out = render("markdown", [r], summary_only=False)
        self.assertIsNotNone(full_out)
        self.assertNotIn("AI 决策信号", full_out)
        self.assertNotIn("理由: 技术面走弱", full_out)

    def test_render_markdown_phase_decision_section(self) -> None:
        """Markdown renders phase_decision when present."""
        r = _make_result(
            dashboard={
                "core_conclusion": {"one_sentence": "等待确认"},
                "intelligence": {"risk_alerts": []},
                "phase_decision": {
                    "action_window": "盘中跟踪",
                    "immediate_action": "等待确认",
                    "watch_conditions": ["放量突破"],
                    "next_check_time": "14:30",
                    "confidence_reason": "数据质量可用",
                    "data_limitations": ["quote: stale"],
                },
                "battle_plan": {"sniper_points": {"stop_loss": "110"}},
            }
        )

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertIn("盘中决策护栏", out)
        self.assertIn("盘中跟踪", out)
        self.assertIn("放量突破", out)
        self.assertIn("quote: stale", out)

    def test_render_markdown_skips_context_only_phase_decision_shape(self) -> None:
        """Markdown skips mechanically shaped phase_decision without actionable content."""
        r = _make_result(
            dashboard={
                "core_conclusion": {"one_sentence": "持有观望"},
                "intelligence": {"risk_alerts": []},
                "phase_decision": {
                    "phase_context": {"phase": "intraday", "market": "cn"},
                    "action_window": None,
                    "immediate_action": None,
                    "watch_conditions": [],
                    "next_check_time": None,
                    "confidence_reason": None,
                    "data_limitations": [],
                },
                "battle_plan": {"sniper_points": {"stop_loss": "110"}},
            }
        )

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertNotIn("盘中决策护栏", out)

    def test_render_wechat(self) -> None:
        """Wechat platform renders."""
        r = _make_result()
        out = render("wechat", [r])
        self.assertIsNotNone(out)
        self.assertIn("贵州茅台", out)

    def test_render_wechat_omits_decision_signal_excerpt(self) -> None:
        """Wechat reports omit the duplicated DecisionSignal excerpt."""
        r = _with_decision_signal_summary(_make_result())

        summary_out = render("wechat", [r], summary_only=True)
        self.assertIsNotNone(summary_out)
        self.assertNotIn("AI 决策信号", summary_out)

        full_out = render("wechat", [r], summary_only=False)
        self.assertIsNotNone(full_out)
        self.assertNotIn("AI 决策信号", full_out)
        self.assertNotIn("理由: 技术面走弱", full_out)

    def test_render_brief(self) -> None:
        """Brief platform renders 3-5 sentence summary."""
        r = _make_result()
        out = render("brief", [r])
        self.assertIsNotNone(out)
        self.assertIn("决策简报", out)
        self.assertIn("贵州茅台", out)

    def test_render_brief_omits_decision_signal_excerpt(self) -> None:
        r = _with_decision_signal_summary(_make_result())

        out = render("brief", [r])

        self.assertIsNotNone(out)
        self.assertNotIn("AI 决策信号", out)

    def test_render_brief_respects_model_visibility_toggle(self) -> None:
        r = _make_result(model_used="gemini/gemini-2.5-flash")

        with patch("src.services.report_renderer.get_config", return_value=_make_renderer_config(True)):
            visible = render("brief", [r])
        with patch("src.services.report_renderer.get_config", return_value=_make_renderer_config(False)):
            hidden = render("brief", [r])

        self.assertIsNotNone(visible)
        self.assertIsNotNone(hidden)
        self.assertIn("分析模型: gemini/gemini-2.5-flash", visible)
        self.assertNotIn("分析模型", hidden)
        self.assertNotIn("gemini/gemini-2.5-flash", hidden)

    def test_render_templates_show_compact_market_status_only(self) -> None:
        r = _make_result()
        r.market_phase_summary = {
            "phase": "intraday",
            "market": "cn",
            "trigger_source": "api",
            "is_partial_bar": True,
        }
        r.analysis_context_pack_overview = {
            "data_quality": {
                "level": "limited",
                "limitations": ["quote: stale", "news: missing", "technical: fallback"],
            }
        }
        r.raw_response = "raw context pack should not appear"

        out = render("brief", [r])

        self.assertIsNotNone(out)
        self.assertIn("市场状态：A股 · 盘中", out)
        self.assertNotIn("阶段：intraday", out)
        self.assertNotIn("盘中数据提示", out)
        self.assertNotIn("数据质量: limited", out)
        self.assertNotIn("限制: quote: stale", out)
        self.assertNotIn("限制: news: missing", out)
        self.assertNotIn("technical: fallback", out)
        self.assertNotIn("raw context pack", out)

    def test_render_templates_skip_phase_pack_excerpt_when_summary_missing(self) -> None:
        r = _make_result()

        out = render("brief", [r])

        self.assertIsNotNone(out)
        self.assertNotIn("摘要来源", out)
        self.assertNotIn("evaluator snapshot", out)

    def test_render_market_status_preserves_input_order(self) -> None:
        cn = _make_result(
            code="600519",
            name="贵州茅台",
            sentiment_score=60,
        )
        cn.market_phase_summary = {"market": "cn", "phase": "postmarket"}
        us = _make_result(
            code="AAPL",
            name="Apple",
            sentiment_score=90,
        )
        us.market_phase_summary = {"market": "us", "phase": "premarket"}

        out = render("markdown", [cn, us], summary_only=True)

        self.assertIsNotNone(out)
        self.assertIn("市场状态：A股 · 盘后", out)
        self.assertNotIn("市场状态：美股 · 盘前", out)

    def test_render_markdown_footer_uses_consistent_separator(self) -> None:
        r = _make_result(model_used="gemini/gemini-2.5-flash")

        with patch("src.services.report_renderer.get_config", return_value=_make_renderer_config(True)):
            out = render("markdown", [r], summary_only=True)

        self.assertIsNotNone(out)
        self.assertIn("报告生成时间：", out)
        self.assertIn("分析模型：gemini/gemini-2.5-flash", out)
        self.assertNotIn("分析模型: gemini/gemini-2.5-flash", out)

    def test_render_markdown_in_english(self) -> None:
        """Markdown renderer switches headings and summary labels for English reports."""
        r = _make_result(
            name="Kweichow Moutai",
            operation_advice="Buy",
            analysis_summary="Momentum remains constructive.",
            report_language="en",
        )
        out = render("markdown", [r], summary_only=True)
        self.assertIsNotNone(out)
        self.assertIn("Decision Dashboard", out)
        self.assertIn("Summary", out)
        self.assertIn("Buy", out)

    def test_render_markdown_market_snapshot_uses_template_context(self) -> None:
        """Market snapshot macro should render localized labels with template context."""
        r = _make_result(
            code="AAPL",
            name="Apple",
            operation_advice="Buy",
            report_language="en",
        )
        r.market_snapshot = {
            "close": "180.10",
            "prev_close": "178.25",
            "open": "179.00",
            "high": "181.20",
            "low": "177.80",
            "pct_chg": "+1.04%",
            "change_amount": "1.85",
            "amplitude": "1.91%",
            "volume": "1200000",
            "amount": "215000000",
            "price": "180.35",
            "volume_ratio": "1.2",
            "turnover_rate": "0.8%",
            "source": "polygon",
        }

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertIn("Market Snapshot", out)
        self.assertIn("Volume Ratio", out)

    def test_render_markdown_collapses_unavailable_chip_structure(self) -> None:
        r = _make_result(
            dashboard={
                "core_conclusion": {"one_sentence": "持有观望"},
                "data_perspective": {
                    "chip_structure": {
                        "profit_ratio": "数据缺失，无法判断",
                        "avg_cost": "数据缺失，无法判断",
                        "concentration": "数据缺失，无法判断",
                        "chip_health": "数据缺失，无法判断",
                    }
                },
            }
        )

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertIn("**筹码**: 筹码分布未启用或数据源暂不可用，未纳入筹码判断。", out)
        self.assertEqual(out.count("数据缺失，无法判断"), 0)

    def test_render_markdown_renders_strategy_synthesis_with_localized_labels(self) -> None:
        r = _make_result(
            dashboard={
                "core_conclusion": {"one_sentence": "持有观望"},
                "strategy_synthesis": {
                    "final_signal": "buy",
                    "confidence": 0.8,
                    "conflict_count": 1,
                    "conflict_severity": "medium",
                    "consensus_level": "medium",
                    "summary_key": "strategy_synthesis.with_conflicts",
                    "summary_params": {
                        "opinion_count": 2,
                        "final_signal": "buy",
                        "consensus_level": "medium",
                        "conflict_severity": "medium",
                        "conflict_count": 1,
                    },
                    "supporting_skills": [{"skill_id": "bull_trend", "signal": "buy", "confidence": 0.8}],
                    "opposing_skills": [{"skill_id": "hot_theme", "signal": "sell", "confidence": 0.75}],
                    "conflicts": [
                        {
                            "conflict_type": "directional_opposition",
                            "severity": "medium",
                            "description_key": "strategy_conflict.directional_opposition",
                            "participants": ["bull_trend", "hot_theme"],
                        }
                    ],
                },
            }
        )

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        self.assertIn("多策略综合", out)
        self.assertIn("综合信号: 买入", out)
        self.assertIn("默认多头趋势/买入/80%", out)
        self.assertIn("热点题材/卖出/75%", out)
        self.assertNotIn("bull_trend/买入", out)

    def test_render_templates_use_english_empty_strategy_labels(self) -> None:
        result = _make_result(
            report_language="en",
            dashboard={
                "core_conclusion": {"one_sentence": "Wait for confirmation"},
                "strategy_synthesis": {
                    "final_signal": "hold",
                    "confidence": 0.0,
                    "conflict_count": 0,
                    "conflict_severity": "none",
                    "consensus_level": "insufficient",
                    "summary_params": {"opinion_count": 0},
                    "supporting_skills": [],
                    "opposing_skills": [],
                    "conflicts": [],
                },
            },
        )

        for platform in ("markdown", "wechat"):
            out = render(platform, [result], summary_only=False)

            self.assertIsNotNone(out)
            self.assertIn("Supporting Strategies: None", out)
            self.assertIn("Opposing Strategies: None", out)
            self.assertIn(
                "Strategy synthesis from 0 strategies: final signal is Hold, "
                "consensus level is Insufficient, with no detected conflicts.",
                out,
            )
            self.assertNotIn("支持策略", out)

    def test_render_templates_handle_legacy_strategy_synthesis_shapes(self) -> None:
        for platform in ("markdown", "wechat"):
            for malformed in ("bad-shape", ["bad-shape"], 42, True):
                result = _make_result(
                    dashboard={
                        "core_conclusion": {"one_sentence": "持有观望"},
                        "intelligence": {},
                        "battle_plan": {},
                        "strategy_synthesis": malformed,
                    }
                )

                out = render(platform, [result], summary_only=False)

                self.assertIsNotNone(out)
                self.assertNotIn("多策略综合", out)

            result = _make_result(
                dashboard={
                    "core_conclusion": {"one_sentence": "持有观望"},
                    "intelligence": {},
                    "battle_plan": {},
                    "strategy_synthesis": {
                        "final_signal": "hold",
                        "consensus_level": "insufficient",
                        "conflict_severity": "none",
                        "conflict_count": 0,
                        "supporting_skills": "bad-shape",
                        "opposing_skills": ["bad-shape"],
                        "conflicts": "bad-shape",
                        "summary_params": {"invalid_opinion_count": "3"},
                    },
                }
            )

            out = render(platform, [result], summary_only=False)

            self.assertIsNotNone(out)
            self.assertIn("多策略综合", out)
            self.assertIn("另有 3 个策略解析失败", out)

    def test_render_markdown_normalizes_malformed_conflict_participants(self) -> None:
        result = _make_result(
            dashboard={
                "core_conclusion": {"one_sentence": "持有观望"},
                "strategy_synthesis": {
                    "final_signal": "hold",
                    "consensus_level": "insufficient",
                    "conflict_severity": "medium",
                    "conflict_count": 1,
                    "conflicts": [
                        {
                            "conflict_type": "directional_opposition",
                            "severity": "medium",
                            "participants": 7,
                        }
                    ],
                },
            }
        )

        out = render("markdown", [result], summary_only=False)

        self.assertIsNotNone(out)
        self.assertIn("策略方向出现对立", out)

    def test_render_unknown_platform_returns_none(self) -> None:
        """Unknown platform returns None (caller fallback)."""
        r = _make_result()
        out = render("unknown_platform", [r])
        self.assertIsNone(out)

    def test_render_empty_results_returns_content(self) -> None:
        """Empty results still produces header."""
        out = render("markdown", [], summary_only=True)
        self.assertIsNotNone(out)
        self.assertIn("0", out)


class TestReportStrataRendering(unittest.TestCase):
    """Issue #616: strata sections and always-on disclaimer."""

    def _strata_dashboard(self) -> dict:
        return {
            "core_conclusion": {"one_sentence": "等待确认"},
            "intelligence": {"risk_alerts": []},
            "battle_plan": {"sniper_points": {"stop_loss": "110"}},
            "report_strata": {
                "schema_version": "report-strata-v1",
                "verified_facts": [
                    {
                        "statement": "Close was 1680 on the last daily bar.",
                        "source_id": "ohlcv:daily",
                        "as_of": "2026-07-25T15:00:00+08:00",
                    }
                ],
                "missing_or_conflicts": [
                    {
                        "kind": "conflict",
                        "description": "Volume sources disagree.",
                        "source_ids": ["a", "b"],
                    }
                ],
                "model_inference": [
                    "Momentum may improve if volume confirms."
                ],
                "risks_counter_evidence": [
                    "Break below support invalidates the constructive case."
                ],
                "framework_alignment": {
                    "status": "not_configured",
                    "summary": "Personal investment framework not configured or inactive",
                },
                "disclaimer": "AI-generated content for reference only. Not investment advice.",
            },
        }

    def test_markdown_renders_six_strata_and_keeps_inference_out_of_facts(self) -> None:
        r = _make_result(dashboard=self._strata_dashboard(), report_language="en")
        out = render(
            "markdown",
            [r],
            summary_only=False,
            extra_context={"report_mode": "research"},
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("Evidence Strata", out)
        self.assertIn("Verified Facts", out)
        self.assertIn("Close was 1680", out)
        self.assertIn("Missing Data or Source Conflicts", out)
        self.assertIn("Volume sources disagree", out)
        self.assertIn("Model Inference", out)
        self.assertIn("Momentum may improve", out)
        self.assertIn("Risks / Counter-Evidence", out)
        self.assertIn("Alignment with User Framework", out)
        self.assertIn("Not investment advice", out)
        # Inference text must not appear inside the facts bullet for the close price line only once as fact.
        facts_idx = out.index("Verified Facts")
        inference_idx = out.index("Model Inference")
        self.assertLess(facts_idx, inference_idx)
        facts_block = out[facts_idx:inference_idx]
        self.assertNotIn("Momentum may improve", facts_block)

    def test_historical_without_strata_still_renders_with_disclaimer(self) -> None:
        r = _make_result()
        md = render("markdown", [r], summary_only=False)
        brief = render("brief", [r])
        wechat = render("wechat", [r])
        for out, name in ((md, "markdown"), (brief, "brief"), (wechat, "wechat")):
            self.assertIsNotNone(out, name)
            assert out is not None
            self.assertIn("不构成投资建议", out)
            self.assertNotIn("证据分层", out)

    def test_brief_and_wechat_explicit_brief_mode_omits_strata(self) -> None:
        r = _make_result(dashboard=self._strata_dashboard(), report_language="en")
        brief = render("brief", [r], extra_context={"report_mode": "brief"})
        wechat = render("wechat", [r], extra_context={"report_mode": "brief"})
        for out in (brief, wechat):
            self.assertIsNotNone(out)
            assert out is not None
            self.assertNotIn("Evidence Strata", out)
            self.assertIn("Not investment advice", out)
            self.assertIn("🃏", out)

    def test_brief_and_wechat_default_standard_mode_render_compact_strata(self) -> None:
        r = _make_result(dashboard=self._strata_dashboard(), report_language="en")
        brief = render("brief", [r])
        wechat = render("wechat", [r])
        for out in (brief, wechat):
            self.assertIsNotNone(out)
            assert out is not None
            self.assertIn("Evidence Strata", out)
            self.assertNotIn("#### 1. Verified Facts", out)

    def test_brief_and_wechat_research_mode_renders_strata(self) -> None:
        r = _make_result(dashboard=self._strata_dashboard(), report_language="en")
        brief = render("brief", [r], extra_context={"report_mode": "research"})
        wechat = render("wechat", [r], extra_context={"report_mode": "research"})
        for out in (brief, wechat):
            self.assertIsNotNone(out)
            assert out is not None
            self.assertIn("Evidence Strata", out)


    def test_markdown_disclaimer_once_with_strata(self) -> None:
        r = _make_result(dashboard=self._strata_dashboard(), report_language="en")
        out = render(
            "markdown",
            [r],
            summary_only=False,
            extra_context={"report_mode": "research"},
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("Evidence Strata", out)
        self.assertIn("Verified Facts", out)
        self.assertNotIn("Non-Investment-Advice Disclaimer", out)
        count = out.count("Not investment advice")
        self.assertEqual(count, 1, out)

    def test_markdown_standard_mode_uses_compact_strata(self) -> None:
        r = _make_result(dashboard=self._strata_dashboard(), report_language="en")
        out = render(
            "markdown",
            [r],
            summary_only=False,
            extra_context={"report_mode": "standard"},
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("Evidence Strata", out)
        self.assertNotIn("#### 1. Verified Facts", out)

    def test_markdown_disclaimer_once_without_strata(self) -> None:
        r = _make_result()
        out = render("markdown", [r], summary_only=False)
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out.count("不构成投资建议"), 1)




class TestReportModesAndDecisionCard(unittest.TestCase):
    def _rich_dashboard(self) -> dict:
        return {
            "core_conclusion": {
                "one_sentence": "等待放量确认后再加仓并且继续观察板块轮动与业绩指引变化",
                "time_sensitivity": "本周内",
                "position_advice": {"no_position": "观望等待", "has_position": "继续持有"},
            },
            "intelligence": {
                "sentiment_summary": "中性",
                "risk_alerts": [
                    "业绩波动风险提示较长文本需要被截断处理一二三四五六七八九十",
                    "板块轮动",
                    "流动性收紧",
                    "估值偏高",
                    "外资流出",
                ],
                "positive_catalysts": ["催化A", "催化B", "催化C", "催化D"],
            },
            "phase_decision": {
                "action_window": "盘中跟踪",
                "immediate_action": "等待确认",
                "watch_conditions": ["放量突破前高并且站稳均线", "跌破支撑离场", "成交量持续萎缩"],
                "confidence_reason": "数据质量可用",
            },
            "battle_plan": {
                "sniper_points": {"stop_loss": "1580", "take_profit": "1780"},
                "action_checklist": ["✅ 检查支撑", "⚠️ 观察量能", "❌ 避免追高", "extra1", "extra2"],
            },
            "data_perspective": {
                "trend_status": {"ma_alignment": "多头", "is_bullish": True, "trend_score": 70},
            },
            "report_strata": {
                "verified_facts": [
                    {"statement": f"fact-{i}", "source_id": f"s{i}", "as_of": "2026-08-01"}
                    for i in range(10)
                ],
                "missing_or_conflicts": [],
                "model_inference": [f"inference-{i}" for i in range(6)],
                "risks_counter_evidence": [f"risk-{i}" for i in range(5)],
                "framework_alignment": {"status": "partial", "summary": "partial align"},
            },
        }

    def _rich_result(self):
        r = _make_result(
            sentiment_score=72,
            operation_advice="买入",
            decision_type="buy",
            dashboard=self._rich_dashboard(),
        )
        r.confidence_level = "高"
        return r

    def test_markdown_standard_pins_decision_card_and_keeps_main_sections(self) -> None:
        r = self._rich_result()
        out = render("markdown", [r], summary_only=False, extra_context={"report_mode": "standard"})
        self.assertIsNotNone(out)
        assert out is not None
        card_idx = out.find("### 🃏")
        core_idx = out.find("核心结论")
        self.assertGreaterEqual(card_idx, 0)
        self.assertGreater(core_idx, card_idx)
        self.assertIn("评分 72", out)
        self.assertIn("作战计划", out)

    def test_markdown_brief_mode_is_card_only_with_notice(self) -> None:
        r = self._rich_result()
        out = render("markdown", [r], summary_only=False, extra_context={"report_mode": "brief"})
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("### 🃏", out)
        self.assertIn("已省略", out)
        self.assertNotIn("作战计划", out)
        self.assertNotIn("证据分层", out)
        self.assertIn("评分 72", out)

    def test_extra_context_cannot_override_resolved_mode_limits(self) -> None:
        r = self._rich_result()
        out = render(
            "markdown",
            [r],
            summary_only=False,
            extra_context={
                "report_mode": "brief",
                "mode_limits": {"include_detail_sections": True},
                "report_truncation_notice": "forged notice",
            },
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertNotIn("作战计划", out)
        self.assertNotIn("forged notice", out)
        self.assertIn("已省略", out)

    def test_markdown_research_shows_full_strata_and_more_risks(self) -> None:
        r = self._rich_result()
        out = render("markdown", [r], summary_only=False, extra_context={"report_mode": "research"})
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("### 🃏", out)
        self.assertIn("证据分层", out)
        self.assertIn("已核实事实", out)
        self.assertIn("估值偏高", out)

    def test_hard_limits_cap_risks_and_annotate(self) -> None:
        r = self._rich_result()
        out = render("markdown", [r], summary_only=False, extra_context={"report_mode": "standard"})
        self.assertIsNotNone(out)
        assert out is not None
        # standard max_risks=3 drops lower-priority risks with explicit notice
        self.assertNotIn("外资流出", out)
        self.assertIn("已省略", out)
        self.assertIn("流动性收紧", out)  # third risk kept

    def test_decision_card_never_dropped_when_fields_missing(self) -> None:
        r = _make_result(dashboard={"core_conclusion": {}}, analysis_summary="")
        out = render("markdown", [r], summary_only=False, extra_context={"report_mode": "brief"})
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("### 🃏", out)
        self.assertIn("评分", out)

    def test_brief_platform_supports_explicit_brief_mode(self) -> None:
        r = self._rich_result()
        out = render("brief", [r], extra_context={"report_mode": "brief"})
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("🃏", out)
        self.assertNotIn("证据分层", out)
        self.assertIn("已省略", out)

    def test_wechat_platform_supports_explicit_brief_mode(self) -> None:
        r = self._rich_result()
        out = render("wechat", [r], extra_context={"report_mode": "brief"})
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("🃏", out)
        self.assertNotIn("证据分层", out)

    def test_explicit_research_on_brief_platform(self) -> None:
        r = self._rich_result()
        out = render("brief", [r], extra_context={"report_mode": "research"})
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("🃏", out)
        self.assertIn("证据分层", out)

    def test_config_research_forces_wechat_research(self) -> None:
        r = self._rich_result()
        cfg = _make_renderer_config(True)
        cfg.report_mode = "research"
        with patch("src.services.report_renderer.get_config", return_value=cfg):
            out = render("wechat", [r])
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("证据分层", out)


class TestReportModeHelpers(unittest.TestCase):
    def test_normalize_aliases(self) -> None:
        from src.services.report_mode import normalize_report_mode, resolve_report_mode
        self.assertEqual(normalize_report_mode("minimal"), "brief")
        self.assertEqual(normalize_report_mode("full"), "research")
        self.assertEqual(normalize_report_mode("nope"), "standard")
        self.assertEqual(resolve_report_mode("markdown", config_mode="standard"), "standard")
        self.assertEqual(resolve_report_mode("wechat", config_mode="standard"), "standard")
        self.assertEqual(resolve_report_mode("wechat", config_mode="research"), "research")
        self.assertEqual(
            resolve_report_mode("wechat", explicit="standard", config_mode="research"),
            "standard",
        )

    def test_config_parser_normalizes_report_mode(self) -> None:
        from src.config import Config

        self.assertEqual(Config._parse_report_mode(None), "standard")
        self.assertEqual(Config._parse_report_mode("brief"), "brief")
        self.assertEqual(Config._parse_report_mode("research"), "research")
        self.assertEqual(Config._parse_report_mode("invalid"), "standard")


class TestDecisionCardRendering(unittest.TestCase):
    """Issue #861 Phase 1: Decision Card pin + missing-field degradation."""

    def test_markdown_decision_card_pinned_above_existing_sections(self) -> None:
        r = _make_result(
            dashboard={
                "core_conclusion": {
                    "one_sentence": "等待放量确认",
                    "time_sensitivity": "今日内",
                    "position_advice": {
                        "no_position": "观望",
                        "has_position": "继续持有",
                    },
                },
                "intelligence": {"risk_alerts": ["业绩不及预期", "板块轮动风险"]},
                "phase_decision": {
                    "action_window": "盘中跟踪",
                    "immediate_action": "等待确认",
                    "watch_conditions": ["放量突破", "跌破支撑离场"],
                    "confidence_reason": "数据质量可用",
                },
                "battle_plan": {
                    "sniper_points": {
                        "stop_loss": "110",
                        "take_profit": "130",
                    }
                },
            }
        )
        r.confidence_level = "高"

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        assert out is not None
        card_idx = out.find("### 🃏")
        core_idx = out.find("### 📌 核心结论")
        intel_idx = out.find("### 📰 重要信息速览")
        self.assertGreaterEqual(card_idx, 0, out)
        self.assertGreater(core_idx, card_idx, "core conclusion must stay after Decision Card")
        self.assertGreater(intel_idx, card_idx, "intel section must stay after Decision Card")
        self.assertIn("一句话决策", out)
        self.assertIn("等待放量确认", out)
        self.assertIn("置信度", out)
        self.assertIn("高", out)
        self.assertIn("风险警报", out)
        self.assertIn("业绩不及预期", out)
        self.assertIn("观察条件", out)
        self.assertIn("放量突破", out)
        self.assertIn("止损位", out)
        # Original sections preserved (not deleted).
        self.assertIn("核心结论", out)
        self.assertIn("作战计划", out)

    def test_decision_card_degrades_when_optional_fields_missing(self) -> None:
        r = _make_result(
            analysis_summary="仅有摘要",
            dashboard={},
        )
        r.confidence_level = ""
        r.risk_warning = ""

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("### 🃏", out)
        self.assertIn("仅有摘要", out)
        # Missing optional rows must not render empty labels.
        self.assertNotIn("**风险警报**:", out)
        self.assertNotIn("**观察条件**:", out)
        self.assertNotIn("**置信度理由**:", out)
        self.assertNotIn("**操作点位**:", out)

    def test_decision_card_uses_risk_warning_when_alerts_missing(self) -> None:
        r = _make_result(
            dashboard={
                "core_conclusion": {"one_sentence": "谨慎持有"},
                "intelligence": {},
            }
        )
        r.risk_warning = "流动性风险"
        r.confidence_level = "中"

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("风险提示", out)
        self.assertIn("流动性风险", out)
        self.assertNotIn("**风险警报**:", out)

    def test_brief_and_wechat_lead_with_compact_decision_card(self) -> None:
        r = _make_result(
            dashboard={
                "core_conclusion": {"one_sentence": "持有观望等待确认信号"},
                "intelligence": {"risk_alerts": ["波动加大"]},
                "phase_decision": {
                    "watch_conditions": ["跌破前低失效"],
                    "confidence_reason": "盘中数据可用",
                },
                "battle_plan": {"sniper_points": {"stop_loss": "100", "take_profit": "120"}},
            }
        )
        r.confidence_level = "中"

        brief = render("brief", [r])
        wechat = render("wechat", [r], summary_only=False)

        for out, name in ((brief, "brief"), (wechat, "wechat")):
            self.assertIsNotNone(out, name)
            assert out is not None
            self.assertIn("🃏", out, name)
            self.assertIn("持有观望", out, name)
            self.assertIn("风险警报", out, name)
            self.assertIn("观察条件", out, name)
            # Card appears before stock-local strata or trailing sections.
            card_idx = out.find("🃏")
            self.assertGreaterEqual(card_idx, 0, name)
            if name == "wechat":
                trail_idx = out.find("📌")
            else:
                trail_idx = out.find("不构成投资建议")
            self.assertGreater(
                trail_idx,
                card_idx,
                f"{name}: Decision Card must appear before trailing stock-local / footer content",
            )

    def test_brief_decision_card_respects_push_length_budget(self) -> None:
        """Brief Decision Card must honor the documented push length budget.

        Contract (templates/_macros.j2 decision_card compact='brief' + report_brief.j2):
        - At most 2 non-empty body lines per stock (1 primary + optional 1 supplementary).
        - Primary line keeps origin/main parity fields: signal_emoji, signal_text,
          score label + sentiment_score, and one-sentence conclusion.
        - After markdown_to_plain_text, a 10-stock watchlist must fit in one
          Pushover message (src/notification_parts/senders/pushover_sender.py
          max_length = 1024).
        """
        from src.formatters import markdown_to_plain_text

        results = []
        for i in range(10):
            r = _make_result(
                code=str(600519 + i),
                name="贵州茅台",
                sentiment_score=72,
                operation_advice="买入",
                analysis_summary="等待放量确认后再加仓",
                decision_type="buy",
                dashboard={
                    "core_conclusion": {
                        "one_sentence": "等待放量确认后再加仓",
                        "time_sensitivity": "今日内",
                        "position_advice": {
                            "no_position": "观望",
                            "has_position": "继续持有",
                        },
                    },
                    "intelligence": {
                        "risk_alerts": ["业绩不及预期", "板块轮动风险"],
                    },
                    "phase_decision": {
                        "immediate_action": "等待确认",
                        "watch_conditions": ["放量突破前高", "跌破支撑离场"],
                        "confidence_reason": "数据质量可用",
                    },
                    "battle_plan": {
                        "sniper_points": {
                            "stop_loss": "110",
                            "take_profit": "130",
                        }
                    },
                },
            )
            r.confidence_level = "中"
            results.append(r)

        out = render("brief", results)
        self.assertIsNotNone(out)
        assert out is not None

        # Per-stock line budget: body lines between first stock marker and
        # the disclaimer line (exclude footer lines that start with '*').
        body_start = out.find("**贵州茅台")
        self.assertGreaterEqual(body_start, 0, out)
        disclaimer_line_idx = out.find("*AI生成")
        if disclaimer_line_idx < 0:
            disclaimer_line_idx = out.find("不构成投资建议")
        self.assertGreater(disclaimer_line_idx, body_start, out)
        body = out[body_start:disclaimer_line_idx]
        # Split into per-stock blocks on the stock name marker.
        blocks = [b for b in body.split("**贵州茅台") if b.strip()]
        self.assertEqual(len(blocks), 10, body)
        for i, block in enumerate(blocks):
            stock_block = "**贵州茅台" + block
            non_empty = [
                ln
                for ln in stock_block.splitlines()
                if ln.strip()
                # Exclude italic footer lines (*disclaimer*) but keep **name** primaries.
                and not (
                    ln.strip().startswith("*") and not ln.strip().startswith("**")
                )
            ]
            self.assertLessEqual(
                len(non_empty),
                2,
                f"stock[{i}] exceeds 2-line brief budget ({len(non_empty)} lines):\n"
                + "\n".join(non_empty),
            )
            # Primary-line parity with origin/main one-liner fields.
            primary = non_empty[0]
            self.assertRegex(primary, r"🟢|🟡|🔴")
            self.assertIn("评分", primary)
            self.assertIn("72", primary)
            self.assertIn("等待放量确认后再加仓", primary)

        plain = markdown_to_plain_text(out)
        self.assertLessEqual(
            len(plain),
            1024,
            f"brief plain text for 10 stocks exceeds Pushover max_length=1024 "
            f"(len={len(plain)}):\n{plain}",
        )

    def test_english_decision_card_reuses_existing_labels(self) -> None:
        r = _make_result(
            name="Apple",
            operation_advice="Buy",
            analysis_summary="Momentum remains constructive.",
            report_language="en",
            dashboard={
                "core_conclusion": {"one_sentence": "Buy on pullbacks"},
                "intelligence": {"risk_alerts": ["Macro risk"]},
                "phase_decision": {"watch_conditions": ["Break of support"]},
            },
        )
        r.confidence_level = "High"

        out = render("markdown", [r], summary_only=False)

        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("### 🃏", out)
        self.assertIn("One-line Decision", out)
        self.assertIn("Buy on pullbacks", out)
        self.assertIn("Confidence", out)
        self.assertIn("Risk Alerts", out)
        self.assertIn("Watch Conditions", out)
