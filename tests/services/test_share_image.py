# -*- coding: utf-8 -*-
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
