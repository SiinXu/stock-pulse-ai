# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Native adapter for plugin-owned Agent Tool definitions."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable

from src.agent.tools.registry import (
    SUPPORTED_TOOL_SURFACE_SCOPE_DIMENSIONS,
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)

from .registry import (
    ExtensionContract,
    ExtensionRegistry,
    default_extension_contracts,
)


_PARAMETER_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SUPPORTED_PARAMETER_TYPES = frozenset(
    {"string", "number", "integer", "boolean", "array", "object"}
)


def _valid_parameter(parameter: object) -> bool:
    if not isinstance(parameter, ToolParameter):
        return False
    if (
        type(parameter.name) is not str
        or _PARAMETER_NAME_PATTERN.fullmatch(parameter.name) is None
        or type(parameter.description) is not str
        or not parameter.description.strip()
        or parameter.type not in _SUPPORTED_PARAMETER_TYPES
        or type(parameter.required) is not bool
    ):
        return False
    if parameter.enum is not None:
        if (
            type(parameter.enum) is not list
            or not parameter.enum
            or any(
                type(value) not in {str, int, float, bool}
                or (type(value) is float and not math.isfinite(value))
                for value in parameter.enum
            )
        ):
            return False
    if parameter.pattern is not None:
        if parameter.type != "string" or type(parameter.pattern) is not str:
            return False
        try:
            re.compile(parameter.pattern)
        except re.error:
            return False
    for bound in (parameter.minimum, parameter.maximum):
        if bound is not None and (
            parameter.type not in {"integer", "number"}
            or isinstance(bound, bool)
            or not isinstance(bound, (int, float))
            or (isinstance(bound, float) and not math.isfinite(bound))
        ):
            return False
    if (
        parameter.minimum is not None
        and parameter.maximum is not None
        and parameter.minimum > parameter.maximum
    ):
        return False
    return True


def validate_agent_tool_definition(implementation: object) -> bool:
    """Return whether a plugin tool satisfies the executable ToolSurface contract."""

    if not isinstance(implementation, ToolDefinition):
        return False
    if (
        type(implementation.name) is not str
        or not implementation.name.strip()
        or len(implementation.name) > 128
        or type(implementation.description) is not str
        or not implementation.description.strip()
        or type(implementation.category) is not str
        or not implementation.category.strip()
        or not callable(implementation.handler)
        or type(implementation.parameters) is not list
        or any(not _valid_parameter(parameter) for parameter in implementation.parameters)
    ):
        return False
    parameter_names = [parameter.name for parameter in implementation.parameters]
    if len(parameter_names) != len(set(parameter_names)):
        return False

    policy = implementation.policy
    if (
        not isinstance(policy, ToolPolicy)
        or policy.policy_status != "declared"
        or type(policy.read_only) is not bool
        or any(type(item) is not str or not item for item in policy.side_effects)
        or any(type(item) is not str or not item for item in policy.permissions)
        or any(
            type(item) is not str
            or item not in SUPPORTED_TOOL_SURFACE_SCOPE_DIMENSIONS
            for item in policy.scope_dimensions
        )
    ):
        return False
    has_stock_parameter = "stock_code" in parameter_names
    declares_stock_scope = "stock" in policy.scope_dimensions
    if has_stock_parameter != declares_stock_scope:
        return False

    try:
        json.dumps(
            implementation.to_public_descriptor(),
            allow_nan=False,
            sort_keys=True,
        )
    except (TypeError, ValueError):
        return False
    return True


class AgentToolRegistrationBackend:
    """Delegate exact-owner plugin registrations to one native ToolRegistry."""

    def __init__(
        self,
        registry: ToolRegistry | Callable[[], ToolRegistry],
    ) -> None:
        if not isinstance(registry, ToolRegistry) and not callable(registry):
            raise TypeError("agent tool registry must be a ToolRegistry or provider")
        self._registry_or_provider = registry

    def _registry(self) -> ToolRegistry:
        candidate = self._registry_or_provider
        registry = candidate() if callable(candidate) else candidate
        if not isinstance(registry, ToolRegistry):
            raise TypeError("agent tool registry provider returned an invalid registry")
        return registry

    def contains(self, registration_id: str) -> bool:
        return self._registry().get(registration_id) is not None

    def register(self, registration_id: str, implementation: object) -> None:
        if (
            not isinstance(implementation, ToolDefinition)
            or implementation.name != registration_id
        ):
            raise TypeError("agent tool registration identity is invalid")
        registry = self._registry()
        if registry.get(registration_id) is not None:
            raise ValueError("agent tool registration conflicts with an existing tool")
        registry.register(implementation)

    def unregister(self, registration_id: str, implementation: object) -> None:
        registry = self._registry()
        if registry.get(registration_id) is implementation:
            registry.unregister(registration_id)


def build_agent_tool_extension_registry(
    registry: ToolRegistry | Callable[[], ToolRegistry],
) -> ExtensionRegistry:
    """Build the six-point registry with Agent Tools wired to ToolRegistry."""

    contracts = dict(default_extension_contracts())
    contracts["agent_tool"] = ExtensionContract(
        identity_resolver=lambda implementation: implementation.name,
        validator=validate_agent_tool_definition,
        backend=AgentToolRegistrationBackend(registry),
    )
    return ExtensionRegistry(contracts)
