# -*- coding: utf-8 -*-
from src.share_image import ShareImageBranding, build_share_image_html

def test_build_share_image_html_includes_stock_identity_and_brand():
    html = build_share_image_html("# 贵州茅台 600519\n\n## 决策仪表盘\n\n- 评分: 80\n", branding=ShareImageBranding())
    assert "StockPulse" in html
    assert "600519" in html or "贵州茅台" in html
