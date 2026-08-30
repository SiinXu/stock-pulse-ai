# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Plugin snapshot helpers extracted from PluginManager."""

from __future__ import annotations

from .manager_types import PluginSnapshot, _ManagedPlugin


class PluginSnapshotMixin:
    """Build immutable plugin state snapshots from managed records."""

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
