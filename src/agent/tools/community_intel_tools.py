# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Stock-scoped ToolDefinition contract for bounded community intelligence."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from data_provider.base import canonical_stock_code, normalize_stock_code
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy
from src.utils.sanitize import (
    exception_chain_redaction_values,
    log_safe_exception,
    redact_sensitive_text,
)

logger = logging.getLogger(__name__)

COMMUNITY_INTEL_TOOL_NAME = "get_community_intel_brief"
COMMUNITY_INTEL_SCHEMA_VERSION = "community-intel-brief-v1"
COMMUNITY_INTEL_DEFAULT_WINDOW_DAYS = 7
COMMUNITY_INTEL_MAX_WINDOW_DAYS = 30
COMMUNITY_INTEL_MAX_RESULT_BYTES = 8 * 1024
COMMUNITY_INTEL_DISCLAIMER = (
    "Community and social signals are unverified supporting evidence, not "
    "investment advice or trading authority."
)

_STOCK_CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9.-]{0,15}$"
_SOURCE_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,23}$"
_MAX_SUMMARY_CHARS = 1200
_MAX_CONFIDENCE_BASIS_CHARS = 240
_MAX_THEME_CHARS = 80
_MAX_GAP_CHARS = 120
_MAX_REFERENCE_CHARS = 160
_MAX_CITATION_URL_CHARS = 500

CommunityIntelTone = Literal["bullish", "bearish", "mixed", "unclear"]
CommunityIntelVolumeSignal = Literal["low", "normal", "elevated", "unavailable"]
CommunityIntelCoverageStatus = Literal["available", "partial", "unavailable"]
CommunityIntelResultStatus = Literal["available", "degraded", "unavailable"]
CommunityIntelReasonCode = Literal[
    "partial_coverage",
    "provider_not_configured",
    "provider_timeout",
    "no_data",
    "provider_error",
    "invalid_provider_output",
    "output_too_large",
]


class _StrictCommunityIntelModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        strict=True,
    )


def _parse_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp must use ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed


def _validate_timestamp(value: str | None) -> str | None:
    if value is not None:
        _parse_timestamp(value)
    return value


class CommunityIntelCoverage(_StrictCommunityIntelModel):
    source_id: str = Field(pattern=_SOURCE_ID_PATTERN)
    status: CommunityIntelCoverageStatus
    as_of: str | None = Field(default=None, max_length=40)

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_timestamp(cls, value: str | None) -> str | None:
        return _validate_timestamp(value)


class CommunityIntelCitation(_StrictCommunityIntelModel):
    source_id: str = Field(pattern=_SOURCE_ID_PATTERN)
    reference_id: str = Field(min_length=1, max_length=_MAX_REFERENCE_CHARS)
    url: str | None = Field(default=None, max_length=_MAX_CITATION_URL_CHARS)

    @field_validator("url")
    @classmethod
    def _url_must_be_public_http_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("citation URL is invalid") from exc
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or port is not None and not 1 <= port <= 65535
        ):
            raise ValueError("citation URL must be credential-free HTTP(S)")
        return value


class CommunityIntelObservation(_StrictCommunityIntelModel):
    stock_code: str = Field(pattern=_STOCK_CODE_PATTERN)
    language: Literal["zh", "en"]
    as_of: str = Field(max_length=40)
    window_days: int = Field(ge=1, le=COMMUNITY_INTEL_MAX_WINDOW_DAYS)
    window_start: str = Field(max_length=40)
    window_end: str = Field(max_length=40)
    summary: str = Field(min_length=1, max_length=_MAX_SUMMARY_CHARS)
    tone: CommunityIntelTone
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_basis: str = Field(min_length=1, max_length=_MAX_CONFIDENCE_BASIS_CHARS)
    themes: tuple[str, ...] = Field(default=(), max_length=8)
    volume_signal: CommunityIntelVolumeSignal
    coverage: tuple[CommunityIntelCoverage, ...] = Field(min_length=1, max_length=4)
    citations: tuple[CommunityIntelCitation, ...] = Field(default=(), max_length=6)
    gaps: tuple[str, ...] = Field(default=(), max_length=8)

    @field_validator("as_of", "window_start", "window_end")
    @classmethod
    def _timestamps_must_be_explicit(cls, value: str) -> str:
        _validate_timestamp(value)
        return value

    @field_validator("themes")
    @classmethod
    def _themes_must_be_bounded(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or len(value) > _MAX_THEME_CHARS for value in values):
            raise ValueError("themes must contain bounded non-empty strings")
        if len(set(values)) != len(values):
            raise ValueError("themes must be unique")
        return values

    @field_validator("gaps")
    @classmethod
    def _gaps_must_be_bounded(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or len(value) > _MAX_GAP_CHARS for value in values):
            raise ValueError("gaps must contain bounded non-empty strings")
        if len(set(values)) != len(values):
            raise ValueError("gaps must be unique")
        return values

    @model_validator(mode="after")
    def _validate_evidence_relationships(self) -> "CommunityIntelObservation":
        as_of = _parse_timestamp(self.as_of)
        window_start = _parse_timestamp(self.window_start)
        window_end = _parse_timestamp(self.window_end)
        if window_start > window_end or window_end > as_of:
            raise ValueError("provider timestamps must satisfy start <= end <= as_of")
        if window_end - window_start > timedelta(days=self.window_days):
            raise ValueError("provider evidence window exceeds the requested bound")
        source_ids = [item.source_id for item in self.coverage]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("coverage source ids must be unique")
        known_sources = set(source_ids)
        if any(citation.source_id not in known_sources for citation in self.citations):
            raise ValueError("citation source must be present in coverage")
        return self


class CommunityIntelWindow(_StrictCommunityIntelModel):
    days: int = Field(ge=1, le=COMMUNITY_INTEL_MAX_WINDOW_DAYS)
    start: str | None = Field(default=None, max_length=40)
    end: str | None = Field(default=None, max_length=40)

    @field_validator("start", "end")
    @classmethod
    def _timestamps_must_be_explicit(cls, value: str | None) -> str | None:
        return _validate_timestamp(value)


class CommunityIntelBriefResult(_StrictCommunityIntelModel):
    schema_version: Literal["community-intel-brief-v1"] = COMMUNITY_INTEL_SCHEMA_VERSION
    status: CommunityIntelResultStatus
    degraded: bool
    reason_code: CommunityIntelReasonCode | None
    stock_code: str = Field(pattern=_STOCK_CODE_PATTERN)
    language: Literal["zh", "en"]
    as_of: str | None = Field(default=None, max_length=40)
    window: CommunityIntelWindow
    summary: str = Field(min_length=1, max_length=_MAX_SUMMARY_CHARS)
    tone: CommunityIntelTone
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_basis: str = Field(min_length=1, max_length=_MAX_CONFIDENCE_BASIS_CHARS)
    themes: tuple[str, ...] = Field(default=(), max_length=8)
    volume_signal: CommunityIntelVolumeSignal
    coverage: tuple[CommunityIntelCoverage, ...] = Field(default=(), max_length=4)
    citations: tuple[CommunityIntelCitation, ...] = Field(default=(), max_length=6)
    gaps: tuple[str, ...] = Field(default=(), max_length=8)
    disclaimer: str

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_timestamp(cls, value: str | None) -> str | None:
        return _validate_timestamp(value)

    @field_validator("disclaimer")
    @classmethod
    def _disclaimer_is_mandatory(cls, value: str) -> str:
        if value != COMMUNITY_INTEL_DISCLAIMER:
            raise ValueError("community intelligence disclaimer is mandatory")
        return value

    @model_validator(mode="after")
    def _status_matches_evidence(self) -> "CommunityIntelBriefResult":
        if self.status == "available":
            if self.degraded or self.reason_code is not None:
                raise ValueError("available results cannot carry degradation state")
            if self.as_of is None or self.confidence is None or not self.coverage:
                raise ValueError("available results require dated confidence and coverage")
        elif not self.degraded or self.reason_code is None:
            raise ValueError("non-available results require a degradation reason")
        return self


class CommunityIntelProvider(Protocol):
    @property
    def is_configured(self) -> bool: ...

    def get_brief(
        self,
        *,
        stock_code: str,
        window_days: int,
        language_hint: Literal["zh", "en"],
    ) -> CommunityIntelObservation | None: ...


_COMMUNITY_INTEL_POLICY = ToolPolicy.declared(
    read_only=True,
    side_effects=["network_read"],
    permissions=["community_intel:read"],
    scope_dimensions=["stock"],
)

_DEGRADED_SUMMARIES: dict[CommunityIntelReasonCode, str] = {
    "partial_coverage": "Community intelligence has partial source coverage.",
    "provider_not_configured": "Community intelligence is not configured.",
    "provider_timeout": "Community intelligence was not available within the bounded time window.",
    "no_data": "No community intelligence was available for the requested stock and window.",
    "provider_error": "Community intelligence is temporarily unavailable.",
    "invalid_provider_output": "Community intelligence was rejected because its evidence contract was invalid.",
    "output_too_large": "Community intelligence was rejected because its bounded payload limit was exceeded.",
}


def _canonical_code(stock_code: str) -> str:
    return canonical_stock_code(normalize_stock_code(stock_code.strip()))


def _safe_text(value: str, max_chars: int) -> str:
    return redact_sensitive_text(value, redact_opaque_tokens=True)[:max_chars]


def _safe_identifier(value: str) -> str:
    safe = redact_sensitive_text(value, redact_opaque_tokens=True)
    if safe != value:
        raise ValueError("source identity contained sensitive material")
    return safe


def _safe_citation_url(value: str) -> tuple[str | None, bool]:
    safe = _safe_text(value, _MAX_CITATION_URL_CHARS)
    if safe != value or not safe.lower().startswith(("http://", "https://")):
        return None, True
    return safe, False


def _result_dict(result: CommunityIntelBriefResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def _serialized_size(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, allow_nan=False, default=str).encode("utf-8"))


def _degraded_result(
    *,
    stock_code: str,
    language: Literal["zh", "en"],
    window_days: int,
    reason_code: CommunityIntelReasonCode,
    status: Literal["degraded", "unavailable"],
) -> dict[str, Any]:
    return _result_dict(
        CommunityIntelBriefResult(
            status=status,
            degraded=True,
            reason_code=reason_code,
            stock_code=stock_code,
            language=language,
            as_of=None,
            window=CommunityIntelWindow(days=window_days),
            summary=_DEGRADED_SUMMARIES[reason_code],
            tone="unclear",
            confidence=None,
            confidence_basis="No confidence score is reported without validated source evidence.",
            themes=(),
            volume_signal="unavailable",
            coverage=(),
            citations=(),
            gaps=(reason_code,),
            disclaimer=COMMUNITY_INTEL_DISCLAIMER,
        )
    )


def _project_observation(
    observation: CommunityIntelObservation,
    *,
    stock_code: str,
    language: Literal["zh", "en"],
    window_days: int,
) -> dict[str, Any]:
    if (
        _canonical_code(observation.stock_code) != stock_code
        or observation.language != language
        or observation.window_days != window_days
    ):
        raise ValueError("provider observation does not match the requested scope")
    coverage = tuple(
        CommunityIntelCoverage(
            source_id=_safe_identifier(item.source_id),
            status=item.status,
            as_of=item.as_of,
        )
        for item in observation.coverage
    )
    projected_citations = []
    citation_url_redacted = False
    for item in observation.citations:
        safe_url = None
        if item.url is not None:
            safe_url, was_redacted = _safe_citation_url(item.url)
            citation_url_redacted = citation_url_redacted or was_redacted
        projected_citations.append(
            CommunityIntelCitation(
                source_id=_safe_identifier(item.source_id),
                reference_id=_safe_text(item.reference_id, _MAX_REFERENCE_CHARS),
                url=safe_url,
            )
        )
    citations = tuple(projected_citations)
    themes = tuple(_safe_text(item, _MAX_THEME_CHARS) for item in observation.themes)
    projected_gaps = [_safe_text(item, _MAX_GAP_CHARS) for item in observation.gaps]
    if citation_url_redacted and "citation_url_redacted" not in projected_gaps and len(projected_gaps) < 8:
        projected_gaps.append("citation_url_redacted")
    gaps = tuple(projected_gaps)
    is_partial = bool(gaps) or any(item.status != "available" for item in coverage)
    status: CommunityIntelResultStatus = "degraded" if is_partial else "available"
    reason_code: CommunityIntelReasonCode | None = "partial_coverage" if is_partial else None
    return _result_dict(
        CommunityIntelBriefResult(
            status=status,
            degraded=is_partial,
            reason_code=reason_code,
            stock_code=stock_code,
            language=language,
            as_of=observation.as_of,
            window=CommunityIntelWindow(
                days=window_days,
                start=observation.window_start,
                end=observation.window_end,
            ),
            summary=_safe_text(observation.summary, _MAX_SUMMARY_CHARS),
            tone=observation.tone,
            confidence=observation.confidence,
            confidence_basis=_safe_text(observation.confidence_basis, _MAX_CONFIDENCE_BASIS_CHARS),
            themes=themes,
            volume_signal=observation.volume_signal,
            coverage=coverage,
            citations=citations,
            gaps=gaps,
            disclaimer=COMMUNITY_INTEL_DISCLAIMER,
        )
    )


class _CommunityIntelToolHandler:
    def __init__(self, provider: CommunityIntelProvider | None) -> None:
        self._provider = provider

    def __call__(
        self,
        stock_code: str,
        window_days: int = COMMUNITY_INTEL_DEFAULT_WINDOW_DAYS,
        language_hint: Literal["zh", "en"] = "en",
    ) -> dict[str, Any]:
        canonical_code = _canonical_code(stock_code)
        if self._provider is None:
            return _degraded_result(
                stock_code=canonical_code,
                language=language_hint,
                window_days=window_days,
                reason_code="provider_not_configured",
                status="unavailable",
            )
        try:
            configured = self._provider.is_configured
            if type(configured) is not bool:
                return _degraded_result(
                    stock_code=canonical_code,
                    language=language_hint,
                    window_days=window_days,
                    reason_code="invalid_provider_output",
                    status="degraded",
                )
            if not configured:
                return _degraded_result(
                    stock_code=canonical_code,
                    language=language_hint,
                    window_days=window_days,
                    reason_code="provider_not_configured",
                    status="unavailable",
                )
            observation = self._provider.get_brief(
                stock_code=canonical_code,
                window_days=window_days,
                language_hint=language_hint,
            )
        except TimeoutError as exc:
            log_safe_exception(
                logger,
                "Community intelligence provider timed out",
                exc,
                error_code="community_intel_provider_timeout",
                level=logging.WARNING,
                context={"stock_code": canonical_code},
                exception_redaction_values=exception_chain_redaction_values(exc),
            )
            return _degraded_result(
                stock_code=canonical_code,
                language=language_hint,
                window_days=window_days,
                reason_code="provider_timeout",
                status="degraded",
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Typed optional-provider degradation.
            log_safe_exception(
                logger,
                "Community intelligence provider failed",
                exc,
                error_code="community_intel_provider_failed",
                level=logging.WARNING,
                context={"stock_code": canonical_code},
                exception_redaction_values=exception_chain_redaction_values(exc),
            )
            return _degraded_result(
                stock_code=canonical_code,
                language=language_hint,
                window_days=window_days,
                reason_code="provider_error",
                status="degraded",
            )
        if observation is None:
            return _degraded_result(
                stock_code=canonical_code,
                language=language_hint,
                window_days=window_days,
                reason_code="no_data",
                status="unavailable",
            )
        if not isinstance(observation, CommunityIntelObservation):
            return _degraded_result(
                stock_code=canonical_code,
                language=language_hint,
                window_days=window_days,
                reason_code="invalid_provider_output",
                status="degraded",
            )
        try:
            payload = _project_observation(
                observation,
                stock_code=canonical_code,
                language=language_hint,
                window_days=window_days,
            )
        except (TypeError, ValueError, ValidationError):
            return _degraded_result(
                stock_code=canonical_code,
                language=language_hint,
                window_days=window_days,
                reason_code="invalid_provider_output",
                status="degraded",
            )
        if _serialized_size(payload) > COMMUNITY_INTEL_MAX_RESULT_BYTES:
            return _degraded_result(
                stock_code=canonical_code,
                language=language_hint,
                window_days=window_days,
                reason_code="output_too_large",
                status="degraded",
            )
        return payload


def build_community_intel_tool(
    provider: CommunityIntelProvider | None = None,
) -> ToolDefinition:
    """Build an explicitly registered Phase A community-intelligence tool."""
    return ToolDefinition(
        name=COMMUNITY_INTEL_TOOL_NAME,
        description=(
            "Return a bounded, source-attributed community intelligence brief "
            "for the stock already authorized in the current analysis scope."
        ),
        parameters=[
            ToolParameter(
                name="stock_code",
                type="string",
                description="Stock code already authorized by the current analysis scope.",
                pattern=_STOCK_CODE_PATTERN,
            ),
            ToolParameter(
                name="window_days",
                type="integer",
                description="Bounded evidence window in calendar days (1-30).",
                required=False,
                default=COMMUNITY_INTEL_DEFAULT_WINDOW_DAYS,
                minimum=1,
                maximum=COMMUNITY_INTEL_MAX_WINDOW_DAYS,
            ),
            ToolParameter(
                name="language_hint",
                type="string",
                description="Preferred brief language.",
                required=False,
                default="en",
                enum=["zh", "en"],
            ),
        ],
        handler=_CommunityIntelToolHandler(provider),
        category="search",
        policy=_COMMUNITY_INTEL_POLICY,
        enforce_contract=True,
    )
