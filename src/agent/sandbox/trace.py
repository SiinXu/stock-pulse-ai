# -*- coding: utf-8 -*-
"""Production-isomorphic sandbox traces for agent-variant comparison.

Trace shape intentionally mirrors the production agent-trajectory / L0 event
fields so sandbox vs production runs can be diffed field-by-field. Sandbox
traces always carry simulation labels and never imply production authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from src.agent.sandbox.context import SandboxContext
from src.agent.sandbox.policy import SANDBOX_MODE, SIMULATION_LABEL

SANDBOX_TRACE_SCHEMA_VERSION = "sandbox-trace-v1"


@dataclass(frozen=True)
class SandboxTraceEvent:
    """One bounded, redaction-friendly sandbox event (production-isomorphic)."""

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
        """Project to agent-trajectory-input-v1-compatible run dicts."""
        return [
            {
                "schema_version": "agent-trajectory-input-v1",
                "run_id": self.sandbox_run_id,
                "agent_id": self.agent_variant_id,
                "started_at": self.clock_now,
                "completed": True,
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
                "sandbox": {
                    "simulation": True,
                    "label": self.label,
                    "mode": self.mode,
                    "config_digest": self.config_digest,
                },
            }
        ]


def build_sandbox_trace(
    context: SandboxContext,
    *,
    events: Optional[Sequence[Union[Mapping[str, Any], SandboxTraceEvent]]] = None,
    tool_calls: Optional[Sequence[Mapping[str, Any]]] = None,
    simulated_actions: Optional[Sequence[Mapping[str, Any]]] = None,
    blocked_external_effects: Optional[Sequence[Mapping[str, Any]]] = None,
    rejected_actions: Optional[Sequence[Mapping[str, Any]]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> SandboxTrace:
    """Assemble a labeled sandbox trace from run artifacts."""
    normalized_events: List[SandboxTraceEvent] = []
    for index, raw in enumerate(events or ()):
        if isinstance(raw, SandboxTraceEvent):
            normalized_events.append(raw)
            continue
        if not isinstance(raw, Mapping):
            continue
        normalized_events.append(
            SandboxTraceEvent(
                event_type=str(raw.get("event_type") or "agent.event"),
                name=str(raw.get("name") or raw.get("event_type") or "event"),
                sequence=int(raw.get("sequence", index)),
                timestamp=str(
                    raw.get("timestamp") or context.clock.isoformat()
                ),
                status=(
                    str(raw["status"]) if raw.get("status") is not None else None
                ),
                duration_ms=(
                    int(raw["duration_ms"])
                    if raw.get("duration_ms") is not None
                    else None
                ),
                step=int(raw["step"]) if raw.get("step") is not None else None,
                attrs=dict(raw.get("attrs") or {}),
            )
        )

    meta = {
        **context.public_metadata(),
        **dict(metadata or {}),
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
        events=tuple(normalized_events),
        tool_calls=tuple(dict(item) for item in (tool_calls or ())),
        simulated_actions=tuple(dict(item) for item in (simulated_actions or ())),
        blocked_external_effects=tuple(
            dict(item) for item in (blocked_external_effects or ())
        ),
        rejected_actions=tuple(dict(item) for item in (rejected_actions or ())),
        metadata=meta,
    )
