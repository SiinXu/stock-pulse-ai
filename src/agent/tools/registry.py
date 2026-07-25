# -*- coding: utf-8 -*-
"""
Tool Registry for the Agent framework.

Provides:
- ToolParameter / ToolDefinition dataclasses
- ToolRegistry: central tool registry with multi-provider schema generation
- @tool decorator for easy tool registration
"""

import json
import inspect
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_TOOL_SURFACE_SCOPE_DIMENSIONS = frozenset({"stock"})
SUPPORTED_AGENT_TOOL_CAPABILITIES = frozenset({
    "analysis_context:read",
    "backtest:read",
    "community_intel:read",
    "intel:read",
    "local_model:execute",
    "market_data:read",
    "news:read",
    "portfolio:read",
})
SUPPORTED_AGENT_TOOL_PARAMETER_TYPES = frozenset({
    "array",
    "boolean",
    "integer",
    "number",
    "object",
    "string",
})
_MAX_AGENT_TOOL_CAPABILITIES = len(SUPPORTED_AGENT_TOOL_CAPABILITIES)
_MAX_AGENT_TOOL_PARAMETERS = 128
_MAX_AGENT_TOOL_DEFAULT_DEPTH = 12
_MAX_AGENT_TOOL_DEFAULT_NODES = 512
_CAPABILITY_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]{0,31}:[a-z][a-z0-9_]{0,31}$"
)
_PARAMETER_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


# ============================================================
# Data classes
# ============================================================

@dataclass
class ToolParameter:
    """Schema for a single tool parameter."""
    name: str
    type: str  # "string" | "number" | "integer" | "boolean" | "array" | "object"
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    pattern: Optional[str] = None


@dataclass(frozen=True)
class ToolPolicy:
    """Internal policy metadata for DSA Tool Surface descriptors."""

    read_only: Optional[bool] = None
    side_effects: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    policy_status: str = "unknown"
    scope_dimensions: List[str] = field(default_factory=list)

    @classmethod
    def unknown(cls) -> "ToolPolicy":
        return cls()

    @classmethod
    def declared(
        cls,
        *,
        read_only: bool,
        side_effects: Optional[List[str]] = None,
        permissions: Optional[List[str]] = None,
        scope_dimensions: Optional[List[str]] = None,
    ) -> "ToolPolicy":
        return cls(
            read_only=read_only,
            side_effects=list(side_effects or []),
            permissions=list(permissions or []),
            policy_status="declared",
            scope_dimensions=list(scope_dimensions or []),
        )

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "read_only": self.read_only,
            "side_effects": list(self.side_effects),
            "permissions": list(self.permissions),
            # ``permissions`` is retained for descriptor compatibility. Agent
            # execution treats the same bounded values as capabilities.
            "capabilities": list(self.permissions),
            "policy_status": self.policy_status,
        }


@dataclass
class ToolDefinition:
    """Complete definition of an agent-callable tool."""
    name: str
    description: str
    parameters: List[ToolParameter]
    handler: Callable
    category: str = "data"  # data | analysis | search | action
    policy: ToolPolicy = field(default_factory=ToolPolicy.unknown)
    enforce_contract: bool = False

    # ----- Multi-provider schema converters -----

    def _params_json_schema(self) -> dict:
        """Convert parameters to JSON Schema (shared by OpenAI/Anthropic)."""
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for p in self.parameters:
            prop: Dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.minimum is not None:
                prop["minimum"] = p.minimum
            if p.maximum is not None:
                prop["maximum"] = p.maximum
            if p.pattern is not None:
                prop["pattern"] = p.pattern
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
        schema: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema

    def _descriptor_json_schema(self) -> dict:
        """Return a descriptor schema with explicit empty required list."""
        schema = self._params_json_schema()
        schema.setdefault("required", [])
        schema["additionalProperties"] = self.accepts_extra_arguments()
        return schema

    def accepts_extra_arguments(self) -> bool:
        """Return whether the handler explicitly accepts undeclared kwargs."""
        try:
            sig = inspect.signature(self.handler)
        except (TypeError, ValueError):
            return False
        return any(param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values())

    def to_openai_tool(self) -> dict:
        """Convert to OpenAI ``tools`` list element format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._params_json_schema(),
            },
        }

    def to_public_descriptor(self) -> dict:
        """Return Tool Surface descriptor without exposing the Python handler."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self._descriptor_json_schema(),
            "policy": self.policy.to_public_dict(),
            "scope": {
                "scope_dimensions": list(self.policy.scope_dimensions),
                "requires_stock_scope": "stock" in self.policy.scope_dimensions,
            },
        }

    def to_mcp_descriptor(self) -> dict:
        """Return an MCP-compatible descriptor only; no server/transport implied."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self._descriptor_json_schema(),
        }


# ============================================================
# Tool Registry
# ============================================================

class ToolRegistry:
    """Central registry for all agent-callable tools.

    Usage::

        registry = ToolRegistry()
        registry.register(tool_def)
        ToolSurface(registry).execute_tool(
            "get_realtime_quote",
            {"stock_code": "600519"},
            access_context,
        )
    """

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    # ----- Registration -----

    def register(self, tool_def: ToolDefinition) -> None:
        """Register a tool definition."""
        if tool_def.name in self._tools:
            logger.warning(f"Tool '{tool_def.name}' already registered, overwriting")
        self._tools[tool_def.name] = tool_def
        logger.debug(f"Registered tool: {tool_def.name} (category={tool_def.category})")

    def unregister(self, name: str) -> None:
        """Remove a registered tool."""
        self._tools.pop(name, None)

    # ----- Query -----

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Return a tool definition by name."""
        return self._tools.get(name)

    def resolve(self, name: str) -> Optional[ToolDefinition]:
        """Return a tool definition by exact registered name."""
        return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> List[ToolDefinition]:
        """List all tools, optionally filtered by category."""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    def list_names(self) -> List[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    # ----- Schema generation -----

    def to_openai_tools(self) -> List[dict]:
        """Generate OpenAI-format tools list (used by litellm for all providers)."""
        return [t.to_openai_tool() for t in self._tools.values()]

    def validate_tool_policies(self, *, strict: bool = False) -> List[Dict[str, Any]]:
        """Return policy validation issues for registered tools.

        Ordinary registration intentionally stays permissive.  Strict mode is
        used by Tool Surface checks for production/default registries.
        """
        issues: List[Dict[str, Any]] = []
        for tool_def in self._tools.values():
            policy = tool_def.policy
            if not isinstance(policy, ToolPolicy):
                if strict:
                    issues.append({
                        "tool": tool_def.name,
                        "code": "policy_unknown",
                        "message": "Tool policy is not declared.",
                    })
                continue
            if policy.policy_status != "declared":
                if strict:
                    issues.append({
                        "tool": tool_def.name,
                        "code": "policy_unknown",
                        "message": "Tool policy is not declared.",
                    })
                continue
            if strict and policy.read_only is None:
                issues.append({
                    "tool": tool_def.name,
                    "code": "read_only_missing",
                    "message": "Tool policy read_only is not declared.",
                })
            if not strict:
                continue
            capability_error = validate_tool_capability_contract(tool_def)
            if capability_error is not None:
                issues.append({
                    "tool": tool_def.name,
                    "code": capability_error["code"],
                    "message": capability_error["message"],
                    **capability_error["details"],
                })
            schema_error = validate_tool_schema_contract(tool_def)
            if schema_error is not None:
                issues.append({
                    "tool": tool_def.name,
                    "code": schema_error["code"],
                    "message": schema_error["message"],
                    **schema_error["details"],
                })
            if type(policy.scope_dimensions) is not list:
                issues.append({
                    "tool": tool_def.name,
                    "code": "invalid_scope_metadata",
                    "message": "Tool scope metadata must be a list.",
                })
                continue
            unsupported_scopes = [
                dimension
                for dimension in policy.scope_dimensions
                if (
                    type(dimension) is not str
                    or dimension not in SUPPORTED_TOOL_SURFACE_SCOPE_DIMENSIONS
                )
            ]
            for dimension in unsupported_scopes:
                issues.append({
                    "tool": tool_def.name,
                    "code": "unsupported_scope_dimension",
                    "message": "Tool declares an unsupported scope dimension.",
                    "dimension": (
                        dimension
                        if type(dimension) is str
                        else type(dimension).__name__
                    ),
                })
            has_stock_param = any(param.name == "stock_code" for param in tool_def.parameters)
            declares_stock_scope = "stock" in policy.scope_dimensions
            if has_stock_param and not declares_stock_scope:
                issues.append({
                    "tool": tool_def.name,
                    "code": "stock_scope_missing",
                    "message": "Tool has stock_code parameter but does not declare stock scope.",
                })
            if declares_stock_scope and not has_stock_param:
                issues.append({
                    "tool": tool_def.name,
                    "code": "stock_scope_parameter_missing",
                    "message": "Tool declares stock scope but has no stock_code parameter.",
                })
        return issues

    def supported_declared_capabilities(
        self,
        tool_names: Optional[Iterable[str]] = None,
    ) -> frozenset[str]:
        """Return application-owned grants for valid registered tool policies.

        Invalid and unsupported declarations are deliberately omitted. The
        ToolSurface independently rejects those tools before handler dispatch.
        """
        selected = (
            self.list_names()
            if tool_names is None
            else [
                name
                for name in tool_names
                if isinstance(name, str) and name.strip()
            ]
        )
        capabilities = set()
        for name in selected:
            tool_def = self.resolve(name)
            if (
                tool_def is not None
                and validate_tool_capability_contract(tool_def) is None
                and validate_tool_schema_contract(tool_def) is None
            ):
                capabilities.update(tool_def.policy.permissions)
        return frozenset(capabilities)

    # ----- Execution -----

    def execute(self, name: str, **kwargs) -> Any:
        """Reject legacy direct execution outside the ToolSurface authority."""
        raise RuntimeError("direct_tool_execution_disabled")


def validate_tool_capability_contract(
    tool_def: ToolDefinition,
) -> Optional[Dict[str, Any]]:
    """Return one stable fail-closed capability-contract error."""
    policy = tool_def.policy
    if not isinstance(policy, ToolPolicy):
        return {
            "code": "policy_undeclared",
            "message": "Tool policy is not declared.",
            "details": {"policy_status": "invalid"},
        }
    if policy.policy_status != "declared":
        return {
            "code": "policy_undeclared",
            "message": "Tool policy is not declared.",
            "details": {"policy_status": policy.policy_status},
        }
    if type(policy.read_only) is not bool:
        return {
            "code": "policy_undeclared",
            "message": "Tool policy is incomplete.",
            "details": {"policy_status": "incomplete"},
        }
    if type(policy.permissions) is not list:
        return {
            "code": "unsupported_capability",
            "message": "Tool declares unsupported executable capabilities.",
            "details": {
                "invalid_capabilities": ["invalid_collection"],
                "duplicate_capabilities": [],
                "unsupported_capabilities": [],
                "supported_capabilities": sorted(
                    SUPPORTED_AGENT_TOOL_CAPABILITIES
                ),
            },
        }

    declared = list(policy.permissions)
    if not declared:
        return {
            "code": "capability_undeclared",
            "message": "Tool declares no executable capabilities.",
            "details": {
                "required_capabilities": [],
                "supported_capabilities": sorted(
                    SUPPORTED_AGENT_TOOL_CAPABILITIES
                ),
            },
        }
    if len(declared) > _MAX_AGENT_TOOL_CAPABILITIES:
        return {
            "code": "unsupported_capability",
            "message": "Tool declares unsupported executable capabilities.",
            "details": {
                "invalid_capabilities": ["too_many_capabilities"],
                "duplicate_capabilities": [],
                "unsupported_capabilities": [],
                "supported_capabilities": sorted(
                    SUPPORTED_AGENT_TOOL_CAPABILITIES
                ),
            },
        }

    invalid = sorted({
        type(value).__name__
        for value in declared
        if type(value) is not str
    })
    strings = [value for value in declared if type(value) is str]
    noncanonical = any(value != value.strip() for value in strings)
    normalized = [value for value in strings if value]
    malformed = sorted({
        "invalid_name"
        for value in normalized
        if _CAPABILITY_NAME_PATTERN.fullmatch(value) is None
    })
    if any(not value for value in strings):
        malformed.append("invalid_name")
    if noncanonical:
        malformed.append("noncanonical_name")
    duplicates = sorted({
        value
        for value in normalized
        if (
            _CAPABILITY_NAME_PATTERN.fullmatch(value) is not None
            and normalized.count(value) > 1
        )
    })
    unsupported = sorted({
        value
        for value in normalized
        if (
            _CAPABILITY_NAME_PATTERN.fullmatch(value) is not None
            and value not in SUPPORTED_AGENT_TOOL_CAPABILITIES
        )
    })
    if invalid or malformed or duplicates or unsupported:
        return {
            "code": "unsupported_capability",
            "message": "Tool declares unsupported executable capabilities.",
            "details": {
                "invalid_capabilities": invalid + malformed,
                "duplicate_capabilities": duplicates,
                "unsupported_capabilities": unsupported,
                "supported_capabilities": sorted(
                    SUPPORTED_AGENT_TOOL_CAPABILITIES
                ),
            },
        }
    return None


def validate_tool_schema_contract(
    tool_def: ToolDefinition,
) -> Optional[Dict[str, Any]]:
    """Return one bounded fail-closed tool-definition schema error."""
    if not isinstance(tool_def, ToolDefinition):
        return _schema_contract_error(["invalid_definition"])
    if not callable(tool_def.handler):
        return _schema_contract_error(["invalid_handler"])
    if type(tool_def.parameters) is not list:
        return _schema_contract_error(["invalid_parameter_collection"])
    if len(tool_def.parameters) > _MAX_AGENT_TOOL_PARAMETERS:
        return _schema_contract_error(["too_many_parameters"])

    issues: List[str] = []
    names: List[str] = []
    for index, parameter in enumerate(tool_def.parameters):
        field = f"parameters[{index}]"
        if not isinstance(parameter, ToolParameter):
            issues.append(f"{field}.definition")
            continue
        if (
            type(parameter.name) is not str
            or _PARAMETER_NAME_PATTERN.fullmatch(parameter.name) is None
        ):
            issues.append(f"{field}.name")
        else:
            names.append(parameter.name)
        if (
            type(parameter.description) is not str
            or not parameter.description.strip()
        ):
            issues.append(f"{field}.description")
        if (
            type(parameter.type) is not str
            or parameter.type not in SUPPORTED_AGENT_TOOL_PARAMETER_TYPES
        ):
            issues.append(f"{field}.type")
        if type(parameter.required) is not bool:
            issues.append(f"{field}.required")

        enum_is_valid = parameter.enum is None or (
            type(parameter.enum) is list
            and bool(parameter.enum)
            and all(_is_bounded_json_scalar(value) for value in parameter.enum)
        )
        if not enum_is_valid:
            issues.append(f"{field}.enum")
        if parameter.pattern is not None:
            if parameter.type != "string" or type(parameter.pattern) is not str:
                issues.append(f"{field}.pattern")
            else:
                try:
                    re.compile(parameter.pattern)
                except re.error:
                    issues.append(f"{field}.pattern")

        bounds_valid = True
        for bound in (parameter.minimum, parameter.maximum):
            if bound is not None and (
                parameter.type not in {"integer", "number"}
                or isinstance(bound, bool)
                or not isinstance(bound, (int, float))
                or (isinstance(bound, float) and not math.isfinite(bound))
            ):
                bounds_valid = False
        if (
            bounds_valid
            and parameter.minimum is not None
            and parameter.maximum is not None
            and parameter.minimum > parameter.maximum
        ):
            bounds_valid = False
        if not bounds_valid:
            issues.append(f"{field}.bounds")

        if type(parameter.required) is bool:
            if parameter.required and parameter.default is not None:
                issues.append(f"{field}.default")
            elif (
                not parameter.required
                and parameter.default is not None
                and not _parameter_default_is_valid(parameter)
            ):
                issues.append(f"{field}.default")

    if len(names) != len(set(names)):
        issues.append("duplicate_parameter_name")
    if issues:
        return _schema_contract_error(issues)
    return None


def _schema_contract_error(issues: Iterable[str]) -> Dict[str, Any]:
    bounded = list(dict.fromkeys(issues))[:32]
    return {
        "code": "schema_contract_violation",
        "message": "Tool declares an invalid argument schema.",
        "details": {"invalid_schema_fields": bounded},
    }


def _is_bounded_json_scalar(value: Any) -> bool:
    return (
        type(value) in {str, bool, int}
        or (type(value) is float and math.isfinite(value))
    )


def _parameter_default_is_valid(parameter: ToolParameter) -> bool:
    value = parameter.default
    if parameter.type == "string":
        type_matches = type(value) is str
    elif parameter.type == "integer":
        type_matches = type(value) is int
    elif parameter.type == "number":
        type_matches = type(value) in {int, float} and (
            type(value) is int or math.isfinite(value)
        )
    elif parameter.type == "boolean":
        type_matches = type(value) is bool
    elif parameter.type == "array":
        type_matches = type(value) is list
    elif parameter.type == "object":
        type_matches = type(value) is dict
    else:
        return False
    if not type_matches or not _is_bounded_json_value(value):
        return False
    try:
        json.dumps(value, allow_nan=False, sort_keys=True)
    except (RecursionError, TypeError, ValueError):
        return False
    if parameter.enum is not None:
        if (
            type(parameter.enum) is not list
            or not all(_is_bounded_json_scalar(item) for item in parameter.enum)
            or value not in parameter.enum
        ):
            return False
    if parameter.pattern is not None and type(value) is str:
        if type(parameter.pattern) is not str:
            return False
        try:
            if re.search(parameter.pattern, value) is None:
                return False
        except re.error:
            return False
    if parameter.type in {"integer", "number"}:
        for bound in (parameter.minimum, parameter.maximum):
            if bound is not None and (
                isinstance(bound, bool)
                or not isinstance(bound, (int, float))
                or (isinstance(bound, float) and not math.isfinite(bound))
            ):
                return False
        if parameter.minimum is not None and value < parameter.minimum:
            return False
        if parameter.maximum is not None and value > parameter.maximum:
            return False
    return True


def _is_bounded_json_value(value: Any) -> bool:
    """Validate one default without unbounded recursion or container walks."""
    node_count = 0
    active_containers: set[int] = set()

    def _walk(candidate: Any, depth: int) -> bool:
        nonlocal node_count
        node_count += 1
        if (
            depth > _MAX_AGENT_TOOL_DEFAULT_DEPTH
            or node_count > _MAX_AGENT_TOOL_DEFAULT_NODES
        ):
            return False
        if candidate is None or type(candidate) in {str, bool, int}:
            return True
        if type(candidate) is float:
            return math.isfinite(candidate)
        if type(candidate) not in {list, dict}:
            return False

        identity = id(candidate)
        if identity in active_containers:
            return False
        active_containers.add(identity)
        try:
            if type(candidate) is list:
                return all(_walk(item, depth + 1) for item in candidate)
            return all(
                type(key) is str and _walk(item, depth + 1)
                for key, item in candidate.items()
            )
        finally:
            active_containers.remove(identity)

    return _walk(value, 0)


# ============================================================
# @tool decorator
# ============================================================

# Global default registry (singleton pattern)
_default_registry: Optional[ToolRegistry] = None


def get_default_registry() -> ToolRegistry:
    """Get or create the global default ToolRegistry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


def tool(
    name: str,
    description: str,
    category: str = "data",
    parameters: Optional[List[ToolParameter]] = None,
    registry: Optional[ToolRegistry] = None,
    policy: Optional[ToolPolicy] = None,
):
    """Decorator to register a function as an agent tool.

    Parameters can be specified explicitly or inferred from type hints.

    Example::

        @tool(name="get_realtime_quote", category="data",
              description="Get real-time stock quote")
        def get_realtime_quote(stock_code: str) -> dict:
            ...
    """
    def decorator(func: Callable) -> Callable:
        # Infer parameters from type hints if not provided
        params = parameters
        if params is None:
            params = _infer_parameters(func)

        tool_def = ToolDefinition(
            name=name,
            description=description,
            parameters=params,
            handler=func,
            category=category,
            policy=policy or ToolPolicy.unknown(),
        )

        target_registry = registry or get_default_registry()
        target_registry.register(tool_def)

        # Attach metadata to function for introspection
        func._tool_definition = tool_def
        return func

    return decorator


def _infer_parameters(func: Callable) -> List[ToolParameter]:
    """Infer ToolParameter list from function signature and type hints."""
    sig = inspect.signature(func)
    hints = getattr(func, '__annotations__', {})
    params: List[ToolParameter] = []

    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        # Skip return annotation
        hint = hints.get(param_name, str)
        # Handle Optional and other typing constructs
        origin = getattr(hint, '__origin__', None)
        if origin is not None:
            # Optional[X] -> X, List[X] -> array, etc.
            args = getattr(hint, '__args__', ())
            if origin is list or (hasattr(origin, '__name__') and origin.__name__ == 'List'):
                param_type = "array"
            elif origin is dict:
                param_type = "object"
            else:
                # Union/Optional - use first non-None arg
                for a in args:
                    if a is not type(None):
                        param_type = type_map.get(a, "string")
                        break
                else:
                    param_type = "string"
        else:
            param_type = type_map.get(hint, "string")

        has_default = param.default is not inspect.Parameter.empty
        tp = ToolParameter(
            name=param_name,
            type=param_type,
            description=f"Parameter: {param_name}",
            required=not has_default,
            default=param.default if has_default else None,
        )
        params.append(tp)

    return params
