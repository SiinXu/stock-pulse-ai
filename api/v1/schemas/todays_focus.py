# -*- coding: utf-8 -*-
"""Schemas for Today's Focus recommendations (Issue #157 / T26)."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class TodaysFocusCostContract(BaseModel):
    provider_calls: int = 0
    analysis_runs_triggered: int = 0
    zero_extra_fetch: bool = True

class TodaysFocusPresentationBoundary(BaseModel):
    alerts_owned_by: str = "notifications_or_alerts_hub"
    focus_shows: str = "prioritized_symbols_with_why_selected"
    duplicate_alert_ui: bool = False

class TodaysFocusItem(BaseModel):
    code: str
    name: str
    reason_code: str = Field(description="Deterministic reason code: alert_triggered | corporate_event | analysis_reversal | high_weight_move")
    reason_display: str
    priority: int
    weight_pct: Optional[float] = None
    secondary_reason_codes: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)

class TodaysFocusResponse(BaseModel):
    pack_version: str
    generated_at: str
    status: str = Field(description="'ok' or 'empty'")
    max_items: int
    item_count: int
    items: List[TodaysFocusItem] = Field(default_factory=list)
    empty_reason: Optional[str] = None
    empty_message: Optional[str] = None
    sources_used: List[str] = Field(default_factory=list)
    cost_contract: TodaysFocusCostContract = Field(default_factory=TodaysFocusCostContract)
    presentation_boundary: TodaysFocusPresentationBoundary = Field(default_factory=TodaysFocusPresentationBoundary)
