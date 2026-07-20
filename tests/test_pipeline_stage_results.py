# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression tests for typed Pipeline stage execution and retry fences."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.analyzer import AnalysisResult
from src.config import Config
from src.core.pipeline import StockAnalysisPipeline
from src.core.pipeline_stage_results import (
    PipelineStageName,
    PipelineStageResult,
    PipelineStageRunner,
    PipelineStageStatus,
)
from src.enums import ReportType
from src.notification import (
    ChannelAttemptResult,
    NotificationChannel,
    NotificationDispatchResult,
    NotificationService,
)
from src.services.run_diagnostics import PIPELINE_STAGE_NAMES


def test_typed_stage_names_match_diagnostic_contract() -> None:
    """Keep executable Results aligned with the eight observable stages."""
    assert tuple(stage.value for stage in PipelineStageName) == PIPELINE_STAGE_NAMES


def test_retry_reexecutes_only_an_eligible_uncommitted_stage() -> None:
    """Retry a failed pure stage and expose the successful second attempt."""
    runner = PipelineStageRunner()
    calls = 0

    def _fail_once() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary model failure")
        return "stable-analysis-output"

    first = runner.run(
        PipelineStageName.ANALYZE,
        _fail_once,
        retryable=True,
    )
    second = runner.retry(first, _fail_once)

    assert first.status == PipelineStageStatus.FAILED
    assert first.retryable is True
    assert second.status == PipelineStageStatus.SUCCESS
    assert second.attempt == 2
    assert second.value == "stable-analysis-output"
    assert calls == 2


def test_concurrent_committed_side_effect_executes_once() -> None:
    """Serialize one keyed side effect while allowing the waiter to reuse it."""
    runner = PipelineStageRunner()
    entered = threading.Event()
    release = threading.Event()
    calls = 0

    def _persist() -> PipelineStageResult[int]:
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(timeout=2)
        return PipelineStageResult.success(
            PipelineStageName.PERSIST,
            17,
            side_effect_committed=True,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner = executor.submit(
            runner.run,
            PipelineStageName.PERSIST,
            _persist,
            side_effect_key="query-17",
        )
        assert entered.wait(timeout=2)
        waiter = executor.submit(
            runner.run,
            PipelineStageName.PERSIST,
            _persist,
            side_effect_key="query-17",
        )
        release.set()
        results = [owner.result(timeout=2), waiter.result(timeout=2)]

    assert calls == 1
    assert [result.value for result in results] == [17, 17]
    assert sorted(result.reused for result in results) == [False, True]
    assert all(result.retryable is False for result in results)


def test_persist_retry_does_not_duplicate_committed_history() -> None:
    """Retry an uncommitted write once and fence every later invocation."""
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._pipeline_stage_runner = PipelineStageRunner()
    pipeline.save_context_snapshot = True
    pipeline.db = SimpleNamespace(
        save_analysis_history=MagicMock(side_effect=[0, 41]),
    )
    pipeline._extract_decision_signal_after_history_save = MagicMock()
    result = SimpleNamespace(code="600519", diagnostic_context_snapshot=None)
    snapshots = MagicMock(side_effect=[{"attempt": 1}, {"attempt": 2}])

    def _persist() -> PipelineStageResult:
        return pipeline._persist_analysis_history_stage(
            result=result,
            query_id="query-persist",
            report_type="simple",
            news_content="news",
            context_snapshot_factory=snapshots,
            portfolio_context=None,
            failure_reason="Analysis history was not saved.",
            failure_message="Analysis history persistence failed",
            failure_error_code="pipeline_analysis_history_save_failed",
        )

    first = _persist()
    second = _persist()
    third = _persist()

    assert first.status == PipelineStageStatus.FAILED
    assert first.retryable is True
    assert first.attempt == 1
    assert second.status == PipelineStageStatus.SUCCESS
    assert second.attempt == 2
    assert second.side_effect_committed is True
    assert second.value is not None
    assert second.value.history_id == 41
    assert third.reused is True
    assert third.attempt == 2
    assert third.value == second.value
    assert pipeline.db.save_analysis_history.call_count == 2
    assert snapshots.call_count == 2
    pipeline._extract_decision_signal_after_history_save.assert_called_once()


class _PartialNotifier:
    """Return one confirmed and one failed channel delivery."""

    def __init__(self) -> None:
        self.send_calls = 0
        self.rendered: list[str] = []

    def is_available(self) -> bool:
        return True

    def generate_single_stock_report(self, result) -> str:
        content = f"report:{result.code}:{result.query_id}"
        self.rendered.append(content)
        return content

    def send_with_results(self, content: str, **kwargs) -> NotificationDispatchResult:
        _ = (content, kwargs)
        self.send_calls += 1
        return NotificationDispatchResult(
            dispatched=True,
            success=True,
            status="partial_failed",
            channel_results=[
                ChannelAttemptResult(channel="email", success=True),
                ChannelAttemptResult(
                    channel="ntfy",
                    success=False,
                    retryable=True,
                    error_code="send_failed",
                ),
            ],
        )


class _AggregateNotifier:
    """Expose one aggregate channel and count its real send calls."""

    _markdown_to_image_channels: list[str] = []
    _markdown_to_image_max_chars = 10_000

    def __init__(self) -> None:
        self.send_calls = 0

    def is_available(self) -> bool:
        return True

    def get_available_channels(self):
        from src.notification import NotificationChannel

        return [NotificationChannel.NTFY]

    def get_channels_for_route(self, route_type, *, channels):
        _ = route_type
        return channels

    def _has_context_channel(self) -> bool:
        return False

    def send_to_context(self, report) -> bool:
        _ = report
        return False

    def should_broadcast_static_channels(self) -> bool:
        return True

    def send_to_ntfy(self, report) -> bool:
        _ = report
        self.send_calls += 1
        return True


class _RetryingAggregateNotifier(_AggregateNotifier):
    """Succeed once on Ntfy while retrying an initially failed Gotify send."""

    def __init__(self) -> None:
        super().__init__()
        self.gotify_calls = 0
        self.noise_evaluations = 0
        self.noise_records = 0
        self.noise_releases = 0

    def get_available_channels(self):
        from src.notification import NotificationChannel

        return [NotificationChannel.NTFY, NotificationChannel.GOTIFY]

    def send_to_gotify(self, report) -> bool:
        _ = report
        self.gotify_calls += 1
        return self.gotify_calls > 1

    def evaluate_noise_control(self, report, **kwargs):
        _ = (report, kwargs)
        self.noise_evaluations += 1
        return SimpleNamespace(
            should_send=self.noise_evaluations == 1,
            reason_code="duplicate",
            route_type="report",
            severity="info",
            message="duplicate report",
        )

    def record_noise_control(self, decision) -> None:
        _ = decision
        self.noise_records += 1

    def release_noise_control(self, decision) -> None:
        _ = decision
        self.noise_releases += 1


class _AllFailedThenSuccessNotifier(_RetryingAggregateNotifier):
    """Re-enter the first-entry noise gate after an uncommitted failure."""

    def get_available_channels(self):
        return [NotificationChannel.NTFY]

    def evaluate_noise_control(self, report, **kwargs):
        _ = (report, kwargs)
        self.noise_evaluations += 1
        return SimpleNamespace(
            should_send=True,
            reason_code="allowed",
            route_type="report",
            severity="info",
            message="",
        )

    def send_to_ntfy(self, report) -> bool:
        _ = report
        self.send_calls += 1
        return self.send_calls > 1


class _ConcurrentNoiseRetryNotifier(_AllFailedThenSuccessNotifier):
    """Model an in-flight noise reservation during concurrent re-entry."""

    def __init__(self) -> None:
        super().__init__()
        self.first_gate_entered = threading.Event()
        self.second_started = threading.Event()
        self._noise_lock = threading.Lock()
        self._noise_inflight = False

    def evaluate_noise_control(self, report, **kwargs):
        _ = (report, kwargs)
        with self._noise_lock:
            self.noise_evaluations += 1
            should_send = not self._noise_inflight
            if should_send:
                self._noise_inflight = True
        if should_send:
            self.first_gate_entered.set()
            assert self.second_started.wait(timeout=2)
        return SimpleNamespace(
            should_send=should_send,
            reason_code="allowed" if should_send else "inflight",
            route_type="report",
            severity="info",
            message="",
        )

    def record_noise_control(self, decision) -> None:
        _ = decision
        with self._noise_lock:
            self.noise_records += 1
            self._noise_inflight = False

    def release_noise_control(self, decision) -> None:
        _ = decision
        with self._noise_lock:
            self.noise_releases += 1
            self._noise_inflight = False


class _PartialThenImageErrorNotifier(_RetryingAggregateNotifier):
    """Commit one image channel before a retry fails during image rendering."""

    _markdown_to_image_channels = [NotificationChannel.TELEGRAM.value]

    def __init__(self) -> None:
        super().__init__()
        self.telegram_calls = 0

    def get_available_channels(self):
        return [NotificationChannel.TELEGRAM, NotificationChannel.GOTIFY]

    def _should_use_image_for_channel(self, channel, image_bytes) -> bool:
        _ = channel
        return image_bytes is not None

    def _send_telegram_photo(self, image_bytes) -> bool:
        _ = image_bytes
        self.telegram_calls += 1
        return True

    def send_to_telegram(self, report) -> bool:
        _ = report
        self.telegram_calls += 1
        return True


def test_delivery_reentry_increments_only_physical_attempts() -> None:
    """Advance keyed dispatch attempts while preserving a committed attempt."""
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._pipeline_stage_runner = PipelineStageRunner()
    outcomes = iter((False, True))
    send = MagicMock(side_effect=lambda: next(outcomes))
    key = ("aggregate", "simple", "ntfy", (("query", "600519"),))

    first = pipeline._run_delivery_attempt(side_effect_key=key, send=send)
    second = pipeline._run_delivery_attempt(side_effect_key=key, send=send)
    third = pipeline._run_delivery_attempt(side_effect_key=key, send=send)

    assert first.status == PipelineStageStatus.FAILED
    assert first.attempt == 1
    assert second.status == PipelineStageStatus.SUCCESS
    assert second.attempt == 2
    assert third.reused is True
    assert third.attempt == 2
    assert send.call_count == 2


def test_dispatch_retry_preserves_output_without_duplicate_notification() -> None:
    """Reuse a partial committed dispatch without sending successful channels again."""
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._pipeline_stage_runner = PipelineStageRunner()
    pipeline._single_stock_notify_lock = threading.Lock()
    pipeline.notifier = _PartialNotifier()
    pipeline.save_context_snapshot = False
    pipeline.db = SimpleNamespace(
        update_analysis_history_diagnostics=lambda **kwargs: 1,
    )
    result = SimpleNamespace(
        code="600519",
        query_id="query-dispatch",
        success=True,
    )

    with patch("src.core.pipeline.record_notification_run") as record_run:
        first_output = pipeline._send_single_stock_notification(
            result,
            report_type=ReportType.SIMPLE,
        )
        first_dispatch = pipeline._pipeline_stage_runner.latest(
            PipelineStageName.DISPATCH
        )
        second_output = pipeline._send_single_stock_notification(
            result,
            report_type=ReportType.SIMPLE,
        )

    assert first_output is None
    assert second_output is None
    assert pipeline.notifier.rendered == [
        "report:600519:query-dispatch",
        "report:600519:query-dispatch",
    ]
    assert pipeline.notifier.send_calls == 1
    assert record_run.call_count == 2
    assert first_dispatch is not None
    assert first_dispatch.side_effect_committed is True
    assert first_dispatch.retryable is False
    latest = pipeline._pipeline_stage_runner.latest(PipelineStageName.DISPATCH)
    assert latest is not None
    assert latest.status == PipelineStageStatus.DEGRADED
    assert latest.side_effect_committed is True
    assert latest.reused is True


def test_aggregate_retry_does_not_repeat_successful_channel() -> None:
    """Fence a successful aggregate channel when delivery is re-entered."""
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._pipeline_stage_runner = PipelineStageRunner()
    pipeline.notifier = _AggregateNotifier()
    pipeline.config = SimpleNamespace(stock_email_groups=[])
    pipeline._generate_aggregate_report = MagicMock(return_value="aggregate-report")
    pipeline._refresh_saved_diagnostic_snapshot = MagicMock()
    results = [
        SimpleNamespace(
            code="600519",
            query_id="query-aggregate",
            success=True,
        )
    ]

    with patch("src.core.pipeline.record_notification_run") as record_run:
        first_output = pipeline._send_notifications(results, ReportType.SIMPLE)
        second_output = pipeline._send_notifications(results, ReportType.SIMPLE)

    assert first_output is None
    assert second_output is None
    assert pipeline.notifier.send_calls == 1
    assert pipeline._generate_aggregate_report.call_count == 2
    assert record_run.call_count == 1
    latest = pipeline._pipeline_stage_runner.latest(PipelineStageName.DISPATCH)
    assert latest is not None
    assert latest.status == PipelineStageStatus.SUCCESS


def test_aggregate_retry_only_reexecutes_uncommitted_channel() -> None:
    """Retry a failed channel without replaying a confirmed delivery."""
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._pipeline_stage_runner = PipelineStageRunner()
    pipeline.notifier = _RetryingAggregateNotifier()
    pipeline.config = SimpleNamespace(stock_email_groups=[])
    pipeline._generate_aggregate_report = MagicMock(return_value="aggregate-report")
    pipeline._refresh_saved_diagnostic_snapshot = MagicMock()
    results = [
        SimpleNamespace(
            code="600519",
            query_id="query-aggregate-partial",
            success=True,
        )
    ]

    with patch("src.core.pipeline.record_notification_run") as record_run:
        first_output = pipeline._send_notifications(results, ReportType.SIMPLE)
        first_dispatch = pipeline._pipeline_stage_runner.latest(
            PipelineStageName.DISPATCH
        )
        second_output = pipeline._send_notifications(results, ReportType.SIMPLE)

    assert first_output is None
    assert second_output is None
    assert pipeline.notifier.send_calls == 1
    assert pipeline.notifier.gotify_calls == 2
    assert pipeline.notifier.noise_evaluations == 1
    assert pipeline.notifier.noise_records == 1
    assert pipeline.notifier.noise_releases == 0
    assert record_run.call_count == 3
    assert first_dispatch is not None
    assert first_dispatch.status == PipelineStageStatus.DEGRADED
    assert first_dispatch.side_effect_committed is True
    assert first_dispatch.retryable is True
    latest = pipeline._pipeline_stage_runner.latest(PipelineStageName.DISPATCH)
    assert latest is not None
    assert latest.status == PipelineStageStatus.SUCCESS


def test_all_failed_aggregate_rechecks_noise_gate_before_retry() -> None:
    """Release an uncommitted scope and reacquire noise control on retry."""
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._pipeline_stage_runner = PipelineStageRunner()
    pipeline.notifier = _AllFailedThenSuccessNotifier()
    pipeline.config = SimpleNamespace(stock_email_groups=[])
    pipeline._generate_aggregate_report = MagicMock(return_value="aggregate-report")
    pipeline._refresh_saved_diagnostic_snapshot = MagicMock()
    results = [
        SimpleNamespace(
            code="600519",
            query_id="query-aggregate-all-failed",
            success=True,
        )
    ]

    first_output = pipeline._send_notifications(results, ReportType.SIMPLE)
    second_output = pipeline._send_notifications(results, ReportType.SIMPLE)

    assert first_output is None
    assert second_output is None
    assert pipeline.notifier.send_calls == 2
    assert pipeline.notifier.noise_evaluations == 2
    assert pipeline.notifier.noise_releases == 1
    assert pipeline.notifier.noise_records == 1


def test_concurrent_aggregate_reentry_waits_for_owner_outcome() -> None:
    """Wait out an owner's failed reservation before evaluating the retry gate."""
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._pipeline_stage_runner = PipelineStageRunner()
    pipeline.notifier = _ConcurrentNoiseRetryNotifier()
    pipeline.config = SimpleNamespace(stock_email_groups=[])
    pipeline._generate_aggregate_report = MagicMock(return_value="aggregate-report")
    pipeline._refresh_saved_diagnostic_snapshot = MagicMock()
    results = [
        SimpleNamespace(
            code="600519",
            query_id="query-aggregate-concurrent",
            success=True,
        )
    ]

    def _waiter() -> None:
        pipeline.notifier.second_started.set()
        return pipeline._send_notifications(results, ReportType.SIMPLE)

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner = executor.submit(
            pipeline._send_notifications,
            results,
            ReportType.SIMPLE,
        )
        assert pipeline.notifier.first_gate_entered.wait(timeout=2)
        waiter = executor.submit(_waiter)
        outputs = [owner.result(timeout=3), waiter.result(timeout=3)]

    assert outputs == [None, None]
    assert pipeline.notifier.noise_evaluations == 2
    assert pipeline.notifier.send_calls == 2
    assert pipeline.notifier.noise_releases == 1
    assert pipeline.notifier.noise_records == 1


def test_partial_scope_survives_reentry_error_before_cached_channels() -> None:
    """Keep a committed scope when retry setup fails before channel reuse."""
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline._pipeline_stage_runner = PipelineStageRunner()
    pipeline.notifier = _PartialThenImageErrorNotifier()
    pipeline.config = SimpleNamespace(stock_email_groups=[])
    pipeline._generate_aggregate_report = MagicMock(return_value="aggregate-report")
    pipeline._refresh_saved_diagnostic_snapshot = MagicMock()
    results = [
        SimpleNamespace(
            code="600519",
            query_id="query-aggregate-reentry-error",
            success=True,
        )
    ]
    static_scope = (
        "aggregate_static_delivery",
        pipeline._delivery_stage_key(
            route="aggregate",
            results=results,
            report_type=ReportType.SIMPLE,
        ),
    )

    with patch("src.md2img.markdown_to_image", return_value=b"image"):
        pipeline._send_notifications(results, ReportType.SIMPLE)
    assert pipeline._pipeline_stage_runner.scope_started(static_scope) is True

    with patch(
        "src.md2img.markdown_to_image",
        side_effect=RuntimeError("image renderer unavailable"),
    ):
        pipeline._send_notifications(results, ReportType.SIMPLE)
    assert pipeline._pipeline_stage_runner.scope_started(static_scope) is True

    with patch("src.md2img.markdown_to_image", return_value=b"image"):
        pipeline._send_notifications(results, ReportType.SIMPLE)

    assert pipeline.notifier.noise_evaluations == 1
    assert pipeline.notifier.telegram_calls == 1
    assert pipeline.notifier.gotify_calls == 2


def test_process_single_stock_returns_original_analysis_result() -> None:
    """Keep the compatibility output identical while stages use typed Results."""
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.query_id = "query-output"
    pipeline.trace_id = "trace-output"
    pipeline.query_source = "api"
    pipeline._emit_progress = MagicMock()
    pipeline._resolve_resume_target_date = MagicMock(return_value=date(2026, 7, 17))
    pipeline.fetch_and_save_stock_data = MagicMock(return_value=(True, None))
    expected = SimpleNamespace(
        code="600519",
        query_id="query-output",
        success=True,
        sentiment_score=67,
    )
    pipeline.analyze_stock = MagicMock(return_value=expected)
    pipeline._refresh_saved_diagnostic_snapshot = MagicMock()

    actual = pipeline.process_single_stock(
        "600519",
        report_type=ReportType.SIMPLE,
        analysis_query_id="query-output",
        current_time=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )

    assert actual is expected
    assert pipeline._get_pipeline_stage_runner().latest(
        PipelineStageName.RESOLVE
    ).status == PipelineStageStatus.SUCCESS
    assert pipeline._get_pipeline_stage_runner().latest(
        PipelineStageName.FETCH
    ).value == (True, None)


def test_real_report_content_is_identical_for_save_and_dispatch() -> None:
    """Pass real aggregate Markdown through both output routes unchanged."""
    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 7, 20, 12, 0, 0, tzinfo=tz)

    config = Config(
        stock_list=[],
        report_language="en",
        report_renderer_enabled=False,
    )
    result = AnalysisResult(
        code="AAPL",
        name="Apple",
        sentiment_score=72,
        trend_prediction="Bullish",
        operation_advice="Hold",
        analysis_summary="Stable outlook",
        report_language="en",
        query_id="query-output-equivalence",
    )

    with patch("src.notification.datetime", _FrozenDateTime), patch(
        "src.notification.get_config",
        return_value=config,
    ):
        notifier = NotificationService()
        expected = notifier.generate_aggregate_report(
            [result],
            ReportType.SIMPLE,
        )
        notifier.save_report_to_file = MagicMock(
            return_value="/tmp/output-equivalence.md"
        )
        notifier.is_available = MagicMock(return_value=True)
        notifier.get_available_channels = MagicMock(
            return_value=[NotificationChannel.NTFY]
        )
        notifier.get_channels_for_route = MagicMock(
            side_effect=lambda route_type, *, channels: channels
        )
        notifier._has_context_channel = MagicMock(return_value=False)
        notifier.send_to_context = MagicMock(return_value=False)
        notifier.should_broadcast_static_channels = MagicMock(return_value=True)
        notifier.evaluate_noise_control = MagicMock(
            return_value=SimpleNamespace(
                should_send=True,
                reason_code="allowed",
                route_type="report",
                severity="info",
                message="",
            )
        )
        notifier.record_noise_control = MagicMock()
        notifier.release_noise_control = MagicMock()
        notifier.send_to_ntfy = MagicMock(return_value=True)

        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline._pipeline_stage_runner = PipelineStageRunner()
        pipeline.notifier = notifier
        pipeline.config = SimpleNamespace(stock_email_groups=[])
        pipeline._refresh_saved_diagnostic_snapshot = MagicMock()

        save_output = pipeline._save_local_report([result], ReportType.SIMPLE)
        dispatch_output = pipeline._send_notifications(
            [result],
            ReportType.SIMPLE,
        )

    assert save_output is None
    assert dispatch_output is None
    notifier.save_report_to_file.assert_called_once_with(expected)
    notifier.send_to_ntfy.assert_called_once_with(expected)
