# -*- coding: utf-8 -*-
"""PortfolioAgent must prefer deterministic rebalancing base over free-form LLM numbers."""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from src.agent.agents.portfolio_agent import PortfolioAgent
from src.agent.protocols import AgentContext


def _agent() -> PortfolioAgent:
    return PortfolioAgent(tool_registry=MagicMock(), llm_adapter=MagicMock())


class PortfolioAgentRebalancingBaseTests(unittest.TestCase):
    def test_post_process_merges_deterministic_suggestions(self) -> None:
        agent = _agent()
        ctx = AgentContext(stock_code="PORT", query="rebalance")
        base: Dict[str, Any] = {
            "status": "ok",
            "status_message": "1 suggestion",
            "disclaimer": "Research aid only — not investment advice.",
            "suggestions": [
                {
                    "action": "trim",
                    "symbol": "AAA",
                    "delta_weight_pct": -15.0,
                    "rationale": "AAA exceeds cap 25%.",
                    "is_suggestion_only": True,
                    "auto_execute": False,
                }
            ],
            "position_bands": [
                {
                    "symbol": "AAA",
                    "action": "reduce",
                    "target_weight_pct_mid": 25.0,
                    "target_weight_pct_low": 20.0,
                    "target_weight_pct_high": 25.0,
                    "signal": "hold",
                    "rationale": "band",
                }
            ],
            "drift": {"breaches": []},
            "target_model": {"name": "risk_band_v1"},
            "assumptions": {"method": "risk_band_drift_v1"},
        }
        ctx.data["portfolio_rebalancing_base"] = base

        raw = json.dumps(
            {
                "portfolio_risk_score": 6,
                "summary": "ok",
                "rebalance_suggestions": ["Buy everything leveraged"],
                "positions": [],
            }
        )
        opinion = agent.post_process(ctx, raw)
        self.assertIsNotNone(opinion)
        assessment = ctx.data["portfolio_assessment"]
        self.assertTrue(
            any("AAA" in str(s) and "trim" in str(s).lower() for s in assessment["rebalance_suggestions"])
        )
        self.assertFalse(
            any("leveraged" in str(s).lower() for s in assessment["rebalance_suggestions"])
        )
        det = assessment["deterministic_rebalancing"]
        self.assertEqual(det["source"], "PortfolioRebalancingService")
        self.assertFalse(det["auto_execute"])
        self.assertEqual(det["suggestions"][0]["symbol"], "AAA")
        self.assertEqual(assessment["positions"][0]["code"], "AAA")

    def test_post_process_overwrites_llm_when_base_has_empty_suggestions(self) -> None:
        agent = _agent()
        ctx = AgentContext(stock_code="PORT", query="rebalance")
        base: Dict[str, Any] = {
            "status": "ok",
            "status_message": "within band",
            "disclaimer": "Research aid only — not investment advice.",
            "suggestions": [],
            "position_bands": [
                {
                    "symbol": "AAA",
                    "action": "hold",
                    "target_weight_pct_mid": 13.75,
                    "target_weight_pct_low": 10.0,
                    "target_weight_pct_high": 15.0,
                    "signal": "hold",
                    "rationale": "within band",
                }
            ],
            "drift": {"breaches": []},
            "target_model": {"name": "risk_band_v1"},
            "assumptions": {"method": "risk_band_drift_v1"},
        }
        ctx.data["portfolio_rebalancing_base"] = base

        raw = json.dumps(
            {
                "portfolio_risk_score": 4,
                "summary": "ok",
                "rebalance_suggestions": ["Buy AAA to 40%", "Trim BBB"],
                "positions": [
                    {
                        "code": "ZZZ",
                        "suggested_weight": 0.40,
                        "note": "invented",
                    }
                ],
            }
        )
        opinion = agent.post_process(ctx, raw)
        self.assertIsNotNone(opinion)
        assessment = ctx.data["portfolio_assessment"]
        self.assertEqual(assessment["rebalance_suggestions"], [])
        self.assertEqual(len(assessment["positions"]), 1)
        self.assertEqual(assessment["positions"][0]["code"], "AAA")
        self.assertAlmostEqual(assessment["positions"][0]["suggested_weight"], 0.1375)
        self.assertNotEqual(assessment["positions"][0]["code"], "ZZZ")

    def test_build_user_message_embeds_base_when_service_returns(self) -> None:
        agent = _agent()
        ctx = AgentContext(stock_code="PORT", query="rebalance")
        ctx.data["stock_list"] = ["AAA", "BBB"]
        fake_base = {
            "status": "ok",
            "suggestions": [{"action": "trim", "symbol": "AAA", "rationale": "cap"}],
            "disclaimer": "Research aid only — not investment advice.",
        }
        with patch(
            "src.agent.agents.portfolio_agent._build_deterministic_portfolio_base",
            return_value=fake_base,
        ):
            message = agent.build_user_message(ctx)
        self.assertIn("Deterministic Rebalancing Base", message)
        self.assertIn("AAA", message)
        self.assertEqual(ctx.data["portfolio_rebalancing_base"], fake_base)


if __name__ == "__main__":
    unittest.main()
