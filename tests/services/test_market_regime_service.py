# -*- coding: utf-8 -*-
"""Tests for explainable market-regime detection (Issue #220)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.agent.protocols import AgentContext, AgentOpinion
from src.agent.skills.router import SkillRouter
from src.market.regime_prompt import format_market_regime_prompt_section
from src.schemas.market_regime import MARKET_REGIME_SCHEMA_VERSION
from src.services.market_regime_service import (
    MARKET_REGIME_KEY,
    MarketRegimeService,
    extract_market_regime_context,
    is_actionable_regime,
)
from src.stock_analyzer import TrendStatus, VolumeStatus


def _trend(
    *,
    status: TrendStatus,
    strength: float,
    volume: VolumeStatus = VolumeStatus.NORMAL,
    volume_ratio: float = 1.0,
    ma_alignment: str = "",
):
    return SimpleNamespace(
        trend_status=status,
        trend_strength=strength,
        volume_status=volume,
        volume_ratio_5d=volume_ratio,
        ma_alignment=ma_alignment or status.value,
    )


class TestMarketRegimeService(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MarketRegimeService()

    def test_trending_up_from_bull_stack(self):
        artifact = self.service.build_from_trend(
            _trend(status=TrendStatus.STRONG_BULL, strength=90),
            stock_code="600519",
            market="cn",
        )
        self.assertEqual(artifact["regime"], "trending_up")
        self.assertEqual(artifact["source"], "rules")
        self.assertEqual(artifact["risk_posture"], "risk_on")
        self.assertIn("ma_bull_stack", artifact["rules_fired"])
        self.assertTrue(artifact["focus_hints"])

    def test_trending_down_from_bear_stack(self):
        artifact = self.service.build_from_trend(
            _trend(status=TrendStatus.BEAR, strength=20),
        )
        self.assertEqual(artifact["regime"], "trending_down")
        self.assertEqual(artifact["risk_posture"], "risk_off")
        self.assertIn("ma_bear_stack", artifact["rules_fired"])

    def test_sideways_from_consolidation(self):
        artifact = self.service.build_from_trend(
            _trend(status=TrendStatus.CONSOLIDATION, strength=50),
        )
        self.assertEqual(artifact["regime"], "sideways")
        self.assertEqual(artifact["risk_posture"], "neutral")

    def test_volatile_from_heavy_volume_mid_strength(self):
        artifact = self.service.build_from_trend(
            _trend(
                status=TrendStatus.CONSOLIDATION,
                strength=50,
                volume=VolumeStatus.HEAVY_VOLUME_UP,
                volume_ratio=2.0,
            ),
        )
        # consolidation wins over volatile when both could apply depending on order;
        # force non-stack mid + heavy without consolidation label via technical raw.
        artifact = self.service.build_from_technical_raw(
            {
                "ma_alignment": "neutral",
                "trend_score": 50,
                "volume_status": "heavy",
            }
        )
        self.assertEqual(artifact["regime"], "volatile")

    def test_unknown_when_missing_inputs(self):
        artifact = self.service.build_from_trend(None)
        self.assertEqual(artifact["regime"], "unknown")
        self.assertEqual(artifact["status"], "unknown")
        evidence_ids = {item["rule_id"] for item in artifact["evidence"]}
        self.assertIn("insufficient_inputs", evidence_ids)
        self.assertFalse(is_actionable_regime(artifact["regime"]))

    def test_unknown_on_conflicting_bull_weak_strength(self):
        artifact = self.service.build_from_trend(
            _trend(status=TrendStatus.BULL, strength=20),
        )
        self.assertEqual(artifact["regime"], "unknown")
        evidence_ids = {item["rule_id"] for item in artifact["evidence"]}
        self.assertIn("conflict_bull_weak", evidence_ids)

    def test_override_takes_precedence(self):
        service = MarketRegimeService(
            config=SimpleNamespace(market_regime_override="sideways")
        )
        artifact = service.build_from_trend(
            _trend(status=TrendStatus.STRONG_BULL, strength=95),
        )
        self.assertEqual(artifact["regime"], "sideways")
        self.assertEqual(artifact["source"], "override")
        self.assertEqual(artifact["override"], "sideways")
        self.assertIn("override_applied", artifact["rules_fired"])

    def test_artifact_evidence_is_traceable(self):
        """Acceptance: regime basis can be reconstructed from the persisted artifact."""
        artifact = self.service.build_from_trend(
            _trend(status=TrendStatus.STRONG_BULL, strength=90),
            stock_code="000001",
        )
        # Round-trip through extract as if loaded from context_snapshot.
        restored = extract_market_regime_context(
            {MARKET_REGIME_KEY: artifact}
        )
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored["schema_version"], MARKET_REGIME_SCHEMA_VERSION)
        self.assertEqual(restored["regime"], "trending_up")
        self.assertEqual(restored["method"], "deterministic_rules_v1")

        evidence = restored["evidence"]
        self.assertTrue(evidence)
        rule_ids = [item["rule_id"] for item in evidence]
        self.assertIn("ma_bull_stack", rule_ids)
        self.assertIn("decision", rule_ids)
        decision = next(item for item in evidence if item["rule_id"] == "decision")
        self.assertEqual(decision["inputs"]["regime"], "trending_up")
        self.assertIn("ma_bull_stack", decision["inputs"]["rules_fired"])
        # Every matched decision rule has inspectable inputs
        bull_rule = next(item for item in evidence if item["rule_id"] == "ma_bull_stack")
        self.assertEqual(bull_rule["outcome"], "matched")
        self.assertIn("trend_status", bull_rule["inputs"])

    def test_prompt_section_includes_evidence_rule_ids(self):
        artifact = self.service.build_from_trend(
            _trend(status=TrendStatus.BEAR, strength=15),
        )
        section = format_market_regime_prompt_section(artifact, report_language="en")
        self.assertIn("## Market Regime Context", section)
        self.assertIn("trending_down", section)
        self.assertIn("Evidence rule ids:", section)
        self.assertIn("ma_bear_stack", section)
        self.assertIn("Analysis focus adjustments:", section)
        self.assertIn("Capital preservation", section)

        section_zh = format_market_regime_prompt_section(artifact, report_language="zh")
        self.assertIn("市场状态（Regime）上下文", section_zh)
        self.assertIn("下降趋势", section_zh)

    def test_prompt_empty_for_invalid_schema(self):
        self.assertEqual(
            format_market_regime_prompt_section({"regime": "trending_up"}),
            "",
        )

    def test_unknown_prebuilt_does_not_block_technical_redetect(self):
        """Pipeline-seeded unknown must not short-circuit later technical recovery."""
        ctx = AgentContext()
        ctx.meta[MARKET_REGIME_KEY] = self.service.build_unavailable(
            stock_code="600519",
            reason="pipeline_seed",
        )
        ctx.add_opinion(
            AgentOpinion(
                agent_name="technical",
                signal="buy",
                confidence=0.8,
                raw_data={
                    "ma_alignment": "bullish",
                    "trend_score": 80,
                    "volume_status": "normal",
                },
            )
        )
        artifact = self.service.build_from_agent_context(ctx)
        self.assertEqual(artifact["regime"], "trending_up")
        self.assertEqual(artifact["source"], "rules")

    def test_unknown_trend_falls_through_to_technical_opinion(self):
        """Conflicting trend stays unknown unless technical data is actionable."""
        ctx = AgentContext()
        ctx.set_data("trend_result", _trend(status=TrendStatus.BULL, strength=20))
        ctx.add_opinion(
            AgentOpinion(
                agent_name="technical",
                signal="buy",
                confidence=0.8,
                raw_data={
                    "ma_alignment": "bullish",
                    "trend_score": 80,
                    "volume_status": "normal",
                },
            )
        )
        artifact = self.service.build_from_agent_context(ctx)
        self.assertEqual(artifact["regime"], "trending_up")

    def test_actionable_prebuilt_is_still_preferred(self):
        prebuilt = self.service.build_from_trend(
            _trend(status=TrendStatus.STRONG_BULL, strength=90),
        )
        ctx = AgentContext()
        ctx.meta[MARKET_REGIME_KEY] = prebuilt
        ctx.add_opinion(
            AgentOpinion(
                agent_name="technical",
                signal="sell",
                confidence=0.8,
                raw_data={
                    "ma_alignment": "bearish",
                    "trend_score": 10,
                    "volume_status": "normal",
                },
            )
        )
        artifact = self.service.build_from_agent_context(ctx)
        self.assertEqual(artifact["regime"], "trending_up")


class TestSkillRouterRegimeIntegration(unittest.TestCase):
    def test_router_uses_explainable_regime_and_stores_artifact(self):
        router = SkillRouter(config=SimpleNamespace(agent_skill_routing="auto"))
        ctx = AgentContext()
        ctx.add_opinion(
            AgentOpinion(
                agent_name="technical",
                signal="buy",
                confidence=0.8,
                raw_data={
                    "ma_alignment": "bullish",
                    "trend_score": 80,
                    "volume_status": "normal",
                },
            )
        )
        regime = router._detect_regime(ctx)
        self.assertEqual(regime, "trending_up")
        artifact = ctx.meta.get(MARKET_REGIME_KEY)
        self.assertIsInstance(artifact, dict)
        self.assertEqual(artifact["regime"], "trending_up")
        self.assertTrue(artifact.get("evidence"))
        # Traceability: decision rule present on the artifact left for consumers
        rule_ids = {item["rule_id"] for item in artifact["evidence"]}
        self.assertIn("decision", rule_ids)

    def test_router_returns_none_for_unknown_regime(self):
        router = SkillRouter(config=SimpleNamespace(agent_skill_routing="auto"))
        ctx = AgentContext()
        # No technical opinion and no trend_result → unknown → no forced route
        regime = router._detect_regime(ctx)
        self.assertIsNone(regime)
        artifact = ctx.meta.get(MARKET_REGIME_KEY)
        self.assertIsInstance(artifact, dict)
        self.assertEqual(artifact["regime"], "unknown")

    def test_router_does_not_force_sideways_on_ambiguous_mid_without_alignment(self):
        """Regression vs old router: incomplete/conflicting data must stay unknown."""
        router = SkillRouter(config=SimpleNamespace(agent_skill_routing="auto"))
        ctx = AgentContext()
        ctx.add_opinion(
            AgentOpinion(
                agent_name="technical",
                signal="hold",
                confidence=0.5,
                raw_data={
                    "ma_alignment": "bullish",
                    "trend_score": 20,  # conflict → unknown
                    "volume_status": "normal",
                },
            )
        )
        regime = router._detect_regime(ctx)
        self.assertIsNone(regime)
        self.assertEqual(ctx.meta[MARKET_REGIME_KEY]["regime"], "unknown")

    def test_router_redetects_when_prebuilt_regime_is_unknown(self):
        router = SkillRouter(config=SimpleNamespace(agent_skill_routing="auto"))
        ctx = AgentContext()
        ctx.meta[MARKET_REGIME_KEY] = MarketRegimeService().build_unavailable(
            stock_code="600519",
            reason="pipeline_seed",
        )
        ctx.add_opinion(
            AgentOpinion(
                agent_name="technical",
                signal="buy",
                confidence=0.8,
                raw_data={
                    "ma_alignment": "bullish",
                    "trend_score": 80,
                    "volume_status": "normal",
                },
            )
        )
        regime = router._detect_regime(ctx)
        self.assertEqual(regime, "trending_up")
        self.assertEqual(ctx.meta[MARKET_REGIME_KEY]["regime"], "trending_up")


if __name__ == "__main__":
    unittest.main()
