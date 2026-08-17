# -*- coding: utf-8 -*-
"""Schemas for per-symbol research timeline API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ResearchTimelineLink(BaseModel):
    """Deep-link payload for a timeline node (client builds the concrete URL)."""

    type: str = Field(
        ...,
        description="Target type: analysis_history | chat_session | decision_signal | hypothesis",
    )
    stock_code: Optional[str] = Field(None, description="Canonical stock code for the target")
    record_id: Optional[int] = Field(None, description="analysis_history.id when type=analysis_history")
    query_id: Optional[str] = Field(None, description="analysis_history.query_id when available")
    session_id: Optional[str] = Field(None, description="Chat session id when type=chat_session")
    message_id: Optional[int] = Field(None, description="Conversation message id")
    turn_id: Optional[str] = Field(None, description="Durable chat turn id (#923 contract)")
    signal_id: Optional[int] = Field(None, description="decision_signals.id when type=decision_signal")
    source_report_id: Optional[int] = Field(None, description="Linked analysis history id for a signal")

    model_config = ConfigDict(extra="allow")


class ResearchTimelineNode(BaseModel):
    """One research activity node on the per-symbol timeline."""

    id: str = Field(..., description="Stable node id, e.g. analysis_run:12")
    kind: str = Field(..., description="analysis_run | chat | signal | hypothesis")
    occurred_at: str = Field(..., description="ISO-8601 timestamp with offset")
    title: str = Field(..., description="Short human-readable title")
    summary: Optional[str] = Field(None, description="Optional one-line summary")
    direction: Optional[str] = Field(
        None,
        description="Direction/advice label for simple analysis-node diffs",
    )
    confidence: Optional[float] = Field(
        None,
        description="Normalized 0-1 confidence when available",
        ge=0.0,
        le=1.0,
    )
    status: Optional[str] = Field(None, description="Lifecycle status when applicable")
    link: ResearchTimelineLink = Field(..., description="Deep-link coordinates")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Kind-specific extras")


class ResearchTimelineSources(BaseModel):
    """Per-source honesty flags so the UI never invents empty success for missing feeds."""

    analysis_run: str = Field(..., description="ok | empty | unavailable | error")
    chat: str = Field(..., description="ok | empty | unavailable | error")
    signal: str = Field(..., description="ok | empty | unavailable | error")
    hypothesis: str = Field(..., description="ok | empty | unavailable | error")


class ResearchTimelineResponse(BaseModel):
    """Cursor page of research timeline nodes for one symbol."""

    stock_code: str = Field(..., description="Canonical display stock code")
    items: List[ResearchTimelineNode] = Field(default_factory=list)
    next_cursor: Optional[str] = Field(
        None,
        description="Opaque cursor for the next page; null when has_more is false",
        max_length=512,
    )
    has_more: bool = Field(..., description="Whether additional older nodes exist")
    limit: int = Field(..., description="Page size applied to this response", ge=1, le=50)
    sources: ResearchTimelineSources = Field(
        ...,
        description="Per-source status; hypothesis is unavailable until #1130 ships",
    )
