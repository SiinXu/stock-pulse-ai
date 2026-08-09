# -*- coding: utf-8 -*-
"""Internal, low-sensitivity facts produced by the multi-agent runtime.

These types are intentionally separate from report schemas. They describe
what happened inside an Agent run without publishing reasoning, raw payloads,
errors, tokens, or a user-facing final explanation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import Enum
from math import isfinite
from typing import TYPE_CHECKING, Any, Optional, Tuple

from src.agent.protocols import (
    AgentContext,
    AgentOpinion,
    StageFailureReason,
    normalize_stage_failure_reason,
)
from src.agent.soul import (
    get_agent_soul_metadata,
    get_context_agent_soul_metadata,
    has_canonical_agent_soul,
)

if TYPE_CHECKING:
    from src.agent.risk_override import RiskGateResult, RiskOverrideApplication


_BULLISH_SIGNALS = {"strong_buy", "buy"}
_RISK_AGENT_NAMES = {"risk"}


@dataclass(frozen=True)
class BaseAgentOpinionFact:
    """Prompt-safe projection of one independently executed upstream opinion."""

    agent: str
    signal: str
    confidence: float


@dataclass(frozen=True)
class RiskEvidenceFact:
    """Bounded facts needed to re-evaluate the final action at later exits."""

    signal: str = "hold"
    confidence: float = 0.0
    risk_level: Optional[str] = None
    veto_buy: bool = False
    signal_adjustment: Optional[str] = None
    flags: Tuple[Tuple[str, str, str], ...] = ()
    portfolio_exposure: Optional[float] = None
    volatility: Optional[float] = None
    historical_outcomes: Optional[str] = None
    current_holdings: Optional[str] = None
    as_of: Optional[str] = None


class DegradationBoundary(str, Enum):
    """Whether an incomplete stage failed or never started."""

    DURING_STAGE = "during_stage"
    BEFORE_STAGE = "before_stage"


@dataclass(frozen=True)
class DegradedEvent:
    """Low-sensitivity fact for a stage that did not complete normally."""

    stage: str
    reason: StageFailureReason
    boundary: DegradationBoundary

    def __post_init__(self) -> None:
        """Normalize and validate the stage, reason, and boundary values."""
        normalized_stage = str(self.stage or "").strip()
        if not normalized_stage:
            raise ValueError("degraded event requires a stage")
        object.__setattr__(self, "stage", normalized_stage)
        object.__setattr__(self, "reason", normalize_stage_failure_reason(self.reason))
        object.__setattr__(self, "boundary", DegradationBoundary(self.boundary))


@dataclass(frozen=True)
class PipelineTerminationFact:
    """Pipeline deadline fact with the latest completed stage, when any."""

    reason: StageFailureReason
    last_completed_stage: Optional[str] = None

    def __post_init__(self) -> None:
        """Normalize the stage and enforce timeout-only termination facts."""
        normalized_reason = normalize_stage_failure_reason(self.reason)
        if normalized_reason != StageFailureReason.TIMEOUT:
            raise ValueError("pipeline termination currently supports timeout only")
        normalized_stage = str(self.last_completed_stage or "").strip() or None
        object.__setattr__(self, "reason", normalized_reason)
        object.__setattr__(self, "last_completed_stage", normalized_stage)


@dataclass(frozen=True)
class AgentRuntimeFacts:
    """Immutable internal snapshot carried by ``AgentResult``."""

    base_agent_opinions: Tuple[BaseAgentOpinionFact, ...] = ()
    degraded_events: Tuple[DegradedEvent, ...] = ()
    pipeline_termination: Optional[PipelineTerminationFact] = None
    risk_override_application: Optional[RiskOverrideApplication] = None
    risk_gate_result: Optional[RiskGateResult] = None
    risk_evidence: Optional[RiskEvidenceFact] = None

    @property
    def soul_version(self) -> Optional[str]:
        """Return the module-owned Soul version after verified composition."""
        return project_agent_runtime_metadata(self).get("soul_version")

    @property
    def soul_hash(self) -> Optional[str]:
        """Return the module-owned Soul hash after verified composition."""
        return project_agent_runtime_metadata(self).get("soul_hash")

    def to_metadata(self) -> dict[str, str]:
        """Project the stable run identity without exposing model reasoning."""
        return project_agent_runtime_metadata(self)


@dataclass(frozen=True)
class _VerifiedAgentRuntimeFacts(AgentRuntimeFacts):
    """Module-owned facts type proving canonical Soul composition."""


def project_agent_runtime_metadata(facts: Any) -> dict[str, str]:
    """Project identity only from the exact module-owned verified facts type."""
    if type(facts) is not _VerifiedAgentRuntimeFacts:
        return {}
    return get_agent_soul_metadata()


def build_agent_soul_runtime_facts(system_prompt: str) -> AgentRuntimeFacts:
    """Build identity facts after the canonical Soul composer ran."""
    if not has_canonical_agent_soul(system_prompt):
        raise ValueError("Agent Soul runtime facts require the canonical composed prompt")
    return _VerifiedAgentRuntimeFacts()


def inherit_agent_soul_runtime_facts(facts: Any) -> Optional[AgentRuntimeFacts]:
    """Copy only a module-verified Soul identity into a new result snapshot."""
    if type(facts) is not _VerifiedAgentRuntimeFacts:
        return None
    return _VerifiedAgentRuntimeFacts(
        base_agent_opinions=facts.base_agent_opinions,
        degraded_events=facts.degraded_events,
        pipeline_termination=facts.pipeline_termination,
        risk_override_application=facts.risk_override_application,
        risk_gate_result=facts.risk_gate_result,
        risk_evidence=facts.risk_evidence,
    )


def build_agent_runtime_facts(ctx: AgentContext) -> AgentRuntimeFacts:
    """Build a validated low-sensitivity snapshot from an Agent context."""
    facts_type = (
        _VerifiedAgentRuntimeFacts
        if get_context_agent_soul_metadata(ctx) is not None
        else AgentRuntimeFacts
    )
    return facts_type(
        base_agent_opinions=tuple(_iter_base_agent_opinions(ctx)),
        degraded_events=tuple(_iter_degraded_events(ctx)),
        pipeline_termination=_pipeline_termination(ctx),
        risk_override_application=_risk_override_application(ctx),
        risk_gate_result=_risk_gate_result(ctx),
        risk_evidence=_risk_evidence(ctx),
    )


def attach_risk_gate_result(
    facts: Any,
    result: RiskGateResult,
    *,
    evidence: Optional[RiskEvidenceFact] = None,
) -> AgentRuntimeFacts:
    """Return immutable runtime facts carrying the canonical gate result."""
    if isinstance(facts, AgentRuntimeFacts):
        return replace(
            facts,
            risk_gate_result=result,
            risk_evidence=evidence if evidence is not None else facts.risk_evidence,
        )
    return AgentRuntimeFacts(risk_gate_result=result, risk_evidence=evidence)


def _iter_base_agent_opinions(ctx: AgentContext):
    """Yield low-sensitivity facts for independently executed opinions."""
    for opinion in ctx.opinions:
        if not _is_base_agent_opinion(opinion):
            continue
        yield BaseAgentOpinionFact(
            agent=str(opinion.agent_name or "unknown"),
            signal=_effective_signal(opinion.agent_name, opinion.signal),
            confidence=_safe_confidence(opinion.confidence),
        )


def _is_base_agent_opinion(opinion: AgentOpinion) -> bool:
    """Exclude the final decision and synthesized consensus opinions."""
    from src.agent.skills.defaults import is_skill_consensus_name

    agent_name = str(opinion.agent_name or "").strip().lower()
    return agent_name != "decision" and not is_skill_consensus_name(agent_name)


def _iter_degraded_events(ctx: AgentContext):
    """Yield valid, deduplicated degradation events from runtime metadata."""
    source = ctx.meta.get("degraded_events")
    if not isinstance(source, list):
        return

    seen = set()
    for item in source:
        if isinstance(item, DegradedEvent):
            event = item
        elif isinstance(item, dict):
            try:
                event = DegradedEvent(
                    stage=item.get("stage", ""),
                    reason=item.get("reason", StageFailureReason.STAGE_FAILURE),
                    boundary=item.get("boundary", ""),
                )
            except (TypeError, ValueError):
                continue
        else:
            continue
        key = (event.stage, event.reason, event.boundary)
        if key in seen:
            continue
        seen.add(key)
        yield event


def _pipeline_termination(ctx: AgentContext) -> Optional[PipelineTerminationFact]:
    """Return the validated pipeline termination fact when one exists."""
    source = ctx.meta.get("pipeline_termination")
    if isinstance(source, PipelineTerminationFact):
        return source
    if not isinstance(source, dict):
        return None
    try:
        return PipelineTerminationFact(
            reason=source.get("reason", ""),
            last_completed_stage=source.get("last_completed_stage", ""),
        )
    except (TypeError, ValueError):
        return None


def _risk_override_application(ctx: AgentContext) -> Optional[RiskOverrideApplication]:
    """Return only a validated risk application stored by the orchestrator."""
    from src.agent.risk_override import RiskOverrideApplication

    application = ctx.meta.get("risk_override_application")
    return application if isinstance(application, RiskOverrideApplication) else None


def _risk_gate_result(ctx: AgentContext) -> Optional[RiskGateResult]:
    from src.agent.risk_override import RiskGateResult

    result = ctx.meta.get("risk_gate_result")
    return result if isinstance(result, RiskGateResult) else None


def _risk_evidence(ctx: AgentContext) -> Optional[RiskEvidenceFact]:
    risk_opinion = next(
        (opinion for opinion in reversed(ctx.opinions) if _is_risk_agent(opinion.agent_name)),
        None,
    )
    raw = risk_opinion.raw_data if risk_opinion and isinstance(risk_opinion.raw_data, dict) else {}
    flags = tuple(
        (
            str(flag.get("category") or flag.get("type") or "risk")[:64],
            str(flag.get("description") or "risk")[:200],
            str(flag.get("severity") or "medium")[:16],
        )
        for flag in ctx.risk_flags[:20]
        if isinstance(flag, dict)
    )
    if risk_opinion is None and not raw and not flags:
        return None
    return RiskEvidenceFact(
        signal=_effective_signal("risk", getattr(risk_opinion, "signal", "hold")),
        confidence=_safe_confidence(getattr(risk_opinion, "confidence", 0.0)),
        risk_level=_bounded_text(raw.get("risk_level"), 32),
        veto_buy=raw.get("veto_buy") is True,
        signal_adjustment=_bounded_text(raw.get("signal_adjustment"), 32),
        flags=flags,
        portfolio_exposure=_bounded_number(ctx.get_data("portfolio_exposure")),
        volatility=_bounded_number(ctx.get_data("volatility")),
        historical_outcomes=_bounded_json(ctx.get_data("historical_outcomes"), 500),
        current_holdings=_bounded_json(ctx.get_data("current_holdings"), 500),
        as_of=_bounded_text(ctx.get_data("risk_evidence_as_of"), 64),
    )


def _bounded_text(value: Any, maximum: int) -> Optional[str]:
    text = str(value or "").strip()
    return text[:maximum] or None


def _bounded_json(value: Any, maximum: int) -> Optional[str]:
    if value in (None, "", (), [], {}):
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text[:maximum] or None


def _bounded_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(parsed):
        return None
    return parsed if -1_000_000_000 <= parsed <= 1_000_000_000 else None


def _normalize_opinion_signal(signal: Any) -> str:
    """Normalize an opinion signal without exposing arbitrary model text."""
    if not isinstance(signal, str):
        return "hold"
    normalized = signal.strip().lower()
    if normalized in {"strong_buy", "buy", "hold", "sell", "strong_sell"}:
        return normalized
    return "hold"


def _effective_signal(agent_name: str, signal: Any) -> str:
    """Apply conservative signal semantics to one base-agent opinion."""
    normalized = _normalize_opinion_signal(signal)
    if _is_risk_agent(agent_name) and normalized in _BULLISH_SIGNALS:
        return "hold"
    return normalized


def _is_risk_agent(agent_name: str) -> bool:
    """Return whether the normalized name identifies the risk agent."""
    return str(agent_name or "").strip().lower() in _RISK_AGENT_NAMES


def _safe_confidence(confidence: Any) -> float:
    """Clamp a confidence value to a two-decimal probability."""
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        value = 0.0
    if not isfinite(value):
        value = 0.0
    return round(max(0.0, min(1.0, value)), 2)


__all__ = [
    "AgentRuntimeFacts",
    "BaseAgentOpinionFact",
    "DegradationBoundary",
    "DegradedEvent",
    "PipelineTerminationFact",
    "RiskEvidenceFact",
    "build_agent_runtime_facts",
    "attach_risk_gate_result",
    "build_agent_soul_runtime_facts",
    "inherit_agent_soul_runtime_facts",
    "project_agent_runtime_metadata",
]
