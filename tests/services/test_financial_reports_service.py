# -*- coding: utf-8 -*-
"""Deterministic tests for financial_reports_service (issue #235)."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.services.financial_reports_service import (
    assess_sufficiency,
    build_financial_report_payload,
    compute_statement_metrics,
    extract_periods_from_wide_or_long,
    format_financial_report_prompt_section,
    merge_period_lists,
    safe_float,
    to_eastmoney_report_symbol,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "financial_reports"


def _load_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TestFinancialReportsService(unittest.TestCase):
    def test_to_eastmoney_report_symbol_a_share(self) -> None:
        self.assertEqual(to_eastmoney_report_symbol("600519"), "SH600519")
        self.assertEqual(to_eastmoney_report_symbol("000001"), "SZ000001")
        self.assertEqual(to_eastmoney_report_symbol("300750"), "SZ300750")
        self.assertEqual(to_eastmoney_report_symbol("920748"), "BJ920748")
        self.assertIsNone(to_eastmoney_report_symbol("AAPL"))
        self.assertIsNone(to_eastmoney_report_symbol("HK00700"))

    def test_extract_periods_from_wide_abstract_fixture(self) -> None:
        payload = _load_json("a_share_abstract_wide.json")
        df = pd.DataFrame(payload["rows"], columns=payload["columns"])
        periods = extract_periods_from_wide_or_long(df, max_periods=8)
        self.assertGreaterEqual(len(periods), 3)
        self.assertEqual(periods[0]["report_date"], "2024-12-31")
        self.assertEqual(periods[0]["revenue"], 150000000000.0)
        self.assertEqual(periods[1]["report_date"], "2024-09-30")

    def test_extract_periods_from_long_profit_fixture(self) -> None:
        payload = _load_json("a_share_profit_long.json")
        df = pd.DataFrame(payload["rows"])
        periods = extract_periods_from_wide_or_long(df)
        self.assertEqual(len(periods), 3)
        self.assertEqual(periods[0]["net_profit_parent"], 70000000000.0)

    def test_merge_and_metrics_yoy_period_match(self) -> None:
        profit = extract_periods_from_wide_or_long(pd.DataFrame(_load_json("a_share_profit_long.json")["rows"]))
        balance = extract_periods_from_wide_or_long(pd.DataFrame(_load_json("a_share_balance_long.json")["rows"]))
        cashflow = extract_periods_from_wide_or_long(pd.DataFrame(_load_json("a_share_cashflow_long.json")["rows"]))
        periods = merge_period_lists(profit, balance, cashflow)
        self.assertGreaterEqual(len(periods), 2)
        latest = periods[0]
        self.assertEqual(latest["report_date"], "2024-12-31")
        self.assertEqual(latest["total_assets"], 300000000000.0)
        self.assertEqual(latest["operating_cash_flow"], 80000000000.0)

        metrics = compute_statement_metrics(periods)
        # (150-130)/130 * 100 = 15.3846...
        self.assertAlmostEqual(metrics["revenue_yoy"]["value"], (150 - 130) / 130 * 100, places=3)
        self.assertIn("prior_year_same.revenue", metrics["revenue_yoy"]["formula"])
        self.assertAlmostEqual(
            metrics["debt_to_asset"]["value"],
            80000000000.0 / 300000000000.0 * 100,
            places=3,
        )
        self.assertAlmostEqual(
            metrics["ocf_to_net_profit"]["value"],
            80000000000.0 / 70000000000.0,
            places=3,
        )
        # Financial honesty: never invent zeros when base missing
        thin = compute_statement_metrics([{"report_date": "2024-12-31", "revenue": 100.0}])
        self.assertIsNone(thin["revenue_yoy"]["value"])
        self.assertEqual(thin["revenue_yoy"]["basis"], "unavailable")

    def test_build_payload_rich_and_insufficient(self) -> None:
        profit = extract_periods_from_wide_or_long(pd.DataFrame(_load_json("a_share_profit_long.json")["rows"]))
        balance = extract_periods_from_wide_or_long(pd.DataFrame(_load_json("a_share_balance_long.json")["rows"]))
        cashflow = extract_periods_from_wide_or_long(pd.DataFrame(_load_json("a_share_cashflow_long.json")["rows"]))
        periods = merge_period_lists(profit, balance, cashflow)
        rich = build_financial_report_payload(periods=periods, currency="CNY")
        self.assertEqual(rich["sufficiency"]["level"], "rich")
        self.assertIsNotNone(rich["revenue"])
        self.assertTrue(rich["sufficiency"]["has_multi_period_history"])
        self.assertIn("not real-time", rich["data_recency"]["note"])

        empty = build_financial_report_payload(periods=[], currency="CNY")
        self.assertEqual(empty["sufficiency"]["level"], "insufficient")
        self.assertIn("insufficient fundamentals", empty["sufficiency"]["message"])
        # No silent zeros
        self.assertIsNone(empty.get("revenue"))
        self.assertIsNone(empty.get("net_profit_parent"))

    def test_assess_sufficiency_partial(self) -> None:
        report = {"report_date": "2024-12-31", "revenue": 1.0, "net_profit_parent": None, "operating_cash_flow": None}
        result = assess_sufficiency(report, periods=[{"report_date": "2024-12-31", "revenue": 1.0}])
        self.assertEqual(result["level"], "partial")
        self.assertIn("net_profit_parent", result["missing_fields"])

    def test_prompt_section_insufficient_and_rich(self) -> None:
        insufficient = format_financial_report_prompt_section({}, language="en")
        self.assertIn("insufficient fundamentals", insufficient)
        self.assertIn("do not invent", insufficient.lower())

        periods = extract_periods_from_wide_or_long(pd.DataFrame(_load_json("a_share_profit_long.json")["rows"]))
        payload = build_financial_report_payload(periods=periods)
        section = format_financial_report_prompt_section(payload, language="zh")
        self.assertIn("财务报表（事实）", section)
        self.assertIn("充分性", section)
        self.assertIn("N/A 必须表述为缺失", section)

    def test_safe_float_never_zero_for_empty(self) -> None:
        self.assertIsNone(safe_float(None))
        self.assertIsNone(safe_float(""))
        self.assertIsNone(safe_float("-"))
        self.assertIsNone(safe_float("N/A"))
        self.assertEqual(safe_float(0), 0.0)
        self.assertEqual(safe_float("12.5%"), 12.5)


if __name__ == "__main__":
    unittest.main()
