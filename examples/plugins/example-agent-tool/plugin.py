# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Load-and-register Agent Tool plugin for authoring and contract tests.

``ToolDefinition`` remains ToolSurface-owned and is imported from
``src.agent.tools.registry``. Live agent invocation through a hardened
ToolSurface sandbox is gated by issue #539; this package only proves that a
valid definition can load and register on the process ``ToolRegistry``.
"""

from __future__ import annotations

from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy
from src.plugins import Plugin as BasePlugin
from src.plugins import PluginContext


TOOL_NAME = "example_echo"


def example_echo(message: str) -> dict[str, str]:
    """Return a deterministic echo payload without network or process I/O."""

    return {"echo": message}


class Plugin(BasePlugin):
    """Register a read-only echo tool on each enable transition."""

    def onload(self, context: PluginContext) -> None:
        tool = ToolDefinition(
            name=TOOL_NAME,
            description=(
                "Echo a short message. Official plugin authoring sample; "
                "not intended for production agent runs."
            ),
            parameters=[
                ToolParameter(
                    name="message",
                    type="string",
                    description="Text to echo back unchanged",
                )
            ],
            handler=example_echo,
            category="data",
            policy=ToolPolicy.declared(
                read_only=True,
                side_effects=[],
                permissions=[],
                scope_dimensions=[],
            ),
            enforce_contract=True,
        )
        context.register(
            "agent_tool",
            tool.name,
            tool,
            contract_version="1",
        )

    def onunload(self) -> None:
        """Release plugin-owned resources; registration cleanup is manager-owned."""
