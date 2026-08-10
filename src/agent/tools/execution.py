# -*- coding: utf-8 -*-
"""Shared agent-tool execution helpers.

This module is intentionally runtime-neutral.  It contains the existing
runner semantics that later Tool Surface / AgentBackend adapters can reuse
without importing the full ReAct loop.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Protocol,
)

if TYPE_CHECKING:
    from src.agent.runtime.tool_session import BoundToolSession
    from src.agent.stock_scope import StockScope

from src.agent.tools.registry import ToolRegistry
from src.utils.sanitize import redact_sensitive_data, redact_sensitive_text

logger = logging.getLogger(__name__)


class RunnerToolCall(Protocol):
    name: str
    arguments: Dict[str, Any]


RunnerToolCompletionGuard = Callable[[Callable[[], None]], None]
RunnerToolDispatchGuard = Callable[[Callable[[], None]], None]
_RUNNER_TOOL_COMPLETION_GUARD: ContextVar[Optional[RunnerToolCompletionGuard]] = (
    ContextVar("runner_tool_completion_guard", default=None)
)
_RUNNER_TOOL_DISPATCH_GUARD: ContextVar[Optional[RunnerToolDispatchGuard]] = (
    ContextVar("runner_tool_dispatch_guard", default=None)
)
_RUNNER_TOOL_DEADLINE_MONOTONIC: ContextVar[Optional[float]] = ContextVar(
    "runner_tool_deadline_monotonic",
    default=None,
)


@contextmanager
def bind_runner_tool_completion_guard(
    guard: RunnerToolCompletionGuard,
    *,
    dispatch_guard: Optional[RunnerToolDispatchGuard] = None,
    deadline_monotonic: Optional[float] = None,
) -> Iterator[None]:
    """Bind one runner timeout fence across dispatch and completion."""
    completion_token = _RUNNER_TOOL_COMPLETION_GUARD.set(guard)
    dispatch_token = _RUNNER_TOOL_DISPATCH_GUARD.set(dispatch_guard)
    deadline_token = _RUNNER_TOOL_DEADLINE_MONOTONIC.set(deadline_monotonic)
    try:
        yield
    finally:
        _RUNNER_TOOL_DEADLINE_MONOTONIC.reset(deadline_token)
        _RUNNER_TOOL_DISPATCH_GUARD.reset(dispatch_token)
        _RUNNER_TOOL_COMPLETION_GUARD.reset(completion_token)


_SUMMARY_LIMIT = 500
_HOME_PATH_PATTERN = re.compile(r"(/Users/[^/\s]+|/home/[^/\s]+)(/[^\s,;]*)?")
_MAX_TOOL_ARGUMENT_INSPECTION_DEPTH = 12
_MAX_TOOL_ARGUMENT_INSPECTION_NODES = 512
_MAX_TOOL_CACHE_TEXT_CHARS = 16_384
_MAX_UNTRUSTED_DOCUMENT_ARGUMENT_CHARS = 220_000
_CACHE_VALUE_UNAVAILABLE = object()
_UNTRUSTED_DOCUMENT_TOOL_NAMES = frozenset({"parse_earnings_transcript"})


@dataclass
class ToolAccessContext:
    """Execution context for Tool Surface calls."""

    stock_scope: Any = None
    market: Optional[str] = None
    time_range: Optional[dict] = None
    data_sources: Optional[List[str]] = None
    backend: Optional[str] = None
    session_id: Optional[str] = None
    timeout_seconds: Optional[float] = None
    deadline_monotonic: Optional[float] = None
    cancelled_check: Optional[Callable[[], bool]] = None
    max_result_bytes: Optional[int] = None
    audit_context: Dict[str, Any] = field(default_factory=dict)
    granted_capabilities: frozenset[str] = field(default_factory=frozenset)
    # Retained for call-site compatibility. Security contracts are always
    # enforced by ToolSurface; callers cannot use this field to bypass them.
    enforce_contract: bool = True


def serialize_tool_result(result: Any) -> str:
    """Serialize a tool result to a JSON string consumable by an LLM."""
    if result is None:
        return json.dumps({"result": None})
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(result)
    if hasattr(result, "__dict__"):
        try:
            d = {k: v for k, v in result.__dict__.items() if not k.startswith("_")}
            return json.dumps(d, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(result)
    return str(result)


def serialize_tool_error_result(*, message: str, code: str, retriable: bool) -> str:
    """Serialize the stable model-visible error contract shared by agent runtimes."""
    return serialize_tool_result({
        "error": message,
        "code": code,
        "retriable": retriable,
    })


def _normalize_tool_stock_code(value: Any) -> Any:
    """Canonicalize stock code arguments so equivalent HK variants share one cache key."""
    if not isinstance(value, str):
        return value

    text = value.strip().upper()
    if not text:
        return text

    if text.endswith(".HK"):
        base = text[:-3]
        if base.isdigit() and 1 <= len(base) <= 5:
            return f"HK{base.zfill(5)}"

    if text.startswith("HK"):
        base = text[2:]
        if base.isdigit() and 1 <= len(base) <= 5:
            return f"HK{base.zfill(5)}"

    if text.isdigit() and len(text) == 5:
        return f"HK{text}"

    try:
        from data_provider.base import canonical_stock_code, normalize_stock_code

        return canonical_stock_code(normalize_stock_code(text))
    except Exception:
        return text


def _build_tool_cache_key(tool_name: str, arguments: Dict[str, Any]) -> Optional[str]:
    """Build a stable cache key for tool calls with normalized stock-code arguments."""
    if not isinstance(arguments, dict):
        return None

    normalized_args = _bounded_tool_arguments(
        arguments,
        normalize_stock_code=True,
        max_text_chars=(
            _MAX_UNTRUSTED_DOCUMENT_ARGUMENT_CHARS
            if tool_name in _UNTRUSTED_DOCUMENT_TOOL_NAMES
            else _MAX_TOOL_CACHE_TEXT_CHARS
        ),
    )
    if normalized_args is None:
        return None

    try:
        payload = json.dumps(
            normalized_args,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
        )
    except (RecursionError, TypeError, ValueError):
        return None
    if tool_name in _UNTRUSTED_DOCUMENT_TOOL_NAMES:
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{tool_name}:sha256:{digest}"
    return f"{tool_name}:{payload}"


def _document_safe_arguments(tool_name: str, arguments: Any) -> Any:
    """Replace raw untrusted-document content before audit/diagnostic storage."""
    if tool_name not in _UNTRUSTED_DOCUMENT_TOOL_NAMES or not isinstance(arguments, dict):
        return arguments
    safe = dict(arguments)
    text_value = safe.get("text")
    if isinstance(text_value, str):
        safe["text"] = {
            "redacted": True,
            "char_count": len(text_value),
            "sha256": hashlib.sha256(text_value.encode("utf-8")).hexdigest(),
        }
    return safe


def _document_safe_result(tool_name: str, result: Any) -> Any:
    if tool_name not in _UNTRUSTED_DOCUMENT_TOOL_NAMES:
        return result
    parsed = result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except (TypeError, ValueError):
            return {"result_redacted": True}
    if not isinstance(parsed, dict):
        return {"result_redacted": True}
    source = parsed.get("source") if isinstance(parsed.get("source"), dict) else {}
    return {
        "schema_version": parsed.get("schema_version"),
        "status": parsed.get("status"),
        "reason_code": parsed.get("reason_code"),
        "content_sha256": source.get("content_sha256"),
        "text_char_count": parsed.get("text_char_count"),
        "result_redacted": True,
    }


def redact_tool_diagnostic_value(
    tool_name: str,
    value: Any,
    *,
    kind: str,
    limit: int = _SUMMARY_LIMIT,
) -> str:
    safe = (
        _document_safe_arguments(tool_name, value)
        if kind == "arguments"
        else _document_safe_result(tool_name, value)
    )
    return redact_diagnostic_value(safe, limit=limit)


def _bounded_tool_arguments(
    arguments: Dict[str, Any],
    *,
    normalize_stock_code: bool,
    max_text_chars: int = _MAX_TOOL_CACHE_TEXT_CHARS,
) -> Optional[Dict[str, Any]]:
    """Copy JSON arguments within the shared ToolSurface inspection bounds."""
    node_count = 0
    text_chars = 0
    active_containers: set[int] = set()

    def _copy(value: Any, *, depth: int) -> Any:
        nonlocal node_count, text_chars
        node_count += 1
        if (
            depth > _MAX_TOOL_ARGUMENT_INSPECTION_DEPTH
            or node_count > _MAX_TOOL_ARGUMENT_INSPECTION_NODES
        ):
            return _CACHE_VALUE_UNAVAILABLE
        if value is None or type(value) in {bool, int}:
            if type(value) is int and value.bit_length() > 4096:
                return _CACHE_VALUE_UNAVAILABLE
            return value
        if type(value) is float:
            return value if math.isfinite(value) else _CACHE_VALUE_UNAVAILABLE
        if type(value) is str:
            text_chars += len(value)
            return (
                value
                if text_chars <= max_text_chars
                else _CACHE_VALUE_UNAVAILABLE
            )
        if type(value) not in {dict, list}:
            return _CACHE_VALUE_UNAVAILABLE

        identity = id(value)
        if identity in active_containers:
            return _CACHE_VALUE_UNAVAILABLE
        active_containers.add(identity)
        try:
            if type(value) is list:
                copied_list = []
                for item in value:
                    copied_item = _copy(item, depth=depth + 1)
                    if copied_item is _CACHE_VALUE_UNAVAILABLE:
                        return _CACHE_VALUE_UNAVAILABLE
                    copied_list.append(copied_item)
                return copied_list

            copied_dict: Dict[str, Any] = {}
            for key, item in value.items():
                if type(key) is not str:
                    return _CACHE_VALUE_UNAVAILABLE
                text_chars += len(key)
                if text_chars > max_text_chars:
                    return _CACHE_VALUE_UNAVAILABLE
                copied_item = _copy(item, depth=depth + 1)
                if copied_item is _CACHE_VALUE_UNAVAILABLE:
                    return _CACHE_VALUE_UNAVAILABLE
                copied_dict[key] = (
                    _normalize_tool_stock_code(copied_item)
                    if (
                        normalize_stock_code
                        and depth == 0
                        and key == "stock_code"
                    )
                    else copied_item
                )
            return copied_dict
        finally:
            active_containers.remove(identity)

    copied = _copy(arguments, depth=0)
    return copied if type(copied) is dict else None


def _is_non_retriable_tool_result(result: Any) -> bool:
    """Return True when a tool result explicitly tells the agent not to retry."""
    return (
        isinstance(result, dict)
        and bool(result.get("error"))
        and result.get("retriable") is False
    )


def _is_stock_scoped_tool(tool_registry: ToolRegistry, tool_name: str) -> bool:
    tool_def = tool_registry.resolve(tool_name)
    if tool_def is None:
        return False
    return any(param.name == "stock_code" for param in tool_def.parameters)


def _normalize_guard_stock_code(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    raw = value if isinstance(value, str) else str(value)
    normalized = _normalize_tool_stock_code(raw)
    return normalized if isinstance(normalized, str) else str(normalized)


def _iter_allowed_stock_codes(stock_scope: Any) -> Iterable[Any]:
    return getattr(stock_scope, "allowed_stock_codes", set()) or set()


def _guard_tool_stock_scope(
    tool_registry: ToolRegistry,
    tool_name: str,
    arguments: Dict[str, Any],
    stock_scope: Optional[StockScope],
) -> Optional[Dict[str, Any]]:
    return _guard_tool_definition_stock_scope(
        tool_registry.resolve(tool_name),
        arguments,
        stock_scope,
    )


def _guard_tool_definition_stock_scope(
    tool_def: Any,
    arguments: Dict[str, Any],
    stock_scope: Optional[StockScope],
) -> Optional[Dict[str, Any]]:
    """Guard one captured definition without re-resolving a mutable registry."""
    if stock_scope is None or not isinstance(arguments, dict):
        return None
    if tool_def is None or not any(
        param.name == "stock_code"
        for param in getattr(tool_def, "parameters", ())
    ):
        return None
    if "stock_code" not in arguments:
        return None

    requested = _normalize_guard_stock_code(arguments.get("stock_code"))
    expected = _normalize_guard_stock_code(getattr(stock_scope, "expected_stock_code", ""))
    allowed = {
        normalized
        for code in _iter_allowed_stock_codes(stock_scope)
        for normalized in [_normalize_guard_stock_code(code)]
        if normalized
    }
    if requested and (requested == expected or requested in allowed):
        return None

    return {
        "error": "stock_scope_violation",
        "expected_stock_code": expected,
        "requested_stock_code": requested,
        "allowed_stock_codes": sorted(allowed),
        "retriable": False,
    }


def execute_runner_tool_call_via_session(
    tool_call: RunnerToolCall,
    session: "BoundToolSession",
) -> tuple[Any, str, bool, float, bool, Optional[Dict[str, Any]]]:
    """Single migration mapper: dispatch one runner tool call through the
    ``BoundToolSession`` authority and adapt its dict result to the 6-tuple the
    runner loop consumes: ``(tool_call, res_str, ok, dur, cached, guard_result)``.

    This is the only bridge between the native runner and the bound session; it
    never touches the tool registry directly, so ToolSurface remains the single
    tool-dispatch authority. The session applies its frozen allowlist and grants
    before ToolSurface enforces capability, schema, scope, and outbound policy.
    The serialized ``result_text`` uses the shared
    :func:`serialize_tool_result` / :func:`serialize_tool_error_result`
    helpers.
    """
    t0 = time.time()
    name = tool_call.name
    arguments = tool_call.arguments
    bounded_arguments = (
        _bounded_tool_arguments(
            arguments,
            normalize_stock_code=False,
        )
        if isinstance(arguments, dict)
        else None
    )
    safe_arguments = redact_sensitive_data(
        _document_safe_arguments(name if isinstance(name, str) else "", bounded_arguments)
        if bounded_arguments is not None
        else {"arguments_redacted": True}
    )
    tool_call.arguments = (
        safe_arguments if isinstance(safe_arguments, dict) else {}
    )
    # Coerce exactly like the session/surface so a non-string name never leaks
    # its ``__str__`` into a cache key or log line.
    tool_name = name if isinstance(name, str) else ""
    cache_key = (
        _build_tool_cache_key(tool_name, arguments)
        if isinstance(arguments, dict)
        else None
    )
    # Mirror the legacy semantics of reporting ``cached`` for a non-retriable
    # memo that already existed *before* this dispatch.
    cached = bool(cache_key) and session.is_non_retriable_cached(cache_key)

    completion_guard = _RUNNER_TOOL_COMPLETION_GUARD.get()
    dispatch_guard = _RUNNER_TOOL_DISPATCH_GUARD.get()
    call_deadline_monotonic = _RUNNER_TOOL_DEADLINE_MONOTONIC.get()
    if (
        completion_guard is None
        and dispatch_guard is None
        and call_deadline_monotonic is None
    ):
        result = session.execute(name, arguments)
    else:
        completion_token = _RUNNER_TOOL_COMPLETION_GUARD.set(None)
        dispatch_token = _RUNNER_TOOL_DISPATCH_GUARD.set(None)
        deadline_token = _RUNNER_TOOL_DEADLINE_MONOTONIC.set(None)
        try:
            result = session.execute(
                name,
                arguments,
                dispatch_guard=dispatch_guard,
                completion_guard=completion_guard,
                call_deadline_monotonic=call_deadline_monotonic,
            )
        finally:
            _RUNNER_TOOL_DEADLINE_MONOTONIC.reset(deadline_token)
            _RUNNER_TOOL_DISPATCH_GUARD.reset(dispatch_token)
            _RUNNER_TOOL_COMPLETION_GUARD.reset(completion_token)

    res_str = result["result_text"]
    # A non-retriable cache hit is reported as a non-success skip, exactly like
    # the legacy direct path (it short-circuited with ``ok=False`` regardless of
    # the memoized result's original outcome).
    ok = False if cached else bool(result["ok"])
    dur = round(time.time() - t0, 2)

    guard_result: Optional[Dict[str, Any]] = None
    if not cached:
        error = result.get("error") or {}
        if error.get("code") == "stock_scope_violation":
            details = error.get("details") or {}
            # Reconstruct the runner log_entry contract (guarded fields) from
            # the structured surface error details.
            guard_result = {
                "error": "stock_scope_violation",
                "expected_stock_code": details.get("expected_stock_code", ""),
                "requested_stock_code": details.get("requested_stock_code", ""),
                "allowed_stock_codes": details.get("allowed_stock_codes", []),
                "retriable": False,
            }
    return tool_call, res_str, ok, dur, cached, guard_result


def redact_diagnostic_value(value: Any, *, limit: int = _SUMMARY_LIMIT) -> str:
    """Return a redacted and truncated diagnostic preview."""
    try:
        redacted = redact_sensitive_data(value, redact_opaque_tokens=True)
        text = (
            redacted
            if isinstance(redacted, str)
            else json.dumps(redacted, ensure_ascii=False, default=str)
        )
    except Exception:  # broad-exception: optional_metadata - Audit preview degrades to a fixed marker.
        try:
            text = redact_sensitive_text(
                value,
                redact_opaque_tokens=True,
            )
        except Exception:  # broad-exception: optional_metadata - Hostile audit values use a fixed marker.
            text = "<unserializable>"

    text = redact_sensitive_text(text, redact_opaque_tokens=True)
    text = _HOME_PATH_PATTERN.sub(lambda m: f"{m.group(1).rsplit('/', 1)[0] if '/' in m.group(1) else m.group(1)}/[REDACTED_PATH]", text)
    if len(text) > limit:
        return f"{text[:limit]}...<truncated {len(text) - limit} chars>"
    return text


def build_tool_audit(
    *,
    tool_name: str,
    arguments: Any,
    result: Any = None,
    error_code: Optional[str] = None,
    duration: float = 0.0,
    context: Optional[ToolAccessContext] = None,
) -> Dict[str, Any]:
    """Build a redacted Tool Surface audit record."""
    ctx = context or ToolAccessContext()
    payload = {
        "tool_name": tool_name,
        "arguments_summary": redact_tool_diagnostic_value(
            tool_name, arguments, kind="arguments"
        ),
        "duration": round(duration, 4),
        "result_summary": redact_tool_diagnostic_value(
            tool_name, result, kind="result"
        ),
        "error_code": error_code,
        "backend": ctx.backend,
        "session_id": ctx.session_id,
    }
    if ctx.audit_context:
        payload["audit_context"] = redact_diagnostic_value(ctx.audit_context)
    return redact_sensitive_data(payload)
