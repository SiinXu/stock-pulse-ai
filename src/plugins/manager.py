# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Central plugin registration and lifecycle state management."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Iterable, Literal

from src.utils.sanitize import log_safe_exception

from .errors import PluginError
from .manifest import API_MAJOR_PATTERN, PluginManifest, parse_semver
from .plugin import Plugin
from .registry import ExtensionPoint, ExtensionRegistration, ExtensionRegistry, PluginContext, RegistrationHandle


logger = logging.getLogger(__name__)

PluginSource = Literal["builtin", "external"]
PluginState = Literal["registered", "enabled", "disabled", "failed"]


@dataclass(frozen=True, slots=True)
class PluginOperationResult:
    """Stable result for one lifecycle or registration operation."""

    plugin_id: str
    operation: str
    success: bool
    state: PluginState
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class PluginSnapshot:
    """Read-only manager state for diagnostics and later composition wiring."""

    manifest: PluginManifest
    source: PluginSource
    state: PluginState


@dataclass(slots=True)
class _ManagedPlugin:
    plugin: Plugin
    manifest: PluginManifest
    source: PluginSource
    state: PluginState = "registered"
    handles: list[RegistrationHandle] = field(default_factory=list)
    transition: str | None = None
    cleanup_pending: bool = False


class PluginManager:
    """Own plugin compatibility, state transitions, and reverse cleanup."""

    def __init__(
        self,
        *,
        application_version: str,
        supported_api_versions: Iterable[str] = ("1",),
        registry: ExtensionRegistry | None = None,
    ) -> None:
        self._application_version = parse_semver(application_version)
        if isinstance(supported_api_versions, str):
            supported = frozenset({supported_api_versions})
        else:
            supported = frozenset(supported_api_versions)
        if not supported or any(
            type(version) is not str or API_MAJOR_PATTERN.fullmatch(version) is None
            for version in supported
        ):
            raise ValueError("supported plugin API versions must be positive majors")
        self._supported_api_versions = supported
        self._registry = registry or ExtensionRegistry()
        self._plugins: dict[str, _ManagedPlugin] = {}
        self._lock = threading.RLock()

    @property
    def registry(self) -> ExtensionRegistry:
        """Return the manager-owned unified extension registry."""

        return self._registry

    def compatibility_error(self, manifest: PluginManifest) -> str | None:
        """Return a stable compatibility code without importing plugin code."""

        if not isinstance(manifest, PluginManifest):
            return "plugin_manifest_invalid"
        if parse_semver(manifest.min_app_version) > self._application_version:
            return "plugin_app_version_unsupported"
        if manifest.api_version not in self._supported_api_versions:
            return "plugin_api_version_unsupported"
        return None

    def register(
        self,
        plugin: Plugin,
        *,
        source: PluginSource,
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

    def snapshot(self, plugin_id: str) -> PluginSnapshot | None:
        """Return one immutable plugin state snapshot."""

        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is None:
                return None
            return PluginSnapshot(
                manifest=record.manifest,
                source=record.source,
                state=record.state,
            )

    def plugin_ids(self) -> tuple[str, ...]:
        """Return plugin IDs in registration order."""

        with self._lock:
            return tuple(self._plugins)

    def registrations(
        self,
        extension_point: ExtensionPoint | None = None,
    ) -> tuple[ExtensionRegistration, ...]:
        """Return the active extension snapshot from the unified registry."""

        return self._registry.registrations(extension_point)

    def load(self, plugin_id: str) -> PluginOperationResult:
        """Perform the first ``registered -> enabled`` transition."""

        return self._enable(plugin_id, operation="load", required_state="registered")

    def enable(self, plugin_id: str) -> PluginOperationResult:
        """Perform ``disabled -> enabled`` and remain idempotent when enabled."""

        return self._enable(plugin_id, operation="enable", required_state="disabled")

    def _enable(
        self,
        plugin_id: str,
        *,
        operation: str,
        required_state: PluginState,
    ) -> PluginOperationResult:
        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is None:
                return self._not_found(plugin_id, operation)
            if record.transition is not None:
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation=operation,
                    success=False,
                    state=record.state,
                    error_code="plugin_transition_in_progress",
                )
            if record.state == "enabled":
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation=operation,
                    success=True,
                    state="enabled",
                )
            if record.state != required_state:
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation=operation,
                    success=False,
                    state=record.state,
                    error_code="plugin_invalid_state",
                )

            record.transition = operation
            context = PluginContext(plugin_id, self._registry)
            load_error_code: str | None = None
            try:
                record.plugin.onload(context)
            except Exception as exc:  # broad-exception: fallback_recorded - A plugin load failure is safely logged before partial registrations are removed.
                load_error_code = (
                    exc.error_code
                    if isinstance(exc, PluginError)
                    else "plugin_onload_failed"
                )
                log_safe_exception(
                    logger,
                    "Plugin onload callback failed",
                    exc,
                    error_code=load_error_code,
                    context={"plugin_id": plugin_id, "operation": operation},
                )
            finally:
                context.close()

            if load_error_code is None:
                load_error_code = context.recovery_error_code

            if load_error_code is not None:
                remaining, cleanup_errors = self._cleanup_handles(
                    plugin_id,
                    context.handles,
                )
                record.handles = list(remaining)
                record.cleanup_pending = bool(remaining)
                record.state = "failed"
                record.transition = None
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation=operation,
                    success=False,
                    state="failed",
                    error_code=(
                        cleanup_errors[0]
                        if cleanup_errors
                        else load_error_code
                    ),
                )

            record.handles = list(context.handles)
            record.cleanup_pending = False
            record.state = "enabled"
            record.transition = None
            return PluginOperationResult(
                plugin_id=plugin_id,
                operation=operation,
                success=True,
                state="enabled",
            )

    def disable(self, plugin_id: str) -> PluginOperationResult:
        """Unload an enabled plugin or converge a failed plugin after cleanup."""

        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is None:
                return self._not_found(plugin_id, "disable")
            if record.transition is not None:
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation="disable",
                    success=False,
                    state=record.state,
                    error_code="plugin_transition_in_progress",
                )
            if record.state == "disabled":
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation="disable",
                    success=True,
                    state="disabled",
                )
            if record.state == "failed":
                record.transition = "disable"
                remaining, cleanup_errors = self._cleanup_handles(
                    plugin_id,
                    tuple(record.handles),
                )
                record.handles = list(remaining)
                record.cleanup_pending = bool(remaining)
                record.state = "failed" if remaining else "disabled"
                record.transition = None
                cleanup_error = cleanup_errors[0] if cleanup_errors else None
                if cleanup_error is None and remaining:
                    cleanup_error = "plugin_registration_cleanup_failed"
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation="disable",
                    success=not cleanup_errors and not remaining,
                    state=record.state,
                    error_code=cleanup_error,
                )
            if record.state != "enabled":
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation="disable",
                    success=False,
                    state=record.state,
                    error_code="plugin_invalid_state",
                )

            record.transition = "disable"
            unload_failed = False
            try:
                record.plugin.onunload()
            except Exception as exc:  # broad-exception: fallback_recorded - A plugin unload failure is safely logged while manager-owned cleanup still runs.
                unload_failed = True
                log_safe_exception(
                    logger,
                    "Plugin onunload callback failed",
                    exc,
                    error_code="plugin_onunload_failed",
                    context={"plugin_id": plugin_id},
                )

            remaining, cleanup_errors = self._cleanup_handles(
                plugin_id,
                tuple(record.handles),
            )
            record.handles = list(remaining)
            record.cleanup_pending = bool(remaining)
            record.state = "failed" if remaining else "disabled"
            record.transition = None
            if cleanup_errors or remaining:
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation="disable",
                    success=False,
                    state=record.state,
                    error_code=(
                        cleanup_errors[0]
                        if cleanup_errors
                        else "plugin_registration_cleanup_failed"
                    ),
                )
            return PluginOperationResult(
                plugin_id=plugin_id,
                operation="disable",
                success=not unload_failed,
                state="disabled",
                error_code="plugin_onunload_failed" if unload_failed else None,
            )

    def load_all(self, plugin_ids: Iterable[str] | None = None) -> tuple[PluginOperationResult, ...]:
        """Load a snapshot of plugins, continuing after every isolated failure."""

        selected = self.plugin_ids() if plugin_ids is None else tuple(plugin_ids)
        return tuple(self.load(plugin_id) for plugin_id in selected)

    def disable_all(self, plugin_ids: Iterable[str] | None = None) -> tuple[PluginOperationResult, ...]:
        """Disable a reverse-order snapshot, continuing after every failure."""

        selected = self.plugin_ids() if plugin_ids is None else tuple(plugin_ids)
        return tuple(self.disable(plugin_id) for plugin_id in reversed(selected))

    def _cleanup_handles(
        self,
        plugin_id: str,
        handles: tuple[RegistrationHandle, ...],
    ) -> tuple[tuple[RegistrationHandle, ...], tuple[str, ...]]:
        remaining: list[RegistrationHandle] = []
        error_codes: list[str] = []
        for handle in reversed(handles):
            try:
                handle.unregister()
            except PluginError as exc:
                error_codes.append(exc.error_code)
            except Exception as exc:  # broad-exception: fallback_recorded - Unexpected cleanup failures are safely logged while later handles still run.
                error_codes.append("plugin_registration_cleanup_failed")
                log_safe_exception(
                    logger,
                    "Plugin registration cleanup failed",
                    exc,
                    error_code="plugin_registration_cleanup_failed",
                    context={
                        "plugin_id": plugin_id,
                        "extension_point": handle.extension_point,
                    },
                )
            if handle.active:
                remaining.append(handle)
        remaining.reverse()
        return tuple(remaining), tuple(error_codes)

    @staticmethod
    def _not_found(plugin_id: str, operation: str) -> PluginOperationResult:
        return PluginOperationResult(
            plugin_id=plugin_id,
            operation=operation,
            success=False,
            state="failed",
            error_code="plugin_not_found",
        )
