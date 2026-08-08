# -*- coding: utf-8 -*-
"""Schemas for report version comparison (issue #188 / T18)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReportVersionRunItem(BaseModel):
    """One selectable analysis run for a symbol."""

    model_config = ConfigDict(protected_namespaces=("model_validate", "model_dump"))

    run_id: str = Field(..., description="Stable analysis history primary key as string")
    query_id: str = Field(..., description="Analysis query_id (may repeat in batch runs)")
    stock_code: str = Field(..., description="Display stock code")
    stock_name: Optional[str] = Field(None, description="Stock name when available")
    report_type: Optional[str] = Field(None, description="Report type snapshot")
    created_at: Optional[str] = Field(None, description="ISO created_at timestamp")
    model_used: Optional[str] = Field(
        None,
        description="Model snapshot for display only; not used for runtime routing",
    )
    report_language: Optional[str] = Field(None, description="Report language snapshot")
    action: Optional[str] = Field(None, description="Structured decision action taxonomy")
    action_label: Optional[str] = Field(None, description="Localized action label snapshot")
    operation_advice: Optional[str] = Field(None, description="Legacy operation advice text")
    sentiment_score: Optional[int] = Field(None, description="Sentiment / confidence score")
    trend_prediction: Optional[str] = Field(None, description="Trend prediction text")
    analysis_summary: Optional[str] = Field(None, description="Short analysis summary")
    config_fingerprint: Optional[str] = Field(
        None,
        description="Short hash of configuration components used for this run",
    )
    config_components: Dict[str, str] = Field(
        default_factory=dict,
        description="Human-readable configuration components that form the fingerprint",
    )


class ReportVersionRunListResponse(BaseModel):
    stock_code: str
    total: int
    page: int
    limit: int
    items: List[ReportVersionRunItem] = Field(default_factory=list)


class ConfigComponentDiff(BaseModel):
    key: str
    base_value: Optional[str] = None
    target_value: Optional[str] = None
    changed: bool = False


class ConfigFingerprintDiff(BaseModel):
    base_fingerprint: Optional[str] = None
    target_fingerprint: Optional[str] = None
    identical: bool = False
    has_differences: bool = False
    components: List[ConfigComponentDiff] = Field(default_factory=list)


class ReportFieldDiff(BaseModel):
    field: str
    base_value: Optional[str] = None
    target_value: Optional[str] = None
    changed: bool = False
    severity: Literal["major", "moderate", "minor", "none", "unknown"] = "none"


class AnalysisDeltaPayload(BaseModel):
    """Presentation projection of T17 AnalysisDelta (contract A)."""

    has_baseline: bool = False
    conclusion_changes: List[Any] = Field(default_factory=list)
    score_changes: List[Any] = Field(default_factory=list)
    evidence_changes: List[Any] = Field(default_factory=list)
    risk_changes: List[Any] = Field(default_factory=list)
    base_run_id: str
    target_run_id: str


class ReportVersionCompareResponse(BaseModel):
    """Compare two selected analysis runs for one symbol."""

    model_config = ConfigDict(protected_namespaces=("model_validate", "model_dump"))

    status: Literal["ok", "engine_pending", "no_baseline", "incomparable"] = Field(
        ...,
        description=(
            "ok: T17 delta available with baseline; "
            "engine_pending: T17 compare_analyses not wired yet; "
            "no_baseline: T17 returned has_baseline=false (distinct from no changes); "
            "incomparable: runs cannot be compared"
        ),
    )
    stock_code: str
    base_run: ReportVersionRunItem
    target_run: ReportVersionRunItem
    config_diff: ConfigFingerprintDiff
    field_diffs: List[ReportFieldDiff] = Field(default_factory=list)
    delta: Optional[AnalysisDeltaPayload] = Field(
        None,
        description="T17 AnalysisDelta projection when the comparison engine is available",
    )
    engine_status: Literal["ok", "engine_pending"] = Field(
        ...,
        description="Whether T17 compare_analyses was invoked successfully",
    )
