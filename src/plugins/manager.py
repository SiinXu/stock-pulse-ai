# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Central plugin registration and lifecycle state management."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable, Iterable

from src.utils.sanitize import log_safe_exception

from .health import PluginHealthReport, build_plugin_health_report
from .lifecycle import PluginLifecycleMixin
from .lifecycle_audit import LifecycleAuditRecorder, PluginLifecycleAuditor
from .settings_query import PluginSettingsQueryMixin
from .settings_update import PluginSettingsUpdateMixin
from .snapshot import PluginSnapshotMixin
from .manifest import (
    API_MAJOR_PATTERN,
    PluginManifest,
    parse_semver,
)
from .manager_types import (
    PluginLifecycleAuditCompletionUnavailable,
    PluginOperationResult,
    PluginReloadResult,
    PluginSettingsUpdateResult,
    PluginSettingsValidationError,
    PluginSnapshot,
    PluginSource,
    PluginState,
    _ManagedPlugin,
)
from .permissions import compatibility_error as permission_compatibility_error
from .plugin import Plugin
from .registry import ExtensionPoint, ExtensionRegistration, ExtensionRegistry
from .state_store import PluginLifecycleStateStore
from .settings_store import PluginSettingsStore


logger = logging.getLogger(__name__)

__all__ = (
    "PluginLifecycleAuditCompletionUnavailable",
    "PluginManager",
    "PluginOperationResult",
    "PluginReloadResult",
    "PluginSettingsUpdateResult",
    "PluginSettingsValidationError",
    "PluginSnapshot",
    "PluginSource",
    "PluginState",
)


class PluginManager(
    PluginSettingsUpdateMixin,
    PluginSettingsQueryMixin,
    PluginSnapshotMixin,
    PluginLifecycleMixin,
):
    """Own plugin compatibility, state transitions, and reverse cleanup."""

    def __init__(
        self,
        *,
        application_version: str,
        supported_api_versions: Iterable[str] = ("1",),
        registry: ExtensionRegistry | None = None,
        state_store: PluginLifecycleStateStore | None = None,
        settings_store: PluginSettingsStore | None = None,
        audit: LifecycleAuditRecorder | None = None,
        audit_enabled: bool = True,
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
        self._stable_enabled_plugin_ids: frozenset[str] = frozenset()
        # Monotonic counter advanced by every lifecycle write (record add or
        # removal, observed state transition, operator-intent write). Extension
        # registration generations alone cannot represent these transitions.
        self._lifecycle_generation = 0
        self._lock = threading.RLock()
        self._lifecycle_boundary: (
            Callable[[Callable[[], Any]], Any] | None
        ) = None
        self._activation_allowed: Callable[[], bool] | None = None
        self._disable_boundary: (
            Callable[
                [str, Callable[[], PluginOperationResult]],
                PluginOperationResult,
            ]
            | None
        ) = None
        self._lifecycle_boundary_state = threading.local()
        self._state_store = (
            state_store if state_store is not None else PluginLifecycleStateStore.from_env()
        )
        self._settings_store = (
            settings_store
            if settings_store is not None
            else PluginSettingsStore.beside_lifecycle_state(self._state_store.path)
        )
        # Startup operations use best-effort auditing. API operator mutations
        # opt into fail-closed attempt and completion persistence.
        self._lifecycle_audit_disabled = not audit_enabled
        self._lifecycle_auditor = PluginLifecycleAuditor(
            recorder=None if self._lifecycle_audit_disabled else audit,
        )

    @property
    def registry(self) -> ExtensionRegistry:
        """Return the manager-owned unified extension registry."""

        return self._registry

    @property
    def state_store(self) -> PluginLifecycleStateStore:
        """Return the persisted enable/disable intent store."""

        return self._state_store

    @property
    def settings_store(self) -> PluginSettingsStore:
        """Return the manager-owned per-plugin settings store."""

        return self._settings_store

    def compatibility_error(self, manifest: PluginManifest) -> str | None:
        """Return a stable compatibility code without importing plugin code."""

        return permission_compatibility_error(
            manifest,
            self._application_version,
            self._supported_api_versions,
        )

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

    def health_check(self) -> PluginHealthReport:
        """Return a read-only health report for every registered plugin."""

        return build_plugin_health_report(self)

    def bind_lifecycle_auditor(
        self,
        recorder: LifecycleAuditRecorder | None,
    ) -> None:
        """Attach or replace the best-effort lifecycle audit recorder."""

        if self._lifecycle_audit_disabled:
            return
        self._lifecycle_auditor.bind_recorder(recorder)

    def registrations(
        self,
        extension_point: ExtensionPoint | None = None,
    ) -> tuple[ExtensionRegistration, ...]:
        """Return the active extension snapshot from the unified registry."""

        return self._registry.registrations(extension_point)

    def enabled_registrations(
        self,
        extension_point: ExtensionPoint | None = None,
    ) -> tuple[ExtensionRegistration, ...]:
        """Return registrations owned by lifecycle-stable enabled plugins."""

        with self._lock:
            if (
                self._activation_allowed is not None
                and not self._activation_allowed()
            ):
                return ()
            enabled_plugin_ids = {
                plugin_id
                for plugin_id, record in self._plugins.items()
                if record.state == "enabled" and record.transition is None
            }
            return tuple(
                registration
                for registration in self._registry.registrations(extension_point)
                if registration.plugin_id in enabled_plugin_ids
            )

    def enabled_registrations_snapshot(
        self,
        extension_point: ExtensionPoint | None = None,
    ) -> tuple[ExtensionRegistration, ...]:
        """Return active registrations for a lock-free stable-owner snapshot."""

        enabled_plugin_ids = self._stable_enabled_plugin_ids
        return tuple(
            registration
            for registration in self._registry.registrations_snapshot(
                extension_point
            )
            if registration.plugin_id in enabled_plugin_ids
        )

    def capability_inventory_snapshot(
        self,
    ) -> tuple[str, tuple[PluginSnapshot, ...], tuple[ExtensionRegistration, ...]]:
        """Correlate lifecycle and active contributions at stable generations."""

        from .registry import EXTENSION_POINTS

        for _ in range(3):
            with self._lock:
                lifecycle_generation = self._lifecycle_generation
                before = {
                    point: self._registry.registration_snapshot_generation(point)
                    for point in EXTENSION_POINTS
                }
                enabled_plugin_ids = self._stable_enabled_plugin_ids
                registrations = tuple(
                    registration
                    for registration in self._registry.registrations_snapshot()
                    if registration.plugin_id in enabled_plugin_ids
                )
                lifecycle = tuple(
                    self._build_snapshot(record) for record in self._plugins.values()
                )
                after = {
                    point: self._registry.registration_snapshot_generation(point)
                    for point in EXTENSION_POINTS
                }
                lifecycle_generation_after = self._lifecycle_generation
            if before == after and lifecycle_generation == lifecycle_generation_after:
                # Lifecycle transitions never touch a registration generation, so
                # the published generation must carry the lifecycle counter too.
                generation = ",".join(
                    (
                        f"lifecycle:{lifecycle_generation}",
                        *(f"{point}:{before[point]}" for point in sorted(before)),
                    )
                )
                return generation, lifecycle, registrations
        raise RuntimeError("extension registry generation drift")

    def enabled_native_owner_registrations_snapshot(
        self,
        extension_point: ExtensionPoint | None = None,
    ) -> tuple[tuple[ExtensionRegistration, object], ...]:
        """Return stable enabled registrations with exact native owner tokens."""

        enabled_plugin_ids = self._stable_enabled_plugin_ids
        return tuple(
            (registration, owner_token)
            for registration, owner_token in (
                self._registry.native_owner_registrations_snapshot(
                    extension_point
                )
            )
            if registration.plugin_id in enabled_plugin_ids
        )

    def registration_snapshot_generation(
        self,
        extension_point: ExtensionPoint,
    ) -> int:
        """Return the lock-free unified-registry generation for one point."""

        return self._registry.registration_snapshot_generation(extension_point)
