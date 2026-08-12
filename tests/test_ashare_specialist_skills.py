# -*- coding: utf-8 -*-
"""Contract tests for default-off A-share specialist Skills (Refs #192)."""

from __future__ import annotations

import unittest
from pathlib import Path

from src.agent.skills.base import SkillManager
from src.agent.skills.defaults import get_default_active_skill_ids
from src.agent.tools.analysis_tools import ALL_ANALYSIS_TOOLS
from src.agent.tools.backtest_tools import ALL_BACKTEST_TOOLS
from src.agent.tools.data_tools import ALL_DATA_TOOLS
from src.agent.tools.market_tools import ALL_MARKET_TOOLS
from src.agent.tools.search_tools import ALL_SEARCH_TOOLS

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


if __name__ == "__main__":
    unittest.main()
