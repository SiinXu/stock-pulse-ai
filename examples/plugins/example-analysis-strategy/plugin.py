# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic analysis-strategy plugin for authoring and tests.

Registers a real ``Skill`` definition. Prefer YAML / ``SKILL.md`` under
``AGENT_SKILL_DIR`` when trusted process code is not required.
"""

from __future__ import annotations

from src.agent.skills.base import Skill
from src.plugins import Plugin as BasePlugin
from src.plugins import PluginContext


STRATEGY_NAME = "example-quality-compounder"


class Plugin(BasePlugin):
    """Publish one declarative strategy definition on each enable transition."""

    def onload(self, context: PluginContext) -> None:
        definition = Skill(
            name=STRATEGY_NAME,
            display_name="Example Quality Compounder",
            description=(
                "Evaluate durable quality and compounding evidence "
                "(plugin authoring sample)."
            ),
            instructions=(
                "Require durable cash generation, defensible returns on capital, "
                "and an explicit valuation and downside-risk check. "
                "This is a teaching definition only."
            ),
            category="framework",
            required_tools=["get_daily_history"],
            default_active=False,
            default_router=False,
        )
        context.register(
            "analysis_strategy",
            definition.name,
            definition,
            contract_version="1",
        )

    def onunload(self) -> None:
        """Release plugin-owned resources; registration cleanup is manager-owned."""
