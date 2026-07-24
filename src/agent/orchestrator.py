# -*- coding: utf-8 -*-
"""
AgentOrchestrator — multi-agent pipeline coordinator.

Manages the lifecycle of specialised agents (Technical → Intel → Risk →
Specialist → Decision) for a single stock analysis run.

Modes:
- ``quick``   : Technical only → Decision (fastest, ~2 LLM calls)
- ``standard``: Technical → Intel → Decision (default)
- ``full``    : Technical → Intel → Risk → Decision
- ``specialist``: Technical → Intel → Risk → specialist evaluation → Decision

The orchestrator:
1. Seeds an :class:`AgentContext` with the user query and stock code
2. Runs agents sequentially, passing the shared context
3. Collects :class:`StageResult` from each agent
4. Produces a unified :class:`OrchestratorResult` with the final dashboard

Importantly, this class exposes the same ``run(task, context)`` and
``chat(message, session_id, ...)`` interface as ``AgentExecutor`` so it
can be a drop-in replacement via the factory.
"""

from __future__ import annotations

import contextvars
import copy
import json
import inspect
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field, fields as dataclass_fields
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from src.agent.chat_context import (
    build_agent_chat_market_context,
    build_agent_chat_tool_registry,
    build_visible_chat_history,
)
from src.agent.dashboard_payload import sanitize_agent_dashboard_payload
from src.agent.disagreement import build_agent_disagreement_summary
from src.agent.llm_adapter import LLMToolAdapter
from src.agent.protocols import (
    AgentContext,
    AgentRunStats,
    StageFailureReason,
    StageResult,
    StageStatus,
    normalize_decision_signal,
    normalize_stage_failure_reason,
)
from src.agent.skills.engine import StrategyEngine, StrategyResultStatus
from src.agent.public_contract import (
    AGENT_CHAT_FAILURE_HISTORY_SENTINEL,
    AGENT_CHAT_FAILURE_MESSAGE,
    AGENT_EXECUTION_FAILURE_MESSAGE,
    sanitize_agent_diagnostic,
)
from src.agent.risk_override import (
    RiskOverrideApplication,
    build_risk_override_application,
    build_risk_override_plan,
)
from src.agent.runner import parse_dashboard_json, run_agent_loop
from src.agent.runtime.contract import ExecutionState
from src.agent.runtime_facts import (
    AgentRuntimeFacts,
    DegradationBoundary,
    DegradedEvent,
    PipelineTerminationFact,
    build_agent_runtime_facts,
)
from src.agent.runtime.lifecycle import classify_result_terminal_state
from src.agent.soul import compose_agent_soul_prompt as _compose_agent_soul_prompt
from src.agent.runtime.guards import (
    RuntimeGuardPolicy,
    StageFailurePolicy,
    log_runtime_guard_event,
)
from src.agent.stock_scope import StockScope, resolve_stock_scope
from src.agent.stream_events import stream_event
from src.agent.tools.registry import ToolRegistry
from src.config import AGENT_MAX_STEPS_DEFAULT, get_config
from src.report_language import normalize_report_language
from src.utils.sanitize import log_safe_exception
from src.agent.facade_binding import bind_facade_methods as _bind_facade_methods
from src.agent.orchestrator_parts.chat import _ChatMethods
from src.agent.orchestrator_parts.dashboard import _DashboardMethods
from src.agent.orchestrator_parts.execution import _ExecutionMethods
from src.agent.orchestrator_parts.pipeline import _PipelineMethods

if TYPE_CHECKING:
    from src.agent.executor import AgentResult

    _AGENT_RESULT_TYPE = AgentResult

logger = logging.getLogger(__name__)

# These names remain part of the legacy module namespace and are the global
# lookup surface used by descriptors rebound from the private source modules.
_ORCHESTRATOR_COMPAT_EXPORTS = (
    AGENT_CHAT_FAILURE_HISTORY_SENTINEL,
    AGENT_CHAT_FAILURE_MESSAGE,
    AGENT_EXECUTION_FAILURE_MESSAGE,
    AgentContext,
    build_agent_chat_market_context,
    build_agent_chat_tool_registry,
    build_agent_disagreement_summary,
    build_agent_runtime_facts,
    build_risk_override_application,
    build_risk_override_plan,
    build_visible_chat_history,
    classify_result_terminal_state,
    contextvars,
    copy,
    dataclass_fields,
    DegradationBoundary,
    DegradedEvent,
    ExecutionState,
    FuturesTimeoutError,
    get_config,
    inspect,
    json,
    log_runtime_guard_event,
    log_safe_exception,
    _compose_agent_soul_prompt,
    normalize_decision_signal,
    normalize_report_language,
    normalize_stage_failure_reason,
    parse_dashboard_json,
    PipelineTerminationFact,
    resolve_stock_scope,
    RiskOverrideApplication,
    run_agent_loop,
    sanitize_agent_dashboard_payload,
    sanitize_agent_diagnostic,
    StageFailurePolicy,
    StageFailureReason,
    StageResult,
    StageStatus,
    StockScope,
    StrategyResultStatus,
    stream_event,
    ThreadPoolExecutor,
    time,
)

# Valid orchestrator modes (ordered by cost/depth)
VALID_MODES = ("quick", "standard", "full", "specialist")
NON_CRITICAL_BASE_STAGES = frozenset({"intel", "risk"})
_PREPARED_DECISION_TYPE_INSERTED = "_prepared_dashboard_decision_type_inserted"


@dataclass
class OrchestratorResult:
    """Unified result from a multi-agent pipeline run."""

    success: bool = False
    content: str = ""
    dashboard: Optional[Dict[str, Any]] = None
    tool_calls_log: List[Dict[str, Any]] = field(default_factory=list)
    total_steps: int = 0
    total_tokens: int = 0
    provider: str = ""
    model: str = ""
    error: Optional[str] = None
    stats: Optional[AgentRunStats] = None
    runtime_facts: Optional[AgentRuntimeFacts] = field(default_factory=AgentRuntimeFacts)
    cancelled: bool = False
    timed_out: bool = False


class _StageProgressFence:
    """Serialize stage progress delivery with terminal closure."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._closed = False

    def close(self) -> None:
        """Wait for an in-flight callback, then reject later progress."""
        with self._lock:
            self._closed = True

    def is_closed(self) -> bool:
        """Return whether the owning stage has reached a terminal boundary."""
        with self._lock:
            return self._closed

    def emit(
        self,
        callback: Callable[[Dict[str, Any]], None],
        event: Dict[str, Any],
    ) -> None:
        """Deliver progress only while the stage owns the emission fence."""
        with self._lock:
            if not self._closed:
                callback(event)


class AgentOrchestrator:
    """Multi-agent pipeline coordinator.

    Drop-in replacement for ``AgentExecutor`` — exposes the same ``run()``
    and ``chat()`` interface.  The factory switches between them via
    ``AGENT_ARCH``.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm_adapter: LLMToolAdapter,
        skill_instructions: str = "",
        technical_skill_policy: str = "",
        max_steps: int = AGENT_MAX_STEPS_DEFAULT,
        mode: str = "standard",
        skill_manager=None,
        config=None,
        runtime_guard_policy: Optional[RuntimeGuardPolicy] = None,
    ):
        self.tool_registry = tool_registry
        self.llm_adapter = llm_adapter
        self.skill_instructions = skill_instructions
        self.technical_skill_policy = technical_skill_policy
        self.max_steps = max_steps
        normalized_mode = "specialist" if mode in {"strategy", "skill"} else mode
        self.mode = normalized_mode if normalized_mode in VALID_MODES else "standard"
        self.skill_manager = skill_manager
        self.config = config
        self.strategy_engine = StrategyEngine()
        self.runtime_guard_policy = (
            runtime_guard_policy or RuntimeGuardPolicy.from_sources(config)
        )

_EXECUTION_METHOD_NAMES = _bind_facade_methods(
    AgentOrchestrator, _ExecutionMethods, globals()
)
_CHAT_METHOD_NAMES = _bind_facade_methods(
    AgentOrchestrator, _ChatMethods, globals()
)
_PIPELINE_METHOD_NAMES = _bind_facade_methods(
    AgentOrchestrator, _PipelineMethods, globals()
)
_DASHBOARD_METHOD_NAMES = _bind_facade_methods(
    AgentOrchestrator, _DashboardMethods, globals()
)


# Common English words (2-5 uppercase letters) that should NOT be treated as
# US stock tickers.  This set is checked by _extract_stock_code() and should
# be kept at module level to avoid re-creating it on every call.
_COMMON_WORDS: set[str] = {
    # Pronouns / articles / prepositions / conjunctions
    "AM", "AS", "AT", "BE", "BY", "DO", "GO", "HE", "IF", "IN",
    "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR", "SO", "TO",
    "UP", "US", "WE",
    "THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL",
    "CAN", "HAD", "HER", "WAS", "ONE", "OUR", "OUT", "HAS",
    "HIS", "HOW", "ITS", "LET", "MAY", "NEW", "NOW", "OLD",
    "SEE", "WAY", "WHO", "DID", "GET", "HIM", "USE", "SAY",
    "SHE", "TOO", "ANY", "WITH", "FROM", "THAT", "THAN",
    "THIS", "WHAT", "WHEN", "WILL", "JUST", "ALSO",
    "BEEN", "EACH", "HAVE", "MUCH", "ONLY", "OVER",
    "SOME", "SUCH", "THEM", "THEN", "THEY", "VERY",
    "WERE", "YOUR", "ABOUT", "AFTER", "COULD", "EVERY",
    "OTHER", "THEIR", "THERE", "THESE", "THOSE", "WHICH",
    "WOULD", "BEING", "STILL", "WHERE",
    # Finance/analysis jargon that looks like tickers
    "BUY", "SELL", "HOLD", "LONG", "PUT", "CALL",
    "ETF", "IPO", "RSI", "EPS", "PEG", "ROE", "ROA",
    "USA", "USD", "CNY", "HKD", "EUR", "GBP",
    "STOCK", "TRADE", "PRICE", "INDEX", "FUND",
    "HIGH", "LOW", "OPEN", "CLOSE", "STOP", "LOSS",
    "TREND", "BULL", "BEAR", "RISK", "CASH", "BOND",
    "MACD", "VWAP", "BOLL", "KDJ",
    "TTM", "LTM", "NTM", "FWD", "YOY", "QOQ", "YTD",
    "EBIT", "EBITDA", "DCF", "CAGR", "FCF", "NAV", "AUM",
    "PE", "PB",
    # Greetings / filler words that often appear in chat messages
    "HELLO", "PLEASE", "THANKS", "CHECK", "LOOK", "THINK",
    "MAYBE", "GUESS", "TELL", "SHOW", "WHAT", "WHATS",
    "WHY", "WHEN", "HOWDY", "HEY", "HI",
}

_LOWERCASE_TICKER_HINTS = re.compile(
    r"分析|看看|查一?下|研究|诊断|走势|趋势|股价|股票|个股",
)


def _is_denied_ticker_candidate(candidate: str) -> bool:
    """Return whether a text token should not be auto-treated as a ticker."""
    return (candidate or "").strip().upper() in _COMMON_WORDS


def _extract_stock_code(text: str) -> str:
    """Best-effort stock code extraction from free text."""
    # A-share 6-digit — use lookarounds instead of \b because Python's \b
    # does not fire at Chinese-character / digit boundaries.
    m = re.search(r'(?<!\d)((?:[03648]\d{5}|92\d{4}))(?!\d)', text)
    if m:
        return m.group(1)
    # HK — same lookaround approach
    m = re.search(r'(?<![a-zA-Z])(hk\d{5})(?!\d)', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # US ticker — require 2+ uppercase letters bounded by non-alpha chars.
    for match in re.finditer(r'(?<![a-zA-Z])([A-Z]{2,5}(?:\.[A-Z]{1,2})?)(?![a-zA-Z])', text):
        candidate = match.group(1)
        if not _is_denied_ticker_candidate(candidate):
            return candidate

    stripped = (text or "").strip()
    bare_match = re.fullmatch(r'([A-Za-z]{2,5}(?:\.[A-Za-z]{1,2})?)', stripped)
    if bare_match:
        candidate = bare_match.group(1).upper()
        if not _is_denied_ticker_candidate(candidate):
            return candidate

    if not _LOWERCASE_TICKER_HINTS.search(stripped):
        return ""

    for match in re.finditer(r'(?<![a-zA-Z])([A-Za-z]{2,5}(?:\.[A-Za-z]{1,2})?)(?![a-zA-Z])', text):
        raw_candidate = match.group(1)
        candidate = raw_candidate.upper()
        if _is_denied_ticker_candidate(candidate):
            continue
        return candidate
    return ""


def _adjust_sentiment_score(score: int, signal: str) -> int:
    """Clamp sentiment score into the target band for the overridden signal."""
    bands = {
        "buy": (60, 79),
        "hold": (40, 59),
        "sell": (0, 39),
    }
    low, high = bands.get(signal, (0, 100))
    return max(low, min(high, score))


def _adjust_operation_advice(advice: str, signal: str) -> str:
    """Normalize action wording to the overridden decision signal."""
    mapping = {
        "buy": "买入",
        "hold": "观望",
        "sell": "减仓/卖出",
    }
    if signal not in mapping:
        return advice
    if advice == mapping[signal]:
        return advice
    return f"{mapping[signal]}（原建议已被风控下调）"


def _signal_to_operation(signal: str) -> str:
    mapping = {
        "buy": "买入",
        "hold": "观望",
        "sell": "减仓/卖出",
    }
    return mapping.get(signal, "观望")


def _signal_to_signal_type(signal: str) -> str:
    mapping = {
        "buy": "🟢买入信号",
        "hold": "⚪观望信号",
        "sell": "🔴卖出信号",
    }
    return mapping.get(signal, "⚪观望信号")


def _default_position_advice(signal: str) -> Dict[str, str]:
    mapping = {
        "buy": {
            "no_position": "可结合支撑位分批试仓，避免一次性追高。",
            "has_position": "可继续持有，回踩关键位不破再考虑加仓。",
        },
        "hold": {
            "no_position": "暂不追高，等待更清晰的入场条件。",
            "has_position": "以观察为主，跌破止损位再执行风控。",
        },
        "sell": {
            "no_position": "暂不参与，等待风险充分释放。",
            "has_position": "优先控制回撤，按计划减仓或离场。",
        },
    }
    return mapping.get(signal, mapping["hold"])


def _post_risk_position_advice(signal: str) -> Dict[str, str]:
    """Return authoritative position advice after an applied risk transition."""
    mapping = {
        "hold": {
            "no_position": "风险未解除前先观望，等待更清晰的入场条件。",
            "has_position": "谨慎持有并收紧止损，待风险缓解后再考虑加仓。",
        },
        "sell": {
            "no_position": "风险明显偏高，暂不新开仓。",
            "has_position": "优先控制回撤，建议减仓或退出高风险仓位。",
        },
    }
    return dict(mapping.get(signal, _default_position_advice(signal)))


def _default_position_size(signal: str) -> str:
    mapping = {
        "buy": "轻仓试仓",
        "hold": "控制仓位",
        "sell": "降仓防守",
    }
    return mapping.get(signal, "控制仓位")


def _normalize_operation_advice_value(value: Any, signal: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return _signal_to_operation(signal)


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.75:
        return "高"
    if confidence >= 0.45:
        return "中"
    return "低"


def _estimate_sentiment_score(signal: str, confidence: float) -> int:
    confidence = max(0.0, min(1.0, float(confidence)))
    bands = {
        "buy": (65, 79),
        "hold": (45, 59),
        "sell": (20, 39),
    }
    low, high = bands.get(signal, (45, 59))
    return int(round(low + (high - low) * confidence))


def _coerce_level_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    text = str(value).replace(",", "").replace("，", "").strip()
    if not text or text.upper() == "N/A" or text in {"-", "—"}:
        return None
    try:
        return round(float(text), 2)
    except ValueError:
        return text


def _pick_first_level(*values: Any) -> Any:
    for value in values:
        normalized = _coerce_level_value(value)
        if normalized is not None:
            return normalized
    return None


def _level_values_equal(left: Any, right: Any) -> bool:
    left_normalized = _coerce_level_value(left)
    right_normalized = _coerce_level_value(right)
    return (
        left_normalized is not None
        and right_normalized is not None
        and left_normalized == right_normalized
    )


def _first_non_empty_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _truncate_text(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _extract_latest_news_title(intelligence: Dict[str, Any]) -> str:
    key_news = intelligence.get("key_news")
    if isinstance(key_news, list):
        for item in key_news:
            if isinstance(item, dict):
                title = str(item.get("title", "")).strip()
                if title:
                    return title
    latest_news = intelligence.get("latest_news")
    if isinstance(latest_news, str) and latest_news.strip():
        return latest_news.strip()
    return ""
