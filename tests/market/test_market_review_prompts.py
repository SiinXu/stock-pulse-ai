# -*- coding: utf-8 -*-
"""Characterization tests for extracted market-review prompt builders (Issue #1085 step 2)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.core.market_profile import CN_PROFILE, HK_PROFILE, KR_PROFILE, US_PROFILE
from src.core.market_strategy import get_market_strategy_blueprint
from src.market.analyzer import MarketAnalyzer, MarketIndex, MarketOverview
from src.market.prompts import (
    build_output_template_sections,
    build_review_prompt,
    get_strategy_prompt_block,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_PATH = REPO_ROOT / "src" / "market" / "prompts.py"
ANALYZER_PATH = REPO_ROOT / "src" / "market" / "analyzer.py"

ZH_FULL_SECTIONS = """### 三、板块主线
（区分行业板块与概念题材，分析领涨/领跌背后的逻辑、持续性和是否形成主线）

### 四、资金与情绪
（解读成交额、涨跌停结构、市场宽度和风险偏好）

### 五、消息催化
（结合近三日新闻，提炼真正影响明日交易的催化或扰动）

### 六、明日交易计划
（给出进攻/均衡/防守结论、仓位区间、关注方向、回避方向和一个触发失效条件）

### 七、风险提示
（列出需要关注的风险点；最后补充“建议仅供参考，不构成投资建议”。）"""

EN_FULL_SECTIONS = """### 3. Fund Flows
(Interpret what turnover, participation, and flow signals imply.)

### 4. Sector Highlights
(Distinguish industry-sector moves from concept/theme moves, then analyze drivers and persistence.)

### 5. Outlook
(Provide the near-term outlook based on price action and news.)

### 6. Risk Alerts
(List the main risks to monitor.)

### 7. Strategy Plan
(Provide an offensive/balanced/defensive stance, a position-sizing guideline, one invalidation trigger, and end with "For reference only, not investment advice.")"""


def _make_analyzer(*, region: str = "cn", report_language: str = "zh") -> MarketAnalyzer:
    analyzer = MarketAnalyzer.__new__(MarketAnalyzer)
    analyzer.region = region
    analyzer.profile = {
        "cn": CN_PROFILE,
        "us": US_PROFILE,
        "hk": HK_PROFILE,
        "kr": KR_PROFILE,
    }[region]
    analyzer.config = SimpleNamespace(report_language=report_language)
    analyzer.strategy = get_market_strategy_blueprint(region)
    return analyzer


def _cn_overview() -> MarketOverview:
    return MarketOverview(
        date="2026-03-18",
        indices=[
            MarketIndex(code="000001", name="上证指数", current=3200.12, change_pct=0.64),
            MarketIndex(code="399001", name="深证成指", current=9800.40, change_pct=-0.21),
        ],
        up_count=1200,
        down_count=900,
        flat_count=60,
        limit_up_count=12,
        limit_down_count=4,
        total_amount=12345.0,
        top_sectors=[{"name": "半导体", "change_pct": 2.35}],
        bottom_sectors=[{"name": "煤炭", "change_pct": -1.1}],
        top_concepts=[{"name": "机器人概念", "change_pct": 4.2}],
        bottom_concepts=[{"name": "转基因", "change_pct": -2.05}],
    )


def test_zh_full_sections_are_byte_stable() -> None:
    sections = build_output_template_sections(
        "zh",
        has_market_stats=True,
        has_sector_rankings=True,
    )
    assert sections == ZH_FULL_SECTIONS

    ma = _make_analyzer(region="cn", report_language="zh")
    assert ma._build_output_template_sections("zh") == ZH_FULL_SECTIONS
    prompt = ma._build_review_prompt(_cn_overview(), [])
    assert ZH_FULL_SECTIONS in prompt
    assert "### 一、盘面总览" in prompt
    assert "行业领涨: 半导体(+2.35%)" in prompt
    assert "概念领涨: 机器人概念(+4.20%)" in prompt


def test_en_full_sections_are_byte_stable() -> None:
    sections = build_output_template_sections(
        "en",
        has_market_stats=True,
        has_sector_rankings=True,
    )
    assert sections == EN_FULL_SECTIONS

    ma = _make_analyzer(region="cn", report_language="en")
    assert ma._build_output_template_sections("en") == EN_FULL_SECTIONS
    prompt = ma._build_review_prompt(_cn_overview(), [])
    assert EN_FULL_SECTIONS in prompt
    assert "### 1. Market Summary" in prompt
    assert "A-share Three-Phase Recap Strategy" in prompt
    assert "### 3. News Catalysts" not in prompt


def test_missing_stats_and_rankings_shift_numbering_without_inferred_language() -> None:
    en_none = build_output_template_sections(
        "en",
        has_market_stats=False,
        has_sector_rankings=False,
    )
    assert en_none.startswith("### 3. News Catalysts")
    assert "### 3. Fund Flows" not in en_none
    assert "### 4. Sector Highlights" not in en_none
    assert "### 4. Outlook" in en_none
    assert "### 三、消息催化" not in en_none

    en_stats_only = build_output_template_sections(
        "en",
        has_market_stats=True,
        has_sector_rankings=False,
    )
    assert en_stats_only.startswith("### 3. Fund Flows")
    assert "### 4. News Catalysts" in en_stats_only
    assert "### 4. Sector Highlights" not in en_stats_only

    en_rankings_only = build_output_template_sections(
        "en",
        has_market_stats=False,
        has_sector_rankings=True,
    )
    assert en_rankings_only.startswith("### 3. Sector Highlights")
    assert "### 4. News Catalysts" in en_rankings_only
    assert "### 3. Fund Flows" not in en_rankings_only

    zh_none = build_output_template_sections(
        "zh",
        has_market_stats=False,
        has_sector_rankings=False,
    )
    assert zh_none.startswith("### 三、消息催化")
    assert "### 三、板块主线" not in zh_none
    assert "### 四、资金与情绪" not in zh_none
    assert "### 3. News Catalysts" not in zh_none

    # Language is the explicit argument, not inferred from a market region.
    jp_like_zh = build_output_template_sections(
        "zh",
        has_market_stats=False,
        has_sector_rankings=False,
    )
    jp_like_en = build_output_template_sections(
        "en",
        has_market_stats=False,
        has_sector_rankings=False,
    )
    assert jp_like_zh == zh_none
    assert jp_like_en == en_none

    kr_en = _make_analyzer(region="kr", report_language="en")
    kr_prompt = kr_en._build_review_prompt(MarketOverview(date="2026-02-24"), [])
    assert "### 3. News Catalysts" in kr_prompt
    assert "### 3. Fund Flows" not in kr_prompt
    assert "### 三、消息催化" not in kr_prompt


def test_korean_uses_english_structural_template_and_korean_shell_label() -> None:
    ma = _make_analyzer(region="cn", report_language="ko")
    prompt = ma._build_review_prompt(_cn_overview(), [])

    assert ma._get_review_language() == "en"
    assert ma._get_output_language() == "ko"
    assert "Korean (한국어)" in prompt
    assert "must be in Korean (한국어)" in prompt
    assert "### 1. Market Summary" in prompt
    assert "# Today's Market Data" in prompt
    assert EN_FULL_SECTIONS in prompt
    assert "### 一、盘面总览" not in prompt
    assert "must be in English" not in prompt


def test_hk_english_strategy_blueprint_is_preserved() -> None:
    fallback = "FALLBACK_STRATEGY_BLOCK"
    block = get_strategy_prompt_block("hk", "en", fallback)

    assert "Hong Kong Market Regime Strategy" in block
    assert "southbound" in block
    assert fallback not in block

    ma = _make_analyzer(region="hk", report_language="en")
    assert ma._get_strategy_prompt_block() == block
    prompt = ma._build_review_prompt(MarketOverview(date="2026-02-24"), [])
    assert "Hong Kong Market Regime Strategy" in prompt
    assert "You are a professional Hong Kong market analyst." in prompt
    assert fallback not in prompt


def test_facade_methods_remain_present_with_original_signatures() -> None:
    assert hasattr(MarketAnalyzer, "_get_strategy_prompt_block")
    assert hasattr(MarketAnalyzer, "_build_output_template_sections")
    assert hasattr(MarketAnalyzer, "_build_review_prompt")

    assert list(inspect.signature(MarketAnalyzer._get_strategy_prompt_block).parameters) == ["self"]
    assert list(inspect.signature(MarketAnalyzer._build_output_template_sections).parameters) == [
        "self",
        "review_language",
    ]
    assert list(inspect.signature(MarketAnalyzer._build_review_prompt).parameters) == [
        "self",
        "overview",
        "news",
    ]
    assert MarketAnalyzer._get_strategy_prompt_block.__module__ == "src.market.analyzer"
    assert MarketAnalyzer._build_output_template_sections.__module__ == "src.market.analyzer"
    assert MarketAnalyzer._build_review_prompt.__module__ == "src.market.analyzer"


def test_analyzer_delegates_through_module_level_seams() -> None:
    import src.market.analyzer as analyzer_mod
    import src.market.prompts as prompts_mod

    assert analyzer_mod.get_strategy_prompt_block is prompts_mod.get_strategy_prompt_block
    assert analyzer_mod.build_output_template_sections is prompts_mod.build_output_template_sections
    assert analyzer_mod.build_review_prompt is prompts_mod.build_review_prompt

    ma = _make_analyzer(region="cn", report_language="zh")
    with patch.object(analyzer_mod, "get_strategy_prompt_block", return_value="patched-strategy") as patched:
        assert ma._get_strategy_prompt_block() == "patched-strategy"
        patched.assert_called_once_with(
            "cn",
            "zh",
            default_strategy_block=ma.strategy.to_prompt_block(),
        )

    with patch.object(analyzer_mod, "build_output_template_sections", return_value="patched-sections") as patched:
        assert ma._build_output_template_sections("zh") == "patched-sections"
        patched.assert_called_once_with(
            "zh",
            has_market_stats=True,
            has_sector_rankings=True,
        )


def test_review_prompt_override_still_uses_instance_strategy_and_sections() -> None:
    ma = _make_analyzer(region="cn", report_language="zh")
    overview = _cn_overview()
    with patch.object(ma, "_get_strategy_prompt_block", return_value="INSTANCE_STRATEGY"):
        with patch.object(ma, "_build_output_template_sections", return_value="INSTANCE_SECTIONS"):
            prompt = ma._build_review_prompt(overview, [])
    assert "INSTANCE_STRATEGY" in prompt
    assert "INSTANCE_SECTIONS" in prompt


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
    return names


def test_prompt_builders_import_one_way_and_do_not_import_analyzer() -> None:
    prompt_imports = _imported_modules(PROMPTS_PATH)
    analyzer_imports = _imported_modules(ANALYZER_PATH)
    tree = ast.parse(PROMPTS_PATH.read_text(encoding="utf-8"))
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert "src.market.analyzer" not in prompt_imports
    assert "src.market.prompts" in analyzer_imports
    assert "MarketAnalyzer" not in imported_names
    assert not any(name.startswith("src.market.analyzer") for name in prompt_imports)


def test_cn_default_strategy_policy_and_us_zh_override() -> None:
    cn_zh = get_strategy_prompt_block("cn", "zh", default_strategy_block="CN_DEFAULT")
    assert cn_zh == "CN_DEFAULT"

    cn_en = get_strategy_prompt_block("cn", "en", default_strategy_block="CN_DEFAULT")
    assert "A-share Three-Phase Recap Strategy" in cn_en
    assert cn_en != "CN_DEFAULT"

    us_zh = get_strategy_prompt_block("us", "zh", default_strategy_block="US_DEFAULT")
    assert "美股市场三段式复盘策略" in us_zh
    assert us_zh != "US_DEFAULT"
