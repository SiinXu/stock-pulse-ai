# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Native adapter for plugin-owned Agent Tool definitions."""

from __future__ import annotations

import inspect
import json
import math
import re
import threading
from collections.abc import Callable

from src.agent.tool_surface import validate_tool_parameter_value
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
_PORTABLE_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SUPPORTED_PARAMETER_TYPES = frozenset(
    {"string", "number", "integer", "boolean", "array", "object"}
)


def _same_json_value(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if type(left) is list:
        return len(left) == len(right) and all(
            _same_json_value(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    if type(left) is dict:
        return set(left) == set(right) and all(
            _same_json_value(left[key], right[key]) for key in left
        )
    return left == right


def _is_lossless_json_value(value: object) -> bool:
    if value is None or type(value) in {str, bool, int}:
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_is_lossless_json_value(item) for item in value)
    if type(value) is dict:
        return all(
            type(key) is str and _is_lossless_json_value(item)
            for key, item in value.items()
        )
    return False


def _has_lossless_json_roundtrip(value: object) -> bool:
    if not _is_lossless_json_value(value):
        return False
    try:
        decoded = json.loads(json.dumps(value, allow_nan=False, sort_keys=True))
    except (TypeError, ValueError):
        return False
    return _same_json_value(value, decoded)


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
    if parameter.enum is not None and any(
        validate_tool_parameter_value(parameter, value) is not None
        for value in parameter.enum
    ):
        return False
    if parameter.required:
        if parameter.default is not None:
            return False
    else:
        if validate_tool_parameter_value(parameter, parameter.default) is not None:
            return False
        if not _has_lossless_json_roundtrip(parameter.default):
            return False
    return True


def _same_default(schema_default: object, handler_default: object) -> bool:
    if type(schema_default) is not type(handler_default):
        return False
    try:
        comparison = schema_default == handler_default
    except Exception:  # broad-exception: optional_metadata - Custom equality failures make the optional default invalid.
        return False
    return type(comparison) is bool and comparison


def _valid_handler_signature(implementation: ToolDefinition) -> bool:
    try:
        signature = inspect.signature(implementation.handler)
    except (TypeError, ValueError):
        return False

    handler_parameters = signature.parameters
    schema_parameters = {
        parameter.name: parameter for parameter in implementation.parameters
    }
    if set(handler_parameters) != set(schema_parameters):
        return False

    for name, handler_parameter in handler_parameters.items():
        if handler_parameter.kind not in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }:
            return False
        schema_parameter = schema_parameters[name]
        if schema_parameter.required:
            if handler_parameter.default is not inspect.Parameter.empty:
                return False
        elif (
            handler_parameter.default is inspect.Parameter.empty
            or not _same_default(
                schema_parameter.default,
                handler_parameter.default,
            )
        ):
            return False
    return True


def validate_agent_tool_definition(implementation: object) -> bool:
    """Return whether a plugin tool satisfies the executable ToolSurface contract."""

    if not isinstance(implementation, ToolDefinition):
        return False
    if (
        type(implementation.name) is not str
        or _PORTABLE_TOOL_NAME_PATTERN.fullmatch(implementation.name) is None
        or type(implementation.description) is not str
        or not implementation.description.strip()
        or type(implementation.category) is not str
        or not implementation.category.strip()
        or not callable(implementation.handler)
        or implementation.enforce_contract is not True
        or type(implementation.parameters) is not list
        or any(not _valid_parameter(parameter) for parameter in implementation.parameters)
    ):
        return False
    parameter_names = [parameter.name for parameter in implementation.parameters]
    if len(parameter_names) != len(set(parameter_names)):
        return False
    if not _valid_handler_signature(implementation):
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
    stock_parameter = next(
        (
            parameter
            for parameter in implementation.parameters
            if parameter.name == "stock_code"
        ),
        None,
    )
    if declares_stock_scope and (
        stock_parameter is None or not stock_parameter.required
    ):
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
        self._owned_registries: dict[
            tuple[str, int], tuple[object, ToolRegistry]
        ] = {}
        self._lock = threading.RLock()

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
        owner_key = (registration_id, id(implementation))
        with self._lock:
            if owner_key in self._owned_registries:
                raise ValueError("agent tool implementation is already registered")
            self._owned_registries[owner_key] = (implementation, registry)
            registry.register(implementation)

    def unregister(self, registration_id: str, implementation: object) -> None:
        owner_key = (registration_id, id(implementation))
        with self._lock:
            owner = self._owned_registries.get(owner_key)
            if owner is None or owner[0] is not implementation:
                return
            registry = owner[1]
            if registry.get(registration_id) is implementation:
                registry.unregister(registration_id)
            current = self._owned_registries.get(owner_key)
            if (
                current is not None
                and current[0] is implementation
                and current[1] is registry
            ):
                del self._owned_registries[owner_key]


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
