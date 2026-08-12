# -*- coding: utf-8 -*-
"""Bounded, read-only evidence Critic for the Native Multi pipeline."""

from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

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
CRITIC_MAX_ITERS_DEFAULT = 1
CRITIC_MAX_ITERS_HARD_CAP = 2
INTELLIGENCE_RETRY_TARGET = "intelligence"
SKILL_RETRY_TARGET_PREFIX = "skill:"
_SKILL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_JSON_FENCE_PATTERN = re.compile(
    r"\A```(?:json)?\s*(?P<body>.*?)\s*```\Z",
    re.DOTALL | re.IGNORECASE,
)
_MAX_TRACE_ITEMS = 5
_MAX_TRACE_TEXT_LENGTH = 300
_MAX_REVISION_ROUNDS = CRITIC_MAX_ITERS_HARD_CAP
_MAX_DIFF_KEYS = 8
_CONVERGENCE_PASS = "pass"
_CONVERGENCE_CONVERGED = "converged"
_CONVERGENCE_NOT_CONVERGED = "not_converged"
_CONVERGENCE_NOT_REQUIRED = "not_required"
_CONVERGENCE_UNAVAILABLE = "unavailable"
_CONVERGENCE_BUDGET_SKIPPED = "budget_skipped"
_CONVERGENCE_STAGE_FAILED = "stage_failed"


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


def resolve_critic_max_iters(config: Any = None) -> int:
    """Return the hard-capped revision-iteration budget for this run."""
    raw = getattr(config, "agent_critic_max_iters", CRITIC_MAX_ITERS_DEFAULT)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = CRITIC_MAX_ITERS_DEFAULT
    if value < 1:
        return CRITIC_MAX_ITERS_DEFAULT
    return min(value, CRITIC_MAX_ITERS_HARD_CAP)


def _empty_revision_fields(max_iters: int = CRITIC_MAX_ITERS_DEFAULT) -> Dict[str, Any]:
    """Shared revision/convergence fields for every critic_trace."""
    bounded = max(1, min(int(max_iters or CRITIC_MAX_ITERS_DEFAULT), CRITIC_MAX_ITERS_HARD_CAP))
    return {
        "iteration_max": bounded,
        "iteration_consumed": 0,
        "revision_rounds": [],
        "convergence_status": _CONVERGENCE_NOT_REQUIRED,
    }


def _fail_soft_trace(
    reason: str,
    *,
    validation_status: str,
    requested_verdict: Optional[str] = None,
    requested_targets: Optional[Sequence[str]] = None,
    max_iters: int = CRITIC_MAX_ITERS_DEFAULT,
) -> Dict[str, Any]:
    """Build the fixed, bounded trace used for every fail-soft outcome."""
    budget = max(1, min(int(max_iters or CRITIC_MAX_ITERS_DEFAULT), CRITIC_MAX_ITERS_HARD_CAP))
    if validation_status == "budget_skipped":
        convergence = _CONVERGENCE_BUDGET_SKIPPED
    elif validation_status == "stage_failed":
        convergence = _CONVERGENCE_STAGE_FAILED
    elif validation_status in {"invalid", "runtime_invalid"}:
        convergence = _CONVERGENCE_NOT_CONVERGED
    else:
        convergence = _CONVERGENCE_NOT_REQUIRED
    return {
        "verdict": "fail_soft",
        "requested_verdict": requested_verdict,
        "reasons": [sanitize_agent_diagnostic(reason)],
        "missing_evidence": [],
        "retry_targets_requested": list(requested_targets or []),
        "retry_targets_executed": [],
        "retry_budget_total": budget,
        "retry_budget_consumed": 0,
        "retry_budget_remaining": budget,
        "retry_status": "not_started",
        "validation_status": validation_status,
        "confidence_delta": None,
        **_empty_revision_fields(budget),
        "convergence_status": convergence,
    }


def apply_iteration_budget(
    trace: Dict[str, Any],
    *,
    max_iters: int,
) -> Dict[str, Any]:
    """Stamp the configured iteration budget onto a validated critic_trace."""
    budget = max(1, min(int(max_iters or CRITIC_MAX_ITERS_DEFAULT), CRITIC_MAX_ITERS_HARD_CAP))
    updated = dict(trace)
    consumed = min(budget, max(0, int(updated.get("retry_budget_consumed") or 0)))
    updated["retry_budget_total"] = budget
    updated["retry_budget_consumed"] = consumed
    updated["retry_budget_remaining"] = max(0, budget - consumed)
    updated["iteration_max"] = budget
    if "iteration_consumed" not in updated:
        updated["iteration_consumed"] = 0
    if "revision_rounds" not in updated or not isinstance(updated.get("revision_rounds"), list):
        updated["revision_rounds"] = []
    if not updated.get("convergence_status"):
        if updated.get("verdict") == "pass":
            updated["convergence_status"] = _CONVERGENCE_PASS
        elif updated.get("verdict") == "retry":
            updated["convergence_status"] = _CONVERGENCE_NOT_REQUIRED
        else:
            updated["convergence_status"] = _CONVERGENCE_NOT_CONVERGED
    return updated


def mode_budget_allows_optional_work(ctx: AgentContext) -> Tuple[bool, str]:
    """Soft-align optional Critic revision with per-mode hard budgets (#1213)."""
    account = ctx.meta.get("mode_budget_account")
    if account is None:
        return True, ""
    check = getattr(account, "check", None)
    if not callable(check):
        return True, ""
    try:
        breach = check()
    except Exception as exc:  # broad-exception: fallback_recorded - Optional budget probe must not stop Critic.
        log_safe_exception(
            logger,
            "Critic mode-budget probe failed",
            exc,
            error_code="agent_critic_mode_budget_probe_failed",
            level=logging.INFO,
        )
        return True, ""
    if breach is None:
        return True, ""
    reason = getattr(breach, "reason", None) or getattr(breach, "message", None) or "mode_budget"
    return False, (
        "Critic revision was skipped because the per-mode budget was "
        f"exhausted ({reason})."
    )


def snapshot_target_evidence(ctx: AgentContext, target: str) -> Dict[str, Any]:
    """Capture a bounded, low-sensitivity evidence snapshot for revision diffs."""
    if target == INTELLIGENCE_RETRY_TARGET:
        opinions = [opinion for opinion in ctx.opinions if opinion.agent_name == "intel"]
        agent_name = "intel"
    elif target.startswith(SKILL_RETRY_TARGET_PREFIX):
        skill_id = target[len(SKILL_RETRY_TARGET_PREFIX):]
        agent_name = build_skill_agent_name(skill_id)
        opinions = [opinion for opinion in ctx.opinions if opinion.agent_name == agent_name]
    else:
        return {
            "target": sanitize_agent_diagnostic(str(target or "")),
            "present": False,
            "signals": [],
            "confidence": [],
            "reasoning_fingerprints": [],
        }

    signals: List[str] = []
    confidences: List[float] = []
    fingerprints: List[str] = []
    for opinion in opinions[:_MAX_TRACE_ITEMS]:
        signals.append(str(opinion.signal or ""))
        try:
            confidences.append(round(float(opinion.confidence), 4))
        except (TypeError, ValueError):
            confidences.append(0.0)
        reasoning = sanitize_agent_diagnostic(str(opinion.reasoning or ""))
        fingerprints.append(f"{len(reasoning)}:{reasoning[:48]}")
    return {
        "target": target,
        "agent_name": agent_name,
        "present": bool(opinions),
        "signals": signals,
        "confidence": confidences,
        "reasoning_fingerprints": fingerprints,
    }


def build_revision_diff(
    before: Optional[Dict[str, Any]],
    after: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a bounded before/after revision diff for the critic_trace."""
    before_map = before if isinstance(before, dict) else {}
    after_map = after if isinstance(after, dict) else {}
    before_signals = list(before_map.get("signals") or [])
    after_signals = list(after_map.get("signals") or [])
    before_fps = list(before_map.get("reasoning_fingerprints") or [])
    after_fps = list(after_map.get("reasoning_fingerprints") or [])
    changed_keys: List[str] = []
    if bool(before_map.get("present")) != bool(after_map.get("present")):
        changed_keys.append("present")
    if before_signals != after_signals:
        changed_keys.append("signals")
    if list(before_map.get("confidence") or []) != list(after_map.get("confidence") or []):
        changed_keys.append("confidence")
    if before_fps != after_fps:
        changed_keys.append("reasoning")
    return {
        "target": after_map.get("target") or before_map.get("target"),
        "before_present": bool(before_map.get("present")),
        "after_present": bool(after_map.get("present")),
        "before_signals": before_signals[:_MAX_TRACE_ITEMS],
        "after_signals": after_signals[:_MAX_TRACE_ITEMS],
        "changed": changed_keys[:_MAX_DIFF_KEYS],
        "evidence_changed": bool(changed_keys),
    }


def append_revision_round(
    ctx: AgentContext,
    *,
    target: str,
    before: Optional[Dict[str, Any]],
    after: Optional[Dict[str, Any]],
    status: str,
) -> Dict[str, Any]:
    """Append one bounded revision-round record and update iteration counters."""
    trace = dict(get_critic_trace(ctx) or {})
    rounds = list(trace.get("revision_rounds") or [])
    if len(rounds) >= _MAX_REVISION_ROUNDS:
        ctx.meta["critic_trace"] = trace
        return trace
    diff = build_revision_diff(before, after)
    round_index = len(rounds) + 1
    rounds.append({
        "round": round_index,
        "target": target,
        "status": status,
        "revision_diff": diff,
    })
    trace["revision_rounds"] = rounds
    trace["iteration_consumed"] = round_index
    ctx.meta["critic_trace"] = trace
    return trace


def finalize_convergence(
    ctx: AgentContext,
    *,
    recheck_verdict: Optional[str] = None,
) -> Dict[str, Any]:
    """Set convergence_status after revision rounds complete or are blocked.

    Terminal product semantics:
    - pass / converged: original gap reasons must not reappear as product limitations
    - not_converged / fail_soft / unavailable / budget paths: keep Critic opinions
    """
    trace = dict(get_critic_trace(ctx) or {})
    verdict = str(trace.get("verdict") or "")
    retry_status = str(trace.get("retry_status") or "")
    validation = str(trace.get("validation_status") or "")
    rounds = list(trace.get("revision_rounds") or [])
    evidence_changed = any(
        isinstance(item, dict)
        and (item.get("revision_diff") or {}).get("evidence_changed")
        for item in rounds
    )

    if validation == "budget_skipped":
        status = _CONVERGENCE_BUDGET_SKIPPED
    elif validation == "stage_failed":
        status = _CONVERGENCE_STAGE_FAILED
    elif recheck_verdict == "pass":
        status = _CONVERGENCE_CONVERGED
        trace["verdict"] = "pass"
        trace["retry_status"] = "completed"
    elif recheck_verdict in {"fail_soft", "retry"}:
        status = _CONVERGENCE_NOT_CONVERGED
        if recheck_verdict == "fail_soft":
            trace["verdict"] = "fail_soft"
    elif verdict == "fail_soft":
        status = _CONVERGENCE_NOT_CONVERGED
    elif verdict == "pass" and not rounds:
        status = _CONVERGENCE_PASS
    elif verdict == "pass" and rounds and retry_status == "completed":
        status = _CONVERGENCE_CONVERGED if evidence_changed or rounds else _CONVERGENCE_PASS
    elif retry_status == "completed" and recheck_verdict is None:
        status = (
            _CONVERGENCE_CONVERGED if evidence_changed else _CONVERGENCE_NOT_CONVERGED
        )
        if status == _CONVERGENCE_CONVERGED:
            trace["verdict"] = "pass"
    elif retry_status in {"unavailable", "failed"}:
        status = _CONVERGENCE_NOT_CONVERGED
    elif verdict == "retry" and retry_status in {"requested", "running", "not_started"}:
        status = _CONVERGENCE_NOT_REQUIRED
    else:
        status = _CONVERGENCE_NOT_CONVERGED

    trace["convergence_status"] = status
    ctx.meta["critic_trace"] = trace
    return trace


def project_critic_product_limitations(
    trace: Optional[Dict[str, Any]],
) -> List[str]:
    """Project critic opinions into product-facing data_limitations strings.

    Keep original Critic gap reasons only when convergence failed or was skipped.
    On pass/converged paths, only a short revision note (and round summary) is
    emitted so successful revision does not restate stale failure opinions.
    """
    if not isinstance(trace, dict):
        return []
    verdict = str(trace.get("verdict") or "")
    convergence = str(trace.get("convergence_status") or "")
    retry_status = str(trace.get("retry_status") or "")
    rounds = list(trace.get("revision_rounds") or [])

    def _round_summaries() -> List[str]:
        lines: List[str] = []
        for round_item in rounds[:_MAX_REVISION_ROUNDS]:
            if not isinstance(round_item, dict):
                continue
            target = sanitize_agent_diagnostic(str(round_item.get("target") or ""))
            status = sanitize_agent_diagnostic(str(round_item.get("status") or ""))
            diff = (
                round_item.get("revision_diff")
                if isinstance(round_item.get("revision_diff"), dict)
                else {}
            )
            changed = (
                ",".join(str(x) for x in list(diff.get("changed") or [])[:_MAX_DIFF_KEYS])
                or "none"
            )
            lines.append(
                f"Critic revision round {round_item.get('round')}: "
                f"target={target}; status={status}; changed={changed}."
            )
        return lines

    if convergence == _CONVERGENCE_PASS or (
        verdict == "pass"
        and not rounds
        and convergence in {"", _CONVERGENCE_PASS, _CONVERGENCE_NOT_REQUIRED}
    ):
        return []

    if convergence == _CONVERGENCE_CONVERGED:
        lines = ["Critic: evidence revision converged after a controlled retry."]
        lines.extend(_round_summaries())
        return lines[: (_MAX_TRACE_ITEMS * 3)]

    residual = (
        convergence in {
            _CONVERGENCE_NOT_CONVERGED,
            _CONVERGENCE_UNAVAILABLE,
            _CONVERGENCE_BUDGET_SKIPPED,
            _CONVERGENCE_STAGE_FAILED,
        }
        or retry_status in {"unavailable", "failed"}
        or verdict == "fail_soft"
    )
    if not residual:
        return []

    lines = [
        f"Critic: verdict={verdict or 'unknown'}; "
        f"convergence={convergence or 'unknown'}; "
        f"retry_status={retry_status or 'none'}."
    ]
    for reason in list(trace.get("reasons") or [])[:_MAX_TRACE_ITEMS]:
        if isinstance(reason, str) and reason.strip():
            lines.append(f"Critic reason: {sanitize_agent_diagnostic(reason)}")
    for item in list(trace.get("missing_evidence") or [])[:_MAX_TRACE_ITEMS]:
        if isinstance(item, str) and item.strip():
            lines.append(f"Critic missing evidence: {sanitize_agent_diagnostic(item)}")
    lines.extend(_round_summaries())
    return lines[: (_MAX_TRACE_ITEMS * 3)]


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


def parse_critic_output(
    raw_text: str,
    *,
    max_iters: int = CRITIC_MAX_ITERS_DEFAULT,
) -> Dict[str, Any]:
    """Parse one Critic response and fail closed without retaining raw output."""
    budget = max(1, min(int(max_iters or CRITIC_MAX_ITERS_DEFAULT), CRITIC_MAX_ITERS_HARD_CAP))
    parsed = _parse_strict_json_object(raw_text)
    if parsed is None:
        return _fail_soft_trace(
            "Critic output was not a JSON object.",
            validation_status="invalid",
            max_iters=budget,
        )

    try:
        output = _CriticOutput.model_validate(parsed)
        _validate_text_items(output.reasons, "reasons")
        _validate_text_items(output.missing_evidence, "missing_evidence")
        if len(output.retry_targets) > budget:
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
            max_iters=budget,
        )

    if output.verdict == "pass":
        convergence = _CONVERGENCE_PASS
    elif output.verdict == "retry":
        convergence = _CONVERGENCE_NOT_REQUIRED
    else:
        convergence = _CONVERGENCE_NOT_CONVERGED

    return {
        "verdict": output.verdict,
        "requested_verdict": output.verdict,
        "reasons": [sanitize_agent_diagnostic(item) for item in output.reasons],
        "missing_evidence": [
            sanitize_agent_diagnostic(item) for item in output.missing_evidence
        ],
        "retry_targets_requested": list(output.retry_targets),
        "retry_targets_executed": [],
        "retry_budget_total": budget,
        "retry_budget_consumed": 0,
        "retry_budget_remaining": budget,
        "retry_status": (
            "requested" if output.verdict == "retry" else "not_requested"
        ),
        "validation_status": "valid",
        "confidence_delta": output.confidence_delta,
        **_empty_revision_fields(budget),
        "convergence_status": convergence,
    }


def get_critic_trace(ctx: AgentContext) -> Optional[Dict[str, Any]]:
    """Return the current Critic trace when it has the expected mapping shape."""
    trace = ctx.meta.get("critic_trace")
    return trace if isinstance(trace, dict) else None


def record_critic_stage_failure(
    ctx: AgentContext,
    *,
    max_iters: int = CRITIC_MAX_ITERS_DEFAULT,
) -> Dict[str, Any]:
    """Record a fail-soft trace when the Critic stage itself does not complete."""
    trace = _fail_soft_trace(
        "Critic stage did not complete; Decision must preserve this limitation.",
        validation_status="stage_failed",
        max_iters=max_iters,
    )
    ctx.meta["critic_trace"] = trace
    return trace


def record_critic_budget_skip(
    ctx: AgentContext,
    *,
    max_iters: int = CRITIC_MAX_ITERS_DEFAULT,
) -> Dict[str, Any]:
    """Record that optional Critic work yielded to the Decision reserve."""
    trace = _fail_soft_trace(
        "Critic was skipped to preserve the minimum Decision stage budget.",
        validation_status="budget_skipped",
        max_iters=max_iters,
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
    existing = get_critic_trace(ctx)
    max_iters = int((existing or {}).get("retry_budget_total") or CRITIC_RETRY_BUDGET)
    trace = dict(existing or _fail_soft_trace(
        reason,
        validation_status="runtime_invalid",
        requested_verdict="retry",
        requested_targets=[target],
        max_iters=max_iters,
    ))
    total = max(1, int(trace.get("retry_budget_total") or max_iters or CRITIC_RETRY_BUDGET))
    trace["verdict"] = "fail_soft"
    trace["retry_status"] = "unavailable"
    consumed = min(total, max(0, int(trace.get("retry_budget_consumed") or 0)))
    trace["retry_budget_total"] = total
    trace["retry_budget_consumed"] = consumed
    trace["retry_budget_remaining"] = max(0, total - consumed)
    trace["reasons"] = _append_runtime_reason(trace, reason)
    trace["convergence_status"] = _CONVERGENCE_NOT_CONVERGED
    ctx.meta["critic_trace"] = trace
    return trace


def start_retry(ctx: AgentContext, target: str) -> Optional[Dict[str, Any]]:
    """Consume one revision-budget unit, or return None if unavailable."""
    trace = get_critic_trace(ctx)
    if trace is None:
        return None
    executed = list(trace.get("retry_targets_executed") or [])
    remaining = int(trace.get("retry_budget_remaining") or 0)
    total = max(1, int(trace.get("retry_budget_total") or CRITIC_RETRY_BUDGET))
    if remaining < 1 or target in executed:
        return None

    updated = dict(trace)
    updated["retry_targets_executed"] = [*executed, target][:_MAX_REVISION_ROUNDS]
    consumed = min(total, int(updated.get("retry_budget_consumed") or 0) + 1)
    updated["retry_budget_consumed"] = consumed
    updated["retry_budget_remaining"] = max(0, total - consumed)
    updated["retry_status"] = "running"
    ctx.meta["critic_trace"] = updated
    return updated


def finish_retry(
    ctx: AgentContext,
    *,
    completed: bool,
) -> Dict[str, Any]:
    """Record whether the current revision produced an accepted completed stage."""
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
        trace["convergence_status"] = _CONVERGENCE_NOT_CONVERGED
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
    revision_rounds = []
    for item in list(trace.get("revision_rounds") or [])[:_MAX_REVISION_ROUNDS]:
        if not isinstance(item, dict):
            continue
        diff = item.get("revision_diff") if isinstance(item.get("revision_diff"), dict) else {}
        revision_rounds.append({
            "round": item.get("round"),
            "target": item.get("target"),
            "status": item.get("status"),
            "evidence_changed": bool(diff.get("evidence_changed")),
            "changed": list(diff.get("changed") or [])[:_MAX_DIFF_KEYS],
        })
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
        "iteration_max": trace.get("iteration_max", CRITIC_MAX_ITERS_DEFAULT),
        "iteration_consumed": trace.get("iteration_consumed", 0),
        "convergence_status": trace.get("convergence_status"),
        "revision_rounds": revision_rounds,
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
            "prior_critic_trace": {
                key: (ctx.meta.get("critic_trace") or {}).get(key)
                for key in (
                    "verdict",
                    "reasons",
                    "missing_evidence",
                    "retry_targets_executed",
                    "convergence_status",
                    "iteration_consumed",
                    "iteration_max",
                )
            }
            if isinstance(ctx.meta.get("critic_trace"), dict)
            else None,
        }
        return (
            "Review this completed pre-Decision evidence snapshot:\n"
            + json.dumps(payload, ensure_ascii=False, default=str)
        )

    def post_process(self, ctx: AgentContext, raw_text: str):
        """Validate the model output and store only its bounded trace."""
        max_iters = resolve_critic_max_iters(
            getattr(self, "config", None) or getattr(self, "_config", None)
        )
        prior = ctx.meta.get("critic_trace")
        if isinstance(prior, dict) and prior.get("iteration_max"):
            try:
                max_iters = max(1, min(int(prior["iteration_max"]), CRITIC_MAX_ITERS_HARD_CAP))
            except (TypeError, ValueError):
                pass
        prior_consumed = 0
        prior_executed: List[str] = []
        prior_rounds: List[Dict[str, Any]] = []
        if isinstance(prior, dict):
            prior_consumed = max(0, int(prior.get("retry_budget_consumed") or 0))
            prior_executed = list(prior.get("retry_targets_executed") or [])
            if isinstance(prior.get("revision_rounds"), list):
                prior_rounds = list(prior.get("revision_rounds") or [])

        trace = parse_critic_output(raw_text, max_iters=max_iters)
        if prior_consumed or prior_executed or prior_rounds:
            total = max(1, int(trace.get("retry_budget_total") or max_iters))
            consumed = min(total, prior_consumed)
            trace["retry_budget_consumed"] = consumed
            trace["retry_budget_remaining"] = max(0, total - consumed)
            if prior_executed:
                merged = list(dict.fromkeys([*prior_executed, *list(trace.get("retry_targets_executed") or [])]))
                trace["retry_targets_executed"] = merged[:_MAX_REVISION_ROUNDS]
            if prior_rounds:
                trace["revision_rounds"] = prior_rounds[:_MAX_REVISION_ROUNDS]
                trace["iteration_consumed"] = len(trace["revision_rounds"])
        ctx.meta["critic_trace"] = trace
        return None


__all__ = [
    "BoundedCriticAgent",
    "CRITIC_MAX_ITERS_DEFAULT",
    "CRITIC_MAX_ITERS_HARD_CAP",
    "CRITIC_MAX_STEPS",
    "CRITIC_RETRY_BUDGET",
    "CRITIC_STAGE_NAME",
    "INTELLIGENCE_RETRY_TARGET",
    "SKILL_RETRY_TARGET_PREFIX",
    "append_revision_round",
    "apply_iteration_budget",
    "build_retry_seed",
    "build_revision_diff",
    "finalize_convergence",
    "finish_retry",
    "get_critic_trace",
    "is_critic_enabled",
    "is_critic_stage",
    "mark_retry_unavailable",
    "mode_budget_allows_optional_work",
    "parse_critic_output",
    "project_critic_product_limitations",
    "record_critic_budget_skip",
    "record_critic_stage_failure",
    "resolve_critic_max_iters",
    "resolve_retry_source_agent",
    "retry_produced_evidence",
    "snapshot_target_evidence",
    "start_retry",
    "trace_event_fields",
]
