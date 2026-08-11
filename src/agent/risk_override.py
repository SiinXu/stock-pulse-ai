# -*- coding: utf-8 -*-
"""Shared risk override planning and mandatory Risk Manager gate.

The historical ``build_risk_override_plan`` / ``build_risk_override_application``
helpers remain the single source of truth for force-downgrade transitions. This
module also exposes a mandatory **Risk Manager gate** that every decision exit
must invoke before a final buy/hold/sell recommendation is published.

Gate outcomes are deterministic and never LLM-backed: ``pass``, ``downgrade``,
or ``reject``. ``RISK_GATE_PROFILE`` selects conservative, balanced, or
aggressive thresholds, but cannot disable evaluation. Gate failures fail closed
and never publish an unevaluated bullish action.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import isfinite
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.agent.protocols import AgentContext, AgentOpinion, normalize_decision_signal

logger = logging.getLogger(__name__)

_DOWNGRADE_STEPS = {
    "downgrade_one": 1,
    "downgrade_two": 2,
}

# Decision-exit identifiers (every exit must call the gate; missing one is incomplete).
EXIT_ORCHESTRATOR_MULTI_AGENT = "orchestrator_multi_agent"
EXIT_SINGLE_AGENT = "single_agent"
EXIT_COMMITTEE_MODE = "committee_mode"
EXIT_DELIBERATION_PROJECTION = "deliberation_projection"
EXIT_AGENT_CHAT = "agent_chat"

META_RISK_GATE_RESULT = "risk_gate_result"
DATA_RISK_GATE_APPLIED = "risk_gate_applied"

_HIGH_CONFIDENCE_THRESHOLD = 0.75
_BULLISH_DASHBOARD = frozenset({"buy"})
_BEARISH_RISK_SIGNALS = frozenset({"sell", "strong_sell"})
_MAX_GATE_CODES = 20
_MAX_GATE_PARAMS = 20
_MAX_GATE_TEXT = 200
_STABLE_GATE_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class DashboardDecisionSignal(str, Enum):
    """Canonical signals used while applying Agent risk controls."""

    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"


class RiskTrigger(str, Enum):
    """Normalized trigger selected for one risk-control evaluation."""

    NONE = "none"
    RISK_VETO = "risk_veto"
    RISK_DOWNGRADE = "risk_downgrade"


class RiskApplicationReason(str, Enum):
    """Exhaustive internal outcomes of evaluating a risk override."""

    NO_RISK_EVIDENCE = "no_risk_evidence"
    NO_OVERRIDE_TRIGGER = "no_override_trigger"
    OVERRIDE_DISABLED = "override_disabled"
    POST_RISK_SIGNAL_ALREADY_WITHIN_RISK_LIMIT = (
        "post_risk_signal_already_within_risk_limit"
    )
    RISK_VETO_APPLIED = "risk_veto_applied"
    RISK_DOWNGRADE_APPLIED = "risk_downgrade_applied"
    RISK_CONTROL_BYPASS_APPROVED = "risk_control_bypass_approved"


_APPLIED_REASONS = frozenset({
    RiskApplicationReason.RISK_VETO_APPLIED,
    RiskApplicationReason.RISK_DOWNGRADE_APPLIED,
})
_VALID_DOWNGRADE_TRANSITIONS = frozenset({
    (DashboardDecisionSignal.BUY, DashboardDecisionSignal.HOLD),
    (DashboardDecisionSignal.BUY, DashboardDecisionSignal.SELL),
    (DashboardDecisionSignal.HOLD, DashboardDecisionSignal.SELL),
})


def classify_risk_application_reason(
    *,
    evidence_present: bool,
    trigger: RiskTrigger,
    override_enabled: bool,
    applied: bool,
    bypassed: bool = False,
) -> RiskApplicationReason:
    """Classify one application from normalized runtime facts."""
    trigger = RiskTrigger(trigger)
    if not evidence_present:
        return RiskApplicationReason.NO_RISK_EVIDENCE
    if trigger == RiskTrigger.NONE:
        return RiskApplicationReason.NO_OVERRIDE_TRIGGER
    if not override_enabled:
        return RiskApplicationReason.OVERRIDE_DISABLED
    if bypassed:
        return RiskApplicationReason.RISK_CONTROL_BYPASS_APPROVED
    if not applied:
        return RiskApplicationReason.POST_RISK_SIGNAL_ALREADY_WITHIN_RISK_LIMIT
    if trigger == RiskTrigger.RISK_VETO:
        return RiskApplicationReason.RISK_VETO_APPLIED
    return RiskApplicationReason.RISK_DOWNGRADE_APPLIED


def validate_risk_application_transition(
    *,
    applied: bool,
    reason: RiskApplicationReason,
    post_risk_signal: DashboardDecisionSignal,
    from_signal: Optional[DashboardDecisionSignal],
    to_signal: Optional[DashboardDecisionSignal],
    bypassed: bool = False,
    approval_id: Optional[str] = None,
) -> None:
    """Reject internally contradictory application records."""
    reason = RiskApplicationReason(reason)
    post_risk_signal = DashboardDecisionSignal(post_risk_signal)
    from_signal = DashboardDecisionSignal(from_signal) if from_signal is not None else None
    to_signal = DashboardDecisionSignal(to_signal) if to_signal is not None else None

    if bypassed:
        if applied or from_signal is not None or to_signal is not None:
            raise ValueError("approved risk bypass cannot carry an override transition")
        if reason is not RiskApplicationReason.RISK_CONTROL_BYPASS_APPROVED:
            raise ValueError("approved risk bypass requires its stable reason")
        if not isinstance(approval_id, str) or len(approval_id) != 32:
            raise ValueError("approved risk bypass requires a bounded approval id")
        return
    if approval_id is not None:
        raise ValueError("non-bypassed risk application cannot carry an approval id")

    if not applied:
        if from_signal is not None or to_signal is not None:
            raise ValueError("non-applied risk override cannot carry a signal transition")
        if reason in _APPLIED_REASONS:
            raise ValueError("applied reason requires applied=True")
        return

    if from_signal is None or to_signal is None:
        raise ValueError("applied risk override requires from_signal and to_signal")
    if from_signal == to_signal:
        raise ValueError("applied risk override must change the signal")
    if to_signal != post_risk_signal:
        raise ValueError("to_signal must match post_risk_signal")
    if reason == RiskApplicationReason.RISK_VETO_APPLIED:
        if (from_signal, to_signal) != (
            DashboardDecisionSignal.BUY,
            DashboardDecisionSignal.HOLD,
        ):
            raise ValueError("risk veto application must change buy to hold")
    elif reason == RiskApplicationReason.RISK_DOWNGRADE_APPLIED:
        if (from_signal, to_signal) not in _VALID_DOWNGRADE_TRANSITIONS:
            raise ValueError("risk downgrade must move to a more conservative signal")
    else:
        raise ValueError("applied risk override requires an applied reason")


@dataclass(frozen=True)
class RiskOverridePlan:
    """Configuration-aware risk override decision shared by summary and executor."""

    evidence_present: bool
    override_enabled: bool
    override_trigger_present: bool
    veto_buy: bool
    adjustment: str
    has_high_flag: bool
    risk_level_high: bool
    current_signal: Optional[str]
    target_signal: Optional[str]
    will_apply: Optional[bool]
    reason: str

    @property
    def trigger(self) -> RiskTrigger:
        """Return the effective trigger using execution precedence."""
        if self.veto_buy and self.current_signal == DashboardDecisionSignal.BUY:
            return RiskTrigger.RISK_VETO
        if self.adjustment in _DOWNGRADE_STEPS:
            return RiskTrigger.RISK_DOWNGRADE
        if self.veto_buy:
            return RiskTrigger.RISK_VETO
        return RiskTrigger.NONE

    def to_low_sensitivity_dict(self) -> Dict[str, Any]:
        """Return a prompt-safe view that does not expose raw risk payloads."""
        return {
            "evidence_present": self.evidence_present,
            "override_enabled": self.override_enabled,
            "override_trigger_present": self.override_trigger_present,
            "veto_buy": self.veto_buy,
            "will_apply": self.will_apply,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RiskOverrideApplication:
    """Validated low-sensitivity result of a risk-control evaluation."""

    evidence_present: bool
    override_enabled: bool
    trigger: RiskTrigger
    applied: bool
    reason: RiskApplicationReason
    post_risk_signal: DashboardDecisionSignal
    from_signal: Optional[DashboardDecisionSignal] = None
    to_signal: Optional[DashboardDecisionSignal] = None
    bypassed: bool = False
    approval_id: Optional[str] = None

    def __post_init__(self) -> None:
        """Normalize enum values and reject contradictory application facts."""
        object.__setattr__(self, "trigger", RiskTrigger(self.trigger))
        object.__setattr__(self, "reason", RiskApplicationReason(self.reason))
        object.__setattr__(
            self,
            "post_risk_signal",
            DashboardDecisionSignal(self.post_risk_signal),
        )
        if self.from_signal is not None:
            object.__setattr__(self, "from_signal", DashboardDecisionSignal(self.from_signal))
        if self.to_signal is not None:
            object.__setattr__(self, "to_signal", DashboardDecisionSignal(self.to_signal))

        if not self.evidence_present and self.trigger != RiskTrigger.NONE:
            raise ValueError("risk trigger requires risk evidence")
        expected_reason = classify_risk_application_reason(
            evidence_present=self.evidence_present,
            trigger=self.trigger,
            override_enabled=self.override_enabled,
            applied=self.applied,
            bypassed=self.bypassed,
        )
        if self.reason != expected_reason:
            raise ValueError(
                f"risk application reason must be {expected_reason.value} for the supplied facts"
            )
        validate_risk_application_transition(
            applied=self.applied,
            reason=self.reason,
            post_risk_signal=self.post_risk_signal,
            from_signal=self.from_signal,
            to_signal=self.to_signal,
            bypassed=self.bypassed,
            approval_id=self.approval_id,
        )


def build_risk_override_application(plan: RiskOverridePlan) -> RiskOverrideApplication:
    """Build the actual outcome for a plan evaluated against a dashboard signal."""
    if plan.current_signal is None or plan.target_signal is None or plan.will_apply is None:
        raise ValueError("risk override application requires an evaluated current signal")

    current_signal = DashboardDecisionSignal(plan.current_signal)
    target_signal = DashboardDecisionSignal(plan.target_signal)
    reason = classify_risk_application_reason(
        evidence_present=plan.evidence_present,
        trigger=plan.trigger,
        override_enabled=plan.override_enabled,
        applied=plan.will_apply,
    )
    if plan.will_apply:
        return RiskOverrideApplication(
            evidence_present=plan.evidence_present,
            override_enabled=plan.override_enabled,
            trigger=plan.trigger,
            applied=True,
            reason=reason,
            post_risk_signal=target_signal,
            from_signal=current_signal,
            to_signal=target_signal,
        )
    return RiskOverrideApplication(
        evidence_present=plan.evidence_present,
        override_enabled=plan.override_enabled,
        trigger=plan.trigger,
        applied=False,
        reason=reason,
        post_risk_signal=current_signal,
    )


def build_approved_risk_bypass_application(
    plan: RiskOverridePlan,
    *,
    approval_id: str,
) -> RiskOverrideApplication:
    """Represent an approved one-shot bypass without a contradictory transition."""
    if (
        plan.current_signal is None
        or plan.will_apply is not True
        or plan.trigger is RiskTrigger.NONE
    ):
        raise ValueError("approved risk bypass requires an applicable risk override")
    current_signal = DashboardDecisionSignal(plan.current_signal)
    return RiskOverrideApplication(
        evidence_present=plan.evidence_present,
        override_enabled=plan.override_enabled,
        trigger=plan.trigger,
        applied=False,
        reason=RiskApplicationReason.RISK_CONTROL_BYPASS_APPROVED,
        post_risk_signal=current_signal,
        bypassed=True,
        approval_id=approval_id,
    )


def build_risk_application_from_gate(
    result: RiskGateResult,
    *,
    veto_buy: bool = False,
) -> RiskOverrideApplication:
    """Project the canonical final action into the legacy application contract."""
    original = DashboardDecisionSignal(result.original_action)
    final = DashboardDecisionSignal(result.final_action)
    evidence_present = bool(result.evidence_codes)
    if original == final:
        trigger = RiskTrigger.RISK_VETO if veto_buy else RiskTrigger.NONE
        return RiskOverrideApplication(
            evidence_present=evidence_present,
            override_enabled=True,
            trigger=trigger,
            applied=False,
            reason=classify_risk_application_reason(
                evidence_present=evidence_present,
                trigger=trigger,
                override_enabled=True,
                applied=False,
            ),
            post_risk_signal=final,
        )
    trigger = (
        RiskTrigger.RISK_VETO
        if veto_buy and original is DashboardDecisionSignal.BUY and final is DashboardDecisionSignal.HOLD
        else RiskTrigger.RISK_DOWNGRADE
    )
    reason = (
        RiskApplicationReason.RISK_VETO_APPLIED
        if trigger is RiskTrigger.RISK_VETO
        else RiskApplicationReason.RISK_DOWNGRADE_APPLIED
    )
    return RiskOverrideApplication(
        evidence_present=True,
        override_enabled=True,
        trigger=trigger,
        applied=True,
        reason=reason,
        post_risk_signal=final,
        from_signal=original,
        to_signal=final,
    )


def build_approved_risk_application_from_gate(
    result: RiskGateResult,
    *,
    approval_id: str,
    veto_buy: bool = False,
) -> RiskOverrideApplication:
    """Represent an authorized bypass of any conservative gate verdict."""
    if result.verdict not in {RiskGateOutcome.DOWNGRADE, RiskGateOutcome.REJECT}:
        raise ValueError("approved risk bypass requires a conservative gate verdict")
    trigger = RiskTrigger.RISK_VETO if veto_buy else RiskTrigger.RISK_DOWNGRADE
    return RiskOverrideApplication(
        evidence_present=True,
        override_enabled=True,
        trigger=trigger,
        applied=False,
        reason=RiskApplicationReason.RISK_CONTROL_BYPASS_APPROVED,
        post_risk_signal=DashboardDecisionSignal(result.original_action),
        bypassed=True,
        approval_id=approval_id,
    )


def build_risk_override_plan(
    ctx: AgentContext,
    *,
    current_signal: Any = None,
    override_enabled: bool = True,
) -> RiskOverridePlan:
    """Build the single source of truth for risk override decisions.

    ``risk_level=high`` is risk evidence, but it is not by itself an override
    trigger. Actual execution also depends on ``override_enabled`` and on the
    final dashboard signal.
    """
    risk_raw = _latest_risk_raw(ctx)
    adjustment = str(risk_raw.get("signal_adjustment") or "").strip().lower()
    has_high_flag = any(
        str(flag.get("severity", "")).strip().lower() == "high"
        for flag in ctx.risk_flags
        if isinstance(flag, dict)
    )
    risk_level_high = str(risk_raw.get("risk_level") or "").strip().lower() == "high"
    veto_buy = bool(risk_raw.get("veto_buy")) or adjustment == "veto" or has_high_flag
    has_downgrade = adjustment in _DOWNGRADE_STEPS
    override_trigger_present = veto_buy or has_downgrade
    evidence_present = override_trigger_present or risk_level_high

    normalized_current = (
        normalize_decision_signal(current_signal)
        if isinstance(current_signal, str)
        else None
    )
    target_signal = normalized_current
    will_apply: Optional[bool]

    if normalized_current is None:
        will_apply = None
    elif not override_enabled or not override_trigger_present:
        will_apply = False
    else:
        if veto_buy and normalized_current == "buy":
            target_signal = "hold"
        elif has_downgrade:
            target_signal = _downgrade_signal(
                normalized_current,
                steps=_DOWNGRADE_STEPS[adjustment],
            )
        will_apply = target_signal != normalized_current

    return RiskOverridePlan(
        evidence_present=evidence_present,
        override_enabled=bool(override_enabled),
        override_trigger_present=override_trigger_present,
        veto_buy=veto_buy,
        adjustment=adjustment,
        has_high_flag=has_high_flag,
        risk_level_high=risk_level_high,
        current_signal=normalized_current,
        target_signal=target_signal,
        will_apply=will_apply,
        reason=_risk_override_reason(
            veto_buy=veto_buy,
            adjustment=adjustment,
            has_high_flag=has_high_flag,
            risk_level_high=risk_level_high,
        ),
    )


def _latest_risk_raw(ctx: AgentContext) -> Dict[str, Any]:
    risk_opinion = next((op for op in reversed(ctx.opinions) if op.agent_name == "risk"), None)
    if risk_opinion and isinstance(risk_opinion.raw_data, dict):
        return risk_opinion.raw_data
    return {}


def build_risk_context_for_exit(
    *,
    stock_code: str,
    current_signal: Any,
    dashboard: Optional[Mapping[str, Any]] = None,
    runtime_facts: Any = None,
) -> AgentContext:
    """Project real dashboard/runtime evidence into one final-action context."""
    ctx = AgentContext(query="", stock_code=str(stock_code or "")[:32])
    signal = normalize_decision_signal(current_signal)
    ctx.add_opinion(AgentOpinion(
        agent_name="decision",
        signal=signal,
        confidence=_bounded_confidence(
            (dashboard or {}).get("confidence") if dashboard else None
        ),
    ))

    evidence = getattr(runtime_facts, "risk_evidence", None)
    raw: Dict[str, Any] = {}
    risk_signal = "hold"
    risk_confidence = 0.0
    invalid_evidence = False
    evidence_as_of: Optional[str] = None

    def absorb_raw(source: Mapping[str, Any]) -> None:
        nonlocal invalid_evidence
        risk_level = source.get("risk_level")
        if risk_level not in (None, ""):
            normalized_level = str(risk_level).strip().lower()
            if normalized_level in {"low", "medium", "high"}:
                raw["risk_level"] = normalized_level
            else:
                invalid_evidence = True
        veto = source.get("veto_buy")
        if veto not in (None, ""):
            if type(veto) is bool:
                raw["veto_buy"] = veto
            else:
                invalid_evidence = True
        adjustment = source.get("signal_adjustment")
        if adjustment not in (None, ""):
            normalized_adjustment = str(adjustment).strip().lower()
            if normalized_adjustment in {*_DOWNGRADE_STEPS, "veto"}:
                raw["signal_adjustment"] = normalized_adjustment
            else:
                invalid_evidence = True

    if evidence is not None:
        absorb_raw({
            "risk_level": getattr(evidence, "risk_level", None),
            "veto_buy": getattr(evidence, "veto_buy", False),
            "signal_adjustment": getattr(evidence, "signal_adjustment", None),
        })
        risk_signal = str(getattr(evidence, "signal", "hold") or "hold")
        if risk_signal.strip().lower() not in {
            "strong_buy",
            "buy",
            "hold",
            "sell",
            "strong_sell",
        }:
            invalid_evidence = True
            risk_signal = "hold"
        risk_confidence = _bounded_confidence(
            getattr(evidence, "confidence", 0.0)
        )
        evidence_as_of = str(getattr(evidence, "as_of", "") or "").strip() or None
        for flag in getattr(evidence, "flags", ()) or ():
            if isinstance(flag, tuple) and len(flag) == 3:
                ctx.add_risk_flag(flag[0], flag[1], severity=flag[2])
        if getattr(evidence, "invalid_fields", ()):
            invalid_evidence = True
        for key in (
            "portfolio_exposure",
            "volatility",
            "historical_outcomes",
            "current_holdings",
        ):
            value = getattr(evidence, key, None)
            if value not in (None, "", (), [], {}):
                ctx.set_data(key, value)

    for source in _dashboard_risk_sources(dashboard):
        absorb_raw(source)
        for key in (
            "portfolio_exposure",
            "volatility",
            "historical_outcomes",
            "current_holdings",
        ):
            if key in source and key not in ctx.data:
                ctx.set_data(key, source[key])
        risk_signal = str(source.get("risk_signal") or source.get("signal") or risk_signal)
        risk_confidence = _bounded_confidence(
            source.get("risk_confidence", source.get("confidence", risk_confidence))
        )
        flags = source.get("risk_flags")
        if isinstance(flags, list):
            for flag in flags:
                if isinstance(flag, Mapping):
                    ctx.add_risk_flag(
                        str(
                            flag.get("category")
                            or flag.get("type")
                            or flag.get("flag_type")
                            or "risk"
                        ),
                        str(flag.get("description") or flag.get("message") or "risk"),
                        severity=str(flag.get("severity") or "medium"),
                    )

        source_as_of = str(
            source.get("as_of") or source.get("risk_evidence_as_of") or ""
        ).strip()
        if source_as_of:
            evidence_as_of = source_as_of

    if invalid_evidence:
        ctx.set_data("risk_evidence_invalid", True)
    if evidence_as_of:
        ctx.set_data("risk_evidence_as_of", evidence_as_of)
        try:
            if _is_stale_risk_evidence(evidence_as_of):
                ctx.set_data("risk_evidence_stale", True)
        except ValueError:
            ctx.set_data("risk_evidence_invalid", True)

    if raw or risk_signal not in {"", "hold"}:
        ctx.add_opinion(AgentOpinion(
            agent_name="risk",
            signal=risk_signal,
            confidence=risk_confidence,
            raw_data=raw,
        ))
    return ctx


def _is_stale_risk_evidence(value: str, *, maximum_age_hours: int = 24) -> bool:
    """Return whether a valid risk-evidence timestamp is older than the limit."""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - parsed.astimezone(timezone.utc) > timedelta(
        hours=maximum_age_hours
    )


def _dashboard_risk_sources(
    dashboard: Optional[Mapping[str, Any]],
) -> Tuple[Mapping[str, Any], ...]:
    if not isinstance(dashboard, Mapping):
        return ()
    sources: List[Mapping[str, Any]] = [dashboard]
    for key in ("risk", "risk_assessment", "risk_manager_input"):
        value = dashboard.get(key)
        if isinstance(value, Mapping):
            sources.append(value)
    nested = dashboard.get("dashboard")
    if isinstance(nested, Mapping):
        sources.append(nested)
        for key in ("risk", "risk_assessment", "risk_manager_input"):
            value = nested.get(key)
            if isinstance(value, Mapping):
                sources.append(value)
    return tuple(sources)


def _bounded_confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not isfinite(parsed):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _risk_override_reason(
    *,
    veto_buy: bool,
    adjustment: str,
    has_high_flag: bool,
    risk_level_high: bool,
) -> str:
    if has_high_flag:
        return "high_severity_flag"
    if veto_buy:
        return "risk_veto"
    if adjustment in _DOWNGRADE_STEPS:
        return adjustment
    if risk_level_high:
        return "high_risk_evidence"
    return "none"


def _downgrade_signal(signal: str, steps: int = 1) -> str:
    order = ["buy", "hold", "sell"]
    try:
        index = order.index(signal)
    except ValueError:
        return signal
    return order[min(len(order) - 1, index + max(0, steps))]


# ---------------------------------------------------------------------------
# Mandatory Risk Manager gate
# ---------------------------------------------------------------------------


class RiskGateOutcome(str, Enum):
    """Deterministic outcomes of the mandatory Risk Manager gate."""

    PASS = "pass"
    DOWNGRADE = "downgrade"
    REJECT = "reject"
    # Compatibility-only enum member for pre-adoption callers. New evaluation
    # never emits it; the canonical verdict set is pass/downgrade/reject.
    ATTACH_WARNING = "attach_warning"


class RiskGateProfile(str, Enum):
    """Risk thresholds applied by the final-action authority."""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


_PORTFOLIO_RISK_THRESHOLDS: Dict[RiskGateProfile, Dict[str, float]] = {
    RiskGateProfile.CONSERVATIVE: {
        "portfolio_exposure": 0.70,
        "volatility": 0.40,
        "historical_loss_rate": 0.50,
    },
    RiskGateProfile.BALANCED: {
        "portfolio_exposure": 0.80,
        "volatility": 0.60,
        "historical_loss_rate": 0.65,
    },
    RiskGateProfile.AGGRESSIVE: {
        "portfolio_exposure": 0.90,
        "volatility": 0.75,
        "historical_loss_rate": 0.80,
    },
}


@dataclass(frozen=True)
class RiskGateResult:
    """Traceable result of one Risk Manager gate evaluation.

    Always retains a final signal — the gate never empties or nulls a
    recommendation. ``fail_safe=True`` is the compatibility storage name for a
    fail-closed internal error.
    """

    outcome: RiskGateOutcome
    original_signal: str
    final_signal: str
    reasons: Tuple[str, ...]
    warnings: Tuple[str, ...]
    evidence_codes: Tuple[str, ...]
    enabled: bool
    strict: bool
    override_enabled: bool
    override_would_apply: bool
    exit_id: str
    profile: RiskGateProfile = RiskGateProfile.BALANCED
    evaluation_id: str = ""
    evaluated_at: str = ""
    authorized_bypass_id: Optional[str] = None
    adjustment: Optional[str] = None
    reason_params: Tuple[Tuple[str, str], ...] = ()
    evidence_provenance: Tuple[str, ...] = ()
    fail_safe: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", RiskGateOutcome(self.outcome))
        object.__setattr__(self, "profile", RiskGateProfile(self.profile))
        original = normalize_decision_signal(self.original_signal)
        final = normalize_decision_signal(self.final_signal)
        object.__setattr__(self, "original_signal", original)
        object.__setattr__(self, "final_signal", final)
        exit_id = str(self.exit_id or "").strip()
        if not exit_id:
            raise ValueError("risk gate result requires an exit_id")
        if len(exit_id) > 64:
            raise ValueError("risk gate exit id is too long")
        object.__setattr__(self, "exit_id", exit_id)
        for field_name in ("reasons", "evidence_codes", "evidence_provenance"):
            values = tuple(str(value or "").strip() for value in getattr(self, field_name))
            if len(values) > _MAX_GATE_CODES:
                raise ValueError(f"risk gate {field_name} exceeds {_MAX_GATE_CODES} items")
            if any(not _STABLE_GATE_KEY.fullmatch(value) for value in values):
                raise ValueError(f"risk gate {field_name} must contain stable bounded keys")
            object.__setattr__(self, field_name, values)
        warnings = tuple(str(value or "").strip() for value in self.warnings)
        if len(warnings) > _MAX_GATE_CODES or any(
            not value or len(value) > _MAX_GATE_TEXT for value in warnings
        ):
            raise ValueError("risk gate warnings must be bounded")
        object.__setattr__(self, "warnings", warnings)
        params = tuple(
            (str(key or "").strip(), str(value or "").strip())
            for key, value in self.reason_params
        )
        if len(params) > _MAX_GATE_PARAMS:
            raise ValueError(f"risk gate reason_params exceeds {_MAX_GATE_PARAMS} items")
        if any(
            not _STABLE_GATE_KEY.fullmatch(key) or len(value) > _MAX_GATE_TEXT
            for key, value in params
        ):
            raise ValueError("risk gate reason_params must be bounded")
        if len({key for key, _value in params}) != len(params):
            raise ValueError("risk gate reason_params keys must be unique")
        object.__setattr__(self, "reason_params", params)
        if self.adjustment is not None:
            adjustment = str(self.adjustment or "").strip()
            if not _STABLE_GATE_KEY.fullmatch(adjustment):
                raise ValueError("risk gate adjustment must be a stable bounded key")
            object.__setattr__(self, "adjustment", adjustment)
        evaluation_id = str(self.evaluation_id or "").strip() or uuid.uuid4().hex
        if len(evaluation_id) > 64:
            raise ValueError("risk gate evaluation id is too long")
        object.__setattr__(self, "evaluation_id", evaluation_id)
        evaluated_at = str(self.evaluated_at or "").strip() or datetime.now(
            timezone.utc
        ).isoformat()
        if len(evaluated_at) > 64:
            raise ValueError("risk gate evaluation timestamp is too long")
        object.__setattr__(self, "evaluated_at", evaluated_at)
        if self.outcome in {RiskGateOutcome.DOWNGRADE, RiskGateOutcome.REJECT}:
            if original == final and original == "buy":
                raise ValueError("conservative risk verdict must change a buy action")
        if self.authorized_bypass_id is not None:
            bypass_id = str(self.authorized_bypass_id).strip()
            if not bypass_id or len(bypass_id) > 64:
                raise ValueError("authorized bypass id must be bounded")
            object.__setattr__(self, "authorized_bypass_id", bypass_id)

    @property
    def verdict(self) -> RiskGateOutcome:
        """Canonical verdict alias used by persistence and renderers."""
        return self.outcome

    @property
    def original_action(self) -> str:
        return self.original_signal

    @property
    def final_action(self) -> str:
        return self.final_signal

    @property
    def fail_closed(self) -> bool:
        return self.fail_safe

    def to_trace_dict(self) -> Dict[str, Any]:
        """Low-sensitivity dict safe for traces / meta / T03 consumers."""
        return {
            "schema_version": "risk-manager-result/v1",
            "verdict": self.verdict.value,
            "original_action": self.original_action,
            "final_action": self.final_action,
            "reason_codes": list(self.reasons),
            "reason_params": dict(self.reason_params),
            "adjustment": self.adjustment,
            "evidence_codes": list(self.evidence_codes),
            "evidence_provenance": list(self.evidence_provenance),
            "profile": self.profile.value,
            "override_enabled": self.override_enabled,
            "override_would_apply": self.override_would_apply,
            "exit_id": self.exit_id,
            "evaluation_id": self.evaluation_id,
            "evaluated_at": self.evaluated_at,
            "authorized_bypass_id": self.authorized_bypass_id,
            "fail_closed": self.fail_closed,
        }


def resolve_risk_gate_flags(
    config: Any = None,
) -> Tuple[bool, RiskGateProfile, bool]:
    """Return mandatory-enabled, validated profile, and legacy override state."""
    if config is None:
        return True, RiskGateProfile.BALANCED, True
    config_values = vars(config)
    profile = RiskGateProfile(
        str(config_values.get("risk_gate_profile", "balanced") or "").strip().lower()
    )
    override_value = config_values.get("agent_risk_override", True)
    if type(override_value) is not bool:
        raise TypeError("agent_risk_override must be bool")
    return True, profile, override_value


def _collect_gate_evidence(
    ctx: AgentContext,
    *,
    current_signal: str,
    plan: RiskOverridePlan,
    profile: RiskGateProfile,
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Return stable ``(evidence_codes, reason_codes)`` from deterministic facts."""
    codes: List[str] = []
    reasons: List[str] = []

    if ctx.get_data("risk_evidence_invalid") is True:
        codes.append("invalid_risk_evidence")
        reasons.append("invalid_risk_evidence")
    if ctx.get_data("risk_evidence_stale") is True:
        codes.append("stale_risk_evidence")
        reasons.append("stale_risk_evidence")

    if plan.has_high_flag:
        codes.append("high_severity_flag")
        reasons.append("high_severity_flag")
    if plan.veto_buy:
        codes.append("risk_veto")
        reasons.append("risk_veto")
    if plan.adjustment in _DOWNGRADE_STEPS:
        codes.append("signal_downgrade_adjustment")
        reasons.append("signal_downgrade_adjustment")
    if plan.risk_level_high:
        codes.append("high_risk_evidence")
        reasons.append("high_risk_evidence")

    thresholds = _PORTFOLIO_RISK_THRESHOLDS[profile]
    exposure, exposure_invalid = _unit_interval_fact(ctx, "portfolio_exposure")
    volatility, volatility_invalid = _unit_interval_fact(ctx, "volatility")
    loss_rate, history_invalid = _historical_loss_rate(ctx)
    if exposure_invalid or volatility_invalid or history_invalid:
        codes.append("invalid_risk_evidence")
        reasons.append("invalid_risk_evidence")
    for value, threshold_key, code in (
        (exposure, "portfolio_exposure", "portfolio_exposure_limit"),
        (volatility, "volatility", "volatility_limit"),
        (loss_rate, "historical_loss_rate", "historical_loss_rate_limit"),
    ):
        if value is not None and value >= thresholds[threshold_key]:
            codes.append(code)
            reasons.append(code)

    risk_opinion = next(
        (op for op in reversed(ctx.opinions) if op.agent_name == "risk"),
        None,
    )
    # Do not treat "no risk agent opinion" as evidence by itself: quick/single
    # paths and replay fixtures often omit the risk specialist without that
    # meaning a mandatory warning on every buy.
    if risk_opinion is not None:
        risk_signal = str(risk_opinion.signal or "").strip().lower()
        if (
            current_signal in _BULLISH_DASHBOARD
            and risk_signal in _BEARISH_RISK_SIGNALS
        ):
            codes.append("evidence_conclusion_conflict")
            reasons.append("evidence_conclusion_conflict")
        conf = risk_opinion.confidence
        try:
            conf_value = float(conf)
        except (TypeError, ValueError):
            conf_value = 0.0
        if not isfinite(conf_value):
            conf_value = 0.0
        decision_conf = 0.0
        for opinion in reversed(ctx.opinions):
            if opinion.agent_name == "decision":
                try:
                    decision_conf = float(opinion.confidence)
                except (TypeError, ValueError):
                    decision_conf = 0.0
                if not isfinite(decision_conf):
                    decision_conf = 0.0
                break
        if (
            current_signal in _BULLISH_DASHBOARD
            and decision_conf >= _HIGH_CONFIDENCE_THRESHOLD
            and (
                plan.has_high_flag
                or plan.veto_buy
                or plan.risk_level_high
                or risk_signal in _BEARISH_RISK_SIGNALS
            )
        ):
            codes.append("confidence_risk_mismatch")
            reasons.append("confidence_risk_mismatch")

    # Stable unique order
    unique_codes: List[str] = []
    unique_reasons: List[str] = []
    for code, reason in zip(codes, reasons):
        if code not in unique_codes:
            unique_codes.append(code)
            unique_reasons.append(reason)
    return tuple(unique_codes), tuple(unique_reasons)


def _gate_reason_params(
    ctx: AgentContext,
    *,
    plan: RiskOverridePlan,
    profile: RiskGateProfile,
) -> Tuple[Tuple[str, str], ...]:
    """Return bounded diagnostic values separately from stable reason keys."""
    params: Dict[str, str] = {}
    if plan.adjustment:
        params["signal_adjustment"] = plan.adjustment
    risk_opinion = next(
        (op for op in reversed(ctx.opinions) if op.agent_name == "risk"),
        None,
    )
    if risk_opinion is not None:
        params["risk_signal"] = str(risk_opinion.signal or "")[:_MAX_GATE_TEXT]
    evidence_as_of = ctx.get_data("risk_evidence_as_of")
    if evidence_as_of not in (None, ""):
        params["risk_evidence_as_of"] = str(evidence_as_of)[:_MAX_GATE_TEXT]
    thresholds = _PORTFOLIO_RISK_THRESHOLDS[profile]
    exposure, exposure_invalid = _unit_interval_fact(ctx, "portfolio_exposure")
    volatility, volatility_invalid = _unit_interval_fact(ctx, "volatility")
    loss_rate, history_invalid = _historical_loss_rate(ctx)
    for key, value in (
        ("portfolio_exposure", exposure),
        ("volatility", volatility),
        ("historical_loss_rate", loss_rate),
    ):
        if value is not None:
            params[key] = _format_risk_ratio(value)
            params[f"{key}_threshold"] = _format_risk_ratio(thresholds[key])
    invalid_fields = []
    if exposure_invalid:
        invalid_fields.append("portfolio_exposure")
    if volatility_invalid:
        invalid_fields.append("volatility")
    if history_invalid:
        invalid_fields.append("historical_outcomes")
    if invalid_fields:
        params["invalid_fields"] = ",".join(invalid_fields)
    return tuple(params.items())


def _unit_interval_fact(
    ctx: AgentContext,
    key: str,
) -> Tuple[Optional[float], bool]:
    """Return one optional [0, 1] ratio and whether it was invalid."""
    value = ctx.get_data(key)
    if value in (None, ""):
        return None, False
    if isinstance(value, bool):
        return None, True
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None, True
    if not isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        return None, True
    return parsed, False


def _historical_loss_rate(ctx: AgentContext) -> Tuple[Optional[float], bool]:
    """Extract the optional bounded loss-rate ratio from historical outcomes."""
    source = ctx.get_data("historical_outcomes")
    if source in (None, "", (), [], {}):
        return None, False
    if isinstance(source, str):
        try:
            source = json.loads(source)
            if isinstance(source, str):
                source = json.loads(source)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, True
    if not isinstance(source, Mapping):
        return None, True
    if "loss_rate" not in source or source.get("loss_rate") in (None, ""):
        return None, False
    value = source.get("loss_rate")
    if isinstance(value, bool):
        return None, True
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None, True
    if not isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        return None, True
    return parsed, False


def _format_risk_ratio(value: float) -> str:
    """Render a deterministic bounded ratio for diagnostic parameters."""
    return f"{value:.4f}".rstrip("0").rstrip(".")


def evaluate_risk_manager_gate(
    ctx: AgentContext,
    *,
    current_signal: Any,
    exit_id: str,
    override_enabled: bool = True,
    gate_enabled: bool = True,
    gate_strict: bool = False,
    profile: RiskGateProfile | str = RiskGateProfile.BALANCED,
) -> RiskGateResult:
    """Evaluate the mandatory Risk Manager gate without mutating the context.

    Deterministic only — never calls an LLM. Always returns a non-empty final
    signal. Callers that mutate dashboards should use
    :func:`apply_risk_manager_gate`.
    """
    normalized = normalize_decision_signal(current_signal)
    exit_key = str(exit_id or "").strip() or "unknown"
    selected_profile = (
        RiskGateProfile.CONSERVATIVE
        if gate_strict
        else RiskGateProfile(profile)
    )

    if not gate_enabled:
        final = "hold" if normalized == "buy" else normalized
        return RiskGateResult(
            outcome=RiskGateOutcome.REJECT,
            original_signal=normalized,
            final_signal=final,
            reasons=("mandatory_gate_disable_rejected",),
            warnings=(),
            evidence_codes=("gate_configuration_invalid",),
            enabled=True,
            strict=selected_profile is RiskGateProfile.CONSERVATIVE,
            override_enabled=bool(override_enabled),
            override_would_apply=False,
            exit_id=exit_key,
            profile=selected_profile,
            adjustment=(
                f"{normalized}_to_{final}" if normalized != final else "publication_rejected"
            ),
            evidence_provenance=("configuration",),
            fail_safe=True,
        )

    active_plan = build_risk_override_plan(
        ctx,
        current_signal=normalized,
        override_enabled=bool(override_enabled),
    )
    force_plan = build_risk_override_plan(
        ctx,
        current_signal=normalized,
        override_enabled=True,
    )
    evidence_codes, reasons = _collect_gate_evidence(
        ctx,
        current_signal=normalized,
        plan=force_plan,
        profile=selected_profile,
    )
    reason_params = _gate_reason_params(
        ctx,
        plan=force_plan,
        profile=selected_profile,
    )
    override_would_apply = bool(force_plan.will_apply)

    if not evidence_codes:
        provenance = _gate_evidence_provenance(ctx)
        return RiskGateResult(
            outcome=RiskGateOutcome.PASS,
            original_signal=normalized,
            final_signal=normalized,
            reasons=("no_risk_evidence",),
            warnings=(),
            evidence_codes=(),
            enabled=True,
            strict=bool(gate_strict),
            override_enabled=bool(override_enabled),
            override_would_apply=False,
            exit_id=exit_key,
            profile=selected_profile,
            evidence_provenance=provenance,
            reason_params=reason_params,
        )

    explicit_block = any(
        code in evidence_codes
        for code in (
            "high_severity_flag",
            "risk_veto",
            "invalid_risk_evidence",
            "stale_risk_evidence",
            "portfolio_exposure_limit",
            "volatility_limit",
            "historical_loss_rate_limit",
        )
    )
    directional_conflict = any(
        code in evidence_codes
        for code in (
            "signal_downgrade_adjustment",
            "evidence_conclusion_conflict",
            "confidence_risk_mismatch",
        )
    )
    force_downgrade = bool(active_plan.will_apply)
    if normalized == "buy":
        if selected_profile is RiskGateProfile.CONSERVATIVE:
            force_downgrade = bool(evidence_codes)
        elif selected_profile is RiskGateProfile.BALANCED:
            force_downgrade = explicit_block or directional_conflict
        else:
            force_downgrade = explicit_block or bool(active_plan.will_apply)

    if force_downgrade:
        target = (
            force_plan.target_signal
            if force_plan.target_signal and force_plan.target_signal != normalized
            else "hold"
            if normalized == "buy"
            else normalized
        )
        target = normalize_decision_signal(target)
        if target == normalized and normalized == "buy":
            target = "hold"
        outcome = (
            RiskGateOutcome.REJECT
            if selected_profile is RiskGateProfile.CONSERVATIVE and explicit_block
            else RiskGateOutcome.DOWNGRADE
        )
        return RiskGateResult(
            outcome=outcome,
            original_signal=normalized,
            final_signal=target,
            reasons=reasons or ("risk_gate_force",),
            warnings=(),
            evidence_codes=evidence_codes,
            enabled=True,
            strict=selected_profile is RiskGateProfile.CONSERVATIVE,
            override_enabled=bool(override_enabled),
            override_would_apply=override_would_apply,
            exit_id=exit_key,
            profile=selected_profile,
            adjustment=f"{normalized}_to_{target}",
            reason_params=reason_params,
            evidence_provenance=_gate_evidence_provenance(ctx),
        )

    return RiskGateResult(
        outcome=RiskGateOutcome.PASS,
        original_signal=normalized,
        final_signal=normalized,
        reasons=reasons,
        warnings=(),
        evidence_codes=evidence_codes,
        enabled=True,
        strict=selected_profile is RiskGateProfile.CONSERVATIVE,
        override_enabled=bool(override_enabled),
        override_would_apply=override_would_apply,
        exit_id=exit_key,
        profile=selected_profile,
        reason_params=reason_params,
        evidence_provenance=_gate_evidence_provenance(ctx),
    )


def _gate_evidence_provenance(ctx: AgentContext) -> Tuple[str, ...]:
    sources: List[str] = []
    if any(op.agent_name == "risk" for op in ctx.opinions):
        sources.append("risk_agent_opinion")
    if ctx.risk_flags:
        sources.append("risk_flags")
    for key in (
        "portfolio_exposure",
        "volatility",
        "historical_outcomes",
        "current_holdings",
        "risk_evidence_as_of",
        "risk_evidence_invalid",
        "risk_evidence_stale",
    ):
        if ctx.get_data(key) not in (None, "", [], {}):
            sources.append(key)
    return tuple(sources)


def render_risk_gate_notice(
    result: RiskGateResult,
    report_language: str = "zh",
) -> str:
    """Render one localized summary from structured verdict facts."""
    language = str(report_language or "zh").strip().lower()
    if language == "en":
        labels = {
            RiskGateOutcome.PASS: "Risk Manager passed",
            RiskGateOutcome.DOWNGRADE: "Risk Manager downgraded",
            RiskGateOutcome.REJECT: "Risk Manager rejected",
        }
        text = labels.get(result.verdict, "Risk Manager reviewed")
        if result.authorized_bypass_id:
            return (
                "Risk Manager recommended a conservative action, but an authorized "
                f"one-shot bypass retained {result.final_action}."
            )
        return f"{text}: {result.original_action} -> {result.final_action}."
    if language == "ko":
        labels = {
            RiskGateOutcome.PASS: "리스크 매니저 승인",
            RiskGateOutcome.DOWNGRADE: "리스크 매니저 하향 조정",
            RiskGateOutcome.REJECT: "리스크 매니저 거부",
        }
        text = labels.get(result.verdict, "리스크 매니저 검토 완료")
        if result.authorized_bypass_id:
            return (
                "리스크 매니저는 보수적인 조치를 권고했지만, 일회성 승인을 통해 "
                f"{result.final_action} 결정을 유지했습니다."
            )
        return f"{text}: {result.original_action} -> {result.final_action}."
    labels = {
        RiskGateOutcome.PASS: "风控经理已通过",
        RiskGateOutcome.DOWNGRADE: "风控经理已下调",
        RiskGateOutcome.REJECT: "风控经理已拒绝",
    }
    text = labels.get(result.verdict, "风控经理已复核")
    if result.authorized_bypass_id:
        return f"风控经理建议保守处理，但经一次性授权保留 {result.final_action}。"
    return f"{text}：{result.original_action} -> {result.final_action}。"


def _merge_mandatory_warnings(existing: Any, warnings: Sequence[str]) -> str:
    parts: List[str] = []
    existing_text = str(existing or "").strip()
    if existing_text:
        parts.append(existing_text)
    for note in warnings:
        text = str(note or "").strip()
        if text and text not in parts and text not in existing_text:
            parts.append(text)
    return " ".join(parts).strip()


def _store_gate_result(ctx: AgentContext, result: RiskGateResult) -> None:
    ctx.meta[META_RISK_GATE_RESULT] = result
    ctx.set_data(DATA_RISK_GATE_APPLIED, result.to_trace_dict())


def apply_risk_manager_gate(
    ctx: AgentContext,
    *,
    current_signal: Any,
    exit_id: str,
    override_enabled: bool = True,
    gate_enabled: bool = True,
    gate_strict: bool = False,
    profile: RiskGateProfile | str = RiskGateProfile.BALANCED,
    dashboard: Optional[Dict[str, Any]] = None,
) -> RiskGateResult:
    """Evaluate the gate, record trace facts, and optionally annotate a dashboard.

    Never clears recommendations. On internal failure, records a fail-closed
    REJECT and replaces a bullish action with hold.
    """
    normalized = normalize_decision_signal(current_signal)
    exit_key = str(exit_id or "").strip() or "unknown"
    try:
        selected_profile = RiskGateProfile(profile)
    except (TypeError, ValueError):
        selected_profile = RiskGateProfile.BALANCED
    try:
        result = evaluate_risk_manager_gate(
            ctx,
            current_signal=normalized,
            exit_id=exit_key,
            override_enabled=override_enabled,
            gate_enabled=gate_enabled,
            gate_strict=gate_strict,
            profile=profile,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - publish conservatively
        logger.warning(
            "Risk Manager gate failed closed at exit=%s: %s",
            exit_key,
            type(exc).__name__,
        )
        final = "hold" if normalized == "buy" else normalized
        result = RiskGateResult(
            outcome=RiskGateOutcome.REJECT,
            original_signal=normalized,
            final_signal=final,
            reasons=("gate_internal_failure",),
            warnings=(),
            evidence_codes=("gate_internal_failure",),
            enabled=True,
            strict=selected_profile is RiskGateProfile.CONSERVATIVE,
            override_enabled=bool(override_enabled),
            override_would_apply=False,
            exit_id=exit_key,
            profile=selected_profile,
            adjustment=(
                f"{normalized}_to_{final}" if normalized != final else "publication_rejected"
            ),
            reason_params=(
                ("exception_type", type(exc).__name__),
                ("requested_profile", str(profile or "")[:_MAX_GATE_TEXT]),
            ),
            evidence_provenance=("gate_runtime",),
            fail_safe=True,
        )

    _store_gate_result(ctx, result)

    if isinstance(dashboard, dict):
        if result.outcome in {RiskGateOutcome.DOWNGRADE, RiskGateOutcome.REJECT}:
            dashboard["decision_type"] = result.final_signal
        dashboard["risk_manager"] = result.to_trace_dict()
        if result.outcome is not RiskGateOutcome.PASS or result.authorized_bypass_id:
            notice = render_risk_gate_notice(
                result,
                str(dashboard.get("report_language") or "zh"),
            )
            dashboard["risk_warning"] = _merge_mandatory_warnings(
                dashboard.get("risk_warning"),
                (notice,),
            )

    return result


def apply_risk_manager_gate_from_config(
    ctx: AgentContext,
    *,
    current_signal: Any,
    exit_id: str,
    config: Any = None,
    dashboard: Optional[Dict[str, Any]] = None,
) -> RiskGateResult:
    """Config-aware wrapper used by decision-exit insertion points."""
    gate_enabled, profile, override_enabled = resolve_risk_gate_flags(config)
    return apply_risk_manager_gate(
        ctx,
        current_signal=current_signal,
        exit_id=exit_id,
        override_enabled=override_enabled,
        gate_enabled=gate_enabled,
        profile=profile,
        dashboard=dashboard,
    )


def authorize_risk_gate_bypass(
    result: RiskGateResult,
    *,
    approval_id: str,
    approval_owner: Optional[str] = None,
    approved_at: Optional[str] = None,
) -> RiskGateResult:
    """Retain the original action under one explicit audited approval."""
    if result.verdict not in {RiskGateOutcome.DOWNGRADE, RiskGateOutcome.REJECT}:
        raise ValueError("risk bypass requires a conservative gate verdict")
    return RiskGateResult(
        outcome=RiskGateOutcome.PASS,
        original_signal=result.original_action,
        final_signal=result.original_action,
        reasons=(*result.reasons, "authorized_bypass_retained_original"),
        warnings=(),
        evidence_codes=result.evidence_codes,
        enabled=True,
        strict=result.strict,
        override_enabled=result.override_enabled,
        override_would_apply=result.override_would_apply,
        exit_id=result.exit_id,
        profile=result.profile,
        evaluation_id=result.evaluation_id,
        evaluated_at=result.evaluated_at,
        authorized_bypass_id=approval_id,
        adjustment="authorized_bypass_retained_original",
        reason_params=tuple(
            {
                **dict(result.reason_params),
                "approval_owner": str(approval_owner or "")[:64],
                "approved_at": str(approved_at or "")[:64],
            }.items()
        ),
        evidence_provenance=result.evidence_provenance,
    )


def get_risk_gate_result(ctx: AgentContext) -> Optional[RiskGateResult]:
    """Return the last stored gate result from context meta, if any."""
    value = ctx.meta.get(META_RISK_GATE_RESULT)
    return value if isinstance(value, RiskGateResult) else None


__all__ = [
    "DATA_RISK_GATE_APPLIED",
    "DashboardDecisionSignal",
    "EXIT_AGENT_CHAT",
    "EXIT_COMMITTEE_MODE",
    "EXIT_DELIBERATION_PROJECTION",
    "EXIT_ORCHESTRATOR_MULTI_AGENT",
    "EXIT_SINGLE_AGENT",
    "META_RISK_GATE_RESULT",
    "RiskApplicationReason",
    "RiskGateOutcome",
    "RiskGateProfile",
    "RiskGateResult",
    "RiskOverrideApplication",
    "RiskOverridePlan",
    "RiskTrigger",
    "apply_risk_manager_gate",
    "apply_risk_manager_gate_from_config",
    "authorize_risk_gate_bypass",
    "build_approved_risk_application_from_gate",
    "build_approved_risk_bypass_application",
    "build_risk_application_from_gate",
    "build_risk_context_for_exit",
    "build_risk_override_application",
    "build_risk_override_plan",
    "classify_risk_application_reason",
    "evaluate_risk_manager_gate",
    "get_risk_gate_result",
    "render_risk_gate_notice",
    "resolve_risk_gate_flags",
    "validate_risk_application_transition",
]
