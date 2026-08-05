# -*- coding: utf-8 -*-
"""Share-image dataclasses and stock/market poster data assembly."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping, Optional

from .formatting import (
    _QUOTE_RE,
    _DATE_RE,
    _CODE_RE,
    _plain,
    _clean_value,
    _compact_text,
    _nested_mapping,
    _poster_language,
    _metric_value,
    _merge_metrics,
    _merge_compact_list,
    _market_light_overlay_allowed,
    _merge_index_cards,
    _merge_sector_rankings,
    _number_text,
    _compact_turnover,
    _signed_percent,
    _compact_sniper_value,
    _compact_position,
    _opposite_color,
    _marker_color,
    _positive_color_from_change,
    _ranking_change_tone,
    _tone_for_score,
    _stock_positive_tone,
)
from .parsing import (
    _extract_sections,
    _section,
    _parse_tables,
    _table_map,
    _find_table,
    _mapped_value,
    _has_meaningful_section,
    _meaningful_market_subsection_count,
    _labeled_value,
    _labeled_line,
    _list_after_label,
    _section_items,
    _sentences,
    _extract_date,
    _market_label,
    _market_region_hint,
    _market_label_for_region,
    _stock_heading_entry,
    _stock_headings,
    _is_market_review_title,
)

@dataclass(frozen=True)
class ShareImageBranding:
    """Optional deployment-owned social branding for share posters."""

    xiaohongshu_url: str = ""
    xiaohongshu_handle: str = ""
    xiaohongshu_id: str = ""
    xiaohongshu_qr_path: str = ""

    @property
    def has_xiaohongshu(self) -> bool:
        return any((
            self.xiaohongshu_url,
            self.xiaohongshu_handle,
            self.xiaohongshu_id,
            self.xiaohongshu_qr_path,
        ))

@dataclass
class StockPoster:
    title: str
    language: str = "zh"
    code: str = ""
    report_date: str = ""
    action: str = ""
    score: str = ""
    trend: str = ""
    confidence: str = ""
    conclusion: str = ""
    snapshot: list[tuple[str, str, str]] = field(default_factory=list)
    sniper: list[tuple[str, str, str]] = field(default_factory=list)
    technical: list[tuple[str, str, str]] = field(default_factory=list)
    catalysts: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    watch_items: list[tuple[str, str, str]] = field(default_factory=list)
    no_position: str = ""
    has_position: str = ""
    position_size: str = ""
    entry_plan: str = ""
    risk_control: str = ""
    data_source: str = ""

@dataclass
class MarketPoster:
    title: str
    language: str = "zh"
    report_date: str = ""
    summary: str = ""
    score: str = ""
    temperature: str = ""
    signal: str = ""
    guidance: str = ""
    reasons: list[str] = field(default_factory=list)
    indices: list[tuple[str, str, str, str]] = field(default_factory=list)
    breadth: list[tuple[str, str, str]] = field(default_factory=list)
    dimensions: list[tuple[str, str, str]] = field(default_factory=list)
    sectors: list[tuple[str, str, str]] = field(default_factory=list)
    laggards: list[tuple[str, str, str]] = field(default_factory=list)
    funds: list[tuple[str, str, str]] = field(default_factory=list)
    focus: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    catalysts: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

def _stock_data(markdown_text: str, generated_on: date) -> StockPoster:
    headings = _stock_headings(markdown_text)
    if headings:
        name, code = headings[0]
    else:
        first_title = next((title for title, _body, _level in _extract_sections(markdown_text)), "个股分析")
        entry = _stock_heading_entry(first_title)
        if entry:
            name, code = entry
        else:
            match = _CODE_RE.search(first_title)
            if match and match.start() == 0:
                # US ticker-only titles (and titles containing escaped HTML) read
                # better as one title than as an empty name plus a detached code.
                code = ""
                name = _plain(first_title)
            else:
                code = match.group(1).upper() if match else ""
                name = _plain(first_title[: match.start()] if match else first_title)
            name = re.sub(r"(?:分析报告|analysis report)$", "", name, flags=re.IGNORECASE).strip()

    score_match = re.search(r"(?:评分|score)\s*[:：]?\s*\*{0,2}(\d{1,3})", markdown_text, re.IGNORECASE)
    core = _section(markdown_text, "核心结论", "core conclusion", "核心判断")
    action_terms = (
        "买入", "加仓", "持有", "观望", "减仓", "卖出", "回避", "警戒",
        "buy", "add", "hold", "watch", "reduce", "sell", "avoid", "alert",
    )
    action_value = next(
        (
            candidate
            for candidate in (
                _clean_value(raw_candidate, limit=18)
                for raw_candidate in re.findall(
                    r"\*\*([^*\n]+)\*\*\s*[:：]",
                    core or markdown_text,
                    re.IGNORECASE,
                )
            )
            if any(term in candidate.lower() for term in action_terms)
        ),
        "",
    )
    quote_trend_match = re.search(
        r"^\s*>\s+.*?(?:评分|score)\s*[:：]?\s*\*{0,2}\d{1,3}\*{0,2}\s*\|\s*([^\n|]+)",
        markdown_text,
        re.IGNORECASE | re.MULTILINE,
    )
    trend_match = re.search(r"\*\*[^\n]+?\*\*\s*\|\s*([^\n]+)", core)
    conclusion = _labeled_value(core, "一句话决策", "One-line Decision", limit=110)
    if not conclusion:
        match = re.search(r"\*\*[^\n]+?\*\*\s*[:：]\s*(.+)", core)
        conclusion = _clean_value(match.group(1), limit=110) if match else ""

    poster = StockPoster(
        title=name or "个股分析",
        language=_poster_language(markdown_text),
        code=code,
        report_date=_extract_date(markdown_text, generated_on),
        action=action_value,
        score=score_match.group(1) if score_match else "",
        trend=(
            _clean_value(quote_trend_match.group(1), limit=16)
            if quote_trend_match
            else _clean_value(trend_match.group(1), limit=16) if trend_match else ""
        ),
        conclusion=conclusion,
    )

    snapshot_section = _section(markdown_text, "市场快照", "当日行情", "market snapshot", "시세 스냅샷")
    snapshot_map: dict[str, str] = {}
    for table in _parse_tables(snapshot_section):
        if len(table.rows) == 1:
            snapshot_map.update(
                {_plain(header).lower(): _clean_value(value) for header, value in zip(table.headers, table.rows[0])}
            )
        snapshot_map.update(_table_map(table))
    current = _mapped_value(snapshot_map, "当前价", "current price", "price") or _mapped_value(
        snapshot_map, "收盘价", "收盘", "close"
    )
    change = _mapped_value(snapshot_map, "涨跌幅", "change %", "change pct")
    ratio = _mapped_value(snapshot_map, "量比", "volume ratio")
    turnover = _mapped_value(snapshot_map, "换手率", "turnover rate")
    for label, value, tone in (
        ("当前/收盘", current, "primary"),
        ("涨跌幅", change, "up" if not change.startswith("-") else "down"),
        ("量比", ratio, "neutral"),
        ("换手率", turnover, "neutral"),
    ):
        if value:
            poster.snapshot.append((label, value, tone))
    poster.data_source = _mapped_value(snapshot_map, "数据源", "行情来源", "source")

    data_section = _section(markdown_text, "数据透视", "data view", "技术面", "technicals")
    data_map: dict[str, str] = {}
    for table in _parse_tables(data_section):
        data_map.update(_table_map(table))
    ma = _labeled_value(data_section, "均线排列", "MA Alignment", limit=42)
    ma = next((label for label in ("多头排列", "空头排列") if label in ma), _compact_text(ma, limit=16))
    volume_ratio = _labeled_line(data_section, "量能", "成交量", "Volume", limit=64)
    support = _mapped_value(data_map, "支撑位", "support")
    resistance = _mapped_value(data_map, "压力位", "resistance")
    for label, value, tone in (
        ("均线", ma, "positive" if "多头" in ma.lower() or "bull" in ma.lower() else "neutral"),
        ("量能", volume_ratio, "neutral"),
        ("支撑", support, "positive"),
        ("压力", resistance, "negative"),
    ):
        if value:
            poster.technical.append((label, value, tone))

    battle = _section(markdown_text, "作战计划", "battle plan", "操作计划", "操作点位", "action levels")
    sniper_table = _find_table(battle, "理想") or _find_table(battle, "ideal")
    sniper_values: dict[str, str] = {}
    if sniper_table:
        if len(sniper_table.headers) >= 3 and len(sniper_table.rows) == 1:
            sniper_values = {
                _plain(header).lower(): _clean_value(value, limit=62)
                for header, value in zip(sniper_table.headers, sniper_table.rows[0])
            }
        else:
            sniper_values = _table_map(sniper_table)
    for labels, display, tone in (
        (("理想买入点", "ideal entry"), "理想买入", "buy"),
        (("次优买入点", "secondary entry"), "次优买入", "secondary"),
        (("止损位", "stop loss"), "止损", "stop"),
        (("目标位", "target"), "目标", "target"),
    ):
        raw_value = _mapped_value(sniper_values, *labels)
        key = {
            "理想买入": "ideal_buy",
            "次优买入": "secondary_buy",
            "止损": "stop_loss",
            "目标": "take_profit",
        }[display]
        value = _compact_sniper_value(key, raw_value)
        if value:
            poster.sniper.append(("确认买入" if display == "次优买入" else display, value, tone))

    info = _section(markdown_text, "重要信息", "key updates", "消息面", "news flow")
    poster.catalysts = [
        _compact_text(item, limit=36)
        for item in _list_after_label(info, "利好催化", "positive catalysts")[:2]
    ]
    poster.risks = [
        _compact_text(item, limit=36)
        for item in _list_after_label(info, "风险警报", "risk alerts")[:2]
    ]
    if not poster.risks:
        poster.risks = [
            _compact_text(item, limit=36)
            for item in _section_items(
                _section(markdown_text, "风险提示", "risk warning", "risk alerts"), limit=2
            )
        ]

    position_table = _find_table(core, "持仓") or _find_table(core, "position")
    if position_table:
        position_map = _table_map(position_table)
        poster.no_position = _mapped_value(position_map, "空仓", "no position")
        poster.has_position = _mapped_value(position_map, "持仓者", "holding")
    position_section = _section(markdown_text, "持仓建议", "position advice")
    if not poster.no_position:
        poster.no_position = _labeled_value(position_section, "空仓者", "no position", limit=90)
    if not poster.has_position:
        poster.has_position = _labeled_value(position_section, "持仓者", "holding", limit=90)
    poster.no_position = _compact_position(poster.no_position, holding=False)
    poster.has_position = _compact_position(poster.has_position, holding=True)
    return poster

def _stock_data_from_payload(
    payload: Mapping[str, Any],
    markdown_text: str,
    generated_on: date,
) -> StockPoster:
    """Prefer the analysis JSON contract and retain Markdown as a field fallback."""

    poster = _stock_data(markdown_text, generated_on)
    poster.language = _poster_language(markdown_text, payload)
    dashboard = payload.get("dashboard")
    if not isinstance(dashboard, Mapping):
        dashboard = {}

    core = _nested_mapping(dashboard, "core_conclusion")
    data_view = _nested_mapping(dashboard, "data_perspective")
    price = _nested_mapping(data_view, "price_position")
    volume = _nested_mapping(data_view, "volume_analysis")
    trend = _nested_mapping(data_view, "trend_status")
    intelligence = _nested_mapping(dashboard, "intelligence")
    battle = _nested_mapping(dashboard, "battle_plan")
    sniper = _nested_mapping(battle, "sniper_points")
    position_advice = _nested_mapping(core, "position_advice")
    phase = _nested_mapping(dashboard, "phase_decision")

    poster.title = _clean_value(payload.get("name"), limit=30) or poster.title
    poster.code = _clean_value(payload.get("code"), limit=16) or poster.code
    poster.action = _clean_value(
        payload.get("action_label") or payload.get("operation_advice"), limit=12
    ) or poster.action
    score = payload.get("sentiment_score")
    if score is not None:
        poster.score = _number_text(score)
    poster.trend = _clean_value(payload.get("trend_prediction"), limit=16) or poster.trend
    poster.confidence = _clean_value(
        payload.get("confidence_level") or dashboard.get("confidence_level"),
        limit=10,
    )
    poster.conclusion = _compact_text(core.get("one_sentence"), limit=54) or poster.conclusion

    persisted_snapshot = _nested_mapping(payload, "market_snapshot")
    current = _number_text(payload.get("current_price") or price.get("current_price"))
    if not current:
        current = _clean_value(
            persisted_snapshot.get("price") or persisted_snapshot.get("close"),
            limit=18,
        )
    current = current or _metric_value(poster.snapshot, "现价", "当前/收盘")
    change = _signed_percent(payload.get("change_pct"))
    if not change:
        change = _clean_value(persisted_snapshot.get("pct_chg"), limit=18)
    change = change or _metric_value(poster.snapshot, "涨跌", "涨跌幅")
    ratio = _number_text(volume.get("volume_ratio"))
    if not ratio:
        ratio = _clean_value(persisted_snapshot.get("volume_ratio"), limit=18)
    ratio = ratio or _metric_value(poster.snapshot, "量比")
    turnover = _number_text(volume.get("turnover_rate"), suffix="%")
    if not turnover:
        turnover = _clean_value(persisted_snapshot.get("turnover_rate"), limit=18)
    turnover = turnover or _metric_value(poster.snapshot, "换手", "换手率")
    positive_tone = _stock_positive_tone(poster.code)
    negative_tone = _opposite_color(positive_tone)
    poster.snapshot = [
        item for item in (
            ("现价", current, "primary"),
            ("涨跌", change, positive_tone if not change.startswith("-") else negative_tone),
            ("量比", ratio, "neutral"),
            ("换手", turnover, "neutral"),
        ) if item[1]
    ]
    poster.data_source = (
        _clean_value(persisted_snapshot.get("source"), limit=30)
        or poster.data_source
    )

    ma_alignment = _clean_value(trend.get("ma_alignment"), limit=60)
    ma_summary = next(
        (label for label in ("多头排列", "空头排列") if label in ma_alignment),
        _compact_text(ma_alignment, limit=16),
    )
    support = _number_text(price.get("support_level"))
    resistance = _number_text(price.get("resistance_level"))
    trend_score = _number_text(trend.get("trend_score"), suffix="/100")
    bias_ma5 = _signed_percent(price.get("bias_ma5"))
    payload_technical = [
        item for item in (
            ("均线", ma_summary, "positive" if "多头" in ma_summary else "negative" if "空头" in ma_summary else "neutral"),
            ("趋势分", trend_score, _tone_for_score(_number_text(trend.get("trend_score")))),
            ("MA5乖离", bias_ma5, "positive" if not bias_ma5.startswith("-") else "negative"),
            ("支撑", support, "positive"),
            ("压力", resistance, "negative"),
        ) if item[1]
    ]
    existing_technical = poster.technical
    if any(volume.get(key) is not None for key in ("volume_ratio", "turnover_rate")):
        # Ratio/turnover already appear in the snapshot.  Keep the verbose
        # Markdown volume prose only for older/partial payloads that do not
        # carry those exact structured fields.
        existing_technical = [
            item for item in existing_technical if item[0] != "量能"
        ]
    poster.technical = _merge_metrics(existing_technical, payload_technical)

    payload_sniper: list[tuple[str, str, str]] = []
    for key, label, tone in (
        ("ideal_buy", "理想买入", "buy"),
        ("secondary_buy", "确认买入", "secondary"),
        ("stop_loss", "止损", "stop"),
        ("take_profit", "目标", "target"),
    ):
        value = _compact_sniper_value(key, sniper.get(key))
        if value:
            payload_sniper.append((label, value, tone))
    poster.sniper = _merge_metrics(poster.sniper, payload_sniper)

    catalysts = intelligence.get("positive_catalysts")
    risks = intelligence.get("risk_alerts")
    if isinstance(catalysts, list):
        poster.catalysts = _merge_compact_list(poster.catalysts, catalysts)
    if isinstance(risks, list):
        poster.risks = _merge_compact_list(poster.risks, risks)

    watch_conditions = phase.get("watch_conditions")
    payload_watch_items = [
        item for item in (
            ("行动窗口", _compact_text(phase.get("action_window"), limit=24), "primary"),
            ("下次检查", _compact_text(phase.get("next_check_time"), limit=28), "secondary"),
        ) if item[1]
    ]
    if isinstance(watch_conditions, list):
        payload_watch_items.extend(
            (f"观察 {index}", _compact_text(value, limit=31), "warning")
            for index, value in enumerate(watch_conditions[:2], 1)
            if _clean_value(value)
        )
    if payload_watch_items:
        poster.watch_items = payload_watch_items

    poster.no_position = (
        _compact_position(position_advice.get("no_position"), holding=False)
        or poster.no_position
    )
    poster.has_position = (
        _compact_position(position_advice.get("has_position"), holding=True)
        or poster.has_position
    )
    # The full report keeps sizing, entry and risk-control prose.  The share
    # poster intentionally shows only the two user states above.
    poster.position_size = ""
    poster.entry_plan = ""
    poster.risk_control = ""
    return poster

def _market_title(markdown_text: str) -> str:
    first_title = next((title for title, _body, _level in _extract_sections(markdown_text)), "")
    language = _poster_language(markdown_text)
    if language in {"en", "ko"} and _is_market_review_title(first_title):
        return first_title
    market = _market_label(first_title)
    if market:
        return f"{market}市场复盘"
    hinted_market = _market_label_for_region(_market_region_hint(markdown_text))
    if hinted_market:
        return f"{hinted_market}市场复盘"
    market = _market_label(markdown_text[:600])
    if market:
        return f"{market}市场复盘"
    if _is_market_review_title(first_title):
        return first_title
    return "A股市场复盘"

def _parsed_breadth_metrics(overview: str) -> list[tuple[str, str]]:
    metrics: list[tuple[str, str]] = []
    advance_match = re.search(
        r"Advancers\s+([^/;\n]+?)\s*/\s*Decliners\s+([^/;\n]+?)(?:\s*/\s*Flat\s+([^;\n]+?))?(?=$|;|\n)",
        overview or "",
        flags=re.IGNORECASE,
    )
    if advance_match:
        metrics.extend(
            [
                ("上涨", _clean_value(advance_match.group(1), limit=32)),
                ("下跌", _clean_value(advance_match.group(2), limit=32)),
            ]
        )

    limit_match = re.search(
        r"Limit(?:-|\s)?up\s+([^/;\n]+?)\s*/\s*Limit(?:-|\s)?down\s+([^;\n]+?)(?=$|;|\n)",
        overview or "",
        flags=re.IGNORECASE,
    )
    if limit_match:
        metrics.extend(
            [
                ("涨停", _clean_value(limit_match.group(1), limit=32)),
                ("跌停", _clean_value(limit_match.group(2), limit=32)),
            ]
        )

    turnover_match = re.search(
        r"Turnover\s+(.+?)(?=$|;|\n)",
        overview or "",
        flags=re.IGNORECASE,
    )
    if turnover_match:
        metrics.append(("成交额", _clean_value(turnover_match.group(1), limit=48)))
    return [(label, value) for label, value in metrics if value]

def _parse_index_bullets(index_section: str) -> list[tuple[str, str, str, str]]:
    indices: list[tuple[str, str, str, str]] = []
    for line in (index_section or "").splitlines():
        match = re.match(
            r"^\s*[-*+]\s+(?:\*\*)?(?P<name>[^:*]+?)(?:\*\*)?\s*[:：]\s*(?P<current>[^()\n]+?)\s*\((?P<change>[^)\n]+)\)\s*$",
            line,
        )
        if not match:
            continue
        name = _clean_value(match.group("name"), limit=28)
        current = _clean_value(match.group("current"), limit=18)
        change = re.sub(r"\s+", " ", match.group("change")).strip()
        if not (name and current and change):
            continue
        color = _marker_color(change)
        if not color:
            color = "green" if any(marker in change for marker in ("↑", "+")) else "red" if any(marker in change for marker in ("↓", "-")) else ""
        indices.append((name, current, change, color))
        if len(indices) >= 4:
            break
    return indices

def _direction_items(value: object, *, limit: int = 2) -> list[str]:
    """Extract short sector/theme labels from a verbose plan sentence."""

    text = _clean_value(value, limit=220)
    if not text:
        return []
    text = re.sub(r"其[一二三四][、，,:：]?", "", text)
    clauses = [part.strip(" ，,；;") for part in re.split(r"[；;]", text) if part.strip()]
    items: list[str] = []
    for clause in clauses:
        qualified = re.findall(r"的([^，,；;等]{2,20})等", clause)
        candidates = re.findall(
            r"(?:^|[，,])([A-Za-z0-9一-鿿]+(?:、[A-Za-z0-9一-鿿]+)*)等",
            clause,
        )
        if qualified:
            label = qualified[-1]
        elif candidates:
            label = candidates[-1]
        else:
            label = re.split(r"[，,。]", clause, maxsplit=1)[0]
        label = re.sub(r"^(?:关注方向|回避方向)[:：]?", "", label).strip()
        label = _compact_text(label, limit=24)
        if label and label not in items:
            items.append(label)
        if len(items) >= limit:
            break
    return items

def _market_fund_metrics(markdown_text: str) -> list[tuple[str, str, str]]:
    section = _section(markdown_text, "资金与情绪", "fund flows", "liquidity & sentiment")
    if not section:
        return []
    metrics: list[tuple[str, str, str]] = []
    ratio = re.search(r"涨跌比(?:接近|约为|约)?\s*([\d.]+\s*:\s*[\d.]+)", section)
    if ratio:
        metrics.append(("涨跌比", ratio.group(1).replace(" ", ""), "positive"))
    increment = re.search(
        r"较前(?:一交易日|日).*?放量(?:超|逾)?\s*([\d.]+)\s*亿元",
        section,
    )
    if increment:
        metrics.append(("增量成交", f"+{increment.group(1)}亿", "primary"))
    if any(term in section for term in ("科技", "科创", "半导体")) and any(
        term in section for term in ("分歧", "冲高回落", "兑现")
    ):
        metrics.append(("资金风格", "科技主导·高位分歧", "warning"))
    return metrics[:3]

def _market_data(markdown_text: str, generated_on: date) -> MarketPoster:
    overview = _section(markdown_text, "盘面总览", "market summary", "breadth & liquidity", "시장 요약")
    score_match = re.search(
        r"(?:盘面信号|市场信号|market signal|시장 신호)\*{0,2}\s*[:：]\s*(\d{1,3})/100(?:\s*[（(]([^，,)]+)[，,]\s*([^）)]+)[）)])?",
        markdown_text,
        re.IGNORECASE,
    )
    quote = _QUOTE_RE.search(markdown_text)
    poster = MarketPoster(
        title=_market_title(markdown_text),
        language=_poster_language(markdown_text),
        report_date=_extract_date(markdown_text, generated_on),
        summary=_compact_text(quote.group(1), limit=58) if quote else "",
        score=score_match.group(1) if score_match else "",
        temperature=_clean_value(score_match.group(2), limit=12) if score_match and score_match.group(2) else "",
        signal=_clean_value(score_match.group(3), limit=12) if score_match and score_match.group(3) else "",
        guidance=_compact_text(
            _labeled_value(overview, "操作建议", "Guidance", "운용 제안", "가이던스", limit=100),
            limit=52,
        ),
    )
    reason_text = _labeled_value(overview, "信号依据", "Drivers", "신호 근거", "동인", limit=220)
    poster.reasons = [
        _compact_text(item, limit=34)
        for item in re.split(r"[；;]", reason_text)
        if _clean_value(item, limit=72)
    ][:3]
    if not poster.reasons and poster.summary:
        poster.reasons = _sentences(poster.summary, limit=2)

    index_section = _section(markdown_text, "指数结构", "major indices", "index commentary", "주요 지수", "지수 구조")
    index_table = (
        _find_table(index_section, "指数", "涨跌幅")
        or _find_table(index_section, "index", "change")
        or _find_table(index_section, "지수", "등락률")
    )
    positive_color = "green"
    if index_table:
        headers = [header.lower() for header in index_table.headers]
        name_i = next((i for i, value in enumerate(headers) if "指数" in value or "index" in value or "지수" in value), 0)
        current_i = next((i for i, value in enumerate(headers) if "最新" in value or "last" in value or "최신" in value), 1)
        change_i = next((i for i, value in enumerate(headers) if "涨跌幅" in value or "change" in value or "등락률" in value), 2)
        for row_index, row in enumerate(index_table.rows[:4]):
            if len(row) > max(name_i, current_i, change_i):
                raw_change = (
                    index_table.raw_rows[row_index][change_i]
                    if row_index < len(index_table.raw_rows)
                    and len(index_table.raw_rows[row_index]) > change_i
                    else row[change_i]
                )
                color = _marker_color(raw_change)
                if not color:
                    color = "red" if row[change_i].strip().startswith("-") else "green"
                positive_color = _positive_color_from_change(raw_change, row[change_i]) or positive_color
                poster.indices.append((row[name_i], row[current_i], row[change_i], color))
    if not poster.indices:
        poster.indices = _parse_index_bullets(index_section)
        if poster.indices:
            first_change = poster.indices[0][2]
            inferred_positive_color = _positive_color_from_change(first_change, first_change)
            if inferred_positive_color:
                positive_color = inferred_positive_color

    breadth_table = (
        _find_table(overview, "上涨", "成交额")
        or _find_table(overview, "breadth")
        or _find_table(overview, "상승", "거래대금")
    )
    if breadth_table:
        mapping = _table_map(breadth_table)
        advance = _mapped_value(mapping, "上涨/下跌", "advancers", "상승/하락")
        limits = _mapped_value(mapping, "涨停/跌停", "limit-up", "상한가/하한가")
        amount = _mapped_value(mapping, "成交额", "turnover", "거래대금")
        if advance:
            parts = [part.strip() for part in advance.split("/")]
            if parts:
                poster.breadth.append(("上涨", parts[0], positive_color))
            if len(parts) > 1:
                negative_color = "red" if positive_color == "green" else "green"
                poster.breadth.append(("下跌", parts[1], negative_color))
        if limits:
            parts = [part.strip() for part in limits.split("/")]
            if parts:
                poster.breadth.append(("涨停", parts[0], positive_color))
            if len(parts) > 1:
                negative_color = "red" if positive_color == "green" else "green"
                poster.breadth.append(("跌停", parts[1], negative_color))
        if amount:
            poster.breadth.append(("成交额", amount, "primary"))
    if not poster.breadth:
        for label, value in _parsed_breadth_metrics(overview):
            if label == "上涨":
                tone = positive_color
            elif label in {"下跌", "跌停"}:
                tone = "red" if positive_color == "green" else "green"
            elif label == "涨停":
                tone = positive_color
            else:
                tone = "primary"
            poster.breadth.append((label, value, tone))

    sector_section = _section(markdown_text, "板块主线", "sector highlights", "섹터 하이라이트", "주도 섹터")
    sector_table = (
        _find_table(sector_section, "板块", "涨跌幅")
        or _find_table(sector_section, "sector", "change")
        or _find_table(sector_section, "섹터", "등락률")
    )
    if sector_table:
        for row in sector_table.rows[:3]:
            if len(row) >= 3:
                change = _clean_value(row[-1], limit=12)
                poster.sectors.append(
                    (
                        _clean_value(row[-2], limit=20),
                        change,
                        _ranking_change_tone(
                            change,
                            positive_tone=positive_color,
                            negative_tone=_opposite_color(positive_color),
                            default_tone=positive_color,
                        ),
                    )
                )
    sector_tables = [
        table
        for table in _parse_tables(sector_section)
        if any(term in " ".join(table.headers).lower() for term in ("板块", "sector", "섹터"))
    ]
    if len(sector_tables) > 1:
        for row in sector_tables[1].rows[:3]:
            if len(row) >= 3:
                change = _clean_value(row[-1], limit=12)
                poster.laggards.append(
                    (
                        _clean_value(row[-2], limit=20),
                        change,
                        _ranking_change_tone(
                            change,
                            positive_tone=positive_color,
                            negative_tone=_opposite_color(positive_color),
                            default_tone=_opposite_color(positive_color),
                        ),
                    )
                )

    catalyst_section = _section(markdown_text, "消息催化", "news catalysts", "뉴스 촉매")
    poster.catalysts = [
        _compact_text(item, limit=34)
        for item in (_section_items(catalyst_section, limit=2) or _sentences(catalyst_section, limit=2))
    ]
    plan_section = _section(markdown_text, "明日交易计划", "strategy plan", "outlook", "내일 거래 계획", "내일 계획")
    poster.focus = _direction_items(
        _labeled_value(plan_section, "关注方向", "focus", "관심 방향", limit=220)
    )
    poster.avoid = _direction_items(
        _labeled_value(plan_section, "回避方向", "avoid", "회피 방향", limit=220)
    )
    poster.funds = _market_fund_metrics(markdown_text)
    for label in ("结论", "仓位区间", "触发失效条件", "결론", "비중 구간", "무효화 조건"):
        value = _labeled_value(plan_section, label, limit=86)
        if value:
            poster.plan.append(_compact_text(f"{label}：{value}", limit=32))
        if len(poster.plan) >= 3:
            break
    if not poster.plan:
        poster.plan = [
            _compact_text(item, limit=32)
            for item in (_section_items(plan_section, limit=3) or _sentences(plan_section, limit=3))
        ]
    poster.risks = [
        _compact_text(item, limit=34)
        for item in _section_items(
            _section(markdown_text, "风险提示", "risk alerts", "리스크 경보", "리스크 경고"),
            limit=2,
        )
    ]
    return poster

def _market_data_from_payload(
    payload: Mapping[str, Any],
    markdown_text: str,
    generated_on: date,
) -> MarketPoster:
    """Overlay exact market metrics from the persisted market-review payload."""

    poster = _market_data(markdown_text, generated_on)
    poster.language = _poster_language(markdown_text, payload)
    payload_title = _clean_value(payload.get("title"), limit=36)
    if payload_title and not _DATE_RE.match(payload_title):
        poster.title = payload_title
    poster.report_date = _clean_value(payload.get("date"), limit=18) or poster.report_date
    color_scheme = str(payload.get("color_scheme") or "").strip().lower()
    if color_scheme == "red_up":
        positive_tone = "red"
    elif color_scheme == "green_up":
        positive_tone = "green"
    else:
        positive_tone = "green"
        for _name, _current, change, color in poster.indices:
            if not color or not change:
                continue
            positive_tone = _opposite_color(color) if change.strip().startswith("-") else color
            break
    negative_tone = _opposite_color(positive_tone)

    light = payload.get("market_light")
    if isinstance(light, Mapping):
        if _market_light_overlay_allowed(light) and light.get("score") is not None:
            poster.score = _number_text(light.get("score"))
        if _market_light_overlay_allowed(light):
            poster.temperature = _clean_value(light.get("temperature_label"), limit=12) or poster.temperature
            poster.signal = (
                _clean_value(light.get("label"), limit=12)
                or poster.signal
                or poster.temperature
            )
            dimensions = light.get("dimensions")
            if isinstance(dimensions, Mapping):
                for key, label in (
                    ("breadth", "赚钱效应"),
                    ("index", "指数强度"),
                    ("limit", "涨停结构"),
                ):
                    dimension = dimensions.get(key)
                    if (
                        not isinstance(dimension, Mapping)
                        or dimension.get("score") is None
                        or dimension.get("available") is False
                    ):
                        continue
                    score = _number_text(dimension.get("score"))
                    try:
                        numeric_score = float(dimension.get("score"))
                    except (TypeError, ValueError):
                        numeric_score = 0
                    tone = "positive" if numeric_score >= 70 else "warning" if numeric_score >= 50 else "negative"
                    poster.dimensions.append((label, f"{score}/100", tone))

    indices = payload.get("indices")
    if isinstance(indices, list):
        structured_indices = [item for item in indices[:4] if isinstance(item, Mapping)]
        if structured_indices:
            poster.indices = _merge_index_cards(
                poster.indices,
                structured_indices,
                positive_tone=positive_tone,
                negative_tone=negative_tone,
            )

    breadth = payload.get("breadth")
    if isinstance(breadth, Mapping):
        amount = _compact_turnover(
            breadth.get("total_amount"),
            breadth.get("turnover_unit"),
        )
        exact_breadth = [
            item for item in (
                ("上涨", _number_text(breadth.get("up_count")), positive_tone),
                ("下跌", _number_text(breadth.get("down_count")), negative_tone),
                ("涨停", _number_text(breadth.get("limit_up_count")), "hot"),
                ("跌停", _number_text(breadth.get("limit_down_count")), negative_tone),
                ("成交额", amount, "primary"),
            ) if item[1]
        ]
        if exact_breadth:
            poster.breadth = _merge_metrics(poster.breadth, exact_breadth)

    sectors = payload.get("sectors")
    top_sectors = sectors.get("top") if isinstance(sectors, Mapping) else None
    if isinstance(top_sectors, list):
        structured_top = [item for item in top_sectors[:3] if isinstance(item, Mapping)]
        if structured_top:
            poster.sectors = _merge_sector_rankings(
                poster.sectors,
                structured_top,
                positive_tone=positive_tone,
                negative_tone=negative_tone,
                default_tone=positive_tone,
            )
    bottom_sectors = sectors.get("bottom") if isinstance(sectors, Mapping) else None
    if isinstance(bottom_sectors, list):
        structured_bottom = [item for item in bottom_sectors[:3] if isinstance(item, Mapping)]
        if structured_bottom:
            poster.laggards = _merge_sector_rankings(
                poster.laggards,
                structured_bottom,
                positive_tone=positive_tone,
                negative_tone=negative_tone,
                default_tone=negative_tone,
            )
    return poster

def _should_keep_market_fallback(markdown_text: str, data: MarketPoster) -> bool:
    expected_sections = (
        (
            _has_meaningful_section(markdown_text, "盘面总览", "market summary", "breadth & liquidity", "시장 요약"),
            any((data.score, data.guidance, data.reasons, data.summary, data.breadth)),
        ),
        (
            _has_meaningful_section(markdown_text, "指数结构", "major indices", "index commentary", "주요 지수", "지수 구조"),
            bool(data.indices),
        ),
        (
            _has_meaningful_section(markdown_text, "板块主线", "sector highlights", "섹터 하이라이트", "주도 섹터"),
            bool(data.sectors),
        ),
        (
            _has_meaningful_section(markdown_text, "消息催化", "news catalysts", "뉴스 촉매"),
            bool(data.catalysts),
        ),
        (
            _has_meaningful_section(markdown_text, "明日交易计划", "strategy plan", "outlook", "내일 거래 계획", "내일 계획"),
            bool(data.plan),
        ),
        (
            _has_meaningful_section(markdown_text, "风险提示", "risk alerts", "리스크 경보", "리스크 경고"),
            bool(data.risks),
        ),
    )
    if any(expected and not populated for expected, populated in expected_sections):
        return True
    mapped_subsections = sum(1 for expected, populated in expected_sections if expected and populated)
    unmapped_subsections = max(
        0, _meaningful_market_subsection_count(markdown_text) - mapped_subsections
    )
    # A normal report may contain one explanatory detail section such as
    # “资金与情绪”.  That should not duplicate the entire report in a share
    # poster.  Keep the full fallback only when most localized sections remain
    # outside the structured contract.
    return unmapped_subsections > max(1, mapped_subsections)
