# -*- coding: utf-8 -*-
"""Strict offline replay harness for agent-runtime characterization (AR-01).

This module freezes the *current* behaviour of the Native agent runtime by
replaying authored LLM transcripts through the real production code path:

* ``build_agent_executor`` (real factory, real skill prompt resolution)
* ``AgentExecutor`` / ``AgentOrchestrator`` (real pipeline code)
* ``run_agent_loop`` + ``ToolRegistry`` + tool execution + parsers +
  risk override (all real production code)

Only the LLM adapter is replaced, and it is deliberately *strict*:

* it serves the case transcript exactly in order;
* any call beyond the transcript raises ``AssertionError``;
* every tool call referenced by a transcript entry must be present in the
  tool schemas offered for that call (unless the entry explicitly marks the
  tool as intentionally unregistered);
* when a transcript entry declares ``allowed_stage`` the incoming system
  prompt must belong to that stage.

Fixtures live in ``tests/fixtures/agent_runtime/`` and are described by
``manifest.json``.  The ``expected`` block of every fixture is *recorded*
from an actual run (never hand-written): run

    python -m tests.agent_runtime_replay record

from the repository root to re-freeze all fixtures after an intentional
behaviour change.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

try:  # pragma: no cover - environment guard shared with existing agent tests
    import litellm  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    sys.modules["litellm"] = MagicMock()

from src.agent import factory as factory_module
from src.agent import llm_adapter as llm_adapter_module
from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolRegistry

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "agent_runtime"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"

# Stable prompt markers used to attribute each LLM call to a runtime stage.
# The single-agent markers match both AGENT_SYSTEM_PROMPT and the legacy
# default prompt (the factory picks the legacy prompt for the implicit
# builtin bull_trend activation, which is the default-config behaviour).
STAGE_MARKERS = (
    ("technical", "You are a **Technical Analysis Agent**"),
    ("intel", "You are an **Intelligence & Sentiment Agent**"),
    ("risk", "You are a **Risk Screening Agent**"),
    ("decision", "You are a **Decision Synthesis Agent**"),
    ("single_run", "负责生成专业的【决策仪表盘】分析报告"),
    ("single_chat", "负责解答用户的股票投资问题"),
)
_SKILL_STAGE_MARKER = "You are a **Skill Evaluation Agent**"
_SKILL_ID_PATTERN = re.compile(r'"skill_id":\s*"([^"]+)"')

# Errors whose text embeds wall-clock durations; frozen as prefixes.
_VOLATILE_ERROR_PATTERNS = (
    re.compile(r"^(Agent timed out after) .+$"),
    re.compile(r"^(Agent step skipped due to insufficient budget:) .+$"),
    re.compile(r"^(Pipeline timed out after) .+$"),
    re.compile(r"^(Pipeline skipped before stage '[^']+' due to insufficient budget) .+$"),
)


def detect_stage(system_text: str) -> str:
    """Map a system prompt to a stable stage name."""
    text = system_text or ""
    if _SKILL_STAGE_MARKER in text:
        match = _SKILL_ID_PATTERN.search(text)
        return f"skill_{match.group(1)}" if match else "skill_unknown"
    for stage, marker in STAGE_MARKERS:
        if marker in text:
            return stage
    return "unknown"


class ReplayLLMAdapter:
    """Strict transcript-serving fake for ``LLMToolAdapter.call_with_tools``."""

    def __init__(self, transcript: List[Dict[str, Any]], config: Any = None):
        self._transcript = [dict(entry) for entry in transcript]
        self._index = 0
        self._config = config
        self.calls: List[Dict[str, Any]] = []
        self.observed_stages: List[str] = []

    @property
    def consumed(self) -> int:
        return self._index

    @property
    def remaining(self) -> int:
        return len(self._transcript) - self._index

    def call_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        if self._index >= len(self._transcript):
            raise AssertionError(
                f"Replay transcript exhausted: call #{self._index + 1} requested "
                f"but only {len(self._transcript)} entries are available"
            )
        entry = self._transcript[self._index]
        self._index += 1

        system_text = ""
        if messages and messages[0].get("role") == "system":
            system_text = str(messages[0].get("content") or "")
        stage = detect_stage(system_text)
        self.observed_stages.append(stage)

        allowed_stage = entry.get("allowed_stage")
        if allowed_stage is not None and stage != allowed_stage:
            raise AssertionError(
                f"Transcript entry #{self._index} expected stage "
                f"'{allowed_stage}' but was called from stage '{stage}'"
            )

        raise_error = entry.get("raise_error")
        if raise_error:
            # Minimal failure hook: a transcript entry with "raise_error" makes
            # the adapter raise instead of answering, so contract fixtures can
            # characterize runtime fallback behavior when the LLM call itself
            # fails (e.g. provider outage mid-conversation).
            raise RuntimeError(str(raise_error))

        offered = {
            tool.get("function", {}).get("name")
            for tool in (tools or [])
            if isinstance(tool, dict)
        }
        for tool_call in entry.get("tool_calls") or []:
            name = tool_call.get("name")
            if tool_call.get("expect_unregistered"):
                continue
            if isinstance(name, str) and name not in offered:
                raise AssertionError(
                    f"Transcript entry #{self._index} references tool '{name}' "
                    f"that is not part of the offered tool schemas: {sorted(offered)}"
                )

        delay_s = entry.get("delay_s")
        if delay_s:
            time.sleep(float(delay_s))

        self.calls.append(
            {
                "stage": stage,
                "message_count": len(messages),
                "tools_offered": sorted(name for name in offered if name),
                "timeout": timeout,
            }
        )

        tool_calls = [
            ToolCall(
                id=str(tool_call.get("id", f"call_{self._index}_{position}")),
                name=tool_call.get("name"),
                arguments=dict(tool_call.get("arguments") or {}),
                thought_signature=tool_call.get("thought_signature"),
                provider_specific_fields=dict(
                    tool_call.get("provider_specific_fields") or {}
                ),
            )
            for position, tool_call in enumerate(entry.get("tool_calls") or [])
        ]
        return LLMResponse(
            content=entry.get("content"),
            tool_calls=tool_calls,
            reasoning_content=entry.get("reasoning_content"),
            provider_blocks=list(entry.get("provider_blocks") or []),
            usage=dict(entry.get("usage") or {}),
            provider=str(entry.get("provider", "")),
            model=str(entry.get("model", "")),
        )

    def call_text(self, *args: Any, **kwargs: Any) -> LLMResponse:
        raise AssertionError(
            "call_text is outside the replayed transcript; "
            "characterization cases must not trigger summary generation"
        )


# ---------------------------------------------------------------------------
# Deterministic local tool handlers (modelled on test_agent_executor.py)
# ---------------------------------------------------------------------------

def _stock_param() -> ToolParameter:
    return ToolParameter(name="stock_code", type="string", description="Stock code")


def build_replay_tool_registry(
    executed_calls: Optional[List[Dict[str, Any]]] = None,
) -> ToolRegistry:
    """Build a real ToolRegistry backed by deterministic offline handlers."""
    log: List[Dict[str, Any]] = executed_calls if executed_calls is not None else []
    registry = ToolRegistry()

    def _register(name: str, description: str, parameters: List[ToolParameter], handler):
        def wrapped(**kwargs: Any) -> Any:
            log.append({"tool": name, "arguments": dict(kwargs)})
            return handler(**kwargs)

        registry.register(
            ToolDefinition(
                name=name,
                description=description,
                parameters=parameters,
                handler=wrapped,
            )
        )

    _register(
        "get_realtime_quote",
        "Get real-time quote (synthetic fixture data)",
        [_stock_param()],
        lambda stock_code: {
            "stock_code": stock_code,
            "name": "Synthetic Co",
            "price": 100.0,
            "change_pct": 1.5,
            "volume_ratio": 1.2,
            "turnover_rate": 2.4,
        },
    )
    _register(
        "get_daily_history",
        "Get daily K-line history (synthetic fixture data)",
        [
            _stock_param(),
            ToolParameter(name="days", type="integer", description="Days", required=False, default=30),
        ],
        lambda stock_code, days=30: {
            "stock_code": stock_code,
            "bars": int(days),
            "close": [96.0, 97.5, 98.2, 99.1, 100.0],
        },
    )
    _register(
        "analyze_trend",
        "Analyze MA trend (synthetic fixture data)",
        [_stock_param()],
        lambda stock_code: {
            "stock_code": stock_code,
            "ma_alignment": "bullish",
            "trend_score": 78,
            "ma5": 99.0,
            "ma10": 97.5,
            "ma20": 95.0,
            "bias_ma5": 1.0,
            "current_price": 100.0,
            "volume_status": "normal",
        },
    )
    _register(
        "calculate_ma",
        "Calculate moving averages (synthetic fixture data)",
        [_stock_param()],
        lambda stock_code: {"stock_code": stock_code, "ma5": 99.0, "ma10": 97.5, "ma20": 95.0},
    )
    _register(
        "get_volume_analysis",
        "Volume analysis (synthetic fixture data)",
        [_stock_param()],
        lambda stock_code: {"stock_code": stock_code, "volume_status": "normal", "volume_ratio": 1.2},
    )
    _register(
        "analyze_pattern",
        "K-line pattern analysis (synthetic fixture data)",
        [_stock_param()],
        lambda stock_code: {"stock_code": stock_code, "pattern": "ascending_channel"},
    )
    _register(
        "get_chip_distribution",
        "Chip distribution (synthetic fixture data)",
        [_stock_param()],
        lambda stock_code: {
            "stock_code": stock_code,
            "profit_ratio": 0.62,
            "avg_cost": 92.0,
            "concentration_90": 0.12,
        },
    )
    _register(
        "get_analysis_context",
        "Analysis context pack (synthetic fixture data)",
        [_stock_param()],
        lambda stock_code: {"stock_code": stock_code, "summary": "synthetic context pack"},
    )
    _register(
        "search_stock_news",
        "Search stock news (synthetic fixture data)",
        [_stock_param()],
        lambda stock_code: {
            "stock_code": stock_code,
            "items": [
                {"title": "Synthetic quarterly report beats estimates", "sentiment": "positive"},
                {"title": "Synthetic sector policy update", "sentiment": "neutral"},
            ],
        },
    )
    _register(
        "search_comprehensive_intel",
        "Comprehensive intel search (synthetic fixture data)",
        [_stock_param()],
        lambda stock_code: {"stock_code": stock_code, "intel": ["synthetic announcement"]},
    )
    _register(
        "get_stock_info",
        "Stock fundamental info (synthetic fixture data)",
        [_stock_param()],
        lambda stock_code: {"stock_code": stock_code, "pe": 21.5, "pb": 3.1, "industry": "Synthetic"},
    )
    _register(
        "get_capital_flow",
        "Capital flow (synthetic fixture data)",
        [_stock_param()],
        lambda stock_code: {"stock_code": stock_code, "main_inflow": 1234.5},
    )
    _register(
        "echo",
        "Echo a message (synthetic fixture data)",
        [ToolParameter(name="message", type="string", description="Message")],
        lambda message: {"echo": message},
    )
    _register(
        "slow_tool",
        "Sleep for a while (used to characterize late tool results)",
        [ToolParameter(name="seconds", type="number", description="Sleep seconds")],
        lambda seconds: (time.sleep(float(seconds)) or {"slept": float(seconds)}),
    )

    def _failing_tool() -> Dict[str, Any]:
        raise RuntimeError("synthetic handler failure")

    _register("failing_tool", "Always fails (synthetic fixture data)", [], _failing_tool)
    return registry


# ---------------------------------------------------------------------------
# Case configuration and execution
# ---------------------------------------------------------------------------

BASE_CONFIG_FIELDS: Dict[str, Any] = {
    "agent_arch": "single",
    "agent_orchestrator_mode": "standard",
    "agent_max_steps": 10,
    "agent_orchestrator_timeout_s": 0,
    "agent_skills": None,
    "agent_skill_dir": None,
    "agent_risk_override": True,
    "agent_memory_enabled": False,
    "agent_context_compression_enabled": False,
    "agent_context_compression_profile": "balanced",
    "agent_context_compression_trigger_tokens": 999999,
    "agent_context_protected_turns": 1,
    "llm_model_list": [],
    "agent_litellm_model": "openai/gpt-4o-mini",
    "litellm_model": "openai/gpt-4o-mini",
    "litellm_fallback_models": [],
}


def make_case_config(case: Dict[str, Any]) -> SimpleNamespace:
    fields = dict(BASE_CONFIG_FIELDS)
    fields.update(case.get("config") or {})
    return SimpleNamespace(**fields)


def load_manifest() -> Dict[str, Any]:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_case(relative_path: str) -> Dict[str, Any]:
    with open(FIXTURES_DIR / relative_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def iter_manifest_cases():
    manifest = load_manifest()
    for entry in manifest["cases"]:
        yield entry


def _is_chat_case(case: Dict[str, Any]) -> bool:
    return "message" in case["input"]


def run_case(case: Dict[str, Any]):
    """Run one fixture case through the real factory-built runtime.

    Returns ``(result, adapter, executed_tools, chat_artifacts)``.
    ``chat_artifacts`` is ``None`` for non-chat cases.
    """
    config = make_case_config(case)
    executed_tools: List[Dict[str, Any]] = []
    registry = build_replay_tool_registry(executed_tools)
    adapter = ReplayLLMAdapter(case["transcript"], config=config)

    chat = _is_chat_case(case)
    db = None
    if chat:
        from src.config import Config
        from src.storage import DatabaseManager

        DatabaseManager.reset_instance()
        Config.reset_instance()
        db = DatabaseManager(db_url="sqlite:///:memory:")

    try:
        with patch.object(
            llm_adapter_module, "LLMToolAdapter", new=lambda cfg: adapter
        ), patch.object(factory_module, "get_tool_registry", new=lambda: registry):
            executor = factory_module.build_agent_executor(config)
            payload = case["input"]
            if chat:
                result = executor.chat(
                    payload["message"],
                    payload["session_id"],
                    context=payload.get("context"),
                )
            else:
                result = executor.run(payload["task"], context=payload.get("context"))

        chat_artifacts = None
        if chat:
            session_id = case["input"]["session_id"]
            conversation = [
                {"role": row.get("role"), "content": row.get("content")}
                for row in db.get_visible_conversation_messages(session_id)
            ]
            provider_turns = [
                {
                    "provider": row.get("provider"),
                    "model": row.get("model"),
                    "contains_reasoning": bool(row.get("contains_reasoning")),
                    "contains_tool_calls": bool(row.get("contains_tool_calls")),
                    "message_roles": [
                        msg.get("role") for msg in (row.get("messages") or [])
                    ],
                }
                for row in db.get_agent_provider_turns(session_id)
            ]
            chat_artifacts = {
                "conversation": conversation,
                "provider_turns": provider_turns,
            }
        return result, adapter, executed_tools, chat_artifacts
    finally:
        if chat:
            from src.config import Config
            from src.storage import DatabaseManager

            DatabaseManager.reset_instance()
            Config.reset_instance()


def _normalize_tool_log(tool_calls_log: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop wall-clock fields from the tool log while keeping its contract."""
    normalized = []
    for entry in tool_calls_log or []:
        row = {key: value for key, value in entry.items() if key != "duration"}
        normalized.append(row)
    return normalized


def _normalize_error(error: Optional[str]) -> Dict[str, Any]:
    """Return ``{"error": ...}`` or ``{"error_prefix": ...}`` for volatile text."""
    if not error:
        return {"error": error}
    for pattern in _VOLATILE_ERROR_PATTERNS:
        match = pattern.match(error)
        if match:
            return {"error_prefix": match.group(1)}
    return {"error": error}


def observe_case(case: Dict[str, Any]) -> Dict[str, Any]:
    """Run a case and return the frozen ``expected`` payload."""
    result, adapter, _executed_tools, chat_artifacts = run_case(case)

    dashboard = result.dashboard if isinstance(result.dashboard, dict) else None
    observed: Dict[str, Any] = {
        "success": result.success,
        "signal": dashboard.get("decision_type") if dashboard else None,
        "stage_sequence": list(adapter.observed_stages),
        "transcript_fully_consumed": adapter.remaining == 0,
        "tool_calls": _normalize_tool_log(result.tool_calls_log),
        "total_steps": result.total_steps,
        "total_tokens": result.total_tokens,
        "provider": result.provider,
        "model": result.model,
        "dashboard_keys": sorted(dashboard.keys()) if dashboard else None,
        "dashboard": dashboard,
        "content": result.content,
    }
    observed.update(_normalize_error(result.error))
    if chat_artifacts is not None:
        observed["conversation"] = chat_artifacts["conversation"]
        observed["provider_turns"] = chat_artifacts["provider_turns"]
    return observed


def record_all_cases() -> None:
    """Re-freeze the ``expected`` block of every fixture from an actual run."""
    manifest = load_manifest()
    for entry in manifest["cases"]:
        path = FIXTURES_DIR / entry["file"]
        with open(path, "r", encoding="utf-8") as fh:
            case = json.load(fh)
        case["expected"] = observe_case(case)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(case, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"recorded: {entry['file']}")


if __name__ == "__main__":  # pragma: no cover - manual recording entrypoint
    if len(sys.argv) > 1 and sys.argv[1] == "record":
        record_all_cases()
    else:
        print("Usage: python -m tests.agent_runtime_replay record")
