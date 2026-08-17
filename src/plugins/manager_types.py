# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Cycle-free PluginManager types shared by loader, lifecycle, and the facade.

These names stay public through ``src.plugins.manager`` so existing imports and
patch targets do not change. Defining them here lets ``lifecycle`` and
``loader`` import types without completing ``manager``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .manifest import PluginManifest
from .plugin import Plugin
from .registry import ExtensionPoint, RegistrationHandle


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
