# -*- coding: utf-8 -*-
"""Bounded planning pre-step for AgentExecutor (plan-and-execute style).

Role relative to existing orchestration
---------------------------------------
This module is a **pre-step** in front of the single-agent ReAct loop
(``AgentExecutor`` → ``run_agent_loop``). It does **not** replace:

- multi-agent ``AgentOrchestrator`` pipelines
- multi-strategy deliberation scheduling
- deep-research query decomposition in ``research.py``

When ``AGENT_PLANNING_ENABLED`` is false (default), callers get an inert
outcome and must keep the original task/context unchanged.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.agent.planning.config import PlanningSettings, load_planning_settings
from src.agent.planning.format import inject_plan_into_context, inject_plan_into_task
from src.agent.planning.types import AgentPlan, PlanningOutcome, validate_plan_payload
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
        self.settings = settings or load_planning_settings()
        self.llm_adapter = llm_adapter

    def plan(
        self,
        task: str,
        *,
        available_tools: Sequence[str],
        context: Optional[Dict[str, Any]] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
    ) -> PlanningOutcome:
        """Attempt planning under hard step/replan/token bounds."""
        settings = self.settings
        if not settings.enabled:
            return PlanningOutcome(enabled=False, applied=False, strategy="none")

        if cancelled_check is not None and cancelled_check():
            return PlanningOutcome(
                enabled=True,
                applied=False,
                strategy=settings.strategy,
                fallback_reason="cancelled",
            )

        strategy = self._resolve_strategy(settings.strategy)
        tools = [str(name) for name in available_tools if str(name).strip()]
        replan_attempts = 0
        last_error: Optional[str] = None
        planning_tokens = 0
        planning_model = ""

        # Initial attempt + up to max_replans retries on validation/LLM failure.
        max_attempts = 1 + max(0, settings.max_replans)
        for attempt in range(max_attempts):
            if cancelled_check is not None and cancelled_check():
                return PlanningOutcome(
                    enabled=True,
                    applied=False,
                    strategy=strategy,
                    replan_attempts=replan_attempts,
                    planning_tokens=planning_tokens,
                    planning_model=planning_model,
                    fallback_reason="cancelled",
                )

            try:
                if strategy == "llm":
                    raw, tokens, model = self._plan_with_llm(
                        task,
                        available_tools=tools,
                        context=context,
                        settings=settings,
                    )
                    planning_tokens += tokens
                    if model:
                        planning_model = model
                else:
                    raw = self._plan_with_template(
                        task,
                        available_tools=tools,
                        context=context,
                        max_steps=settings.max_plan_steps,
                    )

                plan = validate_plan_payload(
                    raw,
                    available_tools=tools,
                    max_steps=settings.max_plan_steps,
                )
                if plan.step_count > settings.max_plan_steps:
                    raise ValueError("plan exceeds max_plan_steps after validation")

                return PlanningOutcome(
                    enabled=True,
                    applied=True,
                    plan=plan,
                    strategy=strategy,
                    replan_attempts=replan_attempts,
                    planning_tokens=planning_tokens,
                    planning_model=planning_model,
                )
            except Exception as exc:  # broad-exception: fallback_recorded - degrade to direct path
                last_error = str(exc)
                replan_attempts = attempt
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

        reason = "max_replans_exceeded" if replan_attempts >= settings.max_replans else "planning_failed"
        if last_error and "exceeds max_steps" in last_error:
            reason = "max_plan_steps_exceeded"
        return PlanningOutcome(
            enabled=True,
            applied=False,
            strategy=strategy,
            replan_attempts=replan_attempts,
            planning_tokens=planning_tokens,
            planning_model=planning_model,
            fallback_reason=reason,
            error=last_error,
        )

    def _resolve_strategy(self, strategy: str) -> str:
        if strategy == "template":
            return "template"
        if strategy == "llm":
            if self.llm_adapter is None:
                return "template"
            return "llm"
        # auto
        if self.llm_adapter is not None:
            return "llm"
        return "template"

    def _plan_with_template(
        self,
        task: str,
        *,
        available_tools: Sequence[str],
        context: Optional[Dict[str, Any]],
        max_steps: int,
    ) -> Dict[str, Any]:
        available = set(available_tools)
        stock = ""
        if context and context.get("stock_code"):
            stock = str(context.get("stock_code"))
        goal = (task or "").strip() or "Complete stock analysis and produce a decision dashboard"
        if stock and stock not in goal:
            goal = f"{goal} (stock={stock})"

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

    def _plan_with_llm(
        self,
        task: str,
        *,
        available_tools: Sequence[str],
        context: Optional[Dict[str, Any]],
        settings: PlanningSettings,
    ) -> Tuple[Dict[str, Any], int, str]:
        if self.llm_adapter is None:
            raise RuntimeError("llm strategy requires llm_adapter")

        stock_hint = ""
        if context and context.get("stock_code"):
            stock_hint = f"\nStock code: {context.get('stock_code')}"

        user = (
            f"Task:\n{task}{stock_hint}\n\n"
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
            max_tokens=settings.max_tokens,
            timeout=settings.timeout_seconds,
        )
        content = getattr(response, "content", None) or ""
        if getattr(response, "provider", "") == "error":
            raise RuntimeError(content or "planner LLM configuration error")

        usage = getattr(response, "usage", None) or {}
        tokens = 0
        if isinstance(usage, dict):
            try:
                tokens = int(usage.get("total_tokens") or 0)
            except (TypeError, ValueError):
                tokens = 0
        if tokens > settings.max_tokens * 4:
            # Soft guard: absurd usage figures are ignored; hard stop is max_tokens request bound.
            tokens = settings.max_tokens

        model = str(getattr(response, "model", "") or "")
        payload = _parse_json_object(content)
        payload.setdefault("max_steps", settings.max_plan_steps)
        return payload, tokens, model


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
    """Run the planning pre-step and return (task, context, planning_meta).

    When planning is disabled or degrades, ``task`` and ``context`` are returned
    unchanged (same object identity for context when disabled) so the default
    path stays byte-stable aside from the metadata dict always returned for traces.
    """
    resolved_settings = settings or load_planning_settings()
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


def _parse_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty planner response")
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
