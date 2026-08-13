# -*- coding: utf-8 -*-
"""Internal AnalysisContextPack schema for Issue #1389 P1."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from src.utils.sanitize import redact_sensitive_mapping


PACK_VERSION: Literal["1.0"] = "1.0"
_PACK_VERSION_ADAPTER = TypeAdapter(Literal["1.0"])


def new_analysis_context_snapshot_id() -> str:
    """Return a new opaque snapshot id for one sealed analysis-context instance."""
    return uuid.uuid4().hex


class _AnalysisContextModel(BaseModel):
    """Base model for the internal P1 contract."""

    model_config = ConfigDict(validate_assignment=True)


def _validate_iso8601_timestamp(value: Optional[str]) -> Optional[str]:
    if value is None:
        return value
    if "T" not in value:
        raise ValueError("timestamp must be an ISO 8601 datetime string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp must be an ISO 8601 datetime string") from exc
    return value


class ContextFieldStatus(str, Enum):
    """Field or block quality state for the first AnalysisContextPack contract."""

    AVAILABLE = "available"
    MISSING = "missing"
    NOT_SUPPORTED = "not_supported"
    FALLBACK = "fallback"
    STALE = "stale"
    ESTIMATED = "estimated"
    PARTIAL = "partial"
    FETCH_FAILED = "fetch_failed"


class AnalysisSubject(_AnalysisContextModel):
    """Minimal stock identity slot for P1."""

    code: str
    stock_name: Optional[str] = None
    market: Optional[str] = None


class AnalysisContextItem(_AnalysisContextModel):
    """Field-level input context item."""

    status: ContextFieldStatus
    value: Optional[Any] = None
    source: Optional[str] = None
    timestamp: Optional[str] = None
    fallback_from: Optional[str] = None
    missing_reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def _timestamp_must_be_iso8601(cls, value: Optional[str]) -> Optional[str]:
        return _validate_iso8601_timestamp(value)


class AnalysisContextBlock(_AnalysisContextModel):
    """Block-level grouping for related context items."""

    status: ContextFieldStatus
    items: Dict[str, AnalysisContextItem] = Field(default_factory=dict)
    source: Optional[str] = None
    timestamp: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def _timestamp_must_be_iso8601(cls, value: Optional[str]) -> Optional[str]:
        return _validate_iso8601_timestamp(value)


class DataQuality(_AnalysisContextModel):
    """Low-sensitivity data quality summary for an AnalysisContextPack."""

    overall_score: Optional[int] = Field(None, ge=0, le=100)
    level: Optional[Literal["good", "usable", "limited", "poor"]] = None
    block_scores: Dict[str, int] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AnalysisContextPack(_AnalysisContextModel):
    """Versioned internal analysis input envelope.

    ``pack_version`` is the schema contract version (currently fixed at
    ``1.0``). Per-run identity uses ``snapshot_id`` + ``snapshot_revision``
    so multi-agent stages can share one sealed data snapshot without
    confusing the schema contract with a run-local revision (Issue #182).
    """

    subject: AnalysisSubject
    pack_version: Literal["1.0"] = PACK_VERSION
    snapshot_id: str = Field(default_factory=new_analysis_context_snapshot_id)
    snapshot_revision: int = Field(default=1, ge=1)
    as_of: Optional[str] = None
    phase: Optional[Dict[str, Any]] = None
    blocks: Dict[str, AnalysisContextBlock] = Field(default_factory=dict)
    data_quality: DataQuality = Field(default_factory=DataQuality)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_iso8601(cls, value: Optional[str]) -> Optional[str]:
        return _validate_iso8601_timestamp(value)

    @field_validator("snapshot_id")
    @classmethod
    def _snapshot_id_must_be_non_empty(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("snapshot_id must be a non-empty string")
        if len(text) > 128:
            raise ValueError("snapshot_id must be at most 128 characters")
        return text

    def to_safe_dict(self) -> Dict[str, Any]:
        """Return a JSON-safe dict with sensitive mapping values redacted."""
        return redact_sensitive_mapping(self.model_dump(mode="json"))

    def model_copy(
        self,
        *,
        update: Optional[Mapping[str, Any]] = None,
        deep: bool = False,
    ) -> "AnalysisContextPack":
        """Copy the pack without bypassing the fixed P1 contract fields."""
        if update is not None and "pack_version" in update:
            _PACK_VERSION_ADAPTER.validate_python(update["pack_version"])
        return super().model_copy(update=update, deep=deep)

    def audit_identity(self) -> Dict[str, Any]:
        """Return low-sensitivity snapshot identity for diagnostics/audit."""
        created = self.created_at
        if created.tzinfo is not None:
            created_text = created.isoformat().replace("+00:00", "Z")
        else:
            created_text = created.isoformat()
        return {
            "pack_version": self.pack_version,
            "snapshot_id": self.snapshot_id,
            "snapshot_revision": self.snapshot_revision,
            "as_of": self.as_of,
            "created_at": created_text,
            "content_digest": (self.metadata or {}).get("content_digest"),
        }
