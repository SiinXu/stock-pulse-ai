# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Public contracts for the StockPulse plugin core."""

from .agent_tools import (
    AgentToolRegistrationBackend,
    build_agent_tool_extension_registry,
    validate_agent_tool_definition,
)
from .constants import PLUGIN_APPLICATION_VERSION
from .errors import PluginContextClosedError, PluginError, PluginRegistryError
from .event_hooks import (
    EVENT_HOOK_NAMES,
    EVENT_HOOK_SCHEMA_VERSION,
    EventHook,
    EventHookRegistration,
    PluginEvent,
    dispatch_analysis_event,
    dispatch_market_review_event,
    event_hook_extension_contract,
    validate_event_hook_registration,
)
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
    "AgentToolRegistrationBackend",
    "EXTENSION_POINTS",
    "EVENT_HOOK_NAMES",
    "EVENT_HOOK_SCHEMA_VERSION",
    "EventHook",
    "EventHookRegistration",
    "ExternalPluginLoader",
    "ExternalPluginResult",
    "ExtensionContract",
    "ExtensionPoint",
    "ExtensionRegistration",
    "ExtensionRegistry",
    "JSONValue",
    "NativeRegistrationBackend",
    "Plugin",
    "PluginEvent",
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
    "build_agent_tool_extension_registry",
    "default_extension_contracts",
    "dispatch_analysis_event",
    "dispatch_market_review_event",
    "event_hook_extension_contract",
    "validate_agent_tool_definition",
    "validate_event_hook_registration",
]
