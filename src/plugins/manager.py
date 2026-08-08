# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Central plugin registration and lifecycle state management."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Literal

from src.utils.sanitize import log_safe_exception

from .agent_tools import agent_tool_manifest_permissions_error
from .errors import PluginError
from .health import PluginHealthReport, build_plugin_health_report
from .lifecycle_audit import LifecycleAuditRecorder, PluginLifecycleAuditor
from .manifest import API_MAJOR_PATTERN, PluginManifest, parse_semver
from .plugin import Plugin
from .registry import ExtensionPoint, ExtensionRegistration, ExtensionRegistry, PluginContext, RegistrationHandle
from .state_store import PluginLifecycleStateStore


logger = logging.getLogger(__name__)

PluginSource = Literal["builtin", "external"]
PluginState = Literal["registered", "enabled", "disabled", "failed"]

# Extension points that can be unregistered/re-registered in-process via the
# unified registry. All six v1 points support that path; builtin packages and
# failed cleanup still require a process restart.
_HOT_RELOADABLE_EXTENSION_POINTS: frozenset[ExtensionPoint] = frozenset(
    {
        "data_provider",
        "analysis_strategy",
        "agent_tool",
        "notification_channel",
        "report_template",
        "event_hook",
    }
)


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
class PluginSnapshot:
    """Read-only manager state for diagnostics and later composition wiring."""

    manifest: PluginManifest
    source: PluginSource
    state: PluginState
    desired_enabled: bool = True
    package_root: str | None = None
    reloadable: bool = False
    extension_points: tuple[ExtensionPoint, ...] = ()
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


class PluginManager:
    """Own plugin compatibility, state transitions, and reverse cleanup."""

    def __init__(
        self,
        *,
        application_version: str,
        supported_api_versions: Iterable[str] = ("1",),
        registry: ExtensionRegistry | None = None,
        state_store: PluginLifecycleStateStore | None = None,
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
        # Best-effort auditor: never fail-closes lifecycle (see lifecycle_audit).
        # audit_enabled=False disables lazy process-service lookup (tests).
        self._lifecycle_audit_disabled = not audit_enabled
        self._lifecycle_auditor = PluginLifecycleAuditor(
            recorder=None if self._lifecycle_audit_disabled else audit,
        )

    def _bind_lifecycle_boundary(
        self,
        boundary: Callable[[Callable[[], Any]], Any],
        activation_allowed: Callable[[], bool],
        disable_boundary: Callable[
            [str, Callable[[], PluginOperationResult]],
            PluginOperationResult,
        ],
    ) -> None:
        """Bind the owning composition root's outer lifecycle authority."""

        if (
            not callable(boundary)
            or not callable(activation_allowed)
            or not callable(disable_boundary)
        ):
            raise TypeError("plugin lifecycle boundary and guard must be callable")
        with self._lock:
            if self._lifecycle_boundary is not None:
                if (
                    self._lifecycle_boundary == boundary
                    and self._activation_allowed == activation_allowed
                    and self._disable_boundary == disable_boundary
                ):
                    return
                raise RuntimeError(
                    "plugin manager already belongs to an application root"
                )
            self._lifecycle_boundary = boundary
            self._activation_allowed = activation_allowed
            self._disable_boundary = disable_boundary

    def _run_lifecycle_boundary(self, operation: Callable[[], Any]) -> Any:
        """Run only the outermost lifecycle operation through the root hook."""

        boundary = self._lifecycle_boundary
        if boundary is None or getattr(
            self._lifecycle_boundary_state,
            "active",
            False,
        ):
            return operation()
        self._lifecycle_boundary_state.active = True
        try:
            return boundary(operation)
        finally:
            self._lifecycle_boundary_state.active = False

    @property
    def registry(self) -> ExtensionRegistry:
        """Return the manager-owned unified extension registry."""

        return self._registry

    @property
    def state_store(self) -> PluginLifecycleStateStore:
        """Return the persisted enable/disable intent store."""

        return self._state_store

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

    def _audit_metadata_for(self, record: _ManagedPlugin) -> dict[str, Any]:
        return {
            "plugin_version": record.manifest.version,
            "plugin_source": record.source,
            "permissions": list(record.manifest.permissions),
            "extension_points": [
                handle.extension_point
                for handle in record.handles
                if handle.active
            ],
        }

    def _audit_begin(
        self,
        record: _ManagedPlugin | None,
        *,
        plugin_id: str,
        operation: str,
    ) -> str | None:
        if self._lifecycle_audit_disabled:
            return None
        metadata = None if record is None else self._audit_metadata_for(record)
        return self._lifecycle_auditor.begin(
            plugin_id=plugin_id,
            operation=operation,
            metadata=metadata,
        )

    def _audit_complete(
        self,
        record: _ManagedPlugin | None,
        *,
        plugin_id: str,
        operation: str,
        success: bool,
        correlation_id: str | None,
        error_code: str | None,
    ) -> None:
        if self._lifecycle_audit_disabled or correlation_id is None:
            return
        metadata = None if record is None else self._audit_metadata_for(record)
        self._lifecycle_auditor.complete(
            plugin_id=plugin_id,
            operation=operation,
            success=success,
            correlation_id=correlation_id,
            error_code=error_code,
            metadata=metadata,
        )

    def _set_last_error(
        self,
        record: _ManagedPlugin,
        error_code: str | None,
    ) -> None:
        record.last_error_code = error_code

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

    def _publish_stable_enabled_plugin_ids(self) -> None:
        """Publish enabled owners after a state write while holding ``_lock``."""

        self._stable_enabled_plugin_ids = frozenset(
            plugin_id
            for plugin_id, record in self._plugins.items()
            if record.state == "enabled" and record.transition is None
        )

    def _shutdown_plugin_ids(self) -> tuple[str, ...]:
        """Return plugins whose owned lifecycle state still needs shutdown."""

        with self._lock:
            return tuple(
                plugin_id
                for plugin_id, record in self._plugins.items()
                if record.state in {"enabled", "failed"}
            )

    def load(self, plugin_id: str) -> PluginOperationResult:
        """Perform the first ``registered -> enabled`` transition."""

        return self._run_lifecycle_boundary(
            lambda: self._audited_operation(
                plugin_id,
                "load",
                lambda: self._enable(
                    plugin_id,
                    operation="load",
                    required_state="registered",
                ),
            )
        )

    def enable(self, plugin_id: str) -> PluginOperationResult:
        """Perform ``disabled -> enabled`` and remain idempotent when enabled."""

        return self._run_lifecycle_boundary(
            lambda: self._audited_operation(
                plugin_id,
                "enable",
                lambda: self._enable(
                    plugin_id,
                    operation="enable",
                    required_state="disabled",
                ),
            )
        )

    def _audited_operation(
        self,
        plugin_id: str,
        operation: str,
        run: Callable[[], PluginOperationResult],
    ) -> PluginOperationResult:
        """Run one lifecycle operation with best-effort audit + last-error tracking."""

        with self._lock:
            record = self._plugins.get(plugin_id)
        correlation_id = self._audit_begin(
            record,
            plugin_id=plugin_id,
            operation=operation,
        )
        result = run()
        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is not None:
                if result.success and result.error_code is None:
                    self._set_last_error(record, None)
                elif result.error_code is not None:
                    self._set_last_error(record, result.error_code)
        self._audit_complete(
            record,
            plugin_id=plugin_id,
            operation=operation,
            success=result.success,
            correlation_id=correlation_id,
            error_code=result.error_code,
        )
        return result

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
            if (
                self._activation_allowed is not None
                and not self._activation_allowed()
            ):
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation=operation,
                    success=False,
                    state=record.state,
                    error_code="plugin_owner_closed",
                )
            if record.transition is not None:
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation=operation,
                    success=False,
                    state=record.state,
                    error_code="plugin_transition_in_progress",
                )
            if record.state == "enabled":
                if operation == "enable":
                    self._state_store.set_disabled(plugin_id, False)
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

            # Honored across every extension point: disabled plugins never
            # receive onload and therefore never register or invoke hooks.
            if operation == "load" and self._state_store.is_disabled(plugin_id):
                logger.info(
                    "Plugin %s is disabled by persisted lifecycle state; skipping load",
                    plugin_id,
                )
                record.state = "disabled"
                record.transition = None
                record.cleanup_pending = False
                self._publish_stable_enabled_plugin_ids()
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation=operation,
                    success=True,
                    state="disabled",
                )

            if operation == "enable":
                self._state_store.set_disabled(plugin_id, False)

            record.transition = operation
            self._publish_stable_enabled_plugin_ids()
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

            # agent_tool load-time declaration check: every ToolPolicy capability
            # must be declared on the plugin manifest. Fail this plugin only.
            if load_error_code is None:
                active_registrations = tuple(
                    registration
                    for registration in self._registry.registrations()
                    if registration.plugin_id == plugin_id
                )
                load_error_code = agent_tool_manifest_permissions_error(
                    manifest=record.manifest,
                    registrations=active_registrations,
                )
                if load_error_code is not None:
                    logger.warning(
                        "Plugin %s rejected: agent_tool permissions exceed "
                        "manifest declaration (error_code=%s, declared=%s)",
                        plugin_id,
                        load_error_code,
                        list(record.manifest.permissions),
                    )

            if load_error_code is not None:
                remaining, cleanup_errors = self._cleanup_handles(
                    plugin_id,
                    context.handles,
                )
                record.handles = list(remaining)
                record.cleanup_pending = bool(remaining)
                record.state = "failed"
                record.transition = None
                self._publish_stable_enabled_plugin_ids()
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
            self._publish_stable_enabled_plugin_ids()
            logger.info(
                "Plugin enabled id=%s version=%s permissions=%s extension_points=%s",
                plugin_id,
                record.manifest.version,
                list(record.manifest.permissions),
                [
                    handle.extension_point
                    for handle in record.handles
                    if handle.active
                ],
            )
            return PluginOperationResult(
                plugin_id=plugin_id,
                operation=operation,
                success=True,
                state="enabled",
            )

    def disable(self, plugin_id: str) -> PluginOperationResult:
        """Unload an enabled plugin or converge a failed plugin after cleanup."""

        def run_disable() -> PluginOperationResult:
            if self._disable_boundary is None:
                return self._disable(plugin_id)
            return self._disable_boundary(
                plugin_id,
                lambda: self._disable(plugin_id),
            )

        return self._run_lifecycle_boundary(
            lambda: self._audited_operation(plugin_id, "disable", run_disable)
        )

    def _disable(self, plugin_id: str) -> PluginOperationResult:
        """Perform one disable transition inside the outer lifecycle boundary."""

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
            # Root shutdown unload must not rewrite operator intent.
            persist_intent = self._should_persist_operator_intent()

            if record.state == "disabled":
                if persist_intent:
                    self._state_store.set_disabled(plugin_id, True)
                    logger.info(
                        "Plugin %s is already disabled; persisted lifecycle state updated",
                        plugin_id,
                    )
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation="disable",
                    success=True,
                    state="disabled",
                )
            if record.state == "failed":
                record.transition = "disable"
                self._publish_stable_enabled_plugin_ids()
                remaining, cleanup_errors = self._cleanup_handles(
                    plugin_id,
                    tuple(record.handles),
                )
                record.handles = list(remaining)
                record.cleanup_pending = bool(remaining)
                record.state = "failed" if remaining else "disabled"
                record.transition = None
                self._publish_stable_enabled_plugin_ids()
                cleanup_error = cleanup_errors[0] if cleanup_errors else None
                if cleanup_error is None and remaining:
                    cleanup_error = "plugin_registration_cleanup_failed"
                if not remaining and persist_intent:
                    self._state_store.set_disabled(plugin_id, True)
                    logger.info(
                        "Plugin %s disabled after failed-state cleanup; will not be invoked",
                        plugin_id,
                    )
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation="disable",
                    success=not cleanup_errors and not remaining,
                    state=record.state,
                    error_code=cleanup_error,
                )
            if record.state == "registered":
                # Never loaded: mark disabled without onload so every hook type
                # stays unregistered and uninvoked across restarts.
                record.state = "disabled"
                record.transition = None
                if persist_intent:
                    self._state_store.set_disabled(plugin_id, True)
                    logger.info(
                        "Plugin %s disabled before load; skipping registration and invocation",
                        plugin_id,
                    )
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation="disable",
                    success=True,
                    state="disabled",
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
            self._publish_stable_enabled_plugin_ids()
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
            self._publish_stable_enabled_plugin_ids()
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
            if persist_intent:
                self._state_store.set_disabled(plugin_id, True)
                logger.info(
                    "Plugin %s disabled; owned registrations removed and will not be invoked",
                    plugin_id,
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
        return self._run_lifecycle_boundary(
            lambda: tuple(self.load(plugin_id) for plugin_id in selected)
        )

    def disable_all(self, plugin_ids: Iterable[str] | None = None) -> tuple[PluginOperationResult, ...]:
        """Disable a reverse-order snapshot, continuing after every failure."""

        selected = self.plugin_ids() if plugin_ids is None else tuple(plugin_ids)
        return self._run_lifecycle_boundary(
            lambda: tuple(self.disable(plugin_id) for plugin_id in reversed(selected))
        )

    def set_enabled(self, plugin_id: str, enabled: bool) -> PluginOperationResult:
        """Enable or disable one plugin and persist operator intent."""

        if enabled:
            snapshot = self.snapshot(plugin_id)
            if snapshot is None:
                return self._not_found(plugin_id, "enable")
            if snapshot.state == "registered":
                return self.load(plugin_id)
            return self.enable(plugin_id)
        return self.disable(plugin_id)

    def forget(self, plugin_id: str) -> PluginOperationResult:
        """Remove a fully cleaned-up plugin so it can be re-registered."""

        return self._run_lifecycle_boundary(lambda: self._forget(plugin_id))

    def _forget(self, plugin_id: str) -> PluginOperationResult:
        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is None:
                return self._not_found(plugin_id, "forget")
            if record.transition is not None:
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation="forget",
                    success=False,
                    state=record.state,
                    error_code="plugin_transition_in_progress",
                )
            if record.state == "enabled":
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation="forget",
                    success=False,
                    state=record.state,
                    error_code="plugin_invalid_state",
                )
            if record.handles or record.cleanup_pending:
                return PluginOperationResult(
                    plugin_id=plugin_id,
                    operation="forget",
                    success=False,
                    state=record.state,
                    error_code="plugin_registration_cleanup_failed",
                )
            del self._plugins[plugin_id]
            self._publish_stable_enabled_plugin_ids()
            return PluginOperationResult(
                plugin_id=plugin_id,
                operation="forget",
                success=True,
                state="disabled",
            )

    def reload(self, plugin_id: str) -> PluginReloadResult:
        """Reload one external plugin's code/manifest without process restart.

        Built-in plugins always return ``restart_required`` because their code
        is part of the application package. External plugins are re-imported
        from their on-disk package root only; this path never fetches remote
        code and never auto-enables a plugin that is persisted as disabled.
        """

        return self._run_lifecycle_boundary(
            lambda: self._audited_reload(plugin_id)
        )

    def _audited_reload(self, plugin_id: str) -> PluginReloadResult:
        with self._lock:
            record = self._plugins.get(plugin_id)
        correlation_id = self._audit_begin(
            record,
            plugin_id=plugin_id,
            operation="reload",
        )
        result = self._reload(plugin_id)
        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is not None:
                if result.success and result.error_code is None:
                    self._set_last_error(record, None)
                elif result.error_code is not None:
                    self._set_last_error(record, result.error_code)
        self._audit_complete(
            record,
            plugin_id=plugin_id,
            operation="reload",
            success=result.success,
            correlation_id=correlation_id,
            error_code=result.error_code,
        )
        return result

    def _reload(self, plugin_id: str) -> PluginReloadResult:
        snapshot = self.snapshot(plugin_id)
        if snapshot is None:
            return PluginReloadResult(
                plugin_id=plugin_id,
                success=False,
                state="failed",
                reloaded=False,
                restart_required=False,
                error_code="plugin_not_found",
                message="Plugin is not registered",
            )
        if snapshot.source != "external":
            return PluginReloadResult(
                plugin_id=plugin_id,
                success=False,
                state=snapshot.state,
                reloaded=False,
                restart_required=True,
                error_code="plugin_reload_restart_required",
                message=(
                    "Built-in plugins are part of the application package and "
                    "require a process restart to pick up code changes"
                ),
            )
        if snapshot.package_root is None:
            return PluginReloadResult(
                plugin_id=plugin_id,
                success=False,
                state=snapshot.state,
                reloaded=False,
                restart_required=True,
                error_code="plugin_reload_restart_required",
                message=(
                    "External plugin has no recorded package root; restart the "
                    "process to rediscover it from PLUGINS_DIR"
                ),
            )

        desired_enabled = self._state_store.desired_enabled(plugin_id)
        was_enabled = snapshot.state == "enabled"
        if was_enabled or snapshot.state == "failed":
            disable_result = self.disable(plugin_id)
            if not disable_result.success and disable_result.state != "disabled":
                return PluginReloadResult(
                    plugin_id=plugin_id,
                    success=False,
                    state=disable_result.state,
                    reloaded=False,
                    restart_required=True,
                    error_code=disable_result.error_code or "plugin_reload_restart_required",
                    message=(
                        "Plugin could not be fully unloaded; restart the process "
                        "to replace its registrations safely"
                    ),
                )
            # Preserve operator intent after unload-side disable persistence.
            if desired_enabled:
                self._state_store.set_disabled(plugin_id, False)

        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is None:
                return PluginReloadResult(
                    plugin_id=plugin_id,
                    success=False,
                    state="failed",
                    reloaded=False,
                    restart_required=False,
                    error_code="plugin_not_found",
                    message="Plugin disappeared during reload",
                )
            package_root = record.package_root
            module_name = record.module_name
            if package_root is None:
                return PluginReloadResult(
                    plugin_id=plugin_id,
                    success=False,
                    state=record.state,
                    reloaded=False,
                    restart_required=True,
                    error_code="plugin_reload_restart_required",
                    message="External plugin package root is unavailable",
                )
            active_points = {
                handle.extension_point
                for handle in record.handles
                if handle.active
            }
            if active_points - _HOT_RELOADABLE_EXTENSION_POINTS:
                return PluginReloadResult(
                    plugin_id=plugin_id,
                    success=False,
                    state=record.state,
                    reloaded=False,
                    restart_required=True,
                    error_code="plugin_reload_restart_required",
                    message=(
                        "Plugin still owns extension points that cannot be "
                        "hot-reloaded safely"
                    ),
                )

        forget_result = self._forget(plugin_id)
        if not forget_result.success:
            return PluginReloadResult(
                plugin_id=plugin_id,
                success=False,
                state=forget_result.state,
                reloaded=False,
                restart_required=True,
                error_code=forget_result.error_code or "plugin_reload_restart_required",
                message=(
                    "Plugin could not be removed from the manager; restart "
                    "required"
                ),
            )

        if module_name:
            import sys

            sys.modules.pop(module_name, None)

        from .loader import ExternalPluginLoader

        loader = ExternalPluginLoader(self)
        register_result = loader.register_one(package_root)
        if not register_result.success:
            return PluginReloadResult(
                plugin_id=plugin_id,
                success=False,
                state="failed",
                reloaded=False,
                restart_required=False,
                error_code=register_result.error_code or "plugin_reload_failed",
                message="External plugin could not be re-imported from disk",
            )

        if register_result.plugin_id != plugin_id:
            return PluginReloadResult(
                plugin_id=plugin_id,
                success=False,
                state="failed",
                reloaded=False,
                restart_required=False,
                error_code="plugin_reload_id_mismatch",
                message=(
                    f"Reloaded package reports id {register_result.plugin_id!r}, "
                    f"expected {plugin_id!r}"
                ),
            )

        if not desired_enabled:
            # Keep disabled plugins registered-but-not-loaded; do not auto-enable.
            disable_again = self.disable(plugin_id)
            return PluginReloadResult(
                plugin_id=plugin_id,
                success=disable_again.success,
                state=disable_again.state,
                reloaded=True,
                restart_required=False,
                error_code=disable_again.error_code,
                message="Plugin code reloaded; remains disabled by operator intent",
            )

        load_result = self.load(plugin_id)
        return PluginReloadResult(
            plugin_id=plugin_id,
            success=load_result.success,
            state=load_result.state,
            reloaded=load_result.success,
            restart_required=False,
            error_code=load_result.error_code,
            message=(
                "Plugin code and manifest reloaded in-process"
                if load_result.success
                else "Plugin re-imported but failed to enable"
            ),
        )

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

    def _should_persist_operator_intent(self) -> bool:
        """Skip persistence while the composition root is shutting down."""

        if self._activation_allowed is not None and not self._activation_allowed():
            return False
        return True

    @staticmethod
    def _not_found(plugin_id: str, operation: str) -> PluginOperationResult:
        return PluginOperationResult(
            plugin_id=plugin_id,
            operation=operation,
            success=False,
            state="failed",
            error_code="plugin_not_found",
        )
