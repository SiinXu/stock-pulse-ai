# -*- coding: utf-8 -*-
"""Alert API schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from api.v1.schemas.history import AnalysisContextPackOverview
from api.v1.schemas.market_phase import MarketPhaseSummary


TargetScopeValue = Literal["single_symbol", "watchlist", "portfolio_holdings", "portfolio_account", "market"]
SeverityValue = Literal["info", "warning", "critical"]
DryRunStatusValue = Literal["triggered", "not_triggered", "evaluation_error"]
TargetRecordStatusValue = Literal["triggered", "skipped", "degraded", "failed"]
CorporateAlertTypeFilter = Literal["corporate_event"]
CorporateEventCategoryValue = Literal["earnings", "shareholder", "mna", "regulatory", "analyst"]
EventImpactGradeValue = Literal["major", "routine", "unclassified"]


class AlertRuleCreateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    target_scope: TargetScopeValue = "single_symbol"
    target: str = Field(..., min_length=1, max_length=64)
    alert_type: str = Field(..., min_length=1, max_length=32)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    severity: SeverityValue = "warning"
    enabled: bool = True
    cooldown_policy: Optional[Dict[str, Any]] = None
    notification_policy: Optional[Dict[str, Any]] = None


class AlertRuleUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    target_scope: Optional[TargetScopeValue] = None
    target: Optional[str] = Field(None, min_length=1, max_length=64)
    alert_type: Optional[str] = Field(None, min_length=1, max_length=32)
    parameters: Optional[Dict[str, Any]] = None
    severity: Optional[SeverityValue] = None
    enabled: Optional[bool] = None
    cooldown_policy: Optional[Dict[str, Any]] = None
    notification_policy: Optional[Dict[str, Any]] = None


class AlertRuleItem(BaseModel):
    id: int
    name: str
    target_scope: str
    target: str
    alert_type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    severity: str
    enabled: bool
    source: str
    cooldown_policy: Optional[Dict[str, Any]] = None
    notification_policy: Optional[Dict[str, Any]] = None
    last_triggered_at: Optional[str] = None
    cooldown_until: Optional[str] = None
    cooldown_active: Optional[bool] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AlertRuleListResponse(BaseModel):
    items: List[AlertRuleItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class AlertDeleteResponse(BaseModel):
    deleted: int


class AlertRuleTargetResult(BaseModel):
    target: str
    display_target: Optional[str] = None
    status: DryRunStatusValue
    record_status: Optional[TargetRecordStatusValue] = None
    triggered: bool
    observed_value: Optional[Any] = None
    threshold: Optional[Any] = None
    message: str


class AlertRuleTestResponse(BaseModel):
    rule_id: int
    target_scope: Optional[str] = None
    status: DryRunStatusValue
    triggered: bool
    observed_value: Optional[Any] = None
    message: str
    evaluated_count: int = 0
    triggered_count: int = 0
    degraded_count: int = 0
    skipped_count: int = 0
    target_results: List[AlertRuleTargetResult] = Field(default_factory=list)


class AlertEventAffectedContext(BaseModel):
    symbol: Optional[str] = Field(None, max_length=64)
    in_watchlist: bool = False
    in_portfolio: bool = False
    weight_pct: Optional[float] = Field(None, ge=0, le=100, allow_inf_nan=False)


class AlertEventContext(BaseModel):
    what_happened: Optional[str] = Field(None, max_length=512)
    why_it_matters: Optional[str] = Field(None, max_length=512)
    event_category: Optional[CorporateEventCategoryValue] = None
    event_categories: List[CorporateEventCategoryValue] = Field(default_factory=list, max_length=5)
    matched_count: Optional[int] = Field(None, ge=0, le=100_000)
    source_item_id: Optional[str] = Field(None, max_length=64)
    source_name: Optional[str] = Field(None, max_length=100)
    source_url: Optional[str] = Field(None, max_length=2048)


class AlertAutoAnalysisStatus(BaseModel):
    status: str = Field(..., max_length=64)
    submitted: bool = False
    stock_code: Optional[str] = Field(None, max_length=64)
    pipeline: Optional[str] = Field(None, max_length=32)
    reason: Optional[str] = Field(None, max_length=512)


class AlertSuggestedAction(BaseModel):
    action_code: str = Field(..., max_length=64)
    label: Optional[str] = Field(None, max_length=128)
    rationale: Optional[str] = Field(None, max_length=512)
    deep_links: Optional[Dict[str, str]] = None
    relevance: List[str] = Field(default_factory=list, max_length=5)
    auto_analysis: Optional[AlertAutoAnalysisStatus] = None


class AlertImpactContext(AlertEventContext):
    degraded: bool = False
    affected: Optional[AlertEventAffectedContext] = None
    related_analysis: Optional[str] = Field(None, max_length=512)
    suggested_action: Optional[AlertSuggestedAction] = None


class AlertImpactResult(BaseModel):
    grade: EventImpactGradeValue
    severity: Optional[SeverityValue] = None
    provenance: Literal["rule_severity", "unavailable"]


class AlertTriggerItem(BaseModel):
    id: int
    rule_id: Optional[int] = None
    target: str
    observed_value: Optional[float] = Field(None, allow_inf_nan=False)
    threshold: Optional[float] = Field(None, allow_inf_nan=False)
    reason: Optional[str] = None
    data_source: Optional[str] = None
    data_timestamp: Optional[str] = None
    triggered_at: Optional[str] = None
    status: str
    alert_type: Optional[str] = None
    severity: Optional[SeverityValue] = None
    diagnostics: Optional[str] = None
    market_phase_summary: Optional[MarketPhaseSummary] = None
    analysis_context_pack_overview: Optional[AnalysisContextPackOverview] = None
    analysis_visibility_source: Optional[str] = Field(
        None,
        description=(
            "公开摘要来源：alert_trigger_market_context / analysis_history_snapshot / "
            "evaluator_snapshot / legacy_text / null"
        ),
    )
    decision_signal_summary: Optional[Dict[str, Any]] = None
    impact_context: Optional[AlertImpactContext] = None
    event_context: Optional[AlertEventContext] = None
    suggested_action: Optional[AlertSuggestedAction] = None
    auto_analysis: Optional[AlertAutoAnalysisStatus] = None
    impact_result: Optional[AlertImpactResult] = None


class AlertRuleNlCompileRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    default_severity: SeverityValue = "warning"
    default_enabled: bool = True
    auto_analysis: Optional[bool] = Field(
        None,
        description="When true, attach notification_policy.auto_analysis=true to a successful compile.",
    )


class AlertRuleNlCompileResponse(BaseModel):
    outcome: Literal["success", "need_clarification", "rejected"]
    message: str = ""
    matched_metric: Optional[str] = None
    matched_symbols: List[str] = Field(default_factory=list)
    clarifications: List[str] = Field(default_factory=list)
    rejected_reason: Optional[str] = None
    rule: Optional[Dict[str, Any]] = None


class AlertTriggerListResponse(BaseModel):
    items: List[AlertTriggerItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    next_cursor: Optional[str] = None


class AlertNotificationItem(BaseModel):
    id: int
    trigger_id: Optional[int] = None
    channel: str
    attempt: int
    success: bool
    error_code: Optional[str] = None
    retryable: bool
    latency_ms: Optional[int] = None
    diagnostics: Optional[str] = None
    created_at: Optional[str] = None


class AlertNotificationListResponse(BaseModel):
    items: List[AlertNotificationItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
