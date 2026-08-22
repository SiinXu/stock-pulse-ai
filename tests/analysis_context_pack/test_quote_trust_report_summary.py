# -*- coding: utf-8 -*-
"""Issue #1129 DAG-2: render a bounded quote-trust summary in analysis reports.

End-entry coverage goes through DummyFetcher aggregation, then the pack
overview already consumed by reports. Tests do not call GET /trust or
mock away get_realtime_quote.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.analysis_context_pack.overview import render_analysis_context_pack_overview
from src.analysis_context_pack.quote_trust import (
    report_summary_from_overview,
    report_summary_from_pack,
)
from src.analyzer import AnalysisResult
from src.data_provider.base import DataFetcherManager
from src.data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote
from src.services.analysis_context_builder import (
    AnalysisContextBuilder,
    PipelineAnalysisArtifacts,
)
from src.services.report_renderer import render


SENSITIVE_MARKERS = ("circuit_key", "provider_attempts", "field_trust_v1")


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
        report_templates_dir="templates",
        report_language="en",
        report_show_llm_model=False,
        report_mode="research",
        research_presentation_profile="balanced",
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
        "metadata": {"query_id": "q-1129-dag2", "trigger_source": "api"},
    }
    data.update(overrides)
    return PipelineAnalysisArtifacts(**data)


def _result_with_overview(overview) -> AnalysisResult:
    result = AnalysisResult(
        code="600519",
        name="贵州茅台",
        trend_prediction="看多",
        sentiment_score=76,
        operation_advice="持有",
        decision_type="hold",
        confidence_level="中",
        analysis_summary="盘中偏强",
        dashboard={"core_conclusion": {"one_sentence": "持有观望"}},
        report_language="en",
    )
    result.analysis_context_pack_overview = overview
    return result


def _render_reports(result, mock_get_config):
    mock_get_config.return_value = _mock_config()
    markdown = render("markdown", [result], extra_context={"report_language": "en"})
    wechat = render("wechat", [result], extra_context={"report_language": "en"})
    brief = render("brief", [result], extra_context={"report_language": "en"})
    assert markdown is not None
    assert wechat is not None
    assert brief is not None
    return markdown, wechat, brief


def _assert_no_sensitive_leak(*texts: str) -> None:
    joined = "\n".join(texts)
    for marker in SENSITIVE_MARKERS:
        assert marker not in joined
    dumped = json.dumps(joined)
    assert "circuit_key" not in dumped
    assert "provider_attempts" not in dumped


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
@patch("src.services.report_renderer.get_config")
def test_conflicted_quote_report_shows_visible_degradation(
    mock_renderer_config, mock_get_config, validation_enabled
):
    mock_get_config.return_value = _mock_config()
    mock_renderer_config.return_value = _mock_config()
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
    overview = render_analysis_context_pack_overview(pack, report_language="en")
    summary = report_summary_from_pack(pack)
    overview_summary = report_summary_from_overview(overview)

    assert quote.price == 1688.0
    assert summary is not None
    assert summary["confidence"] != "high"
    assert "conflict" in summary["gap_codes"]
    assert summary["conflict_count"] >= 1
    assert overview_summary is not None
    assert "conflict" in overview_summary["gap_codes"]
    assert overview_summary["degraded"] is True

    markdown, wechat, brief = _render_reports(_result_with_overview(overview), mock_renderer_config)
    for text in (markdown, wechat, brief):
        assert "Quote trust" in text
        assert "conflict" in text
        assert "Analysis confidence**: `high`" not in text
        assert "Analysis confidence=high" not in text
        assert "Analysis confidence**: `low`" in text or "Analysis confidence=low" in text
    assert "conflict" in markdown
    _assert_no_sensitive_leak(markdown, wechat, brief)


@patch("src.config.get_config")
@patch("src.services.report_renderer.get_config")
def test_stale_quote_report_shows_visible_degradation(
    mock_renderer_config, mock_get_config, validation_enabled
):
    mock_get_config.return_value = _mock_config()
    mock_renderer_config.return_value = _mock_config()
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    primary = _make_quote(source=RealtimeSource.EFINANCE, provider_timestamp=stale_ts)
    quote = DataFetcherManager(
        fetchers=[_DummyFetcher("EfinanceFetcher", 0, result=primary)]
    ).get_realtime_quote("600519")
    pack = AnalysisContextBuilder.build(_artifacts(quote))
    overview = render_analysis_context_pack_overview(pack, report_language="en")
    summary = report_summary_from_pack(pack)

    assert summary is not None
    assert "stale" in summary["gap_codes"]
    assert summary["confidence"] != "high"

    markdown, wechat, brief = _render_reports(_result_with_overview(overview), mock_renderer_config)
    for text in (markdown, wechat, brief):
        assert "Quote trust" in text
        assert "stale" in text
        assert "Analysis confidence**: `high`" not in text
        assert "Analysis confidence=high" not in text
    _assert_no_sensitive_leak(markdown, wechat, brief)


@patch("src.config.get_config")
@patch("src.services.report_renderer.get_config")
def test_skipped_conflict_check_report_shows_visible_degradation(
    mock_renderer_config, mock_get_config, validation_disabled
):
    mock_get_config.return_value = _mock_config(validation_enabled=False)
    mock_renderer_config.return_value = _mock_config(validation_enabled=False)
    primary = _make_quote(source=RealtimeSource.EFINANCE)
    supplement = _make_quote(source=RealtimeSource.AKSHARE_EM, pe_ratio=25.5)
    quote = DataFetcherManager(
        fetchers=[
            _DummyFetcher("EfinanceFetcher", 0, result=primary),
            _DummyFetcher("AkshareFetcher", 1, result=supplement),
        ]
    ).get_realtime_quote("600519")
    pack = AnalysisContextBuilder.build(_artifacts(quote))
    overview = render_analysis_context_pack_overview(pack, report_language="en")
    summary = report_summary_from_pack(pack)

    assert summary is not None
    assert "conflict_check_skipped" in summary["gap_codes"]
    assert summary["confidence"] != "high"

    markdown, wechat, brief = _render_reports(_result_with_overview(overview), mock_renderer_config)
    for text in (markdown, wechat, brief):
        assert "Quote trust" in text
        assert "conflict_check_skipped" in text
        assert "Analysis confidence**: `high`" not in text
        assert "Analysis confidence=high" not in text
    _assert_no_sensitive_leak(markdown, wechat, brief)


@patch("src.services.report_renderer.get_config")
def test_missing_metadata_report_shows_visible_degradation(mock_renderer_config):
    mock_renderer_config.return_value = _mock_config()
    pack = AnalysisContextBuilder.build(_artifacts(_make_quote()))
    overview = render_analysis_context_pack_overview(pack, report_language="en")
    summary = report_summary_from_pack(pack)

    assert summary is not None
    assert "metadata_absent" in summary["gap_codes"]
    assert summary["confidence"] != "high"

    markdown, wechat, brief = _render_reports(_result_with_overview(overview), mock_renderer_config)
    for text in (markdown, wechat, brief):
        assert "Quote trust" in text
        assert "metadata_absent" in text
        assert "Analysis confidence**: `high`" not in text
        assert "Analysis confidence=high" not in text
    _assert_no_sensitive_leak(markdown, wechat, brief)


@patch("src.config.get_config")
@patch("src.services.report_renderer.get_config")
def test_fresh_non_conflict_report_does_not_false_degrade(
    mock_renderer_config, mock_get_config, validation_enabled
):
    mock_get_config.return_value = _mock_config()
    mock_renderer_config.return_value = _mock_config()
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
    overview = render_analysis_context_pack_overview(pack, report_language="en")
    summary = report_summary_from_pack(pack)
    overview_summary = report_summary_from_overview(overview)

    assert summary is not None
    assert summary["confidence"] == "high"
    assert summary["gap_codes"] == []
    assert summary["degraded"] is False
    assert overview_summary is not None
    assert overview_summary["confidence"] == "high"
    assert overview_summary["degraded"] is False

    markdown, wechat, brief = _render_reports(_result_with_overview(overview), mock_renderer_config)
    assert "Quote trust" in markdown
    assert "Quote trust" in wechat
    assert "Analysis confidence**: `high`" in markdown
    for token in ("conflict", "stale", "conflict_check_skipped", "metadata_absent"):
        assert token not in markdown
        assert token not in wechat
        assert token not in brief
    # Brief omits the fresh summary to keep the push budget; that is not degradation.
    assert "conflict" not in brief
    _assert_no_sensitive_leak(markdown, wechat, brief)


@patch("src.config.get_config")
@patch("src.services.report_renderer.get_config")
def test_missing_quote_report_shows_quote_unavailable_gap(
    mock_renderer_config, mock_get_config
):
    mock_get_config.return_value = _mock_config()
    mock_renderer_config.return_value = _mock_config()
    pack = AnalysisContextBuilder.build(_artifacts(None))
    overview = render_analysis_context_pack_overview(pack, report_language="en")
    summary = report_summary_from_pack(pack)
    overview_summary = report_summary_from_overview(overview)
    reconstructed = report_summary_from_overview(
        {
            "blocks": [
                {
                    "key": "quote",
                    "status": "missing",
                    "source": None,
                    "warnings": [],
                }
            ]
        }
    )

    assert pack.blocks["quote"].status.value == "missing"
    assert summary is not None
    assert summary["confidence"] != "high"
    assert "quote_unavailable" in summary["gap_codes"]
    assert overview_summary is not None
    assert "quote_unavailable" in overview_summary["gap_codes"]
    assert overview_summary["confidence"] == "low"
    assert overview_summary["degraded"] is True
    assert reconstructed is not None
    assert reconstructed["gap_codes"] == ["quote_unavailable"]
    assert reconstructed["confidence"] == "low"

    markdown, wechat, brief = _render_reports(
        _result_with_overview(overview), mock_renderer_config
    )
    for text in (markdown, wechat, brief):
        assert "Quote trust" in text
        assert "quote_unavailable" in text
        assert "Analysis confidence**: `high`" not in text
        assert "Analysis confidence=high" not in text
        assert "Gaps**: none" not in text
        assert "gaps=none" not in text.lower()
    _assert_no_sensitive_leak(markdown, wechat, brief)


@patch("src.services.report_renderer.get_config")
def test_missing_overview_does_not_invent_degradation(mock_renderer_config):
    mock_renderer_config.return_value = _mock_config()
    result = _result_with_overview(None)
    markdown, wechat, brief = _render_reports(result, mock_renderer_config)

    assert "Quote trust" not in markdown
    assert "Quote trust" not in wechat
    assert "Quote trust" not in brief
    for token in ("conflict", "stale", "conflict_check_skipped", "metadata_absent"):
        assert token not in markdown
        assert token not in wechat
        assert token not in brief
    _assert_no_sensitive_leak(markdown, wechat, brief)
