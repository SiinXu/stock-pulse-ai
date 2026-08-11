# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Analysis-context status coverage for SmartMoney money flow."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from data_provider.money_flow_types import MoneyFlowOutcome, MoneyFlowSnapshot, MoneyFlowStatus
from src.schemas.analysis_context_pack import ContextFieldStatus
from src.services.analysis_context_builder import AnalysisContextBuilder, PipelineAnalysisArtifacts
from src.core.stages.analysis_context import _AnalysisContextStageMixin


def _base_artifacts(**overrides):
    payload = dict(
        code="600519", stock_name="Kweichow Moutai", market="cn", phase=None,
        base_context={"date": "2026-08-08", "today": {}, "yesterday": {}},
        enhanced_context={}, realtime_quote=None, trend_result=None, chip_data=None,
        fundamental_context=None, news_context=None, news_result_count=None,
        metadata={"query_id": "q1"},
    )
    payload.update(overrides)
    return PipelineAnalysisArtifacts(**payload)


def _outcome(status=MoneyFlowStatus.PARTIAL, *, date="2026-08-08"):
    snapshot = MoneyFlowSnapshot(
        code="600519", date=date, source="akshare:stock_individual_fund_flow",
        main_net_inflow_ratio=1.5, bucket_definition="eastmoney_v1;amount_unit=unknown",
        as_of=datetime.now(timezone.utc).isoformat(), requested_days=5,
        observed_days=5, completeness="complete",
    )
    return MoneyFlowOutcome(
        status=status, code="600519", market="cn", requested_days=5,
        fetched_at=datetime.now(timezone.utc).isoformat(), snapshot=snapshot,
        provider_date=date, age_days=0 if status != MoneyFlowStatus.STALE else 1,
        warnings=["money_flow_amount_scale_is_not_authoritatively_calibrated"],
    )


def test_money_flow_block_omitted_when_feature_disabled_and_no_data():
    pack = AnalysisContextBuilder.build(_base_artifacts())
    assert "money_flow" not in pack.blocks


def test_money_flow_block_missing_when_enabled_but_empty():
    pack = AnalysisContextBuilder.build(
        _base_artifacts(metadata={"query_id": "q1", "smartmoney_enabled": True})
    )
    assert pack.blocks["money_flow"].status == ContextFieldStatus.MISSING


def test_money_flow_partial_status_and_calibration_are_preserved():
    pack = AnalysisContextBuilder.build(
        _base_artifacts(
            money_flow_data=_outcome(),
            metadata={"query_id": "q1", "smartmoney_enabled": True},
        )
    )
    block = pack.blocks["money_flow"]
    assert block.status == ContextFieldStatus.PARTIAL
    assert block.items["main_net_inflow_ratio"].value == 1.5
    assert block.metadata["unit"] == "unknown"
    assert block.metadata["amount_scale"] == "unknown"
    assert "money_flow: partial" in pack.data_quality.limitations


def test_stale_outcome_never_becomes_available():
    pack = AnalysisContextBuilder.build(
        _base_artifacts(
            money_flow_data=_outcome(MoneyFlowStatus.STALE, date="2026-08-07"),
            metadata={"smartmoney_enabled": True},
        )
    )
    assert pack.blocks["money_flow"].status == ContextFieldStatus.STALE
    assert "money_flow: stale" in pack.data_quality.limitations


def test_fetch_failure_has_explicit_reason_and_no_snapshot_items():
    outcome = MoneyFlowOutcome(
        status=MoneyFlowStatus.FETCH_FAILED, code="600519", market="cn",
        requested_days=5, fetched_at=datetime.now(timezone.utc).isoformat(),
        error_code="money_flow_all_providers_failed",
        source_chain=[{"provider": "akshare", "status": "fetch_failed"}],
    )
    pack = AnalysisContextBuilder.build(
        _base_artifacts(money_flow_data=outcome, metadata={"smartmoney_enabled": True})
    )
    block = pack.blocks["money_flow"]
    assert block.status == ContextFieldStatus.FETCH_FAILED
    assert block.items["money_flow"].missing_reason == "money_flow_all_providers_failed"
    assert block.source == "akshare"


def test_classic_analysis_context_injection_preserves_typed_outcome():
    class _Pipeline(_AnalysisContextStageMixin):
        config = SimpleNamespace(report_language="en")
        search_service = SimpleNamespace(news_window_days=3)
        fetcher_manager = SimpleNamespace(
            build_failed_fundamental_context=lambda code, reason: {
                "status": "failed", "code": code, "reason": reason
            }
        )

    enhanced = _Pipeline()._enhance_context(
        {"code": "600519", "today": {}, "yesterday": {}},
        None,
        None,
        None,
        money_flow_data=_outcome(),
    )

    assert enhanced["money_flow"]["status"] == "partial"
    assert enhanced["money_flow"]["snapshot"]["main_net_inflow_ratio"] == 1.5
