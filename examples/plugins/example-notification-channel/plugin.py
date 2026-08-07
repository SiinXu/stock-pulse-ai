# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic log-sink notification plugin (surface v1 reference).

Imports only the frozen author-facing names from ``src.plugins`` declared by
``PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS`` (ADR-007 surface freeze).
"""

from __future__ import annotations

import logging

from src.plugins import (
    NotificationAdapterResult,
    NotificationRequest,
    Plugin as BasePlugin,
    PluginContext,
)


logger = logging.getLogger(__name__)


class ExampleLogNotificationAdapter:
    """Deliver non-sensitive attempt metadata to the application log."""

    channel_id = "example_log"
    display_name = "Example Log Sink"

    def __init__(self, config: object) -> None:
        del config

    def is_available(self) -> bool:
        return True

    def send(self, request: NotificationRequest) -> NotificationAdapterResult:
        logger.info(
            "Example notification delivered channel=%s route=%s "
            "content_length=%d stock_count=%d has_image=%s",
            self.channel_id,
            request.route_type or "default",
            len(request.content),
            len(request.stock_codes),
            request.image_bytes is not None,
        )
        return NotificationAdapterResult(success=True)


class Plugin(BasePlugin):
    """Register the example adapter for each enabled lifecycle transition."""

    def onload(self, context: PluginContext) -> None:
        context.register(
            "notification_channel",
            ExampleLogNotificationAdapter.channel_id,
            ExampleLogNotificationAdapter,
            contract_version="1",
        )

    def onunload(self) -> None:
        """Release plugin-owned resources; registration cleanup is manager-owned."""
