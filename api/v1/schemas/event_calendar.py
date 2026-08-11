# -*- coding: utf-8 -*-
"""Schemas for event calendar API (issue #153 / T21)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EventCalendarCoverageRow(BaseModel):
    market: str
    earnings: str
    ex_dividend: str
    unlock: str
    index_rebalance: str
    macro: str


class EventImpactPreview(BaseModel):
    available: bool = False
    what_happened: Optional[str] = None
    why_it_matters: Optional[str] = None
    event_category: Optional[str] = None
    affected: Optional[Dict[str, Any]] = None
    related_analysis: Optional[str] = None
    degraded: Optional[bool] = None
    source: Optional[str] = None
    error: Optional[str] = None


class CalendarEventItem(BaseModel):
    event_id: str
    event_type: str = Field(description="earnings|ex_dividend|unlock|index_rebalance|macro")
    event_date: str = Field(description="ISO date YYYY-MM-DD")
    certainty: str = Field(description="confirmed|scheduled|estimated")
    symbol: str
    title: str
    market: str = ""
    source: str = ""
    fetched_at: Optional[str] = None
    description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    impact_preview: Optional[EventImpactPreview] = None


class EventCalendarResponse(BaseModel):
    enabled: bool
    fetch_attempted: bool
    as_of: str
    date_from: str
    date_to: str
    event_types: List[str] = Field(default_factory=list)
    symbols: List[str] = Field(default_factory=list)
    symbol_count: int = 0
    event_count: int = 0
    events: List[CalendarEventItem] = Field(default_factory=list)
    coverage: List[EventCalendarCoverageRow] = Field(default_factory=list)
    sources_attempted: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    coverage_notes: List[str] = Field(default_factory=list)
    fetched_at: Optional[str] = None
    impact_preview_mode: str = "build_impact_context"
    reuses_build_impact_context: bool = True
