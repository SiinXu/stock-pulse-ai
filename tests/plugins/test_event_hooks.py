# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Runtime and lifecycle contracts for observational plugin event hooks."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.core.market_review import run_market_review
from src.core.pipeline import StockAnalysisPipeline
from src.enums import ReportType
from src.plugins import (
    EVENT_HOOK_NAMES,
    EVENT_HOOK_SCHEMA_VERSION,
    EventHookRegistration,
    Plugin,
    PluginContext,
    PluginEvent,
    PluginManifest,
    dispatch_analysis_event,
)


def _manifest(plugin_id: str) -> PluginManifest:
    return PluginManifest.model_validate(
        {
            "id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "minAppVersion": "1.0.0",
            "description": "Event hook plugin test.",
            "author": "StockPulse Tests",
            "permissions": [],
        }
    )


class _HookPlugin(Plugin):
    def __init__(
        self,
        plugin_id: str,
        hook_id: str,
        event_names: frozenset[str],
        callback,
        *,
        priority: int = 100,
    ) -> None:
        super().__init__(_manifest(plugin_id))
        self.registration = EventHookRegistration(
            hook_id=hook_id,
            event_names=event_names,
            callback=callback,
        )
        self.priority = priority
        self.unload_count = 0

    def onload(self, context: PluginContext) -> None:
        context.register(
            "event_hook",
            self.registration.hook_id,
            self.registration,
            priority=self.priority,
        )

    def onunload(self) -> None:
        self.unload_count += 1


@pytest.fixture(autouse=True)
def _clean_application_root():
    reset_application_services()
    yield
    reset_application_services()


def _install_plugins(*plugins: Plugin) -> ApplicationServices:
    services = ApplicationServices(
        builtin_plugins=plugins,
        plugins_dir="",
    )
    set_application_services(services)
    return services


def _pipeline(result: object) -> StockAnalysisPipeline:
    pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
    pipeline.query_id = "analysis-task"
    pipeline.trace_id = "analysis-trace"
    pipeline.query_source = "api"
    pipeline._emit_progress = MagicMock()
    pipeline._resolve_resume_target_date = MagicMock(return_value=date(2026, 7, 24))
    pipeline.fetch_and_save_stock_data = MagicMock(return_value=(True, None))
    pipeline.analyze_stock = MagicMock(return_value=result)
    pipeline._refresh_saved_diagnostic_snapshot = MagicMock()
    return pipeline


def _notifier() -> MagicMock:
    notifier = MagicMock()
    notifier.is_available.return_value = False
    return notifier


def test_contract_accepts_exactly_the_six_initial_event_names() -> None:
    assert EVENT_HOOK_NAMES == {
        "analysis.started",
        "analysis.completed",
        "analysis.failed",
        "market_review.started",
        "market_review.completed",
        "market_review.failed",
    }

    invalid = _HookPlugin(
        "event.invalid",
        "invalid-hook",
        frozenset({"analysis.started", "analysis.retried"}),
        lambda event: None,
    )
    services = _install_plugins(invalid)

    assert services.plugin_load_results[0].success is False
    assert services.plugin_load_results[0].error_code == "extension_implementation_invalid"
    assert services.plugin_manager.registrations("event_hook") == ()


def test_priority_failure_isolation_sanitization_and_immutable_snapshot(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[str] = []
    captured: list[PluginEvent] = []

    def failing_callback(event: PluginEvent) -> None:
        captured.append(event)
        with pytest.raises(TypeError):
            event.payload["stock_code"] = "MUTATED"  # type: ignore[index]
        raise RuntimeError("api_key=callback-secret")

    _install_plugins(
        _HookPlugin(
            "event.late",
            "late-hook",
            frozenset({"analysis.started"}),
            lambda event: calls.append("late"),
            priority=100,
        ),
        _HookPlugin(
            "event.failing",
            "failing-hook",
            frozenset({"analysis.started"}),
            failing_callback,
            priority=10,
        ),
        _HookPlugin(
            "event.equal",
            "equal-hook",
            frozenset({"analysis.started"}),
            lambda event: calls.append("equal"),
            priority=10,
        ),
    )

    with caplog.at_level(logging.WARNING, logger="src.plugins.event_hooks"):
        dispatch_analysis_event(
            "analysis.started",
            task_id="task-1",
            trace_id="trace-1",
            stock_code="AAPL",
            trigger_source="api_key=payload-secret",
        )

    assert calls == ["equal", "late"]
    assert len(captured) == 1
    assert captured[0].schema_version == EVENT_HOOK_SCHEMA_VERSION
    assert captured[0].payload == {
        "task_id": "task-1",
        "stock_code": "AAPL",
        "trigger_source": "api_key=[REDACTED]",
    }
    assert "plugin_event_hook_callback_failed" in caplog.text
    assert "callback-secret" not in caplog.text
    assert "payload-secret" not in str(dict(captured[0].payload))

    source = {"nested": {"items": [1, 2]}}
    detached = PluginEvent(
        name="analysis.started",
        schema_version=EVENT_HOOK_SCHEMA_VERSION,
        occurred_at=datetime.now(timezone.utc),
        trace_id="trace-2",
        payload=source,
    )
    source["nested"]["items"].append(3)  # type: ignore[index,union-attr]
    assert detached.payload["nested"]["items"] == (1, 2)  # type: ignore[index]
    with pytest.raises(TypeError):
        detached.payload["nested"]["new"] = True  # type: ignore[index]


def test_duplicate_hook_id_fails_closed_and_disable_removes_registration() -> None:
    first_calls: list[str] = []
    second_calls: list[str] = []
    first = _HookPlugin(
        "event.first",
        "shared-hook",
        frozenset({"analysis.started"}),
        lambda event: first_calls.append(event.name),
    )
    second = _HookPlugin(
        "event.second",
        "shared-hook",
        frozenset({"analysis.started"}),
        lambda event: second_calls.append(event.name),
    )
    services = _install_plugins(first, second)

    assert services.plugin_load_results[0].success is True
    assert services.plugin_load_results[1].success is False
    assert services.plugin_load_results[1].error_code == "extension_registration_conflict"

    dispatch_analysis_event(
        "analysis.started",
        task_id="task-1",
        trace_id="trace-1",
        stock_code="AAPL",
        trigger_source="api",
    )
    assert first_calls == ["analysis.started"]
    assert second_calls == []

    disabled = services.plugin_manager.disable("event.first")
    assert disabled.success is True
    assert first.unload_count == 1
    dispatch_analysis_event(
        "analysis.started",
        task_id="task-2",
        trace_id="trace-2",
        stock_code="MSFT",
        trigger_source="api",
    )
    assert first_calls == ["analysis.started"]
    assert services.plugin_manager.registrations("event_hook") == ()


def test_analysis_and_market_review_emit_all_six_events_at_real_boundaries() -> None:
    events: list[PluginEvent] = []
    _install_plugins(
        _HookPlugin(
            "event.observer",
            "observer-hook",
            frozenset(EVENT_HOOK_NAMES),
            events.append,
        )
    )

    succeeded = SimpleNamespace(
        code="AAPL",
        query_id="analysis-success",
        success=True,
        sentiment_score=70,
    )
    failed = SimpleNamespace(
        code="MSFT",
        query_id="analysis-failure",
        success=False,
    )
    _pipeline(succeeded).process_single_stock(
        "AAPL",
        report_type=ReportType.SIMPLE,
        analysis_query_id="analysis-success",
    )
    _pipeline(failed).process_single_stock(
        "MSFT",
        report_type=ReportType.SIMPLE,
        analysis_query_id="analysis-failure",
    )

    successful_market_analyzer = MagicMock()
    successful_market_analyzer.run_daily_review_with_snapshot.return_value = SimpleNamespace(
        report="Market review body",
        market_light_snapshot={},
    )
    failed_market_analyzer = MagicMock()
    failed_market_analyzer.run_daily_review_with_snapshot.side_effect = RuntimeError(
        "market provider failed"
    )
    config = SimpleNamespace(report_language="en", market_review_region="us")
    with patch(
        "src.core.market_review.MarketAnalyzer",
        return_value=successful_market_analyzer,
    ):
        market_result = run_market_review(
            _notifier(),
            config=config,
            send_notification=False,
            query_id="market-success",
            save_report_file=False,
            persist_history=False,
            trigger_source="api",
        )
    with patch(
        "src.core.market_review.MarketAnalyzer",
        return_value=failed_market_analyzer,
    ):
        failed_market_result = run_market_review(
            _notifier(),
            config=config,
            send_notification=False,
            query_id="market-failure",
            save_report_file=False,
            persist_history=False,
            trigger_source="api",
        )

    assert market_result == "Market review body"
    assert failed_market_result is None
    assert [event.name for event in events] == [
        "analysis.started",
        "analysis.completed",
        "analysis.started",
        "analysis.failed",
        "market_review.started",
        "market_review.completed",
        "market_review.started",
        "market_review.failed",
    ]
    assert events[0].payload == {
        "task_id": "analysis-success",
        "stock_code": "AAPL",
        "trigger_source": "api",
    }
    assert events[1].payload["terminal_status"] == "completed"
    assert events[3].payload["error_code"] == "analysis_failed"
    assert events[4].payload["market_region"] == "us"
    assert events[5].payload["result_reference"] == "market-success"
    assert events[7].payload["error_code"] == "market_review_execution_failed"
    assert all("report" not in event.payload for event in events)


def test_resolve_rejection_emits_no_started_or_terminal_analysis_event() -> None:
    events: list[PluginEvent] = []
    _install_plugins(
        _HookPlugin(
            "event.admission",
            "admission-hook",
            frozenset(EVENT_HOOK_NAMES),
            events.append,
        )
    )
    pipeline = _pipeline(SimpleNamespace(success=True))
    pipeline._resolve_resume_target_date.side_effect = RuntimeError("not admitted")

    with pytest.raises(RuntimeError, match="not admitted"):
        pipeline.process_single_stock("AAPL", analysis_query_id="rejected-task")

    assert events == []
