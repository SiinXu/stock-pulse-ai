# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Allowlisted prediction get/list API schemas (Issue #1102 leftover query)."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AgentPredictionHorizon = Literal["1d", "3d", "5d", "10d", "20d"]
AgentPredictionStatus = Literal[
    "pending",
    "resolving",
    "resolved",
    "data_unavailable",
    "expired",
    "error",
    "no_verifiable_claim",
]
AgentPredictionOutcomeLabel = Literal["hit", "miss", "partial", "data_unavailable"]


class AgentPredictionListQuery(BaseModel):
    """Identity-filtered list query. Exactly one mode: run_id XOR symbol+market."""

    model_config = ConfigDict(extra="forbid")

    run_id: Optional[str] = Field(
        default=None, min_length=1, max_length=128, pattern=r"^\S+$"
    )
    symbol: Optional[str] = Field(
        default=None, min_length=1, max_length=32, pattern=r"^\S+$"
    )
    market: Optional[str] = Field(
        default=None, min_length=1, max_length=16, pattern=r"^\S+$"
    )
    limit: int = Field(default=50, ge=1, le=50)

    @field_validator("market")
    @classmethod
    def _normalize_market(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.lower()

    @model_validator(mode="after")
    def _exactly_one_identity_mode(self) -> "AgentPredictionListQuery":
        has_run = self.run_id is not None
        has_symbol = self.symbol is not None
        has_market = self.market is not None
        run_mode = has_run and not has_symbol and not has_market
        symbol_mode = (not has_run) and has_symbol and has_market
        if run_mode or symbol_mode:
            return self
        raise ValueError(
            "Provide exactly one identity filter: run_id, or both symbol and market"
        )


class AgentPredictionItem(BaseModel):
    """Public prediction identity, status, and bounded outcome label."""

    model_config = ConfigDict(extra="forbid")

    prediction_id: str = Field(min_length=1, max_length=128, pattern=r"^\S+$")
    run_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=32)
    market: str = Field(min_length=1, max_length=16)
    as_of: str = Field(min_length=1, max_length=32)
    horizon: AgentPredictionHorizon
    resolve_after: str = Field(min_length=1, max_length=64)
    status: AgentPredictionStatus
    outcome_label: Optional[AgentPredictionOutcomeLabel]
    created_at: str = Field(min_length=1, max_length=64)
    updated_at: str = Field(min_length=1, max_length=64)
    resolved_at: Optional[str] = Field(max_length=64)


class AgentPredictionListResponse(BaseModel):
    """Identity-filtered prediction page. No total count or cursor in this slice."""

    model_config = ConfigDict(extra="forbid")

    items: List[AgentPredictionItem]
    truncated: bool
