# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Strict contracts for the offline financial-agent output evaluator."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )


class FinancialFact(_StrictModel):
    fact_id: str = Field(min_length=1, max_length=128)
    field_path: str = Field(min_length=1, max_length=256)
    value: float
    unit: str = Field(min_length=1, max_length=64)
    as_of: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)


class FinancialClaim(_StrictModel):
    claim_id: str = Field(min_length=1, max_length=128)
    source_fact_id: str = Field(min_length=1, max_length=128)
    field_path: str = Field(min_length=1, max_length=256)
    value: float
    unit: str = Field(min_length=1, max_length=64)
    as_of: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=128)


class ToolCallOutcome(_StrictModel):
    tool: Optional[str] = Field(default=None, min_length=1, max_length=128)
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    attempted: bool
    completed: bool
    succeeded: bool
    valid_result: bool
    authorized: bool

    @model_validator(mode="after")
    def require_one_name(self) -> "ToolCallOutcome":
        if (self.tool is None) == (self.name is None):
            raise ValueError("exactly one of tool or name is required")
        return self


class EvidencePolarity(_StrictModel):
    polarity: Optional[str] = Field(default=None, min_length=1, max_length=64)
    sentiment: Optional[str] = Field(default=None, min_length=1, max_length=64)
    direction: Optional[str] = Field(default=None, min_length=1, max_length=64)
    stance: Optional[str] = Field(default=None, min_length=1, max_length=64)
    label: Optional[str] = Field(default=None, min_length=1, max_length=64)
    note: Optional[str] = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_one_label(self) -> "EvidencePolarity":
        if sum(value is not None for value in (
            self.polarity, self.sentiment, self.direction, self.stance
        )) != 1:
            raise ValueError("exactly one evidence polarity label is required")
        return self


class LLMJudgement(_StrictModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    detail: str = Field(min_length=1, max_length=500)
    judge_id: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=128)
    rubric_version: str = Field(min_length=1, max_length=128)
    as_of: str = Field(min_length=1, max_length=64)


class FactualityRubric(_StrictModel):
    required_claim_ids: List[str] = Field(default_factory=list, max_length=128)


class ToolUsageRubric(_StrictModel):
    required_tools: List[str] = Field(default_factory=list, max_length=128)
    forbidden_tools: List[str] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def require_constraint(self) -> "ToolUsageRubric":
        if not self.required_tools and not self.forbidden_tools:
            raise ValueError("at least one tool constraint is required")
        return self


class ConclusionConsistencyRubric(_StrictModel):
    expected_signal: Optional[str] = Field(default=None, min_length=1, max_length=64)


class BoundaryHonestyRubric(_StrictModel):
    data_missing: bool = False
    tools_failed: bool = False
    failed_tools: List[str] = Field(default_factory=list, max_length=128)
    require_limitation_mention: bool = True
    require_risk_warning: bool = False
    forbid_directional_when_missing: bool = False


class LanguageFormatRubric(_StrictModel):
    required_fields: List[str] = Field(default_factory=list, max_length=128)
    required_substrings: List[str] = Field(default_factory=list, max_length=128)
    forbidden_substrings: List[str] = Field(default_factory=list, max_length=128)
    expect_json_object: bool = False

    @model_validator(mode="after")
    def require_constraint(self) -> "LanguageFormatRubric":
        if not any((self.required_fields, self.required_substrings,
                    self.forbidden_substrings, self.expect_json_object)):
            raise ValueError("at least one format constraint is required")
        return self


class LLMRubric(_StrictModel):
    """Marker contract: the external versioned judge owns subjective criteria."""


class AgentEvalCase(_StrictModel):
    id: str = Field(min_length=1, max_length=128)
    title: Optional[str] = Field(default=None, max_length=256)
    tags: List[str] = Field(default_factory=list, max_length=32)
    dimensions: List[
        Literal[
            "factuality",
            "tool_usage",
            "conclusion_consistency",
            "boundary_honesty",
            "language_format",
            "explanation_clarity",
            "risk_framing_quality",
        ]
    ] = Field(min_length=1, max_length=7)
    context: Dict[str, Any]
    agent_output: Dict[str, Any]
    evaluation: Dict[str, Dict[str, Any]]
    agent_version: Optional[str] = Field(default=None, min_length=1, max_length=128)
    config_version: Optional[str] = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_unique_dimensions_and_rubrics(self) -> "AgentEvalCase":
        if len(self.dimensions) != len(set(self.dimensions)):
            raise ValueError("dimensions must be unique")
        if not self.agent_output:
            raise ValueError("agent_output must not be empty")
        if set(self.evaluation) != set(self.dimensions):
            raise ValueError("evaluation keys must exactly match dimensions")
        return self


class ComparisonPolicy(_StrictModel):
    rule_weighting: Literal["micro_average_checks"] = "micro_average_checks"
    missing_dimension_policy: Literal["missing_candidate_dimension_scores_zero"] = (
        "missing_candidate_dimension_scores_zero"
    )
    confidence_method: Literal["deterministic_frozen_panel_no_interval"] = (
        "deterministic_frozen_panel_no_interval"
    )
    regression_threshold: float = Field(default=0.0, ge=0.0)
