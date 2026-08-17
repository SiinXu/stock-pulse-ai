# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Plugin enable/disable/load/reload transitions extracted from PluginManager."""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable

from src.utils.sanitize import log_safe_exception

from .errors import PluginError
from .loader import select_disable_ids, select_load_ids
from .manager import (
    PluginLifecycleAuditCompletionUnavailable,
    PluginOperationResult,
    PluginReloadResult,
    PluginState,
    _ManagedPlugin,
)
from .permissions import load_time_permission_error
from .registry import ExtensionPoint, PluginContext, RegistrationHandle


logger = logging.getLogger("src.plugins.manager")

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


class PluginLifecycleMixin:
    """State transitions, reverse cleanup, and operator lifecycle mutations."""

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
        required: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> str | None:
        if self._lifecycle_audit_disabled:
            if required:
                from src.services.security_audit_service import (
                    SecurityAuditUnavailable,
                )

                raise SecurityAuditUnavailable()
            return None
        metadata = None if record is None else self._audit_metadata_for(record)
        return self._lifecycle_auditor.begin(
            plugin_id=plugin_id,
            operation=operation,
            metadata=metadata,
            required=required,
            actor_type=actor_type,
            actor_id=actor_id,
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
        required: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        if self._lifecycle_audit_disabled or correlation_id is None:
            if required:
                from src.services.security_audit_service import (
                    SecurityAuditUnavailable,
                )

                raise SecurityAuditUnavailable()
            return
        metadata = None if record is None else self._audit_metadata_for(record)
        self._lifecycle_auditor.complete(
            plugin_id=plugin_id,
            operation=operation,
            success=success,
            correlation_id=correlation_id,
            error_code=error_code,
            metadata=metadata,
            required=required,
            actor_type=actor_type,
            actor_id=actor_id,
        )

    def _set_last_error(
        self,
        record: _ManagedPlugin,
        error_code: str | None,
    ) -> None:
        record.last_error_code = error_code

    def _publish_stable_enabled_plugin_ids(self) -> None:
        """Publish enabled owners after a state write while holding ``_lock``."""

        self._stable_enabled_plugin_ids = frozenset(
            plugin_id
            for plugin_id, record in self._plugins.items()
            if record.state == "enabled" and record.transition is None
        )
        self._lifecycle_generation += 1

    def _write_desired_disabled(self, plugin_id: str, disabled: bool) -> None:
        """Persist operator intent and advance the lifecycle generation."""

        self._state_store.set_disabled(plugin_id, disabled)
        with self._lock:
            self._lifecycle_generation += 1

    def _shutdown_plugin_ids(self) -> tuple[str, ...]:
        """Return plugins whose owned lifecycle state still needs shutdown."""

        with self._lock:
            return tuple(
                plugin_id
                for plugin_id, record in self._plugins.items()
                if record.state in {"enabled", "failed"}
            )

    def load(
        self,
        plugin_id: str,
        *,
        require_audit: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> PluginOperationResult:
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
                require_audit=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        )

    def enable(
        self,
        plugin_id: str,
        *,
        require_audit: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> PluginOperationResult:
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
                require_audit=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        )

    def _audited_operation(
        self,
        plugin_id: str,
        operation: str,
        run: Callable[[], PluginOperationResult],
        *,
        require_audit: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> PluginOperationResult:
        """Run one lifecycle operation with selected audit strictness."""

        with self._lock:
            record = self._plugins.get(plugin_id)
            starting_state = None if record is None else record.state
        correlation_id = self._audit_begin(
            record,
            plugin_id=plugin_id,
            operation=operation,
            required=require_audit,
            actor_type=actor_type,
            actor_id=actor_id,
        )
        result = run()
        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is not None:
                if (
                    operation in {"load", "enable"}
                    and result.success
                    and result.error_code is None
                    and starting_state != "enabled"
                ):
                    self._set_last_error(record, None)
                elif result.error_code is not None:
                    self._set_last_error(record, result.error_code)
        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            self._audit_complete(
                record,
                plugin_id=plugin_id,
                operation=operation,
                success=result.success,
                correlation_id=correlation_id,
                error_code=result.error_code,
                required=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        except SecurityAuditUnavailable:
            raise PluginLifecycleAuditCompletionUnavailable(result) from None
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
                    self._write_desired_disabled(plugin_id, False)
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
                self._write_desired_disabled(plugin_id, False)

            record.transition = operation
            self._publish_stable_enabled_plugin_ids()
            context = PluginContext(
                plugin_id,
                self._registry,
                settings=self.settings_values(plugin_id) or {},
            )
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
                load_error_code = load_time_permission_error(
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

    def disable(
        self,
        plugin_id: str,
        *,
        require_audit: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> PluginOperationResult:
        """Unload an enabled plugin or converge a failed plugin after cleanup."""

        return self._run_lifecycle_boundary(
            lambda: self._audited_operation(
                plugin_id,
                "disable",
                lambda: self._run_disable_boundary(plugin_id),
                require_audit=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        )

    def _run_disable_boundary(self, plugin_id: str) -> PluginOperationResult:
        """Apply the root's dispatch drain without creating a nested audit."""

        if self._disable_boundary is None:
            return self._disable(plugin_id)
        return self._disable_boundary(
            plugin_id,
            lambda: self._disable(plugin_id),
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
                    self._write_desired_disabled(plugin_id, True)
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
                    self._write_desired_disabled(plugin_id, True)
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
                    self._write_desired_disabled(plugin_id, True)
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
                self._write_desired_disabled(plugin_id, True)
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

        selected = select_load_ids(plugin_ids, self.plugin_ids())
        return self._run_lifecycle_boundary(
            lambda: tuple(self.load(plugin_id) for plugin_id in selected)
        )

    def disable_all(self, plugin_ids: Iterable[str] | None = None) -> tuple[PluginOperationResult, ...]:
        """Disable a reverse-order snapshot, continuing after every failure."""

        selected = select_disable_ids(plugin_ids, self.plugin_ids())
        return self._run_lifecycle_boundary(
            lambda: tuple(self.disable(plugin_id) for plugin_id in selected)
        )

    def set_enabled(
        self,
        plugin_id: str,
        enabled: bool,
        *,
        require_audit: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> PluginOperationResult:
        """Enable or disable one plugin and persist operator intent."""

        if enabled:
            snapshot = self.snapshot(plugin_id)
            if snapshot is None:
                return self._not_found(plugin_id, "enable")
            if snapshot.state == "registered":
                return self._run_lifecycle_boundary(
                    lambda: self._audited_operation(
                        plugin_id,
                        "enable",
                        lambda: self._enable(
                            plugin_id,
                            operation="enable",
                            required_state="registered",
                        ),
                        require_audit=require_audit,
                        actor_type=actor_type,
                        actor_id=actor_id,
                    )
                )
            return self.enable(
                plugin_id,
                require_audit=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        return self.disable(
            plugin_id,
            require_audit=require_audit,
            actor_type=actor_type,
            actor_id=actor_id,
        )

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

    def reload(
        self,
        plugin_id: str,
        *,
        require_audit: bool = False,
        actor_type: str | None = None,
        actor_id: str | None = None,
    ) -> PluginReloadResult:
        """Reload one external plugin's code/manifest without process restart.

        Built-in plugins always return ``restart_required`` because their code
        is part of the application package. External plugins are re-imported
        from their on-disk package root only; this path never fetches remote
        code and never auto-enables a plugin that is persisted as disabled.
        """

        return self._run_lifecycle_boundary(
            lambda: self._audited_reload(
                plugin_id,
                require_audit=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        )

    def _audited_reload(
        self,
        plugin_id: str,
        *,
        require_audit: bool,
        actor_type: str | None,
        actor_id: str | None,
    ) -> PluginReloadResult:
        with self._lock:
            record = self._plugins.get(plugin_id)
        correlation_id = self._audit_begin(
            record,
            plugin_id=plugin_id,
            operation="reload",
            required=require_audit,
            actor_type=actor_type,
            actor_id=actor_id,
        )
        result = self._reload(plugin_id)
        with self._lock:
            record = self._plugins.get(plugin_id)
            if record is not None:
                if result.success and result.error_code is None:
                    self._set_last_error(record, None)
                elif result.error_code is not None:
                    self._set_last_error(record, result.error_code)
        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            self._audit_complete(
                record,
                plugin_id=plugin_id,
                operation="reload",
                success=result.success,
                correlation_id=correlation_id,
                error_code=result.error_code,
                required=require_audit,
                actor_type=actor_type,
                actor_id=actor_id,
            )
        except SecurityAuditUnavailable:
            raise PluginLifecycleAuditCompletionUnavailable(result) from None
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
            disable_result = self._run_disable_boundary(plugin_id)
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
                self._write_desired_disabled(plugin_id, False)

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
            disable_again = self._disable(plugin_id)
            return PluginReloadResult(
                plugin_id=plugin_id,
                success=disable_again.success,
                state=disable_again.state,
                reloaded=True,
                restart_required=False,
                error_code=disable_again.error_code,
                message="Plugin code reloaded; remains disabled by operator intent",
            )

        load_result = self._enable(
            plugin_id,
            operation="load",
            required_state="registered",
        )
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
