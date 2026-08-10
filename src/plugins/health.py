# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only plugin health snapshots for operators and diagnostics consumers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .manager import PluginManager, PluginSnapshot


PluginHealthState = Literal["registered", "enabled", "disabled", "failed"]
PluginHealthSource = Literal["builtin", "external"]


@dataclass(frozen=True, slots=True)
class PluginHealthEntry:
    """One plugin's load state, extension points, and last failure code."""

    plugin_id: str
    name: str
    version: str
    source: PluginHealthSource
    state: PluginHealthState
    desired_enabled: bool
    extension_points: tuple[str, ...]
    permissions: tuple[str, ...] = ()
    last_error_code: str | None = None
    package_root: str | None = None
    reloadable: bool = False


@dataclass(frozen=True, slots=True)
class PluginHealthReport:
    """Bounded health document for all registered plugins."""

    plugins: tuple[PluginHealthEntry, ...]
    generated_at: str
    total: int

    def as_dict(self) -> dict[str, object]:
        """JSON-friendly projection for diagnostics and future API adapters."""

        return {
            "generated_at": self.generated_at,
            "total": self.total,
            "plugins": [
                {
                    "plugin_id": entry.plugin_id,
                    "name": entry.name,
                    "version": entry.version,
                    "source": entry.source,
                    "state": entry.state,
                    "desired_enabled": entry.desired_enabled,
                    "extension_points": list(entry.extension_points),
                    "permissions": list(entry.permissions),
                    "last_error_code": entry.last_error_code,
                    "package_root": entry.package_root,
                    "reloadable": entry.reloadable,
                }
                for entry in self.plugins
            ],
        }


def health_entry_from_snapshot(snapshot: "PluginSnapshot") -> PluginHealthEntry:
    """Map a manager snapshot to a health entry."""

    return PluginHealthEntry(
        plugin_id=snapshot.manifest.id,
        name=snapshot.manifest.name,
        version=snapshot.manifest.version,
        source=snapshot.source,
        state=snapshot.state,
        desired_enabled=snapshot.desired_enabled,
        extension_points=tuple(snapshot.extension_points),
        permissions=tuple(snapshot.manifest.permissions),
        last_error_code=snapshot.last_error_code,
        package_root=snapshot.package_root,
        reloadable=snapshot.reloadable,
    )


def build_plugin_health_report(manager: "PluginManager") -> PluginHealthReport:
    """Build a read-only health report from the current manager state."""

    entries = tuple(
        health_entry_from_snapshot(snapshot)
        for snapshot in manager.list_snapshots()
    )
    return PluginHealthReport(
        plugins=entries,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total=len(entries),
    )
