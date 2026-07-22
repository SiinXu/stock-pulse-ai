# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Base lifecycle contract for StockPulse plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .manifest import PluginManifest

if TYPE_CHECKING:
    from .registry import PluginContext


class Plugin:
    """Base plugin with one load and unload callback per enable transition."""

    def __init__(self, manifest: PluginManifest) -> None:
        if not isinstance(manifest, PluginManifest):
            raise TypeError("manifest must be a PluginManifest")
        self._manifest = manifest

    @property
    def manifest(self) -> PluginManifest:
        """Return the validated immutable manifest."""

        return self._manifest

    def onload(self, context: "PluginContext") -> None:
        """Register extension implementations for one enable transition."""

    def onunload(self) -> None:
        """Release plugin-owned resources for one disable transition."""
