# -*- coding: utf-8 -*-
"""Market review prompt builders.

Issue #1085 step 2 extracts prompt assembly only. Metric scoring, markdown
injectors, LLM calls, and degradation policy remain in ``src.market.analyzer``.
These helpers take explicit primitives or preformatted strings and must not
import ``MarketAnalyzer``.
"""

from __future__ import annotations

from typing import List


def get_strategy_prompt_block(
    region: str,
    review_language: str,
    default_strategy_block: str,
) -> str:
    """Return the region/language strategy blueprint injected into the LLM prompt."""
    if region == "hk" and review_language == "en":
        return """## Strategy Blueprint: Hong Kong Market Regime Strategy
Focus on HSI trend, southbound flow dynamics, and sector rotation to define next-session risk posture.

### Strategy Principles
- Read market regime from HSI, HSTECH, and HSCEI alignment first.
- Track southbound capital flow as a key sentiment driver.
- Translate recap into actionable risk-on/risk-off stance with clear invalidation points.

### Analysis Dimensions
- Trend Regime: Classify the market as momentum, range, or risk-off.
  - Are HSI/HSTECH/HSCEI directionally aligned
  - Did volume confirm the move
  - Are key index levels reclaimed or lost
- Capital Flows: Map southbound flow and macro narrative into equity risk appetite.
  - Southbound net flow direction and magnitude
  - USD/HKD and China policy implications
  - Breadth and leadership concentration
- Sector Themes: Identify persistent leaders and vulnerable laggards.
  - Tech/internet platform trend persistence
  - Financials/property sensitivity to policy shifts
  - Defensive vs growth factor rotation

### Action Framework
- Risk-on: broad index breakout with expanding southbound participation.
- Neutral: mixed index signals; focus on selective relative strength.
- Risk-off: failed breakouts and rising volatility; prioritize capital preservation."""
    if region == "jp" and review_language == "en":
        return """## Strategy Blueprint: Japan Market Regime Strategy
Focus on Nikkei 225, TOPIX, currency dynamics, and global risk appetite to define the next-session trading plan.

### Strategy Principles
- Read Nikkei 225 and TOPIX alignment first, then assess yen moves, semiconductor/export chains, and financials.
- Translate index conclusions into position sizing, trading pace, and risk-control actions.
- Base judgments only on available index data, news, and price action without inventing breadth or sector statistics.

### Analysis Dimensions
- Trend Regime: Classify Japan equities as advancing, range-bound, or defensive.
  - Are Nikkei 225 and TOPIX directionally aligned
  - Have key index ranges been reclaimed or lost
  - Are large-cap weights and growth chains moving together
- Macro & FX: Map yen, rates, and global risk appetite into equity impact.
  - Yen direction and implications for exporters
  - Bank of Japan and US Treasury yield narratives
  - Overseas technology and semiconductor read-through
- Theme Signals: Identify durable leadership and crowded areas to avoid.
  - Semiconductor, automation, and auto-chain persistence
  - Rotation between financials and domestic-demand stocks
  - Whether news catalysts confirm price action

### Action Framework
- Risk-on: major indices rise together with improving external risk appetite and stronger leadership.
- Neutral: index divergence or FX disruption; avoid chasing and wait for confirmation.
- Risk-off: major indices weaken or external risk rises; prioritize position control."""
    if region == "kr" and review_language == "en":
        return """## Strategy Blueprint: Korea Market Regime Strategy
Focus on KOSPI, KOSDAQ, semiconductor heavyweights, and global technology risk appetite to define the next-session trading plan.

### Strategy Principles
- Read KOSPI and KOSDAQ alignment first, then assess heavyweight signals from Samsung Electronics, SK Hynix, and related technology leaders.
- Separate broad index beta, semiconductor cycle exposure, and growth-stock risk appetite.
- Base judgments only on available index data, news, and price action without inventing breadth or sector statistics.

### Analysis Dimensions
- Trend Regime: Classify Korea equities as advancing, range-bound, or defensive.
  - Are KOSPI and KOSDAQ directionally aligned
  - Are heavyweight technology names supporting the indices
  - Have key support or resistance levels been reclaimed or lost
- Technology Cycle: Map semiconductor, AI hardware, and global technology moves into Korea equity risk.
  - Memory and semiconductor-chain catalysts
  - US technology-market read-through
  - Foreign investor risk appetite signals
- Theme Signals: Identify durable leadership and crowded areas to avoid.
  - Rotation across batteries, autos, and internet platforms
  - KOSDAQ growth-stock risk appetite
  - Whether news catalysts confirm price action

### Action Framework
- Risk-on: KOSPI and KOSDAQ rise together with confirmed technology leadership and improving external risk appetite.
- Neutral: index or heavyweight divergence; keep sizing controlled and wait for confirmation.
- Risk-off: technology heavyweights weaken or external risk rises; prioritize drawdown control."""
    if region == "us" and review_language == "zh":
        return """## 美股市场三段式复盘策略
聚焦指数趋势、宏观叙事与板块轮动，给出次日风控与仓位框架。

### 策略原则
- 先看标普500、纳斯达克、道琼斯是否同向，确认主线是否一致。
- 结合宏观与流动性指标，识别风险偏好是修复还是转弱。
- 将复盘输出映射为“进攻/均衡/防守”动作建议，并给出明确触发失效条件。

### 分析维度
- 趋势结构：明确市场处于上冲、震荡还是防守转向，判断是否存在关键支撑位背离。
- 资金与情绪：区分宏观政策、货币面与波动率对权益风险的影响。
- 主题线索：识别持续性最强的主题与板块轮动是否形成可交易主线。

### 行动框架
- 进攻：主板块联动上行且量能/风险位同步改善。
- 均衡：指数分化或量能未明显放大，仓位保守执行。
- 防守：突破失守且波动率抬升时，优先减码并保留反弹可交易性。"""
    if not (region == "cn" and review_language == "en"):
        return default_strategy_block
    return """## Strategy Blueprint: A-share Three-Phase Recap Strategy
Focus on index trend, liquidity, and sector rotation to shape the next-session trading plan.

### Strategy Principles
- Read index direction first, then confirm liquidity structure, and finally test sector persistence.
- Every conclusion must map to position sizing, trading pace, and risk-control actions.
- Base judgments on today's data and the latest 3-day news flow without inventing unverified information.

### Analysis Dimensions
- Trend Structure: Determine whether the market is in an uptrend, range, or defensive phase.
  - Are the SSE, SZSE, and ChiNext moving in the same direction
  - Is the market advancing on expanding volume or slipping on contracting volume
  - Have key support or resistance levels been reclaimed or broken
- Liquidity & Sentiment: Identify near-term risk appetite and market temperature.
  - Advance/decline breadth and limit-up/limit-down structure
  - Whether turnover is expanding or fading
  - Whether high-beta leaders are showing divergence
- Leading Themes: Distill tradable leadership and areas to avoid.
  - Whether leading sectors have clear event catalysts
  - Whether sector leaders are pulling the group higher
  - Whether weakness is broadening across lagging sectors

### Action Framework
- Offensive: indices rise in sync, turnover expands, and core themes strengthen.
- Balanced: index divergence or low-volume consolidation; keep sizing controlled and wait for confirmation.
- Defensive: indices weaken and laggards broaden; prioritize risk control and de-risking."""


def build_output_template_sections(
    review_language: str,
    *,
    has_market_stats: bool,
    has_sector_rankings: bool,
) -> str:
    """Build LLM output sections according to market data capabilities."""
    if review_language == "en":
        if has_market_stats and has_sector_rankings:
            return """### 3. Fund Flows
(Interpret what turnover, participation, and flow signals imply.)

### 4. Sector Highlights
(Distinguish industry-sector moves from concept/theme moves, then analyze drivers and persistence.)

### 5. Outlook
(Provide the near-term outlook based on price action and news.)

### 6. Risk Alerts
(List the main risks to monitor.)

### 7. Strategy Plan
(Provide an offensive/balanced/defensive stance, a position-sizing guideline, one invalidation trigger, and end with "For reference only, not investment advice.")"""

        section_number = 3
        sections: List[str] = []
        if has_market_stats:
            sections.append(f"""### {section_number}. Fund Flows
(Interpret only the provided turnover, participation, breadth, and flow signals.)""")
            section_number += 1
        if has_sector_rankings:
            sections.append(f"""### {section_number}. Sector Highlights
(Analyze only the provided industry-sector and concept/theme rankings.)""")
            section_number += 1
        sections.extend([
            f"""### {section_number}. News Catalysts
(Connect recent news to index price action and macro/external-market clues. Do not infer unsupported breadth, fund-flow, or sector-ranking data.)""",
            f"""### {section_number + 1}. Outlook
(Provide the near-term outlook based on index price action and the available news.)""",
            f"""### {section_number + 2}. Risk Alerts
(List the main risks to monitor.)""",
            f"""### {section_number + 3}. Strategy Plan
(Provide an offensive/balanced/defensive stance, a position-sizing guideline, one invalidation trigger, and end with "For reference only, not investment advice.")""",
        ])
        return "\n\n".join(sections)

    if has_market_stats and has_sector_rankings:
        return """### 三、板块主线
（区分行业板块与概念题材，分析领涨/领跌背后的逻辑、持续性和是否形成主线）

### 四、资金与情绪
（解读成交额、涨跌停结构、市场宽度和风险偏好）

### 五、消息催化
（结合近三日新闻，提炼真正影响明日交易的催化或扰动）

### 六、明日交易计划
（给出进攻/均衡/防守结论、仓位区间、关注方向、回避方向和一个触发失效条件）

### 七、风险提示
（列出需要关注的风险点；最后补充“建议仅供参考，不构成投资建议”。）"""

    numerals = ["一", "二", "三", "四", "五", "六", "七", "八"]
    section_number = 3
    sections: List[str] = []

    def add_section(title: str, hint: str) -> None:
        nonlocal section_number
        sections.append(f"### {numerals[section_number - 1]}、{title}\n{hint}")
        section_number += 1

    if has_sector_rankings:
        add_section("板块主线", "（仅分析已提供的行业板块与概念题材榜单，不扩展未提供的数据）")
    if has_market_stats:
        add_section("资金与情绪", "（仅解读已提供的成交额、涨跌停结构、市场宽度和风险偏好数据）")
    add_section(
        "消息催化",
        "（结合近三日新闻和指数表现，提炼真正影响明日交易的催化或扰动；不要推断未提供的资金流、市场宽度或板块榜）",
    )
    add_section("明日交易计划", "（给出进攻/均衡/防守结论、仓位区间、关注方向、回避方向和一个触发失效条件）")
    add_section("风险提示", "（列出需要关注的风险点；最后补充“建议仅供参考，不构成投资建议”。）")
    return "\n\n".join(sections)


def build_review_prompt(
    *,
    review_language: str,
    output_language: str,
    region: str,
    date: str,
    has_market_stats: bool,
    has_sector_rankings: bool,
    indices_text: str,
    news_text: str,
    top_sectors_text: str,
    bottom_sectors_text: str,
    top_concepts_text: str,
    bottom_concepts_text: str,
    sector_analysis_context: str,
    turnover_unit_label: str,
    up_count: int,
    down_count: int,
    flat_count: int,
    limit_up_count: int,
    limit_down_count: int,
    total_amount: float,
    market_scope_name_en: str,
    market_scope_name_zh: str,
    review_title: str,
    index_hint: str,
    strategy_prompt_block: str,
    output_template_sections: str,
) -> str:
    """Assemble the market-review LLM prompt from explicit primitives."""
    # Korean reuses the English structural template but the model is told to
    # write the entire shell, headings, guidance and conclusion in Korean.
    shell_language_label = "Korean (한국어)" if output_language == "ko" else "English"

    stats_block = ""
    sector_block = ""
    data_limits_block = ""
    if review_language == "en":
        if has_market_stats:
            stats_block = f"""## Market Breadth
- Advancers: {up_count} | Decliners: {down_count} | Flat: {flat_count}
- Limit-up: {limit_up_count} | Limit-down: {limit_down_count}
- Turnover: {total_amount:.0f} ({turnover_unit_label})"""

        if has_sector_rankings:
            sector_block = f"""## Sector / Theme Performance
Industry leading: {top_sectors_text if top_sectors_text else "N/A"}
Industry lagging: {bottom_sectors_text if bottom_sectors_text else "N/A"}
Concept leading: {top_concepts_text if top_concepts_text else "N/A"}
Concept lagging: {bottom_concepts_text if bottom_concepts_text else "N/A"}

{sector_analysis_context}"""

        data_limit_lines = []
        if not has_market_stats:
            data_limit_lines.append(
                "- Market breadth, aggregate turnover, participation, and fund-flow signals are not available for this market."
            )
        if has_sector_rankings:
            data_limit_lines.append(
                "- Sector analysis is session-only; namespace-aware sector index codes/levels, "
                "collision-free canonical IDs, ETF mappings, historical series, and sector fund flow are unavailable."
            )
        else:
            data_limit_lines.append("- Sector/theme ranking data is not available for this market.")
        if data_limit_lines:
            data_limits_block = "## Data Limits\n" + "\n".join(data_limit_lines)
    else:
        if has_market_stats:
            stats_block = f"""## 市场概况
- 上涨: {up_count} 家 | 下跌: {down_count} 家 | 平盘: {flat_count} 家
- 涨停: {limit_up_count} 家 | 跌停: {limit_down_count} 家
- 两市成交额: {total_amount:.0f} 亿元"""

        if has_sector_rankings:
            sector_block = f"""## 板块表现
行业领涨: {top_sectors_text if top_sectors_text else "暂无数据"}
行业领跌: {bottom_sectors_text if bottom_sectors_text else "暂无数据"}
概念领涨: {top_concepts_text if top_concepts_text else "暂无数据"}
概念领跌: {bottom_concepts_text if bottom_concepts_text else "暂无数据"}

{sector_analysis_context}"""

        data_limit_lines = []
        if not has_market_stats:
            data_limit_lines.append("- 该市场暂无涨跌家数、涨跌停、成交额汇总、参与度或资金流信号。")
        if has_sector_rankings:
            data_limit_lines.append(
                "- 板块分析仅使用当日排行；板块指数命名空间/代码/点位、无冲突规范 ID、"
                "ETF 映射、历史序列和板块资金流暂不可用。"
            )
        else:
            data_limit_lines.append("- 该市场暂无行业板块/概念题材涨跌榜。")
        if data_limit_lines:
            data_limits_block = "## 数据边界\n" + "\n".join(data_limit_lines)

    data_no_indices_hint = (
        "注意：由于行情数据获取失败，请主要根据【市场新闻】进行定性分析和总结，不要编造具体的指数点位。"
        if not indices_text
        else ""
    )
    if review_language == "en":
        data_no_indices_hint = (
            "Note: Market data fetch failed. Rely mainly on [Market News] for qualitative analysis. Do not invent index levels."
            if not indices_text
            else ""
        )
        indices_placeholder = indices_text if indices_text else "No index data (API error)"
        news_placeholder = news_text if news_text else "No relevant news"
        data_boundary_requirement = (
            "- Respect Data Limits: do not invent or over-interpret unsupported breadth, fund-flow, turnover, participation, or sector-ranking data.\n"
            if data_limits_block
            else ""
        )
        market_summary_hint = (
            "2-3 sentences summarizing overall market tone, index moves, and liquidity."
            if has_market_stats
            else "2-3 sentences summarizing overall market tone, index moves, and available news context."
        )
    else:
        indices_placeholder = indices_text if indices_text else "暂无指数数据（接口异常）"
        news_placeholder = news_text if news_text else "暂无相关新闻"
        data_boundary_requirement = (
            "- 严格遵守数据边界：未提供涨跌家数、资金流、成交额汇总或板块榜时，不要编造或过度解读。\n"
            if data_limits_block
            else ""
        )
        market_summary_hint = (
            "2-3句话概括指数、涨跌家数、成交额和情绪温度，明确“强势/偏暖/震荡/偏弱”判断"
            if has_market_stats
            else "2-3句话概括指数表现、新闻线索和整体风险状态，不要补写未提供的市场宽度或资金流数据"
        )

    zh_report_title = f"{date} 大盘复盘"
    if region in ("jp", "kr"):
        zh_report_title = f"{date} {market_scope_name_zh}大盘复盘"
    workflow_hint = (
        "报告要像交易员盘后工作台：先给结论，再按数据表、主线、催化、计划展开"
        if has_market_stats or has_sector_rankings
        else "报告要像交易员盘后工作台：先给结论，再按指数、新闻催化和计划展开"
    )

    if review_language == "en":
        return f"""You are a professional {market_scope_name_en} analyst. Please produce a concise market recap report based on the data below.

[Requirements]
- Output pure Markdown only
- No JSON
- No code blocks
- Use emoji sparingly in headings (at most one per heading)
- The entire fixed shell, headings, guidance, and conclusion must be in {shell_language_label}
{data_boundary_requirement}

---

# Today's Market Data

## Date
{date}

## Major Indices
{indices_placeholder}

{stats_block}

{sector_block}

{data_limits_block}

## Market News
{news_placeholder}

{data_no_indices_hint}

{strategy_prompt_block}

---

# Output Template (follow this structure)

## {review_title}

### 1. Market Summary
({market_summary_hint})

### 2. Index Commentary
({index_hint})

{output_template_sections}

---

Output the report content directly, no extra commentary.
"""

    return f"""你是一位专业的{market_scope_name_zh}分析师，请根据以下数据生成一份结构化的{market_scope_name_zh}大盘复盘报告。

【重要】输出要求：
- 必须输出纯 Markdown 文本格式
- 禁止输出 JSON 格式
- 禁止输出代码块
- emoji 仅在标题处少量使用（每个标题最多1个）
- {workflow_hint}
- 不要重复列出已由系统注入的表格数据；正文负责解释表格背后的含义
{data_boundary_requirement}

---

# 今日市场数据

## 日期
{date}

## 主要指数
{indices_placeholder}

{stats_block}

{sector_block}

{data_limits_block}

## 市场新闻
{news_placeholder}

{data_no_indices_hint}

{strategy_prompt_block}

---

# 输出格式模板（请严格按此格式输出）

## {zh_report_title}

> 一句话给出今日市场状态、核心矛盾和明日优先观察方向。

### 一、盘面总览
（{market_summary_hint}）

### 二、指数结构
（{index_hint}，说明谁在护盘、谁在拖累，以及关键支撑/压力）

{output_template_sections}

---

请直接输出复盘报告内容，不要输出其他说明文字。
"""
