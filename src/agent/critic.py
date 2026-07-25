# -*- coding: utf-8 -*-
"""Bounded, read-only evidence Critic for the Native Multi pipeline."""

from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any, Dict, List, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import AgentContext, StageResult, StageStatus
from src.agent.public_contract import sanitize_agent_diagnostic
from src.agent.skills.defaults import build_skill_agent_name
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

CRITIC_STAGE_NAME = "critic"
CRITIC_MAX_STEPS = 1
CRITIC_RETRY_BUDGET = 1
INTELLIGENCE_RETRY_TARGET = "intelligence"
SKILL_RETRY_TARGET_PREFIX = "skill:"
_SKILL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_JSON_FENCE_PATTERN = re.compile(
    r"\A```(?:json)?\s*(?P<body>.*?)\s*```\Z",
    re.DOTALL | re.IGNORECASE,
)
_MAX_TRACE_ITEMS = 5
_MAX_TRACE_TEXT_LENGTH = 300


class _CriticOutput(BaseModel):
    """Strict model-owned output; runtime availability is checked separately."""

    model_config = ConfigDict(extra="forbid", strict=True)

    verdict: Literal["pass", "retry", "fail_soft"]
    retry_targets: List[str]
    reasons: List[str]
    missing_evidence: List[str]
    confidence_delta: Optional[float] = Field(default=None, ge=-1.0, le=1.0)


def is_critic_enabled(config: Any, ctx: AgentContext) -> bool:
    """Enable the Critic only for explicit, non-Chat Native Multi runs."""
    return (
        getattr(config, "agent_critic_enabled", False) is True
        and ctx.meta.get("response_mode") != "chat"
    )


def is_critic_stage(agent_name: Any) -> bool:
    """Return whether an agent name identifies the bounded Critic stage."""
    return str(agent_name or "").strip().lower() == CRITIC_STAGE_NAME


def _fail_soft_trace(
    reason: str,
    *,
    validation_status: str,
    requested_verdict: Optional[str] = None,
    requested_targets: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Build the fixed, bounded trace used for every fail-soft outcome."""
    return {
        "verdict": "fail_soft",
        "requested_verdict": requested_verdict,
        "reasons": [sanitize_agent_diagnostic(reason)],
        "missing_evidence": [],
        "retry_targets_requested": list(requested_targets or []),
        "retry_targets_executed": [],
        "retry_budget_total": CRITIC_RETRY_BUDGET,
        "retry_budget_consumed": 0,
        "retry_budget_remaining": CRITIC_RETRY_BUDGET,
        "retry_status": "not_started",
        "validation_status": validation_status,
        "confidence_delta": None,
    }


def _validate_text_items(values: List[str], field_name: str) -> None:
    """Reject trace text that exceeds the item or per-item bounds."""
    if len(values) > _MAX_TRACE_ITEMS:
        raise ValueError(f"{field_name} exceeds {_MAX_TRACE_ITEMS} items")
    for value in values:
        if not value.strip():
            raise ValueError(f"{field_name} contains an empty item")
        if len(value) > _MAX_TRACE_TEXT_LENGTH:
            raise ValueError(
                f"{field_name} item exceeds {_MAX_TRACE_TEXT_LENGTH} characters"
            )


def _validate_retry_target(target: str) -> None:
    """Reject targets outside the fixed whitelist and catalog ID grammar."""
    if target == INTELLIGENCE_RETRY_TARGET:
        return
    if not target.startswith(SKILL_RETRY_TARGET_PREFIX):
        raise ValueError("retry target is outside the fixed whitelist")
    skill_id = target[len(SKILL_RETRY_TARGET_PREFIX):]
    if not _SKILL_ID_PATTERN.fullmatch(skill_id):
        raise ValueError("skill retry target has an invalid catalog id")


def _parse_strict_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    """Accept only one direct or fenced top-level JSON object."""
    if not isinstance(raw_text, str):
        return None
    candidate = raw_text.strip()
    if not candidate:
        return None
    fenced = _JSON_FENCE_PATTERN.fullmatch(candidate)
    if fenced is not None:
        candidate = fenced.group("body").strip()
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _append_runtime_reason(trace: Dict[str, Any], reason: str) -> List[str]:
    """Reserve the final bounded reason slot for an authoritative runtime fact."""
    safe_reason = sanitize_agent_diagnostic(reason)
    prior_reasons = []
    for item in trace.get("reasons") or []:
        if not isinstance(item, str):
            continue
        safe_item = sanitize_agent_diagnostic(item)
        if safe_item != safe_reason:
            prior_reasons.append(safe_item)
    return [*prior_reasons[:_MAX_TRACE_ITEMS - 1], safe_reason]


def parse_critic_output(raw_text: str) -> Dict[str, Any]:
    """Parse one Critic response and fail closed without retaining raw output."""
    parsed = _parse_strict_json_object(raw_text)
    if parsed is None:
        return _fail_soft_trace(
            "Critic output was not a JSON object.",
            validation_status="invalid",
        )

    try:
        output = _CriticOutput.model_validate(parsed)
        _validate_text_items(output.reasons, "reasons")
        _validate_text_items(output.missing_evidence, "missing_evidence")
        if len(output.retry_targets) > CRITIC_RETRY_BUDGET:
            raise ValueError("retry target count exceeds the run budget")
        for target in output.retry_targets:
            _validate_retry_target(target)
        if output.verdict == "retry" and len(output.retry_targets) != 1:
            raise ValueError("retry verdict requires exactly one target")
        if output.verdict == "retry" and not output.reasons:
            raise ValueError("retry verdict requires an explicit reason")
        if (
            output.verdict == "fail_soft"
            and not output.reasons
            and not output.missing_evidence
        ):
            raise ValueError("fail_soft verdict requires an explicit limitation")
        if output.verdict != "retry" and output.retry_targets:
            raise ValueError("non-retry verdict cannot request a target")
    except (ValidationError, TypeError, ValueError) as exc:
        log_safe_exception(
            logger,
            "Critic output validation failed",
            exc,
            error_code="agent_critic_output_invalid",
            level=logging.INFO,
        )
        return _fail_soft_trace(
            "Critic output did not satisfy the bounded verdict contract.",
            validation_status="invalid",
        )

    return {
        "verdict": output.verdict,
        "requested_verdict": output.verdict,
        "reasons": [sanitize_agent_diagnostic(item) for item in output.reasons],
        "missing_evidence": [
            sanitize_agent_diagnostic(item) for item in output.missing_evidence
        ],
        "retry_targets_requested": list(output.retry_targets),
        "retry_targets_executed": [],
        "retry_budget_total": CRITIC_RETRY_BUDGET,
        "retry_budget_consumed": 0,
        "retry_budget_remaining": CRITIC_RETRY_BUDGET,
        "retry_status": (
            "requested" if output.verdict == "retry" else "not_requested"
        ),
        "validation_status": "valid",
        "confidence_delta": output.confidence_delta,
    }


def get_critic_trace(ctx: AgentContext) -> Optional[Dict[str, Any]]:
    """Return the current Critic trace when it has the expected mapping shape."""
    trace = ctx.meta.get("critic_trace")
    return trace if isinstance(trace, dict) else None


def record_critic_stage_failure(ctx: AgentContext) -> Dict[str, Any]:
    """Record a fail-soft trace when the Critic stage itself does not complete."""
    trace = _fail_soft_trace(
        "Critic stage did not complete; Decision must preserve this limitation.",
        validation_status="stage_failed",
    )
    ctx.meta["critic_trace"] = trace
    return trace


def record_critic_budget_skip(ctx: AgentContext) -> Dict[str, Any]:
    """Record that optional Critic work yielded to the Decision reserve."""
    trace = _fail_soft_trace(
        "Critic was skipped to preserve the minimum Decision stage budget.",
        validation_status="budget_skipped",
    )
    ctx.meta["critic_trace"] = trace
    return trace


def mark_retry_unavailable(
    ctx: AgentContext,
    target: str,
    *,
    reason: str,
) -> Dict[str, Any]:
    """Record that a requested retry cannot run without consuming its budget."""
    trace = dict(get_critic_trace(ctx) or _fail_soft_trace(
        reason,
        validation_status="runtime_invalid",
        requested_verdict="retry",
        requested_targets=[target],
    ))
    trace["verdict"] = "fail_soft"
    trace["retry_status"] = "unavailable"
    consumed = min(
        CRITIC_RETRY_BUDGET,
        max(0, int(trace.get("retry_budget_consumed") or 0)),
    )
    trace["retry_budget_consumed"] = consumed
    trace["retry_budget_remaining"] = CRITIC_RETRY_BUDGET - consumed
    trace["reasons"] = _append_runtime_reason(trace, reason)
    ctx.meta["critic_trace"] = trace
    return trace


def start_retry(ctx: AgentContext, target: str) -> Optional[Dict[str, Any]]:
    """Consume the one-shot retry budget, or return None if it is unavailable."""
    trace = get_critic_trace(ctx)
    if trace is None:
        return None
    executed = list(trace.get("retry_targets_executed") or [])
    remaining = int(trace.get("retry_budget_remaining") or 0)
    if remaining < 1 or executed or target in executed:
        return None

    updated = dict(trace)
    updated["retry_targets_executed"] = [target]
    updated["retry_budget_consumed"] = 1
    updated["retry_budget_remaining"] = 0
    updated["retry_status"] = "running"
    ctx.meta["critic_trace"] = updated
    return updated


def finish_retry(
    ctx: AgentContext,
    *,
    completed: bool,
) -> Dict[str, Any]:
    """Record whether the one-shot retry produced an accepted completed stage."""
    trace = dict(get_critic_trace(ctx) or {})
    if completed:
        trace["retry_status"] = "completed"
    else:
        trace["verdict"] = "fail_soft"
        trace["retry_status"] = "failed"
        reason = sanitize_agent_diagnostic(
            "Whitelisted retry did not complete; Decision must preserve the limitation."
        )
        trace["reasons"] = _append_runtime_reason(trace, reason)
    ctx.meta["critic_trace"] = trace
    return trace


def resolve_retry_source_agent(
    target: str,
    *,
    agents: Sequence[Any],
    prior_results: Sequence[StageResult],
    skill_manager: Any,
) -> Optional[Any]:
    """Resolve only an already-entered canonical whitelist stage."""
    if target == INTELLIGENCE_RETRY_TARGET:
        agent_name = "intel"
    elif target.startswith(SKILL_RETRY_TARGET_PREFIX):
        skill_id = target[len(SKILL_RETRY_TARGET_PREFIX):]
        if skill_manager is None:
            return None
        try:
            if skill_manager.get(skill_id) is None:
                return None
        except Exception as exc:  # broad-exception: fallback_recorded - Catalog lookup failure makes the optional retry unavailable.
            log_safe_exception(
                logger,
                "Critic retry catalog lookup failed",
                exc,
                error_code="agent_critic_retry_catalog_failed",
                level=logging.WARNING,
                context={"skill_id": skill_id},
            )
            return None
        agent_name = build_skill_agent_name(skill_id)
    else:
        return None

    entered_names = {str(result.stage_name or "") for result in prior_results}
    if agent_name not in entered_names:
        return None
    return next(
        (
            agent
            for agent in reversed(agents)
            if str(getattr(agent, "agent_name", "") or "") == agent_name
        ),
        None,
    )


def build_retry_seed(ctx: AgentContext, target: str) -> AgentContext:
    """Copy context and remove only the target evidence before its retry."""
    retry_ctx = copy.deepcopy(ctx)
    if target == INTELLIGENCE_RETRY_TARGET:
        retry_ctx.opinions = [
            opinion for opinion in retry_ctx.opinions if opinion.agent_name != "intel"
        ]
        retry_ctx.data.pop("intel_opinion", None)
        retry_ctx.risk_flags = [
            flag for flag in retry_ctx.risk_flags if flag.get("category") != "intel"
        ]
    else:
        skill_id = target[len(SKILL_RETRY_TARGET_PREFIX):]
        agent_name = build_skill_agent_name(skill_id)
        retry_ctx.opinions = [
            opinion for opinion in retry_ctx.opinions if opinion.agent_name != agent_name
        ]
        retry_ctx.data.pop("skill_consensus", None)
        retry_ctx.meta.pop("strategy_synthesis", None)
        retry_ctx.meta.pop("invalid_opinions", None)
    return retry_ctx


def retry_produced_evidence(
    ctx: AgentContext,
    target: str,
    *,
    strategy_engine: Any,
) -> bool:
    """Accept retry evidence only at the existing canonical evidence boundary."""
    if target == INTELLIGENCE_RETRY_TARGET:
        return any(opinion.agent_name == "intel" for opinion in ctx.opinions)
    skill_id = target[len(SKILL_RETRY_TARGET_PREFIX):]
    agent_name = build_skill_agent_name(skill_id)
    partition = strategy_engine.partition_only(ctx.opinions)
    return any(
        opinion.agent_name == agent_name
        for opinion in partition.valid_skill_opinions
    )


def trace_event_fields(trace: Dict[str, Any]) -> Dict[str, Any]:
    """Return the bounded fields allowed on stage/SSE trace surfaces."""
    return {
        "verdict": trace.get("verdict"),
        "requested_verdict": trace.get("requested_verdict"),
        "reasons": list(trace.get("reasons") or []),
        "missing_evidence": list(trace.get("missing_evidence") or []),
        "retry_targets_requested": list(trace.get("retry_targets_requested") or []),
        "retry_targets_executed": list(trace.get("retry_targets_executed") or []),
        "retry_budget_consumed": trace.get("retry_budget_consumed", 0),
        "retry_budget_remaining": trace.get("retry_budget_remaining", 0),
        "retry_status": trace.get("retry_status"),
        "validation_status": trace.get("validation_status"),
        "confidence_delta": trace.get("confidence_delta"),
    }


class BoundedCriticAgent(BaseAgent):
    """One-call, tool-free verifier over already-collected Multi evidence."""

    agent_name = CRITIC_STAGE_NAME
    max_steps = CRITIC_MAX_STEPS
    tool_names: List[str] = []

    def system_prompt(self, ctx: AgentContext) -> str:
        """Return the bounded Critic authority and structured-output contract."""
        return """\
You are a read-only evidence Critic inside a bounded stock-analysis pipeline.
Review only the supplied context and completed specialist opinions. You cannot
call tools, make the final investment decision, or author strategy_synthesis.
StrategyEngine and DecisionAgent retain those authorities.

Return only one JSON object with exactly these fields:
{
  "verdict": "pass|retry|fail_soft",
  "retry_targets": ["intelligence|skill:<catalog-id>"],
  "reasons": ["bounded reason"],
  "missing_evidence": ["bounded missing evidence"],
  "confidence_delta": 0.0
}

Use an empty retry_targets list for pass or fail_soft. Under the current global
budget, retry must request exactly one target and include at least one reason.
Request intelligence only when a second intelligence pass could close material
missing evidence. Request a skill target only when that exact catalog-backed
skill opinion is present. Choose fail_soft when evidence remains materially
insufficient but no permitted retry can close the gap, and include at least one
reason or missing_evidence item as the explicit limitation. Never invent
another target or weaken higher-priority Soul evidence, risk, tool, authority,
or refusal rules.
"""

    def build_user_message(self, ctx: AgentContext) -> str:
        """Project the completed pre-Decision evidence into the Critic prompt."""
        opinions = [
            {
                "agent_name": opinion.agent_name,
                "signal": opinion.signal,
                "confidence": opinion.confidence,
                "reasoning": opinion.reasoning,
                "key_levels": opinion.key_levels,
                "raw_data": opinion.raw_data,
            }
            for opinion in ctx.opinions
        ]
        payload = {
            "stock_code": ctx.stock_code,
            "stock_name": ctx.stock_name,
            "opinions": opinions,
            "risk_flags": ctx.risk_flags,
            "degraded_stages": ctx.meta.get("degraded_stages", []),
            "requested_skills": (
                ctx.meta.get("skills_requested")
                or ctx.meta.get("strategies_requested")
                or []
            ),
        }
        return (
            "Review this completed pre-Decision evidence snapshot:\n"
            + json.dumps(payload, ensure_ascii=False, default=str)
        )

    def post_process(self, ctx: AgentContext, raw_text: str):
        """Validate the model output and store only its bounded trace."""
        trace = parse_critic_output(raw_text)
        ctx.meta["critic_trace"] = trace
        return None


__all__ = [
    "BoundedCriticAgent",
    "CRITIC_MAX_STEPS",
    "CRITIC_RETRY_BUDGET",
    "CRITIC_STAGE_NAME",
    "INTELLIGENCE_RETRY_TARGET",
    "SKILL_RETRY_TARGET_PREFIX",
    "build_retry_seed",
    "finish_retry",
    "get_critic_trace",
    "is_critic_enabled",
    "is_critic_stage",
    "mark_retry_unavailable",
    "parse_critic_output",
    "record_critic_budget_skip",
    "record_critic_stage_failure",
    "resolve_retry_source_agent",
    "retry_produced_evidence",
    "start_retry",
    "trace_event_fields",
]
