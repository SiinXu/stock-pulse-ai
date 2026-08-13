# -*- coding: utf-8 -*-
"""Offline contracts for bounded candidate discovery (#177 / #325)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from src.services.candidate_discovery_service import (
    MAX_PROVIDER_CALLS_HARD_CAP,
    MAX_RESULTS_HARD_CAP,
    MAX_UNIVERSE_EVALUATED,
    CandidateDiscoveryService,
    DiscoveryCancelled,
    DiscoveryValidationError,
    IndexSymbol,
    parse_natural_language_query,
)


def _symbol(
    code: str,
    name: str,
    *,
    market: str = "CN",
    aliases: tuple[str, ...] = (),
) -> IndexSymbol:
    blob = " ".join([name, code, *aliases]).lower()
    return IndexSymbol(
        code=code,
        display_code=code.split(".")[0] if "." in code else code,
        name=name,
        market=market,
        aliases=aliases,
        search_blob=blob,
    )


class CandidateDiscoveryServiceTests(unittest.TestCase):
    def test_parse_natural_language_query_extracts_markets_and_thresholds(self) -> None:
        criteria = parse_natural_language_query("A股 银行 涨幅>2 成交额>1亿")
        self.assertIn("CN", criteria.markets)
        self.assertIn("银行", criteria.keywords)
        self.assertEqual(criteria.min_change_pct, 2.0)
        self.assertEqual(criteria.min_amount, 100_000_000.0)

    def test_watchlist_discovery_is_bounded_and_explainable(self) -> None:
        quotes: Dict[str, Dict[str, Any]] = {
            "000001.SZ": {
                "price": 10.5,
                "change_pct": 3.2,
                "amount": 200_000_000,
                "name": "平安银行",
                "source": "test",
            },
            "600519.SH": {
                "price": 1600.0,
                "change_pct": 0.5,
                "amount": 80_000_000,
                "name": "贵州茅台",
                "source": "test",
            },
            "300750.SZ": {
                "price": 180.0,
                "change_pct": 4.1,
                "amount": 300_000_000,
                "name": "宁德时代",
                "source": "test",
            },
        }
        index = [
            _symbol("000001.SZ", "平安银行", aliases=("平银",)),
            _symbol("600519.SH", "贵州茅台"),
            _symbol("300750.SZ", "宁德时代"),
        ]
        calls: List[str] = []

        def quote_fetcher(code: str) -> Optional[Dict[str, Any]]:
            calls.append(code)
            return quotes.get(code)

        service = CandidateDiscoveryService(
            index_loader=lambda: index,
            quote_fetcher=quote_fetcher,
            watchlist_loader=lambda: ["000001.SZ", "600519.SH", "300750.SZ"],
        )
        result = service.discover(
            query="银行",
            universe="watchlist",
            max_results=5,
            max_provider_calls=10,
            language="zh",
        )

        self.assertEqual(result["pack_version"], "candidate_discovery/1.0")
        self.assertEqual(result["status"], "ok")
        self.assertGreaterEqual(result["candidate_count"], 1)
        self.assertLessEqual(result["candidate_count"], MAX_RESULTS_HARD_CAP)
        self.assertLessEqual(result["cost_contract"]["provider_calls"], 10)
        self.assertLessEqual(result["cost_contract"]["provider_calls"], MAX_PROVIDER_CALLS_HARD_CAP)
        self.assertTrue(result["cost_contract"]["bounded"])
        self.assertEqual(result["universe_contract"]["source"], "watchlist")
        self.assertLessEqual(result["universe_contract"]["evaluated_count"], MAX_UNIVERSE_EVALUATED)
        top = result["candidates"][0]
        self.assertIn("code", top)
        self.assertTrue(top["reason"])
        self.assertIn("reason_codes", top)
        self.assertIn("Research screening only", result["research_disclaimer"])
        self.assertTrue(
            any("银行" in item["name"] or "银行" in item["reason"] for item in result["candidates"])
        )
        self.assertEqual(len(calls), result["cost_contract"]["provider_calls"])

    def test_index_universe_paginates_and_respects_provider_budget(self) -> None:
        index = [_symbol(f"{i:06d}.SZ", f"股票{i}") for i in range(1, 121)]
        calls: List[str] = []

        def quote_fetcher(code: str) -> Optional[Dict[str, Any]]:
            calls.append(code)
            return {"price": 1.0, "change_pct": 1.0, "amount": 1_000_000, "source": "test"}

        service = CandidateDiscoveryService(
            index_loader=lambda: index,
            quote_fetcher=quote_fetcher,
        )
        result = service.discover(
            query="",
            universe="index",
            page=2,
            page_size=20,
            max_results=5,
            max_provider_calls=3,
        )
        self.assertEqual(result["universe_contract"]["page"], 2)
        self.assertEqual(result["universe_contract"]["page_size"], 20)
        self.assertEqual(result["universe_contract"]["resolved_count"], 20)
        self.assertTrue(result["universe_contract"]["has_more"])
        self.assertEqual(result["cost_contract"]["provider_calls"], 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["candidate_count"], 5)

    def test_cancel_check_interrupts_run(self) -> None:
        index = [_symbol("000001.SZ", "平安银行")]
        service = CandidateDiscoveryService(
            index_loader=lambda: index,
            quote_fetcher=lambda _code: {"price": 1.0, "change_pct": 1.0, "amount": 1.0},
            watchlist_loader=lambda: ["000001.SZ"],
        )
        with self.assertRaises(DiscoveryCancelled):
            service.discover(universe="watchlist", cancel_check=lambda: True)

    def test_unsupported_universe_raises(self) -> None:
        service = CandidateDiscoveryService(index_loader=lambda: [])
        with self.assertRaises(DiscoveryValidationError):
            service.discover(universe="all_market")

    def test_provider_budget_zero_uses_metadata_only(self) -> None:
        index = [_symbol("000001.SZ", "平安银行")]
        calls: List[str] = []
        service = CandidateDiscoveryService(
            index_loader=lambda: index,
            quote_fetcher=lambda code: calls.append(code) or {"price": 1.0},
            watchlist_loader=lambda: ["000001.SZ"],
        )
        result = service.discover(
            query="银行",
            universe="watchlist",
            max_provider_calls=0,
            max_results=3,
        )
        self.assertEqual(calls, [])
        self.assertEqual(result["cost_contract"]["provider_calls"], 0)
        self.assertGreaterEqual(result["candidate_count"], 1)
        self.assertTrue(
            any("metadata_only" in (item.get("reason_codes") or []) for item in result["candidates"])
        )

    def test_watchlist_parse_failure_is_logged_and_returns_an_empty_universe(self) -> None:
        service = CandidateDiscoveryService(
            config_provider=lambda: SimpleNamespace(stock_list="invalid"),
            index_loader=lambda: [],
        )

        with (
            patch("src.utils.stock_list.split_stock_list", side_effect=ValueError("invalid")),
            self.assertLogs("src.services.candidate_discovery_service", level="DEBUG") as logs,
        ):
            result = service.discover(universe="watchlist")

        self.assertEqual(result["empty_reason"], "empty_universe")
        self.assertEqual(result["universe_contract"]["resolved_count"], 0)
        self.assertTrue(
            any("candidate_discovery_watchlist_parse_failed" in entry for entry in logs.output)
        )

    def test_portfolio_lookup_failure_is_logged_and_returns_an_empty_universe(self) -> None:
        service = CandidateDiscoveryService(index_loader=lambda: [])

        with (
            patch("src.repositories.portfolio_repo.PortfolioRepository") as repository,
            self.assertLogs("src.services.candidate_discovery_service", level="WARNING") as logs,
        ):
            repository.return_value.list_cached_positions.side_effect = RuntimeError("offline")
            result = service.discover(universe="portfolio", account_id=7)

        self.assertEqual(result["empty_reason"], "empty_universe")
        self.assertEqual(result["universe_contract"]["resolved_count"], 0)
        self.assertTrue(
            any("candidate_discovery_portfolio_failed" in entry for entry in logs.output)
        )


if __name__ == "__main__":
    unittest.main()
