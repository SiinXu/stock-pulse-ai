# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Public contracts for the StockPulse plugin core."""

from .errors import PluginContextClosedError, PluginError, PluginRegistryError
from .loader import ExternalPluginLoader, ExternalPluginResult
from .manager import (
    PluginManager,
    PluginOperationResult,
    PluginSnapshot,
    PluginSource,
    PluginState,
)
from .manifest import PluginManifest
from .plugin import Plugin
from .registry import (
    EXTENSION_POINTS,
    ExtensionContract,
    ExtensionPoint,
    ExtensionRegistration,
    ExtensionRegistry,
    JSONValue,
    NativeRegistrationBackend,
    PluginContext,
    RegistrationHandle,
    default_extension_contracts,
)

__all__ = [
    "EXTENSION_POINTS",
    "ExternalPluginLoader",
    "ExternalPluginResult",
    "ExtensionContract",
    "ExtensionPoint",
    "ExtensionRegistration",
    "ExtensionRegistry",
    "JSONValue",
    "NativeRegistrationBackend",
    "Plugin",
    "PluginContext",
    "PluginContextClosedError",
    "PluginError",
    "PluginManager",
    "PluginManifest",
    "PluginOperationResult",
    "PluginRegistryError",
    "PluginSnapshot",
    "PluginSource",
    "PluginState",
    "RegistrationHandle",
    "default_extension_contracts",
]
