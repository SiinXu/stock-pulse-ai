# -*- coding: utf-8 -*-
"""Tool execution function rebound through the legacy runner facade."""

from __future__ import annotations

import contextvars
import json
import logging
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
)
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.llm_adapter import ToolCall
from src.agent.observability import emit_tool_end, emit_tool_start
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
    authority — via the migration mapper. Completion fences use the earlier
    of the batch timeout and the owning session deadline so both layers publish
    one deterministic timeout result at their shared boundary.
    """

    from src.utils.sanitize import redact_sensitive_data, redact_sensitive_text

    tool_deadline_monotonic = tool_session.deadline_monotonic

    def _safe_tool_trace_name(value: Any) -> str:
        canonicalize = getattr(tool_session, "canonical_tool_name", None)
        if callable(canonicalize):
            return canonicalize(value)
        return (
            redact_sensitive_text(value, redact_opaque_tokens=True)
            if isinstance(value, str)
            else ""
        )

    def _safe_tool_trace_arguments(value: Any) -> Dict[str, Any]:
        redacted = redact_sensitive_data(value)
        return redacted if isinstance(redacted, dict) else {}

    def _safe_tool_result_preview(value: Any) -> str:
        redacted = redact_sensitive_data(value)
        rendered = (
            redacted
            if isinstance(redacted, str)
            else json.dumps(redacted, ensure_ascii=False, default=str)
        )
        return rendered[:1200]

    def _exec_single(tc_item, completion_fence=None):
        """Execute one tool with an optional per-dispatch completion fence."""
        if completion_fence is None:
            return execute_runner_tool_call_via_session(tc_item, tool_session)
        with bind_runner_tool_completion_guard(
            completion_fence.claim_completion,
            dispatch_guard=completion_fence.claim_dispatch,
            deadline_monotonic=completion_fence.deadline_monotonic,
        ):
            return execute_runner_tool_call_via_session(tc_item, tool_session)

    def _resolve_tool_wait_timeout(tc_item) -> Optional[float]:
        """Shortest of the batch/global remaining budget and the category cap."""
        from src.agent.runtime.guards import shortest_positive_timeout
        from src.agent.runtime.tool_session import (
            resolve_session_category_timeout_seconds,
        )

        return shortest_positive_timeout(
            tool_wait_timeout_seconds,
            resolve_session_category_timeout_seconds(tool_session, tc_item.name),
        )

    def _build_timeout_execution_result(tc_item, timeout_seconds=None):
        """Build and log the canonical result for one timed-out dispatch."""
        timeout_value = (
            timeout_seconds
            if timeout_seconds is not None
            else (tool_wait_timeout_seconds or 0.0)
        )
        timeout_label = (
            f"{timeout_value:.2f}s"
            if timeout_value
            else "the configured limit"
        )
        log_runtime_guard_event(
            logger,
            "tool_timeout",
            scope="tool",
            execution_id=tool_session.execution_id,
            tool=_safe_tool_trace_name(tc_item.name),
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
        tool_name = _safe_tool_trace_name(tc.name)
        safe_arguments = _safe_tool_trace_arguments(tc.arguments)
        if progress_callback:
            progress_callback(stream_event(
                "tool_start",
                step=step,
                tool=tool_name,
                meta={"arguments": safe_arguments},
            ))
        start_event = emit_tool_start(
            tool_name,
            step=step,
            payload={"arguments": _safe_tool_trace_arguments(tc.arguments)},
        )
        tool_span_id = start_event.span_id if start_event is not None else None
        timeout_triggered = False
        wait_timeout = _resolve_tool_wait_timeout(tc)
        if wait_timeout and wait_timeout > 0:
            pool = ThreadPoolExecutor(max_workers=1)
            ctx = contextvars.copy_context()
            completion_fence = _ToolCompletionFence(
                wait_timeout,
                deadline_monotonic=tool_deadline_monotonic,
            )
            try:
                future = pool.submit(ctx.run, _exec_single, tc, completion_fence)
                try:
                    execution_result = future.result(
                        timeout=wait_timeout,
                    )
                except FuturesTimeoutError:
                    timeout_triggered = completion_fence.mark_timed_out()
                    if not timeout_triggered:
                        execution_result = future.result()
                else:
                    timeout_triggered = completion_fence.timed_out
                if timeout_triggered:
                    future.cancel()
                    execution_result = _build_timeout_execution_result(
                        tc, timeout_seconds=wait_timeout
                    )
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
        result_preview = _safe_tool_result_preview(result_str)
        if progress_callback:
            progress_callback(stream_event(
                "tool_done",
                step=step,
                tool=tool_name,
                success=success,
                duration=dur,
                meta={
                    "arguments": safe_arguments,
                    "cached": cached,
                    "result_length": len(result_str),
                    "result_preview": result_preview,
                },
            ))
        duration_ms = None
        try:
            if dur is not None:
                duration_ms = max(0, int(float(dur) * 1000))
        except (TypeError, ValueError):
            duration_ms = None
        emit_tool_end(
            tool_name,
            success=bool(success),
            duration_ms=duration_ms,
            step=step,
            span_id=tool_span_id,
            attrs={"cached": cached, "result_length": len(result_str)},
            payload={"result_preview": result_str[:200] if isinstance(result_str, str) else None},
        )
        log_entry = {
            "step": step,
            "tool": tool_name,
            "arguments": safe_arguments,
            "success": success, "duration": dur, "result_length": len(result_str),
            "cached": cached, "result_preview": result_preview,
        }
        if wait_timeout and wait_timeout > 0 and not success:
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
        def _record_parallel_result(execution_result, *, timed_out=False, span_id=None):
            """Record one accepted parallel result in the existing output shape."""
            tc_item, result_str, success, dur, cached, guard_result = execution_result
            tool_name = _safe_tool_trace_name(tc_item.name)
            safe_arguments = _safe_tool_trace_arguments(tc_item.arguments)
            result_preview = _safe_tool_result_preview(result_str)
            if progress_callback:
                progress_callback(stream_event(
                    "tool_done",
                    step=step,
                    tool=tool_name,
                    success=success,
                    duration=dur,
                    meta={
                        "arguments": safe_arguments,
                        "cached": cached,
                        "result_length": len(result_str),
                        "result_preview": result_preview,
                    },
                ))
            duration_ms = None
            try:
                if dur is not None:
                    duration_ms = max(0, int(float(dur) * 1000))
            except (TypeError, ValueError):
                duration_ms = None
            emit_tool_end(
                tool_name,
                success=bool(success),
                duration_ms=duration_ms,
                step=step,
                span_id=span_id,
                attrs={"cached": cached, "result_length": len(result_str), "timed_out": timed_out},
                payload={"result_preview": result_str[:200] if isinstance(result_str, str) else None},
            )
            log_entry = {
                "step": step,
                "tool": tool_name,
                "arguments": safe_arguments,
                "success": success,
                "duration": dur,
                "result_length": len(result_str),
                "cached": cached,
                "result_preview": result_preview,
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

        tool_span_by_id: Dict[str, Optional[str]] = {}
        for tc in tool_calls:
            tool_name = _safe_tool_trace_name(tc.name)
            safe_arguments = _safe_tool_trace_arguments(tc.arguments)
            if progress_callback:
                progress_callback(stream_event(
                    "tool_start",
                    step=step,
                    tool=tool_name,
                    meta={"arguments": safe_arguments},
                ))
            start_event = emit_tool_start(
                tool_name,
                step=step,
                payload={"arguments": _safe_tool_trace_arguments(tc.arguments)},
            )
            tool_span_by_id[str(tc.id)] = (
                start_event.span_id if start_event is not None else None
            )

        pool = ThreadPoolExecutor(max_workers=min(len(tool_calls), 5))
        timeout_triggered = False
        try:
            futures = {}
            for tc in tool_calls:
                wait_timeout = _resolve_tool_wait_timeout(tc)
                completion_fence = (
                    _ToolCompletionFence(
                        wait_timeout,
                        deadline_monotonic=tool_deadline_monotonic,
                    )
                    if wait_timeout and wait_timeout > 0
                    else None
                )
                future = pool.submit(
                    contextvars.copy_context().run,
                    _exec_single,
                    tc,
                    completion_fence,
                )
                futures[future] = (tc, completion_fence, wait_timeout)
            pending = set(futures)

            def _accept_completed_future(future):
                """Publish one finished future, fencing results after its deadline."""
                nonlocal timeout_triggered
                pending.discard(future)
                tc_item, completion_fence, wait_timeout = futures[future]
                span_id = tool_span_by_id.get(str(tc_item.id))
                if completion_fence is not None and completion_fence.timed_out:
                    timeout_triggered = True
                    _record_parallel_result(
                        _build_timeout_execution_result(
                            tc_item, timeout_seconds=wait_timeout
                        ),
                        timed_out=True,
                        span_id=span_id,
                    )
                    return
                execution_result = future.result()
                if completion_fence is not None and completion_fence.timed_out:
                    timeout_triggered = True
                    _record_parallel_result(
                        _build_timeout_execution_result(
                            tc_item, timeout_seconds=wait_timeout
                        ),
                        timed_out=True,
                        span_id=span_id,
                    )
                    return
                _record_parallel_result(execution_result, span_id=span_id)

            def _expire_due_future(future):
                """Fence one dispatch whose remaining deadline has elapsed."""
                nonlocal timeout_triggered
                pending.discard(future)
                tc_item, completion_fence, wait_timeout = futures[future]
                span_id = tool_span_by_id.get(str(tc_item.id))
                if completion_fence is not None and not completion_fence.mark_timed_out():
                    _record_parallel_result(future.result(), span_id=span_id)
                    return
                timeout_triggered = True
                future.cancel()
                _record_parallel_result(
                    _build_timeout_execution_result(
                        tc_item, timeout_seconds=wait_timeout
                    ),
                    timed_out=True,
                    span_id=span_id,
                )

            while pending:
                now = time.monotonic()
                remaining_waits = []
                immediately_due = []
                for future in list(pending):
                    _tc_item, completion_fence, _wait_timeout = futures[future]
                    if completion_fence is None:
                        continue
                    remaining = completion_fence.deadline_monotonic - now
                    if remaining <= 0:
                        immediately_due.append(future)
                    else:
                        remaining_waits.append(remaining)
                for future in immediately_due:
                    _expire_due_future(future)
                if not pending:
                    break
                if immediately_due:
                    continue
                batch_timeout = min(remaining_waits) if remaining_waits else None
                try:
                    for future in as_completed(pending, timeout=batch_timeout):
                        _accept_completed_future(future)
                    break
                except FuturesTimeoutError:
                    due_at = now + (batch_timeout if batch_timeout is not None else 0.0)
                    expired_any = False
                    shortest_future = None
                    shortest_deadline = None
                    for future in list(pending):
                        _tc_item, completion_fence, _wait_timeout = futures[future]
                        if completion_fence is None:
                            continue
                        deadline = completion_fence.deadline_monotonic
                        if shortest_deadline is None or deadline < shortest_deadline:
                            shortest_future = future
                            shortest_deadline = deadline
                        if deadline <= due_at + 1e-9:
                            _expire_due_future(future)
                            expired_any = True
                    if expired_any or not pending:
                        continue
                    if shortest_future is not None:
                        _expire_due_future(shortest_future)
                        continue
                    for future in list(pending):
                        _accept_completed_future(future)
        finally:
            # Timed-out dispatches are already fenced per future. Remaining
            # category/global deadlines must keep running instead of being
            # cancelled as one batch.
            pool.shutdown(wait=True, cancel_futures=False)

    return results
