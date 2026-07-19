# -*- coding: utf-8 -*-
"""
Contract tests for get_capital_flow tool output semantics.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.tools.data_tools import _handle_get_capital_flow


CAPITAL_FLOW_CANARY = "CAPITAL_FLOW_PROVIDER_DIAGNOSTIC_CANARY"
CAPITAL_FLOW_PATH = "/Users/private-user/.config/stockpulse/capital-flow.json"


class _DummyManagerOk:
    """Returns a well-formed capital flow context."""

    def get_capital_flow_context(self, _stock_code: str):
        return {
            "status": "ok",
            "data": {
                "stock_flow": {
                    "main_net_inflow": 1500000.0,
                    "inflow_5d": 8000000.0,
                    "inflow_10d": 15000000.0,
                },
                "sector_rankings": {
                    "top": [{"name": "白酒", "inflow": 5e8}, {"name": "半导体", "inflow": 3e8}],
                    "bottom": [{"name": "煤炭", "inflow": -2e8}],
                },
            },
            "errors": [],
        }


class _DummyManagerNotSupported:
    """Returns not_supported status (e.g. ETF or HK stock)."""

    def get_capital_flow_context(self, _stock_code: str):
        return {"status": "not_supported"}


class _DummyManagerRaises:
    """Simulates a fetch failure."""

    def get_capital_flow_context(self, _stock_code: str):
        raise OSError(5, f"capital flow provider failed: {CAPITAL_FLOW_CANARY}", CAPITAL_FLOW_PATH)


class _DummyManagerRawErrors(_DummyManagerOk):
    """Returns provider diagnostics that must not cross the Agent tool boundary."""

    def get_capital_flow_context(self, stock_code: str):
        context = super().get_capital_flow_context(stock_code)
        context["status"] = "partial"
        context["errors"] = [f"provider rejected request: {CAPITAL_FLOW_CANARY} at {CAPITAL_FLOW_PATH}"]
        return context


class TestGetCapitalFlowContract(unittest.TestCase):

    def test_ok_response_shape(self) -> None:
        """Happy path: key fields are present and values match the source data."""
        with patch(
            "src.agent.tools.data_tools._get_fetcher_manager",
            return_value=_DummyManagerOk(),
        ):
            result = _handle_get_capital_flow("600519")

        self.assertEqual(result["stock_code"], "600519")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["main_net_inflow"], 1500000.0)
        self.assertEqual(result["inflow_5d"], 8000000.0)
        self.assertEqual(result["inflow_10d"], 15000000.0)
        self.assertIn("sector_rankings", result)
        self.assertIn("top_inflow_sectors", result["sector_rankings"])
        self.assertIn("top_outflow_sectors", result["sector_rankings"])
        # At most 3 items are returned per ranking list
        self.assertLessEqual(len(result["sector_rankings"]["top_inflow_sectors"]), 3)
        self.assertEqual(result["errors"], [])

    def test_not_supported_for_non_cn_or_etf(self) -> None:
        """ETF / non-CN stocks return status=not_supported with an explanatory note."""
        with patch(
            "src.agent.tools.data_tools._get_fetcher_manager",
            return_value=_DummyManagerNotSupported(),
        ):
            result = _handle_get_capital_flow("510300")

        self.assertEqual(result["stock_code"], "510300")
        self.assertEqual(result["status"], "not_supported")
        self.assertIn("note", result)

    def test_exception_path_formatting(self) -> None:
        """Fetch errors are caught and returned with status=error."""
        with patch(
            "src.agent.tools.data_tools._get_fetcher_manager",
            return_value=_DummyManagerRaises(),
        ), self.assertLogs("src.agent.tools.data_tools", level="WARNING") as logs:
            result = _handle_get_capital_flow("600519")

        self.assertEqual(result["stock_code"], "600519")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "Capital flow data is unavailable.")
        visible = str(result) + "\n" + "\n".join(logs.output)
        self.assertNotIn(CAPITAL_FLOW_CANARY, visible)
        self.assertNotIn(CAPITAL_FLOW_PATH, visible)
        self.assertNotIn("capital flow provider failed", visible)

    def test_provider_errors_are_replaced_with_stable_public_code(self) -> None:
        with patch(
            "src.agent.tools.data_tools._get_fetcher_manager",
            return_value=_DummyManagerRawErrors(),
        ):
            result = _handle_get_capital_flow("600519")

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["errors"], ["capital_flow_provider_error"])
        self.assertNotIn(CAPITAL_FLOW_CANARY, str(result))
        self.assertNotIn(CAPITAL_FLOW_PATH, str(result))


if __name__ == "__main__":
    unittest.main()
