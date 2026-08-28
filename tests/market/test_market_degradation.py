# -*- coding: utf-8 -*-
"""Characterization tests for the extracted no-LLM template renderer (Issue #1085 step 3)."""

from __future__ import annotations

import ast
import inspect
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.core.market_profile import CN_PROFILE, JP_PROFILE, US_PROFILE
from src.core.market_strategy import get_market_strategy_blueprint
from src.llm.generation_backend import GenerationError
from src.market.analyzer import MarketAnalyzer, MarketIndex, MarketOverview
from src.market.degradation import generate_template_review

REPO_ROOT = Path(__file__).resolve().parents[2]
DEGRADATION_PATH = REPO_ROOT / "src" / "market" / "degradation.py"
ANALYZER_PATH = REPO_ROOT / "src" / "market" / "analyzer.py"

CN_EN_GOLDEN = "## 2026-03-18 A-share Market Recap\n\n### 1. Market Summary\nToday's A-share market showed **moderate gains**.\n\n### 2. Major Indices\n- **上证指数**: 3200.12 (↑0.64%)\n- **深证成指**: 9800.40 (↓0.21%)\n- **创业板指**: 2100.00 (↑1.25%)\n- **科创50**: 980.00 (↓1.10%)\n\n\n### 3. Breadth & Liquidity\n| Metric | Value |\n|--------|-------|\n| Advancers | 1200 |\n| Decliners | 900 |\n| Limit-up | 12 |\n| Limit-down | 4 |\n| Turnover (CNY 100m) | 12345 |\n\n\n### 4. Sector / Theme Highlights\n- **Industry Leaders**: 半导体\n- **Industry Laggards**: 煤炭\n- **Concept Leaders**: 机器人概念\n- **Concept Laggards**: 转基因\n\n#### Sector Index Analysis\n> Scope: current-session industry/concept rankings versus the average move of available major indices. This is not a multi-session trend or fund-flow measure.\n- **Benchmark**: major-index average +0.13% (5 indices)\n\n| Group / Rank | Sector / Theme | Session Trend | Relative Strength | Risk |\n|--------------|----------------|---------------|-------------------|------|\n| Industry Leader #1 | 半导体 | +2.35% / Strong up | +2.22% / Outperforming | Low |\n| Industry Laggard #1 | 煤炭 | -1.10% / Down | -1.23% / Underperforming | Moderate |\n| Concept Leader #1 | 机器人概念 | +4.20% / Strong up | +4.07% / Outperforming | Moderate |\n| Concept Laggard #1 | 转基因 | -2.05% / Strong down | -2.18% / Underperforming | High |\n\n- **Data limits**: namespace-aware sector index codes/levels, collision-free canonical IDs, ETF mappings, historical series, and sector capital flow are unavailable from the current public provider contract.\n\n### 5. Risk Alerts\nMarket conditions can change quickly. The data above is for reference only and does not constitute investment advice.\n\n### 6. Strategy Framework\n- **Trend Structure**: Determine whether the market is in an uptrend, range, or defensive phase.\n- **Liquidity & Sentiment**: Track breadth, turnover expansion, and whether leaders are diverging.\n- **Leading Themes**: Focus on sectors with catalysts and sustained leadership while avoiding broadening weakness.\n\n\n---\n*Review Time: 14:05*\n"

CN_ZH_GOLDEN = '## 2026-03-18 大盘复盘\n\n> 今日A股市场整体呈现**小幅上涨**态势，优先观察指数承接、成交额变化和板块持续性。\n\n### 一、盘面总览\n- **盘面信号**：58/100（偏暖，需观察）\n- **信号依据**：上涨家数占比 57%，市场分化；主要指数平均涨跌幅 +0.13%；涨跌停差 +8\n- **操作建议**：信号分化，控制仓位并等待量价确认。\n\n| 指标 | 数值 | 观察 |\n|------|------|------|\n| 上涨/下跌/平盘 | 1200 / 900 / 60 | 上涨占比(不含平盘) 57.1% |\n| 涨停/跌停 | 12 / 4 | 涨跌停差 +8 |\n| 两市成交额 | 12345 亿 | 中等活跃 |\n\n### 二、指数结构\n| 指数 | 最新 | 涨跌幅 | 开盘 | 最高 | 最低 | 振幅 | 成交额(亿) |\n|------|------|--------|------|------|------|------|-----------|\n| 上证指数 | 3200.12 | 🟢 +0.64% | N/A | N/A | N/A | N/A | N/A |\n| 深证成指 | 9800.40 | 🔴 -0.21% | N/A | N/A | N/A | N/A | N/A |\n| 创业板指 | 2100.00 | 🟢 +1.25% | N/A | N/A | N/A | N/A | N/A |\n| 科创50 | 980.00 | 🔴 -1.10% | N/A | N/A | N/A | N/A | N/A |\n| 北证50 | 1200.00 | 🟢 +0.05% | N/A | N/A | N/A | N/A | N/A |\n\n### 三、板块主线\n#### 行业板块领涨 Top 5\n| 排名 | 行业板块 | 涨跌幅 |\n|------|------|--------|\n| 1 | 半导体 | +2.35% |\n\n#### 行业板块领跌 Top 5\n| 排名 | 行业板块 | 涨跌幅 |\n|------|------|--------|\n| 1 | 煤炭 | -1.10% |\n\n#### 概念板块领涨 Top 5\n| 排名 | 概念板块 | 涨跌幅 |\n|------|------|--------|\n| 1 | 机器人概念 | +4.20% |\n\n#### 概念板块领跌 Top 5\n| 排名 | 概念板块 | 涨跌幅 |\n|------|------|--------|\n| 1 | 转基因 | -2.05% |\n\n#### 板块指数分析\n> 口径：仅比较当日行业/概念涨跌榜与可用主要指数平均涨跌幅，不代表多日趋势或真实资金流。\n- **比较基准**：主要指数平均 +0.13%（5 个指数）\n\n| 类型/排名 | 板块/题材 | 当日趋势 | 相对强弱 | 风险 |\n|-----------|-----------|----------|----------|------|\n| 行业 领涨 #1 | 半导体 | +2.35% / 强势上行 | +2.22% / 跑赢 | 低 |\n| 行业 领跌 #1 | 煤炭 | -1.10% / 下行 | -1.23% / 跑输 | 中 |\n| 概念 领涨 #1 | 机器人概念 | +4.20% / 强势上行 | +4.07% / 跑赢 | 中 |\n| 概念 领跌 #1 | 转基因 | -2.05% / 明显下行 | -2.18% / 跑输 | 高 |\n\n- **数据限制**：当前公共 provider 合同不提供板块指数命名空间/代码/点位、无冲突规范 ID、ETF 映射、历史序列和板块资金流，不据此推断。\n\n\n### 四、资金与情绪\n- 结合成交额和涨跌家数看，当前更适合等待确认，避免仅凭单一热点追高。\n\n\n### 五、消息催化\n- 暂无可用新闻时，应降低对题材持续性的确定性判断。\n\n### 六、策略框架\n- **趋势结构**: 判断市场处于上升、震荡还是防守阶段。\n- **资金情绪**: 识别短线风险偏好与情绪温度。\n- **主线板块**: 提炼可交易主线与规避方向。\n\n\n### 七、风险提示\n- 市场有风险，投资需谨慎。以上数据仅供参考，不构成投资建议。\n\n---\n*复盘时间: 14:05*\n'

US_ZH_GOLDEN = '## 2026-03-18 大盘复盘\n\n> 今日美股市场整体呈现**小幅下跌**态势，优先观察指数承接、消息催化和整体风险状态。\n\n### 一、盘面总览\n- 当前以主要指数与可用新闻线索评估整体风险状态。\n\n### 二、指数结构\n| 指数 | 最新 | 涨跌幅 | 开盘 | 最高 | 最低 | 振幅 | 成交额(亿) |\n|------|------|--------|------|------|------|------|-----------|\n| S&P 500 | 5200.00 | 🔴 -0.35% | N/A | N/A | N/A | N/A | N/A |\n\n\n\n### 五、消息催化\n- 暂无可用新闻时，应降低对题材持续性的确定性判断。\n\n### 六、策略框架\n- **趋势结构**：判断市场在进攻、震荡与防守中的状态是否一致。\n- **资金与情绪**：结合波动率、宽度和主题轮动评估风险偏好。\n- **主题主线**：识别可延续和可放大的行业主线与防守线索。\n\n\n### 七、风险提示\n- 市场有风险，投资需谨慎。以上数据仅供参考，不构成投资建议。\n\n---\n*复盘时间: 14:05*\n'

JP_EN_GOLDEN = "## 2026-03-18 Japan Market Recap\n\n### 1. Market Summary\nToday's Japan market showed **moderate gains**.\n\n### 2. Major Indices\n- **Nikkei 225**: 39000.00 (↑0.31%)\n\n\n\n### 5. Risk Alerts\nMarket conditions can change quickly. The data above is for reference only and does not constitute investment advice.\n\n### 6. Strategy Framework\n- **Trend Regime**: Classify Japan equities as advancing, range-bound, or defensive based on Nikkei 225/TOPIX alignment.\n- **Macro & FX**: Track yen, rates, and global risk appetite for exporter and financial-sector implications.\n- **Theme Signals**: Focus on semiconductor, automation, auto-chain, financial, and domestic-demand rotation.\n\n\n---\n*Review Time: 14:05*\n"


class FrozenDateTime:
    """Analyzer-module datetime stand-in for a fixed review clock."""

    @staticmethod
    def now() -> datetime:
        return datetime(2026, 3, 18, 14, 5)


def _make_analyzer(*, region: str = "cn", report_language: str = "zh") -> MarketAnalyzer:
    analyzer = MarketAnalyzer.__new__(MarketAnalyzer)
    analyzer.region = region
    analyzer.profile = {
        "cn": CN_PROFILE,
        "us": US_PROFILE,
        "jp": JP_PROFILE,
    }[region]
    analyzer.config = SimpleNamespace(
        report_language=report_language,
        market_review_color_scheme="green_up",
        generation_backend="litellm",
        generation_fallback_backend="litellm",
        litellm_model="gemini/gemini-2.0-flash",
    )
    analyzer.strategy = get_market_strategy_blueprint(region)
    analyzer.analyzer = None
    return analyzer


def _cn_overview() -> MarketOverview:
    return MarketOverview(
        date="2026-03-18",
        indices=[
            MarketIndex(code="sh000001", name="上证指数", current=3200.12, change_pct=0.64),
            MarketIndex(code="399001", name="深证成指", current=9800.40, change_pct=-0.21),
            MarketIndex(code="399006", name="创业板指", current=2100.00, change_pct=1.25),
            MarketIndex(code="000688", name="科创50", current=980.00, change_pct=-1.10),
            MarketIndex(code="899050", name="北证50", current=1200.00, change_pct=0.05),
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


def _us_overview() -> MarketOverview:
    return MarketOverview(
        date="2026-03-18",
        indices=[MarketIndex(code="SPX", name="S&P 500", current=5200.0, change_pct=-0.35)],
    )


def _jp_overview() -> MarketOverview:
    return MarketOverview(
        date="2026-03-18",
        indices=[MarketIndex(code="N225", name="Nikkei 225", current=39000.0, change_pct=0.31)],
    )


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


def _source_function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "MarketAnalyzer":
            names.update(
                child.name
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return names


def _make_generation_analyzer(return_value="复盘报告") -> MarketAnalyzer:
    with patch("src.analyzer.get_config") as mock_cfg, patch("src.market.analyzer.get_config") as mock_cfg2:
        cfg = MagicMock()
        cfg.litellm_model = "gemini/gemini-2.0-flash"
        cfg.litellm_fallback_models = []
        cfg.gemini_api_keys = ["sk-gemini-testkey-1234"]
        cfg.anthropic_api_keys = []
        cfg.openai_api_keys = []
        cfg.deepseek_api_keys = []
        cfg.llm_model_list = []
        cfg.openai_base_url = None
        cfg.market_review_region = "cn"
        cfg.market_review_color_scheme = "green_up"
        cfg.report_language = "zh"
        cfg.generation_backend = "litellm"
        cfg.generation_fallback_backend = "litellm"
        mock_cfg.return_value = cfg
        mock_cfg2.return_value = cfg

        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
        analyzer._router = None
        analyzer._litellm_available = True
        analyzer._config_override = cfg
        analyzer.generate_text = MagicMock(return_value=return_value)

        ma = MarketAnalyzer.__new__(MarketAnalyzer)
        ma.analyzer = analyzer
        ma.config = cfg
        ma.profile = CN_PROFILE
        ma.strategy = get_market_strategy_blueprint("cn")
        ma.region = "cn"
        return ma


def test_facade_delegates_through_module_level_seam() -> None:
    import src.market.analyzer as analyzer_mod
    import src.market.degradation as degradation_mod

    assert analyzer_mod.generate_template_review is degradation_mod.generate_template_review

    ma = _make_analyzer(region="cn", report_language="en")
    overview = _cn_overview()
    news = [{"title": "unused"}]
    with patch.object(analyzer_mod, "generate_template_review", return_value="patched-template") as patched:
        assert ma._generate_template_review(overview, news) == "patched-template"
        patched.assert_called_once_with(
            ma,
            overview,
            news,
            datetime_cls=analyzer_mod.datetime,
        )


def test_public_facade_signature_and_module_stay_on_analyzer() -> None:
    params = list(inspect.signature(MarketAnalyzer._generate_template_review).parameters)
    assert params == ["self", "overview", "news"]
    assert MarketAnalyzer._generate_template_review.__module__ == "src.market.analyzer"
    assert generate_template_review.__module__ == "src.market.degradation"
    assert "generate_market_review" in _source_function_names(ANALYZER_PATH)
    assert "_generate_template_review" in _source_function_names(ANALYZER_PATH)
    assert "generate_market_review" not in _source_function_names(DEGRADATION_PATH)


def test_degradation_imports_one_way_and_does_not_import_analyzer() -> None:
    degradation_imports = _imported_modules(DEGRADATION_PATH)
    analyzer_imports = _imported_modules(ANALYZER_PATH)
    tree = ast.parse(DEGRADATION_PATH.read_text(encoding="utf-8"))
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert "src.market.analyzer" not in degradation_imports
    assert "src.market.degradation" in analyzer_imports
    assert "MarketAnalyzer" not in imported_names
    assert not any(name.startswith("src.market.analyzer") for name in degradation_imports)
    assert "datetime" not in imported_names


def test_datetime_patch_on_analyzer_module_reaches_renderer() -> None:
    ma = _make_analyzer(region="cn", report_language="en")
    with patch("src.market.analyzer.datetime", FrozenDateTime):
        report = ma._generate_template_review(_cn_overview(), [])
    assert report == CN_EN_GOLDEN
    assert "*Review Time: 14:05*" in report


def test_representative_golden_byte_parity() -> None:
    news = [{"title": "ignored catalyst", "snippet": "should not appear"}]
    with patch("src.market.analyzer.datetime", FrozenDateTime):
        cn_en = _make_analyzer(region="cn", report_language="en")._generate_template_review(
            _cn_overview(), news
        )
        cn_zh = _make_analyzer(region="cn", report_language="zh")._generate_template_review(
            _cn_overview(), news
        )
        us_zh = _make_analyzer(region="us", report_language="zh")._generate_template_review(
            _us_overview(), news
        )
        jp_en = _make_analyzer(region="jp", report_language="en")._generate_template_review(
            _jp_overview(), []
        )

    assert cn_en == CN_EN_GOLDEN
    assert cn_zh == CN_ZH_GOLDEN
    assert us_zh == US_ZH_GOLDEN
    assert jp_en == JP_EN_GOLDEN
    assert "ignored catalyst" not in cn_en
    assert "ignored catalyst" not in cn_zh
    assert "北证50" not in cn_en
    assert "Turnover (CNY 100m)" in cn_en
    assert "### 6. Strategy Framework" in cn_en
    assert "#### Sector Index Analysis" in cn_en


def test_news_is_accepted_passed_and_behaviorally_unused() -> None:
    ma = _make_analyzer(region="cn", report_language="en")
    overview = _cn_overview()
    news = [{"title": "should-not-render"}]
    with patch("src.market.analyzer.datetime", FrozenDateTime):
        via_facade_empty = ma._generate_template_review(overview, [])
        via_facade_news = ma._generate_template_review(overview, news)
        via_helper = generate_template_review(
            ma, overview, news, datetime_cls=FrozenDateTime
        )
    assert via_facade_empty == via_facade_news == via_helper == CN_EN_GOLDEN
    assert "should-not-render" not in via_facade_news


@pytest.mark.parametrize(
    ("change_pct", "language", "expected"),
    [
        (1.01, "en", "strong gains"),
        (1.0, "en", "moderate gains"),
        (0.01, "en", "moderate gains"),
        (0.0, "en", "mild losses"),
        (-0.99, "en", "mild losses"),
        (-1.0, "en", "clear weakness"),
        (1.01, "zh", "强势上涨"),
        (0.5, "zh", "小幅上涨"),
        (-0.5, "zh", "小幅下跌"),
        (-1.2, "zh", "明显下跌"),
    ],
)
def test_mood_thresholds(change_pct: float, language: str, expected: str) -> None:
    ma = _make_analyzer(region="cn", report_language=language)
    overview = MarketOverview(
        date="2026-03-18",
        indices=[MarketIndex(code="000001", name="上证指数", current=3200.0, change_pct=change_pct)],
    )
    with patch("src.market.analyzer.datetime", FrozenDateTime):
        report = ma._generate_template_review(overview, [])
    assert expected in report
    if change_pct == 0.0:
        assert "(-0.00%)" in report


def test_missing_mood_index_uses_range_label() -> None:
    ma = _make_analyzer(region="cn", report_language="en")
    overview = MarketOverview(
        date="2026-03-18",
        indices=[MarketIndex(code="399001", name="深证成指", current=9800.0, change_pct=2.0)],
    )
    with patch("src.market.analyzer.datetime", FrozenDateTime):
        report = ma._generate_template_review(overview, [])
    assert "range-bound trading" in report
    assert "strong gains" not in report


def test_english_rankings_and_indices_are_truncated() -> None:
    ma = _make_analyzer(region="cn", report_language="en")
    overview = _cn_overview()
    overview.top_sectors = [
        {"name": "半导体", "change_pct": 2.35},
        {"name": "有色", "change_pct": 1.8},
        {"name": "军工", "change_pct": 1.2},
        {"name": "excluded-fourth", "change_pct": 0.9},
    ]
    with patch("src.market.analyzer.datetime", FrozenDateTime):
        report = ma._generate_template_review(overview, [])
    assert "半导体, 有色, 军工" in report
    assert "excluded-fourth" not in report
    assert "北证50" not in report
    assert "科创50" in report


def test_helper_overrides_on_owner_are_honored() -> None:
    ma = _make_analyzer(region="cn", report_language="en")
    overview = _cn_overview()
    with patch.object(ma, "_get_market_mood_text", return_value="OVERRIDE_MOOD"), patch.object(
        ma, "_get_strategy_markdown_block", return_value="### OVERRIDE_STRATEGY\n"
    ), patch.object(
        ma, "_get_turnover_unit_label", return_value="OVERRIDE_UNIT"
    ), patch("src.market.analyzer.datetime", FrozenDateTime):
        report = ma._generate_template_review(overview, [])
    assert "OVERRIDE_MOOD" in report
    assert "### OVERRIDE_STRATEGY" in report
    assert "Turnover (OVERRIDE_UNIT)" in report
    assert "moderate gains" not in report


@pytest.mark.parametrize(
    "branch",
    ("config", "missing_analyzer", "empty_response", "generation_error"),
)
def test_generate_market_review_branch_matrix(branch: str) -> None:
    overview = _cn_overview()
    if branch == "config":
        ma = _make_generation_analyzer(return_value=None)
        ma.analyzer._config_override.generation_backend = "codex"
        with patch.object(
            ma, "_generate_template_review", wraps=ma._generate_template_review
        ) as template_review, patch("src.market.analyzer.record_llm_run"):
            with pytest.raises(GenerationError):
                ma.generate_market_review(overview, [])
        template_review.assert_not_called()
        ma.analyzer.generate_text.assert_not_called()
        return

    if branch == "missing_analyzer":
        ma = _make_generation_analyzer(return_value="should-not-run")
        ma.analyzer = None
        with patch("src.market.analyzer.datetime", FrozenDateTime), patch.object(
            ma, "_generate_template_review", wraps=ma._generate_template_review
        ) as template_review:
            result = ma.generate_market_review(overview, [{"title": "unused"}])
        template_review.assert_called_once()
        assert result == CN_ZH_GOLDEN
        return

    if branch == "empty_response":
        ma = _make_generation_analyzer(return_value="")
        with patch("src.market.analyzer.datetime", FrozenDateTime), patch.object(
            ma, "_generate_template_review", wraps=ma._generate_template_review
        ) as template_review, patch("src.market.analyzer.record_llm_run"):
            result = ma.generate_market_review(overview, [])
        template_review.assert_called_once()
        ma.analyzer.generate_text.assert_called_once()
        assert result == CN_ZH_GOLDEN
        return

    ma = _make_generation_analyzer(return_value=None)
    ma.analyzer.generate_text.side_effect = RuntimeError("generation exploded")
    with patch.object(
        ma, "_generate_template_review", wraps=ma._generate_template_review
    ) as template_review, patch("src.market.analyzer.record_llm_run"):
        with pytest.raises(RuntimeError, match="generation exploded"):
            ma.generate_market_review(overview, [])
    template_review.assert_not_called()
