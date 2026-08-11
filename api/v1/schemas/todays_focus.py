# -*- coding: utf-8 -*-
"""Strict schemas for Today's Focus recommendations (Issue #157 / T26)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, List, Literal, Optional, Union

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    model_validator,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


TodaysFocusReasonCode = Literal[
    "alert_triggered",
    "corporate_event",
    "analysis_reversal",
]
TodaysFocusStatus = Literal["ok", "empty", "degraded"]
TodaysFocusSource = Literal[
    "alert",
    "analysis",
    "corporate_event",
    "alerts",
    "analysis_history",
    "corporate_events",
]
TodaysFocusDegradedSource = Literal[
    "alerts",
    "analysis_history",
    "corporate_events",
    "portfolio_position_cache",
]
TodaysFocusMarketCode = Literal["cn", "hk", "us", "unknown"]


class TodaysFocusAlertEvidence(_StrictModel):
    type: Literal["alert"]
    trigger_id: int = Field(gt=0)
    rule_id: Optional[int] = Field(default=None, gt=0)
    observed_at: AwareDatetime
    status: Literal["triggered"]
    source: Optional[str] = Field(default=None, min_length=1, max_length=64)


class TodaysFocusAnalysisEvidence(_StrictModel):
    type: Literal["analysis"]
    record_id: int = Field(gt=0)
    query_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    observed_at: AwareDatetime
    previous_observed_at: AwareDatetime
    previous_action: Literal["buy", "sell", "hold"]
    latest_action: Literal["buy", "sell", "hold"]

    @model_validator(mode="after")
    def validate_reversal(self) -> "TodaysFocusAnalysisEvidence":
        if self.previous_observed_at > self.observed_at:
            raise ValueError("previous_observed_at must not follow observed_at")
        if self.previous_action == self.latest_action:
            raise ValueError("analysis reversal actions must differ")
        return self


class TodaysFocusCorporateEventEvidence(_StrictModel):
    type: Literal["corporate_event"]
    event_id: str = Field(min_length=1, max_length=128)
    observed_at: AwareDatetime
    href: str = Field(pattern=r"^/[^/].*", max_length=512)


TodaysFocusEvidence = Annotated[
    Union[
        TodaysFocusAlertEvidence,
        TodaysFocusAnalysisEvidence,
        TodaysFocusCorporateEventEvidence,
    ],
    Field(discriminator="type"),
]


class TodaysFocusCostContract(_StrictModel):
    alert_repository_calls: int = Field(ge=0, le=1)
    portfolio_repository_calls: int = Field(ge=0, le=1)
    analysis_history_repository_calls: int = Field(ge=0, le=1)
    event_repository_calls: int = Field(ge=0, le=1)
    database_writes: Literal[0]
    provider_calls: Literal[0]
    analysis_runs_triggered: Literal[0]
    zero_extra_fetch: Literal[True]
    read_only: Literal[True]


class TodaysFocusPresentationBoundary(_StrictModel):
    alerts_owned_by: Literal["signal_center"]
    focus_shows: Literal["prioritized_symbols_with_evidence_links"]
    duplicate_alert_ui: Literal[False]


class TodaysFocusMarketDayWindow(_StrictModel):
    market: TodaysFocusMarketCode
    timezone: str = Field(min_length=1, max_length=64)
    local_date: date
    window_start: AwareDatetime
    window_end: AwareDatetime
    is_trading_day: Optional[bool] = None

    @model_validator(mode="after")
    def validate_window(self) -> "TodaysFocusMarketDayWindow":
        if self.window_start > self.window_end:
            raise ValueError("window_start must not follow window_end")
        return self


class TodaysFocusTemporalPolicy(_StrictModel):
    semantics: Literal["per_market_local_calendar_day"]
    cross_market_rule: Literal["evidence_uses_target_symbol_market_timezone"]
    fallback_timezone: str = Field(min_length=1, max_length=64)
    window_end: AwareDatetime
    naive_timestamp_policy: Literal["assume_utc"]
    missing_timestamp_policy: Literal["exclude"]
    non_trading_day_policy: Literal["same_local_day_only"]
    markets: List[TodaysFocusMarketDayWindow] = Field(min_length=4, max_length=8)

    @model_validator(mode="after")
    def validate_required_markets(self) -> "TodaysFocusTemporalPolicy":
        codes = [window.market for window in self.markets]
        if len(codes) != len(set(codes)):
            raise ValueError("temporal_policy markets must be unique")
        required = {"cn", "hk", "us", "unknown"}
        if not required.issubset(set(codes)):
            raise ValueError("temporal_policy must include cn, hk, us, and unknown windows")
        for window in self.markets:
            if window.window_end != self.window_end:
                raise ValueError("market windows must share the build window_end")
        return self


class TodaysFocusUniverseContract(_StrictModel):
    symbol_count: int = Field(ge=0, le=1000)
    hard_cap: Literal[1000]
    truncated: bool
    sources: List[
        Literal[
            "injected_evidences",
            "portfolio_position_cache",
            "request",
            "watchlist_config",
        ]
    ] = Field(max_length=4)
    excluded_non_finite_positions: int = Field(ge=0, le=100000)
    data_notes: List[str] = Field(default_factory=list, max_length=4)


class TodaysFocusItem(_StrictModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=80)
    reason_code: TodaysFocusReasonCode
    reason_display: str = Field(min_length=1, max_length=240)
    priority: int = Field(ge=0, le=100)
    weight_pct: Optional[FiniteFloat] = Field(default=None, ge=0, le=100)
    secondary_reason_codes: List[TodaysFocusReasonCode] = Field(max_length=2)
    evidence: TodaysFocusEvidence

    @model_validator(mode="after")
    def validate_reason_evidence_pair(self) -> "TodaysFocusItem":
        expected = {
            "alert_triggered": "alert",
            "corporate_event": "corporate_event",
            "analysis_reversal": "analysis",
        }[self.reason_code]
        if self.evidence.type != expected:
            raise ValueError("reason_code does not match evidence type")
        if self.reason_code in self.secondary_reason_codes:
            raise ValueError("primary reason cannot also be secondary")
        if len(set(self.secondary_reason_codes)) != len(self.secondary_reason_codes):
            raise ValueError("secondary reason codes must be unique")
        return self


class TodaysFocusResponse(_StrictModel):
    pack_version: Literal["todays_focus/2.1"]
    generated_at: AwareDatetime
    status: TodaysFocusStatus
    max_items: int = Field(ge=0, le=10)
    item_count: int = Field(ge=0, le=10)
    items: List[TodaysFocusItem] = Field(max_length=10)
    empty_reason: Optional[
        Literal[
            "source_unavailable",
            "no_fresh_deterministic_signals",
            "insufficient_finite_data",
        ]
    ] = None
    empty_message: Optional[str] = Field(default=None, max_length=240)
    sources_used: List[TodaysFocusSource] = Field(max_length=6)
    degraded_sources: List[TodaysFocusDegradedSource] = Field(max_length=4)
    temporal_policy: TodaysFocusTemporalPolicy
    universe_contract: TodaysFocusUniverseContract
    cost_contract: TodaysFocusCostContract
    presentation_boundary: TodaysFocusPresentationBoundary

    @model_validator(mode="after")
    def validate_aggregate_counts(self) -> "TodaysFocusResponse":
        if self.item_count != len(self.items):
            raise ValueError("item_count must match items")
        if self.item_count > self.max_items:
            raise ValueError("item_count must not exceed max_items")
        if self.status == "empty" and self.items:
            raise ValueError("empty status cannot include items")
        if self.status == "ok" and not self.items:
            raise ValueError("ok status requires at least one item")
        if self.items and self.empty_reason is not None:
            raise ValueError("non-empty responses cannot include empty_reason")
        if not self.items and self.empty_reason is None:
            raise ValueError("empty responses require empty_reason")
        return self
