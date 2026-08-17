# -*- coding: utf-8 -*-
"""PortfolioAgent must call the real constraint engine on research scenarios."""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict
from unittest.mock import MagicMock

from src.agent.agents.portfolio_agent import PortfolioAgent
from src.agent.protocols import AgentContext
from src.services.portfolio.constraints import (
    LABEL_CONSTRAINT_FEASIBLE,
    LABEL_RESEARCH_ONLY,
)


def _agent() -> PortfolioAgent:
    return PortfolioAgent(tool_registry=MagicMock(), llm_adapter=MagicMock())


def _base_with_buy(*, symbol: str = "AAA", target: float = 20.0) -> Dict[str, Any]:
    return {
        "status": "ok",
        "status_message": "1 suggestion",
        "disclaimer": "Research aid only — not investment advice.",
        "suggestions": [
            {
                "action": "add",
                "symbol": symbol,
                "from_weight_pct": 10.0,
                "to_weight_pct": target,
                "delta_weight_pct": target - 10.0,
                "approx_notional": 0.0,
                "rationale": f"Add {symbol} toward {target:.2f}%.",
                "assumptions": [],
                "is_suggestion_only": True,
                "auto_execute": False,
            }
        ],
        "position_bands": [
            {
                "symbol": symbol,
                "action": "add",
                "current_weight_pct": 10.0,
                "target_weight_pct_mid": target,
                "target_weight_pct_low": max(0.0, target - 5.0),
                "target_weight_pct_high": target,
                "effective_cap_pct": 30.0,
                "signal": "buy",
                "mode": "risk_band",
                "rationale": "band",
                "assumptions": [],
                "is_suggestion_only": True,
                "auto_execute": False,
            }
        ],
        "current": {"weights": [{"symbol": symbol, "weight_pct": 10.0}]},
        "sectors": {symbol: "Tech"},
        "drift": {"breaches": []},
        "target_model": {"name": "risk_band_v1"},
        "assumptions": {"method": "risk_band_drift_v1"},
    }


def _run(
    *,
    config: Dict[str, Any],
    base: Dict[str, Any],
    extra_data: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    agent = _agent()
    ctx = AgentContext(stock_code="PORT", query="rebalance")
    ctx.data["portfolio_rebalancing_base"] = base
    ctx.data["portfolio_constraint_config"] = config
    ctx.data["portfolio_view"] = {
        "weights_pct": {"AAA": 10.0, "BBB": 15.0},
        "sectors": {"AAA": "Tech", "BBB": "Health"},
        "risk_flags": {"AAA": []},
        "weights_known": True,
    }
    if extra_data:
        ctx.data.update(extra_data)
    raw = json.dumps(
        {
            "portfolio_risk_score": 6,
            "summary": "ok",
            "rebalance_suggestions": ["Buy everything leveraged"],
            "positions": [],
        }
    )
    opinion = agent.post_process(ctx, raw)
    assert opinion is not None
    return ctx.data["portfolio_assessment"]


class PortfolioAgentConstraintGateTests(unittest.TestCase):
    def test_allow_path_uses_real_engine_and_keeps_scenario_non_executable(self) -> None:
        assessment = _run(
            config={
                "max_single_name_weight_pct": 30.0,
                "max_sector_weight_pct": 50.0,
                "blacklist": ["ZZZ"],
                "blocking_risk_flags": ["halt"],
            },
            base=_base_with_buy(target=20.0),
        )
        check = assessment["constraint_check"]
        self.assertEqual(check["status"], "allow")
        self.assertEqual(assessment["scenario_label"], LABEL_CONSTRAINT_FEASIBLE)
        self.assertTrue(assessment["constraint_feasible"])
        self.assertFalse(assessment["is_executable_scenario"])
        self.assertFalse(check["executable"])
        self.assertTrue(check["not_broker_compliance"])
        self.assertTrue(
            any("AAA" in str(item) for item in assessment["rebalance_suggestions"])
        )
        self.assertFalse(
            any(str(item).startswith("[research_only]") for item in assessment["rebalance_suggestions"])
        )

    def test_per_name_violation_is_research_only(self) -> None:
        assessment = _run(
            config={"max_single_name_weight_pct": 25.0},
            base=_base_with_buy(target=40.0),
        )
        self.assertEqual(assessment["scenario_label"], LABEL_RESEARCH_ONLY)
        self.assertFalse(assessment["constraint_feasible"])
        self.assertEqual(assessment["constraint_check"]["findings"][0]["constraint"], "per_name_cap")
        self.assertTrue(
            assessment["rebalance_suggestions"][0].startswith("[research_only]")
        )

    def test_sector_violation_is_research_only(self) -> None:
        assessment = _run(
            config={"max_sector_weight_pct": 20.0},
            base=_base_with_buy(target=18.0),
            extra_data={
                "portfolio_view": {
                    "weights_pct": {"AAA": 10.0, "CCC": 12.0},
                    "sectors": {"AAA": "Tech", "CCC": "Tech"},
                    "weights_known": True,
                }
            },
        )
        self.assertEqual(assessment["scenario_label"], LABEL_RESEARCH_ONLY)
        self.assertEqual(assessment["constraint_check"]["findings"][0]["constraint"], "sector_cap")

    def test_blacklist_violation_is_research_only(self) -> None:
        assessment = _run(
            config={"blacklist": ["AAA"]},
            base=_base_with_buy(target=20.0),
        )
        self.assertEqual(assessment["scenario_label"], LABEL_RESEARCH_ONLY)
        self.assertEqual(assessment["constraint_check"]["findings"][0]["constraint"], "blacklist")

    def test_simple_risk_violation_is_research_only(self) -> None:
        assessment = _run(
            config={"blocking_risk_flags": ["halt"]},
            base=_base_with_buy(target=20.0),
            extra_data={
                "portfolio_risk_flags": {"AAA": ["halt"]},
            },
        )
        self.assertEqual(assessment["scenario_label"], LABEL_RESEARCH_ONLY)
        self.assertEqual(assessment["constraint_check"]["findings"][0]["constraint"], "risk_flag")

    def test_unconfigured_passthrough_does_not_invent_executability(self) -> None:
        assessment = _run(config={}, base=_base_with_buy(target=80.0))
        self.assertEqual(assessment["scenario_label"], LABEL_CONSTRAINT_FEASIBLE)
        self.assertTrue(assessment["constraint_check"]["passthrough"])
        self.assertFalse(assessment["is_executable_scenario"])
        self.assertIn("not broker", assessment["disclaimer"].lower())

    def test_unparsed_llm_output_still_runs_the_real_engine(self) -> None:
        agent = _agent()
        ctx = AgentContext(stock_code="PORT", query="rebalance")
        ctx.data["portfolio_constraint_config"] = {"blacklist": ["AAA"]}
        ctx.data["research_proposal"] = {
            "actions": [{"symbol": "AAA", "action": "buy", "target_weight_pct": 10.0}]
        }
        ctx.data["portfolio_view"] = {
            "weights_pct": {"AAA": 5.0},
            "weights_known": True,
        }
        opinion = agent.post_process(ctx, "This is not JSON at all")
        self.assertIsNotNone(opinion)
        self.assertEqual(opinion.signal, "hold")
        self.assertAlmostEqual(opinion.confidence, 0.3)
        assessment = ctx.data["portfolio_assessment"]
        self.assertEqual(assessment["scenario_label"], LABEL_RESEARCH_ONLY)
        self.assertEqual(assessment["constraint_check"]["findings"][0]["constraint"], "blacklist")
        self.assertFalse(assessment["is_executable_scenario"])


if __name__ == "__main__":
    unittest.main()
