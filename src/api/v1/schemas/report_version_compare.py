# -*- coding: utf-8 -*-
"""Schemas for report version comparison (issue #188 / T18)."""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Union

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
    sentiment_score: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Finite sentiment / confidence score in the supported 0-100 range",
    )
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
    config_complete: bool = Field(
        False,
        description="Whether the persisted run contains the minimum reproducibility provenance",
    )
    config_missing_keys: List[str] = Field(
        default_factory=list,
        description="Required provenance keys absent from the persisted run",
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
    comparison_status: Literal["identical", "different", "unknown"] = "unknown"
    base_complete: bool = False
    target_complete: bool = False
    base_missing_keys: List[str] = Field(default_factory=list)
    target_missing_keys: List[str] = Field(default_factory=list)
    components: List[ConfigComponentDiff] = Field(default_factory=list)


class ReportFieldDiff(BaseModel):
    field: str
    base_value: Optional[str] = None
    target_value: Optional[str] = None
    changed: bool = False
    severity: Literal["major", "moderate", "minor", "none", "unknown"] = "none"


JsonScalar = Union[str, int, float, bool]


class ValueUnavailabilityPayload(BaseModel):
    base: Optional[str] = None
    target: Optional[str] = None


class AnalysisValueChangePayload(BaseModel):
    field: str
    base_value: Optional[JsonScalar] = None
    target_value: Optional[JsonScalar] = None
    delta: Optional[JsonScalar] = None
    direction: Literal["up", "down", "changed", "unavailable"]
    comparable: bool = True
    unavailability: Optional[ValueUnavailabilityPayload] = None


class AnalysisListChangePayload(BaseModel):
    field: str
    added: List[str] = Field(default_factory=list)
    removed: List[str] = Field(default_factory=list)
    unchanged: List[str] = Field(default_factory=list)
    added_total: int = Field(0, ge=0)
    removed_total: int = Field(0, ge=0)
    unchanged_total: int = Field(0, ge=0)
    output_truncated: bool = False


class AnalysisDeltaPayload(BaseModel):
    """Typed presentation projection of the merged T17 AnalysisDelta contract."""

    has_baseline: bool = False
    baseline_status: Literal[
        "ok",
        "missing_history",
        "missing_base",
        "missing_target",
        "incomparable_structure",
    ]
    baseline_reason: Optional[str] = None
    stock_code: Optional[str] = None
    base_record_id: int = Field(..., ge=1)
    target_record_id: int = Field(..., ge=1)
    base_query_id: Optional[str] = None
    target_query_id: Optional[str] = None
    report_type: Optional[str] = None
    has_material_changes: bool = False
    conclusion_changes: List[AnalysisValueChangePayload] = Field(default_factory=list)
    score_changes: List[AnalysisValueChangePayload] = Field(default_factory=list)
    evidence_changes: List[AnalysisListChangePayload] = Field(default_factory=list)
    risk_changes: List[AnalysisListChangePayload] = Field(default_factory=list)


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
