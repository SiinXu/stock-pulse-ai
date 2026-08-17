# -*- coding: utf-8 -*-
"""Transport DTOs for bounded AI candidate discovery (#177 / #325)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class CandidateDiscoveryCriteria(BaseModel):
    markets: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    min_change_pct: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("min_change_pct", "minChangePct"),
    )
    max_change_pct: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("max_change_pct", "maxChangePct"),
    )
    min_amount: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("min_amount", "minAmount"),
    )
    exclude_st: bool = Field(
        default=True,
        validation_alias=AliasChoices("exclude_st", "excludeSt"),
    )

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class CandidateDiscoveryRequest(BaseModel):
    query: str = Field("", max_length=500)
    criteria: Optional[CandidateDiscoveryCriteria] = None
    universe: str = Field(
        "watchlist",
        min_length=1,
        max_length=32,
        description="watchlist | portfolio | index | codes",
    )
    page: int = Field(1, ge=1, le=10000)
    page_size: int = Field(
        50,
        ge=1,
        le=100,
        validation_alias=AliasChoices("page_size", "pageSize"),
    )
    max_results: int = Field(
        10,
        ge=1,
        le=30,
        validation_alias=AliasChoices("max_results", "maxResults"),
    )
    max_provider_calls: int = Field(
        20,
        ge=0,
        le=50,
        validation_alias=AliasChoices("max_provider_calls", "maxProviderCalls"),
    )
    codes: List[str] = Field(default_factory=list, max_length=100)
    markets: List[str] = Field(default_factory=list)
    account_id: Optional[int] = Field(
        default=None,
        ge=1,
        validation_alias=AliasChoices("account_id", "accountId"),
    )
    use_llm: bool = Field(
        False,
        validation_alias=AliasChoices("use_llm", "useLlm"),
    )
    language: str = Field("en", pattern="^(en|zh)$")

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class CandidateDiscoveryCandidate(BaseModel):
    rank: int
    code: str
    name: str = ""
    score: Optional[float] = None
    reason: str = ""
    reason_codes: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("reason_codes", "reasonCodes"),
    )
    risk_level: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("risk_level", "riskLevel"),
    )
    price: Optional[float] = None
    change_pct: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("change_pct", "changePct"),
    )
    amount: Optional[float] = None
    industry: Optional[str] = None
    factor_scores: Dict[str, float] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("factor_scores", "factorScores"),
    )
    llm_thesis: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("llm_thesis", "llmThesis"),
    )
    market: Optional[str] = None
    provider: Optional[str] = None
    selection_source: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("selection_source", "selectionSource"),
    )

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class CandidateDiscoveryResponse(BaseModel):
    pack_version: str = Field(validation_alias=AliasChoices("pack_version", "packVersion"))
    run_id: str = Field(validation_alias=AliasChoices("run_id", "runId"))
    status: str
    query: str = ""
    universe: str
    market: str = "cn"
    page: int = 1
    page_size: int = Field(50, validation_alias=AliasChoices("page_size", "pageSize"))
    max_results: int = Field(10, validation_alias=AliasChoices("max_results", "maxResults"))
    candidate_count: int = Field(validation_alias=AliasChoices("candidate_count", "candidateCount"))
    candidates: List[CandidateDiscoveryCandidate] = Field(default_factory=list)
    criteria: Dict[str, Any] = Field(default_factory=dict)
    empty_reason: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("empty_reason", "emptyReason"),
    )
    empty_message: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("empty_message", "emptyMessage"),
    )
    warnings: List[str] = Field(default_factory=list)
    research_disclaimer: str = Field(
        default="Research screening only. Not investment advice or trade instructions.",
        validation_alias=AliasChoices("research_disclaimer", "researchDisclaimer"),
    )
    universe_contract: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("universe_contract", "universeContract"),
    )
    cost_contract: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("cost_contract", "costContract"),
    )

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class CandidateDiscoveryTaskAccepted(BaseModel):
    task_id: str = Field(validation_alias=AliasChoices("task_id", "taskId"))
    trace_id: str = Field(validation_alias=AliasChoices("trace_id", "traceId"))
    status: str
    message: str
    message_code: str = Field(
        default="task.discovery.queued",
        validation_alias=AliasChoices("message_code", "messageCode"),
    )
    message_params: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("message_params", "messageParams"),
    )
    universe: str
    page: int
    page_size: int = Field(validation_alias=AliasChoices("page_size", "pageSize"))
    max_results: int = Field(validation_alias=AliasChoices("max_results", "maxResults"))
    max_provider_calls: int = Field(
        validation_alias=AliasChoices("max_provider_calls", "maxProviderCalls")
    )

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class CandidateDiscoveryTaskStatus(BaseModel):
    task_id: str = Field(validation_alias=AliasChoices("task_id", "taskId"))
    trace_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("trace_id", "traceId"),
    )
    status: str
    progress: int = 0
    message: Optional[str] = None
    message_code: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("message_code", "messageCode"),
    )
    message_params: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("message_params", "messageParams"),
    )
    error: Optional[str] = None
    result: Optional[CandidateDiscoveryResponse] = None

    model_config = ConfigDict(extra="allow", populate_by_name=True)
