# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic observational event-hook plugin for authoring and tests.

Imports only frozen author-facing names from ``src.plugins`` for the
``event_hook`` extension point (ADR-007 surface freeze).
"""

from __future__ import annotations

import logging

from src.plugins import (
    EventHookRegistration,
    Plugin as BasePlugin,
    PluginContext,
    PluginEvent,
)


logger = logging.getLogger(__name__)

HOOK_ID = "example-analysis-lifecycle"
EVENT_NAMES = frozenset(
    {
        "analysis.started",
        "analysis.completed",
        "analysis.failed",
    }
)


def on_analysis_lifecycle(event: PluginEvent) -> None:
    """Log non-sensitive lifecycle metadata; never raise into the analysis path."""

    payload = event.payload
    logger.info(
        "Example event hook received name=%s task_id=%s stock_code=%s "
        "trace_id=%s keys=%s",
        event.name,
        payload.get("task_id"),
        payload.get("stock_code"),
        event.trace_id,
        sorted(payload.keys()),
    )


class Plugin(BasePlugin):
    """Register the observational analysis lifecycle hook."""

    def onload(self, context: PluginContext) -> None:
        registration = EventHookRegistration(
            hook_id=HOOK_ID,
            event_names=EVENT_NAMES,
            callback=on_analysis_lifecycle,
        )
        context.register(
            "event_hook",
            registration.hook_id,
            registration,
            contract_version="1",
        )

    def onunload(self) -> None:
        """Release plugin-owned resources; registration cleanup is manager-owned."""
