# -*- coding: utf-8 -*-
"""Run-flow agent-event projection.

Issue #1086 extracts persisted-agent observability projection from
``src.services.run_flow``. Public builders stay on the compatibility facade.
Consumers import ``src.services.run_flow``, not this internal module.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import FunctionType
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.services.run_diagnostics import sanitize_finite_diagnostic_metadata
from src.services.run_flow_parts.graph import (
    _append_edge,
    _append_event,
    _as_mapping,
    _clone_facade_function,
    _datetime_to_iso,
    _put_node,
    _safe_int,
    _safe_key,
    _safe_text,
    _started_at_from_end_and_duration,
)

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


def _append_agent_events(
    nodes: Dict[str, Dict[str, Any]],
    edges: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    agent_events: List[Any],
    *,
    anchor_node_id: str,
    capture: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Project persisted agent observability events into the run-flow graph."""
    if not agent_events:
        return None

    previous_node_id = anchor_node_id
    last_node_id: Optional[str] = None
    tool_sequence: List[Dict[str, Any]] = []
    phase_node_id = "agent_phase"
    has_phase_node = False

    safe_capture, capture_finite = sanitize_finite_diagnostic_metadata(capture or {})
    if not isinstance(safe_capture, Mapping):
        safe_capture = {}

    for raw_event in agent_events:
        event = _as_mapping(raw_event)
        if not event:
            continue
        event_type = str(event.get("event_type") or "")
        type_key = _safe_key(event_type) or "agent_event"
        name = _safe_text(event.get("name"), max_length=80) or "agent"
        span_key = _safe_key(event.get("span_id"))
        status_raw = _safe_text(event.get("status"), max_length=32) or "unknown"
        status = _agent_event_status(status_raw, event_type=type_key)
        duration_ms = _safe_int(event.get("duration_ms"))
        timestamp = _datetime_to_iso(event.get("timestamp"))
        step = _safe_int(event.get("step"))
        sequence = _safe_int(event.get("sequence"))
        schema_version = _safe_int(event.get("schema_version"))
        raw_attrs = event.get("attrs") if isinstance(event.get("attrs"), Mapping) else {}
        raw_payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        safe_attrs, attrs_finite = sanitize_finite_diagnostic_metadata(raw_attrs)
        safe_payload, payload_finite = sanitize_finite_diagnostic_metadata(raw_payload)
        detail_integrity = _safe_text(event.get("detail_integrity"), max_length=40)
        if not attrs_finite or not payload_finite or not capture_finite:
            detail_integrity = "invalid_non_finite"
        elif not detail_integrity:
            detail_integrity = "valid"
        is_start = type_key.endswith("_start")

        if type_key in {"agent_tool_start", "agent_tool_end"}:
            node_id = f"agent_tool_{span_key}" if span_key else f"agent_tool_{_safe_key(name)}_{len(tool_sequence) + 1}"
            label = f"工具 · {name}"
            kind = "analysis"
            title = f"工具开始: {name}" if is_start else f"工具完成: {name}"
            if type_key == "agent_tool_start":
                tool_sequence.append(
                    {
                        "id": node_id,
                        "label": name,
                        "status": status,
                        "durationMs": duration_ms,
                        "step": step,
                        "span_id": event.get("span_id"),
                    }
                )
            else:
                matched = False
                for item in tool_sequence:
                    if item.get("span_id") == event.get("span_id") or item.get("id") == node_id:
                        item["status"] = status
                        item["durationMs"] = duration_ms
                        matched = True
                        break
                if not matched:
                    tool_sequence.append(
                        {
                            "id": node_id,
                            "label": name,
                            "status": status,
                            "durationMs": duration_ms,
                            "step": step,
                            "span_id": event.get("span_id"),
                        }
                    )
        elif type_key in {"agent_model_start", "agent_model_end"}:
            node_id = f"agent_model_{span_key}" if span_key else f"agent_model_{_safe_key(name)}"
            label = f"模型 · {name}"
            kind = "model"
            title = f"模型开始: {name}" if is_start else f"模型完成: {name}"
        elif type_key in {"agent_phase_start", "agent_phase_end"}:
            node_id = f"agent_phase_{span_key}" if span_key else phase_node_id
            phase_node_id = node_id
            has_phase_node = True
            label = f"阶段 · {name}"
            kind = "analysis"
            title = f"阶段开始: {name}" if is_start else f"阶段结束: {name}"
        else:
            node_id = f"agent_{span_key}" if span_key else f"agent_{type_key}_{_safe_key(name)}"
            label = f"Agent · {name}"
            kind = "analysis"
            title = f"Agent: {name}"

        message_bits = [name]
        if step is not None:
            message_bits.append(f"step={step}")
        if duration_ms is not None and not is_start:
            message_bits.append(f"{duration_ms}ms")
        if status_raw and not is_start:
            message_bits.append(status_raw)
        message = _safe_text(" · ".join(message_bits), max_length=220)

        existing = nodes.get(node_id)
        if existing is None:
            _put_node(
                nodes,
                node_id,
                lane="analysis",
                kind=kind,
                label=label,
                status=status,
                provider=name if type_key.startswith("agent_tool") or type_key.startswith("agent_model") else None,
                started_at=timestamp if is_start else _started_at_from_end_and_duration(timestamp, duration_ms),
                ended_at=None if is_start else timestamp,
                duration_ms=None if is_start else duration_ms,
                message=message,
                metadata={
                    "event_type": event_type,
                    "span_id": event.get("span_id"),
                    "parent_span_id": event.get("parent_span_id"),
                    "trace_id": event.get("trace_id"),
                    "step": step,
                    "phase": event.get("phase"),
                    "duration_ms": duration_ms,
                },
            )
            _append_edge(edges, previous_node_id, node_id, "control", status, label="Agent")
        else:
            if not is_start:
                existing["status"] = status
                existing["ended_at"] = timestamp or existing.get("ended_at")
                existing["duration_ms"] = duration_ms if duration_ms is not None else existing.get("duration_ms")
                existing["message"] = message or existing.get("message")
                if duration_ms is not None and existing.get("started_at") is None:
                    existing["started_at"] = _started_at_from_end_and_duration(timestamp, duration_ms)
            else:
                existing["started_at"] = existing.get("started_at") or timestamp
                if existing.get("status") in {None, "unknown", "pending"}:
                    existing["status"] = status

        _append_event(
            events,
            type_key,
            node_id=node_id,
            timestamp=timestamp,
            severity=(
                "info" if is_start else (
                    "success" if status in {"success", "fallback"} else (
                        "danger" if status == "failed" else "warning"
                    )
                )
            ),
            title=title,
            message=message,
            metadata={
                "schema_version": schema_version,
                "sequence": sequence,
                "event_type": event_type,
                "span_id": event.get("span_id"),
                "parent_span_id": event.get("parent_span_id"),
                "trace_id": event.get("trace_id"),
                "duration_ms": duration_ms,
                "step": step,
                "status": status_raw,
                "tool": name if type_key.startswith("agent_tool") else None,
                "model": name if type_key.startswith("agent_model") else None,
                "attrs": safe_attrs if raw_attrs else None,
                "payload": safe_payload if raw_payload else None,
                "detail_integrity": detail_integrity,
                "capture": safe_capture or None,
            },
        )
        previous_node_id = node_id
        last_node_id = node_id

    if has_phase_node and tool_sequence and phase_node_id in nodes:
        deduped: Dict[str, Dict[str, Any]] = {}
        for item in tool_sequence:
            key = str(item.get("span_id") or item.get("id") or item.get("label"))
            deduped[key] = item
        nodes[phase_node_id].setdefault("metadata", {})
        nodes[phase_node_id]["metadata"]["tool_sequence"] = list(deduped.values())[:40]
        nodes[phase_node_id]["metadata"]["tool_count"] = len(deduped)

    return last_node_id


def _agent_event_status(status: Optional[str], *, event_type: str) -> str:
    normalized = (status or "").strip().lower()
    if event_type.endswith("_start") or normalized in {"running", "started", "in_progress"}:
        return "running"
    if normalized in {"success", "ok", "completed", "done"}:
        return "success"
    if normalized in {"failed", "error", "fail"}:
        return "failed"
    if normalized in {"cancelled", "cancel_requested", "timeout", "skipped", "degraded", "fallback"}:
        return normalized
    if normalized:
        return "degraded"
    return "unknown"


# Names cloned helpers resolve from the facade global namespace. Bind copies
# these owner imports onto the facade so callables keep working without a
# reverse import of ``src.services.run_flow``. Graph helper clones already
# live on the facade and must not be overwritten with owner-imported sources.
_FACADE_HELPER_GLOBAL_NAMES = (
    "sanitize_finite_diagnostic_metadata",
)


EXPECTED_AGENT_EVENT_NAMES = (
    "_append_agent_events",
    "_agent_event_status",
)


def bind_agent_events_facade(
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind agent-event helpers onto the run-flow facade without changing signatures."""
    bound_names = []
    source_namespace = globals()
    for name in _FACADE_HELPER_GLOBAL_NAMES:
        global_namespace[name] = source_namespace[name]
    for name in EXPECTED_AGENT_EVENT_NAMES:
        function = source_namespace.get(name)
        if not isinstance(function, FunctionType):
            raise TypeError(
                f"run-flow agent-event helper requires a Python function: {name}"
            )
        global_namespace[name] = _clone_facade_function(function, global_namespace)
        bound_names.append(name)
    return tuple(bound_names)


def _install_facade_reload_hook(hook: Callable[[], None]) -> None:
    """Register the loaded facade assembly callback for owner reloads."""
    global _FACADE_RELOAD_HOOK
    _FACADE_RELOAD_HOOK = hook


def _rebind_loaded_facade() -> None:
    """Refresh a registered facade after this owner module is reloaded."""
    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
