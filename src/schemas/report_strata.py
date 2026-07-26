# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Report strata presentation contract (Issue #616).

Fixed strata keep model inference from being read as verified fact. This module
defines the additive domain payload only; template and Web rendering consume it
separately. Historical reports without strata remain valid when the field is
absent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


REPORT_STRATA_SCHEMA_VERSION = "report-strata-v1"

FrameworkAlignmentStatus = Literal[
    "aligned",
    "partial",
    "conflict",
    "not_configured",
]
DataGapKind = Literal["missing", "conflict"]

DEFAULT_DISCLAIMER_ZH = "AI生成，仅供参考，不构成投资建议"
DEFAULT_DISCLAIMER_EN = (
    "AI-generated content for reference only. Not investment advice."
)
DEFAULT_DISCLAIMER_KO = "AI 생성 참고용이며 투자 권유가 아닙니다."

FRAMEWORK_NOT_CONFIGURED_SUMMARY_ZH = "个人投资框架未配置"
FRAMEWORK_NOT_CONFIGURED_SUMMARY_EN = "Personal investment framework not configured"
FRAMEWORK_NOT_CONFIGURED_SUMMARY_KO = "개인 투자 프레임워크가 구성되지 않음"


def default_disclaimer(language: Optional[str] = None) -> str:
    """Return the mandatory non-investment-advice disclaimer for a language."""
    key = (language or "zh").strip().lower()
    if key.startswith("en"):
        return DEFAULT_DISCLAIMER_EN
    if key.startswith("ko"):
        return DEFAULT_DISCLAIMER_KO
    return DEFAULT_DISCLAIMER_ZH


def default_framework_not_configured_summary(language: Optional[str] = None) -> str:
    """Return the default framework slot copy when no framework is active."""
    key = (language or "zh").strip().lower()
    if key.startswith("en"):
        return FRAMEWORK_NOT_CONFIGURED_SUMMARY_EN
    if key.startswith("ko"):
        return FRAMEWORK_NOT_CONFIGURED_SUMMARY_KO
    return FRAMEWORK_NOT_CONFIGURED_SUMMARY_ZH


class VerifiedFact(BaseModel):
    """One verified-fact line with optional source id and as-of timestamp."""

    statement: str = Field(..., min_length=1)
    source_id: Optional[str] = None
    as_of: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("statement", "source_id", "as_of", mode="before")
    @classmethod
    def _strip_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("statement")
    @classmethod
    def _require_statement(cls, value: Optional[str]) -> str:
        if not value:
            raise ValueError("verified fact statement is required")
        return value


class DataGapOrConflict(BaseModel):
    """Missing data or a source conflict that must not be presented as fact."""

    kind: DataGapKind
    description: str = Field(..., min_length=1)
    source_ids: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @field_validator("description", mode="before")
    @classmethod
    def _strip_description(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("source_ids", mode="before")
    @classmethod
    def _normalize_source_ids(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            cleaned = value.strip()
            return [cleaned] if cleaned else []
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            out: List[str] = []
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    out.append(text)
            return out
        raise TypeError("source_ids must be a list of strings")


class FrameworkAlignment(BaseModel):
    """Alignment slot against the local personal investment framework (#465)."""

    status: FrameworkAlignmentStatus = "not_configured"
    summary: str = ""
    framework_title: Optional[str] = None
    framework_version: Optional[int] = None
    framework_id: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("summary", "framework_title", "framework_id", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def _default_not_configured_summary(self) -> "FrameworkAlignment":
        if self.status == "not_configured" and not (self.summary or "").strip():
            self.summary = FRAMEWORK_NOT_CONFIGURED_SUMMARY_ZH
        return self


class ReportStrata(BaseModel):
    """Six fixed strata for evidence-oriented analysis presentation."""

    schema_version: Literal["report-strata-v1"] = REPORT_STRATA_SCHEMA_VERSION
    verified_facts: List[VerifiedFact] = Field(default_factory=list)
    missing_or_conflicts: List[DataGapOrConflict] = Field(default_factory=list)
    model_inference: List[str] = Field(default_factory=list)
    risks_counter_evidence: List[str] = Field(default_factory=list)
    framework_alignment: FrameworkAlignment = Field(
        default_factory=lambda: FrameworkAlignment(
            status="not_configured",
            summary=FRAMEWORK_NOT_CONFIGURED_SUMMARY_ZH,
        )
    )
    disclaimer: str = DEFAULT_DISCLAIMER_ZH

    model_config = ConfigDict(extra="forbid")

    @field_validator("model_inference", "risks_counter_evidence", mode="before")
    @classmethod
    def _normalize_string_lists(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            cleaned = value.strip()
            return [cleaned] if cleaned else []
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            out: List[str] = []
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    out.append(text)
            return out
        raise TypeError("expected a list of strings")

    @field_validator("disclaimer", mode="before")
    @classmethod
    def _normalize_disclaimer(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @model_validator(mode="after")
    def _ensure_disclaimer(self) -> "ReportStrata":
        # Language-aware defaults are applied by empty/ensure/normalize helpers.
        if not (self.disclaimer or "").strip():
            self.disclaimer = DEFAULT_DISCLAIMER_ZH
        return self

    def to_public_dict(self) -> Dict[str, Any]:
        """Serialize for templates, API, and fixtures."""
        return self.model_dump(mode="python")


def empty_report_strata(language: Optional[str] = None) -> ReportStrata:
    """Build default empty strata with mandatory disclaimer and framework slot."""
    lang = language or "zh"
    return ReportStrata(
        verified_facts=[],
        missing_or_conflicts=[],
        model_inference=[],
        risks_counter_evidence=[],
        framework_alignment=FrameworkAlignment(
            status="not_configured",
            summary=default_framework_not_configured_summary(lang),
        ),
        disclaimer=default_disclaimer(lang),
    )


def ensure_report_strata(
    payload: Optional[Any] = None,
    *,
    language: Optional[str] = None,
) -> ReportStrata:
    """Return normalized strata, filling defaults for new analysis artifacts."""
    normalized = normalize_report_strata(payload, language=language)
    if normalized is None:
        return empty_report_strata(language)
    return normalized


def normalize_report_strata(
    payload: Optional[Any],
    *,
    language: Optional[str] = None,
) -> Optional[ReportStrata]:
    """Parse optional strata. Missing / empty payload returns None (historical path).

    Partial payloads are accepted and filled so disclaimer and framework slot
    always exist when strata are present.
    """
    if payload is None:
        return None
    if isinstance(payload, ReportStrata):
        strata = payload
    elif isinstance(payload, dict):
        if not payload:
            return None
        try:
            strata = ReportStrata.model_validate(payload)
        except ValidationError as exc:
            strata = _coerce_partial_dict(payload, language=language)
            if strata is None:
                raise exc
    else:
        return None

    lang = language or "zh"
    original_disclaimer = None
    if isinstance(payload, dict):
        original_disclaimer = payload.get("disclaimer")
    elif isinstance(payload, ReportStrata):
        original_disclaimer = payload.disclaimer
    if original_disclaimer is None or not str(original_disclaimer).strip():
        strata.disclaimer = default_disclaimer(lang)
    elif not (strata.disclaimer or "").strip():
        strata.disclaimer = default_disclaimer(lang)
    if strata.framework_alignment is None:
        strata.framework_alignment = FrameworkAlignment(
            status="not_configured",
            summary=default_framework_not_configured_summary(lang),
        )
    elif strata.framework_alignment.status == "not_configured" and not (
        strata.framework_alignment.summary or ""
    ).strip():
        strata.framework_alignment.summary = default_framework_not_configured_summary(
            lang
        )
    return strata


def extract_report_strata_payload(
    source: Optional[Any],
) -> Optional[Any]:
    """Locate raw strata payload from dashboard, result dict, or schema dump.

    Preference order: ``dashboard.report_strata`` then top-level ``report_strata``.
    """
    if source is None:
        return None
    if isinstance(source, ReportStrata):
        return source
    if isinstance(source, dict):
        dashboard = source.get("dashboard")
        if isinstance(dashboard, dict) and dashboard.get("report_strata") is not None:
            return dashboard.get("report_strata")
        if source.get("report_strata") is not None:
            return source.get("report_strata")
        if source.get("schema_version") == REPORT_STRATA_SCHEMA_VERSION:
            return source
        return None
    dashboard = getattr(source, "dashboard", None)
    if isinstance(dashboard, dict) and dashboard.get("report_strata") is not None:
        return dashboard.get("report_strata")
    if dashboard is not None:
        dashboard_model = getattr(dashboard, "report_strata", None)
        if dashboard_model is not None:
            return dashboard_model
    nested = getattr(source, "report_strata", None)
    if nested is not None:
        return nested
    return None


def resolve_report_strata(
    source: Optional[Any],
    *,
    language: Optional[str] = None,
    ensure: bool = False,
) -> Optional[ReportStrata]:
    """Resolve and normalize strata from an analysis result / dashboard / dict."""
    payload = extract_report_strata_payload(source)
    if ensure:
        return ensure_report_strata(payload, language=language)
    return normalize_report_strata(payload, language=language)


def _coerce_partial_dict(
    payload: Dict[str, Any],
    *,
    language: Optional[str] = None,
) -> Optional[ReportStrata]:
    """Best-effort coerce for fixture and LLM drift cases used in unit tests."""
    lang = language or "zh"
    try:
        facts_raw = payload.get("verified_facts") or []
        gaps_raw = payload.get("missing_or_conflicts") or payload.get("gaps") or []
        inference_raw = payload.get("model_inference") or []
        risks_raw = (
            payload.get("risks_counter_evidence")
            or payload.get("risks")
            or []
        )
        framework_raw = payload.get("framework_alignment") or {}
        disclaimer = payload.get("disclaimer") or default_disclaimer(lang)

        facts: List[VerifiedFact] = []
        for item in facts_raw if isinstance(facts_raw, list) else []:
            if isinstance(item, str) and item.strip():
                facts.append(VerifiedFact(statement=item.strip()))
            elif isinstance(item, dict) and item.get("statement"):
                facts.append(
                    VerifiedFact(
                        statement=str(item["statement"]).strip(),
                        source_id=(
                            str(item["source_id"]).strip()
                            if item.get("source_id") not in (None, "")
                            else None
                        ),
                        as_of=(
                            str(item["as_of"]).strip()
                            if item.get("as_of") not in (None, "")
                            else None
                        ),
                    )
                )

        gaps: List[DataGapOrConflict] = []
        for item in gaps_raw if isinstance(gaps_raw, list) else []:
            if isinstance(item, str) and item.strip():
                gaps.append(
                    DataGapOrConflict(kind="missing", description=item.strip())
                )
            elif isinstance(item, dict) and item.get("description"):
                kind = item.get("kind") or "missing"
                if kind not in ("missing", "conflict"):
                    kind = "missing"
                gaps.append(
                    DataGapOrConflict(
                        kind=kind,  # type: ignore[arg-type]
                        description=str(item["description"]).strip(),
                        source_ids=item.get("source_ids") or [],
                    )
                )

        if isinstance(framework_raw, FrameworkAlignment):
            framework = framework_raw
        elif isinstance(framework_raw, dict) and framework_raw:
            framework = FrameworkAlignment.model_validate(
                {
                    "status": framework_raw.get("status") or "not_configured",
                    "summary": framework_raw.get("summary")
                    or default_framework_not_configured_summary(lang),
                    "framework_title": framework_raw.get("framework_title"),
                    "framework_version": framework_raw.get("framework_version"),
                    "framework_id": framework_raw.get("framework_id"),
                }
            )
        else:
            framework = FrameworkAlignment(
                status="not_configured",
                summary=default_framework_not_configured_summary(lang),
            )

        return ReportStrata(
            verified_facts=facts,
            missing_or_conflicts=gaps,
            model_inference=inference_raw if isinstance(inference_raw, list) else [],
            risks_counter_evidence=risks_raw if isinstance(risks_raw, list) else [],
            framework_alignment=framework,
            disclaimer=str(disclaimer).strip() or default_disclaimer(lang),
        )
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


ReportStrataPayload = Union[ReportStrata, Dict[str, Any]]
