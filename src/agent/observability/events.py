# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Structured agent run events (L0) with trace/span correlation.

Design goals:
- Cheap by default: small sanitized attrs only, bounded list size.
- Fail-open: emit helpers never raise into the agent control flow.
- Reuse run-diagnostics context + flow event sink for persistence and live UI.
- Deep payloads (arguments / result previews) only when explicitly enabled.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Mapping, Optional

from src.services.run_diagnostics import (
    get_current_diagnostic_context,
    sanitize_diagnostic_text,
)
from src.utils.sanitize import is_sensitive_key, log_safe_exception, redact_sensitive_data

logger = logging.getLogger(__name__)

AGENT_EVENT_SCHEMA_VERSION = 1
DEFAULT_MAX_AGENT_EVENTS = 200
_DEEP_PAYLOAD_MAX_CHARS = 400

_BLOCKED_DEEP_KEYS = frozenset(
    {
        "prompt",
        "system_prompt",
        "messages",
        "content",
        "api_key",
        "apikey",
        "authorization",
        "token",
        "secret",
        "password",
        "raw_response",
        "completion",
        "input_text",
        "output_text",
    }
)


class AgentEventType(str, Enum):
    """Stable agent observability event types for L0."""

    PHASE_START = "agent.phase_start"
    PHASE_END = "agent.phase_end"
    TOOL_START = "agent.tool_start"
    TOOL_END = "agent.tool_end"
    MODEL_START = "agent.model_start"
    MODEL_END = "agent.model_end"
    DECISION = "agent.decision"
    ERROR = "agent.error"


@dataclass(frozen=True)
class AgentRunEvent:
    """One structured agent run event with trace/span correlation."""

    event_type: str
    trace_id: str
    span_id: str
    sequence: int
    timestamp: str
    name: str
    parent_span_id: Optional[str] = None
    phase: Optional[str] = None
    status: Optional[str] = None
    duration_ms: Optional[int] = None
    step: Optional[int] = None
    attrs: Mapping[str, Any] = field(default_factory=dict)
    payload: Optional[Mapping[str, Any]] = None
    schema_version: int = AGENT_EVENT_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "name": self.name,
        }
        if self.parent_span_id:
            data["parent_span_id"] = self.parent_span_id
        if self.phase:
            data["phase"] = self.phase
        if self.status:
            data["status"] = self.status
        if self.duration_ms is not None:
            data["duration_ms"] = int(self.duration_ms)
        if self.step is not None:
            data["step"] = int(self.step)
        if self.attrs:
            data["attrs"] = dict(self.attrs)
        if self.payload:
            data["payload"] = dict(self.payload)
        return data


_SPAN_STACK: ContextVar[tuple[str, ...]] = ContextVar(
    "agent_observability_span_stack",
    default=(),
)
_OPEN_SPANS: ContextVar[Dict[str, float]] = ContextVar(
    "agent_observability_open_spans",
    default={},
)
_LOCK = threading.Lock()


def build_span_id() -> str:
    """Return a compact span id suitable for correlation metadata."""
    return uuid.uuid4().hex[:16]


def is_agent_observability_enabled() -> bool:
    """Return whether lightweight agent events should be recorded (default on)."""
    try:
        from src.config import get_config

        config = get_config()
        return bool(getattr(config, "agent_observability_enabled", True))
    except Exception:  # broad-exception: fallback_recorded - Config lookup must not block analysis.
        return True


def is_deep_payload_enabled() -> bool:
    """Return whether deep payload capture is enabled (default off)."""
    try:
        from src.config import get_config

        config = get_config()
        return bool(getattr(config, "agent_observability_deep_payload", False))
    except Exception:  # broad-exception: fallback_recorded - Config lookup must not block analysis.
        return False


def sanitize_agent_event_payload(
    value: Any,
    *,
    deep: bool = False,
    depth: int = 0,
) -> Any:
    """Sanitize event attrs/payloads; strip prompts/keys and bound depth/size."""
    if depth > 3:
        return "<truncated>"
    if value is None:
        return None
    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 20:
                out["truncated"] = True
                break
            key_text = str(key)
            safe_key = sanitize_diagnostic_text(key_text, max_length=64) or f"k{index}"
            lowered = key_text.strip().lower().replace("-", "_")
            if is_sensitive_key(key_text) or lowered in _BLOCKED_DEEP_KEYS:
                out[safe_key] = "<redacted>"
                continue
            if not deep and lowered in {"arguments", "result", "result_preview", "messages"}:
                continue
            out[safe_key] = sanitize_agent_event_payload(item, deep=deep, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        items = [
            sanitize_agent_event_payload(item, deep=deep, depth=depth + 1)
            for item in list(value)[:8]
        ]
        return [item for item in items if item not in (None, "", [], {})]
    if isinstance(value, (int, float, bool)):
        return value
    text = sanitize_diagnostic_text(value, max_length=_DEEP_PAYLOAD_MAX_CHARS if deep else 160)
    if text is None:
        return None
    redacted = redact_sensitive_data(text)
    if isinstance(redacted, str):
        return redacted[: _DEEP_PAYLOAD_MAX_CHARS if deep else 160]
    return text


def _current_parent_span_id() -> Optional[str]:
    stack = _SPAN_STACK.get()
    return stack[-1] if stack else None


def _push_span(span_id: str) -> None:
    stack = _SPAN_STACK.get()
    _SPAN_STACK.set(stack + (span_id,))
    open_spans = dict(_OPEN_SPANS.get())
    open_spans[span_id] = time.perf_counter()
    _OPEN_SPANS.set(open_spans)


def _pop_span(span_id: Optional[str] = None) -> tuple[Optional[str], Optional[int]]:
    stack = list(_SPAN_STACK.get())
    open_spans = dict(_OPEN_SPANS.get())
    if not stack:
        return None, None
    if span_id and span_id in stack:
        while stack and stack[-1] != span_id:
            child = stack.pop()
            open_spans.pop(child, None)
        if stack and stack[-1] == span_id:
            stack.pop()
        started = open_spans.pop(span_id, None)
    else:
        span_id = stack.pop()
        started = open_spans.pop(span_id, None)
    _SPAN_STACK.set(tuple(stack))
    _OPEN_SPANS.set(open_spans)
    if started is None:
        return span_id, None
    return span_id, max(0, int((time.perf_counter() - started) * 1000))


def emit_agent_event(
    event_type: AgentEventType | str,
    *,
    name: str,
    span_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    phase: Optional[str] = None,
    status: Optional[str] = None,
    duration_ms: Optional[int] = None,
    step: Optional[int] = None,
    attrs: Optional[Mapping[str, Any]] = None,
    payload: Optional[Mapping[str, Any]] = None,
    push_span: bool = False,
    pop_span: bool = False,
) -> Optional[AgentRunEvent]:
    """Record one agent event into the active diagnostic context (fail-open)."""
    if not is_agent_observability_enabled():
        return None
    try:
        return _emit_agent_event_impl(
            event_type,
            name=name,
            span_id=span_id,
            parent_span_id=parent_span_id,
            phase=phase,
            status=status,
            duration_ms=duration_ms,
            step=step,
            attrs=attrs,
            payload=payload,
            push_span=push_span,
            pop_span=pop_span,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - Observability must never break analysis.
        log_safe_exception(
            logger,
            "Agent observability emit failed",
            exc,
            error_code="agent_observability_emit_failed",
            level=logging.DEBUG,
            context={"event_type": str(event_type), "name": str(name)[:80]},
        )
        return None


def _emit_agent_event_impl(
    event_type: AgentEventType | str,
    *,
    name: str,
    span_id: Optional[str],
    parent_span_id: Optional[str],
    phase: Optional[str],
    status: Optional[str],
    duration_ms: Optional[int],
    step: Optional[int],
    attrs: Optional[Mapping[str, Any]],
    payload: Optional[Mapping[str, Any]],
    push_span: bool,
    pop_span: bool,
) -> Optional[AgentRunEvent]:
    context = get_current_diagnostic_context()
    if context is None:
        return None

    type_value = (
        event_type.value if isinstance(event_type, AgentEventType) else str(event_type or "").strip()
    )
    if not type_value:
        return None

    safe_name = sanitize_diagnostic_text(name, max_length=80) or "unknown"
    resolved_span = span_id or build_span_id()
    resolved_parent = parent_span_id if parent_span_id is not None else _current_parent_span_id()
    resolved_duration = duration_ms

    if pop_span:
        closed_span, measured = _pop_span(resolved_span if span_id else None)
        if closed_span:
            resolved_span = closed_span
        if resolved_duration is None:
            resolved_duration = measured
    elif push_span:
        _push_span(resolved_span)

    deep = is_deep_payload_enabled()
    safe_attrs = sanitize_agent_event_payload(dict(attrs or {}), deep=False)
    if not isinstance(safe_attrs, dict):
        safe_attrs = {}
    safe_payload = None
    if deep and payload:
        candidate = sanitize_agent_event_payload(dict(payload), deep=True)
        if isinstance(candidate, dict) and candidate:
            safe_payload = candidate

    with _LOCK:
        sequence = int(getattr(context, "agent_event_index", 0)) + 1
        context.agent_event_index = sequence  # type: ignore[attr-defined]

    event = AgentRunEvent(
        event_type=type_value,
        trace_id=str(context.trace_id),
        span_id=resolved_span,
        parent_span_id=resolved_parent,
        sequence=sequence,
        timestamp=datetime.now().isoformat(),
        name=safe_name,
        phase=sanitize_diagnostic_text(phase, max_length=64) if phase else None,
        status=sanitize_diagnostic_text(status, max_length=32) if status else None,
        duration_ms=resolved_duration,
        step=step,
        attrs=safe_attrs if isinstance(safe_attrs, dict) else {},
        payload=safe_payload,
    )

    record = getattr(context, "record_agent_event", None)
    if callable(record):
        record(event.to_dict())
    else:
        events = getattr(context, "agent_events", None)
        if isinstance(events, list):
            events.append(event.to_dict())
            while len(events) > DEFAULT_MAX_AGENT_EVENTS:
                events.pop(0)
    return event


def emit_phase_start(
    phase: str,
    *,
    step: Optional[int] = None,
    attrs: Optional[Mapping[str, Any]] = None,
) -> Optional[AgentRunEvent]:
    """Emit phase start and push a span for nested tool/model events."""
    span_id = build_span_id()
    return emit_agent_event(
        AgentEventType.PHASE_START,
        name=phase,
        span_id=span_id,
        phase=phase,
        status="running",
        step=step,
        attrs=attrs,
        push_span=True,
    )


def emit_phase_end(
    phase: str,
    *,
    status: str = "success",
    duration_ms: Optional[int] = None,
    step: Optional[int] = None,
    attrs: Optional[Mapping[str, Any]] = None,
) -> Optional[AgentRunEvent]:
    """Emit phase end and pop the matching span."""
    return emit_agent_event(
        AgentEventType.PHASE_END,
        name=phase,
        phase=phase,
        status=status,
        duration_ms=duration_ms,
        step=step,
        attrs=attrs,
        pop_span=True,
    )


def emit_tool_start(
    tool: str,
    *,
    step: Optional[int] = None,
    attrs: Optional[Mapping[str, Any]] = None,
    payload: Optional[Mapping[str, Any]] = None,
) -> Optional[AgentRunEvent]:
    """Emit tool call start."""
    span_id = build_span_id()
    return emit_agent_event(
        AgentEventType.TOOL_START,
        name=tool,
        span_id=span_id,
        status="running",
        step=step,
        attrs=attrs,
        payload=payload,
        push_span=True,
    )


def emit_tool_end(
    tool: str,
    *,
    success: bool,
    duration_ms: Optional[int] = None,
    step: Optional[int] = None,
    span_id: Optional[str] = None,
    attrs: Optional[Mapping[str, Any]] = None,
    payload: Optional[Mapping[str, Any]] = None,
) -> Optional[AgentRunEvent]:
    """Emit tool call end.

    Pass ``span_id`` from the matching :func:`emit_tool_start` result so
    parallel tool completions do not depend on LIFO stack order.
    """
    return emit_agent_event(
        AgentEventType.TOOL_END,
        name=tool,
        span_id=span_id,
        status="success" if success else "failed",
        duration_ms=duration_ms,
        step=step,
        attrs={**(dict(attrs or {})), "success": bool(success)},
        payload=payload,
        pop_span=True,
    )


def emit_model_start(
    model: str = "model",
    *,
    step: Optional[int] = None,
    attrs: Optional[Mapping[str, Any]] = None,
) -> Optional[AgentRunEvent]:
    """Emit model call start."""
    span_id = build_span_id()
    return emit_agent_event(
        AgentEventType.MODEL_START,
        name=model or "model",
        span_id=span_id,
        status="running",
        step=step,
        attrs=attrs,
        push_span=True,
    )


def emit_model_end(
    model: str = "model",
    *,
    success: bool = True,
    duration_ms: Optional[int] = None,
    step: Optional[int] = None,
    attrs: Optional[Mapping[str, Any]] = None,
) -> Optional[AgentRunEvent]:
    """Emit model call end."""
    return emit_agent_event(
        AgentEventType.MODEL_END,
        name=model or "model",
        status="success" if success else "failed",
        duration_ms=duration_ms,
        step=step,
        attrs={**(dict(attrs or {})), "success": bool(success)},
        pop_span=True,
    )


def emit_decision(
    name: str,
    *,
    status: str = "success",
    step: Optional[int] = None,
    attrs: Optional[Mapping[str, Any]] = None,
) -> Optional[AgentRunEvent]:
    """Emit a decision point (e.g. final answer, no-tool, budget skip)."""
    return emit_agent_event(
        AgentEventType.DECISION,
        name=name,
        status=status,
        step=step,
        attrs=attrs,
    )


def reset_span_state_for_tests() -> None:
    """Clear span contextvars (test helper only)."""
    _SPAN_STACK.set(())
    _OPEN_SPANS.set({})
