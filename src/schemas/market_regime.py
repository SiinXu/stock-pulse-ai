# -*- coding: utf-8 -*-
"""Versioned market-regime context: explainable labels with traceable evidence."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


MARKET_REGIME_SCHEMA_VERSION = "market-regime-v1"
MARKET_REGIME_CONTEXT_KEY = "market_regime_context"

RegimeLabel = Literal[
    "trending_up",
    "trending_down",
    "sideways",
    "volatile",
    "unknown",
]
RegimeStatus = Literal["ok", "partial", "unknown"]
RegimeSource = Literal["rules", "override", "unavailable"]
RiskPosture = Literal["risk_on", "neutral", "risk_off", "unknown"]
RuleOutcome = Literal["matched", "not_matched", "insufficient_data", "applied"]

KNOWN_REGIME_LABELS = frozenset(
    {
        "trending_up",
        "trending_down",
        "sideways",
        "volatile",
        "unknown",
    }
)


class RegimeEvidenceRule(BaseModel):
    """One deterministic rule evaluation step that can be audited later."""

    rule_id: str = Field(..., min_length=1, description="Stable rule identifier")
    description: str = Field(..., min_length=1, description="Human-readable rule purpose")
    outcome: RuleOutcome = Field(..., description="Whether the rule matched or could not run")
    inputs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Inputs inspected by this rule (low-sensitivity scalars only)",
    )
    detail: Optional[str] = Field(
        None,
        description="Optional short explanation for the outcome",
    )


class MarketRegimeContext(BaseModel):
    """Explainable market-regime snapshot for prompts, skills, and history."""

    schema_version: str = MARKET_REGIME_SCHEMA_VERSION
    regime: RegimeLabel = "unknown"
    status: RegimeStatus = "unknown"
    source: RegimeSource = "unavailable"
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    risk_posture: RiskPosture = "unknown"
    rules_fired: List[str] = Field(
        default_factory=list,
        description="rule_id values that matched and contributed to the decision",
    )
    evidence: List[RegimeEvidenceRule] = Field(default_factory=list)
    focus_hints: List[str] = Field(
        default_factory=list,
        description="Analysis focus adjustments for the detected (or unknown) regime",
    )
    missing_inputs: List[str] = Field(default_factory=list)
    override: Optional[str] = Field(
        None,
        description="Configured override label when source is override",
    )
    stock_code: Optional[str] = None
    market: Optional[str] = None
    method: str = Field(
        "deterministic_rules_v1",
        description="Detection method id for artifact provenance",
    )


def dump_market_regime_model(model: BaseModel) -> Dict[str, Any]:
    """Return a low-sensitivity dict using stable snake_case keys."""
    return model.model_dump(exclude_none=True)
