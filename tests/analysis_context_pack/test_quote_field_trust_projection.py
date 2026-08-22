# -*- coding: utf-8 -*-
"""Issue #1129: project field-trust analysis_input into analysis packs.

End-entry coverage goes through DataFetcherManager DummyFetcher aggregation,
then AnalysisContextBuilder / prompt / snapshot / phase-decision guardrail.
Tests do not mock away get_realtime_quote.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

try:
    json_repair_available = importlib.util.find_spec("json_repair") is not None
except ValueError:
    json_repair_available = "json_repair" in sys.modules

if not json_repair_available and "json_repair" not in sys.modules:
    sys.modules["json_repair"] = MagicMock()

from src.analysis_context_pack.overview import render_analysis_context_pack_overview
from src.analysis_context_pack.prompt import format_analysis_context_pack_prompt_section
from src.analysis_context_pack.snapshot import compute_pack_content_digest
from src.analyzer import AnalysisResult
from src.data_provider.base import DataFetcherManager
from src.data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote
from src.phase_decision_guardrail import apply_phase_decision_guardrails
from src.schemas.analysis_context_pack import ContextFieldStatus
from src.services.analysis_context_builder import (
    AnalysisContextBuilder,
    PipelineAnalysisArtifacts,
)


class _DummyFetcher:
    def __init__(self, name: str, priority: int, result=None, error: Exception | None = None):
        self.name = name
        self.priority = priority
        self._result = result
        self._error = error

    def get_realtime_quote(self, *args, **kwargs):
        if self._error is not None:
            raise self._error
        return self._result


def _make_quote(
    code: str = "600519",
    source: RealtimeSource = RealtimeSource.EFINANCE,
    **overrides,
) -> UnifiedRealtimeQuote:
    return UnifiedRealtimeQuote(
        code=code,
        name="贵州茅台",
        source=source,
        price=1688.0,
        change_pct=1.2,
        **overrides,
    )


def _mock_config(*, ttl: int = 600, validation_enabled: bool = True):
    return SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,akshare_em",
        realtime_cache_ttl=ttl,
        data_validation_enabled=validation_enabled,
        data_validation_strict=False,
    )


def _artifacts(quote, **overrides) -> PipelineAnalysisArtifacts:
    data = {
        "code": "600519",
        "stock_name": "贵州茅台",
        "market": "cn",
        "phase": {"market": "cn", "phase": "intraday"},
        "base_context": {
            "code": "600519",
            "stock_name": "贵州茅台",
            "date": "2026-05-24",
            "today": {"date": "2026-05-24", "close": 1688.0},
            "yesterday": {"date": "2026-05-23", "close": 1660.0},
        },
        "enhanced_context": {"today": {"date": "2026-05-24", "close": 1688.0}},
        "realtime_quote": quote,
        "trend_result": {
            "trend_status": "多头排列",
            "ma5": 1600.0,
            "ma10": 1580.0,
            "rsi_6": 66.0,
        },
        "chip_data": {
            "code": "600519",
            "date": "2026-05-24",
            "source": "akshare",
            "profit_ratio": 0.72,
            "avg_cost": 1500.0,
        },
        "fundamental_context": {
            "status": "ok",
            "coverage": {"valuation": "ok"},
            "source_chain": [{"provider": "fundamental_pipeline", "result": "ok"}],
        },
        "news_context": "公司公告与行业新闻摘要",
        "news_result_count": 3,
        "metadata": {"query_id": "q-1129", "trigger_source": "api"},
    }
    data.update(overrides)
    return PipelineAnalysisArtifacts(**data)


def _frozen_digest(pack) -> str:
    payload = pack.model_dump(mode="json")
    payload["as_of"] = "2026-05-31T10:00:00+00:00"
    payload["created_at"] = "2026-05-31T10:00:00+00:00"
    return compute_pack_content_digest(payload)


def _high_confidence_result() -> AnalysisResult:
    return AnalysisResult(
        code="600519",
        name="贵州茅台",
        trend_prediction="看多",
        sentiment_score=76,
        operation_advice="立即买入",
        decision_type="buy",
        confidence_level="高",
        analysis_summary="盘中偏强",
        dashboard={
            "core_conclusion": {"one_sentence": "立即买入"},
            "phase_decision": {
                "action_window": "盘中跟踪",
                "immediate_action": "立即买入",
                "watch_conditions": ["放量突破"],
                "next_check_time": "14:30",
                "confidence_reason": "趋势偏强",
                "data_limitations": [],
            },
        },
    )


@pytest.fixture
def validation_enabled(monkeypatch):
    from src.application_services import reset_application_services
    from src.config import Config

    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "true")
    monkeypatch.setenv("DATA_VALIDATION_STRICT", "false")
    reset_application_services()
    Config.reset_instance()
    yield
    reset_application_services()
    Config.reset_instance()


@pytest.fixture
def validation_disabled(monkeypatch):
    from src.application_services import reset_application_services
    from src.config import Config

    monkeypatch.setenv("DATA_VALIDATION_ENABLED", "false")
    reset_application_services()
    Config.reset_instance()
    yield
    reset_application_services()
    Config.reset_instance()


@patch("src.config.get_config")
def test_fresh_conflict_free_quote_stays_high_eligible(mock_get_config, validation_enabled):
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    primary = _make_quote(
        source=RealtimeSource.EFINANCE,
        provider_timestamp=fresh_ts,
        volume_ratio=1.1,
        turnover_rate=0.5,
        pe_ratio=20.0,
        pb_ratio=5.0,
        total_mv=1.0,
        circ_mv=1.0,
        amplitude=1.0,
        iopv=1.0,
        nav=1.0,
    )
    quote = DataFetcherManager(
        fetchers=[_DummyFetcher("EfinanceFetcher", 0, result=primary)]
    ).get_realtime_quote("600519")
    pack = AnalysisContextBuilder.build(_artifacts(quote))
    block = pack.blocks["quote"]
    prompt = format_analysis_context_pack_prompt_section(pack, report_language="en")

    assert quote is primary
    assert quote.price == 1688.0
    assert block.status == ContextFieldStatus.AVAILABLE
    assert block.metadata["analysis_input"]["confidence"] == "high"
    assert block.metadata["analysis_input"]["gap_codes"] == []
    assert "field_trust" not in block.items
    assert "quote_trust_" not in "".join(block.warnings)
    assert "confidence_level must not be High" not in prompt
    dumped = json.dumps(pack.to_safe_dict(), ensure_ascii=False)
    assert "circuit_key" not in dumped
    assert "provider_attempts" not in dumped


@patch("src.config.get_config")
def test_stale_primary_quote_bans_high_confidence(mock_get_config, validation_enabled):
    mock_get_config.return_value = _mock_config()
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    primary = _make_quote(source=RealtimeSource.EFINANCE, provider_timestamp=stale_ts)
    quote = DataFetcherManager(
        fetchers=[_DummyFetcher("EfinanceFetcher", 0, result=primary)]
    ).get_realtime_quote("600519")
    pack = AnalysisContextBuilder.build(_artifacts(quote))
    block = pack.blocks["quote"]
    prompt = format_analysis_context_pack_prompt_section(pack, report_language="en")

    assert quote is primary
    assert block.status == ContextFieldStatus.STALE
    assert "quote_stale" in block.warnings
    assert "quote_trust_stale" in block.warnings
    assert "stale" in block.metadata["analysis_input"]["gap_codes"]
    assert block.metadata["analysis_input"]["confidence"] != "high"
    assert "confidence_level must not be High" in prompt
    assert "field_trust" not in block.items


@patch("src.config.get_config")
def test_fresh_conflicted_quote_cannot_remain_high_eligible(
    mock_get_config, validation_enabled
):
    mock_get_config.return_value = _mock_config()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    primary = _make_quote(
        source=RealtimeSource.EFINANCE,
        provider_timestamp=fresh_ts,
        fetched_at=fresh_ts,
        is_stale=False,
        stale_seconds=0,
    )
    conflicting = _make_quote(
        source=RealtimeSource.AKSHARE_EM,
        provider_timestamp=fresh_ts,
        volume_ratio=1.5,
    )
    conflicting.price = 2100.0
    quote = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=primary),
            _DummyFetcher("AkshareFetcher", 1, result=conflicting),
        ]
    ).get_realtime_quote("600519")
    pack = AnalysisContextBuilder.build(_artifacts(quote))
    block = pack.blocks["quote"]
    en_prompt = format_analysis_context_pack_prompt_section(pack, report_language="en")
    zh_prompt = format_analysis_context_pack_prompt_section(pack, report_language="zh")
    overview = render_analysis_context_pack_overview(pack, report_language="zh")
    result = _high_confidence_result()
    adjustments = apply_phase_decision_guardrails(
        result,
        market_phase_summary={
            "phase": "intraday",
            "market": "cn",
            "market_local_time": "2026-06-02T10:30:00+08:00",
            "is_trading_day": True,
            "is_market_open_now": True,
            "is_partial_bar": True,
        },
        analysis_context_pack_overview=overview,
        report_language="zh",
    )

    assert quote is primary
    assert quote.price == 1688.0
    assert block.items["price"].value == 1688.0
    assert block.status == ContextFieldStatus.PARTIAL
    assert "quote_trust_conflict" in block.warnings
    assert "conflict" in block.metadata["analysis_input"]["gap_codes"]
    assert block.metadata["analysis_input"]["confidence"] == "low"
    assert block.metadata["analysis_input"]["conflict_count"] >= 1
    assert "field_trust" not in block.items
    assert "confidence_level must not be High" in en_prompt
    assert "confidence_level 不得为高" in zh_prompt
    assert "quote_trust_conflict" in en_prompt
    dumped = json.dumps(pack.to_safe_dict(), ensure_ascii=False)
    assert "circuit_key" not in dumped
    assert "provider_attempts" not in dumped
    assert "confidence_capped_core_data_degraded" in adjustments
    assert result.confidence_level == "中"

    second = AnalysisContextBuilder.build(_artifacts(quote))
    assert _frozen_digest(pack) == _frozen_digest(second)
    assert format_analysis_context_pack_prompt_section(pack, report_language="en") == en_prompt


@patch("src.config.get_config")
def test_skipped_conflict_check_does_not_read_as_agreement(
    mock_get_config, validation_disabled
):
    mock_get_config.return_value = _mock_config(validation_enabled=False)
    primary = _make_quote(source=RealtimeSource.EFINANCE)
    supplement = _make_quote(source=RealtimeSource.AKSHARE_EM, pe_ratio=25.5)
    quote = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=primary),
            _DummyFetcher("AkshareFetcher", 1, result=supplement),
        ]
    ).get_realtime_quote("600519")
    pack = AnalysisContextBuilder.build(_artifacts(quote))
    block = pack.blocks["quote"]
    prompt = format_analysis_context_pack_prompt_section(pack, report_language="en")

    assert block.status != ContextFieldStatus.AVAILABLE
    assert block.metadata["analysis_input"]["confidence"] != "high"
    assert "conflict_check_skipped" in block.metadata["analysis_input"]["gap_codes"]
    assert "quote_trust_conflict_check_skipped" in block.warnings
    assert "confidence_level must not be High" in prompt
    assert quote.price == 1688.0


def test_missing_and_legacy_payloads_fail_closed_without_high_eligibility():
    missing_pack = AnalysisContextBuilder.build(_artifacts(_make_quote()))
    missing = missing_pack.blocks["quote"]
    missing_prompt = format_analysis_context_pack_prompt_section(
        missing_pack, report_language="en"
    )

    assert missing.status == ContextFieldStatus.PARTIAL
    assert "metadata_absent" in missing.metadata["analysis_input"]["gap_codes"]
    assert "quote_trust_metadata_absent" in missing.warnings
    assert "confidence_level must not be High" in missing_prompt
    assert "field_trust" not in missing.items

    legacy_quote = _make_quote(
        field_trust={
            "schema_version": "field_trust_v1",
            "fields": {
                "price": {
                    "source": "efinance",
                    "origin": "primary",
                    "staleness": "fresh",
                    "conflict": True,
                }
            },
            "conflicts": [
                {
                    "field": "price",
                    "values": [
                        {"provider": "efinance", "value": 1688.0},
                        {"provider": "akshare_em", "value": 2100.0},
                    ],
                }
            ],
        }
    )
    legacy_pack = AnalysisContextBuilder.build(_artifacts(legacy_quote))
    legacy = legacy_pack.blocks["quote"]
    assert legacy.status == ContextFieldStatus.PARTIAL
    assert "conflict" in legacy.metadata["analysis_input"]["gap_codes"]
    assert "quote_trust_conflict" in legacy.warnings
    assert "field_trust" not in legacy.items
    assert _frozen_digest(legacy_pack) == _frozen_digest(
        AnalysisContextBuilder.build(_artifacts(legacy_quote))
    )
    assert _frozen_digest(missing_pack) != _frozen_digest(legacy_pack)
