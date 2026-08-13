# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract-focused tests for Pipeline stage IO types (Issues #1072, #1083)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.core.contracts import (
    AnalyzeStageInput,
    AnalyzeStageOutput,
    FetchDailyDataOutput,
    FetchMarketInputsOutput,
    FetchStageInput,
    RenderStageInput,
    RenderStageOutput,
    RunContext,
    StageDegradedError,
    StageFailedError,
    StageSkippedError,
    build_run_context,
    stage_result_from_error,
)
from src.core.pipeline_stage_results import (
    PipelineStageName,
    PipelineStageRunner,
    PipelineStageStatus,
)
from src.enums import ReportType
from src.schemas.analysis_context_pack import AnalysisSubject


def test_run_context_required_fields_and_subject_alignment() -> None:
    """RunContext exposes the AnalysisSubject identity projection."""
    ctx = build_run_context(
        query_id="q-1",
        trace_id="t-1",
        stock_code="600519",
        report_type=ReportType.SIMPLE,
        stock_name="Kweichow Moutai",
        market="CN",
        query_source="web",
    )
    assert isinstance(ctx, RunContext)
    assert ctx.query_id == "q-1"
    assert ctx.trace_id == "t-1"
    assert ctx.stock_code == "600519"
    assert ctx.report_type == ReportType.SIMPLE.value
    assert isinstance(ctx.subject, AnalysisSubject)
    assert ctx.subject.code == "600519"
    assert ctx.subject.stock_name == "Kweichow Moutai"
    assert ctx.subject.market == "CN"
    summary = ctx.to_input_summary()
    assert summary["stock_code"] == "600519"
    assert summary["query_id"] == "q-1"
    assert summary["report_type"] == "simple"


def test_run_context_rejects_blank_identity() -> None:
    with pytest.raises(ValueError):
        RunContext(query_id="", trace_id="t", stock_code="600519", report_type="simple")
    with pytest.raises(ValueError):
        RunContext(query_id="q", trace_id="t", stock_code="", report_type="simple")


def test_fetch_daily_data_output_preserves_tuple_behavior() -> None:
    """Historical process_single_stock consumers unpack and index the value."""
    output = FetchDailyDataOutput(data_ready=True, error=None)
    assert output == (True, None)
    assert output[0] is True
    success, error = output
    assert success is True
    assert error is None
    assert output.to_output_summary() == {"data_ready": True}

    degraded = FetchDailyDataOutput(data_ready=False, error="provider_timeout")
    assert degraded == (False, "provider_timeout")
    assert bool(degraded and degraded[0]) is False


def test_fetch_market_inputs_output_mapping_compatibility() -> None:
    quote = SimpleNamespace(price=100.0)
    output = FetchMarketInputsOutput(
        realtime_quote=quote,
        chip_data=None,
        fundamental_context={"status": "partial"},
        trend_result=object(),
        daily_market_context=None,
    )
    assert output["realtime_quote"] is quote
    assert "chip_data" in output
    assert output.get("missing", "default") == "default"
    legacy = output.as_legacy_value()
    assert legacy["fundamental_context"]["status"] == "partial"
    assert output == legacy
    summary = output.to_output_summary(
        fundamental_status="partial",
        daily_market_context_enabled=True,
    )
    assert summary["realtime_available"] is True
    assert summary["chip_available"] is False
    assert summary["fundamental_status"] == "partial"
    assert summary["daily_market_context_enabled"] is True


def test_fetch_and_analyze_and_render_input_summaries() -> None:
    fetch_in = FetchStageInput(
        stock_code="AAPL",
        operation="assemble_market_inputs",
        realtime_enabled=True,
        chip_enabled=False,
        daily_market_context_enabled=True,
    )
    assert fetch_in.to_input_summary() == {
        "stock_code": "AAPL",
        "operation": "assemble_market_inputs",
        "realtime_enabled": True,
        "chip_enabled": False,
        "daily_market_context_enabled": True,
    }

    analyze_in = AnalyzeStageInput(
        stock_code="AAPL",
        report_type=ReportType.FULL,
        query_id="q-2",
        stock_name="Apple",
    )
    assert analyze_in.report_type == "full"
    assert analyze_in.to_input_summary()["report_type"] == "full"

    single = RenderStageInput(
        report_type=ReportType.SIMPLE,
        result_count=1,
        route="single_stock",
        stock_code="AAPL",
    )
    assert single.to_input_summary() == {
        "report_type": "simple",
        "result_count": 1,
        "stock_code": "AAPL",
    }
    local = RenderStageInput(
        report_type="simple",
        result_count=3,
        route="local_report",
    )
    assert local.to_input_summary()["route"] == "local_report"


def test_analyze_and_render_outputs_legacy_values() -> None:
    result = SimpleNamespace(success=True, model_used="test-model")
    analyze_out = AnalyzeStageOutput.from_result(result)
    assert analyze_out.as_legacy_value() is result
    assert analyze_out.to_output_summary() == {
        "analysis_result_available": True,
        "analysis_success": True,
        "model": "test-model",
    }

    content = "# Report"
    render_out = RenderStageOutput.from_content(content, route="single_stock")
    assert render_out.as_legacy_value() == content
    assert render_out == content
    assert render_out.to_output_summary()["content_length"] == len(content)

    local = RenderStageOutput.from_content(
        content,
        route="local_report",
        saved_path="/tmp/report.md",
    )
    assert local.as_legacy_value() == (content, "/tmp/report.md")
    body, path = local.as_legacy_value()
    assert body == content
    assert path == "/tmp/report.md"


def test_stage_error_taxonomy_maps_to_pipeline_results() -> None:
    skipped = StageSkippedError(stage="render", reason="notification_not_configured")
    skipped_result = stage_result_from_error(skipped, stage=PipelineStageName.RENDER)
    assert skipped_result.status == PipelineStageStatus.SKIPPED
    assert skipped_result.degradation_reason == "notification_not_configured"

    degraded = StageDegradedError(
        stage="fetch",
        reason="partial_inputs",
        value=FetchDailyDataOutput(False, "timeout"),
        retryable=True,
    )
    degraded_result = stage_result_from_error(degraded, stage=PipelineStageName.FETCH)
    assert degraded_result.status == PipelineStageStatus.DEGRADED
    assert degraded_result.retryable is True
    assert degraded_result.value == (False, "timeout")

    failed = StageFailedError(stage="analyze", reason="llm_timeout", retryable=False)
    failed_result = stage_result_from_error(failed, stage=PipelineStageName.ANALYZE)
    assert failed_result.status == PipelineStageStatus.FAILED
    assert failed_result.retryable is False
    assert failed_result.error is failed


def test_pipeline_stage_runner_honors_stage_error_taxonomy() -> None:
    """StageError raised inside a stage is converted via the contract mapper."""
    runner = PipelineStageRunner()

    def _skip() -> str:
        raise StageSkippedError(reason="analysis_disabled")

    result = runner.run(PipelineStageName.ANALYZE, _skip, retryable=True)
    assert result.status == PipelineStageStatus.SKIPPED
    assert result.degradation_reason == "analysis_disabled"

    def _fail() -> str:
        raise StageFailedError(reason="hard_failure", retryable=False)

    failed = runner.run(PipelineStageName.FETCH, _fail, retryable=True)
    assert failed.status == PipelineStageStatus.FAILED
    assert failed.retryable is False
    assert isinstance(failed.error, StageFailedError)


def test_process_single_stock_uses_fetch_daily_contract() -> None:
    """Primary fetch stage stores FetchDailyDataOutput while remaining tuple-equal."""
    from src.core.pipeline import StockAnalysisPipeline
    from src.core.pipeline_stage_results import PipelineStageName, PipelineStageRunner
    from datetime import date

    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._pipeline_stage_runner = PipelineStageRunner()
    pipeline.query_id = "query-contract"
    pipeline.trace_id = "trace-contract"
    pipeline.query_source = "api"
    pipeline.analysis_phase = "auto"
    pipeline.portfolio_context = None
    pipeline.save_context_snapshot = False
    pipeline._emit_progress = MagicMock()
    pipeline._resolve_resume_target_date = MagicMock(return_value=date(2026, 7, 17))
    pipeline.fetch_and_save_stock_data = MagicMock(return_value=(True, None))
    expected = SimpleNamespace(
        code="600519",
        query_id="query-contract",
        success=True,
        sentiment_score=67,
    )
    pipeline.analyze_stock = MagicMock(return_value=expected)
    pipeline._refresh_saved_diagnostic_snapshot = MagicMock()

    actual = pipeline.process_single_stock(
        "600519",
        report_type=ReportType.SIMPLE,
        analysis_query_id="query-contract",
        current_time=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    assert actual is expected
    fetch_stage = pipeline._get_pipeline_stage_runner().latest(PipelineStageName.FETCH)
    assert isinstance(fetch_stage.value, FetchDailyDataOutput)
    # Behavior-preserving equality with the historical tuple value.
    assert fetch_stage.value == (True, None)
    assert isinstance(pipeline._current_run_context, RunContext)
    assert pipeline._current_run_context.stock_code == "600519"
    assert pipeline._current_run_context.query_id == "query-contract"


def test_pipeline_module_remains_orchestration_facade() -> None:
    """pipeline.py stays a thin facade: no new product business helpers."""
    from pathlib import Path

    source = Path("src/core/pipeline.py").read_text(encoding="utf-8")
    assert "orchestration-only" in source or "Issue #1083" in source
    assert "src/core/contracts" in source or "Issue #1072" in source
    # Guard against re-depositing fat business methods into the facade file.
    assert "def generate_dashboard_report" not in source
    assert "def search_stock_news" not in source
    # Line budget: orchestration facade must stay far below historical bulk.
    assert source.count("\n") < 600
