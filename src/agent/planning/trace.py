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
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.agent.planning.config import MAX_PLANNING_TRACE_EVENTS
from src.agent.observability import (
    AgentEventType,
    emit_agent_event,
    is_agent_observability_enabled,
    sanitize_agent_event_payload,
)
from src.utils.sanitize import is_sensitive_key, log_safe_exception

logger = logging.getLogger(__name__)

# Local planning-trace schema version (attrs payload). Aligns with L0 agent events.
# Event list bound lives in planning.config.MAX_PLANNING_TRACE_EVENTS (single authority).
PLANNING_TRACE_SCHEMA_VERSION = 1

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_BUDGET_FIELDS = frozenset(
    {
        "tool_call_count",
        "max_total_tool_calls",
        "observation_replans",
        "max_observation_replans",
        "planning_tokens",
    }
)
_RESERVED_ATTR_FIELDS = _BUDGET_FIELDS | frozenset(
    {
        "arg_names",
        "budget",
        "error_type",
        "failed_step",
        "failure_reason",
        "kind",
        "new_plan_id",
        "observation_replans",
        "plan_id",
        "previous_plan_id",
        "reason",
        "role",
        "run_id",
        "status",
        "step_count",
        "success",
        "tool_count",
        "tool_name",
    }
)

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
    if not isinstance(kind, str) or kind not in PLANNING_TRACE_KINDS:
        errors.append("kind must be one of plan|action|observation|replan|terminate")
    run_id = event.get("run_id")
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        errors.append("run_id must be a bounded correlation identifier")
    if "schema_version" not in event:
        errors.append("schema_version is required")
    elif (
        type(event.get("schema_version")) is not int
        or event.get("schema_version") != PLANNING_TRACE_SCHEMA_VERSION
    ):
        errors.append(
            f"schema_version must equal {PLANNING_TRACE_SCHEMA_VERSION}"
        )
    event_type = event.get("event_type")
    expected_type = _KIND_TO_EVENT_TYPE.get(kind) if isinstance(kind, str) else None
    expected_value = expected_type.value if expected_type is not None else None
    if event_type != expected_value:
        errors.append("event_type must match kind")
    sequence = event.get("sequence")
    if type(sequence) is not int or sequence < 1:
        errors.append("sequence must be a positive int")
    if not isinstance(event.get("timestamp"), str) or not event["timestamp"].strip():
        errors.append("timestamp must be a non-empty string")
    if not isinstance(event.get("name"), str) or not event["name"].strip():
        errors.append("name must be a non-empty string")
    status = event.get("status")
    if status is not None and (not isinstance(status, str) or not status.strip()):
        errors.append("status must be a non-empty string or null")
    reason = event.get("reason")
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        errors.append("reason must be a non-empty string or null")
    error_type = event.get("error_type")
    if error_type is not None and (
        not isinstance(error_type, str) or not error_type.strip()
    ):
        errors.append("error_type must be a non-empty string or null")
    if kind == "terminate":
        if not isinstance(reason, str) or not reason.strip():
            errors.append("terminate events require a non-empty reason")
    step = event.get("step")
    if step is not None and (type(step) is not int or step < 0):
        errors.append("step must be a non-negative int or null")
    attrs = event.get("attrs")
    if not isinstance(attrs, Mapping):
        errors.append("attrs must be a mapping")
    else:
        if attrs.get("run_id") != run_id:
            errors.append("attrs.run_id must match run_id")
        if attrs.get("kind") != kind:
            errors.append("attrs.kind must match kind")
        if "status" in attrs and attrs.get("status") != status:
            errors.append("attrs.status must match status")
        if "reason" in attrs and attrs.get("reason") != reason:
            errors.append("attrs.reason must match reason")
        if "error_type" in attrs and attrs.get("error_type") != error_type:
            errors.append("attrs.error_type must match error_type")
        budget = attrs.get("budget")
        if budget is not None:
            if not isinstance(budget, Mapping):
                errors.append("attrs.budget must be a mapping")
            else:
                for field_name in _BUDGET_FIELDS:
                    value = budget.get(field_name)
                    if type(value) is not int or value < 0:
                        errors.append(
                            f"attrs.budget.{field_name} must be a non-negative int"
                        )
        if kind == "plan":
            if not isinstance(attrs.get("plan_id"), str) or not attrs["plan_id"]:
                errors.append("plan attrs require plan_id")
            if type(attrs.get("step_count")) is not int or attrs["step_count"] < 1:
                errors.append("plan attrs require a positive step_count")
        elif kind == "action":
            if not isinstance(attrs.get("tool_name"), str) or not attrs["tool_name"]:
                errors.append("action attrs require tool_name")
        elif kind == "observation":
            if not isinstance(attrs.get("status"), str) or not attrs["status"]:
                errors.append("observation attrs require status")
        elif kind == "replan":
            if not isinstance(attrs.get("reason"), str) or not attrs["reason"]:
                errors.append("replan attrs require reason")
        elif kind == "terminate":
            if type(attrs.get("success")) is not bool:
                errors.append("terminate attrs require an exact success boolean")
            if not isinstance(attrs.get("reason"), str) or not attrs["reason"]:
                errors.append("terminate attrs require reason")
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

    invalid_event_count = 0
    mixed_run_event_count = 0
    out_of_order_event_count = 0
    accepted_event_count = 0
    previous_sequence = 0

    for raw in events:
        if not isinstance(raw, Mapping):
            invalid_event_count += 1
            continue
        if validate_planning_trace_event(raw):
            invalid_event_count += 1
            continue
        kind = raw.get("kind")
        raw_run_id = raw["run_id"]
        if run_id is None:
            run_id = raw_run_id
        elif raw_run_id != run_id:
            mixed_run_event_count += 1
            continue
        sequence = raw["sequence"]
        if sequence <= previous_sequence:
            out_of_order_event_count += 1
            continue
        previous_sequence = sequence
        accepted_event_count += 1
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
        "event_count": accepted_event_count,
        "input_event_count": len(events),
        "invalid_event_count": invalid_event_count,
        "mixed_run_event_count": mixed_run_event_count,
        "out_of_order_event_count": out_of_order_event_count,
        "complete": (
            bool(plans)
            and accepted_event_count >= 2
            and terminate is not None
            and invalid_event_count == 0
            and mixed_run_event_count == 0
            and out_of_order_event_count == 0
        ),
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
        resolved_run_id = build_planning_run_id() if run_id is None else run_id
        if not isinstance(resolved_run_id, str) or _RUN_ID_RE.fullmatch(resolved_run_id) is None:
            raise ValueError("run_id must be a bounded correlation identifier")
        if enabled is not None and type(enabled) is not bool:
            raise ValueError("enabled must be an exact boolean")
        if type(max_events) is not int or not 1 <= max_events <= MAX_PLANNING_TRACE_EVENTS:
            raise ValueError(
                f"max_events must be an integer within [1, {MAX_PLANNING_TRACE_EVENTS}]"
            )
        self.run_id = resolved_run_id
        self.enabled = is_planning_trace_enabled() if enabled is None else enabled
        self.max_events = max_events
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
        values = {
            "tool_call_count": tool_call_count,
            "max_total_tool_calls": max_total_tool_calls,
            "observation_replans": observation_replans,
            "max_observation_replans": max_observation_replans,
            "planning_tokens": planning_tokens,
        }
        for field_name, value in values.items():
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative int")
        return dict(values)

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
        _require_positive_int("step_count", step_count)
        _require_optional_step(step)
        payload = _extra_attrs(attrs)
        payload.update({
            "plan_id": plan_id,
            "step_count": step_count,
            "role": role,
        })
        if budget:
            payload["budget"] = dict(budget)
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
        _require_optional_step(step)
        payload = _extra_attrs(attrs)
        payload.update({
            "tool_name": tool_name,
        })
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
        _require_optional_step(step)
        _require_nonnegative_int("tool_count", tool_count)
        payload = _extra_attrs(attrs)
        payload.update({
            "status": status,
            "tool_count": tool_count,
        })
        if plan_id:
            payload["plan_id"] = plan_id
        if resolved_error:
            payload["error_type"] = resolved_error
            payload["failure_reason"] = resolved_error
        if budget:
            payload["budget"] = dict(budget)
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
        _require_optional_step(failed_step)
        _require_nonnegative_int("observation_replans", observation_replans)
        payload = _extra_attrs(attrs)
        payload.update({
            "reason": reason,
            "previous_plan_id": previous_plan_id,
            "observation_replans": observation_replans,
        })
        if new_plan_id:
            payload["new_plan_id"] = new_plan_id
        if failed_step is not None:
            payload["failed_step"] = failed_step
        if budget:
            payload["budget"] = dict(budget)
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
        if type(success) is not bool:
            raise ValueError("success must be an exact boolean")
        # Acceptance: terminate always carries a reason.
        resolved_reason = (reason or "").strip() or ("completed" if success else "failed")
        payload = _extra_attrs(attrs)
        payload.update({
            "reason": resolved_reason,
            "status": status,
            "success": success,
        })
        if plan_id:
            payload["plan_id"] = plan_id
        if error_type:
            payload["error_type"] = error_type
        if budget:
            payload["budget"] = dict(budget)
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
        # Correlation and semantic fields are authoritative. Caller-supplied
        # attrs cannot forge a different run, event kind, or terminal outcome.
        safe_name = _safe_event_text(name, default=kind)
        safe_status = _safe_event_text(status) if status is not None else None
        safe_reason = _safe_event_text(reason) if reason is not None else None
        safe_error_type = (
            _safe_event_text(error_type) if error_type is not None else None
        )
        safe_attrs["run_id"] = self.run_id
        safe_attrs["kind"] = kind
        if safe_reason:
            safe_attrs["reason"] = safe_reason
        else:
            safe_attrs.pop("reason", None)
        if safe_error_type:
            safe_attrs["error_type"] = safe_error_type
        else:
            safe_attrs.pop("error_type", None)

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
            "name": safe_name,
            "status": safe_status,
            "step": step,
            "reason": safe_reason,
            "error_type": safe_error_type,
            "attrs": safe_attrs,
        }

        violations = validate_planning_trace_event(record)
        if violations:
            raise ValueError("invalid planning trace event: " + "; ".join(violations))

        self._events.append(record)
        while len(self._events) > self.max_events:
            self._events.pop(0)

        # Best-effort dual-write into the shared agent event stream (#1125 path).
        emit_agent_event(
            event_type,
            name=safe_name,
            phase="planning",
            status=safe_status,
            step=step,
            attrs=safe_attrs,
        )
        return record


def _extra_attrs(attrs: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Return extension attrs without fields owned by the trace contract."""
    if attrs is None:
        return {}
    if not isinstance(attrs, Mapping):
        raise ValueError("attrs must be a mapping")
    return {
        str(key): value
        for key, value in attrs.items()
        if str(key) not in _RESERVED_ATTR_FIELDS
    }


def _safe_event_text(value: Any, *, default: str = "") -> str:
    safe = sanitize_agent_event_payload(value, deep=False)
    if isinstance(safe, str) and safe.strip():
        return safe.strip()
    return default


def _require_nonnegative_int(name: str, value: Any) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative int")


def _require_positive_int(name: str, value: Any) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive int")


def _require_optional_step(value: Any) -> None:
    if value is not None:
        _require_nonnegative_int("step", value)
