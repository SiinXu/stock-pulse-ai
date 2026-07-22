"""Sector analysis contracts for the market-review path."""

from copy import deepcopy
from types import SimpleNamespace

from src.core.market_profile import CN_PROFILE, US_PROFILE
from src.core.market_strategy import get_market_strategy_blueprint
from src.market_analyzer import MarketAnalyzer, MarketIndex, MarketOverview


def _make_market_analyzer(*, region: str = "cn", language: str = "zh") -> MarketAnalyzer:
    """Build a network-free MarketAnalyzer for deterministic contract tests."""
    analyzer = MarketAnalyzer.__new__(MarketAnalyzer)
    analyzer.region = region
    analyzer.profile = CN_PROFILE if region == "cn" else US_PROFILE
    analyzer.strategy = get_market_strategy_blueprint(region)
    analyzer.config = SimpleNamespace(
        report_language=language,
        market_review_color_scheme="green_up",
    )
    analyzer.analyzer = None
    return analyzer


def _sector_overview() -> MarketOverview:
    """Return representative broad-index and sector ranking inputs."""
    return MarketOverview(
        date="2026-07-21",
        indices=[
            MarketIndex(code="000001", name="Shanghai Composite", change_pct=0.4),
            MarketIndex(code="399001", name="Shenzhen Component", change_pct=0.8),
        ],
        top_sectors=[
            {"name": "Semiconductors", "change_pct": 2.6},
            {"name": "Software", "change_pct": 1.2},
        ],
        bottom_sectors=[
            {"name": "Coal", "change_pct": -3.1},
            {"name": "Banks", "change_pct": -0.2},
        ],
        top_concepts=[{"name": "Robotics", "change_pct": 4.2}],
        bottom_concepts=[{"name": "Seed Industry", "change_pct": -1.4}],
    )


def test_sector_analysis_derives_session_relative_strength_and_risk() -> None:
    """Rankings should become bounded session analysis without mutating inputs."""
    analyzer = _make_market_analyzer()
    overview = _sector_overview()
    original = deepcopy(overview)

    analysis = analyzer.build_sector_analysis(overview)

    assert analysis["status"] == "partial"
    assert analysis["scope"] == "session_rankings"
    assert analysis["benchmark"] == {
        "status": "available",
        "method": "major_index_average",
        "change_pct": 0.6,
        "sample_size": 2,
    }
    semiconductor = analysis["industries"][0]
    assert semiconductor["session_change_pct"] == 2.6
    assert semiconductor["relative_strength_pct"] == 2.0
    assert semiconductor["session_trend"] == "strong_up"
    assert semiconductor["relative_strength"] == "outperforming"
    assert semiconductor["risk_level"] == "low"

    coal = analysis["industries"][2]
    assert coal["rank_side"] == "laggard"
    assert coal["relative_strength_pct"] == -3.7
    assert coal["session_trend"] == "strong_down"
    assert coal["relative_strength"] == "underperforming"
    assert coal["risk_level"] == "high"
    assert "downside_momentum" in coal["risk_flags"]
    assert analysis["capital_flow"] == {
        "status": "not_available",
        "reason": "provider_contract_unavailable",
    }
    assert overview == original


def test_sector_analysis_keeps_missing_benchmark_and_provider_boundaries_explicit() -> None:
    """Missing indices or unsupported markets must not invent relative evidence."""
    analyzer = _make_market_analyzer()
    overview = MarketOverview(
        date="2026-07-21",
        top_sectors=[{"name": "Semiconductors", "change_pct": 1.5}],
    )

    analysis = analyzer.build_sector_analysis(overview)

    assert analysis["benchmark"]["status"] == "unavailable"
    assert analysis["industries"][0]["relative_strength_pct"] is None
    assert analysis["industries"][0]["relative_strength"] == "unknown"
    assert "benchmark_unavailable" in analysis["industries"][0]["risk_flags"]
    assert "benchmark_change_pct" in analysis["data_quality"]["missing_fields"]

    empty = analyzer.build_sector_analysis(MarketOverview(date="2026-07-21"))
    assert empty["status"] == "unavailable"
    assert "sector_rankings" in empty["data_quality"]["missing_fields"]

    us_analyzer = _make_market_analyzer(region="us", language="en")
    unsupported = us_analyzer.build_sector_analysis(MarketOverview(date="2026-07-21"))
    assert unsupported["status"] == "not_supported"
    assert unsupported["industries"] == []
    assert unsupported["concepts"] == []


def test_market_review_payload_adds_sector_analysis_without_replacing_rankings() -> None:
    """The structured payload should be additive for existing consumers."""
    analyzer = _make_market_analyzer()
    overview = _sector_overview()

    payload = analyzer.build_market_review_payload(
        overview,
        [],
        "## 2026-07-21 大盘复盘\n\n### 三、板块主线\n正文",
        market_light_snapshot={
            "dimensions": {"breadth": {"available": False}},
        },
    )

    assert payload["sectors"]["top"] == overview.top_sectors
    assert payload["concepts"]["bottom"] == overview.bottom_concepts
    assert payload["sector_analysis"]["status"] == "partial"
    assert payload["sector_analysis"]["industries"][0]["name"] == "Semiconductors"


def test_chinese_sector_report_renders_analysis_and_truthful_data_limits() -> None:
    """Chinese reports should show relative strength and unavailable dimensions."""
    analyzer = _make_market_analyzer(language="zh")
    overview = _sector_overview()

    block = analyzer._build_sector_block(overview)
    prompt = analyzer._build_review_prompt(overview, [])

    assert "#### 板块指数分析" in block
    assert "**比较基准**：主要指数平均 +0.60%（2 个指数）" in block
    assert "| 行业 领涨 #1 | Semiconductors | +2.60% / 强势上行 | +2.00% / 跑赢 | 低 |" in block
    assert "板块指数代码/点位、历史序列和板块资金流" in block
    assert "板块分析仅使用当日排行" in prompt
    assert "确定性板块分析输入" in prompt
    assert "#### 板块指数分析" not in prompt


def test_english_template_report_includes_sector_analysis_once() -> None:
    """English no-LLM fallback should carry the same sector analysis contract."""
    analyzer = _make_market_analyzer(language="en")
    overview = _sector_overview()

    report = analyzer._generate_template_review(overview, [])

    assert report.count("#### Sector Index Analysis") == 1
    assert "**Benchmark**: major-index average +0.60% (2 indices)" in report
    assert "| Industry Leader #1 | Semiconductors | +2.60% / Strong up | +2.00% / Outperforming | Low |" in report
    assert "historical series, and sector capital flow are unavailable" in report
