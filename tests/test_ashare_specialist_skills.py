# -*- coding: utf-8 -*-
"""Contract tests for default-off A-share specialist Skills (Refs #192)."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.agent.llm_adapter import LLMResponse
from src.agent.orchestrator import AgentOrchestrator
from src.agent.protocols import AgentContext, StageStatus
from src.agent.skills.base import SkillManager
from src.agent.skills.defaults import get_default_active_skill_ids
from src.agent.skills.router import SkillRouter
from src.agent.skills.skill_agent import SkillAgent
from src.agent.tools.analysis_tools import ALL_ANALYSIS_TOOLS
from src.agent.tools.backtest_tools import ALL_BACKTEST_TOOLS
from src.agent.tools.data_tools import ALL_DATA_TOOLS
from src.agent.tools.market_tools import ALL_MARKET_TOOLS
from src.agent.tools.search_tools import ALL_SEARCH_TOOLS
from src.agent.tools.registry import ToolRegistry

_ASHARE_SPECIALIST_SKILL_NAMES = {
    "ashare_capital_flow",
    "ashare_microstructure",
    "ashare_policy_catalyst",
}
_ASHARE_SPECIALIST_MARKERS = {
    "ashare_policy_catalyst": (
        "out of scope",
        "evidence: unavailable",
        "strategyengine handoff",
        "china a-share",
    ),
    "ashare_capital_flow": (
        "out of scope",
        "get_capital_flow",
        "do not invent",
        "feed not available in this runtime",
    ),
    "ashare_microstructure": (
        "out of scope",
        "t+1",
        "limit",
        "auction",
    ),
}


class TestAshareSpecialistSkills(unittest.TestCase):
    """A-share specialists load as default-off framework Skills with valid tools."""

    def test_yaml_files_exist_at_strategies_root(self) -> None:
        strategies_dir = Path(__file__).resolve().parent.parent / "strategies"
        for name in sorted(_ASHARE_SPECIALIST_SKILL_NAMES):
            path = strategies_dir / f"{name}.yaml"
            self.assertTrue(path.is_file(), f"missing {path}")

    def test_pack_contract_default_off_tool_valid_fail_soft(self) -> None:
        manager = SkillManager()
        manager.load_builtin_skills()
        skills = {skill.name: skill for skill in manager.list_skills()}
        available_tools = {
            tool.name
            for tool in (
                ALL_DATA_TOOLS
                + ALL_ANALYSIS_TOOLS
                + ALL_SEARCH_TOOLS
                + ALL_MARKET_TOOLS
                + ALL_BACKTEST_TOOLS
            )
        }

        self.assertTrue(_ASHARE_SPECIALIST_SKILL_NAMES.issubset(set(skills)))
        self.assertEqual(
            get_default_active_skill_ids(list(skills.values())),
            ["bull_trend"],
        )

        for name in _ASHARE_SPECIALIST_SKILL_NAMES:
            skill = skills[name]
            self.assertEqual(skill.category, "framework")
            self.assertEqual(skill.source, "builtin")
            self.assertFalse(skill.enabled)
            self.assertFalse(skill.default_active)
            self.assertFalse(skill.default_router)
            self.assertEqual(skill.market_scopes, ["cn/equity"])
            self.assertTrue(skill.required_tools)
            self.assertEqual(len(skill.required_tools), len(set(skill.required_tools)))
            self.assertLessEqual(set(skill.required_tools), available_tools)
            self.assertIn("Data dependencies", skill.instructions)
            self.assertIn("Explicit degradation", skill.instructions)
            self.assertIn("Output contract", skill.instructions)
            self.assertIn("Not investment advice", skill.instructions)
            lowered = skill.instructions.lower()
            for marker in _ASHARE_SPECIALIST_MARKERS[name]:
                self.assertIn(marker, lowered)

        manager.activate(["all"])
        self.assertTrue(
            _ASHARE_SPECIALIST_SKILL_NAMES.issubset(
                {skill.name for skill in manager.list_active_skills()}
            )
        )
        manager.activate(["ashare_policy_catalyst", "ashare_capital_flow"])
        active = {skill.name for skill in manager.list_active_skills()}
        self.assertEqual(
            active,
            {"ashare_policy_catalyst", "ashare_capital_flow"},
        )
        self.assertNotIn("ashare_microstructure", active)

    @staticmethod
    def _runtime(*, skill_ids=None):
        manager = SkillManager()
        manager.load_builtin_skills()
        selected_ids = list(skill_ids or sorted(_ASHARE_SPECIALIST_SKILL_NAMES))
        manager.activate(selected_ids)

        registry = ToolRegistry()
        for tool in (
            ALL_DATA_TOOLS
            + ALL_ANALYSIS_TOOLS
            + ALL_SEARCH_TOOLS
            + ALL_MARKET_TOOLS
            + ALL_BACKTEST_TOOLS
        ):
            registry.register(tool)

        adapter = MagicMock(model="test-model")
        adapter.call_with_tools.return_value = LLMResponse(
            content=(
                '{"skill_id":"ashare_policy_catalyst","signal":"hold",'
                '"confidence":0.6,"conditions_met":[],"conditions_missed":[],'
                '"score_adjustment":0,"reasoning":"bounded fixture"}'
            ),
            provider="test",
            model="test-model",
        )
        config = SimpleNamespace(
            agent_skill_routing="manual",
            agent_skills=selected_ids,
            agent_multi_strategy_deliberation=False,
        )
        orchestrator = AgentOrchestrator(
            tool_registry=registry,
            llm_adapter=adapter,
            mode="specialist",
            skill_manager=manager,
            config=config,
        )
        return orchestrator, adapter

    def test_runtime_constructs_and_invokes_real_specialist_for_ashare(self) -> None:
        orchestrator, adapter = self._runtime()
        ctx = AgentContext(query="analyze", stock_code="600519", stock_name="贵州茅台")

        agents = orchestrator._build_specialist_agents(ctx)

        self.assertEqual(
            {agent.skill_id for agent in agents},
            _ASHARE_SPECIALIST_SKILL_NAMES,
        )
        self.assertTrue(all(isinstance(agent, SkillAgent) for agent in agents))
        for agent in agents:
            filtered_registry = agent._filtered_registry()
            self.assertTrue(agent.tool_names)
            self.assertTrue(
                all(filtered_registry.get(tool_name) is not None for tool_name in agent.tool_names)
            )

        result = agents[0].run(ctx)
        self.assertEqual(result.status, StageStatus.COMPLETED)
        adapter.call_with_tools.assert_called_once()

    def test_runtime_excludes_ashare_specialists_outside_cash_equities(self) -> None:
        orchestrator, adapter = self._runtime()
        cases = (
            AgentContext(query="hk", stock_code="HK00700"),
            AgentContext(query="us", stock_code="AAPL"),
            AgentContext(query="crypto", stock_code="CRYPTO:BTC"),
            AgentContext(query="jp", stock_code="7203.T"),
            AgentContext(query="etf", stock_code="510300"),
            AgentContext(query="index", stock_code="SH000300"),
            AgentContext(
                query="explicit non-equity",
                stock_code="600519",
                meta={"instrument_type": "index"},
            ),
            AgentContext(query="missing symbol"),
        )

        for ctx in cases:
            with self.subTest(stock_code=ctx.stock_code, meta=ctx.meta):
                self.assertEqual(orchestrator._build_specialist_agents(ctx), [])
        adapter.call_with_tools.assert_not_called()

    def test_scope_filter_runs_before_specialist_cap(self) -> None:
        skill_ids = [*sorted(_ASHARE_SPECIALIST_SKILL_NAMES), "bull_trend"]
        orchestrator, _adapter = self._runtime(skill_ids=skill_ids)
        router = SkillRouter(
            skill_manager=orchestrator.skill_manager,
            config=orchestrator.config,
        )

        self.assertEqual(
            router.select_skills(AgentContext(stock_code="AAPL"), max_count=3),
            ["bull_trend"],
        )

    def test_build_context_preserves_explicit_instrument_type_for_scope_gate(self) -> None:
        orchestrator, _adapter = self._runtime()

        ctx = orchestrator._build_context(
            "analyze",
            {
                "stock_code": "600519",
                "asset_type": "index",
                "skills": sorted(_ASHARE_SPECIALIST_SKILL_NAMES),
            },
        )

        self.assertEqual(ctx.meta["instrument_type"], "index")
        self.assertEqual(orchestrator._build_specialist_agents(ctx), [])


if __name__ == "__main__":
    unittest.main()
