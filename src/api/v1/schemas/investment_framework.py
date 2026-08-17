# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API schemas for the versioned personal investment framework."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.investment_framework import InvestmentFrameworkContent


class InvestmentFrameworkCreateRequest(BaseModel):
    content: InvestmentFrameworkContent
    change_summary: Optional[str] = Field(None, min_length=1, max_length=500)

    model_config = ConfigDict(
        extra="forbid",
        revalidate_instances="always",
        strict=True,
    )


class InvestmentFrameworkUpdateRequest(BaseModel):
    expected_revision: int = Field(..., ge=1)
    content: InvestmentFrameworkContent
    change_summary: Optional[str] = Field(None, min_length=1, max_length=500)

    model_config = ConfigDict(
        extra="forbid",
        revalidate_instances="always",
        strict=True,
    )


class InvestmentFrameworkDeactivateRequest(BaseModel):
    expected_revision: int = Field(..., ge=1)

    model_config = ConfigDict(
        extra="forbid",
        revalidate_instances="always",
        strict=True,
    )


class InvestmentFrameworkResponse(BaseModel):
    framework_id: int = Field(..., ge=1)
    scope: Literal["local"]
    version: int = Field(..., ge=1)
    active_version: Optional[int] = Field(None, ge=1)
    revision: int = Field(..., ge=1)
    is_active: bool
    content: InvestmentFrameworkContent
    change_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    version_created_at: datetime

    model_config = ConfigDict(
        extra="forbid",
        revalidate_instances="always",
        strict=True,
    )


class InvestmentFrameworkHistoryItem(BaseModel):
    version: int = Field(..., ge=1)
    is_active: bool
    content: InvestmentFrameworkContent
    change_summary: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(
        extra="forbid",
        revalidate_instances="always",
        strict=True,
    )


class InvestmentFrameworkHistoryResponse(BaseModel):
    framework_id: int = Field(..., ge=1)
    latest_version: int = Field(..., ge=1)
    active_version: Optional[int] = Field(None, ge=1)
    revision: int = Field(..., ge=1)
    items: List[InvestmentFrameworkHistoryItem] = Field(default_factory=list)
    total: int = Field(..., ge=0)

    model_config = ConfigDict(
        extra="forbid",
        revalidate_instances="always",
        strict=True,
    )


class InvestmentFrameworkDeleteResponse(BaseModel):
    deleted: Literal[True]
    framework_id: int = Field(..., ge=1)
    deleted_through_version: int = Field(..., ge=1)

    model_config = ConfigDict(
        extra="forbid",
        revalidate_instances="always",
        strict=True,
    )
