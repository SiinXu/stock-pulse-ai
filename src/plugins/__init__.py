# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Public contracts for the StockPulse plugin core."""

from .agent_tools import (
    AgentToolRegistrationBackend,
    build_agent_tool_extension_contract,
    build_agent_tool_extension_registry,
    validate_agent_tool_definition,
)
from .analysis_strategies import (
    AnalysisStrategyCatalogSnapshot,
    AnalysisStrategyDefinition,
    AnalysisStrategyRegistry,
    RegisteredAnalysisStrategy,
    build_analysis_strategy_extension_contract,
    validate_analysis_strategy_definition,
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
from .plugin import Plugin
from .report_templates import (
    ReportPlatform,
    ReportRenderRequest,
    ReportTemplate,
    SUPPORTED_REPORT_PLATFORMS,
    normalize_report_platform,
    validate_report_template,
)
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
    "AnalysisStrategyCatalogSnapshot",
    "AnalysisStrategyDefinition",
    "AnalysisStrategyRegistry",
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
    "ReportPlatform",
    "ReportRenderRequest",
    "ReportTemplate",
    "RegistrationHandle",
    "SUPPORTED_REPORT_PLATFORMS",
    "RegisteredAnalysisStrategy",
    "build_agent_tool_extension_contract",
    "build_agent_tool_extension_registry",
    "build_analysis_strategy_extension_contract",
    "build_application_extension_registry",
    "default_extension_contracts",
    "normalize_report_platform",
    "validate_agent_tool_definition",
    "validate_report_template",
    "validate_analysis_strategy_definition",
]
