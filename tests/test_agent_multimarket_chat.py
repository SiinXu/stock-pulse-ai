# -*- coding: utf-8 -*-
"""Focused regressions for market-aware Agent chat flows."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agent.chat_context import (
    AgentChatContextBundle,
    build_agent_chat_market_context,
    build_agent_chat_tool_registry,
)
from src.agent.conversation import ConversationSession
from src.agent.executor import AgentExecutor, AgentResult
from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.orchestrator import AgentOrchestrator, OrchestratorResult
from src.agent.runner import RunLoopResult
from src.agent.runtime.guards import RuntimeGuardPolicy
from src.agent.stock_scope import resolve_stock_scope
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolRegistry
from src.market_context import detect_market
from src.services.stock_code_utils import canonicalize_analysis_stock_code


_COLLISION_TICKERS = ("BJ", "BOLL", "EMA", "MA", "RSI", "SH", "SMA", "VS")


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
        ("analyze SH600519", "600519", "cn"),
        ("analyze SZ000001", "000001", "cn"),
        ("analyze BJ920748", "920748", "cn"),
        ("analyze 600519.SH", "600519", "cn"),
        ("analyze 000001.SZ", "000001", "cn"),
        ("分析 00700.HK", "HK00700", "hk"),
        ("analyze HK700", "HK00700", "hk"),
        ("analyze hk700", "HK00700", "hk"),
        ("analyze HK.700", "HK00700", "hk"),
        ("analyze hk.700", "HK00700", "hk"),
        ("analyze AAPL", "AAPL", "us"),
        ("analyze F", "F", "us"),
        ("分析 F", "F", "us"),
        ("switch to T", "T", "us"),
        ("analyze ON", "ON", "us"),
        ("analyze SH", "SH", "us"),
        ("analyze BJ", "BJ", "us"),
        ("analyze BOLL", "BOLL", "us"),
        ("analyze EMA", "EMA", "us"),
        ("analyze MA", "MA", "us"),
        ("analyze SMA", "SMA", "us"),
        ("analyze VS", "VS", "us"),
        ("analyze RSI", "RSI", "us"),
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


@pytest.mark.parametrize(
    "message",
    [
        "analyze SH000001",
        "analyze SZ600519",
        "analyze BJ600519",
        "analyze HK600519",
        "analyze 00700.SH",
        "analyze 600519.HK",
        "analyze SH600519X",
        "analyze 600519HK",
        "analyze 600519.HKX",
        "analyze A600519",
        "analyze order600519x",
        "analyze HK00700X",
        "analyze 00700SH",
    ],
)
def test_invalid_exchange_qualified_token_is_not_reinterpreted(
    message: str,
) -> None:
    resolution = resolve_stock_scope(message, None)

    assert resolution.effective_context == {}
    assert resolution.stock_scope is None


@pytest.mark.parametrize("stock_code", _COLLISION_TICKERS)
def test_bare_collision_ticker_creates_explicit_scope(stock_code: str) -> None:
    resolution = resolve_stock_scope(stock_code, None)

    assert resolution.effective_context == {
        "stock_code": stock_code,
        "stock_name": "",
    }
    assert resolution.stock_scope.mode == "switch"
    assert resolution.stock_scope.allowed_stock_codes == {stock_code}


@pytest.mark.parametrize("stock_code", ["pltr", "shop", "uber", "crm"])
def test_bare_indexed_lowercase_ticker_creates_scope(stock_code: str) -> None:
    resolution = resolve_stock_scope(stock_code, None)
    expected_code = stock_code.upper()

    assert resolution.effective_context == {
        "stock_code": expected_code,
        "stock_name": "",
    }
    assert resolution.stock_scope.mode == "switch"
    assert resolution.stock_scope.allowed_stock_codes == {expected_code}


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("analyze SH fundamentals", "SH"),
        ("review BJ earnings", "BJ"),
        ("look at VS valuation", "VS"),
        ("分析 RSI 的走势", "RSI"),
        ("switch to ON for earnings", "ON"),
        ("analyze aapl fundamentals", "AAPL"),
        ("analyse aapl", "AAPL"),
        ("review aapl", "AAPL"),
        ("look at aapl", "AAPL"),
        ("review brk.b", "BRK.B"),
        ("look at aapl.us", "AAPL.US"),
        ("analyze pltr", "PLTR"),
        ("review shop earnings", "SHOP"),
        ("look at uber valuation", "UBER"),
    ],
)
def test_explicit_command_slot_allows_trailing_analysis_prose(
    message: str,
    expected_code: str,
) -> None:
    resolution = resolve_stock_scope(message, None)

    assert resolution.effective_context["stock_code"] == expected_code
    assert resolution.stock_scope.mode == "switch"
    assert resolution.stock_scope.allowed_stock_codes == {expected_code}


def test_lowercase_command_slot_fails_closed_without_stock_index() -> None:
    with patch(
        "src.agent.stock_scope.get_stock_name_index_map",
        return_value={},
    ):
        resolution = resolve_stock_scope("analyze pltr", None)

    assert resolution.effective_context == {}
    assert resolution.stock_scope is None


def test_first_chat_turn_builds_cross_market_compare_scope() -> None:
    resolution = resolve_stock_scope("比较 AAPL 和 00700.HK", None)

    assert resolution.effective_context == {}
    assert resolution.stock_scope.mode == "compare"
    assert resolution.stock_scope.expected_stock_code == ""
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL", "HK00700"}


@pytest.mark.parametrize(
    ("message", "expected_codes"),
    [
        ("compare AAPL vs TSLA", {"AAPL", "TSLA"}),
        ("compare F vs T", {"F", "T"}),
        ("compare aapl and tsla", {"AAPL", "TSLA"}),
        ("比较 F 和 00700.HK", {"F", "HK00700"}),
        ("compare 600519 and T", {"600519", "T"}),
        ("compare 600519 and t", {"600519", "T"}),
        ("compare pltr and aapl", {"PLTR", "AAPL"}),
        ("compare SH and AAPL", {"SH", "AAPL"}),
        ("比较 BJ 和 AAPL", {"BJ", "AAPL"}),
    ],
)
def test_english_compare_connector_is_not_treated_as_a_ticker(
    message: str,
    expected_codes: set[str],
) -> None:
    resolution = resolve_stock_scope(message, None)

    assert resolution.effective_context == {}
    assert resolution.stock_scope.mode == "compare"
    assert resolution.stock_scope.allowed_stock_codes == expected_codes


@pytest.mark.parametrize("stock_code", _COLLISION_TICKERS + ("ON",))
def test_uppercase_ticker_in_letter_comparison_slot(stock_code: str) -> None:
    resolution = resolve_stock_scope(f"compare {stock_code} and AAPL", None)

    assert resolution.effective_context == {}
    assert resolution.stock_scope.mode == "compare"
    assert resolution.stock_scope.allowed_stock_codes == {stock_code, "AAPL"}


@pytest.mark.parametrize(
    ("message", "expected_codes"),
    [
        ("compare 600519 and SH", {"600519", "SH"}),
        ("compare SH and 600519", {"600519", "SH"}),
        ("600519 vs SH", {"600519", "SH"}),
        ("compare HK00700 and BJ", {"HK00700", "BJ"}),
        ("compare 600519 and ON", {"600519", "ON"}),
        ("compare ON and 600519", {"600519", "ON"}),
        ("compare 600519 and pltr", {"600519", "PLTR"}),
        ("compare AAPL with RSI", {"AAPL", "RSI"}),
    ],
)
def test_uppercase_ticker_in_mixed_comparison_slot(
    message: str,
    expected_codes: set[str],
) -> None:
    resolution = resolve_stock_scope(message, None)

    assert resolution.effective_context == {}
    assert resolution.stock_scope.mode == "compare"
    assert resolution.stock_scope.allowed_stock_codes == expected_codes


def test_comparison_prose_does_not_authorize_lowercase_nouns() -> None:
    messages = [
        "compare it with value",
        "compare its debt with peers",
        "compare yield with debt",
        "compare rates with bonds",
        "compare valuation with peers",
    ]

    for message in messages:
        resolution = resolve_stock_scope(
            message,
            {"stock_code": "AAPL", "stock_name": "Apple"},
        )

        assert resolution.effective_context == {
            "stock_code": "AAPL",
            "stock_name": "Apple",
        }
        assert resolution.stock_scope.mode == "maintain"
        assert resolution.stock_scope.allowed_stock_codes == {"AAPL"}


def test_english_compare_prose_keeps_only_explicit_uppercase_symbols() -> None:
    resolution = resolve_stock_scope(
        "how does AAPL compare with MSFT?",
        None,
    )

    assert resolution.effective_context == {}
    assert resolution.stock_scope.mode == "compare"
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL", "MSFT"}


def test_lowercase_prose_in_switch_slot_is_not_a_ticker() -> None:
    resolution = resolve_stock_scope("switch to rates", None)

    assert resolution.effective_context == {}
    assert resolution.stock_scope is None


def test_explicit_compare_replaces_a_stale_active_symbol_scope() -> None:
    resolution = resolve_stock_scope(
        "AAPL 和 TSLA 哪个更值得买",
        {
            "stock_code": "600519",
            "stock_name": "Kweichow Moutai",
            "previous_analysis_summary": "stale summary",
            "daily_market_context": {
                "region": "cn",
                "summary": "A-share market risk-off",
            },
            "report_language": "zh",
        },
    )

    assert resolution.effective_context == {"report_language": "zh"}
    assert resolution.stock_scope.mode == "compare"
    assert resolution.stock_scope.expected_stock_code == ""
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL", "TSLA"}


def test_english_compare_with_adds_to_the_active_symbol_scope() -> None:
    resolution = resolve_stock_scope(
        "compare with tsla",
        {"stock_code": "AAPL", "stock_name": "Apple"},
    )

    assert resolution.effective_context == {
        "stock_code": "AAPL",
        "stock_name": "Apple",
    }
    assert resolution.stock_scope.mode == "compare"
    assert resolution.stock_scope.expected_stock_code == ""
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL", "TSLA"}


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("compare with RSI", "RSI"),
        ("compare it with VS", "VS"),
        ("compare with ON", "ON"),
        ("compare it with ON", "ON"),
        ("compare with crm", "CRM"),
    ],
)
def test_active_compare_with_accepts_uppercase_ticker_slot(
    message: str,
    expected_code: str,
) -> None:
    resolution = resolve_stock_scope(
        message,
        {"stock_code": "AAPL", "stock_name": "Apple"},
    )

    assert resolution.effective_context == {
        "stock_code": "AAPL",
        "stock_name": "Apple",
    }
    assert resolution.stock_scope.mode == "compare"
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL", expected_code}


@pytest.mark.parametrize(
    "message",
    [
        "analyze VS",
        "analyze VS fundamentals",
        "switch to VS",
        "review VS",
        "look at VS valuation",
    ],
)
def test_active_explicit_vs_ticker_switches_instead_of_comparing(
    message: str,
) -> None:
    resolution = resolve_stock_scope(
        message,
        {"stock_code": "AAPL", "stock_name": "Apple"},
    )

    assert resolution.effective_context == {
        "stock_code": "VS",
        "stock_name": "",
    }
    assert resolution.stock_scope.mode == "switch"
    assert resolution.stock_scope.allowed_stock_codes == {"VS"}


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("AAPL versus MSFT", "MSFT"),
        ("compared with MSFT", "MSFT"),
        ("AAPL VS TSLA", "TSLA"),
        ("AAPL Vs TSLA", "TSLA"),
    ],
)
def test_english_comparison_variants_use_active_symbol(
    message: str,
    expected_code: str,
) -> None:
    resolution = resolve_stock_scope(
        message,
        {"stock_code": "AAPL", "stock_name": "Apple"},
    )

    assert resolution.effective_context == {
        "stock_code": "AAPL",
        "stock_name": "Apple",
    }
    assert resolution.stock_scope.mode == "compare"
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL", expected_code}


@pytest.mark.parametrize("message", ["analyze AAPL", "switch to aapl"])
def test_explicit_english_switch_changes_the_active_symbol(message: str) -> None:
    resolution = resolve_stock_scope(
        message,
        {"stock_code": "HK00700", "stock_name": "Tencent"},
    )

    assert resolution.effective_context == {"stock_code": "AAPL", "stock_name": ""}
    assert resolution.stock_scope.mode == "switch"
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL"}


def test_switch_clears_stale_daily_market_context() -> None:
    resolution = resolve_stock_scope(
        "analyze AAPL",
        {
            "stock_code": "600519",
            "stock_name": "Kweichow Moutai",
            "daily_market_context": {
                "region": "cn",
                "summary": "A-share market risk-off",
            },
            "report_language": "en",
        },
    )

    assert resolution.effective_context == {
        "stock_code": "AAPL",
        "stock_name": "",
        "report_language": "en",
    }
    assert resolution.stock_scope.mode == "switch"


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
    "message",
    [
        "analyze it",
        "review the valuation",
        "look at this",
        "switch to it",
        "Review rates",
        "review debt",
        "review yield",
        "review value",
    ],
)
def test_lowercase_switch_slot_common_words_do_not_become_tickers(
    message: str,
) -> None:
    resolution = resolve_stock_scope(
        message,
        {"stock_code": "AAPL", "stock_name": "Apple"},
    )

    assert resolution.effective_context == {
        "stock_code": "AAPL",
        "stock_name": "Apple",
    }
    assert resolution.stock_scope.mode == "maintain"
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL"}


@pytest.mark.parametrize(
    ("message", "stock_code", "stock_name"),
    [
        ("continue with the valuation", "BOLL", "Established symbol"),
        ("continue with the valuation", "EMA", "Established symbol"),
        ("continue with the valuation", "MA", "Mastercard"),
        ("continue with the valuation", "RSI", "Rush Street Interactive"),
        ("RSI 指标怎么样", "RSI", "Rush Street Interactive"),
        ("continue with the valuation", "SH", "ProShares Short S&P 500"),
        ("continue with the valuation", "BJ", "BJ's Wholesale Club"),
        ("continue with the valuation", "SMA", "Established symbol"),
        ("continue with the valuation", "VS", "Versus Systems"),
    ],
)
def test_trusted_active_ticker_is_preserved(
    message: str,
    stock_code: str,
    stock_name: str,
) -> None:
    resolution = resolve_stock_scope(
        message,
        {"stock_code": stock_code, "stock_name": stock_name},
    )

    assert resolution.effective_context == {
        "stock_code": stock_code,
        "stock_name": stock_name,
    }
    assert resolution.stock_scope.mode == "maintain"
    assert resolution.stock_scope.allowed_stock_codes == {stock_code}


@pytest.mark.parametrize(
    "stock_code",
    ["HK", "KDJ", "NOT-A-SYMBOL", "", None, 0, ["AAPL"]],
)
def test_public_context_reserved_token_is_not_trusted(stock_code: object) -> None:
    resolution = resolve_stock_scope(
        "continue with the valuation",
        {"stock_code": stock_code, "stock_name": "untrusted"},
    )

    assert resolution.effective_context == {}
    assert resolution.stock_scope.mode == "maintain"
    assert resolution.stock_scope.expected_stock_code == ""
    assert resolution.stock_scope.allowed_stock_codes == set()


@pytest.mark.parametrize("message", ["analyze HK", "analyze KDJ", "KDJ"])
def test_reserved_token_is_not_an_explicit_ticker(message: str) -> None:
    resolution = resolve_stock_scope(message, None)

    assert resolution.effective_context == {}
    assert resolution.stock_scope is None


@pytest.mark.parametrize(
    "message",
    [
        "what is MA telling us?",
        "explain the MA indicator",
        "MA crossover",
        "analyze MA indicator",
        "分析 MA 均线",
    ],
)
def test_indicator_prose_does_not_create_contextless_ticker_scope(
    message: str,
) -> None:
    resolution = resolve_stock_scope(message, None)

    assert resolution.effective_context == {}
    assert resolution.stock_scope is None


def test_indicator_token_in_free_text_does_not_switch_the_active_symbol() -> None:
    resolution = resolve_stock_scope(
        "what is RSI telling us?",
        {"stock_code": "AAPL", "stock_name": "Apple"},
    )

    assert resolution.effective_context == {
        "stock_code": "AAPL",
        "stock_name": "Apple",
    }
    assert resolution.stock_scope.mode == "maintain"
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL"}


def test_english_first_person_pronoun_is_not_treated_as_a_ticker() -> None:
    resolution = resolve_stock_scope("I think AAPL looks expensive", None)

    assert resolution.effective_context["stock_code"] == "AAPL"
    assert resolution.stock_scope.mode == "switch"
    assert resolution.stock_scope.allowed_stock_codes == {"AAPL"}


def test_lowercase_first_person_pronoun_is_not_a_compare_ticker() -> None:
    resolution = resolve_stock_scope("compare i and 600519", None)

    assert resolution.effective_context["stock_code"] == "600519"
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


def _market_capability_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for name in (
        "get_realtime_quote",
        "get_chip_distribution",
        "get_capital_flow",
        "get_sector_rankings",
    ):
        registry.register(
            ToolDefinition(
                name=name,
                description=name,
                parameters=[
                    ToolParameter(
                        name="stock_code",
                        type="string",
                        description="Canonical stock code",
                    )
                ],
                handler=lambda stock_code: {"stock_code": stock_code},
            )
        )
    return registry


@pytest.mark.parametrize(
    ("message", "context", "expected_names"),
    [
        (
            "分析 600519",
            {"stock_code": "600519"},
            {
                "get_realtime_quote",
                "get_chip_distribution",
                "get_capital_flow",
                "get_sector_rankings",
            },
        ),
        ("analyze AAPL", {"stock_code": "AAPL"}, {"get_realtime_quote"}),
        ("分析 00700.HK", {"stock_code": "HK00700"}, {"get_realtime_quote"}),
        ("比较 600519 和 AAPL", {}, {"get_realtime_quote"}),
    ],
)
def test_chat_tool_registry_applies_market_capability_matrix(
    message: str,
    context: dict,
    expected_names: set[str],
) -> None:
    scope = resolve_stock_scope(message, context or None).stock_scope
    market_context = build_agent_chat_market_context(context, scope, "zh")

    registry = build_agent_chat_tool_registry(
        _market_capability_registry(),
        market_context,
    )

    assert set(registry.list_names()) == expected_names


def test_single_agent_us_chat_hides_a_share_only_tools() -> None:
    adapter = MagicMock()
    adapter._config = MagicMock()
    adapter.call_with_tools.return_value = LLMResponse(
        content="deterministic answer",
        tool_calls=[],
        usage={},
        provider="openai",
        model="test-model",
    )
    executor = AgentExecutor(_market_capability_registry(), adapter, max_steps=2)
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
        result = executor.chat("analyze AAPL", "us-capability")

    assert result.success is True
    first_messages, first_tools = adapter.call_with_tools.call_args_list[0].args[:2]
    exposed_names = {tool["function"]["name"] for tool in first_tools}
    rendered = "\n".join(str(item.get("content") or "") for item in first_messages)
    assert exposed_names == {"get_realtime_quote"}
    assert "本轮不暴露这些工具" in rendered
    assert "调用 `get_chip_distribution`" not in rendered


@pytest.mark.parametrize(
    "message",
    ["analyze AAPL", "分析 00700.HK"],
)
def test_single_agent_non_cn_chat_cannot_dispatch_fully_filtered_tool(
    message: str,
) -> None:
    executed: list[str] = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_sector_rankings",
            description="A-share sector rankings",
            parameters=[],
            handler=lambda: executed.append("get_sector_rankings") or {"sectors": []},
        )
    )
    adapter = MagicMock()
    adapter._config = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id="sector-1",
                    name="get_sector_rankings",
                    arguments={},
                )
            ],
            usage={},
            provider="openai",
            model="test-model",
        ),
        LLMResponse(
            content="continued without A-share sector data",
            tool_calls=[],
            usage={},
            provider="openai",
            model="test-model",
        ),
    ]
    executor = AgentExecutor(registry, adapter, max_steps=3)
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
        result = executor.chat(message, f"fully-filtered-{message}")

    assert result.success is True
    assert adapter.call_with_tools.call_args_list[0].args[1] == []
    assert executed == []
    assert result.tool_calls_log[0]["tool"] == "get_sector_rankings"
    assert result.tool_calls_log[0]["success"] is False


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


def test_multi_agent_chat_runs_each_comparison_symbol_in_its_own_scope() -> None:
    adapter = MagicMock()
    config = SimpleNamespace(agent_orchestrator_timeout_s=0)
    orchestrator = AgentOrchestrator(
        tool_registry=_market_capability_registry(),
        llm_adapter=adapter,
        config=config,
        runtime_guard_policy=RuntimeGuardPolicy(),
    )
    session = MagicMock()
    session.get_market_context.return_value = {}
    captured = []

    def fake_execute(ctx, **_kwargs):
        captured.append(ctx)
        return OrchestratorResult(success=True, content=f"analysis for {ctx.stock_code}")

    adapter.call_with_tools.return_value = LLMResponse(
        content="cross-market synthesis",
        tool_calls=[],
        usage={},
        provider="openai",
        model="test-model",
    )

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
    assert result.content == "cross-market synthesis"
    assert [ctx.stock_code for ctx in captured] == ["AAPL", "HK00700"]
    for ctx in captured:
        stock_scope = ctx.meta["stock_scope"]
        assert stock_scope.mode == "switch"
        assert stock_scope.expected_stock_code == ctx.stock_code
        assert stock_scope.allowed_stock_codes == {ctx.stock_code}
        history = ctx.meta["conversation_history"]
        assert history[0]["role"] == "user"
        assert f"`{ctx.stock_code}`" in history[0]["content"]
        chat_registry = orchestrator._tool_registry_for_context(ctx)
        assert set(chat_registry.list_names()) == {"get_realtime_quote"}
        technical_agent = orchestrator._build_agent_chain(ctx)[0]
        assert technical_agent.tool_names == ["get_realtime_quote"]
        assert "chip distribution is unavailable" in technical_agent.system_prompt(ctx)
    synthesis_messages, synthesis_tools = adapter.call_with_tools.call_args.args[:2]
    synthesis_text = "\n".join(
        str(message.get("content") or "") for message in synthesis_messages
    )
    assert synthesis_tools == []
    assert "AAPL" in synthesis_text
    assert "HK00700" in synthesis_text
    session.update_market_context.assert_called_once_with({})


def test_multi_agent_compare_shares_one_runtime_budget() -> None:
    adapter = MagicMock()
    config = SimpleNamespace(agent_orchestrator_timeout_s=1)
    orchestrator = AgentOrchestrator(
        tool_registry=_market_capability_registry(),
        llm_adapter=adapter,
        config=config,
        runtime_guard_policy=RuntimeGuardPolicy(),
    )
    scope = resolve_stock_scope("比较 AAPL 和 00700.HK", None).stock_scope
    market_context = build_agent_chat_market_context({}, scope, "zh")
    executed: list[str] = []

    def fake_execute(ctx, **_kwargs):
        executed.append(ctx.stock_code)
        return OrchestratorResult(
            success=True,
            content=f"analysis for {ctx.stock_code}",
        )

    with patch.object(
        orchestrator,
        "_execute_pipeline",
        side_effect=fake_execute,
    ), patch(
        "src.agent.orchestrator.time.monotonic",
        side_effect=[0.0, 0.0, 2.0],
    ):
        result = orchestrator._execute_multi_symbol_chat(
            message="比较 AAPL 和 00700.HK",
            session_id="shared-budget",
            context={},
            stock_scope=scope,
            history=[],
            market_context=market_context,
            report_language="zh",
            progress_callback=None,
            cancelled_check=None,
        )

    assert executed == ["AAPL"]
    assert result.success is True
    assert result.timed_out is True
    assert "逐标的分析" in result.content
    assert "AAPL" in result.content
    assert "## HK00700" in result.content
    assert "不可用" in result.content
    assert "Comparison timeout exhausted before analysis." in result.content
    adapter.call_with_tools.assert_not_called()


def test_multi_agent_compare_preserves_leg_timeout_after_synthesis() -> None:
    adapter = MagicMock()
    adapter.call_with_tools.return_value = LLMResponse(
        content="cross-market synthesis",
        tool_calls=[],
        usage={},
        provider="openai",
        model="test-model",
    )
    orchestrator = AgentOrchestrator(
        tool_registry=_market_capability_registry(),
        llm_adapter=adapter,
        config=SimpleNamespace(agent_orchestrator_timeout_s=60),
        runtime_guard_policy=RuntimeGuardPolicy(),
    )
    scope = resolve_stock_scope("比较 AAPL 和 00700.HK", None).stock_scope
    market_context = build_agent_chat_market_context(
        {},
        scope,
        "zh",
        per_symbol_tool_scopes=True,
    )

    result = orchestrator._synthesize_multi_symbol_chat(
        message="比较 AAPL 和 00700.HK",
        market_context=market_context,
        report_language="zh",
        per_symbol_results=[
            (
                "AAPL",
                OrchestratorResult(
                    success=True,
                    content="AAPL analysis",
                    timed_out=True,
                ),
            ),
            (
                "HK00700",
                OrchestratorResult(
                    success=True,
                    content="HK00700 analysis",
                ),
            ),
        ],
        cancelled_check=None,
        timeout_seconds=30,
    )

    assert result.success is True
    assert result.content == "cross-market synthesis"
    assert result.timed_out is True


def test_multi_agent_fallback_preserves_unavailable_symbol_diagnostic() -> None:
    adapter = MagicMock()
    orchestrator = AgentOrchestrator(
        tool_registry=_market_capability_registry(),
        llm_adapter=adapter,
        config=SimpleNamespace(agent_orchestrator_timeout_s=60),
        runtime_guard_policy=RuntimeGuardPolicy(),
    )
    scope = resolve_stock_scope("compare AAPL and HK00700", None).stock_scope
    market_context = build_agent_chat_market_context(
        {},
        scope,
        "en",
        per_symbol_tool_scopes=True,
    )

    with patch(
        "src.agent.orchestrator.run_agent_loop",
        return_value=RunLoopResult(
            success=False,
            error="comparison synthesis unavailable",
            timed_out=True,
        ),
    ):
        result = orchestrator._synthesize_multi_symbol_chat(
            message="compare AAPL and HK00700",
            market_context=market_context,
            report_language="en",
            per_symbol_results=[
                (
                    "AAPL",
                    OrchestratorResult(success=True, content="AAPL analysis"),
                ),
                (
                    "HK00700",
                    OrchestratorResult(
                        success=False,
                        error="HK quote unavailable",
                    ),
                ),
            ],
            cancelled_check=None,
            timeout_seconds=30,
        )

    assert result.success is True
    assert result.error is None
    assert result.timed_out is True
    assert "AAPL analysis" in result.content
    assert "## HK00700" in result.content
    assert "Unavailable" in result.content
    assert "HK quote unavailable" in result.content


def test_multi_agent_compare_cancellation_wins_before_fallback() -> None:
    adapter = MagicMock()
    orchestrator = AgentOrchestrator(
        tool_registry=_market_capability_registry(),
        llm_adapter=adapter,
        config=SimpleNamespace(agent_orchestrator_timeout_s=1),
        runtime_guard_policy=RuntimeGuardPolicy(),
    )
    scope = resolve_stock_scope("比较 AAPL 和 00700.HK", None).stock_scope
    market_context = build_agent_chat_market_context(
        {},
        scope,
        "zh",
        per_symbol_tool_scopes=True,
    )

    result = orchestrator._synthesize_multi_symbol_chat(
        message="比较 AAPL 和 00700.HK",
        market_context=market_context,
        report_language="zh",
        per_symbol_results=[
            (
                "AAPL",
                OrchestratorResult(success=True, content="AAPL analysis"),
            ),
        ],
        cancelled_check=lambda: True,
        timeout_seconds=0,
    )

    assert result.success is False
    assert result.cancelled is True
    assert result.content == ""
    adapter.call_with_tools.assert_not_called()


def test_multi_agent_compare_preflight_cancellation_prevents_first_leg() -> None:
    adapter = MagicMock()
    orchestrator = AgentOrchestrator(
        tool_registry=_market_capability_registry(),
        llm_adapter=adapter,
        config=SimpleNamespace(agent_orchestrator_timeout_s=0),
        runtime_guard_policy=RuntimeGuardPolicy(),
    )
    scope = resolve_stock_scope("比较 AAPL 和 00700.HK", None).stock_scope
    market_context = build_agent_chat_market_context({}, scope, "zh")

    with patch.object(orchestrator, "_execute_pipeline") as execute_pipeline:
        result = orchestrator._execute_multi_symbol_chat(
            message="比较 AAPL 和 00700.HK",
            session_id="cancel-before-first-leg",
            context={},
            stock_scope=scope,
            history=[],
            market_context=market_context,
            report_language="zh",
            progress_callback=None,
            cancelled_check=lambda: True,
        )

    assert result.success is False
    assert result.cancelled is True
    assert result.timed_out is False
    execute_pipeline.assert_not_called()
    adapter.call_with_tools.assert_not_called()


def test_multi_agent_compare_cancellation_wins_after_completed_leg() -> None:
    adapter = MagicMock()
    orchestrator = AgentOrchestrator(
        tool_registry=_market_capability_registry(),
        llm_adapter=adapter,
        config=SimpleNamespace(agent_orchestrator_timeout_s=0),
        runtime_guard_policy=RuntimeGuardPolicy(),
    )
    scope = resolve_stock_scope("比较 AAPL 和 00700.HK", None).stock_scope
    market_context = build_agent_chat_market_context({}, scope, "zh")
    executed: list[str] = []

    def fake_execute(ctx, **_kwargs):
        executed.append(ctx.stock_code)
        return OrchestratorResult(
            success=True,
            content=f"analysis for {ctx.stock_code}",
        )

    with patch.object(
        orchestrator,
        "_execute_pipeline",
        side_effect=fake_execute,
    ):
        result = orchestrator._execute_multi_symbol_chat(
            message="比较 AAPL 和 00700.HK",
            session_id="cancel-after-leg",
            context={},
            stock_scope=scope,
            history=[],
            market_context=market_context,
            report_language="zh",
            progress_callback=None,
            cancelled_check=lambda: bool(executed),
        )

    assert executed == ["AAPL"]
    assert result.success is False
    assert result.cancelled is True
    assert result.timed_out is False
    assert result.content == ""
    adapter.call_with_tools.assert_not_called()


def test_multi_agent_synthesis_propagates_runner_cancellation() -> None:
    adapter = MagicMock()
    orchestrator = AgentOrchestrator(
        tool_registry=_market_capability_registry(),
        llm_adapter=adapter,
        config=SimpleNamespace(agent_orchestrator_timeout_s=60),
        runtime_guard_policy=RuntimeGuardPolicy(),
    )
    scope = resolve_stock_scope("比较 AAPL 和 00700.HK", None).stock_scope
    market_context = build_agent_chat_market_context({}, scope, "zh")

    with patch(
        "src.agent.orchestrator.run_agent_loop",
        return_value=RunLoopResult(
            success=False,
            cancelled=True,
            error="Agent execution cancelled",
        ),
    ):
        result = orchestrator._synthesize_multi_symbol_chat(
            message="比较 AAPL 和 00700.HK",
            market_context=market_context,
            report_language="zh",
            per_symbol_results=[
                (
                    "AAPL",
                    OrchestratorResult(success=True, content="AAPL analysis"),
                ),
            ],
            cancelled_check=lambda: False,
            timeout_seconds=30,
        )

    assert result.success is False
    assert result.cancelled is True
    assert result.timed_out is False
    assert result.content == ""
