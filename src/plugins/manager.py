# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Central plugin registration and lifecycle state management."""

from __future__ import annotations

import threading
from typing import Any, Callable, Iterable

from .health import PluginHealthReport, build_plugin_health_report
from .inventory import PluginInventoryMixin
from .lifecycle import PluginLifecycleMixin
from .lifecycle_audit import LifecycleAuditRecorder, PluginLifecycleAuditor
from .registration import PluginRegistrationMixin
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
from .registry import ExtensionRegistry
from .state_store import PluginLifecycleStateStore
from .settings_store import PluginSettingsStore


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
    PluginRegistrationMixin,
    PluginInventoryMixin,
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
