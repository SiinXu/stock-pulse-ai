# -*- coding: utf-8 -*-
"""DecisionSignal API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from src.api.v1.schemas.market_phase import MarketPhaseValue
from src.schemas.decision_action import DecisionAction
from src.schemas.decision_profile import DecisionProfile
from src.schemas.memory_fact_opinion import lock_opinion_payload
from src.schemas.memory_provenance import reject_client_provenance_keys
from src.schemas.memory_write_guard import (
    FEEDBACK_NOTE_MAX_LENGTH,
    FEEDBACK_REASON_CODE_MAX_LENGTH,
    reject_memory_write_text,
)

MemoryProvenanceSource = Literal[
    "system_resolve", "user_feedback", "operator"
]


DecisionSignalSourceType = Literal["analysis", "agent", "alert", "market_review", "manual"]
DecisionSignalStatus = Literal["active", "expired", "invalidated", "closed", "archived"]
DecisionSignalPlanQuality = Literal["complete", "partial", "minimal", "unknown"]
DecisionSignalHorizon = Literal["intraday", "1d", "3d", "5d", "10d", "swing", "long"]
DecisionSignalMarket = Literal["cn", "hk", "us", "jp", "kr", "tw"]
DecisionSignalOutcomeStatus = Literal["completed", "unable"]
DecisionSignalOutcomeValue = Literal["hit", "miss", "neutral"]
DecisionSignalFeedbackValue = Literal["useful", "not_useful"]
DecisionSignalFeedbackSource = Literal["web", "api"]


class DecisionSignalCreateRequest(BaseModel):
    stock_code: str = Field(..., min_length=1, max_length=32)
    stock_name: Optional[str] = Field(None, json_schema_extra={"maxLength": 64})
    market: DecisionSignalMarket
    source_type: DecisionSignalSourceType
    source_agent: Optional[str] = Field(None, json_schema_extra={"maxLength": 64})
    source_report_id: Optional[int] = None
    trace_id: Optional[str] = Field(None, json_schema_extra={"maxLength": 64})
    decision_profile: DecisionProfile = Field(
        default=None,
        description="Optional decision profile. Omit to use server-side default/fallback; explicit null is rejected.",
    )
    market_phase: Optional[MarketPhaseValue] = None
    trigger_source: str = Field(..., min_length=1, json_schema_extra={"maxLength": 64})
    action: DecisionAction
    action_label: Optional[str] = Field(None, json_schema_extra={"maxLength": 32})
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    score: Optional[int] = Field(None, ge=0, le=100)
    horizon: Optional[DecisionSignalHorizon] = None
    entry_low: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    entry_high: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    stop_loss: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    target_price: Optional[float] = Field(None, gt=0, allow_inf_nan=False)
    invalidation: Optional[Any] = None
    watch_conditions: Optional[Any] = None
    reason: Optional[Any] = None
    risk_summary: Optional[Any] = None
    catalyst_summary: Optional[Any] = None
    evidence: Optional[Any] = None
    data_quality_summary: Optional[Any] = None
    plan_quality: Optional[DecisionSignalPlanQuality] = None
    status: Optional[DecisionSignalStatus] = None
    expires_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata object. Omitted or null values are treated as absent.",
    )
    report_language: Optional[Literal["zh", "en", "ko"]] = None


class DecisionSignalReassessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_report_id: int = Field(..., gt=0)
    decision_profile: DecisionProfile
    persist: bool = False


class DecisionSignalWarning(BaseModel):
    code: str
    message: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class DecisionSignalGuardrailResult(BaseModel):
    raw_action: str
    final_action: str
    passed: bool
    violations: List[str] = Field(default_factory=list)
    adjustments: List[str] = Field(default_factory=list)
    adjusted: bool


class DecisionSignalPreview(BaseModel):
    action: str
    score: Optional[int] = None
    confidence: Optional[float] = None
    horizon: Optional[str] = None
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    invalidation: Optional[str] = None
    reason: Optional[str] = None
    risk_summary: Optional[str] = None
    watch_conditions: Optional[str] = None
    metadata: Dict[str, Any]


class DecisionSignalStatusUpdateRequest(BaseModel):
    status: DecisionSignalStatus
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional replacement metadata. Omit to preserve the stored value; "
            "null clears caller metadata; an object replaces caller metadata. "
            "Both replacement forms preserve any formal decision_profile identity "
            "and persisted presentation report_language provenance without promoting "
            "either value from replacement metadata."
        ),
    )


class DecisionSignalOutcomeRunRequest(BaseModel):
    signal_id: Optional[int] = Field(None, gt=0)
    horizons: Optional[List[DecisionSignalHorizon]] = None
    force: bool = False
    market: Optional[DecisionSignalMarket] = None
    stock_code: Optional[str] = Field(None, json_schema_extra={"maxLength": 32})
    action: Optional[DecisionAction] = None
    source_type: Optional[DecisionSignalSourceType] = None
    status: Optional[DecisionSignalStatus] = None
    limit: int = Field(100, ge=1, le=500)


class DecisionSignalOutcomeItem(BaseModel):
    id: int
    signal_id: int
    horizon: str
    engine_version: str
    eval_status: str
    outcome: Optional[str] = None
    direction_expected: Optional[str] = None
    direction_correct: Optional[bool] = None
    unable_reason: Optional[str] = None
    anchor_date: Optional[str] = None
    eval_window_days: Optional[int] = None
    start_price: Optional[float] = None
    end_close: Optional[float] = None
    max_high: Optional[float] = None
    min_low: Optional[float] = None
    stock_return_pct: Optional[float] = None
    action: Optional[str] = None
    market: Optional[str] = None
    market_phase: Optional[str] = None
    source_type: Optional[str] = None
    source_agent: Optional[str] = None
    plan_quality: Optional[str] = None
    data_quality_level: Optional[str] = None
    holding_state: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DecisionSignalOutcomeRunResponse(BaseModel):
    items: List[DecisionSignalOutcomeItem] = Field(default_factory=list)
    evaluated: int
    created: int
    updated: int
    skipped: int
    engine_version: str


class DecisionSignalOutcomeListResponse(BaseModel):
    items: List[DecisionSignalOutcomeItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class DecisionSignalOutcomeStatsBucket(BaseModel):
    dimension: str
    value: str
    total: int
    completed: int
    unable: int
    hit: int
    miss: int
    neutral: int
    sample_sufficient: bool = False
    hit_rate_pct: Optional[float] = None
    avg_stock_return_pct: Optional[float] = None
    unable_reasons: Dict[str, int] = Field(default_factory=dict)


class DecisionSignalProfileCalibrationBucket(BaseModel):
    dimensions: Dict[str, str] = Field(default_factory=dict)
    total: int
    completed: int
    unable: int
    hit: int
    miss: int
    neutral: int
    sample_sufficient: bool
    hit_rate_pct: Optional[float] = None
    avg_stock_return_pct: Optional[float] = None
    miss_rate_pct: Optional[float] = None
    unable_rate_pct: Optional[float] = None
    max_adverse_excursion_pct: Optional[float] = None


class DecisionSignalProfileCalibrationBreakdowns(BaseModel):
    decision_profile: List[DecisionSignalProfileCalibrationBucket] = Field(default_factory=list)
    decision_profile_action: List[DecisionSignalProfileCalibrationBucket] = Field(default_factory=list)
    decision_profile_horizon: List[DecisionSignalProfileCalibrationBucket] = Field(default_factory=list)
    decision_profile_market_phase: List[DecisionSignalProfileCalibrationBucket] = Field(default_factory=list)
    decision_profile_data_quality_level: List[DecisionSignalProfileCalibrationBucket] = Field(default_factory=list)
    profile_source: List[DecisionSignalProfileCalibrationBucket] = Field(default_factory=list)


class DecisionSignalProfileCalibration(BaseModel):
    minimum_completed_sample_size: int = Field(..., ge=1)
    breakdowns: DecisionSignalProfileCalibrationBreakdowns


class DecisionSignalOutcomeStatsResponse(BaseModel):
    engine_version: str
    horizons: Optional[List[str]] = None
    statuses: List[str] = Field(default_factory=list)
    total: int
    completed: int
    unable: int
    hit: int
    miss: int
    neutral: int
    sample_sufficient: bool = False
    minimum_completed_sample_size: int = Field(default=30, ge=1)
    hit_rate_pct: Optional[float] = None
    avg_stock_return_pct: Optional[float] = None
    unable_reasons: Dict[str, int] = Field(default_factory=dict)
    # Includes action/market/period (and legacy dimensions). Rates null when sample_sufficient is false.
    breakdowns: Dict[str, List[DecisionSignalOutcomeStatsBucket]] = Field(default_factory=dict)
    # Present only when DECISION_PROFILE_CALIBRATION_ENABLED is true.
    profile_calibration: Optional[DecisionSignalProfileCalibration] = None


class DecisionSignalFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_value: DecisionSignalFeedbackValue
    reason_code: Optional[str] = Field(
        None, json_schema_extra={"maxLength": FEEDBACK_REASON_CODE_MAX_LENGTH}
    )
    note: Optional[str] = Field(
        None, json_schema_extra={"maxLength": FEEDBACK_NOTE_MAX_LENGTH}
    )
    source: DecisionSignalFeedbackSource = "api"

    @model_validator(mode="before")
    @classmethod
    def _reject_fact_and_client_provenance(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            lock_opinion_payload(value)
            reject_client_provenance_keys(value)
        return value

    @field_validator("reason_code", "note")
    @classmethod
    def _reject_soul_or_controls(
        cls, value: Optional[str], info: ValidationInfo
    ) -> Optional[str]:
        max_length = (
            FEEDBACK_NOTE_MAX_LENGTH
            if info.field_name == "note"
            else FEEDBACK_REASON_CODE_MAX_LENGTH
        )
        return reject_memory_write_text(
            value,
            field_name=str(info.field_name),
            max_length=max_length,
        )


class DecisionSignalFeedbackItem(BaseModel):
    signal_id: int
    feedback_value: Optional[DecisionSignalFeedbackValue] = None
    reason_code: Optional[str] = None
    note: Optional[str] = None
    source: Optional[DecisionSignalFeedbackSource] = None
    provenance_source: Optional[MemoryProvenanceSource] = None
    actor_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DecisionSignalMemoryFlagRequest(BaseModel):
    """Curate a signal for decision memory; omitted fields keep their value."""

    memorable: Optional[bool] = None
    ignored: Optional[bool] = None


class DecisionSignalMemoryFlagItem(BaseModel):
    signal_id: int
    memorable: bool = False
    ignored: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DecisionSignalPresentation(BaseModel):
    """Renderer-ready fields whose action mirrors the top-level signal action."""

    action: Literal["buy", "add", "hold", "reduce", "sell", "watch", "avoid", "alert"]
    label: str
    confidence: Optional[float] = None
    summary: Optional[str] = None
    risk: Optional[str] = None
    timestamp: Optional[str] = None


class DecisionSignalItem(BaseModel):
    id: int
    stock_code: str
    stock_name: Optional[str] = None
    market: str
    source_type: str
    source_agent: Optional[str] = None
    source_report_id: Optional[int] = None
    trace_id: Optional[str] = None
    decision_profile: Optional[DecisionProfile] = None
    market_phase: Optional[str] = None
    trigger_source: str
    action: str
    action_label: Optional[str] = None
    confidence: Optional[float] = None
    score: Optional[int] = None
    horizon: Optional[str] = None
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    invalidation: Optional[str] = None
    watch_conditions: Optional[str] = None
    reason: Optional[str] = None
    risk_summary: Optional[str] = None
    catalyst_summary: Optional[str] = None
    evidence: Optional[Any] = None
    data_quality_summary: Optional[Any] = None
    plan_quality: str
    status: str
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: Optional[Any] = None
    presentation: DecisionSignalPresentation


class DecisionSignalMutationResponse(BaseModel):
    item: DecisionSignalItem
    created: bool


class DecisionSignalReassessResponse(BaseModel):
    preview: Optional[DecisionSignalPreview] = None
    item: Optional[DecisionSignalItem] = None
    created: bool = False
    persist_status: Optional[Literal["created", "existing", "refreshed"]] = None
    warnings: List[DecisionSignalWarning] = Field(default_factory=list)
    blocked_reason: Optional[str] = None


class DecisionSignalReassessErrorResponse(BaseModel):
    error: Literal[
        "unsupported_report_type",
        "unsupported_report_snapshot",
        "guardrail_blocked",
    ]
    message: str
    blocked_reason: Optional[str] = None
    warnings: List[DecisionSignalWarning] = Field(default_factory=list)


class DecisionSignalListResponse(BaseModel):
    items: List[DecisionSignalItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
