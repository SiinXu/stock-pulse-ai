# -*- coding: utf-8 -*-
"""First-run failure UX: stable llm_not_configured and setup/region guidance.

CI re-request marker for inventory refresh follow-up.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.v1.endpoints.analysis import _handle_sync_analysis, trigger_market_review
from api.v1.schemas.analysis import AnalyzeRequest, MarketReviewRequest
from src.services.analysis_service import (
    AnalysisService,
    LLM_NOT_CONFIGURED_ERROR_CODE,
    is_llm_not_configured_error,
)
from src.services.run_flow import build_task_run_flow_snapshot
from src.services.task_queue import AnalysisTaskQueue, TaskInfo, TaskStatus
from src.utils.market_review_region import MARKET_REVIEW_REGION_VALID_INPUTS


def test_is_llm_not_configured_error_detects_known_markers_only() -> None:
    assert is_llm_not_configured_error(LLM_NOT_CONFIGURED_ERROR_CODE, None)
    assert is_llm_not_configured_error(None, "LLM API Key 未配置")
    assert is_llm_not_configured_error(None, "LLM API key is not configured")
    assert not is_llm_not_configured_error(None, "upstream timeout from provider")
    assert not is_llm_not_configured_error("analysis_failed", "generic failure")


def test_sync_analyze_maps_missing_llm_to_422_llm_not_configured() -> None:
    service = MagicMock(spec=AnalysisService)
    service.analyze_stock.return_value = None
    service.last_error = "LLM API Key 未配置"
    service.last_error_code = LLM_NOT_CONFIGURED_ERROR_CODE

    with patch(
        "src.services.analysis_service.AnalysisService",
        return_value=service,
    ):
        with pytest.raises(HTTPException) as exc_info:
            _handle_sync_analysis("600519", AnalyzeRequest(stock_code="600519", async_mode=False))

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["error"] == LLM_NOT_CONFIGURED_ERROR_CODE
    assert detail["params"]["stock_code"] == "600519"


def test_sync_analyze_keeps_generic_500_when_llm_is_configured_path_fails() -> None:
    service = MagicMock(spec=AnalysisService)
    service.analyze_stock.return_value = None
    service.last_error = "upstream model returned 500"
    service.last_error_code = None

    with patch(
        "src.services.analysis_service.AnalysisService",
        return_value=service,
    ):
        with pytest.raises(HTTPException) as exc_info:
            _handle_sync_analysis("600519", AnalyzeRequest(stock_code="600519", async_mode=False))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["error"] == "analysis_failed"


def test_analysis_service_captures_error_code_from_failed_result() -> None:
    service = object.__new__(AnalysisService)
    service.repo = MagicMock()
    service.last_error = None
    service.last_error_code = None

    failed = SimpleNamespace(
        success=False,
        error_message="LLM API key is not configured",
        error_code=LLM_NOT_CONFIGURED_ERROR_CODE,
    )
    pipeline = MagicMock()
    pipeline.process_single_stock.return_value = failed

    with patch("src.config.get_config", return_value=SimpleNamespace()), \
         patch("src.core.pipeline.StockAnalysisPipeline", return_value=pipeline):
        result = AnalysisService.analyze_stock(service, "600519", query_id="q-llm")

    assert result is None
    assert service.last_error_code == LLM_NOT_CONFIGURED_ERROR_CODE


def test_analysis_service_success_path_does_not_set_error_code() -> None:
    service = object.__new__(AnalysisService)
    service.repo = MagicMock()
    service.last_error = "stale"
    service.last_error_code = "stale"

    pipeline = MagicMock()
    pipeline.process_single_stock.return_value = object()

    with patch("src.config.get_config", return_value=SimpleNamespace()), \
         patch("src.core.pipeline.StockAnalysisPipeline", return_value=pipeline), \
         patch.object(
             AnalysisService,
             "_build_analysis_response",
             return_value={"stock_code": "600519"},
         ):
        result = AnalysisService.analyze_stock(service, "600519", query_id="q-ok")

    assert result == {"stock_code": "600519"}
    assert service.last_error is None
    assert service.last_error_code is None


def test_async_task_failure_records_llm_not_configured_message_code() -> None:
    class _SyncExecutor:
        def submit(self, fn, *args, **kwargs):
            future: Future = Future()
            try:
                future.set_result(fn(*args, **kwargs))
            except Exception as exc:  # pragma: no cover - asserted via task state
                future.set_exception(exc)
            return future

        def shutdown(self, wait=True, cancel_futures=False) -> None:
            del wait, cancel_futures

    async def run_scenario():
        queue = AnalysisTaskQueue(max_workers=1)
        queue._executor = _SyncExecutor()

        def fail_llm() -> None:
            from src.services.task_queue import KnownTaskFailure

            raise KnownTaskFailure(LLM_NOT_CONFIGURED_ERROR_CODE, "LLM API Key 未配置")

        accepted = queue.submit_background_task(
            fail_llm,
            stock_code="600519",
            failure_error_code="analysis_failed",
        )
        await asyncio.sleep(0)
        return queue, accepted

    original = AnalysisTaskQueue._instance
    AnalysisTaskQueue._instance = None
    try:
        queue, accepted = asyncio.run(run_scenario())
    finally:
        current = AnalysisTaskQueue._instance
        if current is not None:
            current.shutdown()
        AnalysisTaskQueue._instance = original

    failed = queue.get_task(accepted.task_id)
    assert failed is not None
    assert failed.status == TaskStatus.FAILED
    assert failed.error == LLM_NOT_CONFIGURED_ERROR_CODE
    assert failed.message_code == LLM_NOT_CONFIGURED_ERROR_CODE
    assert failed.failure_error_code == LLM_NOT_CONFIGURED_ERROR_CODE


def test_run_flow_failed_node_carries_llm_not_configured_code() -> None:
    task = TaskInfo(
        task_id="task-llm",
        stock_code="600519",
        status=TaskStatus.FAILED,
        message="No LLM model is configured",
        message_code=LLM_NOT_CONFIGURED_ERROR_CODE,
        failure_error_code=LLM_NOT_CONFIGURED_ERROR_CODE,
        error=LLM_NOT_CONFIGURED_ERROR_CODE,
    )
    snapshot = build_task_run_flow_snapshot(task)
    queue_node = next(node for node in snapshot.nodes if node.id == "task_queue")
    assert queue_node.status == "failed"
    assert queue_node.message == LLM_NOT_CONFIGURED_ERROR_CODE
    assert queue_node.metadata.get("error") == LLM_NOT_CONFIGURED_ERROR_CODE
    assert queue_node.metadata.get("message_code") == LLM_NOT_CONFIGURED_ERROR_CODE


def test_market_review_invalid_region_includes_allowed_set() -> None:
    config = SimpleNamespace(market_review_region="cn", report_language="zh")
    with pytest.raises(HTTPException) as exc_info:
        trigger_market_review(
            request=MarketReviewRequest(region="mars"),
            config=config,
        )

    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["error"] == "validation_error"
    message = detail["message"]
    for token in MARKET_REVIEW_REGION_VALID_INPUTS:
        assert token in message
        assert token in detail["params"]["allowed"]
