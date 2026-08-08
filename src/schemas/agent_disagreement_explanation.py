# -*- coding: utf-8 -*-
"""Public low-sensitivity multi-agent final-disagreement explanation schema."""
from __future__ import annotations
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentOpinionExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: str = Field(min_length=1)
    signal: Literal["buy", "hold", "sell"]
    confidence: float = Field(ge=0, le=1)


class BaseAgentDisagreement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal[
        "insufficient_opinions",
        "aligned_bullish",
        "aligned_bearish",
        "aligned_neutral",
        "bullish_with_neutral",
        "bearish_with_neutral",
        "mixed_directional_signals",
    ]
    agents: List[AgentOpinionExplanation] = Field(default_factory=list)


class RiskControlExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_present: bool
    override_enabled: bool
    trigger: Literal["none", "risk_veto", "risk_downgrade"]
    applied: bool
    reason: str = Field(min_length=1)
    post_risk_signal: Literal["buy", "hold", "sell"]
    from_signal: Optional[Literal["buy", "hold", "sell"]] = None
    to_signal: Optional[Literal["buy", "hold", "sell"]] = None

    @model_validator(mode="after")
    def validate_transition(self) -> "RiskControlExplanation":
        if self.applied:
            if not self.from_signal or not self.to_signal:
                raise ValueError("applied risk control requires a signal transition")
            if self.from_signal == self.to_signal or self.to_signal != self.post_risk_signal:
                raise ValueError("risk control transition must end at post_risk_signal")
        elif self.from_signal is not None or self.to_signal is not None:
            raise ValueError("non-applied risk control cannot carry a transition")
        return self


class DegradedEventExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: str = Field(min_length=1)
    reason: Literal["timeout", "budget_skip", "stage_failure"]
    boundary: Literal["during_stage", "before_stage"]


class PipelineTerminationExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["timeout"]
    last_completed_stage: Optional[str] = None


class PipelineActionAdjustmentExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["structure_and_fundamentals", "market_phase", "daily_market_context"]
    from_action: Literal["buy", "add", "hold", "reduce", "sell", "watch", "avoid", "alert"]
    to_action: Literal["buy", "add", "hold", "reduce", "sell", "watch", "avoid", "alert"]

    @model_validator(mode="after")
    def validate_change(self) -> "PipelineActionAdjustmentExplanation":
        if self.from_action == self.to_action:
            raise ValueError("pipeline adjustment must change the action")
        return self


class AgentDataQualityExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: Literal["good", "usable", "limited", "poor", "unknown"]
    limitations: List[str] = Field(default_factory=list, max_length=5)


class AgentDisagreementExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_disagreement: BaseAgentDisagreement
    risk_control: RiskControlExplanation
    degraded_events: List[DegradedEventExplanation] = Field(default_factory=list)
    pipeline_termination: Optional[PipelineTerminationExplanation] = None
    data_quality: Optional[AgentDataQualityExplanation] = None
    pipeline_start_action: Literal["buy", "add", "hold", "reduce", "sell", "watch", "avoid", "alert"]
    final_adjustments: List[PipelineActionAdjustmentExplanation] = Field(default_factory=list)
    final_action: Literal["buy", "add", "hold", "reduce", "sell", "watch", "avoid", "alert"]
    decision_path: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_final_action_chain(self) -> "AgentDisagreementExplanation":
        expected = self.pipeline_start_action
        for adjustment in self.final_adjustments:
            if adjustment.from_action != expected:
                raise ValueError("pipeline adjustment chain is discontinuous")
            expected = adjustment.to_action
        if expected != self.final_action:
            raise ValueError("final_action must match the completed adjustment chain")
        return self
