# -*- coding: utf-8 -*-
"""Visible conversation history builder for Agent chat requests."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from src.agent.llm_adapter import LLMToolAdapter
    from src.agent.tools.registry import ToolRegistry
    from src.config import Config

from src.config import (
    get_agent_context_compression_preset,
    get_effective_agent_primary_model,
    get_effective_agent_models_to_try,
)
from src.agent.litellm_route_resolution import resolve_agent_litellm_route
from src.agent.provider_trace import (
    TRACE_MODEL_KEY,
    TRACE_PROVIDER_KEY,
    TraceDiagnostics,
    resolved_provider_namespace,
    strip_trace_metadata,
    trace_model_matches,
)
from src.agent.runtime.lifecycle import get_default_usage_recorder
from src.market_context import detect_market, get_market_guidelines, get_market_role
from src.report_language import normalize_report_language
from src.services.stock_code_utils import canonicalize_analysis_stock_code
from src.storage import get_db
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

VISIBLE_ROLES = {"user", "assistant"}
SUMMARY_USER_PREFIX = "[系统生成的历史对话摘要，仅供延续本会话]"
SUMMARY_LLM_TIMEOUT_SECONDS = 20
A_SHARE_ONLY_CHAT_TOOLS = frozenset({
    "get_capital_flow",
    "get_chip_distribution",
    "get_sector_rankings",
})

SUMMARY_SYSTEM_PROMPT = """你是股票问答系统的会话压缩器，只能总结已经出现过的用户可见对话内容。

硬性规则：
- 只总结已有对话，不新增行情、新闻、财务数据或投资建议。
- 不推断未出现的事实，不补充新的买卖建议。
- 必须保留标的、持仓成本、周期、风险偏好、策略视角、关键判断、操作条件、止损止盈、数据时效、工具失败和未决问题。
- 输出必须使用 Markdown，并严格包含以下 5 个二级标题：
  ## 会话摘要
  ## 当前关注标的
  ## 用户偏好与约束
  ## 已有判断与操作条件
  ## 风险、数据时效与未决问题
"""


@dataclass(frozen=True)
class VisibleMessage:
    """A persisted user-visible chat message."""

    id: int
    role: str
    content: str
    created_at: Any = None


@dataclass(frozen=True)
class VisibleHistoryState:
    """Id-aware visible history state used for summary and trace splicing."""

    messages: List[Dict[str, Any]]
    visible_ids: set[int]
    visible_tokens: int


@dataclass(frozen=True)
class AgentChatContextBundle:
    """Prepared context messages for a single-agent chat request."""

    context_messages: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]


@dataclass(frozen=True)
class AgentChatMarketContext:
    """Deterministic market identity and prompt context for one chat turn."""

    stock_codes: Tuple[str, ...]
    markets: Tuple[str, ...]
    market_role: str
    market_guidelines: str
    prompt_section: str
    disabled_tool_names: Tuple[str, ...]


@dataclass(frozen=True)
class _MarketPromptFacts:
    currency: str
    timezone: str
    fields_zh: str
    fields_en: str


_CHAT_MARKET_FACTS: Dict[str, _MarketPromptFacts] = {
    "cn": _MarketPromptFacts(
        "CNY",
        "Asia/Shanghai",
        "涨跌停、T+1、北向资金、融资融券与交易所公告",
        "daily price limits, T+1, Northbound flows, margin data, and exchange filings",
    ),
    "hk": _MarketPromptFacts(
        "HKD",
        "Asia/Hong_Kong",
        "港交所交易时段、每手股数、南向资金、HKD 流动性与公司公告",
        "HKEX sessions, board lots, Southbound flows, HKD liquidity, and company filings",
    ),
    "us": _MarketPromptFacts(
        "USD",
        "America/New_York",
        "常规/盘前/盘后价格、熔断、财报、美元汇率、美联储与 SEC 公告",
        "regular/pre/after-hours prices, circuit breakers, earnings, USD FX, Fed policy, and SEC filings",
    ),
    "jp": _MarketPromptFacts(
        "JPY",
        "Asia/Tokyo",
        "日元汇率、日本央行政策、公司治理与交易所公告",
        "JPY FX, BOJ policy, corporate governance, and exchange filings",
    ),
    "kr": _MarketPromptFacts(
        "KRW",
        "Asia/Seoul",
        "韩元汇率、韩国央行政策、KOSPI/KOSDAQ 制度与公司公告",
        "KRW FX, Bank of Korea policy, KOSPI/KOSDAQ rules, and company filings",
    ),
    "tw": _MarketPromptFacts(
        "TWD",
        "Asia/Taipei",
        "新台币汇率、三大法人、融资融券、当冲与 TWSE/TPEx 公告",
        "TWD FX, institutional flows, margin/day trading, and TWSE/TPEx filings",
    ),
}


def build_agent_chat_market_context(
    context: Optional[Dict[str, Any]],
    stock_scope: Any = None,
    report_language: str = "zh",
    *,
    per_symbol_tool_scopes: bool = False,
) -> AgentChatMarketContext:
    """Build market-aware role, rules, and model-visible current-turn facts."""
    stock_codes: List[str] = []

    def append_code(value: Any) -> None:
        if not isinstance(value, str):
            return
        canonical = canonicalize_analysis_stock_code(value)
        if canonical and canonical not in stock_codes:
            stock_codes.append(canonical)

    append_code((context or {}).get("stock_code"))
    for code in sorted(getattr(stock_scope, "allowed_stock_codes", set()) or set()):
        append_code(code)

    if not stock_codes:
        return AgentChatMarketContext(
            stock_codes=(),
            markets=(),
            market_role=get_market_role(None, report_language),
            market_guidelines=get_market_guidelines(None, report_language),
            prompt_section="",
            disabled_tool_names=(),
        )

    markets = tuple(dict.fromkeys(detect_market(code) for code in stock_codes))
    disabled_tool_names = (
        tuple(sorted(A_SHARE_ONLY_CHAT_TOOLS))
        if not per_symbol_tool_scopes and any(market != "cn" for market in markets)
        else ()
    )
    language = normalize_report_language(report_language)
    language_key = "en" if language in {"en", "ko"} else "zh"

    if len(markets) == 1:
        market_role = get_market_role(stock_codes[0], report_language)
        market_guidelines = get_market_guidelines(stock_codes[0], report_language)
    else:
        market_role = "cross-market" if language_key == "en" else "跨市场"
        market_guidelines = _build_cross_market_guidelines(
            stock_codes,
            report_language=report_language,
            language_key=language_key,
        )

    return AgentChatMarketContext(
        stock_codes=tuple(stock_codes),
        markets=markets,
        market_role=market_role,
        market_guidelines=market_guidelines,
        prompt_section=_build_market_prompt_section(
            stock_codes,
            language_key,
            disabled_tool_names,
        ),
        disabled_tool_names=disabled_tool_names,
    )


def build_agent_chat_tool_registry(
    tool_registry: "ToolRegistry",
    market_context: AgentChatMarketContext,
) -> "ToolRegistry":
    """Return the deterministic market-compatible tool surface for Chat."""
    disabled = set(market_context.disabled_tool_names)
    if not disabled:
        return tool_registry

    from src.agent.tools.registry import ToolRegistry

    filtered = ToolRegistry()
    for tool_def in tool_registry.list_tools():
        if tool_def.name not in disabled:
            filtered.register(tool_def)
    return filtered


def build_agent_chat_chip_instruction(
    market_context: AgentChatMarketContext,
) -> str:
    """Build the market-conditional chip-distribution workflow step."""
    if "get_chip_distribution" in market_context.disabled_tool_names:
        return (
            "当前市场不支持 `get_chip_distribution`；本轮不暴露该工具，"
            "不得调用或用 A 股筹码数据替代"
        )
    return "调用 `get_chip_distribution` 获取筹码分布结构"


def _market_facts(market: str) -> _MarketPromptFacts:
    return _CHAT_MARKET_FACTS.get(
        market,
        _MarketPromptFacts(
            "tool-provided",
            "tool-provided",
            "仅使用工具明确返回的市场字段",
            "only market fields explicitly returned by tools",
        ),
    )


def _build_cross_market_guidelines(
    stock_codes: Sequence[str],
    *,
    report_language: str,
    language_key: str,
) -> str:
    blocks: List[str] = []
    seen_markets: set[str] = set()
    for code in stock_codes:
        market = detect_market(code)
        if market in seen_markets:
            continue
        seen_markets.add(market)
        display = get_market_role(code, report_language)
        blocks.append(f"### {display}\n{get_market_guidelines(code, report_language)}")

    if language_key == "en":
        intro = (
            "- This turn covers multiple markets. Apply each market's rules and "
            "market-specific fields separately.\n"
            "- Never substitute China A-share assumptions for missing Hong Kong, US, "
            "or other market data. State partial support explicitly."
        )
    else:
        intro = (
            "- 本轮涉及多个市场，必须分别应用各市场的交易规则与专属字段。\n"
            "- 港股、美股或其他市场数据缺失时，不得套用 A 股默认值；必须明确说明支持边界。"
        )
    return "\n\n".join([intro, *blocks])


def _build_market_prompt_section(
    stock_codes: Sequence[str],
    language_key: str,
    disabled_tool_names: Sequence[str],
) -> str:
    if language_key == "en":
        lines = ["## Current-Turn Market Context (System Generated)"]
        for code in stock_codes:
            market = detect_market(code)
            facts = _market_facts(market)
            lines.append(
                f"- Canonical symbol `{code}`: {get_market_role(code, 'en')} ({market.upper()}); "
                f"quote currency {facts.currency}; trading timezone {facts.timezone}; "
                f"market-specific fields: {facts.fields_en}."
            )
        lines.extend(
            [
                "- Use the canonical symbol above for every stock-scoped tool call.",
                "- If a provider or tool omits a market or field, state that limitation and continue with available evidence; never fabricate or fill it with A-share defaults.",
            ]
        )
        if disabled_tool_names:
            rendered = " and ".join(f"`{name}`" for name in disabled_tool_names)
            lines.append(
                f"- Market capability boundary: {rendered} are unavailable and are not exposed for this turn."
            )
        return "\n".join(lines)

    lines = ["## 本轮市场上下文（系统生成）"]
    for code in stock_codes:
        market = detect_market(code)
        facts = _market_facts(market)
        lines.append(
            f"- 规范代码 `{code}`：{get_market_role(code, 'zh')}（{market.upper()}）；计价货币 "
            f"{facts.currency}；交易时区 {facts.timezone}；市场专属字段："
            f"{facts.fields_zh}。"
        )
    lines.extend(
        [
            "- 每次股票范围工具调用必须使用上述规范代码。",
            "- 若 provider 或工具缺少某市场/字段，必须明确说明限制并基于已有证据继续；不得编造或用 A 股默认值补齐。",
        ]
    )
    if disabled_tool_names:
        rendered = "、".join(f"`{name}`" for name in disabled_tool_names)
        lines.append(f"- 市场能力边界：{rendered} 当前不可用，本轮不暴露这些工具。")
    return "\n".join(lines)


def build_summary_message(summary_text: str) -> Dict[str, str]:
    """Build the synthetic summary message injected into chat history."""
    return {
        "role": "user",
        "content": f"{SUMMARY_USER_PREFIX}\n{summary_text.strip()}",
    }


def estimate_text_tokens(text: str, config: Config) -> int:
    """Estimate tokens deterministically enough for compression decisions."""
    normalized_text = text or ""
    try:
        import litellm  # type: ignore

        model = get_effective_agent_primary_model(config)
        count = litellm.token_counter(model=model, text=normalized_text)
        return max(0, int(count or 0))
    except Exception as exc:
        log_safe_exception(
            logger,
            "Agent token counting failed; using character heuristic",
            exc,
            error_code="agent_token_count_failed",
            level=logging.DEBUG,
        )
        return int(math.ceil(len(normalized_text) / 3))


def estimate_messages_tokens(messages: Sequence[Dict[str, Any]], config: Config) -> int:
    """Estimate tokens for a list of role/content messages."""
    return estimate_text_tokens(_render_messages(messages), config)


def build_summary_messages(
    previous_summary: str,
    messages: Sequence[VisibleMessage],
) -> List[Dict[str, str]]:
    """Build the text-only summary request messages."""
    sections: List[str] = []
    if previous_summary.strip():
        sections.append("已有滚动摘要：\n" + previous_summary.strip())
    sections.append("本次需要纳入摘要的新增对话：")
    sections.append(_render_visible_messages(messages))
    user_payload = "\n\n".join(sections).strip()
    return [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": user_payload},
    ]


def build_visible_chat_history(
    session_id: str,
    llm_adapter: LLMToolAdapter,
    config: Config,
) -> List[Dict[str, str]]:
    """Return visible chat history according to the compression state table."""
    state = _build_visible_history_state(session_id, llm_adapter, config)
    return _strip_internal_message_ids(state.messages)


def build_agent_chat_context_bundle(
    session_id: str,
    llm_adapter: LLMToolAdapter,
    config: Config,
) -> AgentChatContextBundle:
    """Return id-spliced visible history plus provider trace messages.

    The bundle excludes the current user turn.  ``AgentExecutor.chat`` appends
    factual context and the current user after these messages, preserving the
    existing request assembly order.
    """
    state = _build_visible_history_state(session_id, llm_adapter, config)
    diagnostics = TraceDiagnostics(visible_tokens=state.visible_tokens)
    db = get_db()
    resolution = resolve_agent_litellm_route(config)
    candidate_models = resolution.models_to_try if resolution.available else []
    if not candidate_models and not resolution.reason:
        candidate_models = get_effective_agent_models_to_try(config)
    if not candidate_models and not resolution.reason:
        candidate_models = [get_effective_agent_primary_model(config)]
    candidate_trace_targets = _build_trace_match_targets(candidate_models, config)
    turns = db.get_agent_provider_turns(session_id, must_roundtrip_only=True)
    traces_by_anchor: Dict[int, List[Dict[str, Any]]] = {}
    pending_trace_tokens = 0
    pending_trace_count = 0

    for turn in turns:
        if not any(
            trace_model_matches(
                turn.get("provider"),
                turn.get("model"),
                model,
                current_provider=provider,
            )
            for model, provider in candidate_trace_targets
        ):
            diagnostics.model_mismatch += 1
            diagnostics.dropped_trace_count += 1
            diagnostics.trace_dropped_reason = diagnostics.trace_dropped_reason or "model_mismatch"
            continue
        anchor_id = _coerce_int(turn.get("anchor_assistant_message_id"), default=0)
        if anchor_id <= 0 or anchor_id not in state.visible_ids:
            diagnostics.anchor_summarized += 1
            diagnostics.dropped_trace_count += 1
            diagnostics.trace_dropped_reason = diagnostics.trace_dropped_reason or "anchor_summarized"
            continue
        trace_messages = _restore_trace_metadata(
            turn.get("messages") or [],
            provider=turn.get("provider"),
            model=turn.get("model"),
        )
        if not trace_messages:
            continue
        pending_trace_count += 1
        pending_trace_tokens += _coerce_int(
            turn.get("estimated_tokens"),
            default=estimate_messages_tokens(trace_messages, config),
        )
        traces_by_anchor.setdefault(anchor_id, []).extend(trace_messages)

    if traces_by_anchor:
        preset = get_agent_context_compression_preset(
            getattr(config, "agent_context_compression_profile", None)
        )
        history_budget = _coerce_int(
            getattr(config, "agent_context_history_budget_tokens", preset.history_budget_tokens),
            default=preset.history_budget_tokens,
        )
        remaining_budget = history_budget - state.visible_tokens
        if remaining_budget < pending_trace_tokens:
            diagnostics.budget_exceeded = True
            diagnostics.trace_dropped_reason = "budget_exceeded"
            diagnostics.dropped_trace_count += pending_trace_count
            traces_by_anchor = {}
        else:
            diagnostics.trace_injected = True
            diagnostics.trace_tokens = pending_trace_tokens

    merged: List[Dict[str, Any]] = []
    for msg in state.messages:
        msg_id = _coerce_int(msg.get("_message_id"), default=0)
        if msg_id and msg_id in traces_by_anchor:
            merged.extend(traces_by_anchor[msg_id])
        merged.append(msg)

    return AgentChatContextBundle(
        context_messages=_strip_internal_message_ids(merged),
        diagnostics=diagnostics.to_dict(),
    )


def _build_visible_history_state(
    session_id: str,
    llm_adapter: LLMToolAdapter,
    config: Config,
) -> VisibleHistoryState:
    """Return visible history with private ``_message_id`` anchors."""
    db = get_db()
    if not getattr(config, "agent_context_compression_enabled", False):
        selected = _load_visible_messages(session_id, limit=20)
        messages = _to_chat_messages(selected, include_ids=True)
        return VisibleHistoryState(
            messages=messages,
            visible_ids={msg.id for msg in selected},
            visible_tokens=estimate_messages_tokens(_strip_internal_message_ids(messages), config),
        )

    visible_messages = _load_visible_messages(session_id)
    if not visible_messages:
        return VisibleHistoryState(messages=[], visible_ids=set(), visible_tokens=0)

    summary_record = db.get_conversation_summary(session_id)
    previous_summary = (summary_record or {}).get("summary") or ""
    covered_message_id = _coerce_int((summary_record or {}).get("covered_message_id"), default=0)
    preset = get_agent_context_compression_preset(
        getattr(config, "agent_context_compression_profile", None)
    )
    trigger_tokens = _coerce_int(
        getattr(config, "agent_context_compression_trigger_tokens", preset.trigger_tokens),
        default=preset.trigger_tokens,
    )
    protected_turns = _coerce_int(
        getattr(config, "agent_context_protected_turns", preset.protected_turns),
        default=preset.protected_turns,
    )

    protected_tail = _split_protected_tail(visible_messages, protected_turns)
    protected_ids = {msg.id for msg in protected_tail}
    uncovered_messages = [msg for msg in visible_messages if msg.id > covered_message_id]
    candidate = (
        [build_summary_message(previous_summary)] + _to_chat_messages(uncovered_messages, include_ids=True)
        if previous_summary
        else _to_chat_messages(visible_messages, include_ids=True)
    )
    candidate_tokens = estimate_messages_tokens(_strip_internal_message_ids(candidate), config)

    if candidate_tokens <= trigger_tokens:
        return VisibleHistoryState(
            messages=candidate,
            visible_ids={msg.id for msg in visible_messages if msg.id > covered_message_id or not previous_summary},
            visible_tokens=candidate_tokens,
        )

    to_summarize = [
        msg
        for msg in visible_messages
        if msg.id > covered_message_id and msg.id not in protected_ids
    ]
    if not to_summarize:
        if previous_summary:
            logger.warning(
                "Conversation context compression skipped for session %s: protected tail exceeds trigger",
                session_id,
            )
            messages = [build_summary_message(previous_summary)] + _to_chat_messages(protected_tail, include_ids=True)
            return VisibleHistoryState(
                messages=messages,
                visible_ids={msg.id for msg in protected_tail},
                visible_tokens=estimate_messages_tokens(_strip_internal_message_ids(messages), config),
            )
        logger.warning(
            "Conversation context compression skipped for session %s: all visible history is protected",
            session_id,
        )
        messages = _to_chat_messages(visible_messages, include_ids=True)
        return VisibleHistoryState(
            messages=messages,
            visible_ids={msg.id for msg in visible_messages},
            visible_tokens=estimate_messages_tokens(_strip_internal_message_ids(messages), config),
        )

    logger.info(
        "Conversation context compression summarizing session %s: %d messages, candidate_tokens=%d, trigger=%d",
        session_id,
        len(to_summarize),
        candidate_tokens,
        trigger_tokens,
    )
    summary_text, response = _generate_summary(
        llm_adapter=llm_adapter,
        config=config,
        previous_summary=previous_summary,
        to_summarize=to_summarize,
        max_tokens=preset.summary_target_tokens,
    )
    if summary_text:
        new_covered_message_id = max(msg.id for msg in to_summarize)
        estimated_tokens = estimate_text_tokens(summary_text, config)
        db.upsert_conversation_summary(
            session_id=session_id,
            summary=summary_text,
            covered_message_id=new_covered_message_id,
            source_message_count=len(to_summarize),
            estimated_tokens=estimated_tokens,
        )
        usage = getattr(response, "usage", {}) or {}
        get_default_usage_recorder().record(
            usage,
            getattr(response, "model", "") or get_effective_agent_primary_model(config) or "unknown",
            call_type="agent",
        )
        messages = [build_summary_message(summary_text)] + _to_chat_messages(protected_tail, include_ids=True)
        return VisibleHistoryState(
            messages=messages,
            visible_ids={msg.id for msg in protected_tail},
            visible_tokens=estimate_messages_tokens(_strip_internal_message_ids(messages), config),
        )

    logger.warning(
        "Conversation context compression failed for session %s; using state-table fallback",
        session_id,
    )
    if previous_summary:
        return VisibleHistoryState(
            messages=candidate,
            visible_ids={msg.id for msg in visible_messages if msg.id > covered_message_id},
            visible_tokens=candidate_tokens,
        )
    selected = visible_messages[-20:]
    messages = _to_chat_messages(selected, include_ids=True)
    return VisibleHistoryState(
        messages=messages,
        visible_ids={msg.id for msg in selected},
        visible_tokens=estimate_messages_tokens(_strip_internal_message_ids(messages), config),
    )


def _load_visible_messages(session_id: str, *, limit: Optional[int] = None) -> List[VisibleMessage]:
    rows = get_db().get_visible_conversation_messages(session_id, limit=limit)
    messages = []
    for row in rows:
        role = str(row.get("role") or "")
        content = str(row.get("content") or "")
        if role not in VISIBLE_ROLES or not content:
            continue
        messages.append(
            VisibleMessage(
                id=_coerce_int(row.get("id"), default=0),
                role=role,
                content=content,
                created_at=row.get("created_at"),
            )
        )
    return [msg for msg in messages if msg.id > 0]


def _split_protected_tail(messages: Sequence[VisibleMessage], protected_turns: int) -> List[VisibleMessage]:
    if not messages:
        return []
    if protected_turns <= 0:
        return []

    user_count = 0
    # If fewer user turns exist than requested, keep start_index=0 and protect
    # the entire visible history. The caller handles over-trigger protected-only
    # sessions without forcing a magic truncate.
    start_index = 0
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role == "user":
            user_count += 1
            if user_count >= protected_turns:
                start_index = index
                break
    return list(messages[start_index:])


def _generate_summary(
    *,
    llm_adapter: LLMToolAdapter,
    config: Config,
    previous_summary: str,
    to_summarize: Sequence[VisibleMessage],
    max_tokens: int,
) -> Tuple[Optional[str], Any]:
    try:
        response = llm_adapter.call_text(
            build_summary_messages(previous_summary, to_summarize),
            temperature=0,
            max_tokens=max_tokens,
            timeout=SUMMARY_LLM_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        log_safe_exception(
            logger,
            "Agent conversation summary generation failed",
            exc,
            error_code="agent_conversation_summary_failed",
            level=logging.WARNING,
        )
        return None, None

    content = (getattr(response, "content", None) or "").strip()
    if getattr(response, "provider", "") == "error" or not content:
        return None, response
    return content, response


def _to_chat_messages(
    messages: Iterable[VisibleMessage],
    *,
    include_ids: bool = False,
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for msg in messages:
        row: Dict[str, Any] = {"role": msg.role, "content": msg.content}
        if include_ids:
            row["_message_id"] = msg.id
        result.append(row)
    return result


def _strip_internal_message_ids(messages: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {key: value for key, value in msg.items() if key != "_message_id"}
        for msg in messages
    ]


def _restore_trace_metadata(
    messages: Sequence[Any],
    *,
    provider: Any,
    model: Any,
) -> List[Dict[str, Any]]:
    restored: List[Dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        clean = strip_trace_metadata(msg)
        if clean.get("role") in {"assistant", "tool"}:
            clean[TRACE_PROVIDER_KEY] = provider
            clean[TRACE_MODEL_KEY] = model
        restored.append(clean)
    return restored


def _build_trace_match_targets(
    models: Sequence[str],
    config: Config,
) -> List[Tuple[str, str]]:
    model_list = getattr(config, "llm_model_list", []) or []
    targets: List[Tuple[str, str]] = []
    for model in models:
        normalized = str(model or "").strip()
        if not normalized:
            continue
        targets.append((normalized, resolved_provider_namespace(normalized, model_list)))
    return targets


def _render_messages(messages: Sequence[Dict[str, Any]]) -> str:
    return "\n\n".join(
        f"{msg.get('role', '')}:\n{msg.get('content', '')}"
        for msg in messages
    )


def _render_visible_messages(messages: Sequence[VisibleMessage]) -> str:
    return "\n\n".join(f"{msg.role}:\n{msg.content}" for msg in messages)


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)
