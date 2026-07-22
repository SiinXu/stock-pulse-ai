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
import threading
import time
import uuid
import contextvars
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional

from src.agent.facade_binding import clone_facade_function as _clone_facade_function
from src.agent.runner_parts import loop as _runner_loop
from src.agent.runner_parts import parsing as _runner_parsing
from src.agent.runner_parts import results as _runner_results
from src.agent.runner_parts import tools as _runner_tools

parse_dashboard_json = _runner_parsing.parse_dashboard_json
parse_dashboard_json_result = _runner_parsing.parse_dashboard_json_result
run_agent_loop = _runner_loop.run_agent_loop

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
    bind_runner_tool_completion_guard,
    execute_runner_tool_call_via_session,
    serialize_tool_result,
)
from src.agent.runtime.tool_session import BoundToolSession, ExecutionFenceRejected
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


# ============================================================
# Tool completion fence
# ============================================================

class _ToolCompletionFence:
    """Linearize one runner timeout against BoundToolSession completion."""

    def __init__(self, timeout_seconds: float) -> None:
        self._lock = threading.Lock()
        self._timed_out = False
        self._completed = False
        self._deadline_monotonic = time.monotonic() + timeout_seconds

    def mark_timed_out(self) -> bool:
        """Claim timeout ownership unless completion already won."""
        with self._lock:
            if self._completed:
                return False
            self._timed_out = True
            return True

    @property
    def timed_out(self) -> bool:
        """Return whether this dispatch resolved as a timeout."""
        with self._lock:
            return self._timed_out

    def claim_completion(self, claim: Callable[[], None]) -> None:
        """Accept completion only when the runner timeout has not won."""
        with self._lock:
            if self._timed_out or time.monotonic() >= self._deadline_monotonic:
                self._timed_out = True
                raise ExecutionFenceRejected(
                    "tool_timeout",
                    "Tool result arrived after the runner timeout.",
                    {"fence": "tool_timeout"},
                )
            claim()
            self._completed = True



# Preserve legacy imports, patch points, annotations, metadata, and global lookup
# semantics while the implementation lives in focused source modules.
_PARSING_FUNCTION_NAMES = (
    "parse_dashboard_json",
    "parse_dashboard_json_result",
    "_finalize_dashboard_parse_result",
)
_RESULT_FUNCTION_NAMES = (
    "_remaining_timeout_seconds",
    "_build_timeout_result",
    "_build_cancelled_result",
    "_build_budget_guard_result",
    "_build_tool_loop_result",
)
_LOOP_FUNCTION_NAMES = ("run_agent_loop",)
_TOOL_FUNCTION_NAMES = ("_execute_tools",)


def _bind_runner_source(function):
    return _clone_facade_function(
        function,
        globals(),
        module_name=__name__,
        qualname=function.__name__,
        evaluate_annotations=False,
    )


for _source_module, _function_names in (
    (_runner_parsing, _PARSING_FUNCTION_NAMES),
    (_runner_results, _RESULT_FUNCTION_NAMES),
    (_runner_loop, _LOOP_FUNCTION_NAMES),
    (_runner_tools, _TOOL_FUNCTION_NAMES),
):
    for _function_name in _function_names:
        globals()[_function_name] = _bind_runner_source(
            getattr(_source_module, _function_name)
        )

del _function_name, _function_names, _source_module


# Make the full dependency namespace required by rebound functions explicit.
_RUNNER_COMPAT_EXPORTS = (
    BoundToolSession,
    DashboardParseResult,
    ExecutionFenceRejected,
    FuturesTimeoutError,
    LLMToolAdapter,
    RunLoopResult,
    RuntimeGuardPolicy,
    StageFailureReason,
    StockScope,
    ThreadPoolExecutor,
    ToolCall,
    ToolRegistry,
    UsageRecorder,
    _THINKING_TOOL_LABELS,
    _ToolCompletionFence,
    _build_tool_cache_key,
    _guard_tool_stock_scope,
    _is_non_retriable_tool_result,
    _is_stock_scoped_tool,
    _normalize_guard_stock_code,
    _normalize_tool_stock_code,
    _try_parse_json,
    _try_repair_json,
    as_completed,
    bind_runner_tool_completion_guard,
    contextvars,
    execute_runner_tool_call_via_session,
    get_default_usage_recorder,
    has_reserved_explanation_field,
    json,
    log_runtime_guard_event,
    logger,
    logging,
    normalize_report_signal_attribution,
    re,
    replace,
    runtime_guard_fingerprint,
    sanitize_agent_dashboard_payload,
    serialize_tool_result,
    stream_event,
    threading,
    time,
    uuid,
)
