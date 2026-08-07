# -*- coding: utf-8 -*-
"""Report rendering: rich multi-period vs insufficient fundamentals (issue #235)."""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.notification_parts.rendering import _RenderingMethods
from src.report_language import get_report_labels
from src.services.financial_reports_service import build_financial_report_payload


class _Renderer(_RenderingMethods):
    # Mirrors src.notification currency suffixes used by _format_amount_cn.
    _CURRENCY_SUFFIX = {
        "CNY": "元",
        "RMB": "元",
        "HKD": "港元",
        "USD": "美元",
        "": "元",
    }


class TestFinancialReportRendering(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = _Renderer()
        self.labels = get_report_labels("en")

    def test_rich_summary_includes_history(self) -> None:
        periods = [
            {
                "report_date": "2024-12-31",
                "revenue": 150e9,
                "net_profit_parent": 70e9,
                "operating_cash_flow": 80e9,
                "roe": 32.0,
            },
            {
                "report_date": "2023-12-31",
                "revenue": 130e9,
                "net_profit_parent": 60e9,
                "operating_cash_flow": 65e9,
                "roe": 30.0,
            },
        ]
        report = build_financial_report_payload(periods=periods, currency="CNY")
        lines: list[str] = []
        self.renderer._append_financial_summary(
            lines,
            {"financial_report": report, "growth": {}},
            self.labels,
        )
        text = "\n".join(lines)
        self.assertIn(self.labels["financial_summary_heading"], text)
        self.assertIn("2024-12-31", text)
        self.assertIn(self.labels["financial_history_heading"], text)
        self.assertIn("2023-12-31", text)
        self.assertIn(self.labels["financial_recency_label"], text)
        self.assertNotIn("insufficient fundamentals", text.lower() if False else text)
        # Must not fabricate zeros when values exist as large amounts
        self.assertNotRegex(text, r"\| 0\.00 元 \|")

    def test_insufficient_summary_is_explicit(self) -> None:
        report = build_financial_report_payload(periods=[], currency="CNY")
        lines: list[str] = []
        self.renderer._append_financial_summary(
            lines,
            {"financial_report": report, "growth": {}},
            self.labels,
        )
        text = "\n".join(lines)
        self.assertIn(self.labels["financial_summary_heading"], text)
        self.assertIn("insufficient fundamentals", text)
        # No fake zero metrics table
        self.assertNotIn(self.labels["revenue_yoy_label"], text)

    def test_get_fundamental_blocks_passes_enriched_report(self) -> None:
        report = build_financial_report_payload(
            periods=[{"report_date": "2024-12-31", "revenue": 1.0, "net_profit_parent": 0.5, "operating_cash_flow": 0.4}],
        )
        result = SimpleNamespace(
            fundamental_context={
                "earnings": {"data": {"financial_report": report, "dividend": {}}},
                "growth": {"data": {}},
            }
        )
        blocks = self.renderer._get_fundamental_blocks(result)
        self.assertEqual(blocks["financial_report"]["report_date"], "2024-12-31")
        self.assertIn("sufficiency", blocks["financial_report"])


if __name__ == "__main__":
    unittest.main()
