# -*- coding: utf-8 -*-
"""Structured plan→act→observe→replan→terminate trace events (#1078).

Event taxonomy and field contract align with the unified run-trace draft in
issue #1125 (``plan`` / ``action`` / ``observation`` / ``replan`` /
``terminate``; ``reflect`` and evolution kinds are reserved elsewhere).

Events reuse the existing ``AgentRunEvent`` channel (``emit_agent_event``) so
they persist through run-diagnostics when a diagnostic context is active.
A bounded local list is also kept so a single planning run can be reconstructed
from ``PlanExecutionResult.trace_events`` without log diving.

Privacy: free-form tool payloads and prompts are never stored; only stable
codes, bounded tool names, argument *keys*, and short sanitized summaries.
Overhead is gated by ``AGENT_OBSERVABILITY_ENABLED`` (default on).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.agent.observability import (
    AgentEventType,
    emit_agent_event,
    is_agent_observability_enabled,
    sanitize_agent_event_payload,
)
from src.utils.sanitize import is_sensitive_key, log_safe_exception

logger = logging.getLogger(__name__)

# Local planning-trace schema version (attrs payload). Aligns with L0 agent events.
PLANNING_TRACE_SCHEMA_VERSION = 1
MAX_PLANNING_TRACE_EVENTS = 200

# Stable kind names used for reconstruction (mirror #1125 taxonomy).
PLANNING_TRACE_KINDS = frozenset(
    {"plan", "action", "observation", "replan", "terminate"}
)

_KIND_TO_EVENT_TYPE = {
    "plan": AgentEventType.PLAN,
    "action": AgentEventType.ACTION,
    "observation": AgentEventType.OBSERVATION,
    "replan": AgentEventType.REPLAN,
    "terminate": AgentEventType.TERMINATE,
}


def is_planning_trace_enabled() -> bool:
    """Return whether planning-loop structured events should be recorded.

    Shares the existing agent-observability master switch so the feature is
    default-on, cheap, and can be disabled with ``AGENT_OBSERVABILITY_ENABLED=false``.
    """
    return is_agent_observability_enabled()


def build_planning_run_id() -> str:
    """Return a compact planning-run id for correlating one execute_plan_loop."""
    return uuid.uuid4().hex[:16]


def validate_planning_trace_event(event: Mapping[str, Any]) -> List[str]:
    """Return a list of schema violations (empty when the event shape is valid)."""
    errors: List[str] = []
    if not isinstance(event, Mapping):
        return ["event must be a mapping"]
    kind = event.get("kind")
    if kind not in PLANNING_TRACE_KINDS:
        errors.append("kind must be one of plan|action|observation|replan|terminate")
    if not isinstance(event.get("run_id"), str) or not event["run_id"]:
        errors.append("run_id must be a non-empty string")
    if "schema_version" not in event:
        errors.append("schema_version is required")
    elif type(event.get("schema_version")) is not int:
        errors.append("schema_version must be an int")
    event_type = event.get("event_type")
    if not isinstance(event_type, str) or not event_type.startswith("agent."):
        errors.append("event_type must be an agent.* string")
    if kind == "terminate":
        reason = event.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append("terminate events require a non-empty reason")
    step = event.get("step")
    if step is not None and type(step) is not int:
        errors.append("step must be an int or null")
    return errors


def reconstruct_planning_run(
    events: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Rebuild a compact planning story from ordered trace events.

    Suitable for diagnostics and tests: surfaces plans, actions, observations,
    replan reasons, terminal reason, and last budget snapshot.
    """
    plans: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []
    replans: List[Dict[str, Any]] = []
    terminate: Optional[Dict[str, Any]] = None
    run_id: Optional[str] = None
    budget: Dict[str, Any] = {}

    for raw in events:
        if not isinstance(raw, Mapping):
            continue
        kind = raw.get("kind")
        if run_id is None and isinstance(raw.get("run_id"), str):
            run_id = raw["run_id"]
        attrs = raw.get("attrs") if isinstance(raw.get("attrs"), Mapping) else {}
        budget_slice = attrs.get("budget") if isinstance(attrs.get("budget"), Mapping) else None
        if budget_slice:
            budget = dict(budget_slice)
        if kind == "plan":
            plans.append(
                {
                    "plan_id": attrs.get("plan_id"),
                    "step_count": attrs.get("step_count"),
                    "role": attrs.get("role") or "plan",
                    "sequence": raw.get("sequence"),
                }
            )
        elif kind == "action":
            actions.append(
                {
                    "step": raw.get("step"),
                    "tool_name": attrs.get("tool_name") or raw.get("name"),
                    "sequence": raw.get("sequence"),
                }
            )
        elif kind == "observation":
            observations.append(
                {
                    "step": raw.get("step"),
                    "status": raw.get("status") or attrs.get("status"),
                    "error_type": raw.get("error_type") or attrs.get("error_type"),
                    "sequence": raw.get("sequence"),
                }
            )
        elif kind == "replan":
            replans.append(
                {
                    "reason": raw.get("reason") or attrs.get("reason"),
                    "previous_plan_id": attrs.get("previous_plan_id"),
                    "new_plan_id": attrs.get("new_plan_id"),
                    "failed_step": attrs.get("failed_step"),
                    "sequence": raw.get("sequence"),
                }
            )
        elif kind == "terminate":
            terminate = {
                "reason": raw.get("reason") or attrs.get("reason"),
                "error_type": raw.get("error_type") or attrs.get("error_type"),
                "status": raw.get("status") or attrs.get("status"),
                "success": attrs.get("success"),
                "sequence": raw.get("sequence"),
            }

    return {
        "run_id": run_id,
        "plans": plans,
        "actions": actions,
        "observations": observations,
        "replans": replans,
        "terminate": terminate,
        "budget": budget,
        "event_count": len(events),
    }


class PlanningTraceRecorder:
    """Collect and optionally emit structured planning-loop events for one run."""

    def __init__(
        self,
        *,
        run_id: Optional[str] = None,
        enabled: Optional[bool] = None,
        max_events: int = MAX_PLANNING_TRACE_EVENTS,
    ) -> None:
        self.run_id = run_id or build_planning_run_id()
        self.enabled = is_planning_trace_enabled() if enabled is None else bool(enabled)
        self.max_events = max(1, min(int(max_events), MAX_PLANNING_TRACE_EVENTS))
        self._events: List[Dict[str, Any]] = []
        self._sequence = 0

    @property
    def events(self) -> List[Dict[str, Any]]:
        return list(self._events)

    def budget_attrs(
        self,
        *,
        tool_call_count: int = 0,
        max_total_tool_calls: int = 0,
        observation_replans: int = 0,
        max_observation_replans: int = 0,
        planning_tokens: int = 0,
    ) -> Dict[str, Any]:
        return {
            "tool_call_count": int(tool_call_count),
            "max_total_tool_calls": int(max_total_tool_calls),
            "observation_replans": int(observation_replans),
            "max_observation_replans": int(max_observation_replans),
            "planning_tokens": int(planning_tokens),
        }

    def emit_plan(
        self,
        *,
        plan_id: str,
        step_count: int,
        role: str = "initial",
        step: Optional[int] = None,
        budget: Optional[Mapping[str, Any]] = None,
        attrs: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "plan_id": plan_id,
            "step_count": int(step_count),
            "role": role,
        }
        if budget:
            payload["budget"] = dict(budget)
        if attrs:
            payload.update(dict(attrs))
        return self._record(
            kind="plan",
            name="plan",
            status="accepted",
            step=step,
            reason=None,
            error_type=None,
            attrs=payload,
        )

    def emit_action(
        self,
        *,
        tool_name: str,
        step: Optional[int],
        argument_keys: Optional[Sequence[str]] = None,
        plan_id: Optional[str] = None,
        budget: Optional[Mapping[str, Any]] = None,
        attrs: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "tool_name": tool_name,
        }
        if plan_id:
            payload["plan_id"] = plan_id
        if argument_keys is not None:
            # Names only — never argument values. Avoid the substring "key" in the
            # attr name so shared sensitive-key sanitization does not wipe the list.
            names = [
                str(k)
                for k in argument_keys
                if str(k).strip() and not is_sensitive_key(str(k))
            ]
            payload["arg_names"] = sorted(names)[:16]
        if budget:
            payload["budget"] = dict(budget)
        if attrs:
            payload.update(dict(attrs))
        return self._record(
            kind="action",
            name=tool_name or "action",
            status="running",
            step=step,
            reason=None,
            error_type=None,
            attrs=payload,
        )

    def emit_observation(
        self,
        *,
        step: Optional[int],
        status: str,
        error_type: Optional[str] = None,
        failure_reason: Optional[str] = None,
        tool_count: int = 0,
        plan_id: Optional[str] = None,
        budget: Optional[Mapping[str, Any]] = None,
        attrs: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        resolved_error = error_type or failure_reason
        payload: Dict[str, Any] = {
            "status": status,
            "tool_count": int(tool_count),
        }
        if plan_id:
            payload["plan_id"] = plan_id
        if resolved_error:
            payload["error_type"] = resolved_error
            payload["failure_reason"] = resolved_error
        if budget:
            payload["budget"] = dict(budget)
        if attrs:
            payload.update(dict(attrs))
        return self._record(
            kind="observation",
            name="observation",
            status=status,
            step=step,
            reason=failure_reason,
            error_type=resolved_error,
            attrs=payload,
        )

    def emit_replan(
        self,
        *,
        reason: str,
        previous_plan_id: str,
        new_plan_id: Optional[str] = None,
        failed_step: Optional[int] = None,
        observation_replans: int = 0,
        budget: Optional[Mapping[str, Any]] = None,
        error_type: Optional[str] = None,
        attrs: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "reason": reason,
            "previous_plan_id": previous_plan_id,
            "observation_replans": int(observation_replans),
        }
        if new_plan_id:
            payload["new_plan_id"] = new_plan_id
        if failed_step is not None:
            payload["failed_step"] = int(failed_step)
        if budget:
            payload["budget"] = dict(budget)
        if attrs:
            payload.update(dict(attrs))
        return self._record(
            kind="replan",
            name="replan",
            status="replanned" if new_plan_id else "replan_failed",
            step=failed_step,
            reason=reason,
            error_type=error_type,
            attrs=payload,
        )

    def emit_terminate(
        self,
        *,
        reason: str,
        status: str,
        success: bool,
        error_type: Optional[str] = None,
        plan_id: Optional[str] = None,
        budget: Optional[Mapping[str, Any]] = None,
        attrs: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        # Acceptance: terminate always carries a reason.
        resolved_reason = (reason or "").strip() or ("completed" if success else "failed")
        payload: Dict[str, Any] = {
            "reason": resolved_reason,
            "status": status,
            "success": bool(success),
        }
        if plan_id:
            payload["plan_id"] = plan_id
        if error_type:
            payload["error_type"] = error_type
        if budget:
            payload["budget"] = dict(budget)
        if attrs:
            payload.update(dict(attrs))
        return self._record(
            kind="terminate",
            name="terminate",
            status=status,
            step=None,
            reason=resolved_reason,
            error_type=error_type,
            attrs=payload,
        )

    def _record(
        self,
        *,
        kind: str,
        name: str,
        status: Optional[str],
        step: Optional[int],
        reason: Optional[str],
        error_type: Optional[str],
        attrs: Mapping[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            return self._record_impl(
                kind=kind,
                name=name,
                status=status,
                step=step,
                reason=reason,
                error_type=error_type,
                attrs=attrs,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - trace must never break the loop
            log_safe_exception(
                logger,
                "Planning trace record failed",
                exc,
                error_code="planning_trace_record_failed",
                level=logging.DEBUG,
                context={"kind": kind, "name": str(name)[:80]},
            )
            return None

    def _record_impl(
        self,
        *,
        kind: str,
        name: str,
        status: Optional[str],
        step: Optional[int],
        reason: Optional[str],
        error_type: Optional[str],
        attrs: Mapping[str, Any],
    ) -> Dict[str, Any]:
        self._sequence += 1
        safe_attrs = sanitize_agent_event_payload(dict(attrs), deep=False)
        if not isinstance(safe_attrs, dict):
            safe_attrs = {}
        # Always embed correlation fields expected by consumers / #1125.
        safe_attrs.setdefault("run_id", self.run_id)
        safe_attrs.setdefault("kind", kind)
        if reason and "reason" not in safe_attrs:
            safe_attrs["reason"] = reason
        if error_type and "error_type" not in safe_attrs:
            safe_attrs["error_type"] = error_type

        event_type = _KIND_TO_EVENT_TYPE.get(kind, AgentEventType.DECISION)
        type_value = (
            event_type.value if isinstance(event_type, AgentEventType) else str(event_type)
        )

        record: Dict[str, Any] = {
            "schema_version": PLANNING_TRACE_SCHEMA_VERSION,
            "kind": kind,
            "event_type": type_value,
            "run_id": self.run_id,
            "sequence": self._sequence,
            "timestamp": datetime.now().isoformat(),
            "name": name,
            "status": status,
            "step": step,
            "reason": reason,
            "error_type": error_type,
            "attrs": safe_attrs,
        }

        self._events.append(record)
        while len(self._events) > self.max_events:
            self._events.pop(0)

        # Best-effort dual-write into the shared agent event stream (#1125 path).
        emit_agent_event(
            event_type,
            name=name,
            phase="planning",
            status=status,
            step=step,
            attrs=safe_attrs,
        )
        return record
