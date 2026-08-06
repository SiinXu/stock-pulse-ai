# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Frozen plugin extension surface v1 (ADR-007).

External plugin authors may rely only on the extension points and package-root
exports declared here. Unlisted modules, helpers, and composition wiring under
``src.plugins`` are internal and may change without a surface major bump.

Adding, renaming, or removing an official extension point requires a new ADR
(or an explicit amendment of ADR-007) and a surface major bump. See
``docs/plugin-extension-contract.md`` for the living contract text.
"""

from __future__ import annotations

from typing import Final

# Surface major for the six ADR-007 extension points. Bump only with a new ADR.
PLUGIN_EXTENSION_SURFACE_VERSION: Final[int] = 1

# Canonical ordered identity of the frozen v1 points (stable for diagnostics).
PLUGIN_EXTENSION_SURFACE_V1_POINT_ORDER: Final[tuple[str, ...]] = (
    "data_provider",
    "analysis_strategy",
    "agent_tool",
    "notification_channel",
    "report_template",
    "event_hook",
)

PLUGIN_EXTENSION_SURFACE_V1_POINTS: Final[frozenset[str]] = frozenset(
    PLUGIN_EXTENSION_SURFACE_V1_POINT_ORDER
)

# Names external plugins may import from the ``src.plugins`` package root under
# surface v1. Host-only composition helpers (managers, loaders, native backends,
# dispatch wiring) are intentionally excluded so authors do not couple to them.
PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS: Final[frozenset[str]] = frozenset(
    {
        "PLUGIN_APPLICATION_VERSION",
        "PLUGIN_EXTENSION_SURFACE_VERSION",
        "PLUGIN_EXTENSION_SURFACE_V1_POINT_ORDER",
        "PLUGIN_EXTENSION_SURFACE_V1_POINTS",
        "PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS",
        "Plugin",
        "PluginContext",
        "PluginManifest",
        "PluginError",
        "PluginRegistryError",
        "PluginContextClosedError",
        "RegistrationHandle",
        "EXTENSION_POINTS",
        "ExtensionPoint",
        "AnalysisStrategyDefinition",
        "NotificationRequest",
        "NotificationAdapterResult",
        "NotificationChannelAdapter",
        "NotificationChannelFactory",
        "ReportTemplate",
        "ReportRenderRequest",
        "ReportPlatform",
        "SUPPORTED_REPORT_PLATFORMS",
        "EventHook",
        "EventHookRegistration",
        "PluginEvent",
        "EVENT_HOOK_NAMES",
        "EVENT_HOOK_SCHEMA_VERSION",
    }
)
