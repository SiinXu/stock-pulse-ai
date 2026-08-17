# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Compatibility and load-time permission decisions for PluginManager."""

from __future__ import annotations

from typing import Iterable

from .agent_tools import agent_tool_manifest_permissions_error
from .manifest import PluginManifest, parse_semver
from .registry import ExtensionRegistration


def compatibility_error(
    manifest: object,
    application_version: tuple[int, int, int],
    supported_api_versions: Iterable[str],
) -> str | None:
    """Return a stable compatibility code without importing plugin code."""

    if not isinstance(manifest, PluginManifest):
        return "plugin_manifest_invalid"
    if parse_semver(manifest.min_app_version) > application_version:
        return "plugin_app_version_unsupported"
    if manifest.api_version not in supported_api_versions:
        return "plugin_api_version_unsupported"
    return None


def load_time_permission_error(
    *,
    manifest: PluginManifest,
    registrations: tuple[ExtensionRegistration, ...],
) -> str | None:
    """Return the load-time permission code, or ``None`` when the plugin may enable."""

    return agent_tool_manifest_permissions_error(
        manifest=manifest,
        registrations=registrations,
    )
