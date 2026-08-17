# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Central plugin registration and lifecycle state management."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping

from src.utils.sanitize import log_safe_exception

from .health import PluginHealthReport, build_plugin_health_report
from .lifecycle_audit import LifecycleAuditRecorder, PluginLifecycleAuditor
from .manifest import (
    API_MAJOR_PATTERN,
    PluginManifest,
    PluginSettingDefinition,
    PluginSettingScalar,
    parse_semver,
    validate_plugin_setting_value,
)
from .plugin import Plugin
from .registry import ExtensionPoint, ExtensionRegistration, ExtensionRegistry, RegistrationHandle
from .state_store import PluginLifecycleStateStore
from .settings_store import PluginSettingsPersistenceError, PluginSettingsStore


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
    deferred: bool = False


@dataclass(frozen=True, slots=True)
class PluginReloadResult:
    """Result of one hot-reload attempt (honest restart-required when unsafe)."""

    plugin_id: str
    success: bool
    state: PluginState
    reloaded: bool
    restart_required: bool
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class PluginSettingsUpdateResult:
    """Result of one validated per-plugin settings replacement."""

    plugin_id: str
    success: bool
    changed_keys: tuple[str, ...]
    restart_required: bool
    error_code: str | None = None


class PluginSettingsValidationError(ValueError):
    """Structured validation failure for a plugin settings request."""

    code = "plugin_settings_validation_failed"

    def __init__(self, issues: tuple[dict[str, str], ...]) -> None:
        super().__init__(self.code)
        self.issues = issues


class PluginLifecycleAuditCompletionUnavailable(RuntimeError):
    """Audit completion failed after the lifecycle operation returned."""

    code = "security_audit_unavailable"

    def __init__(
        self,
        result: PluginOperationResult | PluginReloadResult | PluginSettingsUpdateResult,
    ) -> None:
        super().__init__(self.code)
        self.result = result


@dataclass(frozen=True, slots=True)
class PluginSnapshot:
    """Read-only manager state for diagnostics and later composition wiring."""

    manifest: PluginManifest
    source: PluginSource
    state: PluginState
    desired_enabled: bool = True
    package_root: str | None = None
    reloadable: bool = False
    extension_points: tuple[ExtensionPoint, ...] = ()
    notification_channels: tuple[str, ...] = ()
    last_error_code: str | None = None


@dataclass(slots=True)
class _ManagedPlugin:
    plugin: Plugin
    manifest: PluginManifest
    source: PluginSource
    state: PluginState = "registered"
    handles: list[RegistrationHandle] = field(default_factory=list)
    transition: str | None = None
    cleanup_pending: bool = False
    package_root: Path | None = None
    module_name: str | None = None
    last_error_code: str | None = None


from .lifecycle import PluginLifecycleMixin
from .permissions import compatibility_error as permission_compatibility_error


class PluginManager(PluginLifecycleMixin):
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

    def settings_schema(self, plugin_id: str) -> tuple[PluginSettingDefinition, ...] | None:
        """Return one registered plugin's immutable declarative field schema."""

        with self._lock:
            record = self._plugins.get(plugin_id)
            return None if record is None else record.manifest.settings

    def settings_values(self, plugin_id: str) -> dict[str, PluginSettingScalar] | None:
        """Return validated effective values (defaults plus explicit overrides)."""

        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is None:
                return None
            definitions = record.manifest.settings
        stored = self._settings_store.values_for(plugin_id)
        effective: dict[str, PluginSettingScalar] = {}
        for definition in definitions:
            persisted = definition.key in stored
            candidate: object = (
                stored[definition.key] if persisted else definition.default_value
            )
            if candidate is None:
                continue
            try:
                validated = validate_plugin_setting_value(
                    definition,
                    candidate,
                    allow_none=False,
                )
            except ValueError:
                logger.warning(
                    "Ignoring invalid persisted plugin setting id=%s key=%s",
                    plugin_id,
                    definition.key,
                    extra={"error_code": "plugin_setting_persisted_value_invalid"},
                )
                if not persisted or definition.default_value is None:
                    continue
                validated = validate_plugin_setting_value(
                    definition,
                    definition.default_value,
                    allow_none=False,
                )
            if validated is not None:
                effective[definition.key] = validated
        return effective

    def update_settings(
        self,
        plugin_id: str,
        values: Mapping[str, object],
        *,
        mask_token: str = "******",
        require_audit: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> PluginSettingsUpdateResult:
        """Validate and durably replace explicit values for one plugin."""

        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is None:
                raise KeyError(plugin_id)
            definitions = record.manifest.settings
            state = record.state
        if not definitions:
            raise PluginSettingsValidationError(
                ({"key": "", "code": "plugin_settings_not_declared", "message": "Plugin does not declare settings"},)
            )
        if not isinstance(values, Mapping):
            raise PluginSettingsValidationError(
                ({"key": "", "code": "invalid_settings_payload", "message": "Settings values must be an object"},)
            )

        by_key = {definition.key: definition for definition in definitions}
        issues: list[dict[str, str]] = []
        for key in values:
            if type(key) is not str or key not in by_key:
                issues.append(
                    {
                        "key": str(key),
                        "code": "unknown_plugin_setting",
                        "message": "Setting is not declared by the plugin manifest",
                    }
                )
        existing = self._settings_store.values_for(plugin_id)
        normalized: dict[str, PluginSettingScalar] = {}
        for definition in definitions:
            if definition.key not in values:
                continue
            submitted = values[definition.key]
            if definition.is_sensitive and submitted == mask_token:
                if definition.key in existing:
                    normalized[definition.key] = existing[definition.key]
                continue
            if submitted is None:
                continue
            try:
                validated = validate_plugin_setting_value(
                    definition,
                    submitted,
                    allow_none=False,
                )
            except ValueError as exc:
                issues.append(
                    {
                        "key": definition.key,
                        "code": "invalid_plugin_setting",
                        "message": str(exc),
                    }
                )
                continue
            if validated is not None:
                normalized[definition.key] = validated

        for definition in definitions:
            if not definition.is_required:
                continue
            candidate = normalized.get(definition.key, definition.default_value)
            try:
                validate_plugin_setting_value(
                    definition,
                    candidate,
                    allow_none=False,
                )
            except ValueError:
                issues.append(
                    {
                        "key": definition.key,
                        "code": "required_plugin_setting_missing",
                        "message": "Required plugin setting is missing",
                    }
                )
        if issues:
            raise PluginSettingsValidationError(tuple(issues))

        changed_keys = tuple(
            sorted(
                key
                for key in set(existing) | set(normalized)
                if existing.get(key) != normalized.get(key)
                or (key in existing) != (key in normalized)
            )
        )
        correlation_id = self._audit_begin(
            record,
            plugin_id=plugin_id,
            operation="settings_update",
            required=require_audit,
            actor_type=actor_type,
            actor_id=actor_id,
        )
        try:
            if changed_keys:
                self._settings_store.replace(plugin_id, normalized)
            result = PluginSettingsUpdateResult(
                plugin_id=plugin_id,
                success=True,
                changed_keys=changed_keys,
                restart_required=bool(changed_keys) and state == "enabled",
            )
        except PluginSettingsPersistenceError:
            result = PluginSettingsUpdateResult(
                plugin_id=plugin_id,
                success=False,
                changed_keys=(),
                restart_required=False,
                error_code="plugin_settings_write_failed",
            )
            self._audit_complete(
                record,
                plugin_id=plugin_id,
                operation="settings_update",
                success=False,
                correlation_id=correlation_id,
                error_code=result.error_code,
                required=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
            raise

        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            self._audit_complete(
                record,
                plugin_id=plugin_id,
                operation="settings_update",
                success=True,
                correlation_id=correlation_id,
                error_code=None,
                required=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        except SecurityAuditUnavailable:
            raise PluginLifecycleAuditCompletionUnavailable(result) from None
        return result

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

    def snapshot(self, plugin_id: str) -> PluginSnapshot | None:
        """Return one immutable plugin state snapshot."""

        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is None:
                return None
            return self._build_snapshot(record)

    def list_snapshots(self) -> tuple[PluginSnapshot, ...]:
        """Return immutable snapshots for every registered plugin in order."""

        with self._lock:
            return tuple(self._build_snapshot(record) for record in self._plugins.values())

    def plugin_ids(self) -> tuple[str, ...]:
        """Return plugin IDs in registration order."""

        with self._lock:
            return tuple(self._plugins)

    def _build_snapshot(self, record: _ManagedPlugin) -> PluginSnapshot:
        extension_points = tuple(
            dict.fromkeys(
                handle.extension_point
                for handle in record.handles
                if handle.active
            )
        )
        notification_channels = tuple(
            dict.fromkeys(
                handle.registration_id
                for handle in record.handles
                if handle.active and handle.extension_point == "notification_channel"
            )
        )
        package_root = (
            None if record.package_root is None else str(record.package_root)
        )
        reloadable = (
            record.source == "external"
            and record.package_root is not None
            and record.transition is None
            and not record.cleanup_pending
        )
        return PluginSnapshot(
            manifest=record.manifest,
            source=record.source,
            state=record.state,
            desired_enabled=self._state_store.desired_enabled(record.manifest.id),
            package_root=package_root,
            reloadable=reloadable,
            extension_points=extension_points,
            notification_channels=notification_channels,
            last_error_code=record.last_error_code,
        )

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
