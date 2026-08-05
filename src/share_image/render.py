# -*- coding: utf-8 -*-
"""HTML body/footer construction for share-image posters."""

from __future__ import annotations

import html
import re
from datetime import date
from typing import Any, Iterable, Mapping, Optional
import markdown2

from .formatting import (
    PROJECT_REPOSITORY,
    PROJECT_DISPLAY_NAME,
    _HEADING_RE,
    _asset_data_uri,
    _poster_language,
    _poster_text,
    _poster_label,
    _escape,
    _tone_for_action,
    _tone_for_score,
    _tone_for_trend,
)
from .parsing import (
    MarketSegment,
    _extract_sections,
    _extract_date,
    _market_label,
    _stock_headings,
    _is_market_review_title,
    _market_segments,
)
from .model import (
    ShareImageBranding,
    StockPoster,
    MarketPoster,
    _stock_data,
    _stock_data_from_payload,
    _market_data,
    _market_data_from_payload,
    _should_keep_market_fallback,
)

def _metric_cards(
    items: Iterable[tuple[str, str, str]],
    class_name: str = "",
    *,
    language: str = "zh",
) -> str:
    cards = []
    for label, value, tone in items:
        classes = " ".join(part for part in ("metric", class_name, tone) if part)
        cards.append(
            f'<div class="{_escape(classes)}"><span>{_escape(_poster_label(language, label))}</span><strong>{_escape(value)}</strong></div>'
        )
    return "".join(cards)

def _list_html(items: Iterable[str], empty: str = "") -> str:
    values = [value for value in items if value]
    if not values:
        return f'<p class="muted">{_escape(empty)}</p>' if empty else ""
    return "<ul>" + "".join(f"<li>{_escape(value)}</li>" for value in values) + "</ul>"

def _section_html(title: str, icon: str, content: str, class_name: str = "") -> str:
    if not content:
        return ""
    return f'<section class="poster-section {class_name}"><h2><b>{_escape(icon)}</b>{_escape(title)}</h2>{content}</section>'

def _render_markdown_fragment(markdown_text: str) -> str:
    return markdown2.markdown(
        markdown_text,
        extras=["tables", "fenced-code-blocks", "break-on-newline", "cuddled-lists"],
        safe_mode="escape",
    )

def _stock_body(data: StockPoster, fallback_html: str) -> str:
    language = data.language
    tone = _tone_for_action(data.action)
    score_tone = _tone_for_score(data.score)
    trend_tone = _tone_for_trend(data.trend)
    score = f'<div class="signal-score {score_tone}"><span>{_escape(_poster_text(language, "score"))}</span><strong>{_escape(data.score)}</strong><small>/100</small></div>' if data.score else ""
    confidence = f'<small>{_escape(_poster_text(language, "confidence"))} {_escape(data.confidence)}</small>' if data.confidence else ""
    trend = f'<div class="signal-trend {trend_tone}"><span>{_escape(_poster_text(language, "trend"))}</span><strong>{_escape(data.trend)}</strong>{confidence}</div>' if data.trend else ""
    action = f'<div class="action-chip {tone}">{_escape(data.action)}</div>' if data.action else ""
    signal_row = f'<div class="signal-row">{action}{score}{trend}</div>' if action or score or trend else ""
    conclusion = _section_html(_poster_text(language, "core"), "◎", f'<div class="conclusion">{_escape(data.conclusion)}</div>') if data.conclusion else ""
    snapshot = _section_html(_poster_text(language, "snapshot"), "▥", f'<div class="metric-grid snapshot-grid">{_metric_cards(data.snapshot, language=language)}</div>') if data.snapshot else ""
    sniper = _section_html(_poster_text(language, "execution"), "◎", f'<div class="metric-grid sniper-grid sniper-table">{_metric_cards(data.sniper, "sniper", language=language)}</div>') if data.sniper else ""
    technical = _section_html(_poster_text(language, "technical"), "⌁", f'<div class="metric-grid technical-grid">{_metric_cards(data.technical, language=language)}</div>') if data.technical else ""
    watch = _section_html(
        _poster_text(language, "next_watch"),
        "✓",
        '<div class="watch-grid">' + "".join(
            f'<div class="watch-card {tone_name}"><span>{_escape(_poster_label(language, label))}</span><p>{_escape(value)}</p></div>'
            for label, value, tone_name in data.watch_items
        ) + "</div>",
    ) if data.watch_items else ""
    insight_cards = ""
    if data.catalysts:
        insight_cards += f'<div class="insight positive"><h3>{_escape(_poster_text(language, "positive_catalysts"))}</h3>{_list_html(data.catalysts)}</div>'
    if data.risks:
        insight_cards += f'<div class="insight negative"><h3>{_escape(_poster_text(language, "risk_alerts"))}</h3>{_list_html(data.risks)}</div>'
    insights = _section_html(_poster_text(language, "catalysts_risks"), "!", f'<div class="two-column">{insight_cards}</div>') if insight_cards else ""
    position_rows = ""
    for label, value, tone_name in (
        (_poster_text(language, "no_position"), data.no_position, "primary"),
        (_poster_text(language, "holding"), data.has_position, "warning"),
        (_poster_text(language, "position"), data.position_size, "positive"),
    ):
        if value:
            position_rows += f'<div class="position-row"><span class="pill {tone_name}">{label}</span><p>{_escape(value)}</p></div>'
    if data.entry_plan:
        position_rows += f'<div class="position-row"><span class="pill primary">{_escape(_poster_text(language, "entry"))}</span><p>{_escape(data.entry_plan)}</p></div>'
    if data.risk_control:
        position_rows += f'<div class="position-row"><span class="pill negative">{_escape(_poster_text(language, "risk_control"))}</span><p>{_escape(data.risk_control)}</p></div>'
    positions = _section_html(_poster_text(language, "position_advice"), "▣", f'<div class="position-box">{position_rows}</div>') if position_rows else ""
    structured = any((signal_row, conclusion, snapshot, sniper, technical, watch, insights, positions))
    fallback = f'<section class="report-fallback"><article class="report-content">{fallback_html}</article></section>' if not structured else ""
    return f"{signal_row}{conclusion}{snapshot}{sniper}{technical}{watch}{insights}{positions}{fallback}"

def _market_body(data: MarketPoster, fallback_html: str, markdown_text: str) -> str:
    language = data.language
    signal = ""
    if data.score:
        signal = (
            '<section class="market-signal">'
            f'<div class="signal-main"><span>{_escape(_poster_text(language, "market_signal"))}</span>'
            f'<strong>{_escape(data.score)}</strong><small>/100</small></div>'
            f'<div class="market-label">{_escape(data.signal or data.temperature)}</div>'
            f'<div class="signal-guidance"><span>{_escape(_poster_text(language, "today_conclusion"))}</span><p>{_escape(data.guidance or data.summary)}</p></div>'
            '</section>'
        )
    elif any((data.guidance, data.summary, data.reasons)):
        overview_parts: list[str] = []
        conclusion = data.guidance or data.summary
        if conclusion:
            overview_parts.append(f'<div class="conclusion">{_escape(conclusion)}</div>')
        if data.reasons:
            overview_parts.append(_list_html(data.reasons))
        signal = _section_html(
            _poster_text(language, "today_conclusion"),
            "◎",
            "".join(overview_parts),
        )
    indices = ""
    if data.indices:
        cards = []
        for name, current, change, color in data.indices:
            cards.append(f'<div class="index-card"><span>{_escape(name)}</span><strong class="{color}">{_escape(change)}</strong><small>{_escape(current)}</small></div>')
        indices = f'<div class="index-grid">{"".join(cards)}</div>'
    breadth = _section_html(_poster_text(language, "breadth"), "↕", f'<div class="metric-grid breadth-grid">{_metric_cards(data.breadth, language=language)}</div>') if data.breadth else ""
    dimensions = _section_html(
        _poster_text(language, "dimensions"),
        "◫",
        f'<div class="metric-grid dimension-grid">{_metric_cards(data.dimensions, language=language)}</div>',
    ) if data.dimensions else ""
    sector_rows = "".join(
        f'<div class="ranking-row"><b>{index:02d}</b><span>{_escape(name)}</span><strong class="{_escape(tone)}">{_escape(change)}</strong></div>'
        for index, (name, change, tone) in enumerate(data.sectors, 1)
    )
    laggard_rows = "".join(
        f'<div class="ranking-row lagging"><b>{index:02d}</b><span>{_escape(name)}</span><strong class="{_escape(tone)}">{_escape(change)}</strong></div>'
        for index, (name, change, tone) in enumerate(data.laggards, 1)
    )
    sectors = _section_html(_poster_text(language, "leaders"), "◆", f'<div class="ranking">{sector_rows}</div>') if sector_rows else ""
    laggards = _section_html(_poster_text(language, "laggards"), "◇", f'<div class="ranking">{laggard_rows}</div>') if laggard_rows else ""
    sector_dual = (
        f'<div class="market-two-column"><div class="market-left">{sectors}</div>'
        f'<div class="market-right">{laggards}</div></div>'
        if sectors or laggards else ""
    )
    focus_rows = "".join(
        f'<div class="focus-row"><b>{_escape(_poster_text(language, "focus_tag"))}</b><span>{_escape(value)}</span></div>'
        for value in data.focus
    ) + "".join(
        f'<div class="focus-row avoid"><b>{_escape(_poster_text(language, "avoid_tag"))}</b><span>{_escape(value)}</span></div>'
        for value in data.avoid
    )
    fund_rows = "".join(
        f'<div class="fund-row {_escape(tone)}"><span>{_escape(_poster_label(language, label))}</span><strong>{_escape(value)}</strong></div>'
        for label, value, tone in data.funds
    )
    focus = _section_html(_poster_text(language, "focus"), "◎", f'<div class="focus-list">{focus_rows}</div>') if focus_rows else ""
    funds = _section_html(_poster_text(language, "funds"), "↗", f'<div class="fund-list">{fund_rows}</div>') if fund_rows else ""
    detail_dual = (
        f'<div class="market-two-column market-details"><div class="market-left">{focus}</div>'
        f'<div class="market-right">{funds}</div></div>'
        if focus or funds else ""
    )
    catalysts = _section_html(
        _poster_text(language, "positive_catalysts"),
        "✦",
        _list_html(data.catalysts),
    ) if data.catalysts else ""
    plan = _section_html(_poster_text(language, "strategy"), "✓", _list_html(data.plan), "strategy-strip") if data.plan else ""
    risks = _section_html(_poster_text(language, "risks"), "!", _list_html(data.risks), "risk-strip") if data.risks else ""
    structured = any((signal, indices, breadth, dimensions, sector_dual, detail_dual, catalysts, plan, risks))
    keep_fallback = not structured or _should_keep_market_fallback(markdown_text, data)
    fallback = f'<section class="report-fallback"><article class="report-content">{fallback_html}</article></section>' if keep_fallback else ""
    return f"{signal}{indices}{breadth}{dimensions}{sector_dual}{detail_dual}{catalysts}{plan}{risks}{fallback}"

def _generic_body(report_html: str) -> str:
    return f'<section class="report-fallback"><article class="report-content">{report_html}</article></section>'

def _market_region_for_segment(segment: MarketSegment) -> str:
    label = _market_label(segment.title) or _market_label(segment.markdown[:500])
    return {
        "A股": "cn",
        "港股": "hk",
        "美股": "us",
        "日股": "jp",
        "韩股": "kr",
    }.get(label, "")

def _multi_market_body(
    segments: list[MarketSegment],
    generated_on: date,
    structured_payload: Optional[Mapping[str, Any]] = None,
) -> str:
    blocks: list[str] = []
    markets = structured_payload.get("markets") if isinstance(structured_payload, Mapping) else None
    market_payloads = markets if isinstance(markets, Mapping) else {}
    unused_regions = [
        region for region in ("cn", "hk", "us", "jp", "kr")
        if isinstance(market_payloads.get(region), Mapping)
    ]
    for segment in segments:
        body_markdown = _HEADING_RE.sub("", segment.markdown, count=1).strip()
        fallback_html = _render_markdown_fragment(body_markdown)
        region = _market_region_for_segment(segment)
        payload = market_payloads.get(region) if region else None
        if not isinstance(payload, Mapping) and unused_regions:
            payload = market_payloads.get(unused_regions[0])
            region = unused_regions[0]
        if region in unused_regions:
            unused_regions.remove(region)
        data = (
            _market_data_from_payload(payload, segment.markdown, generated_on)
            if isinstance(payload, Mapping)
            else _market_data(segment.markdown, generated_on)
        )
        title = data.title or segment.title
        blocks.append(
            f'<section class="poster-section market-region-title"><h2><b>◎</b>{_escape(title)}</h2></section>'
            f"{_market_body(data, fallback_html, segment.markdown)}"
        )
    return "".join(blocks)

def _safe_web_url(value: str) -> str:
    url = value.strip()
    return url if re.match(r"^https?://", url, re.IGNORECASE) else ""

def _xiaohongshu_card(branding: ShareImageBranding, language: str) -> str:
    if not branding.has_xiaohongshu:
        return ""

    label = _poster_text(language, "xiaohongshu")
    account_parts = [part for part in (
        branding.xiaohongshu_handle.strip(),
        f"ID {branding.xiaohongshu_id.strip()}" if branding.xiaohongshu_id.strip() else "",
    ) if part]
    account = " · ".join(account_parts) or branding.xiaohongshu_url.strip()
    qr_data_uri = _asset_data_uri(branding.xiaohongshu_qr_path)
    qr_alt = f"{label}二维码" if language == "zh" else f"{label} QR"
    image = (
        f'<div class="qr-frame"><img src="{qr_data_uri}" alt="{_escape(qr_alt)}"></div>'
        if qr_data_uri else ""
    )
    url = _safe_web_url(branding.xiaohongshu_url)
    if image and url:
        image = f'<a href="{_escape(url)}">{image}</a>'
    account_markup = (
        f'<span><b>{_escape(label)}</b>{(" " + _escape(account)) if account else ""}</span>'
    )
    if url:
        account_markup = f'<a class="social-link" href="{_escape(url)}">{account_markup}</a>'
    return (
        f'<div class="qr-card{(" text-only" if not image else "")}">{image}'
        f'{account_markup}</div>'
    )

def _footer(branding: ShareImageBranding, source_line: str, language: str) -> str:
    social_card = _xiaohongshu_card(branding, language)
    brand_class = "footer-brand" if social_card else "footer-brand full"
    return f"""
    <footer class="poster-footer">
      <div class="{brand_class}">
        <div class="footer-title"><strong>DSA</strong><span>{_escape(PROJECT_DISPLAY_NAME)}</span></div>
        <small>{_escape(_poster_text(language, "tagline"))}</small>
        <div class="repo-line">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0C3.58 0 0 3.64 0 8.13c0 3.59 2.29 6.64 5.47 7.71.4.08.55-.18.55-.39 0-.19-.01-.83-.01-1.51-2.01.38-2.53-.5-2.69-.96-.09-.23-.48-.96-.82-1.15-.28-.15-.68-.53-.01-.54.63-.01 1.08.59 1.23.83.72 1.23 1.87.88 2.33.67.07-.53.28-.88.51-1.08-1.78-.21-3.64-.91-3.64-4.02 0-.89.31-1.62.82-2.19-.08-.21-.36-1.04.08-2.16 0 0 .67-.22 2.2.84A7.45 7.45 0 0 1 8 3.91c.68 0 1.36.09 2 .27 1.53-1.06 2.2-.84 2.2-.84.44 1.12.16 1.95.08 2.16.51.57.82 1.3.82 2.19 0 3.12-1.87 3.81-3.65 4.02.29.25.54.74.54 1.5 0 1.08-.01 1.95-.01 2.22 0 .22.15.47.55.39A8.15 8.15 0 0 0 16 8.13C16 3.64 12.42 0 8 0Z"/></svg>
          <div><em>{_escape(_poster_text(language, "open_source"))}</em><b>{_escape(PROJECT_REPOSITORY)}</b></div>
        </div>
      </div>
      {social_card}
    </footer>
    <div class="disclaimer">{_escape(_poster_text(language, "disclaimer"))}{_escape(source_line)}</div>
    """

def build_share_image_html(
    markdown_text: str,
    *,
    generated_on: Optional[date] = None,
    structured_payload: Optional[Mapping[str, Any]] = None,
    branding: Optional[ShareImageBranding] = None,
) -> str:
    """Build a deterministic 1080px stock, market, or dashboard share poster.

    Structured analysis JSON is preferred when available; stable Markdown remains
    the compatibility fallback. Unknown fields are omitted. Optional social
    branding is supplied by deployment config and never fetched at render time.
    """

    generated = generated_on or date.today()
    language = _poster_language(markdown_text, structured_payload)
    headings = _extract_sections(markdown_text)
    first_title = headings[0][0] if headings else "股票智能分析报告"
    stock_headings = _stock_headings(markdown_text)
    market_segments = _market_segments(markdown_text)
    candidate_market_titles = headings[:2]
    is_market = any(
        level <= 2 and _is_market_review_title(title)
        for title, _body, level in candidate_market_titles
    )
    is_single_stock = len(stock_headings) == 1
    report_kind = "market" if is_market else "stock" if is_single_stock else "dashboard"

    body_markdown = _HEADING_RE.sub("", markdown_text, count=1).strip()
    fallback_html = _render_markdown_fragment(body_markdown)
    stamp = _extract_date(markdown_text, generated)
    source_line = ""
    if report_kind == "market":
        if market_segments:
            title = _poster_text(language, "multi_title")
            subtitle = _poster_text(language, "multi_subtitle")
            content = _multi_market_body(
                market_segments,
                generated,
                structured_payload=structured_payload,
            )
        else:
            data = (
                _market_data_from_payload(structured_payload, markdown_text, generated)
                if isinstance(structured_payload, Mapping)
                else _market_data(markdown_text, generated)
            )
            title = data.title
            language = data.language
            subtitle = data.summary or _poster_text(language, "market_subtitle")
            content = _market_body(data, fallback_html, markdown_text)
    elif report_kind == "stock":
        data = (
            _stock_data_from_payload(structured_payload, markdown_text, generated)
            if isinstance(structured_payload, Mapping)
            else _stock_data(markdown_text, generated)
        )
        title = data.title
        language = data.language
        subtitle = _poster_text(language, "stock_subtitle")
        content = _stock_body(data, fallback_html)
        if data.data_source:
            source_line = (
                f" 数据源：{data.data_source}。"
                if language == "zh"
                else f" {_poster_text(language, 'source')}: {data.data_source}."
            )
    else:
        title = first_title
        subtitle = _poster_text(language, "dashboard_subtitle")
        content = _generic_body(fallback_html)

    poster_branding = branding or ShareImageBranding()

    return f"""<!DOCTYPE html>
<html lang="{'en' if language == 'en' else 'ko' if language == 'ko' else 'zh-CN'}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=1080, initial-scale=1">
  <title>{_escape(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; width: 1080px; background: #eef4fd; }}
    body {{ color: #081b40; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Microsoft YaHei", Arial, sans-serif; font-size: 22px; line-height: 1.5; -webkit-font-smoothing: antialiased; }}
    .poster {{ width: 1080px; padding: 38px 34px 24px; border: 1px solid #aebdd4; border-radius: 28px; background: radial-gradient(circle at 92% 6%, rgba(48,123,255,.15), transparent 260px), linear-gradient(180deg,#fff 0%,#fbfdff 78%,#eef5ff 100%); }}
    .poster-header {{ display: table; width: 100%; margin-bottom: 28px; }}
    .brand, .meta {{ display: table-cell; vertical-align: middle; }}
    .brand {{ font-size: 26px; font-weight: 650; }} .brand strong {{ margin: 0 14px 0 13px; font-size: 43px; letter-spacing: -2px; }} .brand em {{ color: #8b9bb3; font-style: normal; }}
    .brand-mark {{ display: inline-block; width: 39px; height: 40px; vertical-align: middle; white-space: nowrap; }} .brand-mark i {{ display:inline-block; width:8px; margin-right:4px; border-radius:5px 5px 2px 2px; vertical-align:bottom; }} .brand-mark i:nth-child(1){{height:18px;background:#ff3b30}} .brand-mark i:nth-child(2){{height:28px;background:#00a86b}} .brand-mark i:nth-child(3){{height:40px;margin:0;background:#1677ff}}
    .meta {{ text-align:right; color:#3e506c; font-size:21px; }} .date-chip {{ display:inline-block; padding:10px 17px; border:1px solid #aec4e7; border-radius:16px; background:rgba(255,255,255,.85); }}
    .hero {{ min-height: 145px; margin-bottom: 24px; padding: 10px 10px 20px; }} .hero h1 {{ margin:0 0 8px; max-width:820px; font-size:68px; line-height:1.15; letter-spacing:-3px; }} .hero .code {{ margin-left:18px; color:#1768e8; font-size:38px; letter-spacing:0; white-space:nowrap; }} .hero p {{ margin:0; max-width:810px; color:#3c4f70; font-size:24px; }}
    .signal-row {{ display:table; width:100%; margin:0 0 26px; border-spacing:14px 0; table-layout:fixed; }} .signal-row>div {{ display:table-cell; height:88px; padding:14px 20px; border:1px solid #cad8ec; border-radius:16px; vertical-align:middle; background:rgba(255,255,255,.92); }} .signal-row .action-chip {{ width:24%; color:#fff; text-align:center; font-size:38px; font-weight:850; background:#1974ed; box-shadow:0 10px 24px rgba(25,116,237,.22); }} .signal-row .action-chip.positive{{background:linear-gradient(135deg,#118a55,#19b66f)}} .signal-row .action-chip.negative{{background:linear-gradient(135deg,#e63b45,#ff5a52)}} .signal-score span,.signal-trend span{{margin-right:14px;font-weight:750}} .signal-score strong{{color:#0da15d;font-size:41px}} .signal-score.warning strong{{color:#f59e0b}} .signal-score.negative strong{{color:#ed343d}} .signal-score small{{color:#53627b;font-size:20px}} .signal-trend strong{{color:#1768e8;font-size:30px}} .signal-trend>small{{display:block;margin-top:3px;color:#64748b;font-size:15px}} .signal-trend.positive strong{{color:#0a9c58}} .signal-trend.negative strong{{color:#ed343d}}
    .poster-section {{ margin:0 10px 25px; }} .poster-section h2 {{ margin:0 0 12px; font-size:29px; line-height:1.3; }} .poster-section h2 b {{ display:inline-block; width:34px; color:#176ff2; font-family:Arial,sans-serif; }}
    .conclusion {{ padding:16px 24px; border:1.5px solid #72a8ff; border-radius:14px; color:#13294e; background:linear-gradient(90deg,#f9fcff,#eff6ff); font-size:25px; font-weight:600; }}
    .metric-grid {{ display:table; width:100%; border-spacing:12px 0; table-layout:fixed; }} .metric {{ display:table-cell; height:112px; padding:14px 12px; border:1px solid #d0dced; border-radius:16px; text-align:center; vertical-align:middle; background:rgba(255,255,255,.92); }} .metric span {{ display:block; margin-bottom:5px; color:#233653; font-weight:700; }} .metric strong {{ display:block; color:#10254b; font-size:31px; line-height:1.25; overflow-wrap:break-word; word-break:normal; }} .metric.primary strong{{color:#1768e8}} .metric.up strong,.metric.positive strong,.metric.buy strong,.metric.green strong{{color:#0a9c58}} .metric.down strong,.metric.negative strong,.metric.stop strong,.metric.red strong{{color:#ed343d}} .metric.hot strong{{color:#ff4a36}} .metric.secondary strong{{color:#1768e8}} .metric.target strong{{color:#ff8a00}} .sniper-grid .metric{{height:112px}} .sniper-grid .metric strong{{font-size:29px}} .technical-grid .metric strong{{font-size:26px}}
    .watch-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 12px}} .watch-card{{min-height:78px;padding:12px 16px;border:1px solid #d2deef;border-left:4px solid #1768e8;border-radius:13px;background:linear-gradient(145deg,#f7faff,#fff)}} .watch-card.warning{{border-left-color:#f59e0b}} .watch-card.secondary{{border-left-color:#6d5dfc}} .watch-card span{{display:block;color:#52647f;font-size:16px;font-weight:750}} .watch-card p{{margin:4px 0 0;color:#152a4d;font-size:18px;font-weight:650;line-height:1.35}} .two-column {{ display:table; width:100%; border-spacing:12px 0; table-layout:fixed; }} .insight {{ display:table-cell; width:50%; padding:15px 20px; border:1px solid #d5e1f0; border-radius:15px; background:#fff; vertical-align:top; }} .insight.positive{{background:linear-gradient(145deg,#f1fff7,#fff)}} .insight.negative{{background:linear-gradient(145deg,#fff4f4,#fff)}} .insight h3{{margin:0 0 6px;color:#0a9c58;font-size:23px}} .insight.negative h3{{color:#ed343d}} .insight ul{{font-size:19px}} ul{{margin:4px 0;padding-left:25px}} li{{margin:5px 0}}
    .position-box {{ overflow:hidden; border:1px solid #d5e1f0; border-radius:15px; background:#fff; }} .position-row {{ display:table; width:100%; padding:10px 18px; border-bottom:1px solid #e5ecf5; }} .position-row:last-child{{border:0}} .position-row .pill,.position-row p{{display:table-cell;vertical-align:middle}} .position-row .pill{{width:92px;padding:5px 10px;border-radius:8px;color:#fff;text-align:center;font-size:18px;font-weight:750;background:#357dea}} .position-row .pill.warning{{background:#f2a20c}} .position-row .pill.positive{{background:#13a365}} .position-row .pill.negative{{background:#eb3e47}} .position-row p{{margin:0;padding-left:16px}}
    .market-signal {{ display:table; width:calc(100% - 20px); min-height:154px; margin:0 10px 24px; padding:20px 27px; border:1px solid #bfd4f4; border-radius:22px; background:linear-gradient(135deg,#fff 0%,#f1f7ff 58%,#ecfff6 100%); box-shadow:0 12px 34px rgba(18,71,153,.08); table-layout:fixed; }} .signal-main,.market-label,.signal-guidance{{display:table-cell;vertical-align:middle}} .signal-main{{width:25%}} .market-signal span{{display:block;font-weight:750}} .market-signal strong{{color:#1768e8;font-size:74px;line-height:1.05}} .market-signal small{{font-size:30px}} .market-label{{width:19%;padding:9px 12px;border:1px solid #23ad69;border-radius:10px;color:#0d9958;text-align:center;font-size:23px;font-weight:800;background:#f1fff7}} .signal-guidance{{width:56%;padding-left:28px;color:#233653}} .signal-guidance span{{color:#1768e8;font-size:18px;letter-spacing:1px}} .signal-guidance p{{margin:6px 0 0;font-size:23px;font-weight:700;line-height:1.45}}
    .index-grid {{ display:table; width:100%; margin:0 0 24px; border-spacing:10px 0; table-layout:fixed; }} .index-card{{display:table-cell;padding:16px 18px;border:1px solid #d0dced;border-radius:18px;background:linear-gradient(160deg,#fff,#f6f9ff);box-shadow:0 8px 22px rgba(25,78,153,.05)}} .index-card span,.index-card small{{display:block}} .index-card span{{font-weight:750}} .index-card strong{{display:block;margin:8px 0 0;font-size:35px}} .index-card strong.red{{color:#ed3f36}} .index-card strong.green{{color:#0a9c58}} .index-card small{{color:#3d506f;font-size:19px}}
    .breadth-grid .metric{{background:linear-gradient(160deg,#fff,#f7faff)}} .breadth-grid .metric strong{{font-size:29px}} .dimension-grid .metric{{height:94px;background:linear-gradient(145deg,#f7faff,#fff)}} .dimension-grid .metric strong{{font-size:33px}} .market-two-column{{display:table;width:calc(100% - 20px);margin:0 10px 24px;border-spacing:8px 0;table-layout:fixed}} .market-left,.market-right{{display:table-cell;width:50%;vertical-align:top}} .market-two-column .poster-section{{min-height:238px;margin:0;padding:20px 22px;border:1px solid #d3dfef;border-radius:19px;background:linear-gradient(160deg,#fff,#f8fbff)}} .ranking-row{{display:table;width:100%;padding:13px 0;border-bottom:1px solid #e6edf6}} .ranking-row:last-child{{border:0}} .ranking-row>*{{display:table-cell;vertical-align:middle}} .ranking-row b{{width:44px;color:#fff;border-radius:9px;text-align:center;background:linear-gradient(135deg,#1677ff,#6a5cff)}} .ranking-row:nth-child(2) b{{background:linear-gradient(135deg,#ff8a00,#ffb020)}} .ranking-row:nth-child(3) b{{background:linear-gradient(135deg,#12a66a,#37c98a)}} .ranking-row span{{padding-left:13px;font-weight:700}} .ranking-row strong{{text-align:right}} .ranking-row strong.red{{color:#ed3f36}} .ranking-row strong.green{{color:#0a9c58}} .ranking-row.lagging b{{background:linear-gradient(135deg,#64748b,#94a3b8)}} .market-details .poster-section{{min-height:214px}} .focus-row,.fund-row{{display:table;width:100%;padding:10px 0;border-bottom:1px solid #e6edf6}} .focus-row:last-child,.fund-row:last-child{{border:0}} .focus-row b,.focus-row span,.fund-row span,.fund-row strong{{display:table-cell;vertical-align:middle}} .focus-row b{{width:66px;color:#fff;border-radius:8px;text-align:center;background:#1677ff}} .focus-row.avoid b{{background:#ef4444}} .focus-row span{{padding-left:14px;font-weight:700}} .fund-row span{{color:#52647f}} .fund-row strong{{text-align:right;color:#1768e8}} .fund-row.positive strong{{color:#0a9c58}} .fund-row.warning strong{{color:#f59e0b}} .strategy-strip{{padding:16px 22px;border:1px solid #cbdcf4;border-radius:17px;background:linear-gradient(90deg,#f6faff,#fff)}} .strategy-strip ul{{display:table;width:100%;padding-left:25px}} .strategy-strip li{{display:table-cell;width:33.33%;padding-right:20px;font-size:19px;vertical-align:top}}
    .risk-strip{{padding:16px 22px;border:1px solid #ffc5c5;border-radius:17px;background:linear-gradient(90deg,#fff3f3,#fffafa)}} .risk-strip h2{{color:#e7373f}} .risk-strip ul{{display:table;width:100%;padding-left:25px}} .risk-strip li{{display:table-cell;width:50%;padding-right:24px;font-size:19px}}
    .report-fallback {{ margin:0 10px 26px; padding:24px 28px; border:1px solid #d5e1f0; border-radius:18px; background:#fff; }} .report-content h1,.report-content h2,.report-content h3{{color:#153d78}} .report-content h2{{font-size:29px}} .report-content h3{{font-size:25px}} .report-content table{{width:100%;border-collapse:collapse;font-size:19px}} .report-content th,.report-content td{{padding:10px;border:1px solid #dbe4f1}} .report-content th{{background:#eef4fc}} .report-content blockquote{{margin:15px 0;padding:12px 18px;border-left:5px solid #4385ef;background:#f3f7fd}}
    .poster-footer {{ display:table; width:100%; margin-top:18px; padding:14px 34px 5px; border-top:1px solid #ccdaec; table-layout:fixed; }} .footer-brand,.qr-card{{display:table-cell;vertical-align:middle}} .footer-brand{{width:74%;padding-left:6px}} .footer-brand.full{{width:100%}} .footer-title{{display:flex;align-items:baseline;gap:15px}} .footer-title strong{{color:#1768e8;font-size:43px;font-style:italic;line-height:1}} .footer-title span{{font-size:24px;font-weight:800}} .footer-brand>small{{display:block;margin-top:4px;color:#536683;font-size:16px}} .repo-line{{display:flex;align-items:center;gap:9px;margin-top:11px;color:#111827}} .repo-line svg{{width:25px;height:25px;flex:none;fill:currentColor}} .repo-line div{{min-width:0}} .repo-line em,.repo-line b{{display:block;font-style:normal}} .repo-line em{{margin-bottom:1px;color:#64748b;font-size:12px;letter-spacing:.6px}} .repo-line b{{font-size:16px;line-height:1.15;white-space:nowrap}} .qr-card{{width:26%;text-align:center;font-size:16px;font-weight:750;line-height:1.2}} .qr-card.text-only{{padding-left:18px}} .qr-card .social-link{{color:inherit;text-decoration:none}} .qr-card span b{{color:#ff2442}} .qr-frame{{width:132px;height:132px;margin:0 auto 5px;padding:4px;border:1px solid #d3deed;border-radius:13px;background:#fff}} .qr-frame img{{display:block;width:122px;height:122px;object-fit:contain}} .disclaimer{{margin:6px -34px -24px;padding:8px 34px;color:#285b9d;font-size:14px;text-align:center;background:#eaf3ff}}
  </style>
</head>
<body>
  <main class="poster {report_kind}">
    <header class="poster-header"><div class="brand"><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span><strong>DSA</strong><em>|</em> {_escape(_poster_text(language, "brand"))}</div><div class="meta"><span class="date-chip">{_escape(stamp)}</span></div></header>
    <section class="hero"><h1>{_escape(title)}{f'<span class="code">{_escape(data.code)}</span>' if report_kind == 'stock' and data.code else ''}</h1><p>{_escape(subtitle)}</p></section>
    {content}
    {_footer(poster_branding, source_line, language)}
  </main>
</body>
</html>"""
