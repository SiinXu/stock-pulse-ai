# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Strict contracts for owner-scoped Human-in-the-Loop approvals."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


APPROVAL_ACTION_RISK_CONTROL_BYPASS: Literal["risk_control_bypass"] = (
    "risk_control_bypass"
)
LOCAL_ADMIN_OWNER = "local_admin"
DEFAULT_APPROVAL_EXPIRES_IN_SECONDS = 300
MIN_APPROVAL_EXPIRES_IN_SECONDS = 30
MAX_APPROVAL_EXPIRES_IN_SECONDS = 3600
APPROVAL_MAX_PAGE_SIZE = 100
APPROVAL_CONTEXT_MAX_SUMMARY = 240


class ApprovalStatus(str, Enum):
    """Durable proposal states; terminal states never transition again."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalRiskSource(str, Enum):
    """Existing risk-control categories that may request a bypass."""

    RISK_VETO = "risk_veto"
    RISK_DOWNGRADE = "risk_downgrade"


class ApprovalDecision(str, Enum):
    """Administrator decisions accepted by the transition endpoint."""

    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ApprovalContext(_StrictModel):
    """Bounded, redacted context safe for the administrator UI."""

    stock_code: str = Field(default="", max_length=32)
    original_signal: Literal["buy", "hold", "sell"]
    conservative_signal: Literal["buy", "hold", "sell"]
    risk_source: ApprovalRiskSource
    risk_summary: str = Field(min_length=1, max_length=APPROVAL_CONTEXT_MAX_SUMMARY)

    @field_validator("stock_code", "risk_summary")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return value.strip()


class ApprovalRule(_StrictModel):
    """Persisted rule controlling one approval action."""

    owner: str = Field(min_length=1, max_length=128)
    action: Literal["risk_control_bypass"] = APPROVAL_ACTION_RISK_CONTROL_BYPASS
    enabled: bool
    risk_sources: list[ApprovalRiskSource] = Field(min_length=1, max_length=2)
    expires_in_seconds: int = Field(
        ge=MIN_APPROVAL_EXPIRES_IN_SECONDS,
        le=MAX_APPROVAL_EXPIRES_IN_SECONDS,
    )
    version: int = Field(ge=0)
    updated_at: datetime | None = None

    @field_validator("risk_sources")
    @classmethod
    def _risk_sources_are_unique(
        cls,
        value: list[ApprovalRiskSource],
    ) -> list[ApprovalRiskSource]:
        if len(set(value)) != len(value):
            raise ValueError("approval risk sources must be unique")
        return value


class ApprovalProposal(_StrictModel):
    """Public low-sensitivity view of a durable approval proposal."""

    id: str = Field(min_length=32, max_length=32)
    owner: str = Field(min_length=1, max_length=128)
    status: ApprovalStatus
    version: int = Field(ge=1)
    expires_at: datetime
    consumed_at: datetime | None = None
    context: ApprovalContext


class ApprovalProposalPage(_StrictModel):
    items: list[ApprovalProposal]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=APPROVAL_MAX_PAGE_SIZE)
    total: int = Field(ge=0)


ApprovalStatusFilter = Literal[
    "pending",
    "approved",
    "rejected",
    "expired",
    "cancelled",
]
