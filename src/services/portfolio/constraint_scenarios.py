# -*- coding: utf-8 -*-
"""Research proposal/scenario gate over the portfolio constraint engine.

This is the production wiring layer for issue #1132. Real research proposal
and scenario paths must call :func:`evaluate_research_scenario` (or
:func:`apply_constraints_to_research_assessment`) so numeric feasibility is
decided by the deterministic rules engine, not by an LLM.

The gate never marks a scenario as a broker-executable order. A
``constraint_feasible`` label means the configured research constraints did
not block the proposal. It is not broker, exchange, or regulatory compliance.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.services.portfolio.constraints import (
    ConstraintConfig,
    ConstraintFinding,
    ConstraintInputError,
    ConstraintVerdict,
    LABEL_CONSTRAINT_FEASIBLE,
    LABEL_RESEARCH_ONLY,
    PASSTHROUGH_REASON_NO_CONSTRAINTS,
    PortfolioView,
    ProposedAction,
    ResearchProposal,
    SEVERITY_BLOCKING,
    STATUS_REJECT,
    check_proposal_fail_closed,
    load_constraint_config,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

NOT_BROKER_COMPLIANCE_DISCLAIMER = (
    "Constraint checks are a deterministic research aid. They do not execute "
    "trades, are not broker, exchange, or regulatory compliance, and never "
    "make a scenario executable as an order."
)

PASSTHROUGH_REASON_NO_PROPOSED_ACTIONS = "no_proposed_actions"
PASSTHROUGH_REASON_UNPARSEABLE_PROPOSAL = "unparseable_proposal"
PASSTHROUGH_DISCLAIMER = (
    "No portfolio constraint policy was applied; constraint_feasible is a "
    "passthrough, not a policy check."
)


def _as_mapping(raw: Any) -> Optional[Mapping[str, Any]]:
    return raw if isinstance(raw, Mapping) else None


def _weight_pct_from_item(item: Mapping[str, Any]) -> Optional[float]:
    if item.get("target_weight_pct") is not None:
        return float(item["target_weight_pct"])
    if item.get("to_weight_pct") is not None:
        return float(item["to_weight_pct"])
    if item.get("suggested_weight") is not None:
        value = float(item["suggested_weight"])
        return value * 100.0 if value <= 1.0 else value
    if item.get("target_weight_pct_mid") is not None:
        return float(item["target_weight_pct_mid"])
    return None


def _symbol_from_item(item: Mapping[str, Any]) -> str:
    return str(item.get("symbol") or item.get("code") or "").strip()


def portfolio_view_from_mapping(raw: Optional[Mapping[str, Any]]) -> PortfolioView:
    """Project a snapshot-like mapping into a :class:`PortfolioView`."""

    if raw is None:
        return PortfolioView(weights_known=False)
    if not isinstance(raw, Mapping):
        raise ConstraintInputError("portfolio view must be an object")

    weights_raw = raw.get("weights_pct")
    if weights_raw is None:
        weights_raw = raw.get("weights")
    weights: Dict[str, float] = {}
    if isinstance(weights_raw, Mapping):
        for symbol, weight in weights_raw.items():
            weights[str(symbol)] = float(weight)
    elif isinstance(weights_raw, Sequence) and not isinstance(
        weights_raw, (str, bytes, bytearray)
    ):
        for item in weights_raw:
            if not isinstance(item, Mapping):
                continue
            symbol = _symbol_from_item(item)
            if not symbol:
                continue
            if item.get("weight_pct") is not None:
                weights[symbol] = float(item["weight_pct"])
            elif item.get("weight") is not None:
                value = float(item["weight"])
                weights[symbol] = value * 100.0 if value <= 1.0 else value

    sectors_raw = raw.get("sectors") or {}
    sectors: Dict[str, str] = {}
    if isinstance(sectors_raw, Mapping):
        sectors = {str(symbol): str(sector) for symbol, sector in sectors_raw.items()}

    flags_raw = raw.get("risk_flags") or {}
    flags: Dict[str, Tuple[str, ...]] = {}
    if isinstance(flags_raw, Mapping):
        for symbol, items in flags_raw.items():
            if isinstance(items, str):
                cleaned = tuple(
                    part.strip().lower() for part in items.split(",") if part.strip()
                )
            elif isinstance(items, Sequence) and not isinstance(
                items, (bytes, bytearray)
            ):
                cleaned = tuple(
                    str(flag).strip().lower() for flag in items if str(flag).strip()
                )
            else:
                continue
            if cleaned:
                flags[str(symbol)] = cleaned

    weights_known = raw.get("weights_known")
    if weights_known is None:
        weights_known = True
    return PortfolioView(
        weights_pct=weights,
        sectors=sectors,
        risk_flags=flags,
        weights_known=bool(weights_known),
    )


def _optional_sequence(raw: Any) -> List[Any]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return []
    return list(raw)


def _is_candidate_row(item: Any) -> bool:
    if not isinstance(item, Mapping):
        return False
    if _symbol_from_item(item):
        return True
    if str(item.get("action") or item.get("signal") or "").strip():
        return True
    try:
        return _weight_pct_from_item(item) is not None
    except (TypeError, ValueError):
        return True


def _actions_from_sequence(raw_actions: Sequence[Any]) -> Tuple[List[ProposedAction], int]:
    actions: List[ProposedAction] = []
    candidates = 0
    for item in raw_actions:
        if not _is_candidate_row(item):
            continue
        candidates += 1
        symbol = _symbol_from_item(item)
        # PortfolioAgent positions emit `signal`; rebalancing suggestions emit `action`.
        action = str(item.get("action") or item.get("signal") or "").strip()
        if not symbol or not action:
            continue
        try:
            target = _weight_pct_from_item(item)
        except (TypeError, ValueError):
            continue
        sector = item.get("sector")
        actions.append(
            ProposedAction(
                symbol=symbol,
                action=action,
                target_weight_pct=target,
                sector=str(sector).strip() if sector not in (None, "") else None,
            )
        )
    return actions, candidates


def _proposal_from_rows(
    raw_actions: Sequence[Any], *, label: str
) -> Tuple[ResearchProposal, int]:
    actions, candidates = _actions_from_sequence(raw_actions)
    return ResearchProposal(actions=tuple(actions), label=label), candidates


def research_proposal_from_mapping(raw: Optional[Mapping[str, Any]]) -> ResearchProposal:
    """Project a research proposal / scenario mapping into typed actions."""

    proposal, _candidates = _project_research_proposal(explicit_proposal=raw)
    return proposal


def research_proposal_from_assessment(
    assessment: Optional[Mapping[str, Any]],
    *,
    rebalancing_base: Optional[Mapping[str, Any]] = None,
    explicit_proposal: Optional[Mapping[str, Any]] = None,
) -> ResearchProposal:
    """Build the proposal that the live research path actually presents.

    Preference order:
    1. An explicit research proposal mapping.
    2. Deterministic rebalancing suggestions (the user-visible scenario).
    3. Position bands only when suggestions are empty.
    4. Assessment positions already overwritten by the deterministic base.
    """

    proposal, _candidates = _project_research_proposal(
        assessment=assessment,
        rebalancing_base=rebalancing_base,
        explicit_proposal=explicit_proposal,
    )
    return proposal


def _project_research_proposal(
    *,
    assessment: Optional[Mapping[str, Any]] = None,
    rebalancing_base: Optional[Mapping[str, Any]] = None,
    explicit_proposal: Optional[Mapping[str, Any]] = None,
) -> Tuple[ResearchProposal, int]:
    if explicit_proposal is not None:
        if not isinstance(explicit_proposal, Mapping):
            raise ConstraintInputError("research proposal must be an object")
        actions_raw = explicit_proposal.get("actions")
        if actions_raw is None:
            actions_raw = explicit_proposal.get("suggestions")
        if actions_raw is None:
            actions_raw = explicit_proposal.get("positions")
        if not isinstance(actions_raw, Sequence) or isinstance(
            actions_raw, (str, bytes, bytearray)
        ):
            raise ConstraintInputError("proposal actions must be a list")
        return _proposal_from_rows(
            actions_raw,
            label=str(
                explicit_proposal.get("label") or explicit_proposal.get("name") or ""
            ).strip(),
        )

    if isinstance(rebalancing_base, Mapping):
        suggestions = _optional_sequence(rebalancing_base.get("suggestions"))
        bands = _optional_sequence(rebalancing_base.get("position_bands"))
        source = suggestions if suggestions else bands
        if source:
            return _proposal_from_rows(
                source,
                label=str(rebalancing_base.get("status") or "rebalance_scenario"),
            )

    if isinstance(assessment, Mapping):
        positions = _optional_sequence(assessment.get("positions"))
        if positions:
            return _proposal_from_rows(positions, label="assessment")
    return ResearchProposal(actions=()), 0


def _sectors_from_items(*groups: Any) -> Dict[str, str]:
    sectors: Dict[str, str] = {}
    for group in groups:
        if isinstance(group, Mapping):
            values = list(group.values())
            if values and all(not isinstance(item, Mapping) for item in values):
                for raw_symbol, raw_sector in group.items():
                    text = str(raw_sector or "").strip()
                    symbol = str(raw_symbol or "").strip().upper()
                    if symbol and text:
                        sectors.setdefault(symbol, text)
                continue
            group = [group]
        if not isinstance(group, Sequence) or isinstance(group, (str, bytes, bytearray)):
            continue
        for item in group:
            if not isinstance(item, Mapping):
                continue
            symbol = _symbol_from_item(item).upper()
            text = str(item.get("sector") or "").strip()
            if symbol and text:
                sectors.setdefault(symbol, text)
    return sectors


def portfolio_view_from_research_context(
    *,
    portfolio: Any = None,
    rebalancing_base: Optional[Mapping[str, Any]] = None,
    assessment: Optional[Mapping[str, Any]] = None,
    risk_flags: Any = None,
) -> PortfolioView:
    """Project the live research context into a portfolio view."""

    extra_sectors: Dict[str, str] = {}
    if isinstance(rebalancing_base, Mapping):
        current = _as_mapping(rebalancing_base.get("current")) or {}
        extra_sectors.update(
            _sectors_from_items(
                rebalancing_base.get("sectors"),
                current.get("weights"),
                rebalancing_base.get("suggestions"),
                rebalancing_base.get("position_bands"),
            )
        )
    if isinstance(assessment, Mapping):
        extra_sectors.update(_sectors_from_items(assessment.get("positions")))

    explicit = _as_mapping(portfolio)
    if explicit is not None:
        view = portfolio_view_from_mapping(explicit)
    elif isinstance(rebalancing_base, Mapping):
        current = _as_mapping(rebalancing_base.get("current")) or {}
        view = portfolio_view_from_mapping(
            {
                "weights": current.get("weights"),
                "sectors": extra_sectors,
                "risk_flags": rebalancing_base.get("risk_flags") or {},
                "weights_known": True,
            }
        )
    else:
        view = PortfolioView(weights_known=False, sectors=extra_sectors)

    merged_sectors = dict(view.normalized_sectors())
    for symbol, sector in extra_sectors.items():
        merged_sectors.setdefault(symbol, sector)

    extra_flags = _risk_flags_from_agent(risk_flags)
    merged_flags = dict(view.normalized_risk_flags())
    for symbol, flags in extra_flags.items():
        existing = list(merged_flags.get(symbol, ()))
        for flag in flags:
            if flag not in existing:
                existing.append(flag)
        merged_flags[symbol] = tuple(existing)
    return PortfolioView(
        weights_pct=view.normalized_weights(),
        sectors=merged_sectors,
        risk_flags=merged_flags,
        weights_known=view.weights_known,
    )


def _risk_flags_from_agent(raw: Any) -> Dict[str, Tuple[str, ...]]:
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        return portfolio_view_from_mapping({"risk_flags": raw}).normalized_risk_flags()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return {}
    flags: Dict[str, List[str]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        symbol = _symbol_from_item(item)
        if not symbol:
            continue
        flag = str(
            item.get("flag")
            or item.get("code")
            or item.get("type")
            or item.get("name")
            or ""
        ).strip().lower()
        if not flag:
            continue
        flags.setdefault(symbol.upper(), []).append(flag)
    return {symbol: tuple(values) for symbol, values in flags.items()}


def _config_from_input(raw: Any) -> ConstraintConfig:
    if raw is None:
        return ConstraintConfig()
    if isinstance(raw, ConstraintConfig):
        return raw
    if isinstance(raw, Mapping):
        return load_constraint_config(raw)
    raise ConstraintInputError("constraint config must be an object")


def evaluate_research_scenario(
    *,
    portfolio: Any = None,
    proposal: Any = None,
    config: Any = None,
    rebalancing_base: Optional[Mapping[str, Any]] = None,
    assessment: Optional[Mapping[str, Any]] = None,
    risk_flags: Any = None,
) -> Dict[str, Any]:
    """Production entry: run one research proposal/scenario through the engine.

    Always fail-closed. The returned payload is never an executable broker
    order: ``executable`` / ``auto_execute`` stay false even on ``allow``.
    """

    try:
        view = (
            portfolio
            if isinstance(portfolio, PortfolioView)
            else portfolio_view_from_research_context(
                portfolio=portfolio,
                rebalancing_base=rebalancing_base,
                assessment=assessment,
                risk_flags=risk_flags,
            )
        )
        if isinstance(proposal, ResearchProposal):
            typed_proposal = proposal
            candidate_count = len(proposal.actions)
        else:
            typed_proposal, candidate_count = _project_research_proposal(
                assessment=assessment,
                rebalancing_base=rebalancing_base,
                explicit_proposal=_as_mapping(proposal),
            )
        typed_config = _config_from_input(config)
        if not typed_proposal.actions:
            if candidate_count > 0:
                verdict = ConstraintVerdict(
                    status=STATUS_REJECT,
                    label=LABEL_RESEARCH_ONLY,
                    findings=(
                        ConstraintFinding(
                            constraint="unparseable_proposal",
                            severity=SEVERITY_BLOCKING,
                            symbol=None,
                            reason=(
                                "Proposal rows were present but none could be "
                                "normalized into actions; the scenario is "
                                "research-only until the engine can evaluate it."
                            ),
                        ),
                    ),
                    constraints_evaluated=typed_config.normalized().constraint_count,
                    passthrough=False,
                    passthrough_reason=PASSTHROUGH_REASON_UNPARSEABLE_PROPOSAL,
                )
            else:
                verdict = ConstraintVerdict(
                    status="allow",
                    label=LABEL_CONSTRAINT_FEASIBLE,
                    findings=(),
                    constraints_evaluated=typed_config.normalized().constraint_count,
                    passthrough=typed_config.normalized().constraint_count == 0,
                    passthrough_reason=(
                        PASSTHROUGH_REASON_NO_CONSTRAINTS
                        if typed_config.normalized().constraint_count == 0
                        else PASSTHROUGH_REASON_NO_PROPOSED_ACTIONS
                    ),
                )
        else:
            verdict = check_proposal_fail_closed(view, typed_proposal, typed_config)
    except Exception as exc:  # broad-exception: fallback_recorded - Presentation paths must never treat a gate error as feasible.
        log_safe_exception(
            logger,
            "Constraint scenario gate failed; labeling proposal research-only",
            exc,
            error_code="portfolio_constraint_scenario_error",
        )
        verdict = ConstraintVerdict(
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

    return _presentation_payload(verdict)


def _presentation_payload(verdict: ConstraintVerdict) -> Dict[str, Any]:
    payload = verdict.to_dict()
    payload.update(
        {
            "executable": False,
            "is_executable_scenario": False,
            "is_suggestion_only": True,
            "auto_execute": False,
            "not_broker_compliance": True,
            "disclaimer": NOT_BROKER_COMPLIANCE_DISCLAIMER,
            "scenario_label": verdict.label,
        }
    )
    return payload


def apply_constraints_to_research_assessment(
    assessment: Dict[str, Any],
    *,
    portfolio: Any = None,
    config: Any = None,
    proposal: Any = None,
    rebalancing_base: Optional[Mapping[str, Any]] = None,
    risk_flags: Any = None,
) -> Dict[str, Any]:
    """Label a live research assessment with the deterministic constraint verdict.

    Violating proposals are marked ``research_only`` / non-executable. Feasible
    proposals receive ``constraint_feasible`` but remain suggestion-only and
    are still not broker compliance.
    """

    if not isinstance(assessment, dict):
        raise ConstraintInputError("assessment must be a dict")

    result = evaluate_research_scenario(
        portfolio=portfolio,
        proposal=proposal,
        config=config,
        rebalancing_base=rebalancing_base,
        assessment=assessment,
        risk_flags=risk_flags,
    )
    assessment["constraint_check"] = result
    assessment["scenario_label"] = result["scenario_label"]
    assessment["constraint_feasible"] = result["label"] == LABEL_CONSTRAINT_FEASIBLE
    assessment["constraint_passthrough"] = bool(result.get("passthrough"))
    if result.get("passthrough_reason"):
        assessment["constraint_passthrough_reason"] = result["passthrough_reason"]
    assessment["is_executable"] = False
    assessment["is_executable_scenario"] = False
    assessment["not_broker_compliance"] = True

    existing = str(assessment.get("disclaimer") or "").strip()
    extras = []
    if NOT_BROKER_COMPLIANCE_DISCLAIMER not in existing:
        extras.append(NOT_BROKER_COMPLIANCE_DISCLAIMER)
    if assessment.get("constraint_passthrough") and PASSTHROUGH_DISCLAIMER not in existing:
        extras.append(PASSTHROUGH_DISCLAIMER)
    if extras:
        assessment["disclaimer"] = (
            f"{existing} {' '.join(extras)}".strip() if existing else " ".join(extras)
        )

    if result["status"] == STATUS_REJECT:
        suggestions = assessment.get("rebalance_suggestions")
        if isinstance(suggestions, list):
            assessment["rebalance_suggestions"] = [
                _mark_research_only(item) for item in suggestions
            ]
        det = assessment.get("deterministic_rebalancing")
        if isinstance(det, dict):
            det["constraint_check"] = result
            det["auto_execute"] = False
            det["is_suggestion_only"] = True
    return assessment


def _mark_research_only(item: Any) -> Any:
    if isinstance(item, str):
        if item.startswith("[research_only]"):
            return item
        return f"[research_only] {item}"
    return item
