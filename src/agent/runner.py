# -*- coding: utf-8 -*-
"""
Shared runner — extracted LLM + tool execution loop.

Provides ``run_agent_loop``, the single authoritative implementation of the
ReAct execute-loop that was previously inlined inside ``AgentExecutor._run_loop``.
All current and future agents should delegate to this runner instead of
re-implementing the loop themselves.

Design goals:
- Keep the same observable behaviour as the original ``_run_loop``
- Accept pluggable callbacks for progress, message history, and result handling
- Remain stateless — all mutable state lives in the caller
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
import contextvars
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional

from src.agent.dashboard_payload import (
    has_reserved_explanation_field,
    sanitize_agent_dashboard_payload,
)
from src.agent.llm_adapter import LLMToolAdapter, ToolCall
from src.agent.protocols import StageFailureReason
from src.agent.stream_events import stream_event
from src.agent.tools.registry import ToolRegistry
from src.agent.tools.execution import (
    _build_tool_cache_key,
    _guard_tool_stock_scope,
    _is_non_retriable_tool_result,
    _is_stock_scoped_tool,
    _normalize_guard_stock_code,
    _normalize_tool_stock_code,
    execute_runner_tool_call_via_session,
    serialize_tool_result,
)
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.runtime.guards import (
    RuntimeGuardPolicy,
    log_runtime_guard_event,
    runtime_guard_fingerprint,
)
from src.agent.stock_scope import StockScope
from src.agent.runtime.lifecycle import UsageRecorder, get_default_usage_recorder
from src.utils.data_processing import normalize_report_signal_attribution

logger = logging.getLogger(__name__)

__all__ = [
    "DashboardParseResult",
    "RunLoopResult",
    "parse_dashboard_json",
    "parse_dashboard_json_result",
    "run_agent_loop",
    "serialize_tool_result",
    "try_parse_json",
    "_build_tool_cache_key",
    "_guard_tool_stock_scope",
    "_is_non_retriable_tool_result",
    "_is_stock_scoped_tool",
    "_normalize_guard_stock_code",
    "_normalize_tool_stock_code",
]

# Tool name → friendly label for progress messages
_THINKING_TOOL_LABELS: Dict[str, str] = {
    "get_realtime_quote": "行情获取",
    "get_daily_history": "K线数据获取",
    "analyze_trend": "技术指标分析",
    "get_chip_distribution": "筹码分布分析",
    "search_stock_news": "新闻搜索",
    "search_comprehensive_intel": "综合情报搜索",
    "get_market_indices": "市场概览获取",
    "get_sector_rankings": "行业板块分析",
    "get_analysis_context": "历史分析上下文",
    "get_stock_info": "基本信息获取",
    "analyze_pattern": "K线形态识别",
    "get_volume_analysis": "量能分析",
    "calculate_ma": "均线计算",
    "get_skill_backtest_summary": "技能回测概览",
    "get_strategy_backtest_summary": "策略回测概览",
    "get_stock_backtest_summary": "个股回测数据",
}


# ============================================================
# RunLoopResult — the output of one run_agent_loop invocation
# ============================================================

@dataclass
class RunLoopResult:
    """Output produced by :func:`run_agent_loop`."""

    success: bool = False
    content: str = ""
    tool_calls_log: List[Dict[str, Any]] = field(default_factory=list)
    total_steps: int = 0
    total_tokens: int = 0
    provider: str = ""
    models_used: List[str] = field(default_factory=list)
    error: Optional[str] = None
    failure_reason: Optional[StageFailureReason] = None
    # Raw messages list at the end of the loop (callers may want to persist)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    cancelled: bool = False
    timed_out: bool = False

    @property
    def model(self) -> str:
        """Comma-separated de-duplicated model names used during the run."""
        return ", ".join(dict.fromkeys(m for m in self.models_used if m))


@dataclass(frozen=True)
class DashboardParseResult:
    """Canonical dashboard plus deterministic sanitization metadata."""

    payload: Dict[str, Any]
    reserved_field_removed: bool = False


# ============================================================
# Helpers
# ============================================================

def parse_dashboard_json(content: str) -> Optional[Dict[str, Any]]:
    """Extract and parse a canonical Decision Dashboard JSON."""
    result = parse_dashboard_json_result(content)
    return result.payload if result is not None else None


def parse_dashboard_json_result(content: str) -> Optional[DashboardParseResult]:
    """Extract a dashboard and report whether a reserved field was removed.

    Tries multiple strategies:
    1. Markdown code blocks (```json ... ```)
    2. Raw JSON parse
    3. ``json_repair`` library
    4. Brace-delimited substring
    """
    if not content:
        return None

    from json_repair import repair_json

    # Strategy 1: markdown code blocks
    json_blocks = re.findall(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if json_blocks:
        for block in json_blocks:
            parsed = _try_parse_json(block)
            if parsed is not None:
                return _finalize_dashboard_parse_result(parsed)
            parsed = _try_repair_json(block, repair_json)
            if parsed is not None:
                return _finalize_dashboard_parse_result(parsed)

    # Strategy 2: raw parse
    parsed = _try_parse_json(content)
    if parsed is not None:
        return _finalize_dashboard_parse_result(parsed)

    # Strategy 3: json_repair on full content
    parsed = _try_repair_json(content, repair_json)
    if parsed is not None:
        return _finalize_dashboard_parse_result(parsed)

    # Strategy 4: brace-delimited
    brace_start = content.find("{")
    brace_end = content.rfind("}")
    if brace_start >= 0 and brace_end > brace_start:
        candidate = content[brace_start : brace_end + 1]
        parsed = _try_parse_json(candidate)
        if parsed is not None:
            return _finalize_dashboard_parse_result(parsed)
        parsed = _try_repair_json(candidate, repair_json)
        if parsed is not None:
            return _finalize_dashboard_parse_result(parsed)

    logger.warning("Failed to parse dashboard JSON from agent response")
    return None


def _finalize_dashboard_parse_result(payload: Dict[str, Any]) -> DashboardParseResult:
    """Sanitize reserved fields before normal dashboard normalization."""
    reserved_field_removed = has_reserved_explanation_field(payload)
    sanitized = sanitize_agent_dashboard_payload(payload)
    normalize_report_signal_attribution(sanitized)
    return DashboardParseResult(
        payload=sanitized,
        reserved_field_removed=reserved_field_removed,
    )


def try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON dict extraction from LLM text.

    Handles:
    1. Direct JSON parse
    2. Markdown code fences (```json ... ```)
    3. Brace-delimited substring
    4. ``json_repair`` fallback for slightly malformed JSON

    This is the shared utility that all agent ``post_process`` methods
    should use instead of duplicating the same logic.
    """
    if not text:
        return None

    candidates: List[str] = []
    cleaned = text.strip()
    if cleaned:
        candidates.append(cleaned)

    if cleaned.startswith("```"):
        unfenced = re.sub(r'^```(?:json)?\s*', '', cleaned)
        unfenced = re.sub(r'\s*```$', '', unfenced)
        if unfenced:
            candidates.append(unfenced.strip())

    fenced_blocks = re.findall(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    for block in fenced_blocks:
        block = block.strip()
        if block:
            candidates.append(block)

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        snippet = text[start:end + 1].strip()
        if snippet:
            candidates.append(snippet)

    seen: set[str] = set()
    unique_candidates: List[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)

    for candidate in unique_candidates:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    try:
        from json_repair import repair_json
    except Exception:
        repair_json = None

    if repair_json is not None:
        for candidate in unique_candidates:
            repaired = _try_repair_json(candidate, repair_json)
            if repaired is not None:
                return repaired

    return None


# Keep private alias used internally by parse_dashboard_json
_try_parse_json = try_parse_json


def _try_repair_json(text: str, repair_fn: Callable) -> Optional[Dict[str, Any]]:
    try:
        repaired = repair_fn(text)
        obj = json.loads(repaired)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _remaining_timeout_seconds(
    start_time: float,
    max_wall_clock_seconds: Optional[float],
) -> Optional[float]:
    """Return remaining wall-clock budget in seconds, or None when disabled."""
    if max_wall_clock_seconds is None or max_wall_clock_seconds <= 0:
        return None
    return max(0.0, float(max_wall_clock_seconds) - (time.time() - start_time))


def _build_timeout_result(
    *,
    start_time: float,
    max_wall_clock_seconds: float,
    step: int,
    tool_calls_log: List[Dict[str, Any]],
    total_tokens: int,
    provider_used: str,
    models_used: List[str],
    messages: List[Dict[str, Any]],
) -> RunLoopResult:
    elapsed = time.time() - start_time
    return RunLoopResult(
        success=False,
        content="",
        tool_calls_log=tool_calls_log,
        total_steps=step,
        total_tokens=total_tokens,
        provider=provider_used,
        models_used=models_used,
        error=f"Agent timed out after {elapsed:.2f}s (limit: {max_wall_clock_seconds:.2f}s)",
        failure_reason=StageFailureReason.TIMEOUT,
        messages=messages,
        timed_out=True,
    )


def _build_cancelled_result(
    *,
    step: int,
    tool_calls_log: List[Dict[str, Any]],
    total_tokens: int,
    provider_used: str,
    models_used: List[str],
    messages: List[Dict[str, Any]],
) -> RunLoopResult:
    return RunLoopResult(
        success=False,
        content="",
        tool_calls_log=tool_calls_log,
        total_steps=step,
        total_tokens=total_tokens,
        provider=provider_used,
        models_used=models_used,
        error="Agent execution cancelled",
        messages=messages,
        cancelled=True,
    )


def _build_budget_guard_result(
    *,
    start_time: float,
    step: int,
    tool_calls_log: List[Dict[str, Any]],
    total_tokens: int,
    provider_used: str,
    models_used: List[str],
    messages: List[Dict[str, Any]],
    remaining_timeout_s: float,
    min_step_budget_s: float,
) -> RunLoopResult:
    return RunLoopResult(
        success=False,
        content="",
        tool_calls_log=tool_calls_log,
        total_steps=step,
        total_tokens=total_tokens,
        provider=provider_used,
        models_used=models_used,
        error=(
            "Agent step skipped due to insufficient budget: "
            f"{remaining_timeout_s:.2f}s remaining, minimum {min_step_budget_s:.1f}s required"
        ),
        failure_reason=StageFailureReason.BUDGET_SKIP,
        messages=messages,
    )


def _build_tool_loop_result(
    *,
    step: int,
    tool_name: str,
    repeat_limit: int,
    tool_calls_log: List[Dict[str, Any]],
    total_tokens: int,
    provider_used: str,
    models_used: List[str],
    messages: List[Dict[str, Any]],
) -> RunLoopResult:
    return RunLoopResult(
        success=False,
        content="",
        tool_calls_log=tool_calls_log,
        total_steps=step,
        total_tokens=total_tokens,
        provider=provider_used,
        models_used=models_used,
        error=(
            f"Agent stopped because tool '{tool_name}' exceeded the "
            f"identical-call limit ({repeat_limit})"
        ),
        failure_reason=StageFailureReason.LOOP_DETECTED,
        messages=messages,
    )


# ============================================================
# Core loop
# ============================================================

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
    # ``enforce_access_policy=False`` compatibility mode so the replay-frozen
    # behaviour is preserved byte-for-byte while the direct ToolRegistry path is
    # retired. The session's internal non-retriable memo replaces the previous
    # ad-hoc per-run cache dict.
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


# ============================================================
# Internal tool execution
# ============================================================

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

    def _exec_single(tc_item):
        return execute_runner_tool_call_via_session(tc_item, tool_session)

    results: List[Dict[str, Any]] = []

    if len(tool_calls) == 1:
        tc = tool_calls[0]
        if progress_callback:
            progress_callback(stream_event("tool_start", step=step, tool=tc.name))
        timeout_triggered = False
        if tool_wait_timeout_seconds and tool_wait_timeout_seconds > 0:
            pool = ThreadPoolExecutor(max_workers=1)
            ctx = contextvars.copy_context()
            try:
                future = pool.submit(ctx.run, _exec_single, tc)
                try:
                    _, result_str, success, dur, cached, guard_result = future.result(timeout=tool_wait_timeout_seconds)
                except FuturesTimeoutError:
                    timeout_triggered = True
                    future.cancel()
                    timeout_label = f"{tool_wait_timeout_seconds:.2f}s"
                    log_runtime_guard_event(
                        logger,
                        "tool_timeout",
                        scope="tool",
                        execution_id=tool_session.execution_id,
                        tool=tc.name,
                        step=step,
                        limit_seconds=round(tool_wait_timeout_seconds, 3),
                        action="result_fenced",
                    )
                    result_str = json.dumps({
                        "error": f"Tool execution timed out after {timeout_label}",
                        "timeout": True,
                    })
                    success = False
                    dur = round(tool_wait_timeout_seconds, 2)
                    cached = False
                    guard_result = None
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
        for tc in tool_calls:
            if progress_callback:
                progress_callback(stream_event("tool_start", step=step, tool=tc.name))

        pool = ThreadPoolExecutor(max_workers=min(len(tool_calls), 5))
        timeout_triggered = False
        try:
            futures = {pool.submit(contextvars.copy_context().run, _exec_single, tc): tc for tc in tool_calls}
            pending = set(futures)
            for future in as_completed(
                futures,
                timeout=tool_wait_timeout_seconds if tool_wait_timeout_seconds and tool_wait_timeout_seconds > 0 else None,
            ):
                pending.discard(future)
                tc_item, result_str, success, dur, cached, guard_result = future.result()
                if progress_callback:
                    progress_callback(stream_event("tool_done", step=step, tool=tc_item.name, success=success, duration=dur))
                log_entry = {
                    "step": step, "tool": tc_item.name, "arguments": tc_item.arguments,
                    "success": success, "duration": dur, "result_length": len(result_str),
                    "cached": cached,
                }
                if guard_result is not None:
                    log_entry.update({
                        "guarded": True,
                        "expected_stock_code": guard_result.get("expected_stock_code"),
                        "requested_stock_code": guard_result.get("requested_stock_code"),
                        "allowed_stock_codes": guard_result.get("allowed_stock_codes", []),
                    })
                tool_calls_log.append(log_entry)
                results.append({"tc": tc_item, "result_str": result_str})
        except FuturesTimeoutError:
            timeout_triggered = True
            timeout_label = (
                f"{tool_wait_timeout_seconds:.2f}s"
                if tool_wait_timeout_seconds is not None
                else "the configured limit"
            )
            for future, tc_item in futures.items():
                if future in pending:
                    future.cancel()
                    log_runtime_guard_event(
                        logger,
                        "tool_timeout",
                        scope="tool",
                        execution_id=tool_session.execution_id,
                        tool=tc_item.name,
                        step=step,
                        limit_seconds=round(tool_wait_timeout_seconds or 0.0, 3),
                        action="result_fenced",
                    )
                    result_str = json.dumps({
                        "error": f"Tool execution timed out after {timeout_label}",
                        "timeout": True,
                    })
                    if progress_callback:
                        progress_callback(stream_event(
                            "tool_done",
                            step=step,
                            tool=tc_item.name,
                            success=False,
                            duration=round(tool_wait_timeout_seconds or 0.0, 2),
                        ))
                    tool_calls_log.append({
                        "step": step,
                        "tool": tc_item.name,
                        "arguments": tc_item.arguments,
                        "success": False,
                        "duration": round(tool_wait_timeout_seconds or 0.0, 2),
                        "result_length": len(result_str),
                        "cached": False,
                        "timeout": True,
                    })
                    results.append({"tc": tc_item, "result_str": result_str})
        finally:
            pool.shutdown(wait=not timeout_triggered, cancel_futures=timeout_triggered)

    return results
