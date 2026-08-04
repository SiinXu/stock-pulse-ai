# -*- coding: utf-8 -*-
from datetime import date

import pytest

from src import share_image


def test_asset_resolution_and_data_uri(tmp_path, monkeypatch):
    asset = tmp_path / "poster.txt"
    asset.write_bytes(b"poster")

    assert share_image._asset_path("") is None
    assert share_image._asset_path(str(tmp_path / "missing.png")) is None
    assert share_image._asset_path(str(asset)) == asset
    assert share_image._asset_data_uri(str(asset)) == "data:text/plain;base64,cG9zdGVy"
    assert share_image._asset_data_uri(str(tmp_path / "missing.png")) == ""

    monkeypatch.chdir(tmp_path)
    assert share_image._asset_path("poster.txt") == asset


def test_text_normalization_language_and_labels():
    assert share_image._plain("✅ **[Alpha](https://example.com)** <b>Beta</b>") == "Alpha Beta"
    assert share_image._clean_value("Ideal Entry: 12.30") == "12.30"
    assert share_image._clean_value("N/A") == ""
    assert share_image._clean_value("abcdefgh", limit=5) == "abcd…"
    assert share_image._compact_text("⚠️ first clause；second clause", limit=15) == "first clause"
    assert share_image._compact_text("abcdefghijklmnopqrstuvwxyz", limit=8) == "abcdefg…"

    payload = {"outer": {"inner": {"value": 3}}}
    assert share_image._nested_mapping(payload, "outer", "inner") == {"value": 3}
    assert share_image._nested_mapping(payload, "outer", "missing") == {}
    assert share_image._nested_mapping([], "outer") == {}

    assert share_image._poster_language("ignored", {"report_language": "en-US"}) == "en"
    assert share_image._poster_language("ignored", {"language": "ko_KR"}) == "ko"
    assert share_image._poster_language("ignored", {"language": "zh-TW"}) == "zh"
    assert share_image._poster_language("핵심 결론") == "ko"
    assert share_image._poster_language("Core Conclusion") == "en"
    assert share_image._poster_language("核心结论") == "zh"
    assert share_image._poster_text("unknown", "score") == "评分"
    assert share_image._poster_label("en", "当前/收盘") == "Current/Close"
    assert share_image._poster_label("en", "观察 AAPL") == "Watch AAPL"
    assert share_image._poster_label("ko", "观察 삼성") == "관찰 삼성"


def test_metric_and_compact_list_merges_preserve_fallbacks():
    existing = [("Price", "10", "neutral"), ("Volume", "2x", "neutral")]
    overlay = [("Price", "11", "positive"), ("Ignored", "", "neutral"), ("RSI", "55", "neutral")]

    assert share_image._metric_value(existing, "Missing", "Volume") == "2x"
    assert share_image._metric_value(existing, "Missing") == ""
    assert share_image._merge_metrics(existing, overlay) == [
        ("Price", "11", "positive"),
        ("Volume", "2x", "neutral"),
        ("RSI", "55", "neutral"),
    ]
    assert share_image._merge_compact_list(["fallback", "second"], "invalid", limit_items=1) == ["fallback"]
    assert share_image._merge_compact_list(
        ["Duplicate", "fallback"],
        ["duplicate", "structured", "third"],
        limit_items=3,
    ) == ["duplicate", "structured", "third"]
    assert share_image._market_light_overlay_allowed({"data_quality": "ready"}) is True
    assert share_image._market_light_overlay_allowed({"data_quality": " unavailable "}) is False


def test_index_and_sector_merges_apply_identity_and_tone_rules():
    indices = share_image._merge_index_cards(
        [("CSI 300", "3500", "-1.00%", "old")],
        [
            {"name": "CSI 300", "current": 3600, "change_pct": 1.25},
            {"name": "Hang Seng", "current": 25000, "change_pct": -0.5},
            {"name": "", "current": 1, "change_pct": 1},
            {"name": "No Change", "current": 1},
        ],
        positive_tone="up",
        negative_tone="down",
    )
    assert indices == [
        ("CSI 300", "3600", "+1.25%", "up"),
        ("Hang Seng", "25000", "-0.50%", "down"),
    ]

    sectors = share_image._merge_sector_rankings(
        [("Banks", "+0.10%", "old"), ("Energy", "", "neutral")],
        [
            {"name": "Semiconductors", "change_pct": 2.5},
            {"name": "Energy", "change_pct": -1.5},
            {"name": "Utilities", "change_pct": "flat"},
            {"name": "", "change_pct": 1},
        ],
        positive_tone="up",
        negative_tone="down",
        default_tone="flat",
    )
    assert sectors == [
        ("Semiconductors", "+2.50%", "up"),
        ("Energy", "-1.50%", "down"),
        ("Utilities", "flat%", "flat"),
    ]


@pytest.mark.parametrize(
    ("value", "suffix", "expected"),
    [
        (None, "", ""),
        (True, "", ""),
        (12.30, "x", "12.3x"),
        ("unknown", "", "unknown"),
    ],
)
def test_number_text(value, suffix, expected):
    assert share_image._number_text(value, suffix=suffix) == expected


def test_numeric_and_position_compaction_contracts():
    assert share_image._compact_turnover(12345, "亿元") == "1.23万亿"
    assert share_image._compact_turnover("unknown", "亿") == "unknown亿"
    assert share_image._compact_turnover(12.5, "亿") == "12.5亿"
    assert share_image._signed_percent(None) == ""
    assert share_image._signed_percent(-1.2) == "-1.20%"
    assert share_image._signed_percent("flat") == "flat%"
    assert share_image._signed_percent("1.5%") == "1.5%"
    assert share_image._price_tokens("MA10（55.13）, target 60, change 3%") == ["55.13", "60"]
    assert share_image._compact_sniper_value("ideal_buy", "暂无合适买点") == "等待企稳"
    assert share_image._compact_sniper_value("take_profit", "目标 12.5 和 15") == "12.5–15"
    assert share_image._compact_sniper_value("stop_loss", "严格执行纪律") == "严格执行纪律"
    assert share_image._compact_position("反弹至 12 减仓，跌破 10 止损", holding=True) == "反弹至 12 附近减仓；跌破 10 止损"
    assert share_image._compact_position("等待 10 / 11 附近企稳", holding=False) == "等待 10 / 11 附近企稳"
    assert share_image._compact_position("暂不建仓", holding=False) == "暂不建仓"
    assert share_image._compact_position("", holding=False) == ""


def test_markdown_sections_tables_and_lists_are_parsed_without_inference():
    markdown = """# Report

## Market Snapshot
| Item | Value |
| --- | --- |
| Price | 12.3 |
| Source | Local |

## Risks
- Demand slowdown
- Margin pressure

### Detail
Useful detail.
"""
    sections = share_image._extract_sections(markdown)
    assert sections[0] == ("Report", "", 1)
    assert share_image._section(markdown, "market snapshot").startswith("| Item | Value |")
    assert share_image._section(markdown, "missing") == ""

    tables = share_image._parse_tables(markdown)
    assert len(tables) == 1
    assert share_image._table_map(tables[0]) == {"price": "12.3", "source": "Local"}
    assert share_image._find_table(markdown, "item", "price") == tables[0]
    assert share_image._find_table(markdown, "missing") is None
    assert share_image._mapped_value({"current price": "12.3"}, "price") == "12.3"
    assert share_image._mapped_value({}, "price") == ""
    assert share_image._has_meaningful_section(markdown, "risks") is True
    assert share_image._has_meaningful_section("## Risks\n仅供研究交流，不构成投资建议", "risks") is False
    assert share_image._meaningful_market_subsection_count(markdown) == 1
    assert share_image._section_items("- first\n2. second\nplain", limit=2) == ["first", "second"]
    assert share_image._sentences("First. Second! Third?", limit=2) == ["First. Second!", "Third?"]


def test_labeled_content_dates_and_market_identity_helpers():
    labeled = """**Conclusion**: Hold | **Score**: 60
**Plan**: Wait for confirmation
**Catalysts**:
- Earnings beat
- New product
**Next**: done
"""
    assert share_image._labeled_value(labeled, "Conclusion") == "Hold"
    assert share_image._labeled_line(labeled, "Plan") == "Wait for confirmation"
    assert share_image._list_after_label(labeled, "Catalysts") == ["Earnings beat", "New product"]
    assert share_image._list_after_label(labeled, "Missing") == []
    assert share_image._extract_date("Report 2026-08-03 10:30", date(2026, 8, 4)) == "2026-08-03"
    assert share_image._extract_date("Report", date(2026, 8, 4)) == "2026-08-04"
    assert share_image._market_label("US Market Review") == "美股"
    assert share_image._market_label("unknown") == ""
    assert share_image._market_region_hint("[dsa-market-region]: # ( cn,us )") == "cn,us"
    assert share_image._market_region_hint("none") == ""
    assert share_image._market_label_for_region(" hk ") == "港股"
    assert share_image._market_label_for_region("xx") == ""


def test_stock_heading_and_multi_market_segmentation_contracts():
    assert share_image._stock_heading_entry("贵州茅台 (600519)") == ("贵州茅台", "600519")
    assert share_image._stock_heading_entry("00700.HK 腾讯控股") == ("腾讯控股", "00700.HK")
    assert share_image._stock_heading_entry("No code") is None

    markdown = """# Multi-market Recap
# US Market Review
## Conclusion
Hold.
# Hong Kong Market Review
## Conclusion
Watch.
"""
    assert share_image._stock_headings("# 贵州茅台 (600519)\n## Detail\nText") == [("贵州茅台", "600519")]
    assert share_image._is_market_review_title("US Market Review") is True
    assert share_image._has_market_scope("US Market Review") is True
    segments = share_image._market_segments(markdown)
    assert [segment.title for segment in segments] == ["US Market Review", "Hong Kong Market Review"]
    assert share_image._market_segments("# US Market Review\nOnly one") == []
    assert share_image._market_region_for_segment(segments[0]) == "us"


def test_color_tone_and_small_html_helpers_escape_untrusted_text():
    assert share_image._opposite_color("green") == "red"
    assert share_image._opposite_color("red") == "green"
    assert share_image._opposite_color("neutral") == ""
    assert share_image._marker_color("🟢 +1%") == "green"
    assert share_image._marker_color("🔴 -1%") == "red"
    assert share_image._marker_color("1%") == ""
    assert share_image._positive_color_from_change("🟢", "-1%") == "red"
    assert share_image._positive_color_from_change("", "+1%") == ""
    assert share_image._ranking_change_tone("+1%", positive_tone="up", negative_tone="down", default_tone="flat") == "up"
    assert share_image._ranking_change_tone("-1%", positive_tone="up", negative_tone="down", default_tone="flat") == "down"
    assert share_image._ranking_change_tone("flat", positive_tone="up", negative_tone="down", default_tone="flat") == "flat"
    assert share_image._tone_for_action("Buy") == "positive"
    assert share_image._tone_for_action("Reduce") == "negative"
    assert share_image._tone_for_action("Hold") == "primary"
    assert share_image._tone_for_score("80") == "positive"
    assert share_image._tone_for_score("20") == "negative"
    assert share_image._tone_for_score("50") == "warning"
    assert share_image._tone_for_score("unknown") == "primary"
    assert share_image._tone_for_trend("Bullish") == "positive"
    assert share_image._tone_for_trend("Bearish") == "negative"
    assert share_image._tone_for_trend("Sideways") == "primary"
    assert share_image._stock_positive_tone("600519") == "red"
    assert share_image._stock_positive_tone("AAPL") == "green"

    cards = share_image._metric_cards([("<Price>", "1&2", "positive")], language="en")
    assert "&lt;Price&gt;" in cards and "1&amp;2" in cards
    assert share_image._list_html([], "<none>") == '<p class="muted">&lt;none&gt;</p>'
    assert share_image._list_html(["<risk>"]) == "<ul><li>&lt;risk&gt;</li></ul>"
    assert share_image._section_html("Title", "!", "") == ""
    assert "poster-section wide" in share_image._section_html("Title", "!", "body", "wide")
    assert "&lt;script&gt;" in share_image._render_markdown_fragment("<script>")
    assert "report-fallback" in share_image._generic_body("body")
    assert share_image._safe_web_url(" https://example.com ") == "https://example.com"
    assert share_image._safe_web_url("javascript:alert(1)") == ""


def test_social_branding_renders_only_safe_links(tmp_path):
    assert share_image.ShareImageBranding().has_xiaohongshu is False
    assert share_image._xiaohongshu_card(share_image.ShareImageBranding(), "en") == ""

    qr = tmp_path / "qr.png"
    qr.write_bytes(b"qr")
    branding = share_image.ShareImageBranding(
        xiaohongshu_url="https://example.com/profile",
        xiaohongshu_handle="@stockpulse",
        xiaohongshu_id="123",
        xiaohongshu_qr_path=str(qr),
    )
    assert branding.has_xiaohongshu is True
    card = share_image._xiaohongshu_card(branding, "en")
    assert "data:image/png;base64,cXI=" in card
    assert 'href="https://example.com/profile"' in card
    assert "@stockpulse · ID 123" in card
    footer = share_image._footer(branding, " · Local", "en")
    assert "SiinXu/stock-pulse-ai" in footer
    assert "Local" in footer
