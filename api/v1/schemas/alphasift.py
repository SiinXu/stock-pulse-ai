# -*- coding: utf-8 -*-
"""Pydantic v2 transport DTOs for the AlphaSift API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AlphaSiftResponseModel(BaseModel):
    """Preserve forward-compatible adapter fields at the public API boundary."""

    model_config = ConfigDict(extra="allow")


class AlphaSiftScreenRequest(BaseModel):
    market: str = Field("cn", min_length=1, max_length=16)
    strategy: str = Field("dual_low", min_length=1, max_length=64)
    max_results: int = Field(
        20,
        ge=1,
        le=100,
        validation_alias=AliasChoices("max_results", "maxResults"),
    )

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class AlphaSiftStatusResponse(AlphaSiftResponseModel):
    enabled: bool
    available: bool
    install_spec_is_default: bool
    contract_version: Optional[str] = None
    version: Optional[str] = None
    strategy_count: Optional[int] = None
    source_health: Optional[Dict[str, Any]] = None
    diagnostics: Optional[Dict[str, Any]] = None


class AlphaSiftStrategyResponse(AlphaSiftResponseModel):
    id: str
    name: str = ""
    title: str = ""
    description: str = ""
    category: str = ""
    tag: str = ""
    tags: List[str] = Field(default_factory=list)
    market_scope: List[str] = Field(default_factory=list)
    market: str = ""


class AlphaSiftStrategiesResponse(AlphaSiftResponseModel):
    enabled: bool
    strategies: List[AlphaSiftStrategyResponse] = Field(default_factory=list)
    strategy_count: int


class AlphaSiftInstallResponse(AlphaSiftResponseModel):
    installed: bool
    already_installed: bool
    install_spec_is_default: bool


class AlphaSiftHotspotResponse(AlphaSiftResponseModel):
    topic: str = ""
    name: Optional[str] = None
    source: Optional[str] = None
    rank: Optional[int] = None
    change_pct: Optional[float] = None
    heat_score: Optional[float] = None
    trend_score: Optional[float] = None
    persistence_score: Optional[float] = None
    cooling_score: Optional[float] = None
    observations: Optional[int] = None
    state: Optional[str] = None
    stage: Optional[str] = None
    sample_stock_count: Optional[int] = None
    leaders: Optional[List[str]] = None
    provider_used: Optional[str] = None
    fallback_used: Optional[bool] = None
    cache_used: Optional[bool] = None
    cached_at: Optional[str] = None
    source_errors: Optional[List[str]] = None
    stale: Optional[bool] = None
    stale_age_hours: Optional[float] = None


class AlphaSiftHotspotRouteResponse(AlphaSiftResponseModel):
    title: str = ""
    description: str = ""
    source: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    published_at: Optional[str] = None
    url: Optional[str] = None


class AlphaSiftHotspotStockResponse(AlphaSiftResponseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    change_pct: Optional[float] = None
    amount: Optional[float] = None
    turnover_rate: Optional[float] = None
    volume_ratio: Optional[float] = None
    role: Optional[str] = None
    hot_stock_score: Optional[float] = None
    source: Optional[str] = None
    source_confidence: Optional[float] = None
    fallback_used: Optional[bool] = None


class AlphaSiftHotspotDetailResponse(AlphaSiftResponseModel):
    enabled: bool
    provider: str
    topic: str
    name: Optional[str] = None
    canonical_topic: Optional[str] = None
    aliases: Optional[List[str]] = None
    summary: Optional[Any] = None
    summary_detail: Optional[Dict[str, Any]] = None
    route: List[AlphaSiftHotspotRouteResponse] = Field(default_factory=list)
    timeline: Optional[List[AlphaSiftHotspotRouteResponse]] = None
    stocks: List[AlphaSiftHotspotStockResponse]
    leader_stocks: Optional[List[AlphaSiftHotspotStockResponse]] = None
    stock_count: int
    source_errors: Optional[List[str]] = None
    quality_status: Optional[str] = None
    missing_fields: Optional[List[str]] = None
    fallback_used: Optional[bool] = None
    stale: Optional[bool] = None
    stale_age_hours: Optional[float] = None
    cache_used: Optional[bool] = None
    cached_at: Optional[str] = None
    resolver_candidates: Optional[List[Dict[str, Any]]] = None


class AlphaSiftHotspotsResponse(AlphaSiftResponseModel):
    enabled: bool
    provider: str
    provider_used: Optional[str] = None
    fallback_used: Optional[bool] = None
    cache_used: Optional[bool] = None
    cached_at: Optional[str] = None
    source_errors: Optional[List[str]] = None
    stale: Optional[bool] = None
    stale_age_hours: Optional[float] = None
    message: Optional[str] = None
    hotspots: List[AlphaSiftHotspotResponse] = Field(default_factory=list)
    hotspot_count: int
    details: Optional[Dict[str, AlphaSiftHotspotDetailResponse]] = None


class AlphaSiftCandidateResponse(AlphaSiftResponseModel):
    rank: int
    code: str
    name: str
    score: Optional[float] = None
    screen_score: Optional[float] = None
    reason: str
    risk_level: Optional[str] = None
    risk_flags: List[str] = Field(default_factory=list)
    llm_score: Optional[float] = None
    llm_confidence: Optional[float] = None
    llm_sector: Optional[str] = None
    llm_theme: Optional[str] = None
    llm_tags: List[str] = Field(default_factory=list)
    llm_thesis: Optional[str] = None
    llm_catalysts: List[str] = Field(default_factory=list)
    llm_risks: List[str] = Field(default_factory=list)
    llm_watch_items: List[str] = Field(default_factory=list)
    llm_invalidators: List[str] = Field(default_factory=list)
    llm_style_fit: Optional[str] = None
    price: Optional[float] = None
    change_pct: Optional[float] = None
    amount: Optional[float] = None
    industry: Optional[str] = None
    factor_scores: Dict[str, Any] = Field(default_factory=dict)
    post_analysis_summaries: Dict[str, Any] = Field(default_factory=dict)
    post_analysis_tags: List[str] = Field(default_factory=list)
    dsa_context: Dict[str, Any] = Field(default_factory=dict)
    dsa_news: List[Dict[str, Any]] = Field(default_factory=list)
    dsa_analysis_summary: Optional[str] = None
    raw: Dict[str, Any]


class AlphaSiftScreenResponse(AlphaSiftResponseModel):
    enabled: bool
    candidates: List[AlphaSiftCandidateResponse] = Field(default_factory=list)
    candidate_count: int
    run_id: Optional[str] = None
    strategy: Optional[str] = None
    market: Optional[str] = None
    snapshot_count: Optional[int] = None
    snapshot_source: Optional[str] = None
    after_filter_count: Optional[int] = None
    llm_ranked: Optional[bool] = None
    llm_market_view: Optional[str] = None
    llm_selection_logic: Optional[str] = None
    llm_portfolio_risk: Optional[str] = None
    llm_coverage: Optional[float] = None
    llm_parse_errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    source_errors: List[str] = Field(default_factory=list)
    dsa_enrichment: Optional[Dict[str, Any]] = None
    deep_analysis_requested: Optional[bool] = None
    post_analyzers: List[str] = Field(default_factory=list)
    daily_enriched: Optional[bool] = None
    daily_enrich_count: Optional[int] = None
    risk_enabled: Optional[bool] = None
    portfolio_diversity_enabled: Optional[bool] = None
    portfolio_concentration_notes: List[str] = Field(default_factory=list)


class AlphaSiftScreenAccepted(AlphaSiftResponseModel):
    task_id: str
    trace_id: str
    status: str = "pending"
    message: str
    message_code: str = "task.screening.queued"
    message_params: Dict[str, Any] = Field(default_factory=dict)
    strategy: str
    market: str
    max_results: int


class AlphaSiftScreenTaskStatus(AlphaSiftResponseModel):
    task_id: str
    trace_id: Optional[str] = None
    status: str
    progress: int = 0
    message: Optional[str] = None
    message_code: str = "task.status"
    message_params: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    result: Optional[AlphaSiftScreenResponse] = None
