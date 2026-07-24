# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Public contracts for the StockPulse plugin core."""

from .agent_tools import (
    AgentToolRegistrationBackend,
    build_agent_tool_extension_contract,
    build_agent_tool_extension_registry,
    validate_agent_tool_definition,
)
from .constants import PLUGIN_APPLICATION_VERSION
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
from .notification_channels import (
    NotificationAdapterResult,
    NotificationChannelAdapter,
    NotificationChannelFactory,
    NotificationChannelRegistry,
    NotificationChannelSnapshot,
    NotificationRequest,
    available_notification_channel_snapshot,
    build_notification_channel_extension_contract,
    validate_notification_channel_factory,
)
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
from .runtime import build_application_extension_registry

__all__ = [
    "AgentToolRegistrationBackend",
    "EXTENSION_POINTS",
    "ExternalPluginLoader",
    "ExternalPluginResult",
    "ExtensionContract",
    "ExtensionPoint",
    "ExtensionRegistration",
    "ExtensionRegistry",
    "JSONValue",
    "NativeRegistrationBackend",
    "NotificationAdapterResult",
    "NotificationChannelAdapter",
    "NotificationChannelFactory",
    "NotificationChannelRegistry",
    "NotificationChannelSnapshot",
    "NotificationRequest",
    "Plugin",
    "PLUGIN_APPLICATION_VERSION",
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
    "available_notification_channel_snapshot",
    "build_agent_tool_extension_contract",
    "build_agent_tool_extension_registry",
    "build_application_extension_registry",
    "build_notification_channel_extension_contract",
    "default_extension_contracts",
    "validate_agent_tool_definition",
    "validate_notification_channel_factory",
]
