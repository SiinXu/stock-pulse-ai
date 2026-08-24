# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Allowlisted prediction-resolver diagnostics response models."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class PredictionResolverOldestDueItem(BaseModel):
    """Identity and lag for one currently claimable due prediction."""

    model_config = ConfigDict(extra="forbid")

    prediction_id: str
    symbol: str
    market: str
    status: str
    resolve_after: str
    lag_seconds: float = Field(ge=0)


class PredictionResolverResolvedUtcDayCounts(BaseModel):
    """Store-backed durable outcome mix for one UTC civil day."""

    model_config = ConfigDict(extra="forbid")

    hit: int = Field(ge=0)
    miss: int = Field(ge=0)
    partial: int = Field(ge=0)
    unavailable: int = Field(ge=0)
    unlabeled: int = Field(ge=0)


class PredictionResolverDiagnosticsResponse(BaseModel):
    """Read-only claimable-due diagnostics for this API process."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    interval_seconds: int
    this_process_worker_registered: bool
    observed_at: str
    claimable_due_count: int = Field(ge=0)
    claimable_due_truncated: bool
    claimable_due_probe_limit: int = Field(ge=1)
    oldest_due: List[PredictionResolverOldestDueItem]
    resolved_utc_day_start: str
    resolved_utc_day_end: str
    resolved_utc_day_counts: PredictionResolverResolvedUtcDayCounts
