# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression tests for task message identity carried by SSE and polling."""

import json
from concurrent.futures import Future
from queue import Queue

from src.services.task_queue import (
    AnalysisTaskQueue,
    TaskInfo,
    TaskStatus,
    _task_message_metadata,
)


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

    class _ImmediateLoop:
        @staticmethod
        def call_soon_threadsafe(callback, *args) -> None:
            callback(*args)

    def fail_task() -> None:
        raise RuntimeError(secret_marker)

    queue = AnalysisTaskQueue(max_workers=1)
    queue._executor = _SyncExecutor()
    event_queue: Queue = Queue()
    queue._subscribers.append(event_queue)
    queue._main_loop = _ImmediateLoop()
    accepted = queue.submit_background_task(
        fail_task,
        stock_code="market_review",
        failure_error_code="analysis_failed",
    )

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

    events = []
    while not event_queue.empty():
        events.append(event_queue.get_nowait())
    failed_event = next(event for event in events if event["type"] == "task_failed")
    assert failed_event["data"]["error"] == "analysis_failed"
    assert secret_marker not in json.dumps(failed_event, ensure_ascii=False)


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
