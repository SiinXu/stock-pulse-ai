# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Governance projection for alternative data (Issues #139 / #1144).

Responsibilities:
- revalidate tool/plugin payloads fail-closed;
- project into AnalysisContextPack as a non-quality-weighted block;
- project into supporting-only evidence strata (never verified_fact / decision);
- map bad data to gaps without inventing values or polluting core quality.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from pydantic import ValidationError

from src.schemas.alternative_data import (
    ALT_DATA_DISCLAIMER,
    ALTERNATIVE_DATA_FORBIDDEN_CONCLUSION_STRATA,
    ALTERNATIVE_DATA_SCHEMA_VERSION,
    AlternativeDataConclusionLink,
    AlternativeDataEvidenceItem,
    AlternativeDataEvidenceProjection,
    AlternativeDataResult,
)
from src.schemas.analysis_context_pack import (
    AnalysisContextBlock,
    AnalysisContextItem,
    AnalysisContextPack,
    ContextFieldStatus,
)


_STATUS_MAP: dict[str, ContextFieldStatus] = {
    "available": ContextFieldStatus.AVAILABLE,
    "degraded": ContextFieldStatus.PARTIAL,
    "unavailable": ContextFieldStatus.MISSING,
}


def parse_alternative_data_result(payload: Any) -> AlternativeDataResult | None:
    """Return a validated result, or ``None`` when the payload is unusable."""

    if payload is None:
        return None
    if isinstance(payload, AlternativeDataResult):
        try:
            return AlternativeDataResult.model_validate(payload)
        except ValidationError:
            return None
    if not isinstance(payload, Mapping):
        return None
    try:
        return AlternativeDataResult.model_validate(dict(payload))
    except ValidationError:
        return None


def build_alternative_data_context_block(
    payload: Any,
) -> AnalysisContextBlock | None:
    """Project alt-data into an AnalysisContext block that never quality-weights core score.

    Returns ``None`` only when *no* payload was supplied (feature default-off).
    Invalid payloads become an explicit ``fetch_failed`` / gap block so consumers
    cannot treat silence as success.
    """

    if payload is None:
        return None

    result = parse_alternative_data_result(payload)
    if result is None:
        return AnalysisContextBlock(
            status=ContextFieldStatus.FETCH_FAILED,
            items={
                "payload": AnalysisContextItem(
                    status=ContextFieldStatus.FETCH_FAILED,
                    missing_reason="invalid_provider_output",
                    warnings=["alternative_data_rejected", "non_authoritative"],
                    metadata={
                        "authority": "non_authoritative",
                        "role": "supporting_only",
                        "quality_weighted": False,
                        "schema_version": ALTERNATIVE_DATA_SCHEMA_VERSION,
                    },
                )
            },
            warnings=["alternative_data_rejected", "non_authoritative"],
            metadata={
                "authority": "non_authoritative",
                "role": "supporting_only",
                "auxiliary": True,
                "quality_weighted": False,
                "pollutes_core_quality": False,
                "schema_version": ALTERNATIVE_DATA_SCHEMA_VERSION,
            },
        )

    status = _STATUS_MAP.get(result.status, ContextFieldStatus.MISSING)
    warnings = ["non_authoritative", "supporting_only"]
    if result.degraded:
        warnings.append(f"reason:{result.reason_code or 'degraded'}")
    metadata: Dict[str, Any] = {
        "authority": result.authority,
        "role": result.role,
        "category": result.category,
        "auxiliary": True,
        "quality_weighted": False,
        "pollutes_core_quality": False,
        "schema_version": result.schema_version,
        "reason_code": result.reason_code,
        "disclaimer": result.disclaimer,
        "gaps": list(result.gaps),
    }
    items: Dict[str, AnalysisContextItem] = {
        "summary": AnalysisContextItem(
            status=status,
            value=result.summary if result.status != "unavailable" else None,
            source="alternative_data",
            timestamp=result.as_of,
            missing_reason=result.reason_code if result.status != "available" else None,
            warnings=list(warnings),
            metadata={"authority": result.authority, "role": result.role},
        ),
        "confidence": AnalysisContextItem(
            status=status if result.confidence is not None else ContextFieldStatus.MISSING,
            value=result.confidence,
            source="alternative_data",
            timestamp=result.as_of,
            missing_reason=(
                None if result.confidence is not None else "confidence_not_reported"
            ),
            warnings=list(warnings),
            metadata={"basis": result.confidence_basis},
        ),
        "events": AnalysisContextItem(
            status=status if result.events else ContextFieldStatus.MISSING,
            value=[item.model_dump(mode="json") for item in result.events] or None,
            source="alternative_data",
            timestamp=result.as_of,
            missing_reason=None if result.events else (result.reason_code or "no_events"),
            warnings=list(warnings),
            metadata={"count": len(result.events)},
        ),
        "coverage": AnalysisContextItem(
            status=status if result.coverage else ContextFieldStatus.MISSING,
            value=[item.model_dump(mode="json") for item in result.coverage] or None,
            source="alternative_data",
            timestamp=result.as_of,
            missing_reason=None if result.coverage else (result.reason_code or "no_coverage"),
            warnings=list(warnings),
        ),
        "citations": AnalysisContextItem(
            status=ContextFieldStatus.AVAILABLE if result.citations else ContextFieldStatus.MISSING,
            value=[item.model_dump(mode="json") for item in result.citations] or None,
            source="alternative_data",
            timestamp=result.as_of,
            missing_reason=None if result.citations else "no_citations",
            warnings=list(warnings),
        ),
    }
    return AnalysisContextBlock(
        status=status,
        items=items,
        source="alternative_data",
        timestamp=result.as_of,
        warnings=warnings,
        metadata=metadata,
    )


def attach_alternative_data_block(
    pack: AnalysisContextPack,
    payload: Any,
) -> AnalysisContextPack:
    """Return a copy of *pack* with an ``alternative_data`` block when payload is present.

    Core ``data_quality`` scores are left unchanged: alt-data is never quality-weighted.
    """

    block = build_alternative_data_context_block(payload)
    if block is None:
        return pack
    blocks = dict(pack.blocks)
    blocks["alternative_data"] = block
    warnings = list(pack.data_quality.warnings)
    for warning in block.warnings:
        if warning not in warnings:
            warnings.append(warning)
    limitations = list(pack.data_quality.limitations)
    if block.status in {
        ContextFieldStatus.FETCH_FAILED,
        ContextFieldStatus.MISSING,
        ContextFieldStatus.PARTIAL,
    }:
        note = f"alternative_data: {block.status.value}"
        if note not in limitations and len(limitations) < 8:
            limitations.append(note)
    data_quality = pack.data_quality.model_copy(
        update={
            "warnings": warnings,
            "limitations": limitations,
            "metadata": {
                **dict(pack.data_quality.metadata or {}),
                "alternative_data_quality_weighted": False,
                "alternative_data_pollutes_core": False,
            },
        }
    )
    return pack.model_copy(update={"blocks": blocks, "data_quality": data_quality})


def project_alternative_data_evidence(
    payload: Any,
    *,
    stock_code: Optional[str] = None,
) -> AlternativeDataEvidenceProjection:
    """Project alt-data into supporting-only evidence; bad data becomes gaps.

    Never emits ``verified_fact`` or ``decision`` strata. ``pollutes_core_quality``
    is always ``False``.
    """

    result = parse_alternative_data_result(payload)
    if result is None:
        code = (stock_code or "unknown").strip() or "unknown"
        return AlternativeDataEvidenceProjection(
            category="corporate_events",
            stock_code=code,
            evidence_items=[
                AlternativeDataEvidenceItem(
                    evidence_id="alt-data-invalid",
                    source_type="data_source",
                    source_id="alternative_data",
                    snippet=None,
                    status="missing",
                    missing_reason="invalid_provider_output",
                )
            ],
            conclusions=[
                AlternativeDataConclusionLink(
                    conclusion_id="alt-data-gap",
                    stratum="gap",
                    statement=(
                        "Alternative data was rejected as invalid and cannot "
                        "support core conclusions."
                    ),
                    evidence_refs=[],
                    evidence_status="missing",
                )
            ],
            gaps=["invalid_provider_output"],
            pollutes_core_quality=False,
            disclaimer=ALT_DATA_DISCLAIMER,
        )

    evidence_items: List[AlternativeDataEvidenceItem] = []
    conclusions: List[AlternativeDataConclusionLink] = []
    gaps: List[str] = list(result.gaps)

    if result.status == "unavailable" or not result.events:
        if result.reason_code and result.reason_code not in gaps:
            gaps.append(result.reason_code)
        evidence_items.append(
            AlternativeDataEvidenceItem(
                evidence_id="alt-data-absent",
                source_type="data_source",
                source_id=result.category,
                snippet=result.summary,
                as_of=result.as_of,
                confidence=None,
                status="missing",
                missing_reason=result.reason_code or "no_data",
            )
        )
        conclusions.append(
            AlternativeDataConclusionLink(
                conclusion_id="alt-data-gap",
                stratum="gap",
                statement=result.summary,
                evidence_refs=[],
                evidence_status="missing",
            )
        )
    else:
        for index, event in enumerate(result.events):
            evidence_id = f"alt-event-{index + 1}"
            evidence_items.append(
                AlternativeDataEvidenceItem(
                    evidence_id=evidence_id,
                    source_type="data_source",
                    source_id=event.source_id,
                    snippet=f"{event.event_type}: {event.title}",
                    as_of=event.event_date,
                    confidence=event.confidence,
                    status="partial" if result.degraded else "present",
                )
            )
        conclusions.append(
            AlternativeDataConclusionLink(
                conclusion_id="alt-data-supporting",
                stratum="model_inference",
                statement=result.summary,
                evidence_refs=[item.evidence_id for item in evidence_items],
                evidence_status="partial" if result.degraded else "linked",
            )
        )
        if result.degraded and result.reason_code:
            conclusions.append(
                AlternativeDataConclusionLink(
                    conclusion_id="alt-data-partial-gap",
                    stratum="gap",
                    statement=f"Alternative data coverage is incomplete ({result.reason_code}).",
                    evidence_refs=[],
                    evidence_status="partial",
                )
            )
            if result.reason_code not in gaps:
                gaps.append(result.reason_code)

    for conclusion in conclusions:
        if conclusion.stratum in ALTERNATIVE_DATA_FORBIDDEN_CONCLUSION_STRATA:
            raise RuntimeError("alt-data evidence projection emitted a forbidden stratum")

    return AlternativeDataEvidenceProjection(
        category=result.category,
        stock_code=result.stock_code,
        evidence_items=evidence_items,
        conclusions=conclusions,
        gaps=gaps[:16],
        pollutes_core_quality=False,
        disclaimer=ALT_DATA_DISCLAIMER,
    )


def assert_does_not_pollute_core(
    projection: AlternativeDataEvidenceProjection,
    *,
    core_quality_before: Optional[int],
    core_quality_after: Optional[int],
) -> None:
    """Raise if governance mutation altered core quality scoring."""

    if projection.pollutes_core_quality:
        raise AssertionError("alternative data projection claims core pollution")
    for conclusion in projection.conclusions:
        if conclusion.stratum in ALTERNATIVE_DATA_FORBIDDEN_CONCLUSION_STRATA:
            raise AssertionError(
                f"alternative data conclusion uses forbidden stratum {conclusion.stratum}"
            )
    if (
        core_quality_before is not None
        and core_quality_after is not None
        and core_quality_before != core_quality_after
    ):
        raise AssertionError(
            "attaching alternative data must not change core overall_score "
            f"({core_quality_before} -> {core_quality_after})"
        )
