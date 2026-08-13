# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Alternative-data domain contract (Issues #139 / #1144).

Alternative data (corporate events, holdings, supply-chain tags, quantified
sentiment, …) is always **non-authoritative supporting evidence**. It must not
enter the verified-fact or core decision authority path. Bad or missing
payloads become explicit gaps; handlers must never invent values.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ALTERNATIVE_DATA_SCHEMA_VERSION: Literal["alternative-data-v1"] = "alternative-data-v1"

# Fixed authority: alt-data is never core market fact and never decision authority.
AlternativeDataAuthority = Literal["non_authoritative"]
AlternativeDataRole = Literal["supporting_only"]

AlternativeDataCategory = Literal[
    "corporate_events",
    "holdings",
    "supply_chain",
    "quantified_sentiment",
]

AlternativeDataResultStatus = Literal["available", "degraded", "unavailable"]
AlternativeDataCoverageStatus = Literal["available", "partial", "unavailable"]
AlternativeDataReasonCode = Literal[
    "partial_coverage",
    "provider_not_configured",
    "provider_timeout",
    "no_data",
    "provider_error",
    "invalid_provider_output",
    "output_too_large",
    "feature_disabled",
    "capability_denied",
]

# Evidence stratification: alt-data may only appear under these consumer strata.
AlternativeDataEvidenceStratum = Literal[
    "model_inference",
    "synthesis",
    "gap",
]
# Explicit blocklist for any consumer that projects alt-data into conclusions.
ALTERNATIVE_DATA_FORBIDDEN_CONCLUSION_STRATA: frozenset[str] = frozenset(
    {
        "verified_fact",
        "decision",
    }
)

ALT_DATA_PERMISSION = "alt_data:read"
ALT_DATA_DISCLAIMER = (
    "Alternative data is unverified supporting evidence only. It is not "
    "authoritative market fact, not investment advice, and must not drive "
    "core conclusions without independent primary sources."
)

_SOURCE_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,23}$"
_EVENT_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$"
_STOCK_CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9.-]{0,15}$"


class _StrictAltDataModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
        strict=True,
    )



def _coerce_tuple(value: object) -> object:
    """Accept JSON lists while keeping stored values as immutable tuples."""

    if isinstance(value, list):
        return tuple(value)
    return value


def _parse_timestamp(value: str) -> None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    from datetime import datetime

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp must use ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")


class AlternativeDataCoverage(_StrictAltDataModel):
    source_id: str = Field(pattern=_SOURCE_ID_PATTERN)
    status: AlternativeDataCoverageStatus
    as_of: Optional[str] = Field(default=None, max_length=40)

    @field_validator("as_of")
    @classmethod
    def _as_of_timestamp(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            _parse_timestamp(value)
        return value


class AlternativeDataCitation(_StrictAltDataModel):
    source_id: str = Field(pattern=_SOURCE_ID_PATTERN)
    reference_id: str = Field(min_length=1, max_length=160)
    url: Optional[str] = Field(default=None, max_length=500)


class CorporateEventItem(_StrictAltDataModel):
    """One corporate-event observation (reference category for v1)."""

    event_id: str = Field(pattern=_EVENT_ID_PATTERN)
    event_type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=240)
    event_date: str = Field(min_length=4, max_length=40)
    impact_hint: Literal["positive", "negative", "neutral", "unclear"] = "unclear"
    source_id: str = Field(pattern=_SOURCE_ID_PATTERN)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class AlternativeDataObservation(_StrictAltDataModel):
    """Provider-side observation before host projection."""

    schema_version: Literal["alternative-data-v1"] = ALTERNATIVE_DATA_SCHEMA_VERSION
    category: AlternativeDataCategory
    stock_code: str = Field(pattern=_STOCK_CODE_PATTERN)
    language: Literal["zh", "en"] = "en"
    as_of: str = Field(min_length=4, max_length=40)
    summary: str = Field(min_length=1, max_length=1200)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence_basis: str = Field(min_length=1, max_length=240)
    events: tuple[CorporateEventItem, ...] = Field(default=(), max_length=12)
    coverage: tuple[AlternativeDataCoverage, ...] = Field(min_length=1, max_length=6)
    citations: tuple[AlternativeDataCitation, ...] = Field(default=(), max_length=8)
    gaps: tuple[str, ...] = Field(default=(), max_length=8)

    @field_validator("events", "coverage", "citations", "gaps", mode="before")
    @classmethod
    def _tuple_fields(cls, value: object) -> object:
        return _coerce_tuple(value)
    authority: AlternativeDataAuthority = "non_authoritative"
    role: AlternativeDataRole = "supporting_only"
    disclaimer: str = ALT_DATA_DISCLAIMER

    @field_validator("as_of")
    @classmethod
    def _as_of_timestamp(cls, value: str) -> str:
        _parse_timestamp(value)
        return value

    @field_validator("disclaimer")
    @classmethod
    def _disclaimer_fixed(cls, value: str) -> str:
        if value != ALT_DATA_DISCLAIMER:
            raise ValueError("alternative data disclaimer is mandatory and fixed")
        return value

    @model_validator(mode="after")
    def _authority_and_category_rules(self) -> "AlternativeDataObservation":
        if self.authority != "non_authoritative" or self.role != "supporting_only":
            raise ValueError("alternative data must remain non-authoritative supporting only")
        if self.category == "corporate_events" and not self.events and not self.gaps:
            raise ValueError("corporate_events observations require events or explicit gaps")
        if self.category != "corporate_events" and self.events:
            raise ValueError("events are only valid for corporate_events category")
        covered = {item.source_id for item in self.coverage}
        for citation in self.citations:
            if citation.source_id not in covered:
                raise ValueError("citation source_id must appear in coverage")
        for event in self.events:
            if event.source_id not in covered:
                raise ValueError("event source_id must appear in coverage")
        return self


class AlternativeDataResult(_StrictAltDataModel):
    """Host-projected tool / governance result envelope."""

    schema_version: Literal["alternative-data-v1"] = ALTERNATIVE_DATA_SCHEMA_VERSION
    status: AlternativeDataResultStatus
    degraded: bool = False
    reason_code: Optional[AlternativeDataReasonCode] = None
    category: AlternativeDataCategory
    stock_code: str = Field(pattern=_STOCK_CODE_PATTERN)
    language: Literal["zh", "en"] = "en"
    as_of: Optional[str] = Field(default=None, max_length=40)
    summary: str = Field(min_length=1, max_length=1200)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence_basis: str = Field(min_length=1, max_length=240)
    events: tuple[CorporateEventItem, ...] = Field(default=(), max_length=12)
    coverage: tuple[AlternativeDataCoverage, ...] = Field(default=(), max_length=6)
    citations: tuple[AlternativeDataCitation, ...] = Field(default=(), max_length=8)
    gaps: tuple[str, ...] = Field(default=(), max_length=12)

    @field_validator("events", "coverage", "citations", "gaps", mode="before")
    @classmethod
    def _tuple_fields(cls, value: object) -> object:
        return _coerce_tuple(value)
    authority: AlternativeDataAuthority = "non_authoritative"
    role: AlternativeDataRole = "supporting_only"
    disclaimer: str = ALT_DATA_DISCLAIMER

    @field_validator("disclaimer")
    @classmethod
    def _disclaimer_fixed(cls, value: str) -> str:
        if value != ALT_DATA_DISCLAIMER:
            raise ValueError("alternative data disclaimer is mandatory and fixed")
        return value

    @model_validator(mode="after")
    def _status_matches_evidence(self) -> "AlternativeDataResult":
        if self.authority != "non_authoritative" or self.role != "supporting_only":
            raise ValueError("alternative data must remain non-authoritative supporting only")
        if self.status == "available":
            if self.degraded or self.reason_code is not None:
                raise ValueError("available results cannot carry degradation state")
            if self.as_of is None or not self.coverage:
                raise ValueError("available results require as_of and coverage")
            if self.confidence is None:
                raise ValueError("available results require a validated confidence score")
        elif not self.degraded or self.reason_code is None:
            raise ValueError("non-available results require a degradation reason")
        else:
            # Fail closed: never invent numeric confidence without evidence.
            if self.confidence is not None and self.reason_code in {
                "no_data",
                "provider_not_configured",
                "feature_disabled",
                "capability_denied",
            }:
                raise ValueError("unavailable results must not invent confidence")
        return self


class AlternativeDataEvidenceItem(_StrictAltDataModel):
    """Citable evidence item projected from alt-data (supporting stratum only)."""

    evidence_id: str = Field(min_length=1, max_length=96)
    source_type: Literal["data_source", "tool_call"] = "data_source"
    source_id: Optional[str] = Field(default=None, max_length=160)
    snippet: Optional[str] = Field(default=None, max_length=800)
    as_of: Optional[str] = Field(default=None, max_length=64)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: Literal["present", "missing", "partial"] = "present"
    authority: AlternativeDataAuthority = "non_authoritative"
    role: AlternativeDataRole = "supporting_only"
    missing_reason: Optional[str] = Field(default=None, max_length=240)


class AlternativeDataConclusionLink(_StrictAltDataModel):
    """Supporting conclusion link that cannot claim verified-fact or decision authority."""

    conclusion_id: str = Field(min_length=1, max_length=96)
    stratum: AlternativeDataEvidenceStratum
    statement: str = Field(min_length=1, max_length=1200)
    evidence_refs: List[str] = Field(default_factory=list, max_length=32)
    evidence_status: Literal["linked", "missing", "partial"] = "missing"
    authority: AlternativeDataAuthority = "non_authoritative"
    role: AlternativeDataRole = "supporting_only"

    @model_validator(mode="after")
    def _forbid_core_strata(self) -> "AlternativeDataConclusionLink":
        if self.stratum in ALTERNATIVE_DATA_FORBIDDEN_CONCLUSION_STRATA:
            raise ValueError("alternative data cannot project into core conclusion strata")
        if self.stratum == "gap" and self.evidence_status == "linked" and self.evidence_refs:
            raise ValueError("gap conclusions must not claim linked primary evidence")
        return self


class AlternativeDataEvidenceProjection(_StrictAltDataModel):
    """Bounded evidence projection used by governance and future evidence-chain consumers."""

    schema_version: Literal["alternative-data-v1"] = ALTERNATIVE_DATA_SCHEMA_VERSION
    category: AlternativeDataCategory
    stock_code: str
    authority: AlternativeDataAuthority = "non_authoritative"
    role: AlternativeDataRole = "supporting_only"
    evidence_items: List[AlternativeDataEvidenceItem] = Field(default_factory=list, max_length=64)
    conclusions: List[AlternativeDataConclusionLink] = Field(default_factory=list, max_length=32)
    gaps: List[str] = Field(default_factory=list, max_length=16)
    pollutes_core_quality: Literal[False] = False
    disclaimer: str = ALT_DATA_DISCLAIMER
