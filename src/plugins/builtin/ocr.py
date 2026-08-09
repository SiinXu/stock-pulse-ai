# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Built-in lifecycle wrapper for the optional offline OCR Agent Tool."""

from __future__ import annotations

from typing import Any, Callable

from src.agent.tools.ocr_tools import build_ocr_tool
from src.plugins.constants import PLUGIN_APPLICATION_VERSION
from src.plugins.manifest import PluginManifest
from src.plugins.plugin import Plugin
from src.plugins.registry import PluginContext


class OcrAgentToolPlugin(Plugin):
    """Register local OCR only after opt-in configuration and readiness gates."""

    def __init__(
        self,
        config: Any,
        *,
        dependency_probe: Callable[[str], bool] | None = None,
        service_factory: Callable | None = None,
        require_engine_at_register: bool = True,
    ) -> None:
        super().__init__(
            PluginManifest.model_validate(
                {
                    "id": "builtin.ocr",
                    "name": "Offline Image OCR",
                    "version": "1.0.0",
                    "minAppVersion": PLUGIN_APPLICATION_VERSION,
                    "description": (
                        "Optional bounded Tesseract OCR Agent Tool that returns "
                        "redacted, untrusted document text (issue #196)."
                    ),
                    "author": "StockPulse contributors",
                    "permissions": ["multimodal:read"],
                }
            )
        )
        self._config = config
        self._dependency_probe = dependency_probe
        self._service_factory = service_factory
        self._require_engine_at_register = require_engine_at_register
        self._tool = None

    def onload(self, context: PluginContext) -> None:
        kwargs: dict[str, Any] = {
            "require_engine_at_register": self._require_engine_at_register,
        }
        if self._dependency_probe is not None:
            kwargs["dependency_probe"] = self._dependency_probe
        if self._service_factory is not None:
            kwargs["service_factory"] = self._service_factory
        tool = build_ocr_tool(self._config, **kwargs)
        if tool is None:
            return
        context.register(
            "agent_tool",
            tool.name,
            tool,
            metadata={
                "builtin": True,
                "image_bytes_local": True,
                "result_egress": "redacted_tool_context",
                "zero_remote_egress_requires": "LOCAL_ONLY_MODE=true",
                "capability": "ocr",
            },
        )
        self._tool = tool

    def onunload(self) -> None:
        self._tool = None
