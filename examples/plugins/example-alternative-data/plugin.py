# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Default-off reference alternative-data plugin (corporate events).

Registers a deterministic, network-free corporate-events ToolDefinition through
the frozen ``agent_tool`` extension point. Aligns with:

- plugin manifest permissions (#944): declares ``alt_data:read``;
- OpenBB-style thin adapter discipline (#892 family): default-off, no heavy
  deps, fail loudly rather than invent values;
- ToolSurface deny-by-default for undeclared capabilities (#1144).

Not part of the default plugin load set. Point ``PLUGINS_DIR`` at
``examples/plugins`` (parent) only after review. Live agent invocation through
a hardened sandbox remains gated by issue #539; this package proves load,
permission declaration, ToolSurface deny, and governance projection contracts.
"""

from __future__ import annotations

from typing import Literal

from src.agent.tools.alternative_data_tools import build_corporate_events_tool
from src.plugins import Plugin as BasePlugin
from src.plugins import PluginContext
from src.schemas.alternative_data import (
    ALT_DATA_DISCLAIMER,
    AlternativeDataCitation,
    AlternativeDataCoverage,
    AlternativeDataObservation,
    CorporateEventItem,
)

PLUGIN_ID = "stockpulse.example-alternative-data"
TOOL_NAME = "get_corporate_events_brief"


class FixtureCorporateEventsProvider:
    """Deterministic fixture provider (no network, no secrets)."""

    is_configured = True

    def get_events(
        self,
        *,
        stock_code: str,
        window_days: int,
        language_hint: Literal["zh", "en"],
    ) -> AlternativeDataObservation | None:
        del window_days
        code = str(stock_code or "").strip()
        if not code:
            return None
        if language_hint == "zh":
            summary = (
                f"{code} 在参考窗口内出现 1 条非权威公司事件（示例插件固定夹具）。"
            )
            title = "示例：股东大会通知"
            basis = "固定示例源，非权威；不得单独支撑核心结论。"
        else:
            summary = (
                f"{code} has 1 non-authoritative corporate event in the "
                "reference window (deterministic plugin fixture)."
            )
            title = "Example: shareholder meeting notice"
            basis = "Fixture source only; non-authoritative supporting evidence."
        return AlternativeDataObservation(
            category="corporate_events",
            stock_code=code,
            language=language_hint,
            as_of="2026-08-01T00:00:00Z",
            summary=summary,
            confidence=0.55,
            confidence_basis=basis,
            events=(
                CorporateEventItem(
                    event_id="fixture-agm-001",
                    event_type="shareholder_meeting",
                    title=title,
                    event_date="2026-08-15",
                    impact_hint="neutral",
                    source_id="fixture_events",
                    confidence=0.55,
                ),
            ),
            coverage=(
                AlternativeDataCoverage(
                    source_id="fixture_events",
                    status="available",
                    as_of="2026-08-01T00:00:00Z",
                ),
            ),
            citations=(
                AlternativeDataCitation(
                    source_id="fixture_events",
                    reference_id="fixture-agm-001",
                    url=None,
                ),
            ),
            gaps=(),
            authority="non_authoritative",
            role="supporting_only",
            disclaimer=ALT_DATA_DISCLAIMER,
        )


class Plugin(BasePlugin):
    """Register the corporate-events alt-data tool on each enable transition."""

    def onload(self, context: PluginContext) -> None:
        tool = build_corporate_events_tool(FixtureCorporateEventsProvider())
        context.register(
            "agent_tool",
            tool.name,
            tool,
            contract_version="1",
        )

    def onunload(self) -> None:
        """Release plugin-owned resources; registration cleanup is manager-owned."""
