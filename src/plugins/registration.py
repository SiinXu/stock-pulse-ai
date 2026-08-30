# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Plugin occupancy register/contains extracted from PluginManager."""

from __future__ import annotations

import logging
from pathlib import Path

from src.utils.sanitize import log_safe_exception

from .manifest import PluginManifest
from .manager_types import PluginOperationResult, PluginSource, _ManagedPlugin
from .plugin import Plugin


logger = logging.getLogger("src.plugins.manager")


class PluginRegistrationMixin:
    """Record occupancy without invoking plugin ``onload``."""

    def register(
        self,
        plugin: Plugin,
        *,
        source: PluginSource,
        package_root: str | Path | None = None,
        module_name: str | None = None,
    ) -> PluginOperationResult:
        """Record a compatible plugin without invoking ``onload``."""

        if type(source) is not str or source not in {"builtin", "external"}:
            return PluginOperationResult(
                plugin_id="unknown",
                operation="register",
                success=False,
                state="failed",
                error_code="plugin_source_invalid",
            )
        if not isinstance(plugin, Plugin):
            return PluginOperationResult(
                plugin_id="unknown",
                operation="register",
                success=False,
                state="failed",
                error_code="plugin_type_invalid",
            )
        try:
            manifest = plugin.manifest
        except Exception as exc:  # broad-exception: fallback_recorded - Manifest access failure is safely logged and rejected before registration.
            log_safe_exception(
                logger,
                "Plugin manifest access failed",
                exc,
                error_code="plugin_manifest_invalid",
            )
            return PluginOperationResult(
                plugin_id="unknown",
                operation="register",
                success=False,
                state="failed",
                error_code="plugin_manifest_invalid",
            )
        if not isinstance(manifest, PluginManifest):
            return PluginOperationResult(
                plugin_id="unknown",
                operation="register",
                success=False,
                state="failed",
                error_code="plugin_manifest_invalid",
            )
        compatibility_error = self.compatibility_error(manifest)
        if compatibility_error is not None:
            return PluginOperationResult(
                plugin_id=manifest.id,
                operation="register",
                success=False,
                state="failed",
                error_code=compatibility_error,
            )

        resolved_root: Path | None = None
        if package_root is not None:
            try:
                resolved_root = Path(package_root).expanduser().resolve()
            except (OSError, RuntimeError):
                resolved_root = Path(package_root).expanduser()
        resolved_module = module_name if type(module_name) is str and module_name else None

        with self._lock:
            existing = self._plugins.get(manifest.id)
            if existing is not None:
                return PluginOperationResult(
                    plugin_id=manifest.id,
                    operation="register",
                    success=False,
                    state=existing.state,
                    error_code="plugin_id_conflict",
                )
            self._plugins[manifest.id] = _ManagedPlugin(
                plugin=plugin,
                manifest=manifest,
                source=source,
                package_root=resolved_root,
                module_name=resolved_module,
            )
            self._lifecycle_generation += 1
        logger.info(
            "Plugin registered id=%s version=%s source=%s permissions=%s",
            manifest.id,
            manifest.version,
            source,
            list(manifest.permissions),
        )
        return PluginOperationResult(
            plugin_id=manifest.id,
            operation="register",
            success=True,
            state="registered",
        )

    def contains(self, plugin_id: str) -> bool:
        """Return whether a plugin ID is already registered."""

        with self._lock:
            return plugin_id in self._plugins
