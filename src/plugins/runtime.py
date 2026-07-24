# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Default process bindings for executable plugin extension points."""

from __future__ import annotations

from collections.abc import Callable

from src.agent.tools.registry import ToolRegistry

from .agent_tools import build_agent_tool_extension_contract
from .notification_channels import (
    NotificationChannelRegistry,
    build_notification_channel_extension_contract,
)
from .registry import ExtensionRegistry, default_extension_contracts


def build_application_extension_registry(
    agent_tool_registry: ToolRegistry | Callable[[], ToolRegistry],
    notification_channel_registry: NotificationChannelRegistry,
) -> ExtensionRegistry:
    """Build the default process registry with both executable native seams."""

    contracts = dict(default_extension_contracts())
    contracts["agent_tool"] = build_agent_tool_extension_contract(
        agent_tool_registry
    )
    contracts["notification_channel"] = (
        build_notification_channel_extension_contract(
            notification_channel_registry
        )
    )
    return ExtensionRegistry(contracts)
