# -*- coding: utf-8 -*-
"""
Contract tests for get_stock_info tool output semantics.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.tools.data_tools import _handle_get_stock_info


STOCK_INFO_CANARY = "STOCK_INFO_PROVIDER_DIAGNOSTIC_CANARY"
STOCK_INFO_PATH = "/Users/private-user/.config/stockpulse/fundamental.json"


class _DummyManager:
    def __init__(self):
        self._context = {
            "market": "cn",
            "status": "partial",
            "coverage": {
                "valuation": "ok",
                "growth": "not_supported",
                "earnings": "not_supported",
                "institution": "not_supported",
                "capital_flow": "not_supported",
                "dragon_tiger": "not_supported",
                "boards": "ok",
            },
            "valuation": {
                "status": "ok",
                "data": {
                    "pe_ratio": 12.3,
                    "pb_ratio": 2.1,
                    "total_mv": 1.0e11,
                    "circ_mv": 7.0e10,
                },
            },
            "growth": {"status": "not_supported", "data": {}},
            "earnings": {"status": "not_supported", "data": {}},
            "institution": {"status": "not_supported", "data": {}},
            "capital_flow": {"status": "not_supported", "data": {}},
            "dragon_tiger": {"status": "not_supported", "data": {}},
            "boards": {
                "status": "ok",
                "data": {
                    "top": [{"name": "白酒", "change_pct": 2.3}],
                    "bottom": [{"name": "煤炭", "change_pct": -1.7}],
                },
            },
        }
        self._belong_boards = [{"name": "白酒"}, {"name": "消费"}]

    def get_fundamental_context(self, _stock_code: str):
        return self._context

    def build_failed_fundamental_context(self, _stock_code: str, _reason: str):
        return {}

    def get_belong_boards(self, _stock_code: str):
        return self._belong_boards

    def get_stock_name(self, _stock_code: str):
        return "贵州茅台"


class _FailingContextManager(_DummyManager):
    def __init__(self):
        super().__init__()
        self.failure_reason = None

    def get_fundamental_context(self, _stock_code: str):
        raise OSError(5, f"fundamental provider failed: {STOCK_INFO_CANARY}", STOCK_INFO_PATH)

    def build_failed_fundamental_context(self, _stock_code: str, reason: str):
        self.failure_reason = reason
        return {
            "market": "cn",
            "status": "failed",
            "coverage": {},
        }


class TestGetStockInfoContract(unittest.TestCase):
    def test_get_stock_info_preserves_board_semantics(self) -> None:
        manager = _DummyManager()
        with patch("src.agent.tools.data_tools._get_fetcher_manager", return_value=manager):
            result = _handle_get_stock_info("600519")

        self.assertEqual(result["name"], "贵州茅台")
        self.assertEqual(result["code"], "600519")
        self.assertEqual(result["pe_ratio"], 12.3)
        self.assertEqual(result["pb_ratio"], 2.1)

        # Contract: boards is compatibility alias of belong_boards.
        self.assertEqual(result["belong_boards"], manager._belong_boards)
        self.assertEqual(result["boards"], result["belong_boards"])

        # Contract: sector_rankings comes from fundamental_context.boards.data.
        self.assertEqual(result["sector_rankings"], manager._context["boards"]["data"])
        self.assertEqual(
            result["fundamental_context"]["boards"]["data"],
            result["sector_rankings"],
        )

    def test_failure_fallback_does_not_receive_or_return_raw_exception(self) -> None:
        manager = _FailingContextManager()
        with patch(
            "src.agent.tools.data_tools._get_fetcher_manager",
            return_value=manager,
        ), self.assertLogs("src.agent.tools.data_tools", level="WARNING") as logs:
            result = _handle_get_stock_info("600519")

        self.assertEqual(manager.failure_reason, "Fundamental data is unavailable.")
        visible = str(result) + "\n" + "\n".join(logs.output)
        self.assertNotIn(STOCK_INFO_CANARY, visible)
        self.assertNotIn(STOCK_INFO_PATH, visible)
        self.assertNotIn("fundamental provider failed", visible)


if __name__ == "__main__":
    unittest.main()
