# -*- coding: utf-8 -*-
"""Unit tests for backtest methodology contract."""

from __future__ import annotations

import unittest
from datetime import date

from src.core.backtest_methodology import (
    ENGINE_VERSION_MAX_LEN,
    SAMPLE_SPLIT_IN_SAMPLE,
    SAMPLE_SPLIT_OUT_OF_SAMPLE,
    CostModelConfig,
    SampleSplitConfig,
    apply_round_trip_cost,
    build_methodology_statement,
    engine_version_for_cost_model,
    normalize_sample_split,
)


class BacktestMethodologyTestCase(unittest.TestCase):
    def test_cost_model_rejects_nan_and_negative(self) -> None:
        with self.assertRaises(ValueError):
            CostModelConfig(commission_bps=float("nan"))
        with self.assertRaises(ValueError):
            CostModelConfig(slippage_bps=-1.0)

    def test_apply_round_trip_cost_cash_is_zero(self) -> None:
        cost = CostModelConfig(commission_bps=10.0, slippage_bps=5.0)
        self.assertEqual(
            apply_round_trip_cost(
                gross_return_pct=8.0,
                cost_model=cost,
                position="cash",
            ),
            0.0,
        )

    def test_sample_split_includes_by_date(self) -> None:
        split = SampleSplitConfig(
            mode=SAMPLE_SPLIT_IN_SAMPLE,
            split_date=date(2024, 6, 1),
        )
        self.assertTrue(split.includes(date(2024, 5, 31)))
        self.assertFalse(split.includes(date(2024, 6, 1)))

        oos = SampleSplitConfig(
            mode=SAMPLE_SPLIT_OUT_OF_SAMPLE,
            split_date=date(2024, 6, 1),
        )
        self.assertTrue(oos.includes(date(2024, 6, 1)))
        self.assertFalse(oos.includes(date(2024, 5, 31)))

    def test_normalize_sample_split_requires_date_for_non_full(self) -> None:
        with self.assertRaises(ValueError):
            normalize_sample_split(SAMPLE_SPLIT_IN_SAMPLE, None)

    def test_methodology_statement_is_not_return_promise(self) -> None:
        stmt = build_methodology_statement(
            cost_model=CostModelConfig(commission_bps=5.0, slippage_bps=5.0),
            engine_version="v1",
            eval_window_days=10,
        )
        self.assertFalse(stmt["is_return_promise"])
        self.assertIn("must not be presented as guaranteed", stmt["disclaimer"].lower())
        self.assertEqual(stmt["look_ahead_policy"], "forward_only_after_resolved_start_session")
        self.assertEqual(stmt["survivorship_policy"], "analyzed_universe_only")
        self.assertIn("percent_returns_currency_agnostic", stmt["currency_policy"])
        self.assertEqual(stmt["cost_model"]["round_trip_cost_pct"], 0.2)
        joined = " ".join(stmt["limitations"]).lower()
        self.assertIn("survivorship", joined)
        self.assertIn("look-ahead", joined)

    def test_engine_version_fingerprint_isolates_nonzero_cost_models(self) -> None:
        zero = engine_version_for_cost_model("v1", CostModelConfig())
        self.assertEqual(zero, "v1")
        self.assertLessEqual(len(zero), ENGINE_VERSION_MAX_LEN)

        taxed = engine_version_for_cost_model(
            "v1",
            CostModelConfig(commission_bps=50.0, slippage_bps=50.0),
        )
        other = engine_version_for_cost_model(
            "v1",
            CostModelConfig(commission_bps=10.0, slippage_bps=0.0),
        )
        self.assertNotEqual(taxed, "v1")
        self.assertNotEqual(taxed, other)
        self.assertLessEqual(len(taxed), ENGINE_VERSION_MAX_LEN)
        self.assertLessEqual(len(other), ENGINE_VERSION_MAX_LEN)


if __name__ == "__main__":
    unittest.main()
