# -*- coding: utf-8 -*-
"""Tests for LLM cost metering and usage attribution (Refs #166 / #248)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from src.llm.attribution import (
    ROUTE_OUTCOME_FALLBACK_SUCCESS,
    ROUTE_OUTCOME_FAILED,
    ROUTE_OUTCOME_PRIMARY_SUCCESS,
    classify_route_outcome,
    usage_attribution_scope,
    UsageAttribution,
)
from src.llm.cost import (
    COST_STATUS_PRICED,
    COST_STATUS_PROVIDER_REPORTED,
    COST_STATUS_UNPRICED,
    _reset_pricing_cache_for_tests,
    estimate_usage_cost,
    estimate_usage_cost_usd,
    enrich_usage_with_cost,
)
from src.storage import DatabaseManager, persist_llm_usage


def _fresh_db() -> DatabaseManager:
    DatabaseManager.reset_instance()
    return DatabaseManager(db_url="sqlite:///:memory:")


class TestCostMetering(unittest.TestCase):
    def tearDown(self) -> None:
        _reset_pricing_cache_for_tests()
        os.environ.pop("LLM_COST_PRICING_PATH", None)
        os.environ.pop("LLM_USAGE_ATTRIBUTION_ENABLED", None)

    def test_provider_reported_cost_wins(self) -> None:
        estimate = estimate_usage_cost(
            {"response_cost": 0.42, "prompt_tokens": 10, "completion_tokens": 5},
            model="unknown/model",
        )
        self.assertEqual(estimate.status, COST_STATUS_PROVIDER_REPORTED)
        self.assertAlmostEqual(estimate.cost_usd or 0.0, 0.42)
        self.assertAlmostEqual(
            estimate_usage_cost_usd({"response_cost": 0.42}), 0.42
        )

    def test_unpriced_model_is_honest_for_usage_and_zero_for_budget(self) -> None:
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        with patch("src.llm.cost.lookup_model_pricing", return_value=None):
            estimate = estimate_usage_cost(usage, model="custom/unknown-model")
            budget = estimate_usage_cost_usd(usage, model="custom/unknown-model")
        self.assertEqual(estimate.status, COST_STATUS_UNPRICED)
        self.assertIsNone(estimate.cost_usd)
        self.assertEqual(budget, 0.0)

    def test_pricing_path_rates_per_million(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pricing.json"
            path.write_text(
                json.dumps(
                    {
                        "test/model": {
                            "input_cost_per_1m_tokens": 1.0,
                            "output_cost_per_1m_tokens": 2.0,
                        }
                    }
                ),
                encoding="utf-8",
            )
            os.environ["LLM_COST_PRICING_PATH"] = str(path)
            _reset_pricing_cache_for_tests()
            usage = {"prompt_tokens": 1_000_000, "completion_tokens": 500_000}
            estimate = estimate_usage_cost(usage, model="test/model")
        self.assertEqual(estimate.status, COST_STATUS_PRICED)
        self.assertAlmostEqual(estimate.cost_usd or 0.0, 2.0)

    def test_enrich_usage_with_cost_fields(self) -> None:
        enriched = enrich_usage_with_cost(
            {"prompt_tokens": 1, "completion_tokens": 1, "response_cost": 0.05},
            model="x",
        )
        self.assertEqual(enriched["cost_status"], COST_STATUS_PROVIDER_REPORTED)
        self.assertAlmostEqual(enriched["estimated_cost_usd"], 0.05)


class TestRouteClassification(unittest.TestCase):
    def test_primary_fallback_failed(self) -> None:
        self.assertEqual(
            classify_route_outcome(attempt_index=0, success=True),
            ROUTE_OUTCOME_PRIMARY_SUCCESS,
        )
        self.assertEqual(
            classify_route_outcome(attempt_index=1, success=True),
            ROUTE_OUTCOME_FALLBACK_SUCCESS,
        )
        self.assertEqual(
            classify_route_outcome(attempt_index=2, success=False),
            ROUTE_OUTCOME_FAILED,
        )


class TestAttributionPersistAndSummary(unittest.TestCase):
    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        os.environ.pop("LLM_USAGE_ATTRIBUTION_ENABLED", None)

    def test_persist_and_aggregate_cost_and_routing(self) -> None:
        db = _fresh_db()
        now = datetime.now()
        with patch("src.storage.DatabaseManager.get_instance", return_value=db):
            persist_llm_usage(
                {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                    "response_cost": 0.1,
                    "route_outcome": ROUTE_OUTCOME_PRIMARY_SUCCESS,
                    "latency_ms": 120,
                },
                model="test/model-a",
                call_type="agent",
                stage="agent_step",
                agent_mode="standard",
                run_id="run1",
                call_success=True,
            )
            persist_llm_usage(
                {
                    "prompt_tokens": 5,
                    "completion_tokens": 5,
                    "total_tokens": 10,
                    "route_outcome": ROUTE_OUTCOME_FALLBACK_SUCCESS,
                    "response_cost": 0.0,
                },
                model="test/model-b",
                call_type="agent",
                stage="agent_step",
                agent_mode="standard",
                run_id="run1",
                call_success=True,
            )
            with patch("src.llm.cost.lookup_model_pricing", return_value=None):
                persist_llm_usage(
                    {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                        "route_outcome": ROUTE_OUTCOME_FAILED,
                    },
                    model="custom/unpriced",
                    call_type="analysis",
                    stage="analysis",
                    call_success=False,
                )

        summary = db.get_llm_usage_summary(now - timedelta(days=1), now + timedelta(days=1))
        self.assertEqual(summary["total_calls"], 3)
        self.assertAlmostEqual(summary["total_estimated_cost_usd"] or 0.0, 0.1)
        self.assertGreaterEqual(summary["priced_calls"], 1)
        self.assertGreaterEqual(summary["unpriced_calls"], 1)
        self.assertEqual(summary["routing_primary_success"], 1)
        self.assertEqual(summary["routing_fallback_success"], 1)
        self.assertEqual(summary["routing_failed"], 1)
        self.assertAlmostEqual(summary["routing_success_rate"] or 0.0, 2 / 3)
        self.assertAlmostEqual(summary["routing_fallback_rate"] or 0.0, 0.5)
        self.assertTrue(any(s["stage"] == "agent_step" for s in summary["by_stage"]))
        self.assertTrue(any(m["agent_mode"] == "standard" for m in summary["by_agent_mode"]))

        records = db.get_llm_usage_records(now - timedelta(days=1), now + timedelta(days=1), limit=10)
        self.assertEqual(len(records), 3)
        self.assertTrue(any(r.get("route_outcome") == ROUTE_OUTCOME_FAILED for r in records))

    def test_attribution_disabled_skips_cost_fields(self) -> None:
        os.environ["LLM_USAGE_ATTRIBUTION_ENABLED"] = "false"
        db = _fresh_db()
        now = datetime.now()
        with patch("src.storage.DatabaseManager.get_instance", return_value=db):
            persist_llm_usage(
                {
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                    "response_cost": 1.0,
                },
                model="test/model",
                call_type="analysis",
                stage="analysis",
            )
        summary = db.get_llm_usage_summary(now - timedelta(days=1), now + timedelta(days=1))
        self.assertEqual(summary["total_calls"], 1)
        self.assertEqual(summary["total_tokens"], 20)
        self.assertIsNone(summary["total_estimated_cost_usd"])
        records = db.get_llm_usage_records(now - timedelta(days=1), now + timedelta(days=1), limit=5)
        self.assertIsNone(records[0].get("estimated_cost_usd"))
        self.assertIsNone(records[0].get("cost_status"))

    def test_context_scope_merges_into_persist(self) -> None:
        db = _fresh_db()
        now = datetime.now()
        with patch("src.storage.DatabaseManager.get_instance", return_value=db):
            with usage_attribution_scope(
                UsageAttribution(run_id="ctx-run", agent_mode="quick", stage="agent_step")
            ):
                persist_llm_usage(
                    {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                        "response_cost": 0.01,
                    },
                    model="m",
                    call_type="agent",
                )
        records = db.get_llm_usage_records(now - timedelta(days=1), now + timedelta(days=1), limit=5)
        self.assertEqual(records[0]["run_id"], "ctx-run")
        self.assertEqual(records[0]["agent_mode"], "quick")
        self.assertEqual(records[0]["stage"], "agent_step")


if __name__ == "__main__":
    unittest.main()
