# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Plugin inventory snapshots extracted from PluginManager."""

from __future__ import annotations

from .manager_types import PluginSnapshot
from .registry import ExtensionPoint, ExtensionRegistration


class PluginInventoryMixin:
    """Project extension-registry views correlated with enabled owners and generation."""

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
