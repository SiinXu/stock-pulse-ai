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
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

ENGINE_VERSION = "portfolio-constraints-v1"

STATUS_ALLOW = "allow"
STATUS_REJECT = "reject"
STATUS_HINTS = "hints"

LABEL_CONSTRAINT_FEASIBLE = "constraint_feasible"
LABEL_RESEARCH_ONLY = "research_only"

SEVERITY_BLOCKING = "blocking"
SEVERITY_HINT = "hint"

# Reuses the canonical decision-action taxonomy from
# ``src.schemas.decision_action`` (kept as literals so this leaf module does
# not import the report-language stack).
INCREASING_ACTIONS = frozenset({"buy", "add"})
DECREASING_ACTIONS = frozenset({"reduce", "sell"})
NEUTRAL_ACTIONS = frozenset({"hold", "watch", "avoid", "alert"})
VALID_ACTIONS = INCREASING_ACTIONS | DECREASING_ACTIONS | NEUTRAL_ACTIONS

ENV_MAX_NAME_PCT = "PORTFOLIO_CONSTRAINT_MAX_NAME_PCT"
ENV_MAX_SECTOR_PCT = "PORTFOLIO_CONSTRAINT_MAX_SECTOR_PCT"
ENV_BLACKLIST = "PORTFOLIO_CONSTRAINT_BLACKLIST"
ENV_BLOCKING_RISK_FLAGS = "PORTFOLIO_CONSTRAINT_BLOCKING_RISK_FLAGS"

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


@dataclass(frozen=True)
class ProposedAction:
    """One proposed action inside a research proposal."""

    symbol: str
    action: str
    target_weight_pct: Optional[float] = None
    sector: Optional[str] = None

    def normalized(self) -> "ProposedAction":
        symbol = _normalized_symbol(self.symbol, "proposal symbol")
        action = str(self.action or "").strip().lower()
        if action not in VALID_ACTIONS:
            raise ConstraintInputError(
                f"proposal action must be one of {sorted(VALID_ACTIONS)}"
            )
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
        if not self.actions:
            raise ConstraintInputError("proposal must contain at least one action")
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
    blacklist: frozenset = frozenset()
    blocking_risk_flags: frozenset = frozenset()

    def normalized(self) -> "ConstraintConfig":
        max_name = (
            None
            if self.max_single_name_weight_pct is None
            else _finite_pct(self.max_single_name_weight_pct, ENV_MAX_NAME_PCT)
        )
        max_sector = (
            None
            if self.max_sector_weight_pct is None
            else _finite_pct(self.max_sector_weight_pct, ENV_MAX_SECTOR_PCT)
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


def _check_per_name_cap(
    action: ProposedAction,
    *,
    config: ConstraintConfig,
    weights: Mapping[str, float],
    weights_known: bool,
) -> List[ConstraintFinding]:
    cap = config.max_single_name_weight_pct
    if cap is None:
        return []
    target = action.target_weight_pct
    if target is not None:
        if target > cap + _EPS:
            return [
                ConstraintFinding(
                    constraint="per_name_cap",
                    severity=SEVERITY_BLOCKING,
                    symbol=action.symbol,
                    reason=(
                        f"Target weight {target:.2f}% for {action.symbol} exceeds "
                        f"the per-name cap {cap:.2f}%."
                    ),
                    observed_pct=target,
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


def _check_sector_cap(
    action: ProposedAction,
    *,
    config: ConstraintConfig,
    weights: Mapping[str, float],
    sectors: Mapping[str, str],
    weights_known: bool,
) -> List[ConstraintFinding]:
    cap = config.max_sector_weight_pct
    if cap is None:
        return []
    if action.action not in INCREASING_ACTIONS:
        return []
    sector = action.sector or sectors.get(action.symbol)
    if not sector:
        return [
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
        ]
    if not weights_known:
        return [
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
        ]
    current_sector = _sector_weight(sector, weights=weights, sectors=sectors)
    target = action.target_weight_pct
    if target is not None:
        current_name = weights.get(action.symbol, 0.0)
        projected = current_sector + max(0.0, target - current_name)
        if projected > cap + _EPS:
            return [
                ConstraintFinding(
                    constraint="sector_cap",
                    severity=SEVERITY_BLOCKING,
                    symbol=action.symbol,
                    reason=(
                        f"Projected weight {projected:.2f}% for sector '{sector}' "
                        f"exceeds the sector cap {cap:.2f}% "
                        f"(target {target:.2f}% for {action.symbol})."
                    ),
                    observed_pct=projected,
                    limit_pct=cap,
                )
            ]
        return []
    if current_sector >= cap - _EPS:
        return [
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
        ]
    return [
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
    ]


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
                    f"increase exposure."
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

    findings: List[ConstraintFinding] = []
    for action in normalized_proposal.actions:
        findings.extend(_check_blacklist(action, normalized_config))
        findings.extend(
            _check_per_name_cap(
                action,
                config=normalized_config,
                weights=weights,
                weights_known=portfolio.weights_known,
            )
        )
        findings.extend(
            _check_sector_cap(
                action,
                config=normalized_config,
                weights=weights,
                sectors=sectors,
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
    return _verdict_from_findings(
        findings, constraints_evaluated=normalized_config.constraint_count
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


def _parse_optional_pct(raw: Optional[str], key: str) -> Optional[float]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise ConstraintInputError(f"{key} must be a number between 0 and 100") from exc
    return _finite_pct(value, key)


def _parse_csv(raw: Optional[str]) -> Tuple[str, ...]:
    return tuple(
        item.strip() for item in str(raw or "").split(",") if item.strip()
    )


def load_constraint_config_from_env(
    getenv: Callable[[str], Optional[str]] = os.environ.get,
) -> ConstraintConfig:
    """Build a :class:`ConstraintConfig` from environment configuration.

    Unset / empty keys switch the corresponding constraint off; the default
    environment therefore yields the explicit zero-constraints pass-through.

    Raises:
        ConstraintInputError: when a configured value is malformed. Callers on
            presentation paths must treat this as fail-closed (research-only),
            not as "no constraints".
    """
    return ConstraintConfig(
        max_single_name_weight_pct=_parse_optional_pct(
            getenv(ENV_MAX_NAME_PCT), ENV_MAX_NAME_PCT
        ),
        max_sector_weight_pct=_parse_optional_pct(
            getenv(ENV_MAX_SECTOR_PCT), ENV_MAX_SECTOR_PCT
        ),
        blacklist=frozenset(
            _normalized_symbol(symbol, ENV_BLACKLIST)
            for symbol in _parse_csv(getenv(ENV_BLACKLIST))
        ),
        blocking_risk_flags=frozenset(
            flag.lower() for flag in _parse_csv(getenv(ENV_BLOCKING_RISK_FLAGS))
        ),
    ).normalized()
