# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Built-in plugin catalog resolved at application-root construction."""

from __future__ import annotations

import logging
import os
from typing import Any

from src.config_parts.parsers import parse_env_bool

from .kronos import KronosAgentToolPlugin


logger = logging.getLogger(__name__)


def get_configured_builtin_plugins(config: Any = None) -> tuple:
    """Return only explicitly enabled built-ins without resolving Config eagerly."""

    if config is None:
        enabled = parse_env_bool(os.getenv("KRONOS_ENABLED"), default=False)
    else:
        enabled = getattr(config, "kronos_enabled", False) is True
    if not enabled:
        logger.debug(
            "Kronos built-in plugin is disabled; set KRONOS_ENABLED=true to opt in"
        )
        return ()

    if config is None:
        from src.config import get_config

        config = get_config()
    return (KronosAgentToolPlugin(config),)


__all__ = ["KronosAgentToolPlugin", "get_configured_builtin_plugins"]
