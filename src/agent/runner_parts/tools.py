# -*- coding: utf-8 -*-
"""Tool execution function rebound through the legacy runner facade."""

from __future__ import annotations

import contextvars
import json
import logging
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
)
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.llm_adapter import ToolCall
from src.agent.runtime.guards import log_runtime_guard_event
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.stream_events import stream_event
from src.agent.tools.execution import (
    bind_runner_tool_completion_guard,
    execute_runner_tool_call_via_session,
)

if TYPE_CHECKING:
    from src.agent.runner import _ToolCompletionFence

logger = logging.getLogger("src.agent.runner")


def _execute_tools(
    tool_calls: List[ToolCall],
    tool_session: BoundToolSession,
    step: int,
    progress_callback: Optional[Callable],
    tool_calls_log: List[Dict[str, Any]],
    tool_wait_timeout_seconds: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Execute one or more tool calls, returning ordered result dicts.

    Single tools run inline; multiple tools run in parallel threads. Every
    dispatch flows through the bound ``tool_session`` — the single tool
    authority — via the migration mapper.
    """

    def _exec_single(tc_item, completion_fence=None):
        """Execute one tool with an optional per-dispatch completion fence."""
        if completion_fence is None:
            return execute_runner_tool_call_via_session(tc_item, tool_session)
        with bind_runner_tool_completion_guard(completion_fence.claim_completion):
            return execute_runner_tool_call_via_session(tc_item, tool_session)

    def _build_timeout_execution_result(tc_item):
        """Build and log the canonical result for one timed-out dispatch."""
        timeout_value = tool_wait_timeout_seconds or 0.0
        timeout_label = (
            f"{timeout_value:.2f}s"
            if tool_wait_timeout_seconds is not None
            else "the configured limit"
        )
        log_runtime_guard_event(
            logger,
            "tool_timeout",
            scope="tool",
            execution_id=tool_session.execution_id,
            tool=tc_item.name,
            step=step,
            limit_seconds=round(timeout_value, 3),
            action="result_fenced",
        )
        return (
            tc_item,
            json.dumps({
                "error": f"Tool execution timed out after {timeout_label}",
                "timeout": True,
            }),
            False,
            round(timeout_value, 2),
            False,
            None,
        )

    results: List[Dict[str, Any]] = []

    if len(tool_calls) == 1:
        tc = tool_calls[0]
        if progress_callback:
            progress_callback(stream_event("tool_start", step=step, tool=tc.name))
        timeout_triggered = False
        if tool_wait_timeout_seconds and tool_wait_timeout_seconds > 0:
            pool = ThreadPoolExecutor(max_workers=1)
            ctx = contextvars.copy_context()
            completion_fence = _ToolCompletionFence(tool_wait_timeout_seconds)
            try:
                future = pool.submit(ctx.run, _exec_single, tc, completion_fence)
                try:
                    execution_result = future.result(
                        timeout=tool_wait_timeout_seconds,
                    )
                except FuturesTimeoutError:
                    timeout_triggered = completion_fence.mark_timed_out()
                    if not timeout_triggered:
                        execution_result = future.result()
                else:
                    timeout_triggered = completion_fence.timed_out
                if timeout_triggered:
                    future.cancel()
                    execution_result = _build_timeout_execution_result(tc)
                (
                    _,
                    result_str,
                    success,
                    dur,
                    cached,
                    guard_result,
                ) = execution_result
            finally:
                pool.shutdown(wait=not timeout_triggered, cancel_futures=timeout_triggered)
        else:
            _, result_str, success, dur, cached, guard_result = _exec_single(tc)
        if progress_callback:
            progress_callback(stream_event("tool_done", step=step, tool=tc.name, success=success, duration=dur))
        log_entry = {
            "step": step, "tool": tc.name, "arguments": tc.arguments,
            "success": success, "duration": dur, "result_length": len(result_str),
            "cached": cached,
        }
        if tool_wait_timeout_seconds and tool_wait_timeout_seconds > 0 and not success:
            try:
                if json.loads(result_str).get("timeout") is True:
                    log_entry["timeout"] = True
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        if guard_result is not None:
            log_entry.update({
                "guarded": True,
                "expected_stock_code": guard_result.get("expected_stock_code"),
                "requested_stock_code": guard_result.get("requested_stock_code"),
                "allowed_stock_codes": guard_result.get("allowed_stock_codes", []),
            })
        tool_calls_log.append(log_entry)
        results.append({"tc": tc, "result_str": result_str})
    else:
        def _record_parallel_result(execution_result, *, timed_out=False):
            """Record one accepted parallel result in the existing output shape."""
            tc_item, result_str, success, dur, cached, guard_result = execution_result
            if progress_callback:
                progress_callback(stream_event(
                    "tool_done",
                    step=step,
                    tool=tc_item.name,
                    success=success,
                    duration=dur,
                ))
            log_entry = {
                "step": step,
                "tool": tc_item.name,
                "arguments": tc_item.arguments,
                "success": success,
                "duration": dur,
                "result_length": len(result_str),
                "cached": cached,
            }
            if timed_out:
                log_entry["timeout"] = True
            if guard_result is not None:
                log_entry.update({
                    "guarded": True,
                    "expected_stock_code": guard_result.get("expected_stock_code"),
                    "requested_stock_code": guard_result.get("requested_stock_code"),
                    "allowed_stock_codes": guard_result.get("allowed_stock_codes", []),
                })
            tool_calls_log.append(log_entry)
            results.append({"tc": tc_item, "result_str": result_str})

        for tc in tool_calls:
            if progress_callback:
                progress_callback(stream_event("tool_start", step=step, tool=tc.name))

        pool = ThreadPoolExecutor(max_workers=min(len(tool_calls), 5))
        timeout_triggered = False
        try:
            futures = {}
            for tc in tool_calls:
                completion_fence = (
                    _ToolCompletionFence(tool_wait_timeout_seconds)
                    if tool_wait_timeout_seconds and tool_wait_timeout_seconds > 0
                    else None
                )
                future = pool.submit(
                    contextvars.copy_context().run,
                    _exec_single,
                    tc,
                    completion_fence,
                )
                futures[future] = (tc, completion_fence)
            pending = set(futures)
            for future in as_completed(
                futures,
                timeout=tool_wait_timeout_seconds if tool_wait_timeout_seconds and tool_wait_timeout_seconds > 0 else None,
            ):
                pending.discard(future)
                tc_item, completion_fence = futures[future]
                execution_result = future.result()
                if completion_fence is not None and completion_fence.timed_out:
                    timeout_triggered = True
                    execution_result = _build_timeout_execution_result(tc_item)
                    _record_parallel_result(execution_result, timed_out=True)
                else:
                    _record_parallel_result(execution_result)
        except FuturesTimeoutError:
            for future, (tc_item, completion_fence) in futures.items():
                if future in pending:
                    if (
                        completion_fence is not None
                        and not completion_fence.mark_timed_out()
                    ):
                        _record_parallel_result(future.result())
                        continue
                    timeout_triggered = True
                    future.cancel()
                    _record_parallel_result(
                        _build_timeout_execution_result(tc_item),
                        timed_out=True,
                    )
        finally:
            pool.shutdown(wait=not timeout_triggered, cancel_futures=timeout_triggered)

    return results
