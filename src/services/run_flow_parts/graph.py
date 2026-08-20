# -*- coding: utf-8 -*-
"""Run-flow graph mutators and scalar helpers.

Issue #1086 extracts node/edge/event mutation and shared sanitization/time
helpers from ``src.services.run_flow``. Public builders, projectors, skeleton
helpers, and constants stay on the compatibility facade. Consumers import
``src.services.run_flow``, not this internal module.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from types import FunctionType
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from src.services.run_diagnostics import (
    safe_diagnostic_key,
    sanitize_diagnostic_metadata,
    sanitize_diagnostic_text,
)
from src.utils.data_processing import parse_json_field

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


def _put_node(
    nodes: Dict[str, Dict[str, Any]],
    node_id: str,
    *,
    lane: str,
    kind: str,
    label: str,
    status: str,
    provider: Optional[Any] = None,
    started_at: Optional[Any] = None,
    ended_at: Optional[Any] = None,
    duration_ms: Optional[Any] = None,
    attempts: Optional[Any] = None,
    record_count: Optional[Any] = None,
    message: Optional[Any] = None,
    metadata: Optional[Any] = None,
) -> None:
    payload = {
        "id": node_id,
        "lane": lane,
        "kind": kind,
        "label": _safe_text(label, max_length=80) or node_id,
        "status": _valid_status(status),
        "provider": _safe_text(provider, max_length=120),
        "started_at": _datetime_to_iso(started_at),
        "ended_at": _datetime_to_iso(ended_at),
        "duration_ms": _safe_int(duration_ms),
        "attempts": _safe_int(attempts),
        "record_count": _safe_int(record_count),
        "message": _safe_text(message, max_length=220),
        "metadata": _sanitize_metadata(metadata or {}),
    }
    nodes[node_id] = {key: value for key, value in payload.items() if value not in (None, {}, [])}


def _append_edge(
    edges: List[Dict[str, Any]],
    from_node: str,
    to_node: str,
    kind: str,
    status: str,
    *,
    label: Optional[Any] = None,
    message: Optional[Any] = None,
    metadata: Optional[Any] = None,
) -> None:
    edge_id = f"{from_node}_to_{to_node}_{kind}"
    for edge in edges:
        if edge["id"] != edge_id:
            continue
        edge["status"] = _valid_status(status)
        safe_label = _safe_text(label, max_length=40)
        if safe_label:
            edge["label"] = safe_label
        safe_message = _safe_text(message, max_length=180)
        if safe_message:
            edge["message"] = safe_message
        safe_metadata = _sanitize_metadata(metadata or {})
        if safe_metadata:
            edge["metadata"] = safe_metadata
        return
    edges.append(
        {
            "id": edge_id,
            "from": from_node,
            "to": to_node,
            "kind": kind if kind in {"data", "control", "fallback", "retry"} else "data",
            "status": _valid_status(status),
            "label": _safe_text(label, max_length=40),
            "message": _safe_text(message, max_length=180),
            "metadata": _sanitize_metadata(metadata or {}),
        }
    )


def _refresh_incoming_edge_status(
    edges: List[Dict[str, Any]],
    node_id: Optional[str],
    status: Optional[Any],
) -> None:
    if not node_id or status is None:
        return
    valid_status = _valid_status(status)
    for edge in edges:
        if edge.get("to") == node_id:
            edge["status"] = valid_status


def _append_event(
    events: List[Dict[str, Any]],
    event_type: str,
    *,
    node_id: Optional[str],
    timestamp: Optional[Any],
    severity: str,
    title: str,
    message: Optional[Any] = None,
    metadata: Optional[Any] = None,
) -> None:
    event_id = f"evt_{len(events) + 1:04d}"
    events.append(
        {
            "id": event_id,
            "timestamp": _datetime_to_iso(timestamp),
            "severity": severity if severity in {"info", "success", "warning", "danger"} else "info",
            "type": _safe_key(event_type) or "event",
            "node_id": node_id,
            "title": _safe_text(title, max_length=100) or event_type,
            "message": _safe_text(message, max_length=220),
            "metadata": _sanitize_metadata(metadata or {}),
        }
    )


def _valid_status(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    if text in {
        "pending",
        "running",
        "success",
        "failed",
        "degraded",
        "fallback",
        "timeout",
        "cancel_requested",
        "cancelled",
        "skipped",
        "unknown",
    }:
        return text
    return "unknown"


def _safe_text(value: Any, *, max_length: int = 300) -> Optional[str]:
    return sanitize_diagnostic_text(value, max_length=max_length)


def _safe_key(value: Any) -> str:
    return safe_diagnostic_key(value)


def _safe_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed >= 0 else None


def _sanitize_metadata(value: Any, *, depth: int = 0) -> Any:
    return sanitize_diagnostic_metadata(value, depth=depth)


def _as_mapping(value: Any) -> Dict[str, Any]:
    parsed = parse_json_field(value)
    if isinstance(parsed, Mapping):
        return dict(parsed)
    if isinstance(parsed, str) and parsed.strip():
        try:
            loaded = json.loads(parsed)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return dict(loaded) if isinstance(loaded, Mapping) else {}
    return {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _datetime_to_iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return _safe_text(value, max_length=80)
    return None


def _elapsed_ms(start: Any, end: Any) -> Optional[int]:
    start_dt = _datetime_for_elapsed(start)
    end_dt = _datetime_for_elapsed(end)
    if start_dt is None or end_dt is None:
        return None
    seconds = (end_dt - start_dt).total_seconds()
    if seconds < 0:
        return None
    return int(seconds * 1000)


def _started_at_from_end_and_duration(end: Any, duration_ms: Any) -> Optional[str]:
    duration = _safe_int(duration_ms)
    if duration is None:
        return None
    if isinstance(end, datetime):
        parsed = end
    elif isinstance(end, str) and "T" in end:
        normalized = end[:-1] + "+00:00" if end.endswith("Z") else end
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None
    return (parsed - timedelta(milliseconds=duration)).isoformat()


def _local_timezone():
    return datetime.now().astimezone().tzinfo or timezone.utc


def _datetime_for_elapsed(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and "T" in value:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=_local_timezone())
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _events_elapsed_ms(events: Iterable[Dict[str, Any]]) -> Optional[int]:
    timestamps: List[datetime] = []
    for event in events:
        parsed = _datetime_for_elapsed(event.get("timestamp"))
        if parsed is not None:
            timestamps.append(parsed)
    if len(timestamps) < 2:
        return None
    elapsed = (max(timestamps) - min(timestamps)).total_seconds()
    return int(elapsed * 1000) if elapsed >= 0 else None


# Names cloned helpers resolve from the facade global namespace. Bind copies
# these owner imports onto the facade so callables keep working without a
# reverse import of ``src.services.run_flow``.
_FACADE_HELPER_GLOBAL_NAMES = (
    "json",
    "Mapping",
    "timedelta",
    "timezone",
    "parse_json_field",
    "safe_diagnostic_key",
    "sanitize_diagnostic_metadata",
    "sanitize_diagnostic_text",
)


EXPECTED_GRAPH_HELPER_NAMES = (
    "_put_node",
    "_append_edge",
    "_refresh_incoming_edge_status",
    "_append_event",
    "_valid_status",
    "_safe_text",
    "_safe_key",
    "_safe_int",
    "_sanitize_metadata",
    "_as_mapping",
    "_as_list",
    "_datetime_to_iso",
    "_elapsed_ms",
    "_started_at_from_end_and_duration",
    "_local_timezone",
    "_datetime_for_elapsed",
    "_events_elapsed_ms",
)


def _clone_facade_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
) -> FunctionType:
    """Clone a moved helper so global lookups retain facade semantics."""
    cloned = FunctionType(
        function.__code__,
        global_namespace,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    cloned.__annotations__ = dict(function.__annotations__)
    cloned.__dict__.update(function.__dict__)
    cloned.__doc__ = function.__doc__
    cloned.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    cloned.__module__ = str(global_namespace["__name__"])
    cloned.__qualname__ = function.__qualname__
    if hasattr(function, "__type_params__"):
        cloned.__type_params__ = function.__type_params__
    return cloned


def bind_graph_helpers_facade(
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind graph helpers onto the run-flow facade without changing signatures."""
    bound_names = []
    source_namespace = globals()
    for name in _FACADE_HELPER_GLOBAL_NAMES:
        global_namespace[name] = source_namespace[name]
    for name in EXPECTED_GRAPH_HELPER_NAMES:
        function = source_namespace.get(name)
        if not isinstance(function, FunctionType):
            raise TypeError(f"run-flow graph helper requires a Python function: {name}")
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
