# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression tests for task message identity carried by SSE and polling."""

import asyncio
import json
from concurrent.futures import Future

from src.services.task_queue import (
    AnalysisTaskQueue,
    TaskInfo,
    TaskStatus,
    _task_message_metadata,
)
from src.task_execution import TaskEventType, deep_thaw


def test_task_info_serializes_message_code_and_params() -> None:
    task = TaskInfo(
        task_id="task-1",
        stock_code="600519",
        status=TaskStatus.PROCESSING,
        message="贵州茅台：正在检索新闻与舆情",
        message_code="task.analysis.news",
        message_params={"subject": "贵州茅台"},
    )

    payload = task.to_dict()
    assert payload["message_code"] == "task.analysis.news"
    assert payload["message_params"] == {"subject": "贵州茅台"}

    copied = task.copy()
    copied.message_params["subject"] = "changed"
    assert task.message_params == {"subject": "贵州茅台"}


def test_legacy_pipeline_copy_maps_to_stable_message_identity() -> None:
    code, params = _task_message_metadata(
        "AAPL：正在请求 LLM 生成报告",
        fallback_code="task.processing",
    )

    assert code == "task.analysis.llm"
    assert params == {"subject": "AAPL"}


def test_background_failure_keeps_diagnostic_exception_out_of_public_payload() -> None:
    secret_marker = "api_key=sk-task-secret-marker"

    class _SyncExecutor:
        def submit(self, fn, *args, **kwargs):
            future = Future()
            try:
                future.set_result(fn(*args, **kwargs))
            except Exception as exc:  # pragma: no cover - asserted through task state
                future.set_exception(exc)
            return future

        def shutdown(self, wait=True, cancel_futures=False) -> None:
            del wait, cancel_futures

    def fail_task() -> None:
        raise RuntimeError(secret_marker)

    async def run_scenario():
        queue = AnalysisTaskQueue(max_workers=1)
        queue._executor = _SyncExecutor()
        stream = queue.subscribe_all()
        try:
            accepted = queue.submit_background_task(
                fail_task,
                stock_code="market_review",
                failure_error_code="analysis_failed",
            )
            await asyncio.sleep(0)
            events = [await stream.receive(timeout=1) for _ in range(3)]
            return queue, accepted, events
        finally:
            await stream.aclose()

    original_queue = AnalysisTaskQueue._instance
    AnalysisTaskQueue._instance = None
    try:
        queue, accepted, events = asyncio.run(run_scenario())
    finally:
        current_queue = AnalysisTaskQueue._instance
        if current_queue is not None:
            current_queue.shutdown()
        AnalysisTaskQueue._instance = original_queue

    failed = queue.get_task(accepted.task_id)
    assert failed is not None
    assert failed.status == TaskStatus.FAILED
    assert failed.error == "analysis_failed"
    assert failed.message == "任务执行失败"
    assert failed.message_code == "task.failed"
    assert failed.diagnostic_error == "RuntimeError: [REDACTED]"
    assert secret_marker not in failed.diagnostic_error

    public_payload = failed.to_dict()
    assert public_payload["error"] == "analysis_failed"
    assert secret_marker not in json.dumps(public_payload, ensure_ascii=False)

    failed_event = next(event for event in events if event.type == TaskEventType.FAILED)
    failed_payload = deep_thaw(failed_event.data)
    assert failed_payload["error"] == "analysis_failed"
    assert secret_marker not in json.dumps(failed_payload, ensure_ascii=False)


def test_failed_task_public_payload_sanitizes_legacy_raw_error_fields() -> None:
    secret_marker = "Authorization: Bearer sk-legacy-task-secret"
    task = TaskInfo(
        task_id="legacy-failed-task",
        stock_code="600519",
        status=TaskStatus.FAILED,
        message=f"分析失败: {secret_marker}",
        message_code="task.analysis.failed",
        error=secret_marker,
        failure_error_code="analysis_failed",
    )

    public_payload = task.to_dict()

    assert public_payload["error"] == "analysis_failed"
    assert public_payload["message"] == "分析失败"
    assert secret_marker not in json.dumps(public_payload, ensure_ascii=False)
