# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Built-in plugin catalog resolved at application-root construction."""

from __future__ import annotations

import logging
import os
from typing import Any

from src.config_parts.parsers import parse_env_bool

from .analysis_strategies import (
    BuiltinAnalysisStrategyPlugin,
    builtin_analysis_strategy_plugin_id,
    get_builtin_analysis_strategy_plugins,
    is_builtin_analysis_strategy_plugin_id,
    list_builtin_analysis_strategy_names,
)
from .kronos import KronosAgentToolPlugin
from .ocr import OcrAgentToolPlugin


logger = logging.getLogger(__name__)


def get_configured_builtin_plugins(config: Any = None) -> tuple:
    """Return the default built-in plugin catalog for ApplicationServices.

    Built-in analysis strategies are always included (YAML content under
    ``strategies/``, packaged as first-class ``analysis_strategy`` plugins).
    Optional tools such as Kronos and OCR remain configuration-gated.
    """

    plugins: list[Any] = list(get_builtin_analysis_strategy_plugins())

    if config is None:
        kronos_enabled = parse_env_bool(os.getenv("KRONOS_ENABLED"), default=False)
        ocr_enabled = parse_env_bool(
            os.getenv("OCR_AGENT_TOOL_ENABLED"), default=False
        )
    else:
        kronos_enabled = getattr(config, "kronos_enabled", False) is True
        ocr_enabled = getattr(config, "ocr_agent_tool_enabled", False) is True

    if config is None and (kronos_enabled or ocr_enabled):
        from src.config import get_config

        config = get_config()

    if kronos_enabled:
        plugins.append(KronosAgentToolPlugin(config))
    else:
        logger.debug(
            "Kronos built-in plugin is disabled; set KRONOS_ENABLED=true to opt in"
        )

    if ocr_enabled:
        plugins.append(OcrAgentToolPlugin(config))
    else:
        logger.debug(
            "OCR built-in plugin is disabled; set OCR_AGENT_TOOL_ENABLED=true to opt in"
        )

    return tuple(plugins)


__all__ = [
    "BuiltinAnalysisStrategyPlugin",
    "KronosAgentToolPlugin",
    "OcrAgentToolPlugin",
    "builtin_analysis_strategy_plugin_id",
    "get_builtin_analysis_strategy_plugins",
    "get_configured_builtin_plugins",
    "is_builtin_analysis_strategy_plugin_id",
    "list_builtin_analysis_strategy_names",
]
