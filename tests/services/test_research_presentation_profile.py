# -*- coding: utf-8 -*-
"""Tests for research presentation profiles (#205)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.services.report_mode import get_mode_limits
from src.services.research_presentation_profile import (
    PROFILE_AGGRESSIVE,
    PROFILE_BALANCED,
    PROFILE_CONSERVATIVE,
    assert_profile_does_not_change_limits,
    get_presentation_plan,
    normalize_research_presentation_profile,
    profile_framing_notice,
    resolve_research_presentation_profile,
    risk_content_fingerprint,
    should_emit_framing_notice,
)


class TestResearchPresentationProfileContract(unittest.TestCase):
    def test_normalize_and_aliases(self) -> None:
        self.assertEqual(
            normalize_research_presentation_profile("conservative"),
            PROFILE_CONSERVATIVE,
        )
        self.assertEqual(
            normalize_research_presentation_profile("defensive"),
            PROFILE_CONSERVATIVE,
        )
        self.assertEqual(
            normalize_research_presentation_profile("growth"),
            PROFILE_AGGRESSIVE,
        )
        self.assertEqual(
            normalize_research_presentation_profile("nope"),
            PROFILE_BALANCED,
        )
        self.assertEqual(
            normalize_research_presentation_profile(""),
            PROFILE_BALANCED,
        )

    def test_resolve_precedence(self) -> None:
        self.assertEqual(
            resolve_research_presentation_profile(
                explicit="aggressive",
                config_profile="conservative",
            ),
            PROFILE_AGGRESSIVE,
        )
        self.assertEqual(
            resolve_research_presentation_profile(
                explicit=None,
                config_profile="conservative",
            ),
            PROFILE_CONSERVATIVE,
        )
        self.assertEqual(
            resolve_research_presentation_profile(),
            PROFILE_BALANCED,
        )

    def test_plans_reorder_without_dropping_risk_blocks(self) -> None:
        cons = get_presentation_plan(PROFILE_CONSERVATIVE)
        bal = get_presentation_plan(PROFILE_BALANCED)
        agg = get_presentation_plan(PROFILE_AGGRESSIVE)

        self.assertEqual(cons["intelligence_block_order"][0], "risk_alerts")
        self.assertEqual(agg["intelligence_block_order"][0], "positive_catalysts")
        self.assertIn("risk_alerts", cons["intelligence_block_order"])
        self.assertIn("risk_alerts", agg["intelligence_block_order"])
        self.assertIn("risks_counter_evidence", cons["strata_block_order"])
        self.assertIn("risks_counter_evidence", agg["strata_block_order"])
        self.assertEqual(
            set(cons["intelligence_block_order"]),
            set(bal["intelligence_block_order"]),
        )
        self.assertEqual(
            set(agg["strata_block_order"]),
            set(bal["strata_block_order"]),
        )
        self.assertEqual(cons["strata_block_order"][0], "risks_counter_evidence")
        self.assertNotEqual(
            cons["intelligence_block_order"],
            agg["intelligence_block_order"],
        )

    def test_profile_does_not_mutate_mode_limits(self) -> None:
        limits = get_mode_limits("research")
        before = dict(limits)
        after = assert_profile_does_not_change_limits(limits, PROFILE_AGGRESSIVE)
        self.assertEqual(dict(after), before)
        self.assertEqual(
            after["max_risks"],
            assert_profile_does_not_change_limits(
                get_mode_limits("research"), PROFILE_CONSERVATIVE
            )["max_risks"],
        )

    def test_framing_notice_present(self) -> None:
        for profile in (
            PROFILE_CONSERVATIVE,
            PROFILE_BALANCED,
            PROFILE_AGGRESSIVE,
        ):
            en = profile_framing_notice(profile, "en")
            zh = profile_framing_notice(profile, "zh")
            ko = profile_framing_notice(profile, "ko")
            self.assertIn("Research presentation profile", en)
            self.assertIn("not personalized advice", en)
            self.assertIn("研究呈现偏好", zh)
            self.assertIn("연구", ko)
            self.assertEqual(profile_framing_notice(profile, "en", style="none"), "")

    def test_should_emit_framing_notice_skips_brief(self) -> None:
        self.assertFalse(
            should_emit_framing_notice(report_mode="brief", platform="markdown")
        )
        self.assertFalse(
            should_emit_framing_notice(report_mode="standard", platform="brief")
        )
        self.assertTrue(
            should_emit_framing_notice(report_mode="research", platform="markdown")
        )
        self.assertTrue(
            should_emit_framing_notice(report_mode="standard", platform="wechat")
        )

    def test_risk_fingerprint_order_independent(self) -> None:
        dash_a = {
            "intelligence": {"risk_alerts": ["R2", "R1"]},
            "report_strata": {"risks_counter_evidence": ["S1"]},
        }
        dash_b = {
            "intelligence": {"risk_alerts": ["R1", "R2"]},
            "report_strata": {"risks_counter_evidence": ["S1"]},
        }
        self.assertEqual(
            risk_content_fingerprint(dash_a, risk_warning="W"),
            risk_content_fingerprint(dash_b, risk_warning="W"),
        )


class TestResearchPresentationProfileRenderer(unittest.TestCase):
    def _make_result(self):
        from tests.services.test_report_renderer import _make_result

        result = _make_result(
            report_language="en",
            dashboard={
                "core_conclusion": {
                    "one_sentence": "Hold with tight invalidation.",
                    "time_sensitivity": "This week",
                    "position_advice": {
                        "no_position": "Wait",
                        "has_position": "Hold",
                    },
                },
                "intelligence": {
                    "sentiment_summary": "Mixed sentiment.",
                    "earnings_outlook": "Stable earnings.",
                    "risk_alerts": [
                        "Support break is a hard stop.",
                        "Liquidity dries up into event risk.",
                    ],
                    "positive_catalysts": [
                        "Product launch window.",
                        "Margin recovery narrative.",
                    ],
                    "latest_news": "Quiet tape.",
                },
                "phase_decision": {
                    "watch_conditions": ["Break below 10.0 invalidates."],
                    "immediate_action": "Wait",
                },
                "battle_plan": {
                    "sniper_points": {
                        "stop_loss": "9.8",
                        "take_profit": "12.0",
                    },
                    "action_checklist": ["Check volume"],
                },
                "report_strata": {
                    "verified_facts": [
                        {
                            "statement": "Close was 10.5",
                            "source_id": "quote",
                            "as_of": "2026-08-01",
                        }
                    ],
                    "missing_or_conflicts": [
                        {
                            "kind": "missing",
                            "description": "No fund-flow print.",
                            "source_ids": [],
                        }
                    ],
                    "model_inference": ["Momentum may resume if volume confirms."],
                    "risks_counter_evidence": [
                        "Break below support invalidates the constructive case.",
                        "Crowded long positioning amplifies drawdowns.",
                    ],
                    "framework_alignment": {
                        "status": "not_configured",
                        "summary": "Personal investment framework not configured",
                    },
                    "disclaimer": "Not investment advice.",
                },
            },
        )
        result.risk_warning = "Result-level risk warning stays visible."
        return result

    def test_profiles_reorder_emphasis_with_equal_risk_disclosure(self) -> None:
        from src.services.report_renderer import render

        result = self._make_result()
        cfg = MagicMock()
        cfg.report_language = "en"
        cfg.report_mode = "research"
        cfg.research_presentation_profile = "balanced"
        cfg.report_show_llm_model = False
        cfg.report_templates_dir = "templates"
        cfg.report_renderer_enabled = True

        outs = {}
        with patch("src.services.report_renderer.get_config", return_value=cfg):
            for profile in (
                PROFILE_CONSERVATIVE,
                PROFILE_BALANCED,
                PROFILE_AGGRESSIVE,
            ):
                out = render(
                    "markdown",
                    [result],
                    summary_only=False,
                    extra_context={
                        "report_mode": "research",
                        "research_presentation_profile": profile,
                    },
                )
                self.assertIsNotNone(out, profile)
                assert out is not None
                outs[profile] = out
                self.assertIn("Research presentation profile", out)
                self.assertIn("Not investment advice", out)
                self.assertIn("Support break is a hard stop.", out)
                self.assertIn(
                    "Break below support invalidates the constructive case.",
                    out,
                )
                self.assertIn("Product launch window.", out)

        cons = outs[PROFILE_CONSERVATIVE]
        agg = outs[PROFILE_AGGRESSIVE]
        # Order assertions are scoped to the Key Updates (intelligence) section so the
        # Decision Card's fixed risk-first lines do not dominate global string search.
        def _section_after(text: str, marker: str) -> str:
            idx = text.index(marker)
            return text[idx:]

        cons_intel = _section_after(cons, "Key Updates")
        agg_intel = _section_after(agg, "Key Updates")
        risk_label = "Risk Alerts"
        cat_label = "Positive Catalysts"
        self.assertLess(cons_intel.index(risk_label), cons_intel.index(cat_label))
        self.assertLess(agg_intel.index(cat_label), agg_intel.index(risk_label))

        # Strata: conservative leads with risks counter-evidence block title.
        risks_heading = "Risks / Counter-Evidence"
        facts_heading = "Verified Facts"
        cons_strata = _section_after(cons, "Evidence Strata")
        agg_strata = _section_after(agg, "Evidence Strata")
        self.assertLess(cons_strata.index(risks_heading), cons_strata.index(facts_heading))
        self.assertLess(agg_strata.index(facts_heading), agg_strata.index(risks_heading))

        # Risk content equality across profiles.
        for out in outs.values():
            for token in (
                "Support break is a hard stop.",
                "Liquidity dries up into event risk.",
                "Break below support invalidates the constructive case.",
                "Crowded long positioning amplifies drawdowns.",
            ):
                self.assertIn(token, out)

    def test_config_profile_used_when_explicit_absent(self) -> None:
        from src.services.report_renderer import render

        result = self._make_result()
        cfg = MagicMock()
        cfg.report_language = "en"
        cfg.report_mode = "standard"
        cfg.research_presentation_profile = "aggressive"
        cfg.report_show_llm_model = False
        cfg.report_templates_dir = "templates"
        cfg.report_renderer_enabled = True
        with patch("src.services.report_renderer.get_config", return_value=cfg):
            out = render(
                "markdown",
                [result],
                summary_only=False,
                extra_context={"report_mode": "research"},
            )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("aggressive", out.lower())
        intel = out[out.index("Key Updates"):]
        self.assertLess(intel.index("Positive Catalysts"), intel.index("Risk Alerts"))

    def test_brief_platform_omits_framing_banner(self) -> None:
        """Push-budget brief must not spend characters on framing (#861/#874)."""
        from src.services.report_renderer import render

        result = self._make_result()
        cfg = MagicMock()
        cfg.report_language = "en"
        cfg.report_mode = "brief"
        cfg.research_presentation_profile = "conservative"
        cfg.report_show_llm_model = False
        cfg.report_templates_dir = "templates"
        cfg.report_renderer_enabled = True
        with patch("src.services.report_renderer.get_config", return_value=cfg):
            out = render(
                "brief",
                [result],
                extra_context={
                    "report_mode": "brief",
                    "research_presentation_profile": "conservative",
                },
            )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertNotIn("Research presentation profile", out)
        self.assertNotIn("research framing aid", out.lower())
        self.assertIn("Not investment advice", out)

    def test_compact_strata_includes_risks_for_all_profiles(self) -> None:
        """Compact strata intentionally surfaces risk counter-evidence (#205)."""
        from src.services.report_renderer import render

        result = self._make_result()
        cfg = MagicMock()
        cfg.report_language = "en"
        cfg.report_mode = "standard"
        cfg.research_presentation_profile = "balanced"
        cfg.report_show_llm_model = False
        cfg.report_templates_dir = "templates"
        cfg.report_renderer_enabled = True
        # Compact truncates long lines; assert label + distinctive prefix for parity.
        risk_label = "Risks / Counter-Evidence"
        risk_prefix = "Break below support invalidates"
        with patch("src.services.report_renderer.get_config", return_value=cfg):
            for profile in (
                PROFILE_CONSERVATIVE,
                PROFILE_BALANCED,
                PROFILE_AGGRESSIVE,
            ):
                out = render(
                    "markdown",
                    [result],
                    summary_only=False,
                    extra_context={
                        "report_mode": "standard",
                        "research_presentation_profile": profile,
                    },
                )
                self.assertIsNotNone(out, profile)
                assert out is not None
                # compact (no #### headings) but risks present for equal disclosure
                self.assertNotIn("#### 1. Verified Facts", out)
                self.assertIn("Evidence Strata", out)
                self.assertIn(risk_label, out)
                self.assertIn(risk_prefix, out)
                self.assertIn("Research presentation profile", out)



if __name__ == "__main__":
    unittest.main()
