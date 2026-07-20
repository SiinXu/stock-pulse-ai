# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression tests for behavior-preserving Pipeline stage diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.services import run_diagnostics
from src.services.run_diagnostics import (
    PIPELINE_STAGE_NAMES,
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    get_current_diagnostic_context,
    observe_pipeline_stage,
    record_missing_pipeline_stages_as_skipped,
    record_pipeline_stage,
    reset_run_diagnostic_context,
)


def test_stage_observation_records_required_sanitized_fields(monkeypatch) -> None:
    """Record trace, timing, status, degradation, retryability, and summaries."""
    moments = iter((10.0, 10.125))
    monkeypatch.setattr(run_diagnostics.time, "monotonic", lambda: next(moments))
    events: list[dict] = []
    token = activate_run_diagnostic_context(
        trace_id="trace-stage",
        stock_code="600519",
        event_sink=events.append,
    )
    try:
        stage = observe_pipeline_stage(
            "fetch",
            input_summary={"stock_code": "600519", "api_key": "secret-value"},
            retryable=True,
        )
        stage.finish(
            status="degraded",
            output_summary={"record_count": 0},
            degradation_reason="token=secret-value",
        )
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    run = snapshot["pipeline_stage_runs"][0]
    assert run["trace_id"] == "trace-stage"
    assert run["stage"] == "fetch"
    assert run["status"] == "degraded"
    assert run["duration_ms"] == 125
    assert run["degraded"] is True
    assert run["retryable"] is True
    assert run["input_summary"] == {
        "stock_code": "600519",
        "api_key": "<redacted>",
    }
    assert run["output_summary"] == {"record_count": 0}
    assert "secret-value" not in run["degradation_reason"]
    assert run["started_at"]
    assert run["ended_at"]
    assert events == []


def test_stage_observation_records_and_reraises_uncaught_failure() -> None:
    """Record an uncaught stage error without changing exception propagation."""
    token = activate_run_diagnostic_context(trace_id="trace-failure")
    try:
        with pytest.raises(RuntimeError, match="secret-value"):
            with observe_pipeline_stage(
                "analyze",
                input_summary={"stock_code": "AAPL"},
                retryable=True,
            ):
                raise RuntimeError("token=secret-value")
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    run = snapshot["pipeline_stage_runs"][0]
    assert run["status"] == "failed"
    assert run["degraded"] is False
    assert run["retryable"] is True
    assert run["error_type"] == "RuntimeError"
    assert "secret-value" not in run["error_message_sanitized"]


def test_diagnostic_recording_failure_does_not_replace_pipeline_error(
    monkeypatch,
    caplog,
) -> None:
    """Preserve the original Pipeline error when diagnostic persistence fails."""
    token = activate_run_diagnostic_context(trace_id="trace-fail-open")
    try:
        context = get_current_diagnostic_context()
        assert context is not None

        def _fail_recording(stage_run) -> None:
            _ = stage_run
            raise RuntimeError("diagnostic sink unavailable")

        monkeypatch.setattr(context, "record_pipeline_stage", _fail_recording)
        with pytest.raises(ValueError, match="pipeline failure"):
            with observe_pipeline_stage("analyze"):
                raise ValueError("pipeline failure")
    finally:
        reset_run_diagnostic_context(token)

    assert "Pipeline stage diagnostic record failed" in caplog.text


def test_stage_observation_is_terminal_exactly_once() -> None:
    """Keep the first explicit terminal status when completion is repeated."""
    token = activate_run_diagnostic_context(trace_id="trace-once")
    try:
        stage = observe_pipeline_stage("dispatch", input_summary={"result_count": 1})
        stage.finish(status="skipped", output_summary={"reason": "disabled"})
        stage.finish(status="success")
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    assert len(snapshot["pipeline_stage_runs"]) == 1
    assert snapshot["pipeline_stage_runs"][0]["status"] == "skipped"


def test_invalid_stage_diagnostic_fails_open(caplog) -> None:
    """Ignore an invalid diagnostic record without affecting the caller."""
    token = activate_run_diagnostic_context(trace_id="trace-invalid")
    try:
        record_pipeline_stage(stage="unknown", status="success")
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    assert snapshot["pipeline_stage_runs"] == []
    assert "Pipeline stage diagnostic record failed" in caplog.text


def test_pipeline_stage_name_contract_is_complete_and_ordered() -> None:
    """Keep the PIPE-02 target stages stable for downstream decomposition."""
    assert PIPELINE_STAGE_NAMES == (
        "resolve",
        "fetch",
        "intelligence",
        "context",
        "analyze",
        "persist",
        "render",
        "dispatch",
    )


def test_missing_pipeline_stages_are_filled_once_in_contract_order() -> None:
    """Complete a partial trace with explicit skipped stages and no duplicates."""
    token = activate_run_diagnostic_context(trace_id="trace-partial")
    try:
        record_pipeline_stage(stage="resolve", status="success")
        record_pipeline_stage(stage="fetch", status="failed")
        first_added = record_missing_pipeline_stages_as_skipped(
            PIPELINE_STAGE_NAMES,
            input_summary={"stock_code": "600519"},
            reason="stock_processing_failed",
        )
        second_added = record_missing_pipeline_stages_as_skipped(
            PIPELINE_STAGE_NAMES,
            input_summary={"stock_code": "600519"},
            reason="stock_processing_failed",
        )
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    assert first_added == 6
    assert second_added == 0
    assert [run["stage"] for run in snapshot["pipeline_stage_runs"]] == list(
        PIPELINE_STAGE_NAMES
    )
    assert [run["status"] for run in snapshot["pipeline_stage_runs"]] == [
        "success",
        "failed",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
    ]


def test_dry_run_records_all_pipeline_stages_in_order() -> None:
    """Represent disabled downstream work as explicit skipped stage outcomes."""
    from src.core.pipeline import StockAnalysisPipeline

    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.query_id = "query-dry-run"
    pipeline.trace_id = "trace-dry-run"
    pipeline.query_source = "api"
    pipeline._emit_progress = lambda progress, message: None
    pipeline.fetch_and_save_stock_data = lambda code, current_time=None: (True, None)
    token = activate_run_diagnostic_context(
        trace_id="trace-dry-run",
        query_id="query-dry-run",
        stock_code="600519",
    )
    try:
        result = pipeline.process_single_stock(
            "600519",
            skip_analysis=True,
            current_time=datetime(2026, 7, 20, tzinfo=timezone.utc),
        )
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert result is None
    assert snapshot is not None
    assert [run["stage"] for run in snapshot["pipeline_stage_runs"]] == list(
        PIPELINE_STAGE_NAMES
    )
    assert [run["status"] for run in snapshot["pipeline_stage_runs"]] == [
        "success",
        "success",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
    ]


class _FailedNotifier:
    """Minimal notifier that renders successfully but cannot dispatch."""

    def is_available(self) -> bool:
        """Expose one configured notification route."""
        return True

    def generate_single_stock_report(self, result) -> str:
        """Return a deterministic rendered report."""
        _ = result
        return "rendered report"

    def send(self, content: str, **kwargs) -> bool:
        """Return a delivery failure without raising."""
        _ = (content, kwargs)
        return False


def test_notification_failure_is_dispatch_failure_not_analysis_failure() -> None:
    """Keep a successful analysis intact when the dispatch stage fails."""
    from src.core.pipeline import StockAnalysisPipeline
    from src.enums import ReportType

    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.notifier = _FailedNotifier()
    pipeline.save_context_snapshot = False
    result = SimpleNamespace(code="600519", query_id="query-stage", success=True)
    token = activate_run_diagnostic_context(
        trace_id="trace-dispatch",
        query_id="query-stage",
        stock_code="600519",
    )
    try:
        pipeline._send_single_stock_notification(result, ReportType.SIMPLE)
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert result.success is True
    assert snapshot is not None
    stage_runs = snapshot["pipeline_stage_runs"]
    assert [(run["stage"], run["status"]) for run in stage_runs] == [
        ("render", "success"),
        ("dispatch", "failed"),
    ]
