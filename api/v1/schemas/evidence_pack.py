# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Public API contracts for evidence-chain and audit-package export."""
from __future__ import annotations

import math
from typing import Any, Dict, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from src.schemas.evidence_chain import AuditPackageManifest, EvidenceChainPackage

class _StrictModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid", str_strip_whitespace=True)


class EvidenceChainExportResponse(EvidenceChainPackage):
    """Public API name for the strict evidence-chain domain package."""


class AuditPackageJsonEnvelope(_StrictModel):
    schema_version: Literal["audit-package-v1"]
    manifest: AuditPackageManifest
    evidence_chain: EvidenceChainPackage
    artifacts: Dict[str, Any]
    truncated: bool = False

    @field_validator("artifacts")
    @classmethod
    def reject_non_finite_artifact_numbers(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        def check(item: Any) -> None:
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("artifact values must not contain NaN or infinity")
            if isinstance(item, dict):
                for nested in item.values():
                    check(nested)
            elif isinstance(item, (list, tuple)):
                for nested in item:
                    check(nested)

        check(value)
        return value
