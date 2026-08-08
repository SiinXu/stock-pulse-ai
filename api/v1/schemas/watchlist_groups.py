# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Schemas for watchlist group organization APIs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class WatchlistGroupMemberSchema(BaseModel):
    """One symbol membership inside a group."""

    stock_code: str = Field(..., description="Stock code as stored in the watchlist")
    sort_order: int = Field(..., description="Order inside the group (ascending)")
    attrs: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Extensible computed-attribute mount point for future watchlist "
            "features (e.g. AI score, focus flag). Empty object by default."
        ),
    )


class WatchlistGroupSchema(BaseModel):
    """Watchlist group with ordered members."""

    id: str = Field(..., description="Stable group key")
    name: str = Field(..., description="Display name")
    sort_order: int = Field(..., description="Group order (ascending)")
    is_default: bool = Field(..., description="Whether this is the auto-seeded default group")
    created_at: str = Field(..., description="ISO created timestamp")
    updated_at: str = Field(..., description="ISO updated timestamp")
    members: List[WatchlistGroupMemberSchema] = Field(default_factory=list)


class WatchlistGroupsResponse(BaseModel):
    """List of watchlist groups."""

    groups: List[WatchlistGroupSchema] = Field(default_factory=list)
    message: str = Field(..., description="Operation result description")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "groups": [
                    {
                        "id": "default",
                        "name": "Default",
                        "sort_order": 0,
                        "is_default": True,
                        "created_at": "2026-08-09T00:00:00",
                        "updated_at": "2026-08-09T00:00:00",
                        "members": [
                            {"stock_code": "600519", "sort_order": 0, "attrs": {}},
                        ],
                    }
                ],
                "message": "2 groups",
            }
        }
    )


class WatchlistGroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="New group name")


class WatchlistGroupRenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Updated group name")


class WatchlistGroupReorderRequest(BaseModel):
    ordered_ids: List[str] = Field(
        ...,
        min_length=1,
        description="Group ids in desired order",
    )


class WatchlistGroupMemberAddRequest(BaseModel):
    stock_code: str = Field(..., min_length=1, description="Stock code to add to the group")
    attrs: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional attrs payload (T25/T26 mount). Defaults to empty object.",
    )


class WatchlistGroupMemberReorderRequest(BaseModel):
    ordered_codes: List[str] = Field(
        ...,
        min_length=1,
        description="Stock codes in desired order within the group",
    )


class WatchlistGroupMemberMoveRequest(BaseModel):
    stock_code: str = Field(..., min_length=1)
    source_group_id: str = Field(..., min_length=1)
    target_group_id: str = Field(..., min_length=1)
    target_index: Optional[int] = Field(
        default=None,
        ge=0,
        description="Optional insert index inside the target group",
    )
    copy_membership: bool = Field(
        default=False,
        description="When true, keep the source membership (multi-group). Default moves.",
    )
