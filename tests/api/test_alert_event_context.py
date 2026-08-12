# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import unittest

from src.services.alert_event_context import (
    MAX_PUBLIC_TEXT,
    extract_event_display_contexts,
    parse_diagnostics_object,
)


class AlertEventContextExtractionTests(unittest.TestCase):
    def test_parser_accepts_only_bounded_strict_json_objects(self) -> None:
        self.assertEqual(parse_diagnostics_object('{"a": 1}'), {"a": 1})
        self.assertIsNone(parse_diagnostics_object('{"a": NaN}'))
        self.assertIsNone(parse_diagnostics_object("x"))
        self.assertIsNone(parse_diagnostics_object("{" + (" " * 65_536) + "}"))

    def test_projection_is_typed_bounded_and_omits_private_portfolio_fields(self) -> None:
        diagnostics = {
            "impact_context": {
                "why_it_matters": "x" * (MAX_PUBLIC_TEXT + 20),
                "event_category": "earnings",
                "event_categories": ["earnings", "unknown", "earnings", "regulatory"],
                "source_url": "javascript:alert(1)",
                "affected": {
                    "symbol": "AAPL",
                    "in_watchlist": True,
                    "in_portfolio": True,
                    "weight_pct": float("inf"),
                    "account_id": 91,
                    "account_name": "Private account",
                    "quantity": 1234,
                    "market_value": 999999,
                },
                "matched_items": [{"private": "raw provider payload"}],
            },
            "event_context": {"matched_count": 2, "source_url": "https://example.com/news"},
        }

        contexts = extract_event_display_contexts(diagnostics)

        impact = contexts["impact_context"]
        assert impact is not None
        self.assertEqual(len(impact["why_it_matters"]), MAX_PUBLIC_TEXT)
        self.assertEqual(impact["event_categories"], ["earnings", "regulatory"])
        self.assertNotIn("source_url", impact)
        self.assertEqual(
            impact["affected"],
            {"symbol": "AAPL", "in_watchlist": True, "in_portfolio": True},
        )
        self.assertNotIn("matched_items", impact)
        self.assertEqual(contexts["event_context"]["source_url"], "https://example.com/news")


if __name__ == "__main__":
    unittest.main()
