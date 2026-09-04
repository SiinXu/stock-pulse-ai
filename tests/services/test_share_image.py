# -*- coding: utf-8 -*-
from datetime import date
from pathlib import Path

from src.share_image import ShareImageBranding, build_share_image_html

STOCK_MARKDOWN = "# 贵州茅台 600519\n\n## 决策仪表盘\n\n- 评分: 80\n"
DISTINCTIVE_XHS_ID = "99887766"


def test_build_share_image_html_includes_stock_identity_and_brand():
    html = build_share_image_html(STOCK_MARKDOWN, branding=ShareImageBranding())
    assert "StockPulse" in html
    assert "600519" in html or "贵州茅台" in html
    assert 'class="qr-card' not in html
    assert "SiinXu/stock-pulse-ai" in html


def test_share_image_omits_xiaohongshu_numeric_id_from_full_html(tmp_path):
    qr = tmp_path / "qr.png"
    qr.write_bytes(b"qr")
    html = build_share_image_html(
        STOCK_MARKDOWN,
        branding=ShareImageBranding(
            xiaohongshu_url="https://example.com/xiaohongshu",
            xiaohongshu_handle="@stockpulse",
            xiaohongshu_id=DISTINCTIVE_XHS_ID,
            xiaohongshu_qr_path=str(qr),
        ),
    )
    assert "<b>小红书</b>@stockpulse" in html
    assert DISTINCTIVE_XHS_ID not in html
    assert "ID 99887766" not in html
    assert 'href="https://example.com/xiaohongshu"' in html
    assert "data:image/png;base64,cXI=" in html
    assert "SiinXu/stock-pulse-ai" in html
    assert "javascript:" not in html


def test_share_image_empty_branding_keeps_fork_footer_without_xiaohongshu_region():
    html = build_share_image_html(STOCK_MARKDOWN, branding=ShareImageBranding())
    assert "SiinXu/stock-pulse-ai" in html
    assert "小红书" not in html
    assert "Xiaohongshu" not in html
    assert 'class="qr-card' not in html


def test_share_image_id_only_branding_omits_region_and_distinctive_id():
    html = build_share_image_html(
        STOCK_MARKDOWN,
        branding=ShareImageBranding(xiaohongshu_id=DISTINCTIVE_XHS_ID),
    )
    assert DISTINCTIVE_XHS_ID not in html
    assert 'class="qr-card' not in html
    assert "SiinXu/stock-pulse-ai" in html


def test_share_image_declares_supported_cjk_fonts_and_docker_installs_them():
    html = build_share_image_html(
        "# 贵州茅台 600519 分析报告\n\n## 核心判断\n\n- 趋势偏多\n",
        generated_on=date(2026, 8, 24),
    )

    assert 'html[lang="zh-CN"] body' in html
    assert '"Noto Sans CJK SC"' in html
    assert 'html[lang="ko"] body' in html
    assert '"Noto Sans CJK KR"' in html

    dockerfile = (
        Path(__file__).resolve().parents[2] / "docker" / "Dockerfile"
    ).read_text(encoding="utf-8")
    assert "fonts-noto-cjk \\" in dockerfile


def test_japanese_stock_share_image_uses_english_report_cjk_fallback():
    html = build_share_image_html(
        "# トヨタ自動車 7203.T Analysis Report\n\n## Core Conclusion\n\n- Bullish trend.\n",
        generated_on=date(2026, 8, 24),
        structured_payload={
            "code": "7203.T",
            "name": "トヨタ自動車",
            "report_language": "en",
        },
    )

    assert 'class="poster stock"' in html
    assert '<html lang="en">' in html
    assert '"Segoe UI", "Noto Sans CJK SC", "Noto Sans CJK KR"' in html
    assert '"Noto Sans CJK SC"' in html
    assert "トヨタ自動車" in html


def test_japanese_market_share_image_uses_korean_report_font_contract():
    html = build_share_image_html(
        "# 日股市场复盘\n\n## 主要指数\n\n- 日経平均株価上涨。\n",
        generated_on=date(2026, 8, 24),
        structured_payload={
            "kind": "market_review",
            "region": "jp",
            "report_language": "ko",
            "title": "일본 시장 리뷰",
            "indices": [
                {"name": "日経平均株価", "current": 42123.45, "change_pct": 0.8},
            ],
        },
    )

    assert 'class="poster market"' in html
    assert '<html lang="ko">' in html
    assert 'html[lang="ko"] body' in html
    assert '"Noto Sans CJK KR"' in html
    assert "日経平均株価" in html
