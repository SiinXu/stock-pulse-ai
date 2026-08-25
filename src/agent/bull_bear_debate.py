# -*- coding: utf-8 -*-
"""Optional structured Bull-Bear debate stage (Issue #117).

Default-off. When enabled on non-Chat Native Multi runs, the pipeline inserts a
tool-free debate stage after specialist/critic evidence and before DecisionAgent.

Product honesty rules (aligned with disagreement handling #1205 and red-team #1135):
- Debate results enter final products; they must not be silently discarded.
- Synthesis never invents consensus via majority vote.
- Debate does not replace the primary DecisionAgent authority; it only supplies
  structured multi-party evidence and contention points.
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
    AgentOpinion,
    AgentRunStats,
    StageFailureReason,
    StageResult,
    StageStatus,
    normalize_decision_signal,
)
from src.agent.public_contract import AGENT_EXECUTION_FAILURE_MESSAGE, sanitize_agent_diagnostic
from src.agent.runtime_facts import DegradationBoundary
from src.agent.stream_events import stream_event
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

DEBATE_STAGE_NAME = "bull_bear_debate"
DEBATE_SCHEMA_VERSION = "bull-bear-debate-v1"
DEBATE_META_KEY = "bull_bear_debate"
DEBATE_DASHBOARD_KEY = "bull_bear_debate"

RESOLUTION_RESOLVED = "resolved"
RESOLUTION_PARTIAL = "partially_resolved"
RESOLUTION_UNRESOLVED = "unresolved"

STATUS_COMPLETED = "completed"
STATUS_SKIPPED = "skipped"
STATUS_DEGRADED = "degraded"
STATUS_BUDGET_EXHAUSTED = "budget_exhausted"
STATUS_DATA_UNAVAILABLE = "data_unavailable"
STATUS_FAILED = "failed"

BULL_PARTICIPANT = "bull_researcher"
BEAR_PARTICIPANT = "bear_researcher"

_DEFAULT_MAX_ROUNDS = 2
_MIN_ROUNDS = 1
_MAX_ROUNDS = 3
_DEFAULT_TEMPERATURE = 0.4
_MAX_ARGS = 5
_MAX_ARG_LEN = 280
_MAX_POINTS = 12
_MAX_TOKENS_STANCE = 900
_MAX_TOKENS_SYNTHESIS = 700
_DECISION_LLM_TURN_RESERVE = 1
_JSON_FENCE_PATTERN = re.compile(
    r"\A```(?:json)?\s*(?P<body>.*?)\s*```\Z",
    re.DOTALL | re.IGNORECASE,
)

REQUEST_ENABLE_DEBATE = "enable_debate"
REQUEST_DEBATE_MAX_ROUNDS = "debate_max_rounds"


class _StanceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    stance: Literal["buy", "hold", "sell"]
    confidence: float = Field(ge=0.0, le=1.0)
    arguments: List[str]
    evidence_refs: List[str]
    contention_topics: List[str]


class _SynthesisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    final_lean: Literal["buy", "hold", "sell"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1, max_length=_MAX_ARG_LEN)
    winner: Literal["bull", "bear", "draw", "inconclusive"]
    resolution_status: Literal["resolved", "partially_resolved", "unresolved"]
    key_contentions: List[str]


def is_debate_stage(agent_name: Any) -> bool:
    return str(agent_name or "").strip().lower() == DEBATE_STAGE_NAME


def resolve_debate_settings(
    config: Any,
    ctx: Optional[AgentContext] = None,
    *,
    request_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    enabled = bool(getattr(config, "debate_enabled", False)) if config is not None else False
    max_rounds = _clamp_rounds(getattr(config, "debate_max_rounds", _DEFAULT_MAX_ROUNDS) if config is not None else _DEFAULT_MAX_ROUNDS)
    temperature = _safe_temperature(getattr(config, "debate_temperature", _DEFAULT_TEMPERATURE) if config is not None else _DEFAULT_TEMPERATURE)
    model = str(getattr(config, "debate_model", "") or "").strip() if config is not None else ""
    source = "config"

    request = request_context if isinstance(request_context, Mapping) else {}
    meta = ctx.meta if ctx is not None and isinstance(ctx.meta, dict) else {}

    for candidate, origin in (
        (request.get(REQUEST_ENABLE_DEBATE), "request"),
        (meta.get(REQUEST_ENABLE_DEBATE), "meta"),
    ):
        parsed = _parse_optional_bool(candidate)
        if parsed is not None:
            enabled = parsed
            source = origin
            break

    for candidate in (
        request.get(REQUEST_DEBATE_MAX_ROUNDS),
        meta.get(REQUEST_DEBATE_MAX_ROUNDS),
    ):
        if candidate is None or candidate == "":
            continue
        max_rounds = _clamp_rounds(candidate)
        break

    return {
        "enabled": enabled,
        "max_rounds": max_rounds,
        "temperature": temperature,
        "model": model,
        "source": source,
    }


def is_debate_enabled(config: Any, ctx: AgentContext) -> bool:
    if ctx.meta.get("response_mode") == "chat":
        return False
    return bool(resolve_debate_settings(config, ctx)["enabled"])


def get_debate_record(ctx: AgentContext) -> Optional[Dict[str, Any]]:
    record = ctx.meta.get(DEBATE_META_KEY)
    if not isinstance(record, Mapping) or not record:
        return None
    if record.get("schema_version") != DEBATE_SCHEMA_VERSION:
        return None
    return dict(record)


def public_debate_payload(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping) or not value:
        return None
    if value.get("schema_version") != DEBATE_SCHEMA_VERSION:
        return None
    if value.get("enabled") is not True:
        return None

    rounds_out: List[Dict[str, Any]] = []
    raw_rounds = value.get("rounds")
    if isinstance(raw_rounds, list):
        for item in raw_rounds[:_MAX_ROUNDS]:
            if not isinstance(item, Mapping):
                continue
            rounds_out.append(
                {
                    "round": _safe_nonnegative_int(item.get("round")),
                    "bull": _public_side(item.get("bull")),
                    "bear": _public_side(item.get("bear")),
                    "contention_points": _public_points(item.get("contention_points")),
                }
            )

    raw_synthesis = value.get("synthesis")
    synthesis = (
        raw_synthesis
        if isinstance(raw_synthesis, Mapping)
        and str(raw_synthesis.get("final_lean") or "") in {"buy", "hold", "sell"}
        else None
    )
    budget = value.get("budget") if isinstance(value.get("budget"), Mapping) else {}
    degradation = value.get("degradation") if isinstance(value.get("degradation"), Mapping) else {}
    settings = value.get("settings") if isinstance(value.get("settings"), Mapping) else {}

    return {
        "enabled": True,
        "schema_version": DEBATE_SCHEMA_VERSION,
        "status": str(value.get("status") or STATUS_FAILED),
        "max_rounds": _safe_nonnegative_int(value.get("max_rounds")),
        "rounds_completed": _safe_nonnegative_int(value.get("rounds_completed")),
        "rounds": rounds_out,
        "contention_points": _public_points(value.get("contention_points")),
        "disagreement_points": _public_points(value.get("disagreement_points")),
        "synthesis": (
            {
                "final_lean": str(synthesis.get("final_lean") or "hold"),
                "confidence": _clamp_unit(synthesis.get("confidence"), 0.0),
                "summary": sanitize_agent_diagnostic(str(synthesis.get("summary") or ""))[:_MAX_ARG_LEN],
                "winner": str(synthesis.get("winner") or "inconclusive"),
                "resolution_status": str(synthesis.get("resolution_status") or RESOLUTION_UNRESOLVED),
                "majority_vote_used": False,
                "key_contentions": [
                    sanitize_agent_diagnostic(str(x))[:_MAX_ARG_LEN]
                    for x in (synthesis.get("key_contentions") or [])[:_MAX_ARGS]
                    if str(x).strip()
                ],
            }
            if synthesis is not None
            else None
        ),
        "budget": {
            "llm_turns_used": _safe_nonnegative_int(budget.get("llm_turns_used")),
            "llm_turns_limit": _safe_nonnegative_int(budget.get("llm_turns_limit")),
            "tokens_used": _safe_nonnegative_int(budget.get("tokens_used")),
            "terminated_reason": budget.get("terminated_reason"),
        },
        "degradation": {
            "present": bool(degradation.get("present")),
            "reasons": [
                sanitize_agent_diagnostic(str(x))[:_MAX_ARG_LEN]
                for x in (degradation.get("reasons") or [])[:_MAX_ARGS]
                if str(x).strip()
            ],
        },
        "settings": {
            "temperature": _safe_temperature(settings.get("temperature")),
            "model": str(settings.get("model") or ""),
            "source": str(settings.get("source") or "config"),
        },
    }


def decision_signal_debate_metadata(value: Any) -> Dict[str, Any]:
    public = public_debate_payload(value)
    if not public:
        return {}
    synthesis = public.get("synthesis") or {}
    return {
        "debate_enabled": True,
        "debate_status": public.get("status"),
        "debate_rounds": public.get("rounds_completed"),
        "debate_max_rounds": public.get("max_rounds"),
        "debate_summary": synthesis.get("summary") or "",
        "debate_final_lean": synthesis.get("final_lean"),
        "debate_winner": synthesis.get("winner"),
        "debate_resolution_status": synthesis.get("resolution_status"),
        "debate_contention_count": len(public.get("contention_points") or []),
        "debate_schema_version": DEBATE_SCHEMA_VERSION,
    }


def empty_debate_record(*, status: str, settings: Mapping[str, Any], reason: str = "") -> Dict[str, Any]:
    reasons = [sanitize_agent_diagnostic(reason)] if reason else []
    return {
        "enabled": True,
        "schema_version": DEBATE_SCHEMA_VERSION,
        "status": status,
        "max_rounds": int(settings.get("max_rounds") or _DEFAULT_MAX_ROUNDS),
        "rounds_completed": 0,
        "rounds": [],
        "contention_points": [],
        "disagreement_points": [],
        "synthesis": None,
        "budget": {
            "llm_turns_used": 0,
            "llm_turns_limit": _llm_turn_limit(int(settings.get("max_rounds") or _DEFAULT_MAX_ROUNDS)),
            "tokens_used": 0,
            "terminated_reason": (
                "budget_turns" if status == STATUS_BUDGET_EXHAUSTED
                else ("budget_skip" if status == STATUS_SKIPPED and "budget" in reason.lower() else None)
            ),
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
            "temperature": _safe_temperature(settings.get("temperature")),
            "model": str(settings.get("model") or ""),
            "source": str(settings.get("source") or "config"),
        },
    }


def record_debate_budget_skip(
    ctx: AgentContext,
    *,
    settings: Optional[Mapping[str, Any]] = None,
    reason: str = "insufficient wall-clock budget",
) -> Dict[str, Any]:
    resolved = dict(settings) if isinstance(settings, Mapping) else None
    if resolved is None:
        cached = ctx.meta.get("_debate_settings")
        resolved = dict(cached) if isinstance(cached, Mapping) else {
            "enabled": True,
            "max_rounds": _DEFAULT_MAX_ROUNDS,
            "temperature": _DEFAULT_TEMPERATURE,
            "model": "",
            "source": "config",
        }
    record = empty_debate_record(status=STATUS_SKIPPED, settings=resolved, reason=reason)
    ctx.meta[DEBATE_META_KEY] = record
    return record


def reserve_optional_stage_timeout(
    stage_name: str,
    timeout_s: Optional[float],
    elapsed_s: float,
    is_critic_stage: bool,
    reserve_s: float,
    margin_s: float,
) -> Optional[float]:
    """Reserve Decision wall-clock budget for critic or debate stages."""
    remaining = max(0.0, timeout_s - elapsed_s) if timeout_s else None
    if remaining is None:
        return None
    if is_critic_stage or is_debate_stage(stage_name):
        return max(0.0, remaining - reserve_s - margin_s)
    return remaining


def maybe_insert_before_decision(
    pipeline: Any,
    agents: list,
    index: int,
    ctx: AgentContext,
    stats: AgentRunStats,
    timeout_s: Optional[float],
    remaining_budget: Optional[float],
    required_budget_s: float,
    progress_callback: Optional[Callable],
) -> bool:
    """Insert or skip debate before Decision. True means the caller should ``continue``."""
    agent = agents[index]
    if (
        agent.agent_name != "decision"
        or ctx.meta.get("_debate_inserted")
        or not is_debate_enabled(pipeline.config, ctx)
    ):
        return False
    ctx.meta["_debate_inserted"] = True
    debate_settings = resolve_debate_settings(pipeline.config, ctx)
    ctx.meta["_debate_settings"] = debate_settings
    has_budget = (
        not timeout_s
        or remaining_budget is None
        or remaining_budget >= required_budget_s
    )
    if not has_budget:
        apply_pipeline_budget_skip(
            pipeline,
            ctx,
            stats,
            settings=debate_settings,
            progress_callback=progress_callback,
        )
        return False
    debate_agent = pipeline._prepare_agent(
        BoundedBullBearDebateAgent(
            tool_registry=pipeline._tool_registry_for_context(ctx),
            llm_adapter=pipeline.llm_adapter,
            skill_instructions=pipeline.skill_instructions,
            technical_skill_policy=pipeline.technical_skill_policy,
            config=pipeline.config,
            debate_config=pipeline.config,
        )
    )
    agents.insert(index, debate_agent)
    return True


def apply_pipeline_budget_skip(
    pipeline: Any,
    ctx: AgentContext,
    stats: AgentRunStats,
    *,
    settings: Optional[Mapping[str, Any]] = None,
    progress_callback: Optional[Callable] = None,
) -> None:
    """Fail soft on debate without spending Decision's reserved wall-clock budget."""
    record = record_debate_budget_skip(
        ctx,
        settings=settings,
        reason="insufficient wall-clock budget for debate stage",
    )
    public = public_debate_payload(record) or {}
    result = StageResult(
        stage_name=DEBATE_STAGE_NAME,
        status=StageStatus.FAILED,
        failure_reason=StageFailureReason.BUDGET_SKIP,
        meta={"bull_bear_debate": public},
    )
    stats.record_stage(result)
    pipeline._record_degraded_stage(
        ctx,
        DEBATE_STAGE_NAME,
        result,
        boundary=DegradationBoundary.BEFORE_STAGE,
    )
    if progress_callback:
        progress_callback(stream_event(
            "debate_budget_skipped",
            stage=DEBATE_STAGE_NAME,
            status=public.get("status"),
            rounds_completed=public.get("rounds_completed"),
        ))


def commit_pipeline_stage_result(
    ctx: AgentContext,
    result: StageResult,
    stage_name: str,
) -> None:
    """Persist debate evidence onto the stage result and shared context."""
    if not is_debate_stage(stage_name):
        return
    debate_record = get_debate_record(ctx)
    staged_record = result.meta.get("bull_bear_debate")
    if debate_record is None and isinstance(staged_record, dict):
        debate_record = dict(staged_record)
        ctx.meta[DEBATE_META_KEY] = debate_record
    if debate_record is None:
        debate_record = empty_debate_record(
            status=(
                STATUS_DATA_UNAVAILABLE
                if result.status == StageStatus.FAILED
                else STATUS_DEGRADED
            ),
            settings=ctx.meta.get("_debate_settings") or {
                "max_rounds": 2,
                "temperature": 0.4,
                "model": "",
                "source": "config",
            },
            reason=result.error or "debate_record_missing",
        )
        ctx.meta[DEBATE_META_KEY] = debate_record
    result.meta["bull_bear_debate"] = public_debate_payload(debate_record)


def build_contention_point(
    *,
    topic: str,
    round_index: int,
    bull_claim: str = "",
    bear_claim: str = "",
    severity: str = "medium",
    kind: str = "contention_point",
) -> Dict[str, Any]:
    clean_severity = severity if severity in {"low", "medium", "high"} else "medium"
    clean_kind = str(kind or "contention_point").strip() or "contention_point"
    clean_topic = sanitize_agent_diagnostic(topic)[:_MAX_ARG_LEN] or "unspecified"
    return {
        "source": "debate",
        "kind": clean_kind,
        "severity": clean_severity,
        "participants": [BULL_PARTICIPANT, BEAR_PARTICIPANT],
        "sides": {"bullish": [BULL_PARTICIPANT], "bearish": [BEAR_PARTICIPANT]},
        "summary_key": f"debate.point.{clean_kind}",
        "topic": clean_topic,
        "round": _safe_nonnegative_int(round_index),
        "bull_claim": sanitize_agent_diagnostic(bull_claim)[:_MAX_ARG_LEN],
        "bear_claim": sanitize_agent_diagnostic(bear_claim)[:_MAX_ARG_LEN],
    }


def synthesize_debate_deterministic(
    rounds: Sequence[Mapping[str, Any]],
    *,
    contention_points: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    bull_conf = 0.0
    bear_conf = 0.0
    bull_stance = "hold"
    bear_stance = "hold"
    if rounds:
        last = rounds[-1]
        bull = last.get("bull") if isinstance(last.get("bull"), Mapping) else {}
        bear = last.get("bear") if isinstance(last.get("bear"), Mapping) else {}
        bull_stance = normalize_decision_signal(bull.get("stance") or "hold")
        bear_stance = normalize_decision_signal(bear.get("stance") or "hold")
        bull_conf = _clamp_unit(bull.get("confidence"), 0.0)
        bear_conf = _clamp_unit(bear.get("confidence"), 0.0)

    opposing = _stances_oppose(bull_stance, bear_stance) or bool(contention_points)
    if opposing:
        final_lean = "hold"
        winner = "draw" if abs(bull_conf - bear_conf) < 0.15 else ("bull" if bull_conf > bear_conf else "bear")
        resolution = RESOLUTION_UNRESOLVED
        confidence = round(min(bull_conf, bear_conf, 0.45), 4)
        summary = "Bull and Bear remain opposed; conservative hold lean without majority vote."
    elif bull_stance in {"buy", "strong_buy"} and bear_stance in {"buy", "hold"}:
        final_lean, winner, resolution = "buy", "bull", RESOLUTION_PARTIAL
        confidence = round(min(0.65, (bull_conf + (1.0 - bear_conf)) / 2), 4)
        summary = "Debate leaned bullish with limited bear pushback."
    elif bear_stance in {"sell", "strong_sell"} and bull_stance in {"sell", "hold"}:
        final_lean, winner, resolution = "sell", "bear", RESOLUTION_PARTIAL
        confidence = round(min(0.65, (bear_conf + (1.0 - bull_conf)) / 2), 4)
        summary = "Debate leaned bearish with limited bull pushback."
    else:
        final_lean, winner = "hold", "inconclusive"
        resolution = RESOLUTION_PARTIAL if rounds else RESOLUTION_UNRESOLVED
        confidence = 0.4
        summary = "Debate did not produce a decisive directional lean."

    key_contentions = [
        str(point.get("topic") or point.get("kind") or "").strip()
        for point in list(contention_points)[:_MAX_ARGS]
        if isinstance(point, Mapping)
    ]
    return {
        "final_lean": final_lean,
        "confidence": confidence,
        "summary": summary,
        "winner": winner,
        "resolution_status": resolution,
        "majority_vote_used": False,
        "key_contentions": [item for item in key_contentions if item],
    }


def parse_stance_output(raw_text: str, *, side: str) -> Optional[Dict[str, Any]]:
    if side not in {"bull", "bear"}:
        return None
    parsed = _parse_strict_json_object(raw_text)
    if not isinstance(parsed, dict):
        return None
    try:
        model = _StanceOutput.model_validate(parsed)
    except (ValidationError, TypeError, ValueError):
        return None
    return {
        "side": side,
        "participant": BULL_PARTICIPANT if side == "bull" else BEAR_PARTICIPANT,
        "stance": model.stance,
        "confidence": float(model.confidence),
        "arguments": _bounded_str_list(model.arguments),
        "evidence_refs": _bounded_str_list(model.evidence_refs),
        "contention_topics": _bounded_str_list(model.contention_topics),
    }


def parse_synthesis_output(raw_text: str) -> Optional[Dict[str, Any]]:
    parsed = _parse_strict_json_object(raw_text)
    if not isinstance(parsed, dict):
        return None
    try:
        model = _SynthesisOutput.model_validate(parsed)
    except (ValidationError, TypeError, ValueError):
        return None
    return {
        "final_lean": model.final_lean,
        "confidence": float(model.confidence),
        "summary": sanitize_agent_diagnostic(model.summary)[:_MAX_ARG_LEN],
        "winner": model.winner,
        "resolution_status": model.resolution_status,
        "majority_vote_used": False,
        "key_contentions": _bounded_str_list(model.key_contentions),
    }


def extract_contention_points(
    *,
    round_index: int,
    bull: Optional[Mapping[str, Any]],
    bear: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    points: List[Dict[str, Any]] = []
    bull = bull if isinstance(bull, Mapping) else {}
    bear = bear if isinstance(bear, Mapping) else {}
    bull_stance = str(bull.get("stance") or "hold")
    bear_stance = str(bear.get("stance") or "hold")
    if _stances_oppose(bull_stance, bear_stance):
        points.append(
            build_contention_point(
                topic="directional_opposition",
                round_index=round_index,
                bull_claim=f"stance={bull_stance}",
                bear_claim=f"stance={bear_stance}",
                severity="high",
                kind="directional_opposition",
            )
        )
    topics = []
    for source in (bull.get("contention_topics"), bear.get("contention_topics")):
        if isinstance(source, list):
            topics.extend(str(item).strip() for item in source if str(item).strip())
    bull_args = list(bull.get("arguments") or [])
    bear_args = list(bear.get("arguments") or [])
    if not topics and bull_args and bear_args:
        topics.append("argument_clash")
    seen = set()
    for topic in topics:
        key = topic.lower()
        if key in seen:
            continue
        seen.add(key)
        points.append(
            build_contention_point(
                topic=topic,
                round_index=round_index,
                bull_claim=str(bull_args[0]) if bull_args else "",
                bear_claim=str(bear_args[0]) if bear_args else "",
                severity="medium",
                kind="contention_point",
            )
        )
        if len(points) >= _MAX_POINTS:
            break
    return points[:_MAX_POINTS]


def apply_debate_to_dashboard(dashboard: Dict[str, Any], record: Optional[Mapping[str, Any]]) -> None:
    if not isinstance(dashboard, dict):
        return
    dashboard.pop(DEBATE_DASHBOARD_KEY, None)
    public = public_debate_payload(record)
    if public:
        dashboard[DEBATE_DASHBOARD_KEY] = public


class BoundedBullBearDebateAgent(BaseAgent):
    agent_name = DEBATE_STAGE_NAME
    max_steps = 1
    tool_names: List[str] = []

    def __init__(self, *args: Any, debate_config: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.debate_config = debate_config

    def system_prompt(self, ctx: AgentContext) -> str:
        return "You are a structured bull-bear debate coordinator."

    def build_user_message(self, ctx: AgentContext) -> str:
        return "Structured bull-bear debate stage."

    def run(
        self,
        ctx: AgentContext,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        timeout_seconds: Optional[float] = None,
        cancelled_check: Optional[Callable[[], bool]] = None,
    ) -> StageResult:
        t0 = time.time()
        result = StageResult(stage_name=self.agent_name, status=StageStatus.RUNNING)
        config = self.debate_config if self.debate_config is not None else getattr(self.llm_adapter, "_config", None)
        settings = resolve_debate_settings(config, ctx)
        ctx.meta["_debate_settings"] = settings
        max_rounds = int(settings["max_rounds"])
        turn_limit = _llm_turn_limit(max_rounds)
        budget_state = {
            "llm_turns_used": 0,
            "llm_turns_limit": turn_limit,
            "tokens_used": 0,
            "terminated_reason": None,
        }
        degradation_reasons: List[str] = []
        rounds: List[Dict[str, Any]] = []
        all_points: List[Dict[str, Any]] = []
        models_used: List[str] = []

        try:
            evidence = _project_evidence(ctx)
            prior_transcript: List[Dict[str, Any]] = []

            for round_index in range(1, max_rounds + 1):
                if cancelled_check is not None and cancelled_check():
                    budget_state["terminated_reason"] = "cancelled"
                    degradation_reasons.append("cancelled")
                    break
                if timeout_seconds is not None and timeout_seconds > 0 and time.time() - t0 >= float(timeout_seconds):
                    budget_state["terminated_reason"] = "timeout"
                    degradation_reasons.append("stage_timeout")
                    break
                mode_budget_reason = _mode_budget_block_reason(ctx, required_turns=2)
                if budget_state["llm_turns_used"] + 2 > turn_limit or mode_budget_reason:
                    budget_state["terminated_reason"] = mode_budget_reason or "budget_turns"
                    degradation_reasons.append("debate_turn_budget")
                    break

                bull = self._run_side(
                    ctx, side="bull", round_index=round_index, evidence=evidence,
                    prior_transcript=prior_transcript, temperature=float(settings["temperature"]),
                    model_name=str(settings.get("model") or ""),
                    timeout_seconds=_remaining_timeout(timeout_seconds, t0),
                    budget_state=budget_state, models_used=models_used,
                )
                if bull is None:
                    degradation_reasons.append(f"bull_round_{round_index}_failed")
                    break

                if cancelled_check is not None and cancelled_check():
                    budget_state["terminated_reason"] = "cancelled"
                    degradation_reasons.append("cancelled")
                    rounds.append({"round": round_index, "bull": bull, "bear": None, "contention_points": [], "incomplete": True})
                    break
                if timeout_seconds is not None and timeout_seconds > 0 and time.time() - t0 >= float(timeout_seconds):
                    budget_state["terminated_reason"] = "timeout"
                    degradation_reasons.append("stage_timeout")
                    rounds.append({"round": round_index, "bull": bull, "bear": None, "contention_points": [], "incomplete": True})
                    break
                mode_budget_reason = _mode_budget_block_reason(ctx, required_turns=1)
                if budget_state["llm_turns_used"] + 1 > turn_limit or mode_budget_reason:
                    budget_state["terminated_reason"] = mode_budget_reason or "budget_turns"
                    degradation_reasons.append("debate_turn_budget_after_bull")
                    rounds.append({"round": round_index, "bull": bull, "bear": None, "contention_points": [], "incomplete": True})
                    break

                bear = self._run_side(
                    ctx, side="bear", round_index=round_index, evidence=evidence,
                    prior_transcript=prior_transcript + [{"side": "bull", **bull}],
                    temperature=float(settings["temperature"]),
                    model_name=str(settings.get("model") or ""),
                    timeout_seconds=_remaining_timeout(timeout_seconds, t0),
                    budget_state=budget_state, models_used=models_used,
                )
                if bear is None:
                    degradation_reasons.append(f"bear_round_{round_index}_failed")
                    rounds.append({"round": round_index, "bull": bull, "bear": None, "contention_points": [], "incomplete": True})
                    break

                points = extract_contention_points(round_index=round_index, bull=bull, bear=bear)
                all_points.extend(points)
                rounds.append({"round": round_index, "bull": bull, "bear": bear, "contention_points": points, "incomplete": False})
                prior_transcript.append({"side": "bull", **bull})
                prior_transcript.append({"side": "bear", **bear})

            complete_rounds = [item for item in rounds if not item.get("incomplete")]
            synthesis: Optional[Dict[str, Any]] = None
            provider_failed = any(
                str(reason).endswith("_failed")
                for reason in degradation_reasons
            )
            if complete_rounds and not provider_failed:
                mode_budget_reason = _mode_budget_block_reason(ctx, required_turns=1)
                cancelled = cancelled_check is not None and cancelled_check()
                timed_out = (
                    timeout_seconds is not None
                    and timeout_seconds > 0
                    and time.time() - t0 >= float(timeout_seconds)
                )
                can_synthesize = (
                    budget_state["llm_turns_used"] < turn_limit
                    and not mode_budget_reason
                    and not cancelled
                    and not timed_out
                )
                if can_synthesize:
                    synthesis = self._run_synthesis(
                        ctx, rounds=complete_rounds, contention_points=all_points,
                        temperature=float(settings["temperature"]),
                        model_name=str(settings.get("model") or ""),
                        timeout_seconds=_remaining_timeout(timeout_seconds, t0),
                        budget_state=budget_state, models_used=models_used,
                    )
                    if synthesis is None:
                        degradation_reasons.append("synthesis_llm_failed")
                else:
                    if budget_state["terminated_reason"] is None:
                        budget_state["terminated_reason"] = (
                            "cancelled"
                            if cancelled
                            else "timeout"
                            if timed_out
                            else mode_budget_reason or "budget_turns"
                        )
                    degradation_reasons.append(
                        "cancelled"
                        if cancelled
                        else "stage_timeout"
                        if timed_out
                        else "synthesis_skipped_budget"
                    )

            if not complete_rounds:
                # An incomplete one-sided provider response is diagnostic only. Do not
                # expose it as debate evidence or let it bias DecisionAgent.
                rounds = []
                all_points = []

            status = _resolve_status(rounds=rounds, degradation_reasons=degradation_reasons, terminated_reason=budget_state.get("terminated_reason"))
            unique_points = _dedupe_points(all_points)[:_MAX_POINTS]
            record = {
                "enabled": True,
                "schema_version": DEBATE_SCHEMA_VERSION,
                "status": status,
                "max_rounds": max_rounds,
                "rounds_completed": sum(1 for item in rounds if not item.get("incomplete")),
                "rounds": rounds,
                "contention_points": unique_points,
                "disagreement_points": unique_points,
                "synthesis": synthesis,
                "budget": budget_state,
                "degradation": {
                    "present": bool(degradation_reasons) or status != STATUS_COMPLETED,
                    "reasons": [sanitize_agent_diagnostic(item)[:_MAX_ARG_LEN] for item in degradation_reasons[:_MAX_ARGS]],
                },
                "settings": {
                    "temperature": float(settings["temperature"]),
                    "model": str(settings.get("model") or ""),
                    "source": str(settings.get("source") or "config"),
                },
            }
            ctx.meta[DEBATE_META_KEY] = record
            if synthesis is not None:
                ctx.add_opinion(
                    AgentOpinion(
                        agent_name=DEBATE_STAGE_NAME,
                        signal=str(synthesis.get("final_lean")),
                        confidence=float(synthesis.get("confidence") or 0.0),
                        reasoning=str(synthesis.get("summary") or ""),
                        raw_data={
                            "debate_status": status,
                            "winner": synthesis.get("winner"),
                            "resolution_status": synthesis.get("resolution_status"),
                            "contention_count": len(unique_points),
                            "majority_vote_used": False,
                        },
                    )
                )
            result.status = (
                StageStatus.COMPLETED
                if status in {STATUS_COMPLETED, STATUS_DEGRADED}
                else StageStatus.FAILED
            )
            if result.status == StageStatus.FAILED:
                result.error = AGENT_EXECUTION_FAILURE_MESSAGE
                result.failure_reason = _stage_failure_reason(
                    budget_state.get("terminated_reason")
                )
            result.meta["bull_bear_debate"] = public_debate_payload(record)
            result.meta["models_used"] = list(dict.fromkeys(models_used))
            result.tokens_used = int(budget_state.get("tokens_used") or 0)
            if progress_callback:
                progress_callback({
                    "type": "debate_completed",
                    "stage": DEBATE_STAGE_NAME,
                    "status": status,
                    "rounds_completed": record["rounds_completed"],
                    "contention_count": len(unique_points),
                })
        except Exception as exc:  # broad-exception: fallback_recorded - The optional stage records a typed unavailable result and never fabricates evidence.
            log_safe_exception(logger, "[Debate] stage failed", exc, error_code="agent_bull_bear_debate_failed", level=logging.WARNING)
            record = empty_debate_record(status=STATUS_DATA_UNAVAILABLE, settings=settings, reason=sanitize_agent_diagnostic(str(exc))[:_MAX_ARG_LEN])
            record["budget"] = budget_state
            ctx.meta[DEBATE_META_KEY] = record
            result.status = StageStatus.FAILED
            result.error = AGENT_EXECUTION_FAILURE_MESSAGE
            result.failure_reason = StageFailureReason.STAGE_FAILURE
            result.meta["bull_bear_debate"] = public_debate_payload(record)
        finally:
            result.duration_s = round(time.time() - t0, 2)
        return result

    def _run_side(self, ctx, *, side, round_index, evidence, prior_transcript, temperature, model_name, timeout_seconds, budget_state, models_used):
        role = "Bull Researcher" if side == "bull" else "Bear Researcher"
        mandate = (
            "Argue the strongest legitimate bullish case. Challenge complacent risks."
            if side == "bull"
            else "Argue the strongest legitimate bearish case. Attack weak evidence and overconfidence."
        )
        system = f"""You are the {role} in a structured multi-agent stock debate.
{mandate}
You do NOT make the final investment decision. DecisionAgent retains authority.
Return only one JSON object with exactly these fields:
{{
  "stance": "buy|hold|sell",
  "confidence": 0.0,
  "arguments": ["bounded argument"],
  "evidence_refs": ["bounded evidence reference"],
  "contention_topics": ["topic of disagreement"]
}}
Use at most {_MAX_ARGS} items per list. Do not invent price levels not present in evidence.
Never claim majority consensus.
"""
        user_payload = {
            "round": round_index,
            "side": side,
            "stock_code": ctx.stock_code,
            "stock_name": ctx.stock_name,
            "evidence": evidence,
            "prior_transcript": list(prior_transcript)[-6:],
        }
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "Produce your structured debate stance for this round:\n" + json.dumps(user_payload, ensure_ascii=False, default=str)},
        ]
        raw, tokens, model, cost_usd = self._call_llm(
            messages,
            temperature=temperature,
            max_tokens=_MAX_TOKENS_STANCE,
            timeout_seconds=timeout_seconds,
            model_name=model_name,
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
        if raw is None or budget_reason:
            return None
        return parse_stance_output(raw, side=side)

    def _run_synthesis(self, ctx, *, rounds, contention_points, temperature, model_name, timeout_seconds, budget_state, models_used):
        system = f"""You are the Debate Synthesis clerk. Summarize Bull vs Bear debate for DecisionAgent.
You do NOT issue a DecisionSignal or overwrite the primary decision.
Rules:
- Never invent consensus via majority vote (majority_vote_used must be treated as false).
- If sides remain opposed, prefer final_lean=hold and resolution_status=unresolved.
- resolution_status must be one of: resolved | partially_resolved | unresolved.
- winner must be one of: bull | bear | draw | inconclusive.
Return only one JSON object:
{{
  "final_lean": "buy|hold|sell",
  "confidence": 0.0,
  "summary": "short summary",
  "winner": "bull|bear|draw|inconclusive",
  "resolution_status": "resolved|partially_resolved|unresolved",
  "key_contentions": ["topic"]
}}
"""
        payload = {"stock_code": ctx.stock_code, "rounds": list(rounds), "contention_points": list(contention_points)[:_MAX_POINTS]}
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "Synthesize this debate transcript:\n" + json.dumps(payload, ensure_ascii=False, default=str)},
        ]
        raw, tokens, model, cost_usd = self._call_llm(
            messages,
            temperature=min(temperature, 0.3),
            max_tokens=_MAX_TOKENS_SYNTHESIS,
            timeout_seconds=timeout_seconds,
            model_name=model_name,
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
        if raw is None or budget_reason:
            return None
        return parse_synthesis_output(raw)

    def _call_llm(
        self,
        messages,
        *,
        temperature,
        max_tokens,
        timeout_seconds,
        model_name="",
    ):
        try:
            timeout = None
            if timeout_seconds is not None and timeout_seconds > 0:
                timeout = max(0.001, float(timeout_seconds))
            if model_name:
                call_model = getattr(self.llm_adapter, "_call_litellm_model", None)
                if not callable(call_model):
                    logger.warning(
                        "[Debate] dedicated model route unavailable",
                    )
                    return None, 0, "", 0.0
                response = call_model(
                    messages,
                    [],
                    model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
            else:
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
            model = str(getattr(response, "model", "") or model_name or "")
            from src.agent.runtime.mode_budget import estimate_usage_cost_usd

            cost_usd = estimate_usage_cost_usd(
                usage if isinstance(usage, Mapping) else {},
                model,
            )
            return content or None, tokens, model, cost_usd
        except Exception as exc:  # broad-exception: fallback_recorded - Provider failures are converted to data_unavailable by the stage boundary.
            log_safe_exception(logger, "[Debate] LLM call failed", exc, error_code="agent_bull_bear_debate_llm_failed", level=logging.WARNING)
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
    return {
        "opinions": opinions,
        "risk_flags": list(ctx.risk_flags or [])[:8],
        "degraded_stages": ctx.meta.get("degraded_stages", []),
        "agent_disagreement_summary": ctx.meta.get("agent_disagreement_summary"),
        "requested_skills": ctx.meta.get("skills_requested") or ctx.meta.get("strategies_requested") or [],
    }


def _llm_turn_limit(max_rounds: int) -> int:
    return max(1, int(max_rounds) * 2 + 1)


def _resolve_status(*, rounds, degradation_reasons, terminated_reason):
    complete_rounds = [item for item in rounds if not item.get("incomplete")]
    if terminated_reason in {"budget_turns", "budget_tools", "budget_cost", "budget_tokens"}:
        return STATUS_BUDGET_EXHAUSTED
    if terminated_reason == "budget_skip":
        return STATUS_DEGRADED if complete_rounds else STATUS_SKIPPED
    if any(str(reason).endswith("_failed") for reason in degradation_reasons):
        return STATUS_DATA_UNAVAILABLE
    if not complete_rounds:
        return STATUS_FAILED
    if degradation_reasons or terminated_reason:
        return STATUS_DEGRADED
    return STATUS_COMPLETED


def _mode_budget_block_reason(
    ctx: AgentContext,
    *,
    required_turns: int = 1,
) -> Optional[str]:
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
            required_with_decision = required + _DECISION_LLM_TURN_RESERVE
            if max_turns > 0 and used_turns + required_with_decision > max_turns:
                # Yield remaining capacity to Decision instead of fail-fasting
                # the pipeline with a hard budget_turns breach.
                if used_turns + _DECISION_LLM_TURN_RESERVE > max_turns:
                    return "budget_turns"
                return "budget_skip"
        return None
    except Exception as exc:  # broad-exception: fallback_recorded - An unreadable shared budget must stop the optional provider work.
        log_safe_exception(
            logger,
            "[Debate] mode budget check failed",
            exc,
            error_code="agent_debate_mode_budget_check_failed",
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
    except Exception as exc:  # broad-exception: fallback_recorded - Failed accounting stops later debate work rather than bypassing the hard budget.
        log_safe_exception(logger, "[Debate] mode budget record failed", exc, error_code="agent_debate_mode_budget_record_failed", level=logging.DEBUG)
        return "budget_unavailable"


def _stage_failure_reason(reason: Any) -> StageFailureReason:
    mapping = {
        "budget_turns": StageFailureReason.BUDGET_TURNS,
        "budget_tools": StageFailureReason.BUDGET_TOOLS,
        "budget_cost": StageFailureReason.BUDGET_COST,
        "budget_tokens": StageFailureReason.BUDGET_TOKENS,
        "budget_skip": StageFailureReason.BUDGET_SKIP,
        "timeout": StageFailureReason.TIMEOUT,
    }
    return mapping.get(str(reason or ""), StageFailureReason.STAGE_FAILURE)


def _public_side(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    stance = str(value.get("stance") or "").strip().lower()
    if stance not in {"buy", "hold", "sell"}:
        return None
    return {
        "participant": str(value.get("participant") or ""),
        "stance": stance,
        "confidence": _clamp_unit(value.get("confidence"), 0.0),
        "arguments": [sanitize_agent_diagnostic(str(x))[:_MAX_ARG_LEN] for x in (value.get("arguments") or [])[:_MAX_ARGS] if str(x).strip()],
        "evidence_refs": [sanitize_agent_diagnostic(str(x))[:_MAX_ARG_LEN] for x in (value.get("evidence_refs") or [])[:_MAX_ARGS] if str(x).strip()],
        "contention_topics": [sanitize_agent_diagnostic(str(x))[:_MAX_ARG_LEN] for x in (value.get("contention_topics") or [])[:_MAX_ARGS] if str(x).strip()],
    }


def _public_points(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in value[:_MAX_POINTS]:
        if not isinstance(item, Mapping):
            continue
        participants = item.get("participants")
        sides = item.get("sides") if isinstance(item.get("sides"), Mapping) else {}
        out.append({
            "source": str(item.get("source") or "debate"),
            "kind": str(item.get("kind") or "contention_point"),
            "severity": str(item.get("severity") or "medium"),
            "participants": [str(p).strip() for p in (participants if isinstance(participants, list) else []) if str(p).strip()][:12],
            "sides": {
                "bullish": [str(x).strip() for x in (sides.get("bullish") or []) if str(x).strip()][:12],
                "bearish": [str(x).strip() for x in (sides.get("bearish") or []) if str(x).strip()][:12],
            },
            "summary_key": str(item.get("summary_key") or ""),
            "topic": sanitize_agent_diagnostic(str(item.get("topic") or ""))[:_MAX_ARG_LEN],
            "round": _safe_nonnegative_int(item.get("round")),
            "bull_claim": sanitize_agent_diagnostic(str(item.get("bull_claim") or ""))[:_MAX_ARG_LEN],
            "bear_claim": sanitize_agent_diagnostic(str(item.get("bear_claim") or ""))[:_MAX_ARG_LEN],
        })
    return out


def _dedupe_points(points: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for point in points:
        if not isinstance(point, Mapping):
            continue
        key = (
            str(point.get("kind") or ""),
            str(point.get("topic") or ""),
            _safe_nonnegative_int(point.get("round")),
            str(point.get("severity") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(point))
    return out


def _stances_oppose(left: str, right: str) -> bool:
    bullish = {"buy", "strong_buy"}
    bearish = {"sell", "strong_sell"}
    a = str(left or "").strip().lower()
    b = str(right or "").strip().lower()
    return (a in bullish and b in bearish) or (a in bearish and b in bullish)


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


def _clamp_rounds(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return _DEFAULT_MAX_ROUNDS
    return max(_MIN_ROUNDS, min(_MAX_ROUNDS, number))


def _safe_temperature(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return _DEFAULT_TEMPERATURE
    if not math.isfinite(number):
        return _DEFAULT_TEMPERATURE
    return max(0.0, min(1.5, number))


def _clamp_unit(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return max(0.0, min(1.0, number))


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
    "BULL_PARTICIPANT", "BEAR_PARTICIPANT", "BoundedBullBearDebateAgent",
    "DEBATE_DASHBOARD_KEY", "DEBATE_META_KEY", "DEBATE_SCHEMA_VERSION", "DEBATE_STAGE_NAME",
    "REQUEST_DEBATE_MAX_ROUNDS", "REQUEST_ENABLE_DEBATE",
    "RESOLUTION_PARTIAL", "RESOLUTION_RESOLVED", "RESOLUTION_UNRESOLVED",
    "STATUS_BUDGET_EXHAUSTED", "STATUS_COMPLETED", "STATUS_DATA_UNAVAILABLE", "STATUS_DEGRADED", "STATUS_FAILED", "STATUS_SKIPPED",
    "apply_debate_to_dashboard", "apply_pipeline_budget_skip", "build_contention_point",
    "commit_pipeline_stage_result", "decision_signal_debate_metadata",
    "empty_debate_record", "extract_contention_points", "get_debate_record",
    "is_debate_enabled", "is_debate_stage", "maybe_insert_before_decision",
    "parse_stance_output", "parse_synthesis_output",
    "public_debate_payload", "record_debate_budget_skip", "reserve_optional_stage_timeout",
    "resolve_debate_settings", "synthesize_debate_deterministic",
]
