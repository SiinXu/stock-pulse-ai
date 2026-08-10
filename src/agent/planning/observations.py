# -*- coding: utf-8 -*-
"""Typed observations and execution outcomes for the plan→act→observe loop.

Observations are intentionally value-safe: free-form tool payloads are reduced
to bounded status, error codes, and short sanitized summaries. They feed both
the replan path and the existing agent observability / diagnostics channel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.agent.planning.config import (
    MAX_OBSERVATION_ERROR_CODE_CHARS,
    MAX_RESULT_SUMMARY_CHARS,
    MAX_TOOL_NAME_CHARS,
    MAX_TRACE_STEPS,
)
from src.agent.planning.types import AgentPlan, PLAN_SCHEMA_VERSION

_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_SAFE_STATUS = frozenset(
    {
        "pending",
        "running",
        "succeeded",
        "failed",
        "skipped",
        "cancelled",
        "timed_out",
        "budget_exhausted",
    }
)
_TERMINAL_STATUS = frozenset(
    {
        "succeeded",
        "failed",
        "cancelled",
        "timed_out",
        "budget_exhausted",
        "replan_failed",
        "max_observation_replans_exceeded",
        "max_tool_calls_exceeded",
        "invalid_plan",
        "invalid_invoker",
    }
)


def _safe_code(value: Any, *, default: str = "unknown") -> str:
    text = str(value or "").strip()
    if _SAFE_CODE_RE.fullmatch(text) and len(text) <= MAX_OBSERVATION_ERROR_CODE_CHARS:
        return text
    return default


def _safe_tool_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > MAX_TOOL_NAME_CHARS:
        return "unknown"
    if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", text):
        return text
    return "unknown"


def summarize_tool_result(
    payload: Any,
    *,
    max_chars: int,
) -> str:
    """Reduce a tool result to a short, non-sensitive summary for observations."""
    if type(max_chars) is not int or not 1 <= max_chars <= MAX_RESULT_SUMMARY_CHARS:
        max_chars = min(
            MAX_RESULT_SUMMARY_CHARS,
            max(1, int(max_chars) if isinstance(max_chars, int) else 160),
        )
    if payload is None:
        return ""
    if isinstance(payload, dict):
        if payload.get("ok") is False:
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            code = _safe_code(
                error.get("code") if isinstance(error, dict) else None,
                default="tool_failed",
            )
            return f"error:{code}"[:max_chars]
        preview = payload.get("diagnostics")
        if isinstance(preview, dict) and isinstance(preview.get("preview"), str):
            text = preview["preview"].strip()
            return text[:max_chars]
        if isinstance(payload.get("result_text"), str):
            return payload["result_text"].strip()[:max_chars]
        if payload.get("ok") is True:
            return "ok"
    if isinstance(payload, str):
        return payload.strip()[:max_chars]
    text = str(payload).strip()
    return text[:max_chars]


def interpret_tool_payload(payload: Any) -> Tuple[bool, Optional[str], str]:
    """Map a ToolSurface-shaped (or simplified) payload to ok / error_code / summary.

    Accepts:
    - ToolSurface results: ``{"ok": bool, "error": {"code": ...}, ...}``
    - Simplified invoker results: ``{"ok": bool, "error_code": str, "summary": str}``
    - Bare truthy/falsey is rejected: callers must be explicit so failures never
      fail-open as success.
    """
    if not isinstance(payload, dict):
        return False, "invalid_tool_result", "tool result must be a mapping"
    if "ok" not in payload:
        return False, "invalid_tool_result", "tool result requires explicit ok boolean"
    ok = payload.get("ok")
    if type(ok) is not bool:
        return False, "invalid_tool_result", "tool result ok must be an exact boolean"
    if ok:
        summary = ""
        if isinstance(payload.get("summary"), str):
            summary = payload["summary"].strip()
        if not summary:
            summary = summarize_tool_result(payload, max_chars=MAX_RESULT_SUMMARY_CHARS)
        return True, None, summary
    error = payload.get("error")
    if isinstance(error, dict):
        code = _safe_code(error.get("code"), default="tool_failed")
    else:
        code = _safe_code(payload.get("error_code"), default="tool_failed")
    if isinstance(payload.get("summary"), str) and payload["summary"].strip():
        summary = payload["summary"].strip()
    else:
        summary = (
            summarize_tool_result(payload, max_chars=MAX_RESULT_SUMMARY_CHARS)
            or f"error:{code}"
        )
    return False, code, summary


@dataclass(frozen=True)
class ToolCallObservation:
    """One tool invocation recorded during plan execution."""

    tool_name: str
    ok: bool
    error_code: Optional[str] = None
    summary: str = ""
    duration_ms: Optional[int] = None
    step_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "tool_name": self.tool_name,
            "ok": self.ok,
            "summary": self.summary,
        }
        if self.error_code:
            data["error_code"] = self.error_code
        if self.duration_ms is not None:
            data["duration_ms"] = int(self.duration_ms)
        if self.step_id is not None:
            data["step_id"] = int(self.step_id)
        return data


@dataclass(frozen=True)
class StepObservation:
    """Outcome of one plan step after its tool calls (or empty synthesis)."""

    step_id: int
    status: str
    goal: str = ""
    tool_calls: Tuple[ToolCallObservation, ...] = ()
    failure_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "step_id": self.step_id,
            "status": self.status,
            "goal": self.goal,
            "tool_calls": [call.to_dict() for call in self.tool_calls],
        }
        if self.failure_reason:
            data["failure_reason"] = self.failure_reason
        return data


@dataclass
class PlanExecutionResult:
    """Terminal outcome of a plan→act→observe (optional replan) run.

    ``success`` is true only when every executed step of the active plan completed
    successfully and the loop finished without hitting a budget or cancellation
    fence. Failures never fail-open as success.
    """

    success: bool
    status: str
    plan: Optional[AgentPlan] = None
    initial_plan_id: Optional[str] = None
    final_plan_id: Optional[str] = None
    step_observations: List[StepObservation] = field(default_factory=list)
    tool_call_count: int = 0
    observation_replans: int = 0
    planning_tokens: int = 0
    reason: Optional[str] = None
    error_code: Optional[str] = None
    cancelled: bool = False
    timed_out: bool = False
    duration_ms: Optional[int] = None
    plans: List[Dict[str, Any]] = field(default_factory=list)

    def to_metadata(self) -> Dict[str, Any]:
        """Trace-safe metadata for diagnostics / audit consumers."""
        payload: Dict[str, Any] = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "success": self.success,
            "status": (
                self.status
                if self.status in _TERMINAL_STATUS or self.status in _SAFE_STATUS
                else "failed"
            ),
            "tool_call_count": int(self.tool_call_count),
            "observation_replans": int(self.observation_replans),
            "planning_tokens": int(self.planning_tokens),
            "cancelled": bool(self.cancelled),
            "timed_out": bool(self.timed_out),
            "step_count_observed": len(self.step_observations),
        }
        if self.initial_plan_id:
            payload["initial_plan_id"] = self.initial_plan_id
        if self.final_plan_id:
            payload["final_plan_id"] = self.final_plan_id
        if self.reason:
            payload["reason"] = _safe_code(self.reason, default="failed")
        if self.error_code:
            payload["error_code"] = _safe_code(self.error_code, default="failed")
        if self.duration_ms is not None:
            payload["duration_ms"] = int(self.duration_ms)
        if self.plan is not None:
            payload["plan_id"] = self.plan.plan_id
            payload["plan_step_count"] = self.plan.step_count
        obs = self.step_observations[:MAX_TRACE_STEPS]
        payload["observations"] = [item.to_dict() for item in obs]
        if len(self.step_observations) > MAX_TRACE_STEPS:
            payload["observations_truncated"] = True
        if self.plans:
            payload["plans"] = list(self.plans)[:MAX_TRACE_STEPS]
        return payload


def compact_observation_summary(
    observations: Sequence[StepObservation],
    *,
    max_chars: int = 1_500,
) -> str:
    """Render a compact, planner-safe observation brief for replan prompts."""
    lines: List[str] = []
    for obs in observations:
        if obs.status == "succeeded":
            tools = ",".join(call.tool_name for call in obs.tool_calls) or "(none)"
            lines.append(f"step {obs.step_id}: succeeded tools={tools}")
        else:
            reason = obs.failure_reason or "failed"
            failed = [
                f"{call.tool_name}:{call.error_code or 'failed'}"
                for call in obs.tool_calls
                if not call.ok
            ]
            detail = ",".join(failed) if failed else reason
            lines.append(f"step {obs.step_id}: {obs.status} detail={detail}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text
