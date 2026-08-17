# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""OpenAPI schemas for the read-only research API (Issue #1143)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ResearchReportMode = Literal["brief", "standard", "research"]
ResearchGapKind = Literal["missing", "conflict"]


class ResearchEvidenceCounts(BaseModel):
    """Counts derived from the mode-filtered strata projection."""

    model_config = ConfigDict(extra="forbid")

    verified_facts: int = Field(0, ge=0)
    missing_or_conflicts: int = Field(0, ge=0)
    model_inference: int = Field(0, ge=0)
    risks_counter_evidence: int = Field(0, ge=0)
    evidence_refs: int = Field(0, ge=0, description="Unique source_id / source_ids count")


class ResearchGapItem(BaseModel):
    """One missing-data or conflict gap the client can render without full history."""

    model_config = ConfigDict(extra="forbid")

    kind: ResearchGapKind = "missing"
    description: str
    source_ids: List[str] = Field(default_factory=list)


class ResearchConclusionMetadata(BaseModel):
    """Record-level metadata for embed/portal clients."""

    model_config = ConfigDict(extra="forbid")

    record_id: int = Field(..., ge=1)
    query_id: Optional[str] = None
    stock_code: str
    stock_name: Optional[str] = None
    report_type: Optional[str] = None
    created_at: Optional[str] = None
    as_of: Optional[str] = Field(
        None,
        description="Best-effort data as-of timestamp from strata facts or record time",
    )
    confidence_level: Optional[str] = None
    evidence_counts: ResearchEvidenceCounts = Field(default_factory=ResearchEvidenceCounts)
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="Bounded unique evidence reference ids (source_id values)",
    )
    report_language: Optional[str] = None


class ResearchConclusionBody(BaseModel):
    """Mode-density stratified conclusion body (no secrets, no raw_result dump)."""

    model_config = ConfigDict(extra="forbid")

    one_sentence: Optional[str] = None
    signal_type: Optional[str] = None
    position_advice: Optional[str] = None
    time_sensitivity: Optional[str] = None
    operation_advice: Optional[str] = None
    action: Optional[str] = None
    action_label: Optional[str] = None
    risks: List[str] = Field(default_factory=list)
    gaps: List[ResearchGapItem] = Field(default_factory=list)
    report_strata: Optional[Dict[str, Any]] = Field(
        None,
        description="Mode-filtered report strata; null in brief mode",
    )
    omitted_count: int = Field(0, ge=0)
    truncation_notice: Optional[str] = None
    confidence_reason: Optional[str] = None
    positive_catalysts: Optional[List[str]] = None
    analysis_summary: Optional[str] = None
    trend_prediction: Optional[str] = None


class ResearchConclusionResponse(BaseModel):
    """Compact stratified conclusion response for embed/portal use."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["research-conclusion-v1"] = "research-conclusion-v1"
    mode: ResearchReportMode
    metadata: ResearchConclusionMetadata
    conclusion: ResearchConclusionBody
    disclaimer: Optional[str] = None


__all__ = [
    "ResearchConclusionBody",
    "ResearchConclusionMetadata",
    "ResearchConclusionResponse",
    "ResearchEvidenceCounts",
    "ResearchGapItem",
    "ResearchReportMode",
]
