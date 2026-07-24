# -*- coding: utf-8 -*-
"""Core Agent loop rebound through the legacy runner facade."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.llm_adapter import LLMToolAdapter
from src.agent.protocols import StageFailureReason
from src.agent.runtime.guards import (
    RuntimeGuardPolicy,
    log_runtime_guard_event,
    runtime_guard_fingerprint,
)
from src.agent.runtime.lifecycle import UsageRecorder, get_default_usage_recorder
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.stock_scope import StockScope
from src.agent.stream_events import stream_event
from src.agent.tools.execution import _build_tool_cache_key
from src.agent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from src.agent.runner import (
        RunLoopResult,
        _THINKING_TOOL_LABELS,
        _build_budget_guard_result,
        _build_cancelled_result,
        _build_timeout_result,
        _build_tool_loop_result,
        _execute_tools,
        _remaining_timeout_seconds,
    )

logger = logging.getLogger("src.agent.runner")


def run_agent_loop(
    *,
    messages: List[Dict[str, Any]],
    tool_registry: ToolRegistry,
    llm_adapter: LLMToolAdapter,
    max_steps: int = 10,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    thinking_labels: Optional[Dict[str, str]] = None,
    max_wall_clock_seconds: Optional[float] = None,
    tool_call_timeout_seconds: Optional[float] = None,
    stock_scope: Optional[StockScope] = None,
    emit_stage_events: bool = True,
    cancelled_check: Optional[Callable[[], bool]] = None,
    usage_recorder: Optional[UsageRecorder] = None,
    runtime_guard_policy: Optional[RuntimeGuardPolicy] = None,
) -> RunLoopResult:
    """Execute the ReAct LLM ↔ tool loop.

    This is the *single shared implementation* of the agent execution loop.
    Both the legacy ``AgentExecutor`` and any future multi-agent runner
    should delegate here.

    Args:
        messages: The initial message list (system + user + optional history).
                  **Mutated in-place** — tool results are appended.
        tool_registry: Registry of callable tools.
        llm_adapter: LLM backend (handles multi-provider fallback).
        max_steps: Maximum number of LLM round-trips.
        progress_callback: Optional callback receiving progress dicts.
        thinking_labels: Override map of tool_name → friendly label.
        max_wall_clock_seconds: Optional overall timeout budget for the loop.
        tool_call_timeout_seconds: Optional timeout for one parallel tool batch.
        emit_stage_events: Whether to emit the synthetic ``agent_loop``
            stage lifecycle. Orchestrated business stages disable this so
            ``stage_start`` / ``stage_done`` only describe real stages.
        cancelled_check: Optional cooperative-cancellation probe. Checked at
            the top of every step and right after each LLM call; when it
            returns True the loop stops with ``cancelled=True`` before
            dispatching further tools or LLM calls.
        usage_recorder: Optional usage-telemetry sink; defaults to the
            process-wide recorder from the runtime lifecycle layer.
        runtime_guard_policy: Optional resolved timeout and loop policy. When
            omitted, the runner resolves the runtime-local environment policy.

    Returns:
        A :class:`RunLoopResult` with the final content, stats, and the
        (mutated) messages list.
    """
    labels = thinking_labels or _THINKING_TOOL_LABELS
    tool_decls = tool_registry.to_openai_tools()
    recorder = usage_recorder if usage_recorder is not None else get_default_usage_recorder()
    guard_policy = runtime_guard_policy or RuntimeGuardPolicy.from_sources()
    if tool_call_timeout_seconds is None:
        tool_call_timeout_seconds = guard_policy.tool_timeout_seconds
    elif tool_call_timeout_seconds > 0 and guard_policy.tool_timeout_seconds > 0:
        tool_call_timeout_seconds = min(
            tool_call_timeout_seconds,
            guard_policy.tool_timeout_seconds,
        )

    start_time = time.time()
    tool_calls_log: List[Dict[str, Any]] = []
    # Single tool authority for the whole run: every tool call in every step is
    # dispatched through this bound session. Native runs it in
    # ``enforce_access_policy=False`` compatibility mode so replay-frozen core
    # behavior is preserved while the direct ToolRegistry path is retired.
    # Definitions marked ``enforce_contract`` (including plugin tools) still
    # receive ToolSurface argument and scope validation. The session's internal
    # non-retriable memo replaces the previous ad-hoc per-run cache dict.
    tool_session = BoundToolSession(
        tool_registry,
        execution_id=str(uuid.uuid4()),
        allowed_tools=tool_registry.list_names(),
        stock_scope=stock_scope,
        cancelled_check=cancelled_check,
        backend="native",
        principal="native-runtime",
        enforce_access_policy=False,
    )
    total_tokens = 0
    provider_used = ""
    models_used: List[str] = []
    identical_tool_call_counts: Dict[str, int] = {}

    # Minimum seconds needed for a meaningful LLM round-trip.  If the
    # remaining budget is positive but below this threshold, the step will
    # almost certainly timeout mid-call, wasting a billed request.  Only
    # enforced from step 2 onwards so the first step always gets a chance
    # even when the total budget is small.
    _MIN_STEP_BUDGET_S = 8.0

    def _finish(result: RunLoopResult) -> RunLoopResult:
        # Terminal: close the tool session so any tool result still in flight
        # (e.g. a timed-out worker) is dropped behind the late-result fence and
        # can never re-enter the loop or a persisted success.
        tool_session.close()
        if progress_callback and emit_stage_events:
            progress_callback(
                stream_event(
                    "stage_done",
                    stage="agent_loop",
                    status="completed" if result.success else "failed",
                    duration=round(time.time() - start_time, 2),
                )
            )
        return result

    if progress_callback and emit_stage_events:
        progress_callback(
            stream_event(
                "stage_start",
                stage="agent_loop",
                message="Starting agent analysis...",
            )
        )

    for step in range(max_steps):
        if cancelled_check is not None and cancelled_check():
            logger.info("Agent loop cancelled before step %d", step + 1)
            return _finish(_build_cancelled_result(
                step=step,
                tool_calls_log=tool_calls_log,
                total_tokens=total_tokens,
                provider_used=provider_used,
                models_used=models_used,
                messages=messages,
            ))

        remaining_timeout = _remaining_timeout_seconds(start_time, max_wall_clock_seconds)
        timeout_exhausted = remaining_timeout is not None and remaining_timeout <= 0
        budget_guard_triggered = (
            not timeout_exhausted
            and remaining_timeout is not None
            and step > 0
            and remaining_timeout <= _MIN_STEP_BUDGET_S
        )
        if timeout_exhausted or budget_guard_triggered:
            if budget_guard_triggered:
                logger.warning(
                    "Agent budget too low for step %d (%.1fs remaining, min %.1fs)",
                    step + 1,
                    remaining_timeout,
                    _MIN_STEP_BUDGET_S,
                )
                return _finish(_build_budget_guard_result(
                    start_time=start_time,
                    step=step,
                    tool_calls_log=tool_calls_log,
                    total_tokens=total_tokens,
                    provider_used=provider_used,
                    models_used=models_used,
                    messages=messages,
                    remaining_timeout_s=remaining_timeout,
                    min_step_budget_s=_MIN_STEP_BUDGET_S,
                ))

            log_runtime_guard_event(
                logger,
                "run_timeout",
                scope="agent_loop",
                phase="before_step",
                step=step + 1,
                limit_seconds=float(max_wall_clock_seconds),
            )
            return _finish(_build_timeout_result(
                start_time=start_time,
                max_wall_clock_seconds=float(max_wall_clock_seconds),
                step=step,
                tool_calls_log=tool_calls_log,
                total_tokens=total_tokens,
                provider_used=provider_used,
                models_used=models_used,
                messages=messages,
            ))

        logger.info("Agent step %d/%d", step + 1, max_steps)

        # --- progress: thinking ---
        if progress_callback:
            if not tool_calls_log:
                thinking_msg = "正在制定分析路径..."
            else:
                last_tool = tool_calls_log[-1].get("tool", "")
                label = labels.get(last_tool, last_tool)
                thinking_msg = f"「{label}」已完成，继续深入分析..."
            progress_callback(stream_event("thinking", step=step + 1, message=thinking_msg))

        # --- LLM call ---
        response = llm_adapter.call_with_tools(
            messages,
            tool_decls,
            timeout=remaining_timeout,
        )
        provider_used = response.provider
        total_tokens += (response.usage or {}).get("total_tokens", 0)
        m = getattr(response, "model", "") or response.provider
        if m and m != "error":
            models_used.append(m)
        model_for_usage = m or response.provider
        if model_for_usage and model_for_usage != "error":
            recorder.record(response.usage, model_for_usage, call_type="agent")

        if cancelled_check is not None and cancelled_check():
            logger.info("Agent loop cancelled after LLM call at step %d", step + 1)
            return _finish(_build_cancelled_result(
                step=step + 1,
                tool_calls_log=tool_calls_log,
                total_tokens=total_tokens,
                provider_used=provider_used,
                models_used=models_used,
                messages=messages,
            ))

        remaining_timeout = _remaining_timeout_seconds(start_time, max_wall_clock_seconds)
        if remaining_timeout is not None and remaining_timeout <= 0:
            log_runtime_guard_event(
                logger,
                "run_timeout",
                scope="agent_loop",
                phase="after_llm",
                step=step + 1,
                limit_seconds=float(max_wall_clock_seconds),
            )
            return _finish(_build_timeout_result(
                start_time=start_time,
                max_wall_clock_seconds=float(max_wall_clock_seconds),
                step=step + 1,
                tool_calls_log=tool_calls_log,
                total_tokens=total_tokens,
                provider_used=provider_used,
                models_used=models_used,
                messages=messages,
            ))

        if response.tool_calls:
            # ---- tool execution branch ----
            tool_calls = [
                tool_call
                if type(tool_call.name) is str
                else replace(tool_call, name="")
                for tool_call in response.tool_calls
            ]
            logger.info(
                "Agent requesting %d tool call(s): %s",
                len(tool_calls),
                [tc.name for tc in tool_calls],
            )

            repeat_limit = guard_policy.max_identical_tool_calls
            pending_counts: Dict[str, int] = {}
            loop_violation = None
            if repeat_limit > 0:
                for tool_call in tool_calls:
                    signature = _build_tool_cache_key(
                        tool_call.name,
                        tool_call.arguments,
                    )
                    if signature is None:
                        continue
                    observed = (
                        identical_tool_call_counts.get(signature, 0)
                        + pending_counts.get(signature, 0)
                        + 1
                    )
                    if observed > repeat_limit:
                        loop_violation = (tool_call, signature, observed)
                        break
                    pending_counts[signature] = pending_counts.get(signature, 0) + 1

            if loop_violation is not None:
                tool_call, signature, observed = loop_violation
                log_runtime_guard_event(
                    logger,
                    "tool_loop_detected",
                    scope="tool",
                    tool=tool_call.name,
                    signature=runtime_guard_fingerprint(signature),
                    step=step + 1,
                    observed=observed,
                    limit=repeat_limit,
                    action="stop",
                )
                return _finish(_build_tool_loop_result(
                    step=step + 1,
                    tool_name=tool_call.name,
                    repeat_limit=repeat_limit,
                    tool_calls_log=tool_calls_log,
                    total_tokens=total_tokens,
                    provider_used=provider_used,
                    models_used=models_used,
                    messages=messages,
                ))

            for signature, count in pending_counts.items():
                identical_tool_call_counts[signature] = (
                    identical_tool_call_counts.get(signature, 0) + count
                )

            # Append assistant message (with tool_calls) to history
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": response.content,
                "_trace_provider": response.provider,
                "_trace_model": m,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                        **({"provider_specific_fields": tc.provider_specific_fields} if tc.provider_specific_fields else {}),
                        **({"thought_signature": tc.thought_signature} if tc.thought_signature is not None else {}),
                    }
                    for tc in tool_calls
                ],
            }
            if response.reasoning_content is not None:
                assistant_msg["reasoning_content"] = response.reasoning_content
            if response.provider_blocks:
                assistant_msg["provider_blocks"] = response.provider_blocks
            messages.append(assistant_msg)

            # Execute tools (parallel when > 1)
            effective_tool_timeout = tool_call_timeout_seconds
            if remaining_timeout is not None:
                effective_tool_timeout = min(
                    remaining_timeout,
                    tool_call_timeout_seconds if tool_call_timeout_seconds and tool_call_timeout_seconds > 0 else remaining_timeout,
                )
            tool_results = _execute_tools(
                tool_calls,
                tool_session,
                step + 1,
                progress_callback,
                tool_calls_log,
                tool_wait_timeout_seconds=effective_tool_timeout,
            )

            # Append tool results preserving original call order
            tc_order = {tc.id: i for i, tc in enumerate(tool_calls)}
            tool_results.sort(key=lambda x: tc_order.get(x["tc"].id, 0))
            for tr in tool_results:
                messages.append(
                    {
                        "role": "tool",
                        "name": tr["tc"].name,
                        "tool_call_id": tr["tc"].id,
                        "content": tr["result_str"],
                    }
                )

            remaining_timeout = _remaining_timeout_seconds(start_time, max_wall_clock_seconds)
            if remaining_timeout is not None and remaining_timeout <= 0:
                log_runtime_guard_event(
                    logger,
                    "run_timeout",
                    scope="agent_loop",
                    phase="after_tool",
                    step=step + 1,
                    limit_seconds=float(max_wall_clock_seconds),
                )
                return _finish(_build_timeout_result(
                    start_time=start_time,
                    max_wall_clock_seconds=float(max_wall_clock_seconds),
                    step=step + 1,
                    tool_calls_log=tool_calls_log,
                    total_tokens=total_tokens,
                    provider_used=provider_used,
                    models_used=models_used,
                    messages=messages,
                ))

        else:
            # ---- final answer branch ----
            logger.info(
                "Agent completed in %d steps (%.1fs, %d tokens)",
                step + 1,
                time.time() - start_time,
                total_tokens,
            )
            if progress_callback:
                progress_callback(stream_event("generating", step=step + 1, message="正在生成最终分析..."))

            final_content = response.content or ""
            is_error = response.provider == "error"

            return _finish(RunLoopResult(
                success=not is_error and bool(final_content),
                content=final_content if not is_error else "",
                tool_calls_log=tool_calls_log,
                total_steps=step + 1,
                total_tokens=total_tokens,
                provider=provider_used,
                models_used=models_used,
                error=final_content if is_error else None,
                failure_reason=(StageFailureReason.STAGE_FAILURE if is_error else None),
                messages=messages,
            ))

    # Max steps exceeded
    logger.warning("Agent hit max steps (%d)", max_steps)
    return _finish(RunLoopResult(
        success=False,
        content="",
        tool_calls_log=tool_calls_log,
        total_steps=max_steps,
        total_tokens=total_tokens,
        provider=provider_used,
        models_used=models_used,
        error=f"Agent exceeded max steps ({max_steps}). Try increasing AGENT_MAX_STEPS if analysis tasks are complex.",
        failure_reason=StageFailureReason.STAGE_FAILURE,
        messages=messages,
    ))
