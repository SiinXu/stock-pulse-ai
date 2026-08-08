# -*- coding: utf-8 -*-
"""Shared risk override planning and mandatory Risk Manager gate.

The historical ``build_risk_override_plan`` / ``build_risk_override_application``
helpers remain the single source of truth for force-downgrade transitions. This
module also exposes a mandatory **Risk Manager gate** that every decision exit
must invoke before a final buy/hold/sell recommendation is published.

Gate outcomes (deterministic, never LLM-backed):

* ``pass`` — no risk evidence requiring intervention
* ``attach_warning`` — keep the original signal, attach mandatory risk notes
* ``downgrade`` — move to a more conservative signal (strict mode or
  ``AGENT_RISK_OVERRIDE`` force path)

Default mode is warn-first (``RISK_GATE_ENABLED=true``, ``RISK_GATE_STRICT=false``)
so existing non-override outputs stay signal-compatible. Force-downgrade still
occurs when the existing override plan ``will_apply``. Gate failures are
fail-safe: analysis continues with the original signal and a recorded failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.agent.protocols import AgentContext, normalize_decision_signal

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

_MANDATORY_WARNING_PREFIX = "[Risk Manager]"
_HIGH_CONFIDENCE_THRESHOLD = 0.75
_BULLISH_DASHBOARD = frozenset({"buy"})
_BEARISH_RISK_SIGNALS = frozenset({"sell", "strong_sell"})


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
    ATTACH_WARNING = "attach_warning"
    DOWNGRADE = "downgrade"


@dataclass(frozen=True)
class RiskGateResult:
    """Traceable result of one Risk Manager gate evaluation.

    Always retains a final signal — the gate never empties or nulls a
    recommendation. ``fail_safe=True`` means the gate itself failed and the
    original signal was preserved so analysis can continue.
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
    fail_safe: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", RiskGateOutcome(self.outcome))
        original = normalize_decision_signal(self.original_signal)
        final = normalize_decision_signal(self.final_signal)
        object.__setattr__(self, "original_signal", original)
        object.__setattr__(self, "final_signal", final)
        if not str(self.exit_id or "").strip():
            raise ValueError("risk gate result requires an exit_id")
        if self.outcome is RiskGateOutcome.DOWNGRADE and original == final and not self.fail_safe:
            # Downgrade without a signal change is only valid when the signal
            # was already at the conservative bound (e.g. sell).
            pass

    def to_trace_dict(self) -> Dict[str, Any]:
        """Low-sensitivity dict safe for traces / meta / T03 consumers."""
        return {
            "outcome": self.outcome.value,
            "original_signal": self.original_signal,
            "final_signal": self.final_signal,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "evidence_codes": list(self.evidence_codes),
            "enabled": self.enabled,
            "strict": self.strict,
            "override_enabled": self.override_enabled,
            "override_would_apply": self.override_would_apply,
            "exit_id": self.exit_id,
            "fail_safe": self.fail_safe,
        }


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def resolve_risk_gate_flags(config: Any = None) -> Tuple[bool, bool, bool]:
    """Return ``(gate_enabled, gate_strict, override_enabled)`` from config."""
    if config is None:
        return True, False, True
    gate_enabled = _coerce_bool(getattr(config, "risk_gate_enabled", True), True)
    gate_strict = _coerce_bool(getattr(config, "risk_gate_strict", False), False)
    override_enabled = _coerce_bool(getattr(config, "agent_risk_override", True), True)
    return gate_enabled, gate_strict, override_enabled


def _collect_gate_evidence(
    ctx: AgentContext,
    *,
    current_signal: str,
    plan: RiskOverridePlan,
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Return ``(evidence_codes, human_reasons)`` from deterministic facts."""
    codes: List[str] = []
    reasons: List[str] = []

    if plan.has_high_flag:
        codes.append("high_severity_flag")
        reasons.append("high-severity risk flag present")
    if plan.veto_buy:
        codes.append("risk_veto")
        reasons.append("risk veto trigger present")
    if plan.adjustment in _DOWNGRADE_STEPS:
        codes.append("signal_downgrade_adjustment")
        reasons.append(f"risk signal_adjustment={plan.adjustment}")
    if plan.risk_level_high:
        codes.append("high_risk_evidence")
        reasons.append("risk_level=high evidence present")

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
            reasons.append(
                f"buy recommendation conflicts with risk agent signal={risk_signal}"
            )
        conf = risk_opinion.confidence
        try:
            conf_value = float(conf)
        except (TypeError, ValueError):
            conf_value = 0.0
        decision_conf = 0.0
        for opinion in reversed(ctx.opinions):
            if opinion.agent_name == "decision":
                try:
                    decision_conf = float(opinion.confidence)
                except (TypeError, ValueError):
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
            reasons.append(
                "high decision confidence does not match elevated risk evidence"
            )

    # Stable unique order
    unique_codes: List[str] = []
    unique_reasons: List[str] = []
    for code, reason in zip(codes, reasons):
        if code not in unique_codes:
            unique_codes.append(code)
            unique_reasons.append(reason)
    return tuple(unique_codes), tuple(unique_reasons)


def _build_gate_warnings(
    *,
    outcome: RiskGateOutcome,
    original_signal: str,
    final_signal: str,
    reasons: Sequence[str],
) -> Tuple[str, ...]:
    if outcome is RiskGateOutcome.PASS:
        return ()
    detail = "; ".join(reasons) if reasons else "risk evidence present"
    if outcome is RiskGateOutcome.DOWNGRADE:
        note = (
            f"{_MANDATORY_WARNING_PREFIX} Signal downgraded "
            f"{original_signal} -> {final_signal}. Reasons: {detail}."
        )
    else:
        note = (
            f"{_MANDATORY_WARNING_PREFIX} Mandatory risk review for "
            f"{original_signal} recommendation. Reasons: {detail}."
        )
    return (note,)


def evaluate_risk_manager_gate(
    ctx: AgentContext,
    *,
    current_signal: Any,
    exit_id: str,
    override_enabled: bool = True,
    gate_enabled: bool = True,
    gate_strict: bool = False,
) -> RiskGateResult:
    """Evaluate the mandatory Risk Manager gate without mutating the context.

    Deterministic only — never calls an LLM. Always returns a non-empty final
    signal. Callers that mutate dashboards should use
    :func:`apply_risk_manager_gate`.
    """
    normalized = normalize_decision_signal(current_signal)
    exit_key = str(exit_id or "").strip() or "unknown"

    if not gate_enabled:
        return RiskGateResult(
            outcome=RiskGateOutcome.PASS,
            original_signal=normalized,
            final_signal=normalized,
            reasons=("gate_disabled",),
            warnings=(),
            evidence_codes=(),
            enabled=False,
            strict=bool(gate_strict),
            override_enabled=bool(override_enabled),
            override_would_apply=False,
            exit_id=exit_key,
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
    )
    override_would_apply = bool(force_plan.will_apply)

    if not evidence_codes:
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
        )

    force_downgrade = bool(active_plan.will_apply) or (
        bool(gate_strict) and bool(force_plan.will_apply)
    )
    # Strict mode also force-downgrades buy when conflict/mismatch evidence
    # exists even without a classic override trigger.
    if (
        not force_downgrade
        and gate_strict
        and normalized == "buy"
        and any(
            code in evidence_codes
            for code in (
                "evidence_conclusion_conflict",
                "confidence_risk_mismatch",
                "high_severity_flag",
                "risk_veto",
                "signal_downgrade_adjustment",
            )
        )
    ):
        force_downgrade = True

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
            RiskGateOutcome.DOWNGRADE
            if target != normalized
            else RiskGateOutcome.ATTACH_WARNING
        )
        warnings = _build_gate_warnings(
            outcome=outcome,
            original_signal=normalized,
            final_signal=target,
            reasons=reasons,
        )
        return RiskGateResult(
            outcome=outcome,
            original_signal=normalized,
            final_signal=target if outcome is RiskGateOutcome.DOWNGRADE else normalized,
            reasons=reasons or ("risk_gate_force",),
            warnings=warnings,
            evidence_codes=evidence_codes,
            enabled=True,
            strict=bool(gate_strict),
            override_enabled=bool(override_enabled),
            override_would_apply=override_would_apply,
            exit_id=exit_key,
        )

    warnings = _build_gate_warnings(
        outcome=RiskGateOutcome.ATTACH_WARNING,
        original_signal=normalized,
        final_signal=normalized,
        reasons=reasons,
    )
    return RiskGateResult(
        outcome=RiskGateOutcome.ATTACH_WARNING,
        original_signal=normalized,
        final_signal=normalized,
        reasons=reasons,
        warnings=warnings,
        evidence_codes=evidence_codes,
        enabled=True,
        strict=bool(gate_strict),
        override_enabled=bool(override_enabled),
        override_would_apply=override_would_apply,
        exit_id=exit_key,
    )


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
    dashboard: Optional[Dict[str, Any]] = None,
) -> RiskGateResult:
    """Evaluate the gate, record trace facts, and optionally annotate a dashboard.

    Never clears recommendations. On internal failure, records a fail-safe PASS
    with the original signal so the analysis pipeline can continue.
    """
    normalized = normalize_decision_signal(current_signal)
    exit_key = str(exit_id or "").strip() or "unknown"
    try:
        result = evaluate_risk_manager_gate(
            ctx,
            current_signal=normalized,
            exit_id=exit_key,
            override_enabled=override_enabled,
            gate_enabled=gate_enabled,
            gate_strict=gate_strict,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - gate must not abort analysis
        logger.warning(
            "Risk Manager gate failed safe at exit=%s: %s",
            exit_key,
            type(exc).__name__,
        )
        result = RiskGateResult(
            outcome=RiskGateOutcome.PASS,
            original_signal=normalized,
            final_signal=normalized,
            reasons=("gate_internal_failure", type(exc).__name__),
            warnings=(
                f"{_MANDATORY_WARNING_PREFIX} Gate evaluation failed; "
                "original recommendation retained.",
            ),
            evidence_codes=("gate_internal_failure",),
            enabled=bool(gate_enabled),
            strict=bool(gate_strict),
            override_enabled=bool(override_enabled),
            override_would_apply=False,
            exit_id=exit_key,
            fail_safe=True,
        )

    _store_gate_result(ctx, result)

    if isinstance(dashboard, dict):
        if result.outcome is RiskGateOutcome.DOWNGRADE:
            dashboard["decision_type"] = result.final_signal
        if result.warnings:
            dashboard["risk_warning"] = _merge_mandatory_warnings(
                dashboard.get("risk_warning"),
                result.warnings,
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
    gate_enabled, gate_strict, override_enabled = resolve_risk_gate_flags(config)
    return apply_risk_manager_gate(
        ctx,
        current_signal=current_signal,
        exit_id=exit_id,
        override_enabled=override_enabled,
        gate_enabled=gate_enabled,
        gate_strict=gate_strict,
        dashboard=dashboard,
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
    "RiskGateResult",
    "RiskOverrideApplication",
    "RiskOverridePlan",
    "RiskTrigger",
    "apply_risk_manager_gate",
    "apply_risk_manager_gate_from_config",
    "build_approved_risk_bypass_application",
    "build_risk_override_application",
    "build_risk_override_plan",
    "classify_risk_application_reason",
    "evaluate_risk_manager_gate",
    "get_risk_gate_result",
    "resolve_risk_gate_flags",
    "validate_risk_application_transition",
]
