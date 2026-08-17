# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API DTOs for administrator Human-in-the-Loop approvals."""

from __future__ import annotations

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
)

from src.schemas.approvals import (
    ApprovalDecision,
    ApprovalProposal,
    ApprovalProposalPage,
    ApprovalRiskSource,
    ApprovalRule,
    MAX_APPROVAL_EXPIRES_IN_SECONDS,
    MIN_APPROVAL_EXPIRES_IN_SECONDS,
)


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApprovalRuleUpdateRequest(_StrictRequest):
    enabled: StrictBool
    risk_sources: list[ApprovalRiskSource] = Field(min_length=1, max_length=2)
    expires_in_seconds: StrictInt = Field(
        ge=MIN_APPROVAL_EXPIRES_IN_SECONDS,
        le=MAX_APPROVAL_EXPIRES_IN_SECONDS,
    )
    expected_version: StrictInt = Field(
        ge=0,
        validation_alias=AliasChoices("expectedVersion", "expected_version"),
        serialization_alias="expectedVersion",
    )

    @field_validator("risk_sources")
    @classmethod
    def _risk_sources_are_unique(
        cls,
        value: list[ApprovalRiskSource],
    ) -> list[ApprovalRiskSource]:
        if len(set(value)) != len(value):
            raise ValueError("approval risk sources must be unique")
        return value


class ApprovalDecisionRequest(_StrictRequest):
    decision: ApprovalDecision
    expected_version: StrictInt = Field(
        ge=1,
        validation_alias=AliasChoices("expectedVersion", "expected_version"),
        serialization_alias="expectedVersion",
    )


__all__ = [
    "ApprovalDecisionRequest",
    "ApprovalProposal",
    "ApprovalProposalPage",
    "ApprovalRule",
    "ApprovalRuleUpdateRequest",
]
