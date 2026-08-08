# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Schemas for agent-guided onboarding plan generation and apply."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UserOnboardingProfile(BaseModel):
    """Versioned structured intake profile (not free-form chat memory)."""

    schema_version: int = Field(default=1, ge=1)
    experience_stage: str = Field(
        default="beginner",
        description="beginner | report_reader | has_system",
    )
    markets: List[str] = Field(
        default_factory=lambda: ["cn"],
        description="cn | hk | us (multi-select)",
    )
    goals: List[str] = Field(default_factory=list)
    holdings: str = Field(default="none", description="none | watchlist | bookkeeping")
    interaction: str = Field(default="web", description="push | web | chat")
    risk_tone: str = Field(
        default="balanced",
        description="conservative | balanced | assertive (tone only, not advice)",
    )
    infrastructure: str = Field(
        default="cloud_key",
        description="cloud_key | local_models | free_only",
    )
    report_language: str = Field(default="zh", description="zh | en | ko | ja")


class OnboardingPlanRequest(BaseModel):
    """Generate a rule-based (optionally LLM-refined) onboarding plan."""

    profile: UserOnboardingProfile = Field(default_factory=UserOnboardingProfile)
    model_available: bool = Field(
        default=False,
        description="Whether a usable model is already configured (client-reported or server-known).",
    )
    prefer_llm: bool = Field(
        default=False,
        description=(
            "Request LLM refinement when a model is available. "
            "When false or when no model is available, the engine stays rule-based honestly."
        ),
    )


class OnboardingConfigChange(BaseModel):
    key: str
    from_value: str = Field(default="", alias="from")
    to: str

    model_config = {"populate_by_name": True}


class OnboardingConfigItem(BaseModel):
    key: str
    value: str


class OnboardingTodoItem(BaseModel):
    id: str
    priority: int = 1
    title: str
    description: str
    href: Optional[str] = None
    kind: str = "setup"


class OnboardingPlanStep(BaseModel):
    id: str
    title: str
    detail: str


class OnboardingWeekStep(BaseModel):
    day: str
    title: str
    detail: str


class OnboardingFeaturePath(BaseModel):
    stage: str
    label: str
    primary_path: List[str] = Field(default_factory=list)
    emphasize: List[str] = Field(default_factory=list)
    defer: List[str] = Field(default_factory=list)


class OnboardingPlanResponse(BaseModel):
    schema_version: int
    engine: str
    llm_note: str
    model_available: bool = False
    prefer_llm: bool = False
    profile: Dict[str, Any]
    feature_stage: str
    feature_path: OnboardingFeaturePath
    recommended_preset_id: str
    recommended_preset_name: str
    beginner_mode_recommended: bool = True
    config_changes: List[Dict[str, Any]] = Field(default_factory=list)
    config_items: List[OnboardingConfigItem] = Field(default_factory=list)
    todos: List[OnboardingTodoItem] = Field(default_factory=list)
    today_plan: List[OnboardingPlanStep] = Field(default_factory=list)
    week_plan: List[OnboardingWeekStep] = Field(default_factory=list)
    disclaimer: str
    generated_at: str


class OnboardingApplyRequest(BaseModel):
    """Apply non-secret recommended config after explicit user confirmation."""

    profile: UserOnboardingProfile = Field(default_factory=UserOnboardingProfile)
    config_version: str = Field(..., min_length=1)
    confirm: bool = Field(default=True, description="Must be true to apply.")
    model_available: bool = False
    prefer_llm: bool = False


class OnboardingApplyResponse(BaseModel):
    success: bool
    config_version: str
    applied_keys: List[str] = Field(default_factory=list)
    applied_count: int = 0
    plan: OnboardingPlanResponse
    profile: Dict[str, Any]
    message: str
    update: Dict[str, Any] = Field(default_factory=dict)


class OnboardingStateResponse(BaseModel):
    """Persisted profile + last plan (may be null fields when unset)."""

    exists: bool
    status: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None
    plan: Optional[OnboardingPlanResponse] = None
    applied_at: Optional[str] = None
    applied_keys: List[str] = Field(default_factory=list)
    config_version: Optional[str] = None


class OnboardingResetResponse(BaseModel):
    success: bool
    reset: bool
    message: str


class LocalRuntimeSnapshot(BaseModel):
    """Public, non-secret local-runtime detect projection."""

    available: bool = False
    backend: Optional[str] = None
    base_url: Optional[str] = None
    models: List[str] = Field(default_factory=list)
    suggested_profile: Dict[str, str] = Field(default_factory=dict)
    reason: str = "not_probed"
    detect_enabled: bool = True


class FirstRunReadinessResponse(BaseModel):
    """Zero-config first-run readiness snapshot (read-only; never mutates config)."""

    schema_version: int = 1
    is_fresh_environment: bool
    has_primary_model: bool
    beginner_mode_recommended: bool
    primary_path: str = Field(description="configured | local_ollama | demo")
    primary_cta: str = Field(description="continue | start_with_local | view_demo")
    headline: str
    local_runtime: LocalRuntimeSnapshot
    recommended_preset_id: Optional[str] = None
    recommended_preset_name: Optional[str] = None
    suggested_profile: Dict[str, str] = Field(default_factory=dict)
    demo_available: bool = True
    config_mutated: bool = False
    existing_config_untouched: bool = True
    generated_at: str


class DemoAnalysisResponse(BaseModel):
    """Offline sample analysis. Always ``is_sample=True``."""

    schema_version: int = 1
    is_sample: bool = True
    sample_banner: str
    sample_disclaimer: str
    query_id: str
    stock_code: str
    stock_name: str
    created_at: str
    report: Dict[str, Any]

