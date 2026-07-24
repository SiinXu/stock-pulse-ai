# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Built-in lifecycle wrapper for the optional Kronos Agent Tool."""

from __future__ import annotations

from typing import Any, Callable

from src.agent.tools.kronos_tools import build_kronos_tool
from src.plugins.constants import PLUGIN_APPLICATION_VERSION
from src.plugins.manifest import PluginManifest
from src.plugins.plugin import Plugin
from src.plugins.registry import PluginContext


class KronosAgentToolPlugin(Plugin):
    """Register Kronos only after all local readiness gates succeed."""

    def __init__(
        self,
        config: Any,
        *,
        dependency_probe: Callable[[str], bool] | None = None,
        service_factory: Callable | None = None,
    ) -> None:
        super().__init__(
            PluginManifest.model_validate(
                {
                    "id": "builtin.kronos",
                    "name": "Kronos K-line Forecasting",
                    "version": "1.0.0",
                    "minAppVersion": PLUGIN_APPLICATION_VERSION,
                    "description": (
                        "Optional local Kronos time-series forecasting Agent Tool."
                    ),
                    "author": "StockPulse contributors",
                    "permissions": ["market-data.read", "local-model.execute"],
                }
            )
        )
        self._config = config
        self._dependency_probe = dependency_probe
        self._service_factory = service_factory
        self._tool = None

    def onload(self, context: PluginContext) -> None:
        kwargs = {}
        if self._dependency_probe is not None:
            kwargs["dependency_probe"] = self._dependency_probe
        if self._service_factory is not None:
            kwargs["service_factory"] = self._service_factory
        tool = build_kronos_tool(self._config, **kwargs)
        if tool is None:
            return
        context.register(
            "agent_tool",
            tool.name,
            tool,
            metadata={
                "builtin": True,
                "model_family": "Kronos",
                "local_only": True,
            },
        )
        self._tool = tool

    def onunload(self) -> None:
        self._tool = None
