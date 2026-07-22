# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression tests for AnalyzeCommand migrating to the unified task authority.

These tests exercise the real ``AnalysisTaskQueue`` (only its thread pool is
replaced by a synchronous executor) so the Bot submission genuinely flows
through submit -> command closure -> runner. The runner boundary is asserted to
prove the Bot keeps the same task source, dedupe, report type and contextual
reply targets (push destination) as the API path, instead of mocking the queue
away.
"""

from __future__ import annotations

from concurrent.futures import Future
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    from tests.litellm_stub import ensure_litellm_stub

    ensure_litellm_stub()

from bot.application_context import to_analysis_request_context
from bot.commands.analyze import AnalyzeCommand
from bot.models import BotMessage, ChatType
from src.services.task_queue import AnalysisTaskQueue, DuplicateTaskError, TaskStatus


class _SyncExecutor:
    """Run submitted callables inline so the command completes deterministically."""

    def submit(self, fn, *args, **kwargs):
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:  # pragma: no cover - surfaced via task state
            future.set_exception(exc)
        return future

    def shutdown(self, wait=True, cancel_futures=False) -> None:
        del wait, cancel_futures


def _feishu_message(content: str) -> BotMessage:
    return BotMessage(
        platform="feishu",
        message_id="m1",
        user_id="u1",
        user_name="tester",
        chat_id="chat-1",
        chat_type=ChatType.PRIVATE,
        content=content,
        raw_content=content,
        mentioned=True,
        timestamp=datetime.now(),
    )


def _run_execute_with_real_queue(message: BotMessage, args, analyze_result):
    """Execute AnalyzeCommand against a real, inline-executing queue.

    Returns (response, queue, analyze_stock_mock).
    """
    original_instance = AnalysisTaskQueue._instance
    AnalysisTaskQueue._instance = None
    try:
        queue = AnalysisTaskQueue(max_workers=1)
        queue._executor = _SyncExecutor()

        service_instance = MagicMock()
        service_instance.analyze_stock.return_value = analyze_result

        with patch(
            "src.services.task_queue.get_task_queue",
            return_value=queue,
        ), patch(
            "src.services.analysis_service.AnalysisService",
            return_value=service_instance,
        ):
            response = AnalyzeCommand().execute(message, args)
        return response, queue, service_instance.analyze_stock
    finally:
        current = AnalysisTaskQueue._instance
        if current is not None and current is not original_instance:
            current.shutdown()
        AnalysisTaskQueue._instance = original_instance


def test_execute_submits_through_unified_queue_with_bot_context() -> None:
    message = _feishu_message("/analyze 600519")
    response, queue, analyze_stock = _run_execute_with_real_queue(
        message,
        ["600519"],
        {"query_id": "q1", "stock_code": "600519"},
    )

    # The Bot submitted exactly one task through the unified queue.
    tasks = queue.list_all_tasks()
    assert len(tasks) == 1
    task = tasks[0]
    assert task.query_source == "bot"
    assert task.stock_code == "600519"
    assert task.status == TaskStatus.COMPLETED

    # The runner received the Bot's report type, source and reply context.
    analyze_stock.assert_called_once()
    kwargs = analyze_stock.call_args.kwargs
    assert kwargs["report_type"] == "simple"
    assert kwargs["query_source"] == "bot"
    expected_context = to_analysis_request_context(message)
    assert kwargs["request_context"] == expected_context
    # Push destination is preserved: the Feishu reply target survives migration.
    assert kwargs["request_context"].reply_address("feishu") == "chat-1"

    # User-visible success copy stays equivalent to the legacy path.
    assert response.markdown is True
    assert "分析任务已提交" in response.text
    assert "股票代码: `600519`" in response.text
    assert "市场 / Market: A 股 (CN) / A-share" in response.text
    assert "报告类型: 精简报告" in response.text
    assert task.task_id[:20] in response.text


def test_execute_full_report_type_reaches_runner() -> None:
    message = _feishu_message("/analyze 600519 full")
    _response, _queue, analyze_stock = _run_execute_with_real_queue(
        message,
        ["600519", "full"],
        {"query_id": "q1", "stock_code": "600519"},
    )

    analyze_stock.assert_called_once()
    assert analyze_stock.call_args.kwargs["report_type"] == "full"
    assert "报告类型: 完整报告" in _response.text


def test_execute_duplicate_stock_returns_friendly_message() -> None:
    message = _feishu_message("/analyze 600519")
    queue = MagicMock()
    queue.submit_task.side_effect = DuplicateTaskError("600519", "existing-task-id")

    with patch("src.services.task_queue.get_task_queue", return_value=queue):
        response = AnalyzeCommand().execute(message, ["600519"])

    assert response.markdown is True
    assert response.text == (
        "⏳ **该股票正在分析中**\n\n"
        "• 股票代码: `600519`\n\n"
        "• 市场 / Market: A 股 (CN) / A-share\n\n"
        "请等待当前分析完成后再试。"
    )


def test_execute_generic_failure_returns_stable_error() -> None:
    message = _feishu_message("/analyze 600519")
    queue = MagicMock()
    queue.submit_task.side_effect = RuntimeError("boom")

    with patch("src.services.task_queue.get_task_queue", return_value=queue):
        response = AnalyzeCommand().execute(message, ["600519"])

    assert response.text == "❌ 错误：分析失败，请稍后重试"


@pytest.mark.parametrize(
    ("raw_code", "expected_code", "expected_market"),
    [
        ("600519", "600519", "A 股 (CN) / A-share"),
        ("00700.HK", "HK00700", "港股 (HK) / Hong Kong"),
        ("aapl", "AAPL", "美股 (US) / US stock"),
    ],
)
def test_execute_routes_three_markets_through_the_real_queue(
    raw_code: str,
    expected_code: str,
    expected_market: str,
) -> None:
    message = _feishu_message(f"/analyze {raw_code}")
    response, queue, analyze_stock = _run_execute_with_real_queue(
        message,
        [raw_code],
        {"query_id": "q1", "stock_code": expected_code},
    )

    tasks = queue.list_all_tasks()
    assert len(tasks) == 1
    assert tasks[0].stock_code == expected_code
    assert analyze_stock.call_args.kwargs["stock_code"] == expected_code
    assert f"股票代码: `{expected_code}`" in response.text
    assert f"市场 / Market: {expected_market}" in response.text


def test_validate_args_rejects_unsupported_market_with_actionable_guidance() -> None:
    message = AnalyzeCommand().validate_args(["7203.T"])

    assert message is not None
    assert "暂不支持日股" in message
    assert "does not currently support Japan stocks" in message
    assert "HK00700" in message


def test_execute_rejects_invalid_symbol_without_submitting_a_task() -> None:
    queue = MagicMock()

    with patch("src.services.task_queue.get_task_queue", return_value=queue):
        response = AnalyzeCommand().execute(
            _feishu_message("/analyze abc123"),
            ["abc123"],
        )

    assert "Unrecognized stock symbol" in response.text
    queue.submit_task.assert_not_called()


def test_execute_rejects_index_resolved_unsupported_market_without_submission() -> None:
    queue = MagicMock()

    with patch("src.services.task_queue.get_task_queue", return_value=queue):
        response = AnalyzeCommand().execute(
            _feishu_message("/analyze 005930"),
            ["005930"],
        )

    assert "does not currently support Korea stocks" in response.text
    queue.submit_task.assert_not_called()
