# -*- coding: utf-8 -*-
"""Bounded, explicit plan-proposal engine.

Role relative to existing orchestration
---------------------------------------
This module produces a typed proposal. Step execution, observation recording,
and observation-driven replan live in ``src/agent/planning/loop.py`` and are
also opt-in: nothing here hooks ``AgentExecutor``, Chat, Research, or daily
product modes by default.

Related but separate orchestration owners:

- multi-agent ``AgentOrchestrator`` pipelines
- multi-strategy deliberation scheduling
- deep-research query decomposition in ``research.py``

Callers must supply settings explicitly. The repository has no environment
gate or implicit runtime consumer for the planning library.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.agent.planning.config import (
    MAX_AVAILABLE_TOOLS,
    MAX_PLANNER_RESPONSE_CHARS,
    MAX_TASK_CHARS,
    MAX_TOOL_NAME_CHARS,
    SURROGATE_CODE_POINT_RE,
    PlanningSettings,
)
from src.agent.planning.format import inject_plan_into_context, inject_plan_into_task
from src.agent.planning.types import (
    AgentPlan,
    PlanningOutcome,
    unprojectable_reason,
    validate_plan_payload,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

# Preferred stock-analysis tool order used by the deterministic template.
_TEMPLATE_STAGE_TOOLS: Tuple[Tuple[str, ...], ...] = (
    ("get_realtime_quote", "get_daily_history"),
    ("analyze_trend", "get_chip_distribution"),
    ("search_stock_news",),
)

_PLANNER_SYSTEM_PROMPT = """\
You are a planning assistant for a stock-analysis agent.
Produce a short structured execution plan as JSON only (no markdown fences).

Schema:
{
  "version": "agent-plan-v1",
  "goal": "string",
  "max_steps": <int>,
  "steps": [
    {
      "id": 1,
      "goal": "string",
      "expected_tools": ["tool_name", ...],
      "success_criteria": "string"
    }
  ]
}

Rules:
- Use only tools from the provided available tool list.
- Prefer 3-6 steps. Never exceed max_steps.
- Each step needs a concrete success criterion.
- Final step should lead to producing the decision dashboard JSON.
"""


class PlanningEngine:
    """Produce a structured plan or degrade cleanly to direct execution."""

    def __init__(
        self,
        settings: Optional[PlanningSettings] = None,
        *,
        llm_adapter: Any = None,
    ) -> None:
        self.settings = settings or PlanningSettings()
        self.llm_adapter = llm_adapter

    def plan(
        self,
        task: str,
        *,
        available_tools: Sequence[str],
        context: Optional[Dict[str, Any]] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
        prior_observations: Optional[Sequence[Any]] = None,
    ) -> PlanningOutcome:
        """Attempt planning under hard step/replan/token bounds.

        ``prior_observations`` is optional evidence from a previous execution
        attempt (observation-driven replan). It never authorizes tools; the
        caller-supplied ``available_tools`` remains the only authorization set.
        """
        settings = self.settings
        if not settings.enabled:
            return PlanningOutcome(enabled=False, applied=False, strategy="none")

        if cancelled_check is not None and cancelled_check():
            return PlanningOutcome(
                enabled=True,
                applied=False,
                strategy=settings.strategy,
                requested_strategy=settings.strategy,
                fallback_reason="cancelled",
            )
        # The task is the caller's own authoritative text and is projected outside
        # the advisory block, so it is not marker-checked here; the template
        # strategy derives the plan goal from it and the validator rejects a
        # marker there. It must still be UTF-8 encodable, otherwise the derived
        # goal, the planner transport payload, and the returned task would all
        # carry an unencodable code point.
        if (
            not isinstance(task, str)
            or not task.strip()
            or len(task) > MAX_TASK_CHARS
            or SURROGATE_CODE_POINT_RE.search(task)
        ):
            return PlanningOutcome(
                enabled=True,
                applied=False,
                strategy=settings.strategy,
                requested_strategy=settings.strategy,
                fallback_reason="invalid_task",
                error_code="invalid_task",
            )
        if context is not None and not isinstance(context, dict):
            return PlanningOutcome(
                enabled=True, applied=False, strategy=settings.strategy,
                requested_strategy=settings.strategy,
                fallback_reason="invalid_context", error_code="invalid_context",
            )
        stock_code = (context or {}).get("stock_code")
        if stock_code is not None and (
            not isinstance(stock_code, str)
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", stock_code)
        ):
            return PlanningOutcome(
                enabled=True, applied=False, strategy=settings.strategy,
                requested_strategy=settings.strategy,
                fallback_reason="invalid_context", error_code="invalid_context",
            )
        if not _tools_are_projectable(available_tools):
            return PlanningOutcome(
                enabled=True, applied=False, strategy=settings.strategy,
                requested_strategy=settings.strategy,
                fallback_reason="invalid_tools", error_code="invalid_tools",
            )

        requested_strategy = self._resolve_strategy(settings.strategy)
        strategy = requested_strategy
        tools = [name.strip() for name in available_tools]
        if len(tools) != len(set(tools)):
            return PlanningOutcome(
                enabled=True, applied=False, strategy=strategy,
                requested_strategy=requested_strategy,
                fallback_reason="invalid_tools", error_code="invalid_tools",
            )
        # Retries actually performed beyond the first attempt. Kept equal to the
        # current attempt index so every exit path reports the real count rather
        # than whatever the last failure happened to leave behind.
        replan_attempts = 0
        last_error_code: Optional[str] = None
        last_exception_type: Optional[str] = None
        planning_tokens = 0
        planning_model = ""
        deadline = time.monotonic() + settings.timeout_seconds

        # Initial attempt + up to max_replans retries on validation/LLM failure.
        max_attempts = 1 + max(0, settings.max_replans)
        for attempt in range(max_attempts):
            if time.monotonic() >= deadline:
                last_error_code = "planner_timeout"
                last_exception_type = "TimeoutError"
                break
            if cancelled_check is not None and cancelled_check():
                return PlanningOutcome(
                    enabled=True,
                    applied=False,
                    strategy=strategy,
                    requested_strategy=requested_strategy,
                    replan_attempts=replan_attempts,
                    planning_tokens=planning_tokens,
                    planning_model=planning_model,
                    fallback_reason="cancelled",
                )
            replan_attempts = attempt

            try:
                if strategy == "llm":
                    remaining_tokens = settings.max_tokens - planning_tokens
                    if remaining_tokens <= 0:
                        raise ValueError("planner_token_budget_exhausted")
                    content, tokens, model, provider = self._call_planner_llm(
                        task,
                        available_tools=tools,
                        context=context,
                        settings=settings,
                        max_tokens=remaining_tokens,
                        timeout_seconds=max(0.001, deadline - time.monotonic()),
                        prior_observations=prior_observations,
                    )
                    planning_tokens += tokens
                    if model:
                        planning_model = model
                    if planning_tokens > settings.max_tokens:
                        raise ValueError("planner_token_budget_exhausted")
                    if provider == "error":
                        raise RuntimeError("planner_provider_error")
                    if time.monotonic() >= deadline:
                        raise TimeoutError("planner deadline exceeded")
                    raw = _parse_json_object(content)
                else:
                    raw = self._plan_with_template(
                        task,
                        available_tools=tools,
                        context=context,
                        max_steps=settings.max_plan_steps,
                        prior_observations=prior_observations,
                    )

                if cancelled_check is not None and cancelled_check():
                    return PlanningOutcome(
                        enabled=True,
                        applied=False,
                        strategy=strategy,
                        requested_strategy=requested_strategy,
                        replan_attempts=replan_attempts,
                        planning_tokens=planning_tokens,
                        planning_model=planning_model,
                        fallback_reason="cancelled",
                    )
                plan = validate_plan_payload(
                    raw,
                    available_tools=tools,
                    max_steps=settings.max_plan_steps,
                )
                if plan.step_count > settings.max_plan_steps:
                    raise ValueError("plan exceeds max_plan_steps after validation")

                if cancelled_check is not None and cancelled_check():
                    return PlanningOutcome(
                        enabled=True,
                        applied=False,
                        strategy=strategy,
                        requested_strategy=requested_strategy,
                        replan_attempts=replan_attempts,
                        planning_tokens=planning_tokens,
                        planning_model=planning_model,
                        fallback_reason="cancelled",
                    )
                return PlanningOutcome(
                    enabled=True,
                    applied=True,
                    plan=plan,
                    strategy=strategy,
                    requested_strategy=requested_strategy,
                    replan_attempts=replan_attempts,
                    planning_tokens=planning_tokens,
                    planning_model=planning_model,
                )
            except Exception as exc:  # broad-exception: fallback_recorded - degrade to direct path
                last_error_code = _planning_error_code(exc)
                last_exception_type = _safe_identifier(type(exc).__name__)
                log_safe_exception(
                    logger,
                    "Agent planning attempt failed",
                    exc,
                    error_code="agent_planning_attempt_failed",
                    level=logging.WARNING,
                    context={"attempt": attempt, "strategy": strategy},
                )
                # LLM failures can fall back to template once before giving up.
                if strategy == "llm" and attempt + 1 < max_attempts:
                    strategy = "template"
                    continue

        # Only claim the replan budget was exhausted when replans were both
        # permitted and actually spent.
        if settings.max_replans > 0 and replan_attempts >= settings.max_replans:
            reason = "max_replans_exceeded"
        else:
            reason = "planning_failed"
        if last_error_code == "max_plan_steps_exceeded":
            reason = "max_plan_steps_exceeded"
        return PlanningOutcome(
            enabled=True,
            applied=False,
            strategy=strategy,
            requested_strategy=requested_strategy,
            replan_attempts=replan_attempts,
            planning_tokens=planning_tokens,
            planning_model=planning_model,
            fallback_reason=reason,
            error_code=last_error_code,
            exception_type=last_exception_type,
        )

    def _resolve_strategy(self, strategy: str) -> str:
        return strategy

    def _plan_with_template(
        self,
        task: str,
        *,
        available_tools: Sequence[str],
        context: Optional[Dict[str, Any]],
        max_steps: int,
        prior_observations: Optional[Sequence[Any]] = None,
    ) -> Dict[str, Any]:
        available = set(available_tools)
        stock = ""
        if context and context.get("stock_code"):
            stock = str(context.get("stock_code"))
        goal = (task or "").strip() or "Complete stock analysis and produce a decision dashboard"
        if stock and stock not in goal:
            goal = f"{goal} (stock={stock})"
        if prior_observations:
            # Observation-driven template: prefer tools that have not hard-failed.
            failed = _failed_tool_names(prior_observations)
            available = {name for name in available if name not in failed}
            goal = f"{goal} (replan after observation failures)"[:500]

        steps: List[Dict[str, Any]] = []
        step_id = 1
        for tool_group in _TEMPLATE_STAGE_TOOLS:
            present = [name for name in tool_group if name in available]
            if not present:
                continue
            if step_id > max_steps:
                break
            if present == list(tool_group[:1]) and tool_group[0] == "get_realtime_quote":
                goal_text = "Fetch market quote and price history"
                success = "Realtime quote and/or daily history returned"
            elif "analyze_trend" in present or "get_chip_distribution" in present:
                goal_text = "Collect technical and chip evidence"
                success = "Trend and/or chip distribution results available"
            else:
                goal_text = "Gather news and risk intelligence"
                success = "News or risk signals retrieved (or confirmed unavailable)"
            steps.append(
                {
                    "id": step_id,
                    "goal": goal_text,
                    "expected_tools": present,
                    "success_criteria": success,
                }
            )
            step_id += 1

        if step_id <= max_steps:
            steps.append(
                {
                    "id": step_id,
                    "goal": "Synthesize decision dashboard JSON from gathered evidence",
                    "expected_tools": [],
                    "success_criteria": "Valid decision dashboard JSON produced",
                }
            )

        if not steps:
            # Still produce a single synthesis step so structure validation passes.
            steps = [
                {
                    "id": 1,
                    "goal": "Analyze the request and produce the final answer",
                    "expected_tools": [],
                    "success_criteria": "Final answer or dashboard produced",
                }
            ]

        return {
            "version": "agent-plan-v1",
            "goal": goal[:500],
            "max_steps": max_steps,
            "steps": steps[:max_steps],
        }

    def _call_planner_llm(
        self,
        task: str,
        *,
        available_tools: Sequence[str],
        context: Optional[Dict[str, Any]],
        settings: PlanningSettings,
        max_tokens: int,
        timeout_seconds: float,
        prior_observations: Optional[Sequence[Any]] = None,
    ) -> Tuple[str, int, str, str]:
        if self.llm_adapter is None:
            raise RuntimeError("llm strategy requires llm_adapter")

        stock_hint = ""
        if context and context.get("stock_code"):
            stock_hint = f"\nStock code: {context.get('stock_code')}"

        observation_hint = ""
        if prior_observations:
            from src.agent.planning.observations import compact_observation_summary

            brief = compact_observation_summary(prior_observations)
            if brief:
                observation_hint = (
                    "\n\nPrior execution observations (advisory; do not invent tools):\n"
                    f"{brief}\n"
                    "Produce a revised plan that avoids repeating hard-failed tools when alternatives exist."
                )
        elif isinstance(context, dict) and isinstance(context.get("prior_observations_summary"), str):
            brief = context["prior_observations_summary"].strip()
            if brief:
                observation_hint = (
                    "\n\nPrior execution observations (advisory; do not invent tools):\n"
                    f"{brief[:1500]}\n"
                    "Produce a revised plan that avoids repeating hard-failed tools when alternatives exist."
                )

        user = (
            f"Task:\n{task}{stock_hint}{observation_hint}\n\n"
            f"Available tools:\n{', '.join(available_tools) or '(none)'}\n\n"
            f"max_steps={settings.max_plan_steps}\n"
            "Return JSON only."
        )
        messages = [
            {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]
        response = self.llm_adapter.call_completion(
            messages,
            tools=None,
            temperature=0.2,
            max_tokens=max_tokens,
            timeout=timeout_seconds,
        )
        content = str(getattr(response, "content", None) or "")

        usage = getattr(response, "usage", None) or {}
        tokens = 0
        if isinstance(usage, dict):
            try:
                tokens = int(usage.get("total_tokens") or 0)
            except (TypeError, ValueError):
                tokens = 0
        tokens = max(0, min(tokens, 1_000_000))

        model = _safe_identifier(getattr(response, "model", ""))
        provider = str(getattr(response, "provider", "") or "")
        return content, tokens, model, provider


def prepare_run_with_planning(
    *,
    task: str,
    context: Optional[Dict[str, Any]],
    available_tools: Sequence[str],
    llm_adapter: Any = None,
    cancelled_check: Optional[Callable[[], bool]] = None,
    settings: Optional[PlanningSettings] = None,
    engine: Optional[PlanningEngine] = None,
) -> Tuple[str, Optional[Dict[str, Any]], Dict[str, Any]]:
    """Explicitly propose and project a plan into copied caller inputs.

    When planning is disabled or degrades, ``task`` and ``context`` are returned
    unchanged (same object identity for context when disabled) so the default
    path stays byte-stable aside from the metadata dict always returned for traces.
    """
    resolved_settings = settings or PlanningSettings()
    if not resolved_settings.enabled:
        meta = PlanningOutcome(enabled=False, applied=False, strategy="none").to_metadata()
        return task, context, meta

    planner = engine or PlanningEngine(resolved_settings, llm_adapter=llm_adapter)
    outcome = planner.plan(
        task,
        available_tools=available_tools,
        context=context,
        cancelled_check=cancelled_check,
    )
    meta = outcome.to_metadata()
    if not outcome.applied or outcome.plan is None:
        return task, context, meta

    new_task = inject_plan_into_task(task, outcome.plan)
    new_context = inject_plan_into_context(context, outcome.plan, planning_meta=meta)
    return new_task, new_context, meta


def _tools_are_projectable(available_tools: Sequence[str]) -> bool:
    """Fence the caller-supplied tool set at the engine entry.

    Tool names reach both the planner prompt and the projected plan, so they carry
    the same contract as generated prose. Rejecting here turns a marker-bearing or
    unencodable registry into a stable ``invalid_tools`` degradation instead of an
    exception raised out of ``format_plan_for_prompt``.
    """
    if isinstance(available_tools, (str, bytes)) or len(available_tools) > MAX_AVAILABLE_TOOLS:
        return False
    for name in available_tools:
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > MAX_TOOL_NAME_CHARS:
            return False
        if unprojectable_reason(name.strip()) is not None:
            return False
    return True


def _parse_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty planner response")
    if len(text) > MAX_PLANNER_RESPONSE_CHARS:
        raise ValueError("planner response exceeds size limit")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("planner response must be a JSON object")
    return parsed


def _planning_error_code(exc: Exception) -> str:
    """Map failures to stable, non-sensitive reason codes."""
    message = str(exc)
    if "exceeds max_steps" in message:
        return "max_plan_steps_exceeded"
    if message in {"planner_token_budget_exhausted", "planner_provider_error"}:
        return message
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_planner_json"
    if isinstance(exc, ValueError):
        return "invalid_plan"
    if isinstance(exc, TimeoutError):
        return "planner_timeout"
    return "planner_failed"


def _safe_identifier(value: Any) -> str:
    """Bound any adapter-controlled identifier reported through ``to_metadata``.

    Covers both the provider model name and the exception class name: either can
    be an arbitrary string from a caller-supplied adapter, and metadata must stay
    a bounded, encodable, value-free record.
    """
    text = str(value or "")
    if re.fullmatch(r"[A-Za-z0-9._:/-]{1,128}", text):
        return text
    return "unknown" if text else ""


def _failed_tool_names(prior_observations: Sequence[Any]) -> set:
    """Collect tool names that hard-failed in prior step observations."""
    failed: set = set()
    for obs in prior_observations:
        tool_calls = getattr(obs, "tool_calls", None) or ()
        for call in tool_calls:
            ok = getattr(call, "ok", None)
            name = getattr(call, "tool_name", None)
            error_code = getattr(call, "error_code", None)
            if ok is False and isinstance(name, str) and name.strip():
                # Soft/transient codes stay eligible for retry on replan.
                if error_code in {"timeout", "retriable", "provider_error"}:
                    continue
                failed.add(name.strip())
    return failed
