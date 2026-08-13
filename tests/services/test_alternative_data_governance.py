# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Governance: analysis-context attach + evidence stratification for alt-data."""

from __future__ import annotations

from src.schemas.alternative_data import (
    ALT_DATA_DISCLAIMER,
    ALTERNATIVE_DATA_FORBIDDEN_CONCLUSION_STRATA,
    AlternativeDataCitation,
    AlternativeDataCoverage,
    AlternativeDataResult,
    CorporateEventItem,
)
from src.schemas.analysis_context_pack import AnalysisSubject, ContextFieldStatus
from src.services.alternative_data_governance import (
    assert_does_not_pollute_core,
    attach_alternative_data_block,
    build_alternative_data_context_block,
    project_alternative_data_evidence,
)
from src.services.analysis_context_builder import (
    AnalysisContextBuilder,
    PipelineAnalysisArtifacts,
)


def _available_result() -> dict:
    return AlternativeDataResult(
        status="available",
        degraded=False,
        reason_code=None,
        category="corporate_events",
        stock_code="600519",
        language="zh",
        as_of="2026-08-01T00:00:00Z",
        summary="参考窗口内有 1 条非权威公司事件。",
        confidence=0.55,
        confidence_basis="fixture",
        events=(
            CorporateEventItem(
                event_id="e1",
                event_type="dividend",
                title="示例分红",
                event_date="2026-08-10",
                impact_hint="positive",
                source_id="src_a",
                confidence=0.55,
            ),
        ),
        coverage=(
            AlternativeDataCoverage(
                source_id="src_a",
                status="available",
                as_of="2026-08-01T00:00:00Z",
            ),
        ),
        citations=(
            AlternativeDataCitation(
                source_id="src_a",
                reference_id="e1",
            ),
        ),
        gaps=(),
        authority="non_authoritative",
        role="supporting_only",
        disclaimer=ALT_DATA_DISCLAIMER,
    ).model_dump(mode="json")


def _minimal_artifacts(**overrides):
    base = dict(
        code="600519",
        stock_name="Kweichow Moutai",
        market="cn",
        phase=None,
        base_context={
            "date": "2026-08-01",
            "today": {"close": 1600.0},
            "yesterday": {"close": 1590.0},
            "data_missing": False,
        },
        enhanced_context={},
        realtime_quote={
            "price": 1600.0,
            "source": "fixture",
            "change_pct": 0.6,
        },
        trend_result=None,
        chip_data=None,
        fundamental_context=None,
        news_context=None,
        news_result_count=0,
        metadata={},
    )
    base.update(overrides)
    return PipelineAnalysisArtifacts(**base)


def test_context_block_is_non_authoritative_and_unweighted() -> None:
    block = build_alternative_data_context_block(_available_result())
    assert block is not None
    assert block.metadata["authority"] == "non_authoritative"
    assert block.metadata["quality_weighted"] is False
    assert block.metadata["pollutes_core_quality"] is False
    assert "non_authoritative" in block.warnings


def test_invalid_payload_becomes_gap_block_not_silent_success() -> None:
    block = build_alternative_data_context_block({"status": "available", "junk": True})
    assert block is not None
    assert block.status == ContextFieldStatus.FETCH_FAILED
    assert block.items["payload"].missing_reason == "invalid_provider_output"


def test_attach_does_not_change_core_overall_score() -> None:
    pack = AnalysisContextBuilder.build(_minimal_artifacts())
    before = pack.data_quality.overall_score
    assert "alternative_data" not in pack.blocks

    attached = attach_alternative_data_block(pack, _available_result())
    after = attached.data_quality.overall_score
    assert before == after
    assert "alternative_data" in attached.blocks
    assert attached.blocks["alternative_data"].metadata["quality_weighted"] is False
    assert attached.data_quality.metadata["alternative_data_pollutes_core"] is False

    projection = project_alternative_data_evidence(_available_result())
    assert_does_not_pollute_core(
        projection,
        core_quality_before=before,
        core_quality_after=after,
    )


def test_builder_optional_field_end_to_end() -> None:
    pack = AnalysisContextBuilder.build(
        _minimal_artifacts(alternative_data=_available_result())
    )
    assert pack.subject == AnalysisSubject(
        code="600519",
        stock_name="Kweichow Moutai",
        market="cn",
    )
    assert "alternative_data" in pack.blocks
    assert pack.blocks["alternative_data"].status == ContextFieldStatus.AVAILABLE


def test_builder_default_omits_alt_data_block() -> None:
    pack = AnalysisContextBuilder.build(_minimal_artifacts())
    assert "alternative_data" not in pack.blocks


def test_evidence_projection_forbids_core_strata() -> None:
    projection = project_alternative_data_evidence(_available_result())
    assert projection.pollutes_core_quality is False
    assert projection.authority == "non_authoritative"
    strata = {item.stratum for item in projection.conclusions}
    assert strata.isdisjoint(ALTERNATIVE_DATA_FORBIDDEN_CONCLUSION_STRATA)
    assert "model_inference" in strata
    assert projection.evidence_items
    assert all(item.authority == "non_authoritative" for item in projection.evidence_items)


def test_bad_data_projects_to_gap_without_events() -> None:
    projection = project_alternative_data_evidence({"broken": True}, stock_code="AAPL")
    assert projection.gaps == ["invalid_provider_output"]
    assert projection.conclusions[0].stratum == "gap"
    assert projection.evidence_items[0].status == "missing"
    assert projection.pollutes_core_quality is False
