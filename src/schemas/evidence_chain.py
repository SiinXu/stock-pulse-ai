# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Evidence-chain domain contract (Issues #986 / #127)."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


EVIDENCE_CHAIN_SCHEMA_VERSION: Literal["evidence-chain-v1"] = "evidence-chain-v1"
AUDIT_PACKAGE_SCHEMA_VERSION: Literal["audit-package-v1"] = "audit-package-v1"

EvidenceStatus = Literal["present", "missing", "partial"]
AsOfStatus = Literal["present", "missing"]
EvidenceSourceType = Literal[
    "data_source",
    "tool_call",
    "news",
    "indicator",
    "model",
    "pipeline_stage",
    "report_strata",
    "decision",
    "synthesis",
    "missing",
]
ConclusionStratum = Literal[
    "verified_fact",
    "model_inference",
    "risk",
    "synthesis",
    "decision",
    "gap",
]
ConclusionEvidenceStatus = Literal["linked", "missing", "partial"]
GapStatus = Literal["missing", "partial", "not_recorded"]


class _StrictEvidenceModel(BaseModel):
    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        str_strip_whitespace=True,
    )


class EvidenceItem(_StrictEvidenceModel):
    evidence_id: str = Field(min_length=1, max_length=96)
    source_type: EvidenceSourceType
    source_id: Optional[str] = Field(default=None, max_length=160)
    snippet: Optional[str] = Field(default=None, max_length=800)
    as_of: Optional[str] = Field(default=None, max_length=64)
    as_of_status: AsOfStatus = "missing"
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    link: Optional[str] = Field(default=None, max_length=400)
    status: EvidenceStatus = "present"
    missing_reason: Optional[str] = Field(default=None, max_length=240)


class ConclusionLink(_StrictEvidenceModel):
    conclusion_id: str = Field(min_length=1, max_length=96)
    stratum: ConclusionStratum
    statement: str = Field(min_length=1, max_length=1200)
    evidence_refs: List[str] = Field(default_factory=list, max_length=64)
    evidence_status: ConclusionEvidenceStatus = "missing"
    missing_note: Optional[str] = Field(default=None, max_length=240)
    as_of: Optional[str] = Field(default=None, max_length=64)
    as_of_status: AsOfStatus = "missing"
    source_id: Optional[str] = Field(default=None, max_length=160)


class ReasoningStep(_StrictEvidenceModel):
    step_id: str = Field(min_length=1, max_length=96)
    stage: str = Field(min_length=1, max_length=120)
    role: Optional[str] = Field(default=None, max_length=64)
    input_refs: List[str] = Field(default_factory=list, max_length=32)
    output_summary: Optional[str] = Field(default=None, max_length=500)
    model_ref: Optional[str] = Field(default=None, max_length=120)
    tool_call_ids: List[str] = Field(default_factory=list, max_length=32)
    status: EvidenceStatus = "present"
    missing_reason: Optional[str] = Field(default=None, max_length=240)


class EvidenceGap(_StrictEvidenceModel):
    path: str = Field(min_length=1, max_length=160)
    status: GapStatus
    reason: str = Field(min_length=1, max_length=240)
    related_conclusion_ids: List[str] = Field(default_factory=list, max_length=32)


class EvidenceChainRun(_StrictEvidenceModel):
    record_id: Optional[str] = Field(default=None, max_length=128)
    query_id: Optional[str] = Field(default=None, max_length=128)
    trace_id: Optional[str] = Field(default=None, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    lookup_key: Optional[str] = Field(default=None, max_length=128)
    lookup_mode: Optional[Literal["primary_key", "latest_by_query_id"]] = None
    stock_code: Optional[str] = Field(default=None, max_length=32)
    stock_name: Optional[str] = Field(default=None, max_length=120)
    market: Optional[str] = Field(default=None, max_length=32)
    model: Optional[str] = Field(default=None, max_length=120)
    started_at: Optional[str] = Field(default=None, max_length=64)
    exported_at: str = Field(min_length=1, max_length=64)
    config_fingerprint: str = Field(min_length=8, max_length=32)


class EvidenceChainCoverageSource(_StrictEvidenceModel):
    source: str = Field(min_length=1, max_length=96)
    supported: bool = True
    present: bool
    absent: bool
    reasons: List[str] = Field(default_factory=list, max_length=16)


class EvidenceChainCoverage(_StrictEvidenceModel):
    sources: List[EvidenceChainCoverageSource] = Field(default_factory=list, max_length=32)
    not_recorded: List[str] = Field(default_factory=list, max_length=16)
    notes: str = Field(default="", max_length=500)


class EvidenceChainPackage(_StrictEvidenceModel):
    schema_version: Literal["evidence-chain-v1"] = EVIDENCE_CHAIN_SCHEMA_VERSION
    run: EvidenceChainRun
    conclusions: List[ConclusionLink] = Field(default_factory=list, max_length=200)
    evidence_items: List[EvidenceItem] = Field(default_factory=list, max_length=400)
    reasoning_steps: List[ReasoningStep] = Field(default_factory=list, max_length=200)
    gaps: List[EvidenceGap] = Field(default_factory=list, max_length=200)
    coverage: EvidenceChainCoverage
    truncated: bool = False


class AuditPackageArtifact(_StrictEvidenceModel):
    name: str = Field(min_length=1, max_length=120)
    content_type: str = Field(min_length=1, max_length=80)
    status: Literal["present", "missing", "skipped"] = "present"
    missing_reason: Optional[str] = Field(default=None, max_length=240)
    byte_length: Optional[int] = Field(default=None, ge=0)
    sha256: Optional[str] = Field(default=None, max_length=64)


class AuditPackageManifest(_StrictEvidenceModel):
    schema_version: Literal["audit-package-v1"] = AUDIT_PACKAGE_SCHEMA_VERSION
    run: EvidenceChainRun
    artifacts: List[AuditPackageArtifact] = Field(default_factory=list, max_length=32)
    evidence_chain_schema: Literal["evidence-chain-v1"] = EVIDENCE_CHAIN_SCHEMA_VERSION
    reasoning_trace_schema: Optional[str] = Field(default=None, max_length=64)
    redacted: bool = True
    include_raw_artifacts: bool = False
    notes: str = Field(default="", max_length=500)
