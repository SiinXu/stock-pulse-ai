# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded schemas for the revisioned watchlist-group aggregate."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from src.repositories.watchlist_group_repo import (
    MAX_GROUPS,
    MAX_MEMBERS_PER_GROUP,
    MAX_TOTAL_MEMBERSHIPS,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WatchlistComputedAttrsSchema(_StrictModel):
    """Read-only computed projection owned by T25/T26 services."""

    schema_version: Literal[1] = 1
    ai_score: Optional[FiniteFloat] = Field(default=None, ge=0, le=100)
    focus: Optional[bool] = None


class WatchlistGroupMemberSchema(_StrictModel):
    stock_code: str = Field(..., min_length=1, max_length=32)
    sort_order: int = Field(..., ge=0)
    attrs: WatchlistComputedAttrsSchema = Field(default_factory=WatchlistComputedAttrsSchema)


class WatchlistGroupSchema(_StrictModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=80)
    name_key: Optional[str] = Field(default=None, max_length=128)
    sort_order: int = Field(..., ge=0)
    is_default: bool
    created_at: datetime
    updated_at: datetime
    members: List[WatchlistGroupMemberSchema] = Field(
        default_factory=list, max_length=MAX_MEMBERS_PER_GROUP
    )


class WatchlistGroupsResponse(_StrictModel):
    revision: int = Field(..., ge=1)
    groups: List[WatchlistGroupSchema] = Field(default_factory=list, max_length=MAX_GROUPS)
    message: str = Field(..., max_length=160)

    @model_validator(mode="after")
    def validate_total_memberships(self) -> "WatchlistGroupsResponse":
        if sum(len(group.members) for group in self.groups) > MAX_TOTAL_MEMBERSHIPS:
            raise ValueError("watchlist group response exceeds membership limit")
        return self


class _RevisionedRequest(_StrictModel):
    expected_revision: int = Field(..., ge=1)


class WatchlistGroupCreateRequest(_RevisionedRequest):
    name: str = Field(..., min_length=1, max_length=80)


class WatchlistGroupRenameRequest(_RevisionedRequest):
    name: str = Field(..., min_length=1, max_length=80)


class WatchlistGroupReorderRequest(_RevisionedRequest):
    ordered_ids: List[str] = Field(..., min_length=1, max_length=MAX_GROUPS)


class WatchlistGroupMemberAddRequest(_RevisionedRequest):
    stock_code: str = Field(..., min_length=1, max_length=32)


class WatchlistGroupMemberReorderRequest(_RevisionedRequest):
    ordered_codes: List[str] = Field(..., min_length=1, max_length=MAX_MEMBERS_PER_GROUP)


class WatchlistGroupMemberMoveRequest(_RevisionedRequest):
    stock_code: str = Field(..., min_length=1, max_length=32)
    source_group_id: str = Field(..., min_length=1, max_length=64)
    target_group_id: str = Field(..., min_length=1, max_length=64)
    target_index: Optional[int] = Field(default=None, ge=0, lt=MAX_MEMBERS_PER_GROUP)
    copy_membership: bool = False
