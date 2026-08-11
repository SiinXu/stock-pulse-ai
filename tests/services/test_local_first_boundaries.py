"""Structured local-only misses at service, API, pipeline, and scheduler boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.v1.endpoints.analysis import _handle_sync_analysis
from api.v1.endpoints.stocks import get_stock_history
from api.v1.schemas.analysis import AnalyzeRequest
from data_provider.base import DataFetcherManager
from data_provider.daily_cache import (
    DailyCacheConfig,
    DailyDataCache,
    LocalDataMissing,
    LocalDataMissingError,
    MarketDataFetchMode,
)
from src.app import runtime
from src.app.analysis import run_full_analysis
from src.core.stages.orchestration import _OrchestrationStageMixin
from src.services.analysis_service import AnalysisService
from src.services.stock_service import StockService
from src.services.task_queue import AnalysisTaskQueue, KnownTaskFailure
from src.task_execution import TaskCommand, TaskStatusEnum


def _missing_error() -> LocalDataMissingError:
    return LocalDataMissingError(
        LocalDataMissing(
            symbol="600519",
            start_date="2026-07-01",
            end_date="2026-07-20",
            days=30,
            fields=("volume",),
            missing_ranges=(("2026-07-01", "2026-07-09"),),
            mode="local_only",
            reason="missing_fields_and_ranges",
            available_start_date="2026-07-10",
            available_end_date="2026-07-20",
            age_seconds=12,
        )
    )


def test_pipeline_fetch_boundary_preserves_local_missing_type() -> None:
    fetcher = MagicMock()
    fetcher.get_stock_name.return_value = "Kweichow Moutai"
    fetcher.get_daily_data.side_effect = _missing_error()
    stage = object.__new__(_OrchestrationStageMixin)
    stage.fetcher_manager = fetcher
    stage.db = MagicMock()
    stage.db.has_today_data.return_value = False
    stage._resolve_resume_target_date = MagicMock(return_value="2026-07-20")

    with pytest.raises(LocalDataMissingError) as exc_info:
        stage.fetch_and_save_stock_data("600519")

    assert exc_info.value.to_dict()["fields"] == ["volume"]
    stage.db.save_daily_data.assert_not_called()


def test_mixed_batch_propagates_local_missing_before_notifications() -> None:
    stage = object.__new__(_OrchestrationStageMixin)
    stage.max_workers = 2
    stage.fetcher_manager = MagicMock()
    stage.config = SimpleNamespace(
        single_stock_notify=False,
        report_type="simple",
        analysis_delay=0,
    )
    stage.db = MagicMock()
    stage._activate_delivery_diagnostic_context = MagicMock()

    def _process(code, **_kwargs):  # type: ignore[no-untyped-def]
        if code == "COLD":
            raise _missing_error()
        return SimpleNamespace(success=True, code=code)

    stage._process_single_stock_for_batch = MagicMock(side_effect=_process)

    with pytest.raises(LocalDataMissingError):
        stage.run(
            stock_codes=["WARM", "COLD"],
            dry_run=False,
            send_notification=True,
        )

    stage._activate_delivery_diagnostic_context.assert_not_called()


def test_five_symbol_local_only_pipeline_never_enters_provider_or_socket_path(
    tmp_path,
) -> None:
    socket_probe = MagicMock()

    class _OutboundProvider:
        name = "TickFlowFetcher"
        priority = 0
        kline_adjust = "none"

        def _outbound(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            socket_probe()
            raise AssertionError("local_only must not enter provider callbacks")

        get_daily_data = _outbound
        get_stock_name = _outbound
        prefetch_daily_klines = _outbound
        prefetch_realtime_quotes = _outbound

    manager = DataFetcherManager(fetchers=[_OutboundProvider()])
    manager._daily_data_cache = DailyDataCache(
        DailyCacheConfig(
            enabled=True,
            directory=tmp_path,
            fetch_mode=MarketDataFetchMode.LOCAL_ONLY,
            local_only_max_age_seconds=300.0,
        )
    )
    stage = object.__new__(_OrchestrationStageMixin)
    stage.max_workers = 2
    stage.fetcher_manager = manager
    stage.config = SimpleNamespace(
        single_stock_notify=False,
        report_type="simple",
        analysis_delay=0,
    )
    stage._activate_delivery_diagnostic_context = MagicMock()

    def _process(code, **_kwargs):  # type: ignore[no-untyped-def]
        assert manager.get_stock_name(code, allow_realtime=False) == ""
        manager.get_daily_data(
            code,
            start_date="2026-07-01",
            end_date="2026-07-20",
            days=30,
        )

    stage._process_single_stock_for_batch = _process

    with pytest.raises(LocalDataMissingError):
        stage.run(
            stock_codes=["600991", "600992", "600993", "600994", "600995"],
            dry_run=False,
            send_notification=True,
        )

    socket_probe.assert_not_called()
    stage._activate_delivery_diagnostic_context.assert_not_called()


def test_analysis_service_preserves_structured_local_missing_details() -> None:
    service = object.__new__(AnalysisService)
    service.repo = MagicMock()
    service.last_error = None
    service.last_error_code = None
    service.last_error_details = None
    pipeline = MagicMock()
    pipeline.process_single_stock.side_effect = _missing_error()

    with patch("src.config.get_config", return_value=SimpleNamespace()), patch(
        "src.core.pipeline.StockAnalysisPipeline", return_value=pipeline
    ):
        result = AnalysisService.analyze_stock(service, "600519", query_id="q-local")

    assert result is None
    assert service.last_error_code == "local_market_data_missing"
    assert service.last_error_details["missing_ranges"] == [
        {"start_date": "2026-07-01", "end_date": "2026-07-09"}
    ]


def test_async_analysis_command_preserves_local_missing_details() -> None:
    service = MagicMock(spec=AnalysisService)
    service.analyze_stock.return_value = None
    service.last_error = str(_missing_error())
    service.last_error_code = "local_market_data_missing"
    service.last_error_details = _missing_error().to_dict()
    context = SimpleNamespace(
        command=SimpleNamespace(
            metadata={
                "stock_code": "600519",
                "report_type": "detailed",
            }
        ),
        task_id="task-local",
        trace_id="trace-local",
        update_progress=MagicMock(),
    )
    queue = object.__new__(AnalysisTaskQueue)

    with patch("src.services.analysis_service.AnalysisService", return_value=service):
        with pytest.raises(KnownTaskFailure) as exc_info:
            AnalysisTaskQueue._run_analysis_command(queue, context)

    assert exc_info.value.error_code == "local_market_data_missing"
    assert exc_info.value.message_params["fields"] == ["volume"]


def test_async_task_terminal_state_preserves_local_missing_code_and_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(AnalysisTaskQueue, "_instance", None)
    queue = AnalysisTaskQueue(max_workers=1, inflight_store=MagicMock())
    details = _missing_error().to_dict()

    def _run(_context):  # type: ignore[no-untyped-def]
        raise KnownTaskFailure(
            "local_market_data_missing",
            str(_missing_error()),
            message_params=details,
        )

    try:
        task_id = queue.submit(
            TaskCommand(
                kind="stock_analysis",
                run=_run,
                metadata={
                    "stock_code": "600519",
                    "message": "任务已加入队列",
                    "message_code": "task.queued",
                },
                failure_error_code="analysis_failed",
                none_is_success=False,
            )
        )
        queue._futures[task_id].result(timeout=2)
        task = queue.get_task(task_id)
    finally:
        queue.shutdown()

    assert task is not None
    assert task.status is TaskStatusEnum.FAILED
    assert task.error == "local_market_data_missing"
    assert task.message_code == "local_market_data_missing"
    assert task.message_params["missing_ranges"] == details["missing_ranges"]
    assert task.to_dict()["message"] == (
        "Local market data does not cover the requested analysis window"
    )


def test_sync_analysis_api_returns_structured_409() -> None:
    service = MagicMock(spec=AnalysisService)
    service.analyze_stock.return_value = None
    service.last_error = str(_missing_error())
    service.last_error_code = "local_market_data_missing"
    service.last_error_details = _missing_error().to_dict()

    with patch("src.services.analysis_service.AnalysisService", return_value=service):
        with pytest.raises(HTTPException) as exc_info:
            _handle_sync_analysis(
                "600519",
                AnalyzeRequest(stock_code="600519", async_mode=False),
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "local_market_data_missing"
    assert exc_info.value.detail["details"]["fields"] == ["volume"]


def test_history_service_and_api_do_not_collapse_local_missing() -> None:
    manager = MagicMock()
    manager.get_daily_data.side_effect = _missing_error()
    service = StockService()

    with patch("data_provider.base.DataFetcherManager", return_value=manager):
        with pytest.raises(LocalDataMissingError):
            service.get_history_data("600519", days=30)

    endpoint_service = MagicMock()
    endpoint_service.get_history_data.side_effect = _missing_error()
    with patch("api.v1.endpoints.stocks.StockService", return_value=endpoint_service):
        with pytest.raises(HTTPException) as exc_info:
            get_stock_history("600519", period="daily", days=30)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["details"]["reason"] == "missing_fields_and_ranges"


def test_scheduled_analysis_boundary_propagates_local_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise _missing_error()

    monkeypatch.setattr(runtime, "run_full_analysis", _raise, raising=False)

    with pytest.raises(LocalDataMissingError):
        runtime.run_scheduled_analysis(SimpleNamespace(), SimpleNamespace())


def test_standalone_cli_scheduler_uses_raising_analysis_entrypoint() -> None:
    runtime_config = SimpleNamespace()
    config = SimpleNamespace(
        schedule_time="18:00",
        schedule_run_immediately=True,
        agent_event_monitor_enabled=False,
        daily_brief_enabled=False,
    )
    args = SimpleNamespace(no_run_immediately=False)

    def _run_schedule(*, task, **_kwargs):  # type: ignore[no-untyped-def]
        task()

    with patch("src.scheduler.run_with_schedule", side_effect=_run_schedule), patch(
        "src.services.task_queue.get_task_queue"
    ) as get_task_queue, patch.object(
        runtime,
        "_reload_runtime_config",
        return_value=runtime_config,
    ), patch.object(
        runtime,
        "run_scheduled_analysis",
        side_effect=_missing_error(),
    ) as run_scheduled:
        with pytest.raises(LocalDataMissingError):
            runtime._run_schedule_mode(
                config,
                args,
                ["600519"],
                start_serve=False,
            )

    get_task_queue.return_value.recover_persisted_inflight.assert_called_once_with()
    run_scheduled.assert_called_once_with(runtime_config, args, None)


def test_cli_analysis_emits_structured_failure_without_notification() -> None:
    pipeline = MagicMock()
    pipeline.notifier = MagicMock()
    pipeline.run.side_effect = _missing_error()
    config = SimpleNamespace(
        market_review_enabled=False,
        market_review_region="cn",
        single_stock_notify=False,
        merge_email_notification=False,
    )
    args = SimpleNamespace(
        portfolio=None,
        single_notify=False,
        no_market_review=True,
        no_context_snapshot=False,
        workers=1,
        dry_run=False,
        no_notify=False,
    )

    with patch("src.app.analysis._refresh_stock_index_cache_for_analysis"), patch(
        "src.app.analysis._compute_trading_day_filter",
        return_value=(["600519"], None, False),
    ), patch("src.core.pipeline.StockAnalysisPipeline", return_value=pipeline), patch(
        "src.services.actions_daily_run_summary.write_run_status"
    ) as write_status:
        result = run_full_analysis(config, args, ["600519"])

    assert result is False
    status = write_status.call_args.args[0]
    assert status.primary_code == "local_market_data_missing"
    assert status.extra["local_data_missing"]["reason"] == "missing_fields_and_ranges"
    pipeline.notifier.send.assert_not_called()
