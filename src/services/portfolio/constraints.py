# -*- coding: utf-8 -*-
"""Deterministic portfolio constraint engine for research proposals (issue #1132).

Runs proposed actions through configurable portfolio constraints before they
are presented as executable scenarios. The engine is a pure rules engine:

- Constraint subset: per-name cap, sector cap, blacklist, simple risk flags.
- ``check_proposal(portfolio, proposal, config)`` returns a typed
  :class:`ConstraintVerdict` with status ``allow`` / ``reject`` / ``hints``.
- A violating proposal is never silently filtered: every violation is a typed
  :class:`ConstraintFinding` with a stable constraint code and an English
  reason.
- Zero configured constraints is an explicit pass-through verdict
  (``passthrough=True`` with ``passthrough_reason``), never an implicit skip.
- Unknown data (missing weights or sector) is surfaced as an explicit
  ``hint`` finding instead of silently passing or silently blocking.

Hard boundaries:

- The engine labels feasibility for research output only. It does not execute
  trades, mutate the ledger, and it does not replace broker-side compliance.
- Arithmetic happens here, in code, never in LLM prompts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ENGINE_VERSION = "portfolio-constraints-v1"

STATUS_ALLOW = "allow"
STATUS_REJECT = "reject"
STATUS_HINTS = "hints"

LABEL_CONSTRAINT_FEASIBLE = "constraint_feasible"
LABEL_RESEARCH_ONLY = "research_only"

SEVERITY_BLOCKING = "blocking"
SEVERITY_HINT = "hint"

# Canonical eight-state decision-action taxonomy (literals only — this leaf
# module must not import the report-language stack).
INCREASING_ACTIONS = frozenset({"buy", "add"})
DECREASING_ACTIONS = frozenset({"reduce", "sell"})
NEUTRAL_ACTIONS = frozenset({"hold", "watch", "avoid", "alert"})
VALID_ACTIONS = INCREASING_ACTIONS | DECREASING_ACTIONS | NEUTRAL_ACTIONS

# Research / rebalancing aliases used by current proposal producers.
ACTION_ALIASES = {
    "trim": "reduce",
    "exit": "sell",
    "strong_sell": "sell",
    "strong-sell": "sell",
    "strongsell": "sell",
    "strong_buy": "buy",
    "strong-buy": "buy",
    "strongbuy": "buy",
    "accumulate": "add",
}

PASSTHROUGH_REASON_NO_CONSTRAINTS = "no_constraints_configured"

_EPS = 1e-9


class ConstraintInputError(ValueError):
    """A proposal, portfolio view, or config value is malformed.

    Raised by the strict API instead of silently allowing or dropping the
    proposal; wiring layers convert it into a fail-closed reject verdict via
    :func:`check_proposal_fail_closed`.
    """


def _finite_pct(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConstraintInputError(f"{label} must be a number") from exc
    if not math.isfinite(number):
        raise ConstraintInputError(f"{label} must be finite")
    if number < 0.0 or number > 100.0:
        raise ConstraintInputError(f"{label} must be between 0 and 100")
    return number


def _normalized_symbol(value: Any, label: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        raise ConstraintInputError(f"{label} is required")
    if len(text) > 32:
        raise ConstraintInputError(f"{label} exceeds 32 characters")
    return text


def normalize_proposal_action(value: Any) -> str:
    """Map a research / rebalancing action onto the canonical taxonomy."""

    action = str(value or "").strip().lower()
    action = ACTION_ALIASES.get(action, action)
    if action not in VALID_ACTIONS:
        raise ConstraintInputError(
            f"proposal action must be one of {sorted(VALID_ACTIONS)}"
        )
    return action


@dataclass(frozen=True)
class ProposedAction:
    """One proposed action inside a research proposal."""

    symbol: str
    action: str
    target_weight_pct: Optional[float] = None
    sector: Optional[str] = None

    def normalized(self) -> "ProposedAction":
        symbol = _normalized_symbol(self.symbol, "proposal symbol")
        action = normalize_proposal_action(self.action)
        target = (
            None
            if self.target_weight_pct is None
            else _finite_pct(self.target_weight_pct, f"target_weight_pct[{symbol}]")
        )
        sector = str(self.sector or "").strip() or None
        return ProposedAction(
            symbol=symbol, action=action, target_weight_pct=target, sector=sector
        )


@dataclass(frozen=True)
class ResearchProposal:
    """A bundle of proposed actions produced by research output."""

    actions: Tuple[ProposedAction, ...]
    label: str = ""

    def normalized(self) -> "ResearchProposal":
        return ResearchProposal(
            actions=tuple(action.normalized() for action in self.actions),
            label=str(self.label or "").strip(),
        )


@dataclass(frozen=True)
class PortfolioView:
    """Read-only projection of the portfolio the proposal is checked against.

    ``weights_known=False`` states explicitly that current weights are
    unavailable (for example a single-symbol context without portfolio value);
    an empty ``weights_pct`` with ``weights_known=True`` means an all-cash /
    empty portfolio.
    """

    weights_pct: Mapping[str, float] = field(default_factory=dict)
    sectors: Mapping[str, str] = field(default_factory=dict)
    risk_flags: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    weights_known: bool = True

    def normalized_weights(self) -> Dict[str, float]:
        weights: Dict[str, float] = {}
        for raw_symbol, raw_weight in self.weights_pct.items():
            symbol = _normalized_symbol(raw_symbol, "portfolio symbol")
            weights[symbol] = _finite_pct(raw_weight, f"weights_pct[{symbol}]")
        return weights

    def normalized_sectors(self) -> Dict[str, str]:
        sectors: Dict[str, str] = {}
        for raw_symbol, raw_sector in self.sectors.items():
            symbol = _normalized_symbol(raw_symbol, "portfolio symbol")
            text = str(raw_sector or "").strip()
            if text:
                sectors[symbol] = text
        return sectors

    def normalized_risk_flags(self) -> Dict[str, Tuple[str, ...]]:
        flags: Dict[str, Tuple[str, ...]] = {}
        for raw_symbol, raw_flags in self.risk_flags.items():
            symbol = _normalized_symbol(raw_symbol, "portfolio symbol")
            cleaned = tuple(
                sorted(
                    {
                        str(flag or "").strip().lower()
                        for flag in (raw_flags or ())
                        if str(flag or "").strip()
                    }
                )
            )
            if cleaned:
                flags[symbol] = cleaned
        return flags


@dataclass(frozen=True)
class ConstraintConfig:
    """Configured constraint subset. ``None`` / empty means the constraint is off."""

    max_single_name_weight_pct: Optional[float] = None
    max_sector_weight_pct: Optional[float] = None
    blacklist: frozenset[str] = frozenset()
    blocking_risk_flags: frozenset[str] = frozenset()

    def normalized(self) -> "ConstraintConfig":
        max_name = (
            None
            if self.max_single_name_weight_pct is None
            else _finite_pct(
                self.max_single_name_weight_pct, "max_single_name_weight_pct"
            )
        )
        max_sector = (
            None
            if self.max_sector_weight_pct is None
            else _finite_pct(self.max_sector_weight_pct, "max_sector_weight_pct")
        )
        blacklist = frozenset(
            _normalized_symbol(symbol, "blacklist symbol") for symbol in self.blacklist
        )
        flags = frozenset(
            flag
            for flag in (
                str(item or "").strip().lower() for item in self.blocking_risk_flags
            )
            if flag
        )
        return ConstraintConfig(
            max_single_name_weight_pct=max_name,
            max_sector_weight_pct=max_sector,
            blacklist=blacklist,
            blocking_risk_flags=flags,
        )

    @property
    def constraint_count(self) -> int:
        return sum(
            (
                self.max_single_name_weight_pct is not None,
                self.max_sector_weight_pct is not None,
                bool(self.blacklist),
                bool(self.blocking_risk_flags),
            )
        )


@dataclass(frozen=True)
class ConstraintFinding:
    """One structured constraint finding (violation or explicit hint)."""

    constraint: str
    severity: str
    symbol: Optional[str]
    reason: str
    observed_pct: Optional[float] = None
    limit_pct: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "constraint": self.constraint,
            "severity": self.severity,
            "symbol": self.symbol,
            "reason": self.reason,
        }
        if self.observed_pct is not None:
            payload["observed_pct"] = round(self.observed_pct, 6)
        if self.limit_pct is not None:
            payload["limit_pct"] = round(self.limit_pct, 6)
        return payload


@dataclass(frozen=True)
class ConstraintVerdict:
    """Structured verdict for one research proposal."""

    status: str
    label: str
    findings: Tuple[ConstraintFinding, ...]
    constraints_evaluated: int
    passthrough: bool = False
    passthrough_reason: Optional[str] = None
    engine_version: str = ENGINE_VERSION

    @property
    def blocking_findings(self) -> Tuple[ConstraintFinding, ...]:
        return tuple(f for f in self.findings if f.severity == SEVERITY_BLOCKING)

    @property
    def hint_findings(self) -> Tuple[ConstraintFinding, ...]:
        return tuple(f for f in self.findings if f.severity == SEVERITY_HINT)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "engine_version": self.engine_version,
            "status": self.status,
            "label": self.label,
            "constraints_evaluated": self.constraints_evaluated,
            "passthrough": self.passthrough,
            "findings": [finding.to_dict() for finding in self.findings],
        }
        if self.passthrough_reason:
            payload["passthrough_reason"] = self.passthrough_reason
        return payload


def _verdict_from_findings(
    findings: Sequence[ConstraintFinding],
    *,
    constraints_evaluated: int,
) -> ConstraintVerdict:
    has_blocking = any(f.severity == SEVERITY_BLOCKING for f in findings)
    if has_blocking:
        status = STATUS_REJECT
        label = LABEL_RESEARCH_ONLY
    elif findings:
        status = STATUS_HINTS
        label = LABEL_CONSTRAINT_FEASIBLE
    else:
        status = STATUS_ALLOW
        label = LABEL_CONSTRAINT_FEASIBLE
    return ConstraintVerdict(
        status=status,
        label=label,
        findings=tuple(findings),
        constraints_evaluated=constraints_evaluated,
    )


def _check_blacklist(
    action: ProposedAction, config: ConstraintConfig
) -> List[ConstraintFinding]:
    if not config.blacklist or action.symbol not in config.blacklist:
        return []
    if action.action in INCREASING_ACTIONS:
        return [
            ConstraintFinding(
                constraint="blacklist",
                severity=SEVERITY_BLOCKING,
                symbol=action.symbol,
                reason=(
                    f"{action.symbol} is blacklisted; the proposed "
                    f"'{action.action}' would open or increase exposure."
                ),
            )
        ]
    return [
        ConstraintFinding(
            constraint="blacklist",
            severity=SEVERITY_HINT,
            symbol=action.symbol,
            reason=(
                f"{action.symbol} is blacklisted; the proposed "
                f"'{action.action}' does not increase exposure and stays feasible."
            ),
        )
    ]


def _dedupe_findings(findings: Sequence[ConstraintFinding]) -> List[ConstraintFinding]:
    seen: set[Tuple[str, str, Optional[str], str]] = set()
    unique: List[ConstraintFinding] = []
    for finding in findings:
        key = (finding.constraint, finding.severity, finding.symbol, finding.reason)
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def _check_per_name_cap(
    action: ProposedAction,
    *,
    config: ConstraintConfig,
    weights: Mapping[str, float],
    projected_weights: Mapping[str, float],
    weights_known: bool,
) -> List[ConstraintFinding]:
    cap = config.max_single_name_weight_pct
    if cap is None:
        return []
    target = action.target_weight_pct
    if target is not None:
        observed = projected_weights.get(action.symbol, target)
        if observed > cap + _EPS:
            return [
                ConstraintFinding(
                    constraint="per_name_cap",
                    severity=SEVERITY_BLOCKING,
                    symbol=action.symbol,
                    reason=(
                        f"Target weight {observed:.2f}% for {action.symbol} exceeds "
                        f"the per-name cap {cap:.2f}%."
                    ),
                    observed_pct=observed,
                    limit_pct=cap,
                )
            ]
        return []
    if action.action not in INCREASING_ACTIONS:
        return []
    if not weights_known:
        return [
            ConstraintFinding(
                constraint="per_name_cap",
                severity=SEVERITY_HINT,
                symbol=action.symbol,
                reason=(
                    f"Per-name cap {cap:.2f}% is configured but current portfolio "
                    f"weights are unavailable; the unsized "
                    f"'{action.action}' for {action.symbol} cannot be fully evaluated."
                ),
                limit_pct=cap,
            )
        ]
    current = weights.get(action.symbol, 0.0)
    if current >= cap - _EPS:
        return [
            ConstraintFinding(
                constraint="per_name_cap",
                severity=SEVERITY_BLOCKING,
                symbol=action.symbol,
                reason=(
                    f"{action.symbol} already holds {current:.2f}% versus the "
                    f"per-name cap {cap:.2f}%; any increase breaches the cap."
                ),
                observed_pct=current,
                limit_pct=cap,
            )
        ]
    return [
        ConstraintFinding(
            constraint="per_name_cap",
            severity=SEVERITY_HINT,
            symbol=action.symbol,
            reason=(
                f"Unsized '{action.action}' for {action.symbol}: headroom to the "
                f"per-name cap is {cap - current:.2f} pp "
                f"(current {current:.2f}%, cap {cap:.2f}%)."
            ),
            observed_pct=current,
            limit_pct=cap,
        )
    ]


def _sector_weight(
    sector: str,
    *,
    weights: Mapping[str, float],
    sectors: Mapping[str, str],
) -> float:
    return sum(
        weight
        for symbol, weight in weights.items()
        if sectors.get(symbol) == sector
    )


def _check_sector_caps(
    actions: Sequence[ProposedAction],
    *,
    config: ConstraintConfig,
    weights: Mapping[str, float],
    projected_weights: Mapping[str, float],
    sectors: Mapping[str, str],
    weights_known: bool,
) -> List[ConstraintFinding]:
    cap = config.max_sector_weight_pct
    if cap is None:
        return []
    increasing = [action for action in actions if action.action in INCREASING_ACTIONS]
    if not increasing:
        return []

    findings: List[ConstraintFinding] = []
    seen_sectors: set[str] = set()
    for action in increasing:
        sector = action.sector or sectors.get(action.symbol)
        if not sector:
            findings.append(
                ConstraintFinding(
                    constraint="sector_cap",
                    severity=SEVERITY_HINT,
                    symbol=action.symbol,
                    reason=(
                        f"Sector cap {cap:.2f}% is configured but no sector is known "
                        f"for {action.symbol}; the sector cap cannot be evaluated."
                    ),
                    limit_pct=cap,
                )
            )
            continue
        if not weights_known and action.target_weight_pct is None:
            findings.append(
                ConstraintFinding(
                    constraint="sector_cap",
                    severity=SEVERITY_HINT,
                    symbol=action.symbol,
                    reason=(
                        f"Sector cap {cap:.2f}% is configured for sector '{sector}' "
                        f"but current portfolio weights are unavailable; the cap "
                        f"cannot be fully evaluated."
                    ),
                    limit_pct=cap,
                )
            )
            continue
        if sector in seen_sectors:
            continue
        seen_sectors.add(sector)
        current_sector = _sector_weight(sector, weights=weights, sectors=sectors)
        projected = _sector_weight(
            sector, weights=projected_weights, sectors=sectors
        )
        if action.target_weight_pct is None and current_sector >= cap - _EPS:
            findings.append(
                ConstraintFinding(
                    constraint="sector_cap",
                    severity=SEVERITY_BLOCKING,
                    symbol=action.symbol,
                    reason=(
                        f"Sector '{sector}' already holds {current_sector:.2f}% versus "
                        f"the sector cap {cap:.2f}%; any increase breaches the cap."
                    ),
                    observed_pct=current_sector,
                    limit_pct=cap,
                )
            )
            continue
        if projected > cap + _EPS:
            findings.append(
                ConstraintFinding(
                    constraint="sector_cap",
                    severity=SEVERITY_BLOCKING,
                    symbol=action.symbol,
                    reason=(
                        f"Projected weight {projected:.2f}% for sector '{sector}' "
                        f"exceeds the sector cap {cap:.2f}%."
                    ),
                    observed_pct=projected,
                    limit_pct=cap,
                )
            )
            continue
        if action.target_weight_pct is None:
            findings.append(
                ConstraintFinding(
                    constraint="sector_cap",
                    severity=SEVERITY_HINT,
                    symbol=action.symbol,
                    reason=(
                        f"Unsized '{action.action}' in sector '{sector}': headroom to the "
                        f"sector cap is {cap - current_sector:.2f} pp "
                        f"(current {current_sector:.2f}%, cap {cap:.2f}%)."
                    ),
                    observed_pct=current_sector,
                    limit_pct=cap,
                )
            )
    return findings


def _check_risk_flags(
    action: ProposedAction,
    *,
    config: ConstraintConfig,
    risk_flags: Mapping[str, Tuple[str, ...]],
) -> List[ConstraintFinding]:
    if not config.blocking_risk_flags:
        return []
    active = [
        flag
        for flag in risk_flags.get(action.symbol, ())
        if flag in config.blocking_risk_flags
    ]
    if not active:
        return []
    flags_text = ", ".join(active)
    if action.action in INCREASING_ACTIONS:
        return [
            ConstraintFinding(
                constraint="risk_flag",
                severity=SEVERITY_BLOCKING,
                symbol=action.symbol,
                reason=(
                    f"{action.symbol} carries blocking risk flag(s) "
                    f"[{flags_text}]; the proposed '{action.action}' would "
                    "increase exposure."
                ),
            )
        ]
    return [
        ConstraintFinding(
            constraint="risk_flag",
            severity=SEVERITY_HINT,
            symbol=action.symbol,
            reason=(
                f"{action.symbol} carries blocking risk flag(s) [{flags_text}]; "
                f"the proposed '{action.action}' does not increase exposure."
            ),
        )
    ]


def check_proposal(
    portfolio: PortfolioView,
    proposal: ResearchProposal,
    config: ConstraintConfig,
) -> ConstraintVerdict:
    """Check one research proposal against the configured constraints.

    Raises:
        ConstraintInputError: for malformed portfolio, proposal, or config
            inputs. Callers on presentation paths should use
            :func:`check_proposal_fail_closed` to convert errors into a
            fail-closed reject verdict.
    """
    if not isinstance(portfolio, PortfolioView):
        raise ConstraintInputError("portfolio must be a PortfolioView")
    if not isinstance(proposal, ResearchProposal):
        raise ConstraintInputError("proposal must be a ResearchProposal")
    if not isinstance(config, ConstraintConfig):
        raise ConstraintInputError("config must be a ConstraintConfig")

    normalized_config = config.normalized()
    normalized_proposal = proposal.normalized()
    weights = portfolio.normalized_weights()
    sectors = portfolio.normalized_sectors()
    risk_flags = portfolio.normalized_risk_flags()

    if normalized_config.constraint_count == 0:
        return ConstraintVerdict(
            status=STATUS_ALLOW,
            label=LABEL_CONSTRAINT_FEASIBLE,
            findings=(),
            constraints_evaluated=0,
            passthrough=True,
            passthrough_reason=PASSTHROUGH_REASON_NO_CONSTRAINTS,
        )

    projected = dict(weights)
    for action in normalized_proposal.actions:
        if action.target_weight_pct is not None:
            projected[action.symbol] = action.target_weight_pct
        if action.sector:
            sectors.setdefault(action.symbol, action.sector)

    findings: List[ConstraintFinding] = []
    for action in normalized_proposal.actions:
        findings.extend(_check_blacklist(action, normalized_config))
        findings.extend(
            _check_per_name_cap(
                action,
                config=normalized_config,
                weights=weights,
                projected_weights=projected,
                weights_known=portfolio.weights_known,
            )
        )
        findings.extend(
            _check_risk_flags(
                action,
                config=normalized_config,
                risk_flags=risk_flags,
            )
        )
    findings.extend(
        _check_sector_caps(
            normalized_proposal.actions,
            config=normalized_config,
            weights=weights,
            projected_weights=projected,
            sectors=sectors,
            weights_known=portfolio.weights_known,
        )
    )
    return _verdict_from_findings(
        _dedupe_findings(findings),
        constraints_evaluated=normalized_config.constraint_count,
    )


def check_proposal_fail_closed(
    portfolio: PortfolioView,
    proposal: ResearchProposal,
    config: ConstraintConfig,
) -> ConstraintVerdict:
    """Fail-closed wrapper for presentation paths.

    Any engine or input error yields ``reject`` / ``research_only`` with an
    explicit ``engine_error`` finding, so a violating proposal can never slip
    through as feasible because the engine failed.
    """
    try:
        return check_proposal(portfolio, proposal, config)
    except Exception as exc:  # broad-exception: fail_closed_verdict - Engine errors must label the proposal non-executable, never feasible.
        return ConstraintVerdict(
            status=STATUS_REJECT,
            label=LABEL_RESEARCH_ONLY,
            findings=(
                ConstraintFinding(
                    constraint="engine_error",
                    severity=SEVERITY_BLOCKING,
                    symbol=None,
                    reason=(
                        "Constraint engine failed "
                        f"({type(exc).__name__}); the proposal is labeled "
                        "research-only until constraints can be evaluated."
                    ),
                ),
            ),
            constraints_evaluated=0,
        )


def _optional_pct(raw: Any, key: str) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    return _finite_pct(raw, key)


def _string_set(raw: Any, *, symbol_items: bool = False) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        items: Iterable[str] = (item.strip() for item in raw.split(","))
    elif isinstance(raw, Iterable) and not isinstance(raw, (bytes, bytearray)):
        items = (str(item).strip() for item in raw)
    else:
        raise ConstraintInputError("constraint collection must be a string or list")
    cleaned = [item for item in items if item]
    if symbol_items:
        return frozenset(_normalized_symbol(item, "blacklist symbol") for item in cleaned)
    return frozenset(item.lower() for item in cleaned)


def load_constraint_config(raw: Optional[Mapping[str, Any]] = None) -> ConstraintConfig:
    """Build a :class:`ConstraintConfig` from a mapping.

    Missing / empty keys switch the corresponding constraint off. An empty or
    omitted mapping is the explicit zero-constraints pass-through.

    Raises:
        ConstraintInputError: when a configured value is malformed. Callers on
            presentation paths must treat this as fail-closed (research-only),
            not as "no constraints".
    """
    if raw is None:
        return ConstraintConfig()
    if not isinstance(raw, Mapping):
        raise ConstraintInputError("constraint config must be an object")
    return ConstraintConfig(
        max_single_name_weight_pct=_optional_pct(
            raw.get("max_single_name_weight_pct"), "max_single_name_weight_pct"
        ),
        max_sector_weight_pct=_optional_pct(
            raw.get("max_sector_weight_pct"), "max_sector_weight_pct"
        ),
        blacklist=_string_set(raw.get("blacklist"), symbol_items=True),
        blocking_risk_flags=_string_set(raw.get("blocking_risk_flags")),
    ).normalized()
