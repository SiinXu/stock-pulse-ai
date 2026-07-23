# -*- coding: utf-8 -*-
"""Shared agent-tool execution helpers.

This module is intentionally runtime-neutral.  It contains the existing
runner semantics that later Tool Surface / AgentBackend adapters can reuse
without importing the full ReAct loop.
"""

from __future__ import annotations

import json
import logging
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
_RUNNER_TOOL_COMPLETION_GUARD: ContextVar[Optional[RunnerToolCompletionGuard]] = (
    ContextVar("runner_tool_completion_guard", default=None)
)


@contextmanager
def bind_runner_tool_completion_guard(
    guard: RunnerToolCompletionGuard,
) -> Iterator[None]:
    """Bind one dispatch completion fence without changing the bridge API."""
    token = _RUNNER_TOOL_COMPLETION_GUARD.set(guard)
    try:
        yield
    finally:
        _RUNNER_TOOL_COMPLETION_GUARD.reset(token)


_SUMMARY_LIMIT = 500
_HOME_PATH_PATTERN = re.compile(r"(/Users/[^/\s]+|/home/[^/\s]+)(/[^\s,;]*)?")


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
    max_result_bytes: Optional[int] = None
    audit_context: Dict[str, Any] = field(default_factory=dict)
    # When False the surface skips its declared-contract validation (argument
    # schema + scope-dimension contract) and applies the legacy stock-scope
    # guard keyed on the presence of a ``stock_code`` parameter. This mirrors
    # the historical native runner path byte-for-byte so the same
    # ``BoundToolSession`` authority can serve native replay without the
    # stricter checks reserved for external runtimes.
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

    normalized_args: Dict[str, Any] = {}
    for key, value in arguments.items():
        if key == "stock_code":
            normalized_args[key] = _normalize_tool_stock_code(value)
        else:
            normalized_args[key] = value

    try:
        payload = json.dumps(normalized_args, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return None
    return f"{tool_name}:{payload}"


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
    if stock_scope is None or not isinstance(arguments, dict):
        return None
    if not _is_stock_scoped_tool(tool_registry, tool_name):
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
    never touches the tool registry directly, so the session remains the single
    tool-dispatch authority. Byte-exactness with the historical direct path is
    preserved because the session runs in native-compatibility mode (see
    :class:`~src.agent.runtime.tool_session.BoundToolSession`): the serialized
    ``result_text`` is produced by the same :func:`serialize_tool_result` /
    :func:`serialize_tool_error_result` helpers on the same inputs.
    """
    t0 = time.time()
    name = tool_call.name
    arguments = tool_call.arguments
    safe_name = redact_sensitive_text(name) if isinstance(name, str) else ""
    tool_call.name = safe_name
    safe_arguments = redact_sensitive_data(arguments)
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
    if completion_guard is None:
        result = session.execute(name, arguments)
    else:
        token = _RUNNER_TOOL_COMPLETION_GUARD.set(None)
        try:
            result = session.execute(
                name,
                arguments,
                completion_guard=completion_guard,
            )
        finally:
            _RUNNER_TOOL_COMPLETION_GUARD.reset(token)

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
        "arguments_summary": redact_diagnostic_value(arguments),
        "duration": round(duration, 4),
        "result_summary": redact_diagnostic_value(result),
        "error_code": error_code,
        "backend": ctx.backend,
        "session_id": ctx.session_id,
    }
    if ctx.audit_context:
        payload["audit_context"] = redact_diagnostic_value(ctx.audit_context)
    return redact_sensitive_data(payload)
