# -*- coding: utf-8 -*-
"""Production-comparable sandbox traces for agent-variant comparison.

Trace shape intentionally mirrors production agent-trajectory / L0 event fields
so sandbox vs production runs can be diffed field-by-field. Strict trajectory
projections omit sandbox-only keys (``TrajectoryRunInput`` forbids extras);
simulation metadata lives on the enclosing trace / side-car projection.
Sandbox traces always carry simulation labels and never imply production
authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from src.agent.sandbox.context import SandboxContext, validate_sandbox_json
from src.agent.sandbox.policy import SANDBOX_MODE, SIMULATION_LABEL
from src.utils.sanitize import redact_sensitive_data

SANDBOX_TRACE_SCHEMA_VERSION = "sandbox-trace-v1"


@dataclass(frozen=True)
class SandboxTraceEvent:
    """One bounded, redaction-friendly sandbox event (production-comparable)."""

    event_type: str
    name: str
    sequence: int
    timestamp: str
    status: Optional[str] = None
    duration_ms: Optional[int] = None
    step: Optional[int] = None
    attrs: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "event_type": self.event_type,
            "name": self.name,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "simulation": True,
            "label": SIMULATION_LABEL,
            "mode": SANDBOX_MODE,
        }
        if self.status is not None:
            payload["status"] = self.status
        if self.duration_ms is not None:
            payload["duration_ms"] = self.duration_ms
        if self.step is not None:
            payload["step"] = self.step
        if self.attrs:
            payload["attrs"] = dict(self.attrs)
        return payload


@dataclass(frozen=True)
class SandboxTrace:
    """Joinable sandbox run trace with production-comparable tool/step fields."""

    schema_version: str
    sandbox_run_id: str
    agent_variant_id: str
    config_digest: str
    clock_now: str
    data_mode: str
    label: str
    mode: str
    completed: bool
    events: tuple = ()
    tool_calls: tuple = ()
    simulated_actions: tuple = ()
    blocked_external_effects: tuple = ()
    rejected_actions: tuple = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sandbox_run_id": self.sandbox_run_id,
            "agent_variant_id": self.agent_variant_id,
            "config_digest": self.config_digest,
            "clock_now": self.clock_now,
            "data_mode": self.data_mode,
            "label": self.label,
            "mode": self.mode,
            "simulation": True,
            "completed": self.completed,
            "events": [event.to_dict() for event in self.events],
            "tool_calls": [dict(item) for item in self.tool_calls],
            "simulated_actions": [dict(item) for item in self.simulated_actions],
            "blocked_external_effects": [
                dict(item) for item in self.blocked_external_effects
            ],
            "rejected_actions": [dict(item) for item in self.rejected_actions],
            "metadata": dict(self.metadata),
        }

    def trajectory_compatible_runs(self) -> List[Dict[str, Any]]:
        """Project to strict ``agent-trajectory-input-v1`` run dicts.

        Simulation metadata is intentionally **not** embedded in the run
        payload: ``TrajectoryRunInput`` uses ``extra="forbid"``. Callers that
        need sandbox labels should use :meth:`trajectory_projection` or the
        enclosing :class:`SandboxTrace` fields.
        """
        return [
            {
                "schema_version": "agent-trajectory-input-v1",
                "run_id": self.sandbox_run_id,
                "agent_id": self.agent_variant_id,
                "started_at": self.clock_now,
                "completed": self.completed,
                "source_truncated": False,
                "tool_calls": [
                    {
                        "tool": str(call.get("tool") or call.get("name") or "unknown"),
                        "arguments": dict(call.get("arguments") or {}),
                        "success": bool(call.get("success", True)),
                        "duration": call.get("duration"),
                        "cached": bool(call.get("cached", False)),
                        "timeout": bool(call.get("timeout", False)),
                        "guarded": bool(call.get("guarded", False)),
                        "step": call.get("step"),
                        "agent_id": self.agent_variant_id,
                    }
                    for call in self.tool_calls
                ],
            }
        ]

    def trajectory_projection(self) -> Dict[str, Any]:
        """Strict trajectory run(s) plus side-car simulation metadata."""
        runs = self.trajectory_compatible_runs()
        return {
            "runs": runs,
            "sandbox": {
                "simulation": True,
                "label": self.label,
                "mode": self.mode,
                "config_digest": self.config_digest,
                "sandbox_run_id": self.sandbox_run_id,
                "data_mode": self.data_mode,
            },
        }


def build_sandbox_trace(
    context: SandboxContext,
    *,
    events: Optional[Sequence[Union[Mapping[str, Any], SandboxTraceEvent]]] = None,
    tool_calls: Optional[Sequence[Mapping[str, Any]]] = None,
    simulated_actions: Optional[Sequence[Mapping[str, Any]]] = None,
    blocked_external_effects: Optional[Sequence[Mapping[str, Any]]] = None,
    rejected_actions: Optional[Sequence[Mapping[str, Any]]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    completed: bool = True,
) -> SandboxTrace:
    """Assemble a labeled sandbox trace from run artifacts."""
    normalized_events: List[SandboxTraceEvent] = []
    for index, raw in enumerate(events or ()):
        if isinstance(raw, SandboxTraceEvent):
            raw = {
                "event_type": raw.event_type,
                "name": raw.name,
                "sequence": raw.sequence,
                "timestamp": raw.timestamp,
                "status": raw.status,
                "duration_ms": raw.duration_ms,
                "step": raw.step,
                "attrs": dict(raw.attrs),
            }
        elif not isinstance(raw, Mapping):
            raise ValueError(f"events[{index}] must be a mapping")
        validate_sandbox_json(raw, field_name=f"events[{index}]")
        safe_raw = redact_sensitive_data(dict(raw))
        if not isinstance(safe_raw, Mapping):
            raise ValueError(f"events[{index}] could not be safely serialized")
        normalized_events.append(
            SandboxTraceEvent(
                event_type=str(safe_raw.get("event_type") or "agent.event"),
                name=str(
                    safe_raw.get("name")
                    or safe_raw.get("event_type")
                    or "event"
                ),
                sequence=int(safe_raw.get("sequence", index)),
                timestamp=str(
                    safe_raw.get("timestamp") or context.clock.isoformat()
                ),
                status=(
                    str(safe_raw["status"])
                    if safe_raw.get("status") is not None
                    else None
                ),
                duration_ms=(
                    int(safe_raw["duration_ms"])
                    if safe_raw.get("duration_ms") is not None
                    else None
                ),
                step=(
                    int(safe_raw["step"])
                    if safe_raw.get("step") is not None
                    else None
                ),
                attrs=dict(safe_raw.get("attrs") or {}),
            )
        )

    tool_call_rows = _redacted_mapping_rows(tool_calls, "tool_calls")
    simulated_action_rows = _redacted_mapping_rows(
        simulated_actions, "simulated_actions"
    )
    blocked_rows = _redacted_mapping_rows(
        blocked_external_effects, "blocked_external_effects"
    )
    rejected_rows = _redacted_mapping_rows(rejected_actions, "rejected_actions")
    validate_sandbox_json(metadata or {}, field_name="metadata")
    safe_metadata = redact_sensitive_data(dict(metadata or {}))
    if not isinstance(safe_metadata, Mapping):
        raise ValueError("metadata could not be safely serialized")
    meta = {
        **context.public_metadata(),
        **dict(safe_metadata),
        "simulation": True,
        "label": SIMULATION_LABEL,
        "mode": SANDBOX_MODE,
    }
    return SandboxTrace(
        schema_version=SANDBOX_TRACE_SCHEMA_VERSION,
        sandbox_run_id=context.sandbox_run_id,
        agent_variant_id=context.agent_variant_id,
        config_digest=context.config_digest,
        clock_now=context.clock.isoformat(),
        data_mode=context.data_mode,
        label=SIMULATION_LABEL,
        mode=SANDBOX_MODE,
        completed=bool(completed),
        events=tuple(normalized_events),
        tool_calls=tuple(tool_call_rows),
        simulated_actions=tuple(simulated_action_rows),
        blocked_external_effects=tuple(blocked_rows),
        rejected_actions=tuple(rejected_rows),
        metadata=meta,
    )


def _redacted_mapping_rows(
    values: Optional[Sequence[Mapping[str, Any]]],
    field_name: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index, item in enumerate(values or ()):
        if not isinstance(item, Mapping):
            raise ValueError(f"{field_name}[{index}] must be a mapping")
        validate_sandbox_json(item, field_name=f"{field_name}[{index}]")
        safe_item = redact_sensitive_data(dict(item))
        if not isinstance(safe_item, Mapping):
            raise ValueError(
                f"{field_name}[{index}] could not be safely serialized"
            )
        rows.append(dict(safe_item))
    validate_sandbox_json(rows, field_name=field_name)
    return rows
