# -*- coding: utf-8 -*-
"""Number, text, tone, asset, and localization helpers for share posters."""

from __future__ import annotations

import base64
import html
import mimetypes
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

PROJECT_URL = "https://github.com/SiinXu/stock-pulse-ai"

PROJECT_REPOSITORY = "SiinXu/stock-pulse-ai"

PROJECT_DISPLAY_NAME = "StockPulse"

_MARKET_RE = re.compile(
    r"(?:大盘复盘|市场复盘|market\s+(?:review|recap)|시황\s*리뷰)", re.IGNORECASE
)

_MARKET_SCOPE_RE = re.compile(
    r"(?:A股|港股|美股|日股|韩股|中国\s*A주|미국|홍콩|일본|한국|\b(?:cn|hk|us|jp|kr)\b|a[-\s]?share|hong\s+kong|japan|korea|u\.?s\.?)",
    re.IGNORECASE,
)

_DASHBOARD_RE = re.compile(r"(?:决策仪表盘|decision\s+dashboard)", re.IGNORECASE)

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.MULTILINE)

_QUOTE_RE = re.compile(r"^\s*>\s+(.+?)\s*$", re.MULTILINE)

_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})(?:[ T]\d{2}:\d{2}(?::\d{2})?)?\b")

_MARKET_REGION_REF_RE = re.compile(
    r"^\[dsa-market-region\]:\s+#\s+\(\s*([a-z,]+)\s*\)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_SUFFIXED_NUMERIC_CODE_PATTERN = (
    r"(?:\d{6}\.(?:SH|SZ|SS|BJ|KS|KQ)|\d{1,5}\.HK|\d{4,6}\.(?:TWO|TW)|\d{4,5}\.T)"
)

_CODE_RE = re.compile(
    rf"(?:\(|（)?({_SUFFIXED_NUMERIC_CODE_PATTERN}|(?:(?i:sh|sz|bj|hk))?\d{{5,6}}(?:\.[A-Z]{{2}})?|(?<![A-Za-z])[A-Z]{{1,5}}(?:\.[A-Z])?(?![A-Za-z]))(?:\)|）)?",
)

_NUMERIC_CODE_RE = re.compile(
    rf"(?:{_SUFFIXED_NUMERIC_CODE_PATTERN}|(?:(?i:sh|sz|bj|hk))?\d{{5,6}}(?:\.[A-Z]{{2}})?)"
)

_NA_VALUES = {"", "-", "--", "n/a", "na", "none", "null", "暂无", "暂无数据"}

_POSTER_TEXT = {
    "zh": {
        "brand": "StockPulse", "stock_subtitle": "个股决策卡 · 结论、点位与风险一图读懂",
        "market_subtitle": "指数、宽度、主线与风险的收盘复盘", "multi_title": "多市场复盘",
        "multi_subtitle": "按市场分段展示指数、主线与风险边界", "dashboard_subtitle": "多股决策摘要",
        "score": "评分", "confidence": "置信度", "trend": "趋势", "core": "核心结论",
        "snapshot": "市场快照", "execution": "执行计划", "technical": "技术参考",
        "next_watch": "下一步观察", "positive_catalysts": "利好催化", "risk_alerts": "风险警报",
        "catalysts_risks": "催化与风险", "no_position": "未持仓", "holding": "已持仓",
        "position": "仓位", "entry": "建仓", "risk_control": "风控", "position_advice": "持仓建议",
        "market_signal": "市场信号", "today_conclusion": "今日结论", "breadth": "市场宽度",
        "dimensions": "信号拆解", "leaders": "强势板块", "laggards": "弱势板块",
        "focus_tag": "关注", "avoid_tag": "回避", "focus": "重点跟踪", "funds": "资金观察",
        "strategy": "明日策略", "risks": "风险提示", "tagline": "让股票研究更简单、更高效",
        "open_source": "开源项目 · GitHub", "xiaohongshu": "小红书",
        "disclaimer": "AI 生成，仅供研究交流，不构成投资建议。市场有风险，决策需谨慎。",
        "source": "数据源",
    },
    "en": {
        "brand": "StockPulse", "stock_subtitle": "Stock decision card · thesis, levels, and risks",
        "market_subtitle": "Closing review of indices, breadth, themes, and risks", "multi_title": "Multi-market Recap",
        "multi_subtitle": "Indices, themes, and risk boundaries by market", "dashboard_subtitle": "Multi-stock Decision Summary",
        "score": "Score", "confidence": "Confidence", "trend": "Trend", "core": "Core Conclusion",
        "snapshot": "Market Snapshot", "execution": "Execution Plan", "technical": "Technical Reference",
        "next_watch": "Next Watch", "positive_catalysts": "Positive Catalysts", "risk_alerts": "Risk Alerts",
        "catalysts_risks": "Catalysts & Risks", "no_position": "No Position", "holding": "Holding",
        "position": "Position", "entry": "Entry", "risk_control": "Risk Control", "position_advice": "Position Advice",
        "market_signal": "Market Signal", "today_conclusion": "Conclusion", "breadth": "Market Breadth",
        "dimensions": "Signal Breakdown", "leaders": "Leading Sectors", "laggards": "Lagging Sectors",
        "focus_tag": "Watch", "avoid_tag": "Avoid", "focus": "Key Watchlist", "funds": "Fund Flow Watch",
        "strategy": "Next-session Plan", "risks": "Risk Alerts", "tagline": "Make stock research simpler and more efficient",
        "open_source": "Open Source · GitHub", "xiaohongshu": "Xiaohongshu",
        "disclaimer": "AI-generated for research only; not investment advice. Markets involve risk.",
        "source": "Source",
    },
    "ko": {
        "brand": "StockPulse", "stock_subtitle": "종목 의사결정 카드 · 결론, 가격대, 리스크",
        "market_subtitle": "지수, 시장 폭, 주도주와 리스크 마감 리뷰", "multi_title": "다중 시장 리뷰",
        "multi_subtitle": "시장별 지수, 주도주와 리스크 경계", "dashboard_subtitle": "다중 종목 의사결정 요약",
        "score": "점수", "confidence": "신뢰도", "trend": "추세", "core": "핵심 결론",
        "snapshot": "시세 스냅샷", "execution": "실행 계획", "technical": "기술 참고",
        "next_watch": "다음 관찰", "positive_catalysts": "긍정 촉매", "risk_alerts": "리스크 경보",
        "catalysts_risks": "촉매와 리스크", "no_position": "미보유", "holding": "보유 중",
        "position": "포지션", "entry": "진입", "risk_control": "리스크 관리", "position_advice": "포지션 제안",
        "market_signal": "시장 신호", "today_conclusion": "오늘의 결론", "breadth": "시장 폭",
        "dimensions": "신호 분석", "leaders": "강세 섹터", "laggards": "약세 섹터",
        "focus_tag": "관찰", "avoid_tag": "회피", "focus": "주요 관찰", "funds": "자금 흐름",
        "strategy": "다음 거래일 전략", "risks": "리스크 경고", "tagline": "주식 리서치를 더 쉽고 효율적으로",
        "open_source": "오픈소스 · GitHub", "xiaohongshu": "샤오홍슈",
        "disclaimer": "AI 생성 연구 자료이며 투자 조언이 아닙니다. 투자에는 위험이 따릅니다.",
        "source": "데이터 소스",
    },
}

_POSTER_LABELS = {
    "en": {
        "当前/收盘": "Current/Close", "现价": "Current", "涨跌幅": "Change", "涨跌": "Change",
        "量比": "Volume Ratio", "换手率": "Turnover", "换手": "Turnover", "理想买入": "Ideal Entry",
        "确认买入": "Confirmed Entry", "止损": "Stop Loss", "目标": "Target", "均线": "MA Alignment",
        "量能": "Volume", "趋势分": "Trend Score", "MA5乖离": "MA5 Bias", "支撑": "Support", "压力": "Resistance",
        "行动窗口": "Action Window", "下次检查": "Next Check", "上涨": "Advancers", "下跌": "Decliners",
        "涨停": "Limit-up", "跌停": "Limit-down", "成交额": "Turnover", "赚钱效应": "Breadth Score",
        "指数强度": "Index Strength", "涨停结构": "Limit Structure",
    },
    "ko": {
        "当前/收盘": "현재/종가", "现价": "현재가", "涨跌幅": "등락률", "涨跌": "등락",
        "量比": "거래량 비율", "换手率": "회전율", "换手": "회전율", "理想买入": "이상적 진입",
        "确认买入": "확인 진입", "止损": "손절", "目标": "목표", "均线": "이동평균",
        "量能": "거래량", "趋势分": "추세 점수", "MA5乖离": "MA5 이격", "支撑": "지지", "压力": "저항",
        "行动窗口": "행동 구간", "下次检查": "다음 점검", "上涨": "상승", "下跌": "하락",
        "涨停": "상한가", "跌停": "하한가", "成交额": "거래대금", "赚钱效应": "시장 폭 점수",
        "指数强度": "지수 강도", "涨停结构": "상한가 구조",
    },
}

_MARKET_LABEL_PATTERNS = (
    (
        "A股",
        re.compile(
            r"(?:A\s*股|a[-\s]?share|\bcn\s+market\s+(?:review|recap)\b|\bchina\b|중국\s*A주)",
            re.IGNORECASE,
        ),
    ),
    (
        "港股",
        re.compile(
            r"(?:港\s*股|\bhk\s+market\s+(?:review|recap)\b|hong\s+kong|홍콩)",
            re.IGNORECASE,
        ),
    ),
    (
        "美股",
        re.compile(
            r"(?:美\s*股|\b(?:u\.?s\.?|us)\s+market\s+(?:review|recap)\b|united\s+states|미국)",
            re.IGNORECASE,
        ),
    ),
    ("日股", re.compile(r"(?:日\s*股|japan|일본)", re.IGNORECASE)),
    ("韩股", re.compile(r"(?:韩\s*股|korea|한국)", re.IGNORECASE)),
)

def _asset_path(path_value: str) -> Optional[Path]:
    if not path_value.strip():
        return None

    configured = Path(path_value).expanduser()
    candidates = [configured] if configured.is_absolute() else [
        Path.cwd() / configured,
        Path(__file__).resolve().parents[2] / configured,
    ]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root and not configured.is_absolute():
        candidates.append(Path(bundle_root) / configured)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None

def _asset_data_uri(path_value: str) -> str:
    asset_path = _asset_path(path_value)
    if asset_path is None:
        return ""
    try:
        payload = asset_path.read_bytes()
    except OSError:
        return ""
    mime_type = mimetypes.guess_type(asset_path.name)[0] or "image/png"
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"

def _plain(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[*_`~]", "", text)
    text = re.sub(r"^[^\w\u4e00-\u9fff+\-]+", "", text)
    return re.sub(r"\s+", " ", text).strip()

def _clean_value(value: object, *, limit: int = 90) -> str:
    text = _plain(value)
    text = re.sub(
        r"^(?:理想买入点|次优买入点|止损位?|目标位?|ideal entry|secondary entry|stop loss|target)\s*[:：]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    if text.lower() in _NA_VALUES:
        return ""
    if len(text) > limit:
        return text[: limit - 1].rstrip("，,；;。.") + "…"
    return text

def _compact_text(value: object, *, limit: int = 46) -> str:
    """Keep poster copy scannable without changing the underlying report."""

    text = _clean_value(value, limit=max(limit * 2, 90))
    text = re.sub(r"^[✅⚠️❌🔴🟢🟡]+\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ，,；;。")
    if len(text) <= limit:
        return text
    first_clause = re.split(r"[；;。]", text, maxsplit=1)[0].strip()
    if first_clause and len(first_clause) <= limit:
        return first_clause
    return text[: limit - 1].rstrip("，,；;。 ") + "…"

def _nested_mapping(value: object, *keys: str) -> Mapping[str, Any]:
    current: object = value
    for key in keys:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(key)
    return current if isinstance(current, Mapping) else {}

def _poster_language(
    markdown_text: str,
    payload: Optional[Mapping[str, Any]] = None,
) -> str:
    """Resolve poster chrome language from the persisted contract or report."""

    if isinstance(payload, Mapping):
        raw_language = payload.get("report_language") or payload.get("language")
        normalized = str(raw_language or "").strip().lower().replace("_", "-")
        if normalized.startswith("en"):
            return "en"
        if normalized.startswith("ko"):
            return "ko"
        if normalized.startswith("zh"):
            return "zh"
    if re.search(r"[\uac00-\ud7af]", markdown_text or ""):
        return "ko"
    if re.search(
        r"(?:core conclusion|market snapshot|action levels|market (?:review|recap)|major indices)",
        markdown_text or "",
        re.IGNORECASE,
    ):
        return "en"
    return "zh"

def _poster_text(language: str, key: str) -> str:
    return _POSTER_TEXT.get(language, _POSTER_TEXT["zh"]).get(key, _POSTER_TEXT["zh"].get(key, key))

def _poster_label(language: str, label: str) -> str:
    translated = _POSTER_LABELS.get(language, {}).get(label)
    if translated:
        return translated
    if language == "en" and label.startswith("观察 "):
        return label.replace("观察 ", "Watch ", 1)
    if language == "ko" and label.startswith("观察 "):
        return label.replace("观察 ", "관찰 ", 1)
    return label

def _metric_value(
    items: Iterable[tuple[str, str, str]],
    *labels: str,
) -> str:
    for label, value, _tone in items:
        if any(candidate == label for candidate in labels) and value:
            return value
    return ""

def _merge_metrics(
    existing: Iterable[tuple[str, str, str]],
    overlay: Iterable[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    """Overlay populated metric cards without erasing Markdown fallbacks."""

    merged = list(existing)
    positions = {label: index for index, (label, _value, _tone) in enumerate(merged)}
    for item in overlay:
        label, value, _tone = item
        if not value:
            continue
        if label in positions:
            merged[positions[label]] = item
        else:
            positions[label] = len(merged)
            merged.append(item)
    return merged

def _merge_compact_list(
    existing: Iterable[object],
    overlay: object,
    *,
    limit_items: int = 2,
    limit_chars: int = 36,
) -> list[str]:
    """Prefer structured list items without erasing Markdown fallback entries."""

    if not isinstance(overlay, list):
        return [str(item) for item in existing if _clean_value(item)][:limit_items]

    merged: list[str] = []
    seen: set[str] = set()
    for source in (overlay, list(existing)):
        for item in source:
            text = _compact_text(item, limit=limit_chars)
            if not text:
                continue
            key = _plain(text).lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(text)
            if len(merged) >= limit_items:
                return merged
    return merged

def _market_light_overlay_allowed(payload: Mapping[str, Any]) -> bool:
    """Skip fabricated market-light snapshots that were persisted as unavailable."""

    return str(payload.get("data_quality") or "").strip().lower() != "unavailable"

def _normalize_index_name(value: object) -> str:
    return _plain(_clean_value(value, limit=28)).strip().lower()

def _normalize_ranking_name(value: object) -> str:
    return _plain(_clean_value(value, limit=28)).strip().lower()

def _merge_index_cards(
    existing: Iterable[tuple[str, str, str, str]],
    overlay: Iterable[Mapping[str, Any]],
    *,
    positive_tone: str,
    negative_tone: str,
) -> list[tuple[str, str, str, str]]:
    """Merge structured index fields into Markdown-parsed cards without dropping fallbacks."""

    merged = list(existing)
    positions = {
        key: index
        for index, (name, _current, _change, _color) in enumerate(merged)
        if (key := _normalize_index_name(name))
    }
    for item in overlay:
        name = _clean_value(item.get("name"), limit=18)
        if not name:
            continue
        current = _number_text(item.get("current"))
        change = _signed_percent(item.get("change_pct"))
        key = _normalize_index_name(name)
        if not key:
            continue
        if key in positions:
            index = positions[key]
            current_name, current_value, current_change, current_color = merged[index]
            merged_change = change or current_change
            if merged_change.startswith("+"):
                color = positive_tone
            elif merged_change.startswith("-"):
                color = negative_tone
            else:
                color = current_color
            merged[index] = (
                name or current_name,
                current or current_value,
                merged_change,
                color,
            )
            continue
        if not (current and change) or len(merged) >= 4:
            continue
        merged.append(
            (
                name,
                current,
                change,
                positive_tone if change.startswith("+") else negative_tone if change.startswith("-") else "",
            )
        )
        positions[key] = len(merged) - 1
    return merged[:4]

def _merge_sector_rankings(
    existing: Iterable[tuple[str, str, str]],
    overlay: Iterable[Mapping[str, Any]],
    *,
    positive_tone: str,
    negative_tone: str,
    default_tone: str,
) -> list[tuple[str, str, str]]:
    """Merge structured sector rows into Markdown rankings without dropping fallbacks."""

    merged = list(existing)
    positions = {
        key: index
        for index, (name, _change, _tone) in enumerate(merged)
        if (key := _normalize_ranking_name(name))
    }
    for offset, item in enumerate(overlay):
        name = _clean_value(item.get("name"), limit=18)
        change = _signed_percent(item.get("change_pct"))
        if not name:
            continue
        key = _normalize_ranking_name(name)
        target_index = positions.get(key) if key else None
        if target_index is None and change and offset < len(merged):
            target_index = offset
        if target_index is not None:
            current_name, current_change, current_tone = merged[target_index]
            current_key = _normalize_ranking_name(current_name)
            merged_change = change or current_change
            if merged_change.startswith("+"):
                tone = positive_tone
            elif merged_change.startswith("-"):
                tone = negative_tone
            else:
                tone = current_tone or default_tone
            merged[target_index] = (
                name or current_name,
                merged_change,
                tone,
            )
            if current_key and current_key != key and positions.get(current_key) == target_index:
                positions.pop(current_key, None)
            if key:
                positions[key] = target_index
            continue
        if len(merged) >= 3:
            continue
        merged.append(
            (
                name,
                change,
                positive_tone if change.startswith("+") else negative_tone if change.startswith("-") else default_tone,
            )
        )
        if key:
            positions[key] = len(merged) - 1
    return merged[:3]

def _number_text(value: object, *, suffix: str = "") -> str:
    if value is None or isinstance(value, bool):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _clean_value(value, limit=18)
    rendered = f"{number:.2f}".rstrip("0").rstrip(".")
    return f"{rendered}{suffix}"

def _compact_turnover(value: object, unit: object) -> str:
    """Render large CNY turnover figures without forcing narrow cards to wrap."""

    unit_text = _clean_value(unit, limit=8)
    try:
        number = float(value)
    except (TypeError, ValueError):
        amount = _number_text(value)
        return f"{amount}{unit_text}" if amount else ""
    if unit_text in {"亿", "亿元"} and abs(number) >= 10000:
        return f"{number / 10000:.2f}".rstrip("0").rstrip(".") + "万亿"
    return f"{_number_text(number)}{unit_text}"

def _signed_percent(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        text = _clean_value(value, limit=18)
        return text if "%" in text else f"{text}%" if text else ""
    return f"{number:+.2f}%"

def _price_tokens(value: object) -> list[str]:
    text = _plain(value)
    # Indicator labels such as MA5/MA10 are not prices; nearby parenthesized
    # values (for example ``MA10（55.13）``) remain eligible.
    return re.findall(r"(?<![A-Za-z\d])(\d+(?:\.\d+)?)(?!\d|%)", text)

def _compact_sniper_value(key: str, value: object) -> str:
    text = _clean_value(value, limit=120)
    if not text:
        return ""
    if key == "ideal_buy" and any(token in text for token in ("暂无", "暂不", "不满足")):
        return "等待企稳"
    prices = _price_tokens(text)
    if not prices:
        return _compact_text(text, limit=18)
    if key == "take_profit" and len(prices) >= 2:
        return f"{prices[0]}–{prices[1]}"
    return prices[0]

def _compact_position(value: object, *, holding: bool) -> str:
    text = _clean_value(value, limit=150)
    if not text:
        return ""
    prices = _price_tokens(text)
    if holding and prices:
        stop_match = re.search(r"跌破\s*(\d+(?:\.\d+)?)", text)
        reduce_at = next((price for price in prices if price != (stop_match.group(1) if stop_match else "")), "")
        parts = []
        if "减仓" in text:
            parts.append(f"反弹至 {reduce_at} 附近减仓" if reduce_at else "反弹减仓")
        if stop_match:
            parts.append(f"跌破 {stop_match.group(1)} 止损")
        if parts:
            return "；".join(parts)
    if not holding:
        if "等待" in text or "企稳" in text:
            levels = " / ".join(prices[:2])
            return f"等待 {levels} 附近企稳" if levels else "等待右侧企稳信号"
        if "不" in text and any(term in text for term in ("建仓", "接", "买入")):
            return "暂不建仓"
    return _compact_text(text, limit=40)

def _escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)

def _opposite_color(color: str) -> str:
    if color == "green":
        return "red"
    if color == "red":
        return "green"
    return ""

def _marker_color(raw_change: str) -> str:
    if "🟢" in (raw_change or ""):
        return "green"
    if "🔴" in (raw_change or ""):
        return "red"
    return ""

def _positive_color_from_change(raw_change: str, change: str) -> str:
    marker_color = _marker_color(raw_change)
    if not marker_color:
        return ""
    normalized_change = re.sub(r"[🟢🔴⚪\s]", "", change or "")
    return _opposite_color(marker_color) if normalized_change.startswith("-") else marker_color

def _ranking_change_tone(change: str, *, positive_tone: str, negative_tone: str, default_tone: str) -> str:
    normalized_change = (change or "").strip()
    if normalized_change.startswith("+"):
        return positive_tone
    if normalized_change.startswith("-"):
        return negative_tone
    return default_tone

def _tone_for_action(action: str) -> str:
    normalized = (action or "").lower()
    if any(term in normalized for term in ("买", "加仓", "buy", "add")):
        return "positive"
    if any(term in normalized for term in ("卖", "减仓", "回避", "sell", "reduce", "avoid")):
        return "negative"
    return "primary"

def _tone_for_score(score: str) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "primary"
    if value > 60:
        return "positive"
    if value < 40:
        return "negative"
    return "warning"

def _tone_for_trend(trend: str) -> str:
    normalized = (trend or "").lower()
    if any(term in normalized for term in ("看多", "bull", "uptrend")):
        return "positive"
    if any(term in normalized for term in ("看空", "bear", "downtrend")):
        return "negative"
    return "primary"

def _stock_positive_tone(code: str) -> str:
    normalized = (code or "").strip().upper()
    red_up_market = bool(
        re.fullmatch(r"\d{6}", normalized)
        or re.match(r"^(?:SH|SZ|BJ|HK)\d+", normalized)
        or re.search(r"\.(?:SH|SS|SZ|BJ|HK|T|TW|TWO|KS|KQ)$", normalized)
    )
    return "red" if red_up_market else "green"
