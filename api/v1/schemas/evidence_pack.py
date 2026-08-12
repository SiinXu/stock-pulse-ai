# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Public API contracts for evidence-chain and audit-package export."""
from __future__ import annotations
from typing import Any, Dict, List, Literal
from pydantic import BaseModel, ConfigDict, Field

class _StrictModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", str_strip_whitespace=True)

class EvidenceChainExportResponse(_StrictModel):
    schema_version: Literal["evidence-chain-v1"]
    run: Dict[str, Any]
    conclusions: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_items: List[Dict[str, Any]] = Field(default_factory=list)
    reasoning_steps: List[Dict[str, Any]] = Field(default_factory=list)
    gaps: List[Dict[str, Any]] = Field(default_factory=list)
    coverage: Dict[str, Any]
    truncated: bool = False

class AuditPackageJsonEnvelope(_StrictModel):
    schema_version: Literal["audit-package-v1"]
    manifest: Dict[str, Any]
    evidence_chain: Dict[str, Any]
    truncated: bool = False
