# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Default process composition for executable plugin extension points."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from src.agent.tools.registry import ToolRegistry

from .agent_tools import build_agent_tool_extension_contract
from .registry import (
    ExtensionContract,
    ExtensionPoint,
    ExtensionRegistry,
    default_extension_contracts,
)


def build_application_extension_registry(
    agent_tool_registry: ToolRegistry | Callable[[], ToolRegistry],
    *,
    additional_contracts: Mapping[ExtensionPoint, ExtensionContract] | None = None,
) -> ExtensionRegistry:
    """Build one process registry from the Agent Tool and explicit point seams."""

    contracts = dict(default_extension_contracts())
    if additional_contracts is not None:
        contracts.update(additional_contracts)
    contracts["agent_tool"] = build_agent_tool_extension_contract(
        agent_tool_registry
    )
    return ExtensionRegistry(contracts)
