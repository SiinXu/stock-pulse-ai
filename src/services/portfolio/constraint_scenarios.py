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

NOT_BROKER_COMPLIANCE_DISCLAIMER = (
    "Constraint checks are a deterministic research aid. They do not execute "
    "trades, are not broker, exchange, or regulatory compliance, and never "
    "make a scenario executable as an order."
)

PASSTHROUGH_REASON_NO_PROPOSED_ACTIONS = "no_proposed_actions"


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


def _actions_from_sequence(raw_actions: Sequence[Any]) -> List[ProposedAction]:
    actions: List[ProposedAction] = []
    for item in raw_actions:
        if not isinstance(item, Mapping):
            continue
        symbol = _symbol_from_item(item)
        # PortfolioAgent positions emit `signal`; rebalancing suggestions emit `action`.
        action = str(item.get("action") or item.get("signal") or "").strip()
        if not symbol or not action:
            continue
        target = _weight_pct_from_item(item)
        sector = item.get("sector")
        actions.append(
            ProposedAction(
                symbol=symbol,
                action=action,
                target_weight_pct=target,
                sector=str(sector).strip() if sector not in (None, "") else None,
            )
        )
    return actions


def research_proposal_from_mapping(raw: Optional[Mapping[str, Any]]) -> ResearchProposal:
    """Project a research proposal / scenario mapping into typed actions."""

    if raw is None:
        return ResearchProposal(actions=())
    if not isinstance(raw, Mapping):
        raise ConstraintInputError("research proposal must be an object")
    actions_raw = raw.get("actions")
    if actions_raw is None:
        actions_raw = raw.get("suggestions")
    if actions_raw is None:
        actions_raw = raw.get("positions")
    if not isinstance(actions_raw, Sequence) or isinstance(
        actions_raw, (str, bytes, bytearray)
    ):
        raise ConstraintInputError("proposal actions must be a list")
    return ResearchProposal(
        actions=tuple(_actions_from_sequence(actions_raw)),
        label=str(raw.get("label") or raw.get("name") or "").strip(),
    )


def research_proposal_from_assessment(
    assessment: Optional[Mapping[str, Any]],
    *,
    rebalancing_base: Optional[Mapping[str, Any]] = None,
    explicit_proposal: Optional[Mapping[str, Any]] = None,
) -> ResearchProposal:
    """Build the proposal that the live research path actually presents.

    Preference order:
    1. An explicit research proposal mapping.
    2. Deterministic rebalancing suggestions / position bands.
    3. Assessment positions already overwritten by the deterministic base.
    """

    if explicit_proposal is not None:
        return research_proposal_from_mapping(explicit_proposal)

    if isinstance(rebalancing_base, Mapping):
        suggestions = rebalancing_base.get("suggestions") or []
        bands = rebalancing_base.get("position_bands") or []
        actions = _actions_from_sequence(
            list(suggestions) + list(bands) if isinstance(suggestions, Sequence) else list(bands)
        )
        if actions:
            return ResearchProposal(
                actions=tuple(actions),
                label=str(rebalancing_base.get("status") or "rebalance_scenario"),
            )

    if isinstance(assessment, Mapping):
        positions = assessment.get("positions")
        if isinstance(positions, Sequence) and not isinstance(
            positions, (str, bytes, bytearray)
        ):
            actions = _actions_from_sequence(positions)
            if actions:
                return ResearchProposal(actions=tuple(actions), label="assessment")
    return ResearchProposal(actions=())


def portfolio_view_from_research_context(
    *,
    portfolio: Any = None,
    rebalancing_base: Optional[Mapping[str, Any]] = None,
    risk_flags: Any = None,
) -> PortfolioView:
    """Project the live research context into a portfolio view."""

    explicit = _as_mapping(portfolio)
    if explicit is not None:
        view = portfolio_view_from_mapping(explicit)
    elif isinstance(rebalancing_base, Mapping):
        current = _as_mapping(rebalancing_base.get("current")) or {}
        view = portfolio_view_from_mapping(
            {
                "weights": current.get("weights"),
                "sectors": (
                    explicit.get("sectors")
                    if explicit is not None
                    else (rebalancing_base.get("sectors") or {})
                ),
                "risk_flags": rebalancing_base.get("risk_flags") or {},
                "weights_known": True,
            }
        )
    else:
        view = PortfolioView(weights_known=False)

    extra_flags = _risk_flags_from_agent(risk_flags)
    if not extra_flags:
        return view
    merged = dict(view.normalized_risk_flags())
    for symbol, flags in extra_flags.items():
        existing = list(merged.get(symbol, ()))
        for flag in flags:
            if flag not in existing:
                existing.append(flag)
        merged[symbol] = tuple(existing)
    return PortfolioView(
        weights_pct=view.normalized_weights(),
        sectors=view.normalized_sectors(),
        risk_flags=merged,
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
                risk_flags=risk_flags,
            )
        )
        typed_proposal = (
            proposal
            if isinstance(proposal, ResearchProposal)
            else research_proposal_from_assessment(
                assessment,
                rebalancing_base=rebalancing_base,
                explicit_proposal=_as_mapping(proposal),
            )
        )
        typed_config = _config_from_input(config)
        if not typed_proposal.actions:
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
    except Exception as exc:  # broad-exception: fail_closed_verdict - Presentation paths must never treat a gate error as feasible.
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
    assessment["is_executable"] = False
    assessment["is_executable_scenario"] = False
    assessment["not_broker_compliance"] = True

    existing = str(assessment.get("disclaimer") or "").strip()
    if NOT_BROKER_COMPLIANCE_DISCLAIMER not in existing:
        assessment["disclaimer"] = (
            f"{existing} {NOT_BROKER_COMPLIANCE_DISCLAIMER}".strip()
            if existing
            else NOT_BROKER_COMPLIANCE_DISCLAIMER
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
