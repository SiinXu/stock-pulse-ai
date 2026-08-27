# -*- coding: utf-8 -*-
"""Optional adversarial red-team second-opinion stage (Issue #1135).

Default-off. When enabled on non-Chat Native Multi ``full`` / ``specialist``
runs (or an explicit request override), the pipeline inserts one tool-free
LLM turn *after* DecisionAgent. The stage writes an independent counter-thesis
and challenges. It never feeds text back into DecisionAgent and never replaces
the primary decision object.

Product honesty rules:
- Challenges, missing evidence, and suggested confidence pressure are additive.
- Merge is a pure function. It must not change ``decision_type``,
  ``confidence_level``, or ``operation_advice``.
- ``phase_decision.data_limitations`` uses preserve-existing-then-append:
  unique primary limitations keep their original order and occupy the 12
  product slots first; red-team lines are deduplicated and appended only into
  remaining slots. Overflow stays on ``dashboard.red_team`` and is never used
  to evict or reorder the primary decision object.
- Provider / parse / timeout / budget failures fail soft: record
  ``data_unavailable`` or ``budget_skip``, invent no challenges, and keep the
  analysis successful.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.agent.agents.base_agent import BaseAgent
from src.agent.protocols import (
    AgentContext,
    AgentRunStats,
    StageFailureReason,
    StageResult,
    StageStatus,
)
from src.agent.public_contract import AGENT_EXECUTION_FAILURE_MESSAGE, sanitize_agent_diagnostic
from src.agent.runtime_facts import DegradationBoundary
from src.agent.stream_events import stream_event
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

RED_TEAM_STAGE_NAME = "red_team"
RED_TEAM_SCHEMA_VERSION = "red-team-v1"
RED_TEAM_META_KEY = "red_team"
RED_TEAM_DASHBOARD_KEY = "red_team"

STATUS_COMPLETED = "completed"
STATUS_SKIPPED = "skipped"
STATUS_DEGRADED = "degraded"
STATUS_BUDGET_EXHAUSTED = "budget_exhausted"
STATUS_DATA_UNAVAILABLE = "data_unavailable"
STATUS_FAILED = "failed"

REQUEST_ENABLE_RED_TEAM = "enable_red_team"

_LLM_TURN_LIMIT = 1
_DEFAULT_TEMPERATURE = 0.2
_MAX_TOKENS = 700
_MAX_ARGS = 5
_MAX_ARG_LEN = 280
_MAX_CHALLENGES = 5
_MAX_PRODUCT_LIMITATIONS = 12
LIMITATIONS_MERGE_POLICY = "preserve_existing_then_append"
_ALLOWED_MODES = frozenset({"full", "specialist"})
_DECISION_IDENTITY_KEYS = ("decision_type", "confidence_level", "operation_advice")
_PRESSURE_VALUES = frozenset({"none", "mild", "strong"})
_SEVERITY_VALUES = frozenset({"low", "medium", "high"})
_JSON_FENCE_PATTERN = re.compile(
    r"\A```(?:json)?\s*(?P<body>.*?)\s*```\Z",
    re.DOTALL | re.IGNORECASE,
)


class _ChallengeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    claim: str = Field(min_length=1, max_length=_MAX_ARG_LEN)
    weak_evidence: str = Field(min_length=1, max_length=_MAX_ARG_LEN)
    severity: Literal["low", "medium", "high"]


class _RedTeamOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    counter_thesis: str = Field(min_length=1, max_length=_MAX_ARG_LEN)
    challenges: List[_ChallengeOutput]
    missing_evidence: List[str]
    suggested_confidence_pressure: Literal["none", "mild", "strong"]


def is_red_team_stage(agent_name: Any) -> bool:
    return str(agent_name or "").strip().lower() == RED_TEAM_STAGE_NAME


def resolve_red_team_settings(
    config: Any,
    ctx: Optional[AgentContext] = None,
    *,
    request_context: Optional[Mapping[str, Any]] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    enabled = bool(getattr(config, "agent_red_team_enabled", False)) if config is not None else False
    source = "config"
    request = request_context if isinstance(request_context, Mapping) else {}
    meta = ctx.meta if ctx is not None and isinstance(ctx.meta, dict) else {}

    for candidate, origin in (
        (request.get(REQUEST_ENABLE_RED_TEAM), "request"),
        (meta.get(REQUEST_ENABLE_RED_TEAM), "meta"),
    ):
        parsed = _parse_optional_bool(candidate)
        if parsed is not None:
            enabled = parsed
            source = origin
            break

    resolved_mode = str(
        mode
        or meta.get("orchestrator_mode")
        or getattr(config, "agent_orchestrator_mode", "")
        or ""
    ).strip().lower()
    return {
        "enabled": enabled,
        "source": source,
        "mode": resolved_mode,
        "temperature": _DEFAULT_TEMPERATURE,
        "max_tokens": _MAX_TOKENS,
        "llm_turns_limit": _LLM_TURN_LIMIT,
    }


def is_red_team_enabled(
    config: Any,
    ctx: AgentContext,
    *,
    mode: Optional[str] = None,
) -> bool:
    if ctx.meta.get("response_mode") == "chat":
        return False
    settings = resolve_red_team_settings(config, ctx, mode=mode)
    if not settings["enabled"]:
        return False
    if settings["source"] in {"request", "meta"}:
        return True
    return str(settings.get("mode") or "").strip().lower() in _ALLOWED_MODES


def get_red_team_record(ctx: AgentContext) -> Optional[Dict[str, Any]]:
    record = ctx.meta.get(RED_TEAM_META_KEY)
    if not isinstance(record, Mapping) or not record:
        return None
    if record.get("schema_version") != RED_TEAM_SCHEMA_VERSION:
        return None
    return dict(record)


def public_red_team_payload(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping) or not value:
        return None
    if value.get("schema_version") != RED_TEAM_SCHEMA_VERSION:
        return None
    if value.get("enabled") is not True:
        return None
    budget = value.get("budget") if isinstance(value.get("budget"), Mapping) else {}
    degradation = value.get("degradation") if isinstance(value.get("degradation"), Mapping) else {}
    settings = value.get("settings") if isinstance(value.get("settings"), Mapping) else {}
    payload = {
        "enabled": True,
        "schema_version": RED_TEAM_SCHEMA_VERSION,
        "status": str(value.get("status") or STATUS_FAILED),
        "counter_thesis": sanitize_agent_diagnostic(str(value.get("counter_thesis") or ""))[:_MAX_ARG_LEN],
        "challenges": _public_challenges(value.get("challenges")),
        "missing_evidence": _bounded_str_list(value.get("missing_evidence")),
        "suggested_confidence_pressure": _normalize_pressure(
            value.get("suggested_confidence_pressure")
        ),
        "budget": {
            "llm_turns_used": _safe_nonnegative_int(budget.get("llm_turns_used")),
            "llm_turns_limit": _safe_nonnegative_int(budget.get("llm_turns_limit")) or _LLM_TURN_LIMIT,
            "tokens_used": _safe_nonnegative_int(budget.get("tokens_used")),
            "terminated_reason": budget.get("terminated_reason"),
        },
        "degradation": {
            "present": bool(degradation.get("present")),
            "reasons": _bounded_str_list(degradation.get("reasons")),
        },
        "settings": {
            "source": str(settings.get("source") or "config"),
            "mode": str(settings.get("mode") or ""),
        },
    }
    merge_stats = _public_limitations_merge(value.get("data_limitations_merge"))
    if merge_stats is not None:
        payload["data_limitations_merge"] = merge_stats
    return payload


def empty_red_team_record(*, status: str, settings: Mapping[str, Any], reason: str = "") -> Dict[str, Any]:
    reasons = [sanitize_agent_diagnostic(reason)[:_MAX_ARG_LEN]] if reason else []
    terminated = None
    if status == STATUS_BUDGET_EXHAUSTED:
        terminated = "budget_turns"
    elif status == STATUS_SKIPPED and "budget" in reason.lower():
        terminated = "budget_skip"
    return {
        "enabled": True,
        "schema_version": RED_TEAM_SCHEMA_VERSION,
        "status": status,
        "counter_thesis": "",
        "challenges": [],
        "missing_evidence": [],
        "suggested_confidence_pressure": "none",
        "budget": {
            "llm_turns_used": 0,
            "llm_turns_limit": _LLM_TURN_LIMIT,
            "tokens_used": 0,
            "terminated_reason": terminated,
        },
        "degradation": {
            "present": status in {
                STATUS_DEGRADED,
                STATUS_BUDGET_EXHAUSTED,
                STATUS_DATA_UNAVAILABLE,
                STATUS_FAILED,
                STATUS_SKIPPED,
            },
            "reasons": reasons,
        },
        "settings": {
            "source": str(settings.get("source") or "config"),
            "mode": str(settings.get("mode") or ""),
        },
    }


def record_red_team_budget_skip(
    ctx: AgentContext,
    *,
    settings: Optional[Mapping[str, Any]] = None,
    reason: str = "insufficient wall-clock budget",
) -> Dict[str, Any]:
    resolved = dict(settings) if isinstance(settings, Mapping) else None
    if resolved is None:
        cached = ctx.meta.get("_red_team_settings")
        resolved = dict(cached) if isinstance(cached, Mapping) else {
            "enabled": True,
            "source": "config",
            "mode": str(ctx.meta.get("orchestrator_mode") or ""),
        }
    record = empty_red_team_record(status=STATUS_SKIPPED, settings=resolved, reason=reason)
    ctx.meta[RED_TEAM_META_KEY] = record
    return record


def maybe_insert_after_decision(
    pipeline: Any,
    agents: list,
    index: int,
    ctx: AgentContext,
) -> None:
    """Insert the red-team stage after Decision. Decision still runs first."""
    agent = agents[index]
    if (
        agent.agent_name != "decision"
        or ctx.meta.get("_red_team_inserted")
        or not is_red_team_enabled(pipeline.config, ctx, mode=getattr(pipeline, "mode", None))
    ):
        return
    ctx.meta["_red_team_inserted"] = True
    settings = resolve_red_team_settings(
        pipeline.config,
        ctx,
        mode=getattr(pipeline, "mode", None),
    )
    ctx.meta["_red_team_settings"] = settings
    red_team_agent = pipeline._prepare_agent(
        BoundedRedTeamAgent(
            tool_registry=pipeline._tool_registry_for_context(ctx),
            llm_adapter=pipeline.llm_adapter,
            skill_instructions=pipeline.skill_instructions,
            technical_skill_policy=pipeline.technical_skill_policy,
            red_team_config=pipeline.config,
        )
    )
    agents.insert(index + 1, red_team_agent)


def maybe_skip_for_budget(
    pipeline: Any,
    agent: Any,
    ctx: AgentContext,
    stats: AgentRunStats,
    timeout_s: Optional[float],
    remaining_budget: Optional[float],
    min_stage_budget_s: float,
    progress_callback: Optional[Callable],
) -> bool:
    """Fail-soft skip for the optional post-Decision stage. True means ``continue``."""
    if not is_red_team_stage(getattr(agent, "agent_name", "")):
        return False
    wall_clock_short = bool(
        timeout_s
        and remaining_budget is not None
        and remaining_budget < max(0.0, float(min_stage_budget_s))
    )
    mode_reason = _mode_budget_block_reason(ctx, required_turns=1)
    if not wall_clock_short and not mode_reason:
        return False
    reason = (
        "insufficient wall-clock budget for red-team stage"
        if wall_clock_short
        else "insufficient mode-budget turns for red-team stage"
    )
    apply_pipeline_budget_skip(
        pipeline,
        ctx,
        stats,
        settings=ctx.meta.get("_red_team_settings"),
        progress_callback=progress_callback,
        reason=reason,
        terminated_reason="budget_skip",
    )
    return True


def apply_pipeline_budget_skip(
    pipeline: Any,
    ctx: AgentContext,
    stats: AgentRunStats,
    *,
    settings: Optional[Mapping[str, Any]] = None,
    progress_callback: Optional[Callable] = None,
    reason: str = "insufficient wall-clock budget for red-team stage",
    terminated_reason: str = "budget_skip",
) -> None:
    record = record_red_team_budget_skip(ctx, settings=settings, reason=reason)
    record["budget"]["terminated_reason"] = terminated_reason
    public = public_red_team_payload(record) or {}
    result = StageResult(
        stage_name=RED_TEAM_STAGE_NAME,
        status=StageStatus.FAILED,
        failure_reason=(
            StageFailureReason.BUDGET_SKIP
            if terminated_reason == "budget_skip"
            else StageFailureReason.BUDGET_TURNS
        ),
        meta={"red_team": public},
    )
    stats.record_stage(result)
    pipeline._record_degraded_stage(
        ctx,
        RED_TEAM_STAGE_NAME,
        result,
        boundary=DegradationBoundary.BEFORE_STAGE,
    )
    if progress_callback:
        progress_callback(stream_event(
            "red_team_budget_skipped",
            stage=RED_TEAM_STAGE_NAME,
            status=public.get("status"),
            terminated_reason=terminated_reason,
        ))


def commit_pipeline_stage_result(
    ctx: AgentContext,
    result: StageResult,
    stage_name: str,
) -> None:
    if not is_red_team_stage(stage_name):
        return
    record = get_red_team_record(ctx)
    staged = result.meta.get("red_team")
    if record is None and isinstance(staged, dict):
        record = dict(staged)
        ctx.meta[RED_TEAM_META_KEY] = record
    if record is None:
        record = empty_red_team_record(
            status=(
                STATUS_DATA_UNAVAILABLE
                if result.status == StageStatus.FAILED
                else STATUS_DEGRADED
            ),
            settings=ctx.meta.get("_red_team_settings") or {
                "source": "config",
                "mode": str(ctx.meta.get("orchestrator_mode") or ""),
            },
            reason=result.error or "red_team_record_missing",
        )
        ctx.meta[RED_TEAM_META_KEY] = record
    result.meta["red_team"] = public_red_team_payload(record)


def apply_red_team_to_dashboard(dashboard: Dict[str, Any], record: Optional[Mapping[str, Any]]) -> None:
    if not isinstance(dashboard, dict):
        return
    dashboard.pop(RED_TEAM_DASHBOARD_KEY, None)
    public = public_red_team_payload(record)
    if public:
        dashboard[RED_TEAM_DASHBOARD_KEY] = public


def snapshot_decision_identity(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the primary decision fields that red-team merge must not change."""
    return {key: payload.get(key) for key in _DECISION_IDENTITY_KEYS}


def restore_decision_identity(payload: Dict[str, Any], identity: Mapping[str, Any]) -> None:
    for key in _DECISION_IDENTITY_KEYS:
        if key in identity:
            payload[key] = identity[key]


def merge_data_limitations_preserving_existing(
    existing: Any,
    additions: Sequence[str],
    *,
    cap: int = _MAX_PRODUCT_LIMITATIONS,
) -> tuple[List[str], Dict[str, Any]]:
    """Preserve existing product limitations, then append unique red-team lines.

    Unique existing items keep their original order and occupy slots first.
    Additions are stripped and deduplicated against that preserved list and
    against themselves. Only remaining slots up to ``cap`` are filled.
    Overflow is omitted from the product list and returned in merge stats;
    it must not evict, replace, or reorder the primary decision object.
    """
    preserved: List[str] = []
    seen: set[str] = set()
    if isinstance(existing, list):
        for item in existing:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            if not cleaned or cleaned in seen:
                continue
            if len(preserved) >= cap:
                break
            seen.add(cleaned)
            preserved.append(cleaned)
    appended: List[str] = []
    omitted: List[str] = []
    for item in additions:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        if len(preserved) + len(appended) >= cap:
            omitted.append(cleaned[:_MAX_ARG_LEN])
            continue
        seen.add(cleaned)
        appended.append(cleaned)
    return preserved + appended, {
        "cap": cap,
        "policy": LIMITATIONS_MERGE_POLICY,
        "preserved_existing": len(preserved),
        "appended": len(appended),
        "omitted": len(omitted),
        "omitted_items": omitted[:_MAX_ARGS],
    }


def merge_red_team_findings(
    payload: Dict[str, Any],
    record: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Append red-team risks/gaps. Primary decision fields stay byte-identical."""
    if not isinstance(payload, dict):
        return payload
    identity = snapshot_decision_identity(payload)
    public = public_red_team_payload(record)
    apply_red_team_to_dashboard(
        payload.get("dashboard") if isinstance(payload.get("dashboard"), dict) else payload,
        record,
    )
    if public and public.get("status") == STATUS_COMPLETED:
        stats = _append_limitations(payload, _limitation_lines(public))
        _append_risk_warning(payload, public)
        _attach_limitations_merge_stats(payload, record, stats)
    restore_decision_identity(payload, identity)
    return payload


def parse_red_team_output(raw_text: str) -> Optional[Dict[str, Any]]:
    parsed = _parse_strict_json_object(raw_text)
    if parsed is None:
        return None
    try:
        model = _RedTeamOutput.model_validate(parsed)
    except ValidationError:
        return None
    challenges = [
        {
            "claim": sanitize_agent_diagnostic(item.claim)[:_MAX_ARG_LEN],
            "weak_evidence": sanitize_agent_diagnostic(item.weak_evidence)[:_MAX_ARG_LEN],
            "severity": item.severity,
        }
        for item in model.challenges[:_MAX_CHALLENGES]
        if item.claim.strip() and item.weak_evidence.strip()
    ]
    missing = _bounded_str_list(list(model.missing_evidence))
    if not challenges and not missing and not model.counter_thesis.strip():
        return None
    return {
        "counter_thesis": sanitize_agent_diagnostic(model.counter_thesis)[:_MAX_ARG_LEN],
        "challenges": challenges,
        "missing_evidence": missing,
        "suggested_confidence_pressure": model.suggested_confidence_pressure,
    }


class BoundedRedTeamAgent(BaseAgent):
    agent_name = RED_TEAM_STAGE_NAME
    max_steps = 1
    tool_names: List[str] = []

    def __init__(self, *args: Any, red_team_config: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.red_team_config = red_team_config

    def system_prompt(self, ctx: AgentContext) -> str:
        return "You are an adversarial red-team reviewer of an already published decision."

    def build_user_message(self, ctx: AgentContext) -> str:
        return "Produce a structured independent second opinion."

    def run(
        self,
        ctx: AgentContext,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        timeout_seconds: Optional[float] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
    ) -> StageResult:
        t0 = time.time()
        result = StageResult(stage_name=self.agent_name, status=StageStatus.RUNNING)
        config = self.red_team_config if self.red_team_config is not None else getattr(
            self.llm_adapter, "_config", None
        )
        settings = resolve_red_team_settings(
            config,
            ctx,
            mode=str(ctx.meta.get("orchestrator_mode") or ""),
        )
        ctx.meta["_red_team_settings"] = settings
        budget_state = {
            "llm_turns_used": 0,
            "llm_turns_limit": _LLM_TURN_LIMIT,
            "tokens_used": 0,
            "terminated_reason": None,
        }
        models_used: List[str] = []
        try:
            if cancelled_check is not None and cancelled_check():
                record = empty_red_team_record(
                    status=STATUS_SKIPPED, settings=settings, reason="cancelled"
                )
                record["budget"]["terminated_reason"] = "cancelled"
                ctx.meta[RED_TEAM_META_KEY] = record
                result.status = StageStatus.FAILED
                result.failure_reason = StageFailureReason.STAGE_FAILURE
                result.meta["red_team"] = public_red_team_payload(record)
                return result

            mode_reason = _mode_budget_block_reason(ctx, required_turns=1)
            if mode_reason:
                record = empty_red_team_record(
                    status=STATUS_SKIPPED if mode_reason == "budget_skip" else STATUS_BUDGET_EXHAUSTED,
                    settings=settings,
                    reason="insufficient mode-budget turns for red-team stage",
                )
                record["budget"]["terminated_reason"] = mode_reason
                ctx.meta[RED_TEAM_META_KEY] = record
                result.status = StageStatus.FAILED
                result.failure_reason = (
                    StageFailureReason.BUDGET_SKIP
                    if mode_reason == "budget_skip"
                    else StageFailureReason.BUDGET_TURNS
                )
                result.meta["red_team"] = public_red_team_payload(record)
                return result

            parsed = self._run_review(
                ctx,
                timeout_seconds=_remaining_timeout(timeout_seconds, t0),
                budget_state=budget_state,
                models_used=models_used,
            )
            if parsed is None:
                status = STATUS_DATA_UNAVAILABLE
                if budget_state.get("terminated_reason") in {"timeout"}:
                    status = STATUS_DEGRADED
                record = empty_red_team_record(
                    status=status,
                    settings=settings,
                    reason="red-team provider or parse unavailable",
                )
                record["budget"] = budget_state
                ctx.meta[RED_TEAM_META_KEY] = record
                result.status = StageStatus.FAILED
                result.failure_reason = (
                    StageFailureReason.TIMEOUT
                    if budget_state.get("terminated_reason") == "timeout"
                    else StageFailureReason.STAGE_FAILURE
                )
                result.error = AGENT_EXECUTION_FAILURE_MESSAGE
                result.meta["red_team"] = public_red_team_payload(record)
                result.meta["models_used"] = list(dict.fromkeys(models_used))
                result.tokens_used = int(budget_state.get("tokens_used") or 0)
                return result

            record = {
                "enabled": True,
                "schema_version": RED_TEAM_SCHEMA_VERSION,
                "status": STATUS_COMPLETED,
                "counter_thesis": parsed["counter_thesis"],
                "challenges": parsed["challenges"],
                "missing_evidence": parsed["missing_evidence"],
                "suggested_confidence_pressure": parsed["suggested_confidence_pressure"],
                "budget": budget_state,
                "degradation": {"present": False, "reasons": []},
                "settings": {
                    "source": str(settings.get("source") or "config"),
                    "mode": str(settings.get("mode") or ""),
                },
            }
            ctx.meta[RED_TEAM_META_KEY] = record
            result.status = StageStatus.COMPLETED
            result.meta["red_team"] = public_red_team_payload(record)
            result.meta["models_used"] = list(dict.fromkeys(models_used))
            result.tokens_used = int(budget_state.get("tokens_used") or 0)
            if progress_callback:
                progress_callback({
                    "type": "red_team_completed",
                    "stage": RED_TEAM_STAGE_NAME,
                    "status": STATUS_COMPLETED,
                    "challenge_count": len(parsed["challenges"]),
                })
        except Exception as exc:  # broad-exception: fallback_recorded - Optional stage records unavailable and never fabricates challenges.
            log_safe_exception(
                logger,
                "[RedTeam] stage failed",
                exc,
                error_code="agent_red_team_failed",
                level=logging.WARNING,
            )
            record = empty_red_team_record(
                status=STATUS_DATA_UNAVAILABLE,
                settings=settings,
                reason=sanitize_agent_diagnostic(str(exc))[:_MAX_ARG_LEN],
            )
            record["budget"] = budget_state
            ctx.meta[RED_TEAM_META_KEY] = record
            result.status = StageStatus.FAILED
            result.error = AGENT_EXECUTION_FAILURE_MESSAGE
            result.failure_reason = StageFailureReason.STAGE_FAILURE
            result.meta["red_team"] = public_red_team_payload(record)
        finally:
            result.duration_s = round(time.time() - t0, 2)
        return result

    def _run_review(
        self,
        ctx: AgentContext,
        *,
        timeout_seconds: Optional[float],
        budget_state: Dict[str, Any],
        models_used: List[str],
    ) -> Optional[Dict[str, Any]]:
        evidence = _project_evidence(ctx)
        system = f"""You are an adversarial red-team reviewer of an already published stock decision.
Attack weak evidence and overconfidence. Do NOT issue a replacement DecisionSignal.
Do NOT overwrite the primary decision. Return only one JSON object with exactly these fields:
{{
  "counter_thesis": "independent counter-thesis",
  "challenges": [
    {{"claim": "challenged claim", "weak_evidence": "why the evidence is weak", "severity": "low|medium|high"}}
  ],
  "missing_evidence": ["bounded missing evidence"],
  "suggested_confidence_pressure": "none|mild|strong"
}}
Use at most {_MAX_CHALLENGES} challenges and {_MAX_ARGS} missing_evidence items.
Do not invent prices or facts that are not in the evidence pack.
"""
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    "Review this published decision and evidence. "
                    "Produce structured challenges:\n"
                    + json.dumps(evidence, ensure_ascii=False, default=str)
                ),
            },
        ]
        raw, tokens, model, cost_usd = self._call_llm(
            messages,
            temperature=_DEFAULT_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
            timeout_seconds=timeout_seconds,
        )
        budget_state["llm_turns_used"] = int(budget_state.get("llm_turns_used") or 0) + 1
        budget_state["tokens_used"] = int(budget_state.get("tokens_used") or 0) + int(tokens or 0)
        if model:
            models_used.append(model)
        budget_reason = _record_mode_budget_turn(
            ctx,
            tokens=int(tokens or 0),
            cost_usd=cost_usd,
            model=model or "",
        )
        if budget_reason and budget_state.get("terminated_reason") is None:
            budget_state["terminated_reason"] = budget_reason
        if raw is None:
            return None
        return parse_red_team_output(raw)

    def _call_llm(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
        timeout_seconds: Optional[float],
    ):
        try:
            timeout = None
            if timeout_seconds is not None and timeout_seconds > 0:
                timeout = max(0.001, float(timeout_seconds))
            response = self.llm_adapter.call_text(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            if getattr(response, "provider", None) == "error":
                return None, 0, "", 0.0
            content = (getattr(response, "content", None) or "").strip()
            usage = getattr(response, "usage", None) or {}
            tokens = 0
            if isinstance(usage, Mapping):
                try:
                    tokens = int(usage.get("total_tokens") or 0)
                except (TypeError, ValueError, OverflowError):
                    tokens = 0
            model = str(getattr(response, "model", "") or "")
            from src.agent.runtime.mode_budget import estimate_usage_cost_usd

            cost_usd = estimate_usage_cost_usd(
                usage if isinstance(usage, Mapping) else {},
                model,
            )
            return content or None, tokens, model, cost_usd
        except Exception as exc:  # broad-exception: fallback_recorded - Provider failures become data_unavailable.
            log_safe_exception(
                logger,
                "[RedTeam] LLM call failed",
                exc,
                error_code="agent_red_team_llm_failed",
                level=logging.WARNING,
            )
            return None, 0, "", 0.0


def _project_evidence(ctx: AgentContext) -> Dict[str, Any]:
    opinions = [
        {
            "agent_name": opinion.agent_name,
            "signal": opinion.signal,
            "confidence": opinion.confidence,
            "reasoning": sanitize_agent_diagnostic(str(opinion.reasoning or ""))[:_MAX_ARG_LEN],
        }
        for opinion in list(ctx.opinions)[:12]
    ]
    decision = next((item for item in reversed(opinions) if item.get("agent_name") == "decision"), None)
    return {
        "published_decision": decision,
        "opinions": opinions,
        "risk_flags": list(ctx.risk_flags or [])[:8],
        "degraded_stages": ctx.meta.get("degraded_stages", []),
        "critic_trace": ctx.meta.get("critic_trace"),
        "final_dashboard_raw": str(
            (ctx.get_data("final_dashboard_raw") if hasattr(ctx, "get_data") else None) or ""
        )[:_MAX_ARG_LEN],
    }


def _limitation_lines(public: Mapping[str, Any]) -> List[str]:
    lines: List[str] = []
    counter = str(public.get("counter_thesis") or "").strip()
    if counter:
        lines.append(f"red-team counter-thesis: {counter}"[:_MAX_ARG_LEN])
    for challenge in public.get("challenges") or []:
        if not isinstance(challenge, Mapping):
            continue
        claim = str(challenge.get("claim") or "").strip()
        weak = str(challenge.get("weak_evidence") or "").strip()
        if not claim:
            continue
        text = claim if not weak else f"{claim} (weak evidence: {weak})"
        lines.append(f"red-team challenge: {text}"[:_MAX_ARG_LEN])
    for item in public.get("missing_evidence") or []:
        text = str(item or "").strip()
        if text:
            lines.append(f"red-team missing evidence: {text}"[:_MAX_ARG_LEN])
    pressure = _normalize_pressure(public.get("suggested_confidence_pressure"))
    if pressure != "none":
        lines.append(f"red-team suggested confidence pressure: {pressure}")
    return lines[:_MAX_ARGS]


def _append_limitations(payload: Dict[str, Any], additions: Sequence[str]) -> Dict[str, Any]:
    dashboard = payload.get("dashboard")
    if not isinstance(dashboard, dict):
        dashboard = {}
        payload["dashboard"] = dashboard
    phase_decision = dashboard.get("phase_decision")
    if not isinstance(phase_decision, dict):
        phase_decision = {}
    else:
        phase_decision = dict(phase_decision)
    merged, stats = merge_data_limitations_preserving_existing(
        phase_decision.get("data_limitations"),
        additions,
    )
    phase_decision["data_limitations"] = merged
    dashboard["phase_decision"] = phase_decision
    return stats


def _attach_limitations_merge_stats(
    payload: Dict[str, Any],
    record: Optional[Mapping[str, Any]],
    stats: Mapping[str, Any],
) -> None:
    public_stats = _public_limitations_merge(stats)
    if public_stats is None:
        return
    dashboard = payload.get("dashboard")
    if isinstance(dashboard, dict) and isinstance(dashboard.get(RED_TEAM_DASHBOARD_KEY), dict):
        dashboard[RED_TEAM_DASHBOARD_KEY]["data_limitations_merge"] = dict(public_stats)
    if isinstance(record, dict):
        record["data_limitations_merge"] = dict(public_stats)


def _public_limitations_merge(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping) or not value:
        return None
    omitted_items = _bounded_str_list(value.get("omitted_items"))
    return {
        "cap": _safe_nonnegative_int(value.get("cap")) or _MAX_PRODUCT_LIMITATIONS,
        "policy": str(value.get("policy") or LIMITATIONS_MERGE_POLICY),
        "preserved_existing": _safe_nonnegative_int(value.get("preserved_existing")),
        "appended": _safe_nonnegative_int(value.get("appended")),
        "omitted": _safe_nonnegative_int(value.get("omitted")),
        "omitted_items": omitted_items,
    }


def _append_risk_warning(payload: Dict[str, Any], public: Mapping[str, Any]) -> None:
    challenges = public.get("challenges") or []
    missing = public.get("missing_evidence") or []
    if not challenges and not missing:
        return
    snippets: List[str] = []
    for challenge in challenges[:2]:
        if isinstance(challenge, Mapping) and str(challenge.get("claim") or "").strip():
            snippets.append(str(challenge.get("claim")).strip())
    for item in missing[:1]:
        text = str(item or "").strip()
        if text:
            snippets.append(text)
    if not snippets:
        return
    addition = "Red-team: " + "；".join(snippets)
    addition = addition[:_MAX_ARG_LEN]
    existing = payload.get("risk_warning")
    if not isinstance(existing, str) or not existing.strip():
        payload["risk_warning"] = addition
        return
    if addition in existing:
        return
    payload["risk_warning"] = f"{existing}；{addition}"[: _MAX_ARG_LEN * 2]


def _public_challenges(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in value[:_MAX_CHALLENGES]:
        if not isinstance(item, Mapping):
            continue
        claim = sanitize_agent_diagnostic(str(item.get("claim") or "")).strip()
        weak = sanitize_agent_diagnostic(str(item.get("weak_evidence") or "")).strip()
        if not claim or not weak:
            continue
        severity = str(item.get("severity") or "medium").strip().lower()
        if severity not in _SEVERITY_VALUES:
            severity = "medium"
        out.append({
            "claim": claim[:_MAX_ARG_LEN],
            "weak_evidence": weak[:_MAX_ARG_LEN],
            "severity": severity,
        })
    return out


def _bounded_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        text = sanitize_agent_diagnostic(str(item or "")).strip()
        if not text:
            continue
        out.append(text[:_MAX_ARG_LEN])
        if len(out) >= _MAX_ARGS:
            break
    return out


def _normalize_pressure(value: Any) -> str:
    text = str(value or "none").strip().lower()
    return text if text in _PRESSURE_VALUES else "none"


def _parse_strict_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_text, str):
        return None
    candidate = raw_text.strip()
    if not candidate:
        return None
    fenced = _JSON_FENCE_PATTERN.fullmatch(candidate)
    if fenced is not None:
        candidate = fenced.group("body").strip()
    try:
        parsed = json.loads(
            candidate,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {value}")
            ),
        )
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _mode_budget_block_reason(ctx: AgentContext, *, required_turns: int = 1) -> Optional[str]:
    account = ctx.meta.get("mode_budget_account")
    if account is None:
        return None
    check = getattr(account, "check", None)
    try:
        breach = check() if callable(check) else getattr(account, "breach", None)
        if breach is not None:
            return str(getattr(breach, "reason", None) or "budget_unavailable")
        snapshot_method = getattr(account, "snapshot", None)
        if callable(snapshot_method):
            snapshot = snapshot_method()
            limits = snapshot.get("limits") if isinstance(snapshot, Mapping) else {}
            used = snapshot.get("used") if isinstance(snapshot, Mapping) else {}
            if (limits or {}).get("enabled") is False:
                return None
            max_turns = _safe_nonnegative_int((limits or {}).get("max_llm_turns"))
            used_turns = _safe_nonnegative_int((used or {}).get("llm_turns"))
            required = max(1, int(required_turns or 1))
            if max_turns > 0 and used_turns + required > max_turns:
                return "budget_skip"
        return None
    except Exception as exc:  # broad-exception: fallback_recorded - Unreadable shared budget stops optional work.
        log_safe_exception(
            logger,
            "[RedTeam] mode budget check failed",
            exc,
            error_code="agent_red_team_mode_budget_check_failed",
            level=logging.WARNING,
        )
        return "budget_unavailable"


def _record_mode_budget_turn(
    ctx: AgentContext,
    *,
    tokens: int = 0,
    cost_usd: float = 0.0,
    model: str = "",
) -> Optional[str]:
    account = ctx.meta.get("mode_budget_account")
    if account is None:
        return None
    record = getattr(account, "record_llm_turn", None)
    if not callable(record):
        return "budget_unavailable"
    try:
        breach = record(
            tokens=max(0, int(tokens or 0)),
            cost_usd=(cost_usd if math.isfinite(cost_usd) and cost_usd >= 0 else 0.0),
            model=model or "",
        )
        return (
            str(getattr(breach, "reason", None) or "budget_unavailable")
            if breach is not None
            else None
        )
    except Exception as exc:  # broad-exception: fallback_recorded - Failed accounting stops later optional work.
        log_safe_exception(
            logger,
            "[RedTeam] mode budget record failed",
            exc,
            error_code="agent_red_team_mode_budget_record_failed",
            level=logging.DEBUG,
        )
        return "budget_unavailable"


def _safe_nonnegative_int(value: Any) -> int:
    try:
        if value is None or isinstance(value, bool):
            return 0
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, number)


def _remaining_timeout(timeout_seconds: Optional[float], started_at: float) -> Optional[float]:
    if timeout_seconds is None or timeout_seconds <= 0:
        return None
    return max(0.0, float(timeout_seconds) - (time.time() - started_at))


__all__ = [
    "BoundedRedTeamAgent",
    "RED_TEAM_DASHBOARD_KEY",
    "RED_TEAM_META_KEY",
    "RED_TEAM_SCHEMA_VERSION",
    "RED_TEAM_STAGE_NAME",
    "REQUEST_ENABLE_RED_TEAM",
    "STATUS_BUDGET_EXHAUSTED",
    "STATUS_COMPLETED",
    "STATUS_DATA_UNAVAILABLE",
    "STATUS_DEGRADED",
    "STATUS_FAILED",
    "STATUS_SKIPPED",
    "apply_pipeline_budget_skip",
    "apply_red_team_to_dashboard",
    "commit_pipeline_stage_result",
    "empty_red_team_record",
    "get_red_team_record",
    "is_red_team_enabled",
    "is_red_team_stage",
    "LIMITATIONS_MERGE_POLICY",
    "maybe_insert_after_decision",
    "maybe_skip_for_budget",
    "merge_data_limitations_preserving_existing",
    "merge_red_team_findings",
    "parse_red_team_output",
    "public_red_team_payload",
    "record_red_team_budget_skip",
    "resolve_red_team_settings",
    "restore_decision_identity",
    "snapshot_decision_identity",
]
