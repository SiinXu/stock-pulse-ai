# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression tests for behavior-preserving Pipeline stage diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services import run_diagnostics
from src.services.run_diagnostics import (
    PIPELINE_STAGE_NAMES,
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    get_current_diagnostic_context,
    observe_pipeline_stage,
    record_missing_pipeline_stages_as_skipped,
    record_notification_run,
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


def test_stage_input_sanitization_failure_is_fail_open(caplog) -> None:
    """Use an empty summary when a diagnostic value cannot be stringified."""

    class _UnprintableValue:
        def __str__(self) -> str:
            """Raise to simulate an unsafe diagnostic object."""
            raise RuntimeError("cannot stringify diagnostic value")

    token = activate_run_diagnostic_context(trace_id="trace-sanitize-failure")
    try:
        stage = observe_pipeline_stage(
            "fetch",
            input_summary={"unexpected": _UnprintableValue()},
        )
        stage.finish(status="success")
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    assert snapshot["pipeline_stage_runs"][0]["input_summary"] == {}
    assert "Pipeline stage input summary sanitization failed" in caplog.text


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


def test_resolve_failure_is_timed_and_skips_downstream_stages() -> None:
    """Record target-date resolution failures before filling downstream skips."""
    from src.core.pipeline import StockAnalysisPipeline

    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.query_id = "query-resolve-failure"
    pipeline.trace_id = "trace-resolve-failure"
    pipeline.query_source = "api"

    def _fail_resolve(code, current_time=None):
        """Raise before a frozen target-date token exists."""
        _ = (code, current_time)
        raise RuntimeError("target date unavailable")

    pipeline._resolve_resume_target_date = _fail_resolve
    token = activate_run_diagnostic_context(
        trace_id="trace-resolve-failure",
        query_id="query-resolve-failure",
        stock_code="600519",
    )
    try:
        with pytest.raises(RuntimeError, match="target date unavailable"):
            pipeline.process_single_stock("600519")
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    assert [run["stage"] for run in snapshot["pipeline_stage_runs"]] == list(
        PIPELINE_STAGE_NAMES
    )
    assert snapshot["pipeline_stage_runs"][0]["status"] == "failed"
    assert snapshot["pipeline_stage_runs"][0]["error_type"] == "RuntimeError"
    assert all(
        run["status"] == "skipped"
        for run in snapshot["pipeline_stage_runs"][1:]
    )


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


class _PartialStructuredNotifier:
    """Notifier exposing one successful and one failed static channel."""

    def is_available(self) -> bool:
        """Expose configured report channels."""
        return True

    def generate_single_stock_report(self, result) -> str:
        """Return a deterministic rendered report."""
        _ = result
        return "rendered report"

    def send_with_results(self, content: str, **kwargs):
        """Return the authoritative per-channel delivery result."""
        from src.notification import ChannelAttemptResult, NotificationDispatchResult

        _ = (content, kwargs)
        return NotificationDispatchResult(
            dispatched=True,
            success=True,
            status="partial_failed",
            channel_results=[
                ChannelAttemptResult(channel="email", success=True),
                ChannelAttemptResult(
                    channel="ntfy",
                    success=False,
                    error_code="send_failed",
                    retryable=True,
                ),
            ],
        )

    def send(self, content: str, **kwargs) -> bool:
        """Reject use of the lossy compatibility API."""
        _ = (content, kwargs)
        raise AssertionError("send() must not collapse structured results")


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
    assert stage_runs[-1]["output_summary"]["attempt_count"] == 1
    assert stage_runs[-1]["output_summary"]["failure_count"] == 1
    assert stage_runs[-1]["retryable"] is True


def test_single_stock_partial_dispatch_is_degraded_and_not_retryable() -> None:
    """Preserve partial multi-channel results without retrying delivered channels."""
    from src.core.pipeline import StockAnalysisPipeline
    from src.enums import ReportType

    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.notifier = _PartialStructuredNotifier()
    pipeline.save_context_snapshot = False
    result = SimpleNamespace(code="600519", query_id="query-stage", success=True)
    token = activate_run_diagnostic_context(trace_id="trace-partial-single")
    try:
        pipeline._send_single_stock_notification(result, ReportType.SIMPLE)
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    dispatch_run = snapshot["pipeline_stage_runs"][-1]
    assert dispatch_run["stage"] == "dispatch"
    assert dispatch_run["status"] == "degraded"
    assert dispatch_run["retryable"] is False
    assert dispatch_run["output_summary"]["dispatch_status"] == "partial_failed"
    assert dispatch_run["output_summary"]["attempt_count"] == 2
    assert dispatch_run["output_summary"]["failure_count"] == 1
    assert [
        (run["channel"], run["status"])
        for run in snapshot["notification_runs"]
    ] == [("email", "success"), ("ntfy", "failed")]
    assert result.success is True


@pytest.mark.parametrize(
    (
        "dispatch_result",
        "expected_status",
        "expected_retryable",
    ),
    (
        (SimpleNamespace(
            dispatched=True,
            success=True,
            status="sent",
            channel_results=[SimpleNamespace(channel="email", success=True)],
        ), "success", False),
        (SimpleNamespace(
            dispatched=True,
            success=False,
            status="all_failed",
            channel_results=[
                SimpleNamespace(
                    channel="email",
                    success=False,
                    retryable=True,
                    error_code="send_failed",
                )
            ],
        ), "failed", True),
        (SimpleNamespace(
            dispatched=False,
            success=False,
            status="noise_suppressed",
            channel_results=[],
        ), "skipped", False),
        (SimpleNamespace(
            dispatched=False,
            success=False,
            status="no_channel",
            channel_results=[],
        ), "skipped", False),
    ),
)
def test_single_stock_structured_dispatch_status_mapping(
    dispatch_result,
    expected_status: str,
    expected_retryable: bool,
) -> None:
    """Map the notifier's structured terminal contract into Pipeline status."""
    from src.core.pipeline import StockAnalysisPipeline
    from src.enums import ReportType

    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.notifier = _PartialStructuredNotifier()
    pipeline.notifier.send_with_results = MagicMock(return_value=dispatch_result)
    pipeline.save_context_snapshot = False
    result = SimpleNamespace(code="600519", query_id="query-stage", success=True)
    token = activate_run_diagnostic_context(trace_id="trace-structured-single")
    try:
        pipeline._send_single_stock_notification(result, ReportType.SIMPLE)
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    dispatch_run = snapshot["pipeline_stage_runs"][-1]
    assert dispatch_run["status"] == expected_status
    assert dispatch_run["retryable"] is expected_retryable


def test_local_report_save_failure_marks_render_failed() -> None:
    """Keep local output persistence inside the render terminal outcome."""
    from src.core.pipeline import StockAnalysisPipeline
    from src.enums import ReportType

    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._generate_aggregate_report = lambda results, report_type: "report"

    def _fail_save(report):
        """Raise while persisting an otherwise rendered report."""
        _ = report
        raise RuntimeError("local report storage unavailable")

    pipeline.notifier = SimpleNamespace(save_report_to_file=_fail_save)
    token = activate_run_diagnostic_context(trace_id="trace-local-render")
    try:
        pipeline._save_local_report(
            [SimpleNamespace(code="600519")],
            ReportType.SIMPLE,
        )
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    run = snapshot["pipeline_stage_runs"][0]
    assert run["stage"] == "render"
    assert run["status"] == "failed"
    assert run["error_type"] == "RuntimeError"


def test_delivery_snapshot_merge_preserves_analysis_and_final_dispatch() -> None:
    """Merge cumulative delivery runs once and persist the final dispatch record."""
    from src.core.pipeline import StockAnalysisPipeline

    upstream_run = {
        "trace_id": "stock-trace",
        "stage": "analyze",
        "status": "success",
    }
    result = SimpleNamespace(
        code="600519",
        query_id="stock-query",
        diagnostic_context_snapshot={
            "diagnostics": {
                "trace_id": "stock-trace",
                "query_id": "stock-query",
                "stock_code": "600519",
                "pipeline_stage_runs": [upstream_run],
                "notification_runs": [],
            }
        },
    )
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.save_context_snapshot = True
    pipeline.db = MagicMock()
    pipeline.query_id = None
    pipeline.trace_id = None
    pipeline.query_source = "cli"

    token = pipeline._activate_delivery_diagnostic_context([result])
    try:
        record_pipeline_stage(stage="render", status="success")
        notification_run = pipeline._build_notification_run_snapshot(
            channel="email",
            status="success",
            success=True,
        )
        record_notification_run(
            channel="email",
            status="success",
            success=True,
        )
        pipeline._refresh_saved_diagnostic_snapshot(
            results=[result],
            notification_run=notification_run,
        )
        record_pipeline_stage(stage="dispatch", status="success")
        pipeline._refresh_saved_diagnostic_snapshot(results=[result])
    finally:
        reset_run_diagnostic_context(token)

    diagnostics = result.diagnostic_context_snapshot["diagnostics"]
    assert [run["stage"] for run in diagnostics["pipeline_stage_runs"]] == [
        "analyze",
        "render",
        "dispatch",
    ]
    assert [run["channel"] for run in diagnostics["notification_runs"]] == [
        "email"
    ]
    assert pipeline.db.update_analysis_history_diagnostics.call_count == 2
    assert (
        pipeline.db.update_analysis_history_diagnostics.call_args.kwargs[
            "diagnostics"
        ]["pipeline_stage_runs"][-1]["stage"]
        == "dispatch"
    )


def test_delivery_context_is_nested_without_mutating_outer_trace() -> None:
    """Keep batch delivery runs out of an unrelated caller diagnostic context."""
    from src.core.pipeline import StockAnalysisPipeline

    result = SimpleNamespace(
        code="600519",
        query_id="stock-query",
        diagnostic_context_snapshot={
            "diagnostics": {
                "trace_id": "stock-trace",
                "query_id": "stock-query",
                "stock_code": "600519",
                "pipeline_stage_runs": [
                    {
                        "trace_id": "stock-trace",
                        "stage": "analyze",
                        "status": "success",
                    }
                ],
                "notification_runs": [],
            }
        },
    )
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.save_context_snapshot = True
    pipeline.db = MagicMock()
    pipeline.query_id = None
    pipeline.trace_id = None
    pipeline.query_source = "cli"

    outer_token = activate_run_diagnostic_context(
        trace_id="outer-trace",
        query_id="outer-query",
        scope="request",
    )
    try:
        record_pipeline_stage(stage="fetch", status="success")
        outer_before = current_diagnostic_snapshot()
        delivery_token = pipeline._activate_delivery_diagnostic_context([result])
        try:
            delivery_context = get_current_diagnostic_context()
            assert delivery_context is not None
            assert delivery_context.scope == "pipeline_delivery"
            record_pipeline_stage(stage="render", status="success")
            record_pipeline_stage(stage="dispatch", status="success")
            pipeline._refresh_saved_diagnostic_snapshot(results=[result])
        finally:
            reset_run_diagnostic_context(delivery_token)
        outer_after = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(outer_token)

    assert outer_after == outer_before
    assert [
        run["stage"]
        for run in result.diagnostic_context_snapshot["diagnostics"][
            "pipeline_stage_runs"
        ]
    ] == ["analyze", "render", "dispatch"]
    persisted = pipeline.db.update_analysis_history_diagnostics.call_args.kwargs[
        "diagnostics"
    ]
    assert [run["stage"] for run in persisted["pipeline_stage_runs"]] == [
        "analyze",
        "render",
        "dispatch",
    ]


def test_delivery_snapshot_keeps_targeted_notification_runs_isolated() -> None:
    """Do not copy one stock-group notification outcome into another result."""
    from src.core.pipeline import StockAnalysisPipeline

    def _result(code: str, query_id: str):
        """Build one result with an existing analysis diagnostic snapshot."""
        return SimpleNamespace(
            code=code,
            query_id=query_id,
            diagnostic_context_snapshot={
                "diagnostics": {
                    "trace_id": query_id,
                    "query_id": query_id,
                    "stock_code": code,
                    "pipeline_stage_runs": [],
                    "notification_runs": [],
                }
            },
        )

    group_result = _result("000001", "query-group")
    default_result = _result("600519", "query-default")
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.save_context_snapshot = True
    pipeline.db = MagicMock()
    pipeline.query_id = None
    pipeline.trace_id = None
    pipeline.query_source = "cli"

    token = pipeline._activate_delivery_diagnostic_context(
        [group_result, default_result]
    )
    try:
        group_run = pipeline._build_notification_run_snapshot(
            channel="email:group@example.com",
            status="failed",
            success=False,
        )
        record_notification_run(
            channel="email:group@example.com",
            status="failed",
            success=False,
        )
        pipeline._refresh_saved_diagnostic_snapshot(
            results=[group_result],
            notification_run=group_run,
        )

        default_run = pipeline._build_notification_run_snapshot(
            channel="email:default",
            status="success",
            success=True,
        )
        record_notification_run(
            channel="email:default",
            status="success",
            success=True,
        )
        pipeline._refresh_saved_diagnostic_snapshot(
            results=[default_result],
            notification_run=default_run,
        )
        record_pipeline_stage(stage="dispatch", status="degraded")
        pipeline._refresh_saved_diagnostic_snapshot(
            results=[group_result, default_result]
        )
    finally:
        reset_run_diagnostic_context(token)

    assert [
        run["channel"]
        for run in group_result.diagnostic_context_snapshot["diagnostics"][
            "notification_runs"
        ]
    ] == ["email:group@example.com"]
    assert [
        run["channel"]
        for run in default_result.diagnostic_context_snapshot["diagnostics"][
            "notification_runs"
        ]
    ] == ["email:default"]
    assert all(
        result.diagnostic_context_snapshot["diagnostics"][
            "pipeline_stage_runs"
        ][-1]["stage"]
        == "dispatch"
        for result in (group_result, default_result)
    )


def test_batch_run_persists_actual_render_and_disabled_dispatch() -> None:
    """Observe batch delivery after worker contexts finish instead of pre-skipping it."""
    from src.core.pipeline import StockAnalysisPipeline

    result = SimpleNamespace(
        code="600519",
        query_id="query-batch-stock",
        success=True,
        diagnostic_context_snapshot={
            "diagnostics": {
                "trace_id": "trace-batch-stock",
                "query_id": "query-batch-stock",
                "stock_code": "600519",
                "pipeline_stage_runs": [
                    {
                        "trace_id": "trace-batch-stock",
                        "stage": "persist",
                        "status": "success",
                    }
                ],
                "notification_runs": [],
            }
        },
    )
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.max_workers = 1
    pipeline.query_id = None
    pipeline.trace_id = None
    pipeline.query_source = "cli"
    pipeline.save_context_snapshot = True
    pipeline.fetcher_manager = MagicMock()
    pipeline.db = MagicMock()
    pipeline.config = SimpleNamespace(
        stock_list=["600519"],
        refresh_stock_list=lambda: None,
        single_stock_notify=False,
        report_type="simple",
        analysis_delay=0,
    )
    pipeline.notifier = SimpleNamespace(
        generate_dashboard_report=lambda results: "batch report",
        save_report_to_file=lambda report: "/tmp/batch-report.md",
    )
    pipeline.process_single_stock = MagicMock(return_value=result)

    results = pipeline.run(
        stock_codes=["600519"],
        dry_run=False,
        send_notification=False,
    )

    assert results == [result]
    stage_runs = result.diagnostic_context_snapshot["diagnostics"][
        "pipeline_stage_runs"
    ]
    assert [(run["stage"], run["status"]) for run in stage_runs] == [
        ("persist", "success"),
        ("render", "success"),
        ("dispatch", "skipped"),
    ]
    assert (
        pipeline.db.update_analysis_history_diagnostics.call_args.kwargs[
            "diagnostics"
        ]["pipeline_stage_runs"][-1]["stage"]
        == "dispatch"
    )


class _PartialDeliveryNotifier:
    """Notifier with a failed context route and a successful static route."""

    _markdown_to_image_channels: set[str] = set()
    _markdown_to_image_max_chars = 15000

    def generate_aggregate_report(self, results, report_type) -> str:
        """Return deterministic aggregate content."""
        _ = (results, report_type)
        return "aggregate report"

    def is_available(self) -> bool:
        """Expose the configured static route."""
        return True

    def get_available_channels(self):
        """Return one successful static channel."""
        from src.notification import NotificationChannel

        return [NotificationChannel.NTFY]

    def get_channels_for_route(self, route_type, channels=None):
        """Keep the supplied report-route channels."""
        _ = route_type
        return list(channels or [])

    def _has_context_channel(self) -> bool:
        """Expose one configured contextual reply route."""
        return True

    def send_to_context(self, report) -> bool:
        """Fail the contextual delivery."""
        _ = report
        return False

    def should_broadcast_static_channels(self) -> bool:
        """Allow the static route after contextual failure."""
        return True

    def send_to_ntfy(self, report) -> bool:
        """Deliver through the static route."""
        _ = report
        return True


class _NoiseSuppressedNotifier:
    """Notifier with configurable context delivery before static suppression."""

    _markdown_to_image_channels: set[str] = set()
    _markdown_to_image_max_chars = 15000

    def __init__(self, *, context_available: bool, context_success: bool) -> None:
        self.context_available = context_available
        self.context_success = context_success

    def generate_aggregate_report(self, results, report_type) -> str:
        """Return deterministic aggregate content."""
        _ = (results, report_type)
        return "aggregate report"

    def is_available(self) -> bool:
        """Expose one static channel subject to noise control."""
        return True

    def get_available_channels(self):
        """Return one configured static channel."""
        from src.notification import NotificationChannel

        return [NotificationChannel.NTFY]

    def get_channels_for_route(self, route_type, channels=None):
        """Keep the supplied report-route channels."""
        _ = route_type
        return list(channels or [])

    def _has_context_channel(self) -> bool:
        """Report whether contextual delivery was configured."""
        return self.context_available

    def send_to_context(self, report) -> bool:
        """Return the configured contextual outcome."""
        _ = report
        return self.context_success

    def should_broadcast_static_channels(self) -> bool:
        """Continue to static route evaluation."""
        return True

    def evaluate_noise_control(self, report, **kwargs):
        """Suppress static delivery after context delivery is evaluated."""
        _ = (report, kwargs)
        return SimpleNamespace(
            should_send=False,
            reason_code="duplicate",
            route_type="report",
            severity="info",
            message="duplicate report",
        )


@pytest.mark.parametrize(
    ("context_available", "context_success", "expected_status", "retryable"),
    (
        (True, True, "success", False),
        (True, False, "failed", True),
        (False, False, "skipped", False),
    ),
)
def test_noise_suppression_preserves_context_delivery_outcome(
    context_available: bool,
    context_success: bool,
    expected_status: str,
    retryable: bool,
) -> None:
    """Classify dispatch from context outcome when static routes are suppressed."""
    from src.core.pipeline import StockAnalysisPipeline
    from src.enums import ReportType

    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.notifier = _NoiseSuppressedNotifier(
        context_available=context_available,
        context_success=context_success,
    )
    pipeline.config = SimpleNamespace(stock_email_groups=[])
    pipeline.save_context_snapshot = False
    token = activate_run_diagnostic_context(trace_id="trace-noise-context")
    try:
        pipeline._send_notifications(
            [SimpleNamespace(code="600519")],
            ReportType.SIMPLE,
        )
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    dispatch_run = snapshot["pipeline_stage_runs"][-1]
    assert dispatch_run["stage"] == "dispatch"
    assert dispatch_run["status"] == expected_status
    assert dispatch_run["retryable"] is retryable
    assert dispatch_run["output_summary"] == {
        "reason": "noise_control",
        "reason_code": "duplicate",
        "context_delivered": context_success,
        "context_attempted": context_available,
        "static_suppressed": True,
    }


def test_partial_dispatch_is_degraded_and_not_retryable() -> None:
    """Avoid retrying already-delivered channels before PIPE-02 idempotency fences."""
    from src.core.pipeline import StockAnalysisPipeline
    from src.enums import ReportType

    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.notifier = _PartialDeliveryNotifier()
    pipeline.config = SimpleNamespace(stock_email_groups=[])
    pipeline.save_context_snapshot = False
    token = activate_run_diagnostic_context(trace_id="trace-partial-dispatch")
    try:
        pipeline._send_notifications(
            [SimpleNamespace(code="600519")],
            ReportType.SIMPLE,
        )
        snapshot = current_diagnostic_snapshot()
    finally:
        reset_run_diagnostic_context(token)

    assert snapshot is not None
    dispatch_run = snapshot["pipeline_stage_runs"][-1]
    assert dispatch_run["stage"] == "dispatch"
    assert dispatch_run["status"] == "degraded"
    assert dispatch_run["degraded"] is True
    assert dispatch_run["retryable"] is False
    assert dispatch_run["output_summary"]["attempt_count"] == 2
    assert dispatch_run["output_summary"]["failure_count"] == 1
