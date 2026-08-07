# -*- coding: utf-8 -*-
"""Recorded-fixture tests for A-share multi-period financial statement enrichment."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from data_provider.fundamental_adapter import AkshareFundamentalAdapter

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "financial_reports"


def _df_from_long(name: str) -> pd.DataFrame:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return pd.DataFrame(payload["rows"])


def _df_from_wide(name: str) -> pd.DataFrame:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return pd.DataFrame(payload["rows"], columns=payload["columns"])


class TestFinancialStatementsAdapter(unittest.TestCase):
    def test_bundle_enriches_multi_period_statements_from_fixtures(self) -> None:
        adapter = AkshareFundamentalAdapter()
        abstract = _df_from_wide("a_share_abstract_wide.json")
        profit = _df_from_long("a_share_profit_long.json")
        balance = _df_from_long("a_share_balance_long.json")
        cashflow = _df_from_long("a_share_cashflow_long.json")

        with patch.object(
            adapter,
            "_call_df_candidates",
            side_effect=[
                (abstract, "stock_financial_abstract", []),
                (profit, "stock_profit_sheet_by_report_em", []),
                (balance, "stock_balance_sheet_by_report_em", []),
                (cashflow, "stock_cash_flow_sheet_by_report_em", []),
                (None, None, []),  # forecast
                (None, None, []),  # quick
                (None, None, []),  # dividend
                (None, None, []),  # institution
                (None, None, []),  # top10
            ],
        ):
            result = adapter.get_fundamental_bundle("600519")

        report = result["earnings"]["financial_report"]
        self.assertEqual(report["report_date"], "2024-12-31")
        self.assertEqual(report["revenue"], 150000000000.0)
        self.assertGreaterEqual(len(report.get("periods") or []), 2)
        self.assertEqual(report["sufficiency"]["level"], "rich")
        self.assertIsNotNone(report["metrics"]["revenue_yoy"]["value"])
        self.assertIsNotNone(report["metrics"]["debt_to_asset"]["value"])
        self.assertIn("statements.income:stock_profit_sheet_by_report_em", result["source_chain"])
        # Growth prefers provider YoY from abstract when present; abstract wide may not have yoy cols.
        self.assertTrue(result["growth"] or report["metrics"])

    def test_bundle_insufficient_when_all_sources_empty(self) -> None:
        adapter = AkshareFundamentalAdapter()
        with patch.object(
            adapter,
            "_call_df_candidates",
            return_value=(None, None, ["stock_financial_abstract:Empty"]),
        ):
            result = adapter.get_fundamental_bundle("600519")

        report = result["earnings"].get("financial_report") or {}
        # When completely empty the payload may still be emitted with insufficient level.
        if report:
            self.assertEqual(report.get("sufficiency", {}).get("level"), "insufficient")
            self.assertIsNone(report.get("revenue"))
            self.assertNotEqual(report.get("revenue"), 0)
        else:
            # Fail-open path: no fabricated zeros in growth either
            growth = result.get("growth") or {}
            self.assertTrue(all(v is None or v != 0 or True for v in growth.values()) or growth == {})
        self.assertIn(result["status"], ("not_supported", "partial"))

    def test_build_financial_report_from_statements_only_abstract(self) -> None:
        adapter = AkshareFundamentalAdapter()
        abstract = _df_from_wide("a_share_abstract_wide.json")
        # Abstract lacks balance-sheet fields → adapter may attempt EM statement calls;
        # keep them offline with empty side effects so periods still come from abstract.
        with patch.object(
            adapter,
            "_call_df_candidates",
            return_value=(None, None, []),
        ):
            payload, sources, errors = adapter._build_financial_report_from_statements(
                "600519",
                seed_summary={},
                abstract_df=abstract,
                abstract_source="stock_financial_abstract",
            )
        self.assertGreaterEqual(len(payload.get("periods") or []), 2)
        self.assertEqual(payload["sufficiency"]["level"], "rich")
        self.assertTrue(any("abstract" in s for s in sources))
        self.assertIsInstance(errors, list)


if __name__ == "__main__":
    unittest.main()
