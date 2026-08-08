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


logger = logging.getLogger(__name__)


def get_configured_builtin_plugins(config: Any = None) -> tuple:
    """Return the default built-in plugin catalog for ApplicationServices.

    Built-in analysis strategies are always included (YAML content under
    ``strategies/``, packaged as first-class ``analysis_strategy`` plugins).
    Optional tools such as Kronos remain configuration-gated.
    """

    plugins: list[Any] = list(get_builtin_analysis_strategy_plugins())

    if config is None:
        kronos_enabled = parse_env_bool(os.getenv("KRONOS_ENABLED"), default=False)
    else:
        kronos_enabled = getattr(config, "kronos_enabled", False) is True
    if not kronos_enabled:
        logger.debug(
            "Kronos built-in plugin is disabled; set KRONOS_ENABLED=true to opt in"
        )
        return tuple(plugins)

    if config is None:
        from src.config import get_config

        config = get_config()
    plugins.append(KronosAgentToolPlugin(config))
    return tuple(plugins)


__all__ = [
    "BuiltinAnalysisStrategyPlugin",
    "KronosAgentToolPlugin",
    "builtin_analysis_strategy_plugin_id",
    "get_builtin_analysis_strategy_plugins",
    "get_configured_builtin_plugins",
    "is_builtin_analysis_strategy_plugin_id",
    "list_builtin_analysis_strategy_names",
]
