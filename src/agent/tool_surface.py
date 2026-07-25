# -*- coding: utf-8 -*-
"""Internal DSA Tool Surface for future external Agent runtimes."""

from __future__ import annotations

import contextvars
import json
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Dict, Optional, Tuple

from src.agent.tools.execution import (
    _MAX_TOOL_ARGUMENT_INSPECTION_DEPTH,
    _MAX_TOOL_ARGUMENT_INSPECTION_NODES,
    _bounded_tool_arguments,
    ToolAccessContext,
    _guard_tool_definition_stock_scope,
    build_tool_audit,
    redact_diagnostic_value,
    serialize_tool_error_result,
    serialize_tool_result,
)
from src.agent.tools.registry import (
    SUPPORTED_AGENT_TOOL_CAPABILITIES,
    SUPPORTED_TOOL_SURFACE_SCOPE_DIMENSIONS,
    ToolDefinition,
    ToolParameter,
    ToolRegistry,
    validate_tool_capability_contract,
    validate_tool_schema_contract,
)
from src.security.outbound_policy import (
    OutboundPolicyError,
    validate_outbound_url,
)
from src.utils.sanitize import exception_chain_redaction_values, log_safe_exception

logger = logging.getLogger(__name__)


_JSON_TYPE_TO_PYTHON = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}
_ABSOLUTE_URL_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_URL_ARGUMENT_SUFFIXES = (
    "_url",
    "_urls",
    "_uri",
    "_uris",
    "_endpoint",
    "_endpoints",
    "_webhook",
    "_webhooks",
    "_link",
    "_links",
)
_URL_ARGUMENT_NAMES = frozenset({
    "url",
    "urls",
    "uri",
    "uris",
    "endpoint",
    "endpoints",
    "webhook",
    "webhooks",
    "link",
    "links",
})
ToolDispatchRejection = Tuple[str, str, Optional[Dict[str, Any]]]


class _HandlerDispatchBlocked(Exception):
    """Internal signal preventing a handler from starting after a fence wins."""

    def __init__(self, error: Dict[str, Any]) -> None:
        super().__init__(error["message"])
        self.error = error


class ToolSurface:
    """Internal tool schema and execution surface.

    This is a Python API only.  It intentionally does not expose REST, MCP, or
    provider-specific runtime transport.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def list_tools(self, format: str = "public") -> list[dict]:
        """List tools in a stable schema format."""
        normalized = (format or "public").strip().lower()
        if normalized == "openai":
            return self._registry.to_openai_tools()
        if normalized == "public":
            return [tool_def.to_public_descriptor() for tool_def in self._registry.list_tools()]
        if normalized == "mcp_descriptor":
            return [tool_def.to_mcp_descriptor() for tool_def in self._registry.list_tools()]
        raise ValueError(f"Unsupported tool surface format: {format}")

    def execute_tool(
        self,
        name: str,
        arguments: Any,
        context: Optional[ToolAccessContext] = None,
        *,
        dispatch_guard: Optional[
            Callable[[ToolDefinition], Optional[ToolDispatchRejection]]
        ] = None,
    ) -> Dict[str, Any]:
        """Execute one registered tool by exact name and return structured output."""
        ctx = context or ToolAccessContext()
        started_at = time.time()
        started_monotonic = time.monotonic()
        dispatch_deadline = _effective_dispatch_deadline(ctx, started_monotonic)
        tool_name = name if type(name) is str else ""
        if not tool_name.strip():
            return self._error_result(
                tool_name="",
                code="invalid_tool_name",
                message="Tool name must exactly match a registered StockPulse tool.",
                started_at=started_at,
                context=ctx,
                retriable=False,
                arguments=arguments,
            )
        tool_def = self._registry.resolve(tool_name)

        if tool_def is None:
            if isinstance(name, str) and (":" in name or "." in name):
                return self._error_result(
                    tool_name=tool_name,
                    code="invalid_tool_name",
                    message="Tool name must exactly match a registered StockPulse tool.",
                    started_at=started_at,
                    context=ctx,
                    retriable=False,
                    arguments=arguments,
                )
            return self._error_result(
                tool_name=tool_name,
                code="tool_not_found",
                message="Tool not found.",
                started_at=started_at,
                context=ctx,
                retriable=False,
                arguments=arguments,
            )

        capability_error = validate_tool_capability_contract(tool_def)
        if capability_error is not None:
            return self._error_result(
                tool_name=tool_name,
                code=capability_error["code"],
                message=capability_error["message"],
                started_at=started_at,
                context=ctx,
                retriable=False,
                details=capability_error["details"],
                arguments=arguments,
            )

        required_capabilities = frozenset(tool_def.policy.permissions)
        granted_capabilities = _normalized_granted_capabilities(ctx)
        missing_capabilities = required_capabilities - granted_capabilities
        if missing_capabilities:
            required = sorted(required_capabilities)
            missing = sorted(missing_capabilities)
            return self._error_result(
                tool_name=tool_name,
                code="permission_denied",
                message="Execution context lacks required tool capabilities.",
                started_at=started_at,
                context=ctx,
                retriable=False,
                details={
                    "required_capabilities": required,
                    "missing_capabilities": missing,
                    # Compatibility aliases for existing session consumers.
                    "required_permissions": required,
                    "missing_permissions": missing,
                },
                arguments=arguments,
            )

        schema_contract_error = validate_tool_schema_contract(tool_def)
        if schema_contract_error is not None:
            return self._error_result(
                tool_name=tool_name,
                code=schema_contract_error["code"],
                message=schema_contract_error["message"],
                started_at=started_at,
                context=ctx,
                retriable=False,
                details=schema_contract_error["details"],
                arguments=arguments,
            )

        if isinstance(arguments, dict):
            bounded_arguments = _bounded_tool_arguments(
                arguments,
                normalize_stock_code=False,
            )
            if bounded_arguments is None:
                return self._error_result(
                    tool_name=tool_name,
                    code="invalid_arguments",
                    message="Tool arguments exceed security inspection limits.",
                    started_at=started_at,
                    context=ctx,
                    retriable=False,
                    details={"reason": "inspection_limit"},
                    arguments=arguments,
                )
            arguments = bounded_arguments

        arguments = _materialize_optional_defaults(tool_def, arguments)
        validation_error = _validate_arguments(tool_def, arguments)
        if validation_error is not None:
            return self._error_result(
                tool_name=tool_name,
                code="invalid_arguments",
                message=validation_error,
                started_at=started_at,
                context=ctx,
                retriable=False,
                arguments=arguments,
            )

        scope_contract_error = _validate_scope_contract(tool_def)
        if scope_contract_error is not None:
            return self._error_result(
                tool_name=tool_name,
                code="scope_contract_violation",
                message=scope_contract_error["message"],
                started_at=started_at,
                context=ctx,
                retriable=False,
                details=scope_contract_error["details"],
                arguments=arguments,
            )

        guard_result = None
        if _requires_stock_scope(tool_def):
            if ctx.stock_scope is None:
                return self._error_result(
                    tool_name=tool_name,
                    code="stock_scope_violation",
                    message="Tool call requires an explicit stock scope.",
                    started_at=started_at,
                    context=ctx,
                    retriable=False,
                    details={
                        "reason": "stock_scope_required",
                        "scope_dimensions": list(tool_def.policy.scope_dimensions),
                    },
                    arguments=arguments,
                )
            guard_result = _guard_tool_definition_stock_scope(
                tool_def,
                arguments,
                ctx.stock_scope,
            )
        if guard_result is not None:
            result_text = serialize_tool_result(guard_result)
            return self._error_result(
                tool_name=tool_name,
                code="stock_scope_violation",
                message="Tool call is outside the allowed stock scope.",
                started_at=started_at,
                context=ctx,
                retriable=False,
                details={
                    "expected_stock_code": guard_result.get("expected_stock_code"),
                    "requested_stock_code": guard_result.get("requested_stock_code"),
                    "allowed_stock_codes": guard_result.get("allowed_stock_codes", []),
                },
                result_text=result_text,
                arguments=arguments,
            )

        execution_fence_error = _execution_fence_error(ctx, dispatch_deadline)
        if execution_fence_error is not None:
            return self._error_result(
                tool_name=tool_name,
                code=execution_fence_error["code"],
                message=execution_fence_error["message"],
                started_at=started_at,
                context=ctx,
                retriable=execution_fence_error["retriable"],
                details=execution_fence_error["details"],
                arguments=arguments,
            )

        outbound_error = _validate_outbound_arguments(arguments)
        if outbound_error is not None:
            return self._error_result(
                tool_name=tool_name,
                code=outbound_error["code"],
                message=outbound_error["message"],
                started_at=started_at,
                context=ctx,
                retriable=False,
                details=outbound_error["details"],
                arguments=arguments,
            )

        execution_fence_error = _execution_fence_error(ctx, dispatch_deadline)
        if execution_fence_error is not None:
            return self._error_result(
                tool_name=tool_name,
                code=execution_fence_error["code"],
                message=execution_fence_error["message"],
                started_at=started_at,
                context=ctx,
                retriable=execution_fence_error["retriable"],
                details=execution_fence_error["details"],
                arguments=arguments,
            )

        if self._registry.resolve(tool_name) is not tool_def:
            return self._error_result(
                tool_name=tool_name,
                code="tool_not_found",
                message="Tool definition changed before dispatch.",
                started_at=started_at,
                context=ctx,
                retriable=False,
                details={"reason": "definition_changed"},
                arguments=arguments,
            )

        if dispatch_guard is not None:
            dispatch_rejection = dispatch_guard(tool_def)
            if dispatch_rejection is not None:
                code, message, details = dispatch_rejection
                return self._error_result(
                    tool_name=tool_name,
                    code=code,
                    message=message,
                    started_at=started_at,
                    context=ctx,
                    retriable=False,
                    details=details,
                    arguments=arguments,
                )

        def _invoke_handler() -> Any:
            if self._registry.resolve(tool_name) is not tool_def:
                raise _HandlerDispatchBlocked({
                    "code": "tool_not_found",
                    "message": "Tool definition changed before handler dispatch.",
                    "retriable": False,
                    "details": {
                        "reason": "definition_changed",
                        "handler_started": False,
                    },
                })
            fence_error = _execution_fence_error(ctx, dispatch_deadline)
            if fence_error is not None:
                raise _HandlerDispatchBlocked(fence_error)
            return tool_def.handler(**arguments)

        timeout = _remaining_dispatch_timeout(dispatch_deadline)
        try:
            if timeout is not None:
                result = _execute_with_timeout(_invoke_handler, timeout)
            else:
                result = _invoke_handler()
        except _HandlerDispatchBlocked as exc:
            return self._error_result(
                tool_name=tool_name,
                code=exc.error["code"],
                message=exc.error["message"],
                started_at=started_at,
                context=ctx,
                retriable=exc.error["retriable"],
                details=exc.error["details"],
                arguments=arguments,
            )
        except FuturesTimeoutError:
            timeout_label = f"{float(timeout or 0):.2f}s"
            return self._error_result(
                tool_name=tool_name,
                code="timeout",
                message=f"Tool execution timed out after {timeout_label}.",
                started_at=started_at,
                context=ctx,
                retriable=True,
                details={
                    "timeout_seconds": float(timeout or 0),
                    "cancel_requested": True,
                    "handler_may_continue": True,
                },
                arguments=arguments,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Normalize arbitrary tool failures to the audited handler_error contract.
            log_safe_exception(
                logger,
                "Agent tool execution failed",
                exc,
                error_code="agent_tool_execution_failed",
                level=logging.WARNING,
                context={"tool_name": tool_name},
                exception_redaction_values=exception_chain_redaction_values(exc),
            )
            return self._error_result(
                tool_name=tool_name,
                code="handler_error",
                message="Tool handler failed.",
                started_at=started_at,
                context=ctx,
                retriable=False,
                arguments=arguments,
            )

        try:
            result_text = serialize_tool_result(result)
        except Exception as exc:  # broad-exception: fallback_recorded - Normalize arbitrary result objects to an audited serialization error.
            log_safe_exception(
                logger,
                "Agent tool result serialization failed",
                exc,
                error_code="agent_tool_serialization_failed",
                level=logging.WARNING,
                context={"tool_name": tool_name},
                exception_redaction_values=exception_chain_redaction_values(exc),
            )
            return self._error_result(
                tool_name=tool_name,
                code="serialization_error",
                message="Tool result could not be serialized.",
                started_at=started_at,
                context=ctx,
                retriable=False,
                arguments=arguments,
            )

        public_result = _public_payload_from_result_text(result_text)
        result_truncated = False
        if ctx.max_result_bytes is not None and ctx.max_result_bytes >= 0:
            result_text, result_truncated = _truncate_text_bytes(result_text, int(ctx.max_result_bytes))
            public_result = None if result_truncated else _public_payload_from_result_text(result_text)

        duration = time.time() - started_at
        return {
            "ok": True,
            "tool_name": tool_name,
            "result": public_result,
            "result_text": result_text,
            "error": None,
            "audit": build_tool_audit(
                tool_name=tool_name,
                arguments=arguments,
                result=result_text,
                duration=duration,
                context=ctx,
            ),
            "diagnostics": {
                "redacted": True,
                "result_length": len(result_text.encode("utf-8")),
                "result_truncated": result_truncated,
                "preview": redact_diagnostic_value(result_text),
            },
        }

    def _error_result(
        self,
        *,
        tool_name: str,
        code: str,
        message: str,
        started_at: float,
        context: ToolAccessContext,
        retriable: bool,
        details: Optional[Dict[str, Any]] = None,
        result_text: Optional[str] = None,
        arguments: Any = None,
    ) -> Dict[str, Any]:
        return build_tool_error_result(
            tool_name=tool_name,
            code=code,
            message=message,
            started_at=started_at,
            context=context,
            retriable=retriable,
            details=details,
            result_text=result_text,
            arguments=arguments,
        )


def build_tool_error_result(
    *,
    tool_name: str,
    code: str,
    message: str,
    started_at: float,
    context: ToolAccessContext,
    retriable: bool,
    details: Optional[Dict[str, Any]] = None,
    result_text: Optional[str] = None,
    arguments: Any = None,
) -> Dict[str, Any]:
    """Build the shared structured error result used by ToolSurface and
    session-level gates so every rejection carries the same contract shape."""
    duration = time.time() - started_at
    safe_text = result_text or serialize_tool_error_result(
        message=message,
        code=code,
        retriable=retriable,
    )
    result_truncated = False
    if context.max_result_bytes is not None and context.max_result_bytes >= 0:
        safe_text, result_truncated = _truncate_text_bytes(safe_text, int(context.max_result_bytes))
    return {
        "ok": False,
        "tool_name": tool_name,
        "result": None,
        "result_text": safe_text,
        "error": {
            "code": code,
            "message": message,
            "retriable": retriable,
            "details": details or {},
        },
        "audit": build_tool_audit(
            tool_name=tool_name,
            arguments=_denial_audit_arguments(arguments),
            result={
                "denial_code": code,
                "result_redacted": True,
            },
            error_code=code,
            duration=duration,
            context=context,
        ),
        "diagnostics": {
            "redacted": True,
            "result_length": len(safe_text.encode("utf-8")),
            "result_truncated": result_truncated,
            "preview": redact_diagnostic_value({
                "denial_code": code,
                "result_redacted": True,
            }),
        },
    }


def _denial_audit_arguments(arguments: Any) -> Dict[str, Any]:
    """Describe rejected arguments without retaining any caller-controlled value."""
    if isinstance(arguments, dict):
        return {
            "argument_count": min(
                len(arguments),
                _MAX_TOOL_ARGUMENT_INSPECTION_NODES,
            ),
            "arguments_redacted": True,
        }
    return {
        "argument_count": 0,
        "arguments_redacted": True,
        "input_type": "non_object",
    }


def _effective_dispatch_deadline(
    context: ToolAccessContext,
    started_monotonic: float,
) -> Optional[float]:
    deadlines = []
    absolute = getattr(context, "deadline_monotonic", None)
    if absolute is not None:
        try:
            normalized_absolute = float(absolute)
        except (TypeError, ValueError):
            normalized_absolute = started_monotonic
        deadlines.append(
            normalized_absolute
            if math.isfinite(normalized_absolute)
            else started_monotonic
        )
    relative = context.timeout_seconds
    if relative is not None:
        try:
            normalized_relative = float(relative)
        except (TypeError, ValueError):
            normalized_relative = 0.0
        if not math.isfinite(normalized_relative):
            normalized_relative = 0.0
        deadlines.append(started_monotonic + max(0.0, normalized_relative))
    return min(deadlines) if deadlines else None


def _remaining_dispatch_timeout(
    deadline_monotonic: Optional[float],
) -> Optional[float]:
    if deadline_monotonic is None:
        return None
    return max(0.0, deadline_monotonic - time.monotonic())


def _execution_fence_error(
    context: ToolAccessContext,
    deadline_monotonic: Optional[float],
) -> Optional[Dict[str, Any]]:
    cancelled_check = getattr(context, "cancelled_check", None)
    if cancelled_check is not None:
        try:
            cancelled = bool(cancelled_check())
        except Exception:  # broad-exception: fallback_recorded - A broken cancellation probe fails closed before handler dispatch.
            logger.warning(
                "Agent tool cancellation probe failed closed "
                "error_code=agent_tool_cancellation_probe_failed"
            )
            cancelled = True
        if cancelled:
            return {
                "code": "cancelled",
                "message": "Execution cancellation was requested; tool call rejected.",
                "retriable": False,
                "details": {"handler_started": False},
            }
    if (
        deadline_monotonic is not None
        and time.monotonic() >= deadline_monotonic
    ):
        return {
            "code": "timeout",
            "message": "Tool execution deadline elapsed before handler dispatch.",
            "retriable": True,
            "details": {
                "cancel_requested": False,
                "handler_may_continue": False,
                "handler_started": False,
            },
        }
    return None


def _execute_with_timeout(handler: Callable[[], Any], timeout: float) -> Any:
    pool = ThreadPoolExecutor(max_workers=1)
    ctx = contextvars.copy_context()
    future = pool.submit(ctx.run, handler)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        future.cancel()
        raise
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _normalized_granted_capabilities(
    context: ToolAccessContext,
) -> frozenset[str]:
    raw = getattr(context, "granted_capabilities", frozenset())
    if not isinstance(raw, (set, frozenset, list, tuple)):
        return frozenset()
    return frozenset(
        value
        for value in raw
        if type(value) is str
        and value in SUPPORTED_AGENT_TOOL_CAPABILITIES
    )


def _is_url_argument_name(value: Any) -> bool:
    if type(value) is not str:
        return False
    normalized = value.strip().lower().replace("-", "_")
    compact = re.sub(r"[^a-z0-9]", "", normalized)
    compact_url_names = tuple(
        item.replace("_", "")
        for item in (*_URL_ARGUMENT_NAMES, *_URL_ARGUMENT_SUFFIXES)
    )
    return (
        normalized in _URL_ARGUMENT_NAMES
        or normalized.endswith(_URL_ARGUMENT_SUFFIXES)
        or compact in compact_url_names
        or compact.endswith(compact_url_names)
    )


def _validate_outbound_arguments(arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Route every URL-shaped argument through the shared outbound policy."""
    node_count = 0
    active_containers: set[int] = set()

    def _walk(value: Any, *, url_hint: bool, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if (
            depth > _MAX_TOOL_ARGUMENT_INSPECTION_DEPTH
            or node_count > _MAX_TOOL_ARGUMENT_INSPECTION_NODES
        ):
            raise ValueError("inspection_limit")

        if isinstance(value, str):
            candidate = value.strip()
            if url_hint or _ABSOLUTE_URL_PATTERN.match(candidate):
                validate_outbound_url(candidate)
            return

        if not isinstance(value, (dict, list, tuple)):
            return
        identity = id(value)
        if identity in active_containers:
            raise ValueError("cyclic_arguments")
        active_containers.add(identity)
        try:
            if isinstance(value, dict):
                for key, item in value.items():
                    if (
                        isinstance(key, str)
                        and _ABSOLUTE_URL_PATTERN.match(key.strip())
                    ):
                        validate_outbound_url(key.strip())
                    _walk(
                        item,
                        url_hint=url_hint or _is_url_argument_name(key),
                        depth=depth + 1,
                    )
            else:
                for item in value:
                    _walk(item, url_hint=url_hint, depth=depth + 1)
        finally:
            active_containers.remove(identity)

    try:
        _walk(arguments, url_hint=False, depth=0)
    except OutboundPolicyError as exc:
        return {
            "code": "outbound_url_denied",
            "message": "Tool URL argument was rejected by outbound security policy.",
            "details": {
                "reason": exc.reason,
                "correlation_id": exc.correlation_id,
            },
        }
    except ValueError as exc:
        return {
            "code": "invalid_arguments",
            "message": "Tool arguments exceed security inspection limits.",
            "details": {"reason": str(exc)},
        }
    return None


def _validate_arguments(tool_def: ToolDefinition, arguments: Any) -> Optional[str]:
    if not isinstance(arguments, dict):
        return "arguments must be an object"

    params = {param.name: param for param in tool_def.parameters}
    for param in tool_def.parameters:
        if param.required and param.name not in arguments:
            return f"missing required argument: {param.name}"

    accepts_extra = _handler_accepts_extra_kwargs(tool_def)
    for key in arguments:
        if key not in params and not accepts_extra:
            return "unexpected argument"

    for key, value in arguments.items():
        param = params.get(key)
        if param is None:
            continue
        error = validate_tool_parameter_value(param, value)
        if error:
            return error
    return None


def _materialize_optional_defaults(
    tool_def: ToolDefinition,
    arguments: Any,
) -> Any:
    if not isinstance(arguments, dict):
        return arguments
    effective = dict(arguments)
    for parameter in tool_def.parameters:
        if (
            not parameter.required
            and parameter.default is not None
            and parameter.name not in effective
        ):
            effective[parameter.name] = json.loads(
                json.dumps(parameter.default, allow_nan=False)
            )
    return effective


def _handler_accepts_extra_kwargs(tool_def: ToolDefinition) -> bool:
    return tool_def.accepts_extra_arguments()


def _requires_stock_scope(tool_def: ToolDefinition) -> bool:
    return "stock" in tool_def.policy.scope_dimensions


def _validate_scope_contract(tool_def: ToolDefinition) -> Optional[Dict[str, Any]]:
    raw_dimensions = tool_def.policy.scope_dimensions
    if type(raw_dimensions) is not list:
        return {
            "message": "Tool declares invalid scope metadata.",
            "details": {
                "invalid_scope_dimensions": ["invalid_collection"],
                "supported_scope_dimensions": sorted(
                    SUPPORTED_TOOL_SURFACE_SCOPE_DIMENSIONS
                ),
            },
        }
    invalid_dimensions = sorted({
        type(dimension).__name__
        for dimension in raw_dimensions
        if type(dimension) is not str
    })
    dimensions = [
        dimension
        for dimension in raw_dimensions
        if type(dimension) is str
    ]
    duplicate_dimensions = sorted({
        dimension
        for dimension in dimensions
        if dimensions.count(dimension) > 1
    })
    if invalid_dimensions or duplicate_dimensions:
        return {
            "message": "Tool declares invalid scope metadata.",
            "details": {
                "invalid_scope_dimensions": invalid_dimensions,
                "duplicate_scope_dimensions": duplicate_dimensions,
                "supported_scope_dimensions": sorted(
                    SUPPORTED_TOOL_SURFACE_SCOPE_DIMENSIONS
                ),
            },
        }
    stock_parameter = next(
        (
            param
            for param in tool_def.parameters
            if param.name == "stock_code"
        ),
        None,
    )
    has_stock_param = stock_parameter is not None
    declares_stock_scope = "stock" in dimensions
    unsupported = [
        dimension
        for dimension in dimensions
        if dimension not in SUPPORTED_TOOL_SURFACE_SCOPE_DIMENSIONS
    ]
    if unsupported:
        return {
            "message": "Tool declares scope dimensions that ToolSurface cannot enforce.",
            "details": {
                "scope_dimensions": dimensions,
                "unsupported_scope_dimensions": unsupported,
                "supported_scope_dimensions": sorted(SUPPORTED_TOOL_SURFACE_SCOPE_DIMENSIONS),
            },
        }
    if has_stock_param and not declares_stock_scope:
        return {
            "message": "Tool has stock_code parameter but does not declare stock scope.",
            "details": {
                "scope_dimensions": dimensions,
                "missing_scope_dimension": "stock",
            },
        }
    if declares_stock_scope and not has_stock_param:
        return {
            "message": "Tool declares stock scope but has no stock_code parameter.",
            "details": {
                "scope_dimensions": dimensions,
                "missing_parameter": "stock_code",
            },
        }
    if has_stock_param and (
        stock_parameter.type != "string" or stock_parameter.required is not True
    ):
        return {
            "message": "Tool stock scope requires a mandatory string stock_code.",
            "details": {
                "scope_dimensions": dimensions,
                "invalid_parameter": "stock_code",
            },
        }
    return None


def validate_tool_parameter_value(
    param: ToolParameter,
    value: Any,
) -> Optional[str]:
    """Return one stable validation error for a declared parameter value."""

    if value is None:
        return f"argument {param.name} must not be null"
    expected = _JSON_TYPE_TO_PYTHON.get(param.type)
    if expected and param.type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"argument {param.name} must be integer"
    elif expected and param.type == "number":
        if isinstance(value, bool) or not isinstance(value, expected):
            return f"argument {param.name} must be number"
    elif expected and not isinstance(value, expected):
        return f"argument {param.name} must be {param.type}"

    if param.enum and value not in param.enum:
        return f"argument {param.name} must be one of: {', '.join(map(str, param.enum))}"
    if param.pattern is not None and isinstance(value, str):
        try:
            pattern_matches = re.search(param.pattern, value) is not None
        except re.error:
            return f"argument {param.name} has an invalid schema pattern"
        if not pattern_matches:
            return f"argument {param.name} must match the required format"
    if param.type in {"integer", "number"}:
        if isinstance(value, float) and not math.isfinite(value):
            return f"argument {param.name} must be finite"
        if param.minimum is not None and value < param.minimum:
            return f"argument {param.name} must be >= {param.minimum:g}"
        if param.maximum is not None and value > param.maximum:
            return f"argument {param.name} must be <= {param.maximum:g}"
    return None


def _truncate_text_bytes(text: str, max_bytes: int) -> tuple[str, bool]:
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text, False
    if max_bytes <= 0:
        return "", True
    marker = "<truncated>"
    marker_bytes = marker.encode("utf-8")
    if max_bytes <= len(marker_bytes):
        return raw[:max_bytes].decode("utf-8", errors="ignore"), True
    prefix = raw[: max_bytes - len(marker_bytes)].decode("utf-8", errors="ignore")
    return f"{prefix}{marker}", True


def _public_payload_from_result_text(result_text: str) -> Any:
    try:
        return json.loads(result_text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return result_text
