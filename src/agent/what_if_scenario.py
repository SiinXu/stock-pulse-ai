# -*- coding: utf-8 -*-
"""Structured what-if scenario helpers for Agent Chat (Issue #130 / T27)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

WHAT_IF_CONTEXT_KEY = "what_if"
HYPOTHETICAL_ASSUMPTION_MARKER = "[HYPOTHETICAL ASSUMPTION]"
HYPOTHETICAL_RESULT_MARKER = "[HYPOTHETICAL SCENARIO]"
PREVIEW_DISCLAIMER_EN = (
    "collaborative scenario preview only; does not change the system's final recommendation"
)
PREVIEW_DISCLAIMER_ZH = "协同推演预览，不改变系统最终建议"
DEFAULT_WHAT_IF_MAX_TURNS = 5
WHAT_IF_DIMENSIONS = frozenset({"index_move", "fx_rate", "interest_rate", "earnings"})
EARNINGS_OUTCOMES = frozenset({"beat", "miss", "inline"})
MOVE_DIRECTIONS = frozenset({"up", "down"})
WHAT_IF_ISOLATION_POLICY: Dict[str, Any] = {
    "mode": "preview_only",
    "persist_analysis_history": False,
    "persist_decision_signal": False,
    "persist_agent_memory": False,
    "parse_dashboard": False,
}

@dataclass(frozen=True)
class WhatIfAssumption:
    dimension: str
    direction: Optional[str] = None
    magnitude: Optional[float] = None
    currency_pair: Optional[str] = None
    label: Optional[str] = None

@dataclass(frozen=True)
class WhatIfScenario:
    assumptions: Tuple[WhatIfAssumption, ...]
    turn_index: int = 1
    max_turns: int = DEFAULT_WHAT_IF_MAX_TURNS
    enabled: bool = True
    @property
    def is_active(self) -> bool:
        return self.enabled and bool(self.assumptions)

def get_what_if_isolation_policy() -> Dict[str, Any]:
    return dict(WHAT_IF_ISOLATION_POLICY)

def parse_what_if_from_context(context: Optional[Mapping[str, Any]]) -> Optional[WhatIfScenario]:
    if not isinstance(context, Mapping):
        return None
    raw = context.get(WHAT_IF_CONTEXT_KEY)
    if not isinstance(raw, Mapping) or raw.get("enabled") is False:
        return None
    assumptions = _parse_assumptions(raw.get("assumptions"))
    if not assumptions:
        return None
    return WhatIfScenario(
        assumptions=tuple(assumptions),
        turn_index=_coerce_positive_int(raw.get("turn_index"), default=1),
        max_turns=_coerce_positive_int(raw.get("max_turns"), default=DEFAULT_WHAT_IF_MAX_TURNS),
        enabled=True,
    )

def count_what_if_turns_in_messages(messages: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        if str(message.get("role") or "") != "user":
            continue
        if HYPOTHETICAL_ASSUMPTION_MARKER in str(message.get("content") or ""):
            count += 1
    return count

def is_what_if_turn_allowed(scenario: WhatIfScenario, *, prior_turn_count: int = 0) -> bool:
    return scenario.is_active and prior_turn_count < scenario.max_turns

def build_what_if_prompt_section(scenario: WhatIfScenario, language_key: str = "zh", *, prior_turn_count: int = 0) -> str:
    if not scenario.is_active:
        return ""
    if not is_what_if_turn_allowed(scenario, prior_turn_count=prior_turn_count):
        return _limit_section(scenario, language_key=language_key, prior_turn_count=prior_turn_count)
    return _en_section(scenario, prior_turn_count) if language_key == "en" else _zh_section(scenario, prior_turn_count)

def build_what_if_prompt_section_from_context(context: Optional[Mapping[str, Any]], language_key: str = "zh", *, prior_messages: Optional[Sequence[Mapping[str, Any]]] = None) -> str:
    scenario = parse_what_if_from_context(context)
    if scenario is None:
        return ""
    return build_what_if_prompt_section(scenario, language_key, prior_turn_count=count_what_if_turns_in_messages(prior_messages or ()))

def content_has_hypothetical_marker(content: str) -> bool:
    text = content or ""
    return HYPOTHETICAL_RESULT_MARKER in text or HYPOTHETICAL_ASSUMPTION_MARKER in text

def _parse_assumptions(raw: Any) -> List[WhatIfAssumption]:
    if not isinstance(raw, list):
        return []
    out: List[WhatIfAssumption] = []
    for item in raw:
        a = _parse_one(item)
        if a is not None:
            out.append(a)
    return out

def _parse_one(item: Any) -> Optional[WhatIfAssumption]:
    if not isinstance(item, Mapping):
        return None
    dimension = str(item.get("dimension") or "").strip().lower()
    if dimension not in WHAT_IF_DIMENSIONS:
        return None
    direction_raw = item.get("direction")
    direction = str(direction_raw).strip().lower() if direction_raw not in (None, "") else None
    magnitude = _opt_float(item.get("magnitude"))
    currency_pair = _opt_str(item.get("currency_pair"))
    label = _opt_str(item.get("label"))
    if dimension == "earnings":
        if direction not in EARNINGS_OUTCOMES:
            return None
    elif dimension in {"index_move", "fx_rate", "interest_rate"}:
        if direction is not None and direction not in MOVE_DIRECTIONS:
            return None
        if magnitude is None:
            return None
    return WhatIfAssumption(dimension=dimension, direction=direction, magnitude=magnitude, currency_pair=currency_pair, label=label)

def _en_section(scenario: WhatIfScenario, prior_turn_count: int) -> str:
    lines = [
        f"## {HYPOTHETICAL_ASSUMPTION_MARKER}",
        "The following conditions are **hypothetical assumptions only**. They are NOT observed facts, market prints, or confirmed events.",
        f"- Mode: preview_only ({PREVIEW_DISCLAIMER_EN}).",
        f"- What-if turn {prior_turn_count + 1} of {scenario.max_turns} for this session (client turn_index={scenario.turn_index}).",
        "- Structured assumptions:",
    ]
    for a in scenario.assumptions:
        lines.append(f"  - {_fmt_en(a)}")
    lines += [
        "",
        "Hard rules for this turn:",
        "1. Reason only under these assumptions; never present them as real outcomes.",
        f"2. Start the visible answer with `{HYPOTHETICAL_RESULT_MARKER}` and restate that this is a {PREVIEW_DISCLAIMER_EN}.",
        "3. Do not emit formal DecisionSignals, trade tickets, or history-grade conclusions that could be treated as real advice.",
        "4. Keep factual market data (from tools) clearly separated from the hypothetical branch.",
    ]
    return "\n".join(lines)

def _zh_section(scenario: WhatIfScenario, prior_turn_count: int) -> str:
    lines = [
        f"## {HYPOTHETICAL_ASSUMPTION_MARKER}",
        "以下条件为**假设情景**，不是已发生的事实、成交行情或已确认事件。",
        f"- 模式：preview_only（{PREVIEW_DISCLAIMER_ZH}）。",
        f"- 本会话 what-if 第 {prior_turn_count + 1} / {scenario.max_turns} 轮（客户端 turn_index={scenario.turn_index}）。",
        "- 结构化假设：",
    ]
    for a in scenario.assumptions:
        lines.append(f"  - {_fmt_zh(a)}")
    lines += [
        "",
        "本轮硬性规则：",
        "1. 仅在上述假设下推演；不得把假设写成真实结果。",
        f"2. 可见回答必须以 `{HYPOTHETICAL_RESULT_MARKER}` 开头，并重申这是{PREVIEW_DISCLAIMER_ZH}。",
        "3. 不得输出可被当作正式结论的 DecisionSignal、交易指令或可写入分析历史的定论。",
        "4. 工具返回的事实数据必须与假设分支明确分隔。",
    ]
    return "\n".join(lines)

def _limit_section(scenario: WhatIfScenario, *, language_key: str, prior_turn_count: int) -> str:
    if language_key == "en":
        return "\n".join([
            f"## {HYPOTHETICAL_ASSUMPTION_MARKER}",
            f"What-if turn limit reached ({prior_turn_count}/{scenario.max_turns}). Do not run another hypothetical scenario in this session. Reply with `{HYPOTHETICAL_RESULT_MARKER}` explaining the limit and offer a normal (non-what-if) analysis instead.",
            f"- Mode: preview_only ({PREVIEW_DISCLAIMER_EN}).",
        ])
    return "\n".join([
        f"## {HYPOTHETICAL_ASSUMPTION_MARKER}",
        f"what-if 轮次已达上限（{prior_turn_count}/{scenario.max_turns}）。本会话请勿再做假设推演。请以 `{HYPOTHETICAL_RESULT_MARKER}` 开头说明限制，并改用普通（非 what-if）分析回答。",
        f"- 模式：preview_only（{PREVIEW_DISCLAIMER_ZH}）。",
    ])

def _fmt_en(a: WhatIfAssumption) -> str:
    if a.label:
        return a.label
    d, direction, m = a.dimension, a.direction or "", a.magnitude
    if d == "index_move":
        sign = "+" if direction == "up" else "-" if direction == "down" else ""
        return f"Broad index moves {sign}{m:g}%"
    if d == "fx_rate":
        pair = a.currency_pair or "USD/CNY"
        sign = "+" if direction == "up" else "-" if direction == "down" else ""
        return f"FX {pair} moves {sign}{m:g}%"
    if d == "interest_rate":
        action = "cut" if direction == "down" else "hike" if direction == "up" else "change"
        return f"Policy rate {action} by {m:g} bp"
    if d == "earnings":
        return f"Company earnings {direction}"
    return d

def _fmt_zh(a: WhatIfAssumption) -> str:
    if a.label:
        return a.label
    d, direction, m = a.dimension, a.direction or "", a.magnitude
    if d == "index_move":
        sign = "+" if direction == "up" else "-" if direction == "down" else ""
        return f"大盘指数变动 {sign}{m:g}%"
    if d == "fx_rate":
        pair = a.currency_pair or "USD/CNY"
        sign = "+" if direction == "up" else "-" if direction == "down" else ""
        return f"汇率 {pair} 变动 {sign}{m:g}%"
    if d == "interest_rate":
        action = "降息" if direction == "down" else "加息" if direction == "up" else "变动"
        return f"政策利率{action} {m:g} bp"
    if d == "earnings":
        return f"公司财报{ {'beat':'超预期','miss':'不及预期','inline':'符合预期'}.get(direction, direction)}"
    return d

def _coerce_positive_int(value: Any, *, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n >= 1 else default

def _opt_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:
        return None
    return n

def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
