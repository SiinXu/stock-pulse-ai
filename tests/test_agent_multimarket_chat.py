# -*- coding: utf-8 -*-
"""Focused regressions for market-aware Agent chat flows."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agent.chat_context import (
    AgentChatContextBundle,
    build_agent_chat_market_context,
)
from src.agent.conversation import ConversationSession
from src.agent.executor import AgentExecutor, AgentResult
from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.orchestrator import AgentOrchestrator, OrchestratorResult
from src.agent.runtime.guards import RuntimeGuardPolicy
from src.agent.stock_scope import resolve_stock_scope
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolRegistry
from src.market_context import detect_market
from src.services.stock_code_utils import canonicalize_analysis_stock_code


@pytest.mark.parametrize(
    ("raw", "expected_code", "expected_market"),
    [
        ("600519", "600519", "cn"),
        ("00700.HK", "HK00700", "hk"),
        ("aapl", "AAPL", "us"),
        ("7203.T", "7203.T", "jp"),
    ],
)
def test_shared_analysis_canonicalizer_covers_chat_markets(
    raw: str,
    expected_code: str,
    expected_market: str,
) -> None:
    code = canonicalize_analysis_stock_code(raw)

    assert code == expected_code
    assert detect_market(code) == expected_market


def test_hk_letter_tickers_are_not_misclassified_as_hong_kong_prefixes() -> None:
    assert canonicalize_analysis_stock_code("HKG") == "HKG"
    assert detect_market("HKG") == "us"
    assert detect_market("HK00700") == "hk"


def test_shared_canonicalizer_records_format_only_fallback(caplog) -> None:
    with patch(
        "src.services.stock_code_utils.resolve_index_stock_code_for_analysis",
        side_effect=RuntimeError("index unavailable"),
    ):
        code = canonicalize_analysis_stock_code("00700.HK")

    assert code == "HK00700"
    assert "stock_symbol_index_resolution_failed" in caplog.text


@pytest.mark.parametrize(
    ("message", "expected_code", "expected_market"),
    [
        ("分析 600519", "600519", "cn"),
        ("分析 00700.HK", "HK00700", "hk"),
        ("analyze AAPL", "AAPL", "us"),
        ("aapl", "AAPL", "us"),
    ],
)
def test_first_chat_turn_creates_canonical_stock_scope_without_context(
    message: str,
    expected_code: str,
    expected_market: str,
) -> None:
    resolution = resolve_stock_scope(message, None)

    assert resolution.effective_context["stock_code"] == expected_code
    assert resolution.stock_scope.mode == "switch"
    assert resolution.stock_scope.expected_stock_code == expected_code
    assert resolution.stock_scope.allowed_stock_codes == {expected_code}
    assert detect_market(expected_code) == expected_market


def test_first_chat_turn_builds_cross_market_compare_scope() -> None:
    resolution = resolve_stock_scope("比较 AAPL 和 00700.HK", None)

    assert resolution.effective_context == {}
    assert resolution.stock_scope.mode == "compare"
    assert resolution.stock_scope.expected_stock_code == ""
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL", "HK00700"}


@pytest.mark.parametrize("message", ["analyze AAPL", "switch to aapl"])
def test_explicit_english_switch_changes_the_active_symbol(message: str) -> None:
    resolution = resolve_stock_scope(
        message,
        {"stock_code": "HK00700", "stock_name": "Tencent"},
    )

    assert resolution.effective_context == {"stock_code": "AAPL", "stock_name": ""}
    assert resolution.stock_scope.mode == "switch"
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL"}


def test_english_analysis_topic_keeps_the_active_symbol() -> None:
    resolution = resolve_stock_scope(
        "Analyze capital flow",
        {"stock_code": "600519", "stock_name": "Kweichow Moutai"},
    )

    assert resolution.effective_context == {
        "stock_code": "600519",
        "stock_name": "Kweichow Moutai",
    }
    assert resolution.stock_scope.mode == "maintain"
    assert resolution.stock_scope.allowed_stock_codes == {"600519"}


@pytest.mark.parametrize(
    ("code", "currency", "timezone", "market_field"),
    [
        ("600519", "CNY", "Asia/Shanghai", "T+1"),
        ("HK00700", "HKD", "Asia/Hong_Kong", "每手股数"),
        ("AAPL", "USD", "America/New_York", "盘前/盘后价格"),
    ],
)
def test_market_context_exposes_canonical_market_specific_fields(
    code: str,
    currency: str,
    timezone: str,
    market_field: str,
) -> None:
    scope = resolve_stock_scope(f"分析 {code}", None).stock_scope

    market_context = build_agent_chat_market_context(
        {"stock_code": code},
        scope,
        "zh",
    )

    assert f"`{code}`" in market_context.prompt_section
    assert currency in market_context.prompt_section
    assert timezone in market_context.prompt_section
    assert market_field in market_context.prompt_section
    assert "不得编造或用 A 股默认值补齐" in market_context.prompt_section


def test_cross_market_context_keeps_hk_and_us_rules_separate() -> None:
    scope = resolve_stock_scope("比较 AAPL 和 00700.HK", None).stock_scope

    market_context = build_agent_chat_market_context({}, scope, "en")

    assert market_context.market_role == "cross-market"
    assert market_context.stock_codes == ("AAPL", "HK00700")
    assert "US stock (US)" in market_context.prompt_section
    assert "Hong Kong stock (HK)" in market_context.prompt_section
    assert "USD" in market_context.prompt_section
    assert "HKD" in market_context.prompt_section
    assert "Never substitute China A-share assumptions" in market_context.market_guidelines


def test_conversation_replays_active_symbol_and_clears_after_history_deletion() -> None:
    db = MagicMock()
    db.get_visible_conversation_messages.return_value = [
        {"role": "user", "content": "分析 AAPL"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "继续看估值"},
        {"role": "user", "content": "改看 00700.HK"},
        {"role": "assistant", "content": "second reply"},
    ]
    session = ConversationSession("market-session")
    session.update_market_context(
        {"stock_code": "AAPL", "stock_name": "Apple", "report_language": "en"}
    )

    with patch("src.agent.conversation.get_db", return_value=db):
        restored = session.get_market_context()
        db.get_visible_conversation_messages.return_value = []
        cleared = session.get_market_context()

    assert restored == {
        "stock_code": "HK00700",
        "report_language": "en",
    }
    assert cleared == {}
    assert session.context == {}


def _stock_registry(executed: list[str]) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_realtime_quote",
            description="Get a deterministic quote",
            parameters=[
                ToolParameter(
                    name="stock_code",
                    type="string",
                    description="Canonical stock code",
                )
            ],
            handler=lambda stock_code: executed.append(stock_code)
            or {"stock_code": stock_code, "price": 100},
        )
    )
    return registry


@pytest.mark.parametrize(
    ("message", "canonical_code", "market_marker"),
    [
        ("分析 600519", "600519", "CNY"),
        ("分析 00700.HK", "HK00700", "HKD"),
        ("analyze AAPL", "AAPL", "USD"),
    ],
)
def test_single_agent_chat_routes_canonical_symbol_through_real_tool_guard(
    message: str,
    canonical_code: str,
    market_marker: str,
) -> None:
    executed: list[str] = []
    adapter = MagicMock()
    adapter._config = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="quote-1",
                    name="get_realtime_quote",
                    arguments={"stock_code": canonical_code},
                )
            ],
            usage={},
            provider="openai",
            model="test-model",
        ),
        LLMResponse(
            content="deterministic answer",
            tool_calls=[],
            usage={},
            provider="openai",
            model="test-model",
        ),
    ]
    executor = AgentExecutor(_stock_registry(executed), adapter, max_steps=3)
    session = MagicMock()
    session.get_market_context.return_value = {}

    with patch(
        "src.agent.executor.build_agent_chat_context_bundle",
        return_value=AgentChatContextBundle(context_messages=[], diagnostics={}),
    ), patch(
        "src.agent.conversation.conversation_manager.get_or_create",
        return_value=session,
    ), patch(
        "src.agent.conversation.conversation_manager.add_message",
        side_effect=[1, 2],
    ), patch.object(executor, "_persist_provider_trace"):
        result = executor.chat(message, f"single-{canonical_code}")

    assert result.success is True
    assert executed == [canonical_code]
    first_messages = adapter.call_with_tools.call_args_list[0].args[0]
    rendered = "\n".join(str(item.get("content") or "") for item in first_messages)
    assert f"`{canonical_code}`" in rendered
    assert market_marker in rendered
    assert "[系统提供的本轮股票与市场上下文]" in rendered
    assert "[系统提供的历史分析上下文" not in rendered
    assert "好的，我会按本轮股票与市场上下文回答。" in rendered
    assert "已了解该股票的历史分析数据" not in rendered
    session.update_market_context.assert_called_once()


def test_single_agent_chat_reuses_active_us_symbol_on_followup() -> None:
    adapter = MagicMock()
    adapter._config = MagicMock()
    executor = AgentExecutor(ToolRegistry(), adapter, max_steps=2)
    session = MagicMock()
    session.get_market_context.side_effect = [
        {},
        {"stock_code": "AAPL", "stock_name": "Apple"},
    ]
    captured: list[tuple[object, list[dict]]] = []

    def fake_run_loop(messages, _tools, parse_dashboard, **kwargs):
        assert parse_dashboard is False
        captured.append((kwargs.get("stock_scope"), messages))
        return AgentResult(success=True, content="answer")

    with patch.object(executor, "_run_loop", side_effect=fake_run_loop), patch(
        "src.agent.executor.build_agent_chat_context_bundle",
        return_value=AgentChatContextBundle(context_messages=[], diagnostics={}),
    ), patch(
        "src.agent.conversation.conversation_manager.get_or_create",
        return_value=session,
    ), patch(
        "src.agent.conversation.conversation_manager.add_message",
        side_effect=[1, 2, 3, 4],
    ), patch.object(executor, "_persist_provider_trace"):
        executor.chat("分析 AAPL", "followup-us")
        executor.chat("继续看估值", "followup-us")

    assert [item[0].mode for item in captured] == ["switch", "maintain"]
    assert captured[1][0].expected_stock_code == "AAPL"
    assert captured[1][0].allowed_stock_codes == {"AAPL"}
    followup_text = "\n".join(
        str(message.get("content") or "") for message in captured[1][1]
    )
    assert "USD" in followup_text
    assert "America/New_York" in followup_text


def test_single_agent_chat_prefers_explicit_context_over_restored_symbol() -> None:
    adapter = MagicMock()
    adapter._config = MagicMock()
    executor = AgentExecutor(ToolRegistry(), adapter, max_steps=2)
    session = MagicMock()
    session.get_market_context.return_value = {
        "stock_code": "HK00700",
        "stock_name": "Tencent",
    }
    captured = {}

    def fake_run_loop(_messages, _tools, parse_dashboard, **kwargs):
        assert parse_dashboard is False
        captured["stock_scope"] = kwargs.get("stock_scope")
        return AgentResult(success=True, content="answer")

    with patch.object(executor, "_run_loop", side_effect=fake_run_loop), patch(
        "src.agent.executor.build_agent_chat_context_bundle",
        return_value=AgentChatContextBundle(context_messages=[], diagnostics={}),
    ), patch(
        "src.agent.conversation.conversation_manager.get_or_create",
        return_value=session,
    ), patch(
        "src.agent.conversation.conversation_manager.add_message",
        side_effect=[1, 2],
    ), patch.object(executor, "_persist_provider_trace"):
        executor.chat(
            "继续看估值",
            "explicit-context",
            context={"stock_code": "AAPL", "stock_name": "Apple"},
        )

    scope = captured["stock_scope"]
    assert scope.mode == "maintain"
    assert scope.expected_stock_code == "AAPL"
    assert scope.allowed_stock_codes == {"AAPL"}


def test_multi_agent_chat_injects_cross_market_context_into_each_stage() -> None:
    adapter = MagicMock()
    config = SimpleNamespace(agent_orchestrator_timeout_s=0)
    orchestrator = AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=adapter,
        config=config,
        runtime_guard_policy=RuntimeGuardPolicy(),
    )
    session = MagicMock()
    session.get_market_context.return_value = {}
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["context"] = ctx
        return OrchestratorResult(success=True, content="cross-market answer")

    with patch.object(orchestrator, "_execute_pipeline", side_effect=fake_execute), patch(
        "src.agent.orchestrator.build_visible_chat_history",
        return_value=[],
    ), patch(
        "src.agent.conversation.conversation_manager.get_or_create",
        return_value=session,
    ), patch(
        "src.agent.conversation.conversation_manager.add_message",
    ):
        result = orchestrator.chat(
            "比较 AAPL 和 00700.HK",
            "multi-cross-market",
        )

    assert result.success is True
    stock_scope = captured["context"].meta["stock_scope"]
    assert stock_scope.allowed_stock_codes == {"AAPL", "HK00700"}
    history = captured["context"].meta["conversation_history"]
    assert history[0]["role"] == "user"
    assert "USD" in history[0]["content"]
    assert "HKD" in history[0]["content"]
