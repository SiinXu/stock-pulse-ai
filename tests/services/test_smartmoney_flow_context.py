# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Analysis-context injection coverage for SmartMoney money flow."""

from __future__ import annotations

from data_provider.money_flow_types import MoneyFlowSnapshot
from src.services.analysis_context_builder import (
    AnalysisContextBuilder,
    PipelineAnalysisArtifacts,
)
from src.schemas.analysis_context_pack import ContextFieldStatus


def _base_artifacts(**overrides):
    payload = dict(
        code="600519",
        stock_name="Kweichow Moutai",
        market="cn",
        phase=None,
        base_context={"date": "2026-08-08", "today": {}, "yesterday": {}},
        enhanced_context={},
        realtime_quote=None,
        trend_result=None,
        chip_data=None,
        fundamental_context=None,
        news_context=None,
        news_result_count=None,
        metadata={"query_id": "q1"},
    )
    payload.update(overrides)
    return PipelineAnalysisArtifacts(**payload)


def test_money_flow_block_omitted_when_feature_disabled_and_no_data():
    pack = AnalysisContextBuilder.build(_base_artifacts(metadata={"query_id": "q1"}))
    assert "money_flow" not in pack.blocks


def test_money_flow_block_missing_when_enabled_but_empty():
    pack = AnalysisContextBuilder.build(
        _base_artifacts(metadata={"query_id": "q1", "smartmoney_enabled": True})
    )
    block = pack.blocks["money_flow"]
    assert block.status == ContextFieldStatus.MISSING
    assert block.items["money_flow"].missing_reason == "money_flow_missing"


def test_money_flow_block_available_with_snapshot():
    snapshot = MoneyFlowSnapshot(
        code="600519",
        date="2026-08-08",
        source="akshare:stock_individual_fund_flow",
        main_net_inflow=1_000_000.0,
        bucket_definition="eastmoney_em_order_size_buckets_v1",
        unit="CNY",
    )
    pack = AnalysisContextBuilder.build(
        _base_artifacts(
            money_flow_data=snapshot,
            metadata={"query_id": "q1", "smartmoney_enabled": True},
        )
    )
    block = pack.blocks["money_flow"]
    assert block.status == ContextFieldStatus.AVAILABLE
    assert block.items["main_net_inflow"].value == 1_000_000.0
    assert block.metadata.get("bucket_definition")
    assert block.source == "akshare:stock_individual_fund_flow"
