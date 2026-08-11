# -*- coding: utf-8 -*-
"""Boundary and known-answer tests for financial calculator pure functions."""

from __future__ import annotations

import math
import unittest

from src.services.financial_calculator_service import (
    CalculatorInputError,
    compute_compound_growth,
    solve_target_contribution,
    solve_target_duration,
)


class CompoundGrowthTests(unittest.TestCase):
    def test_zero_rate_linear_accumulation(self) -> None:
        result = compute_compound_growth(
            principal=1000.0,
            annual_rate=0.0,
            years=2.0,
            contribution_per_period=100.0,
            periods_per_year=12,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["period_count"], 24)
        self.assertAlmostEqual(result["final_value"], 1000.0 + 100.0 * 24, places=9)
        self.assertAlmostEqual(result["total_contributed"], 1000.0 + 100.0 * 24, places=9)
        self.assertAlmostEqual(result["total_gain"], 0.0, places=9)
        self.assertEqual(len(result["series"]), 25)  # includes period 0

    def test_positive_rate_known_answer_no_contribution(self) -> None:
        # 1000 at 12% annual compounded monthly for 1 year ≈ 1000 * (1.01)^12
        result = compute_compound_growth(
            principal=1000.0,
            annual_rate=0.12,
            years=1.0,
            contribution_per_period=0.0,
            periods_per_year=12,
        )
        expected = 1000.0 * (1.01 ** 12)
        self.assertAlmostEqual(result["final_value"], expected, places=9)
        self.assertAlmostEqual(result["total_gain"], expected - 1000.0, places=9)

    def test_positive_rate_with_contribution(self) -> None:
        # FV = P*(1+r)^n + c*((1+r)^n - 1)/r
        p, r, n, c = 1000.0, 0.01, 12, 50.0
        expected = p * (1 + r) ** n + c * (((1 + r) ** n - 1) / r)
        result = compute_compound_growth(
            principal=p,
            annual_rate=0.12,
            years=1.0,
            contribution_per_period=c,
            periods_per_year=12,
        )
        self.assertAlmostEqual(result["final_value"], expected, places=9)

    def test_negative_rate_decreases_principal(self) -> None:
        result = compute_compound_growth(
            principal=1000.0,
            annual_rate=-0.12,
            years=1.0,
            contribution_per_period=0.0,
            periods_per_year=12,
        )
        self.assertLess(result["final_value"], 1000.0)
        self.assertLess(result["total_gain"], 0.0)

    def test_daily_horizon_returns_bounded_sample_with_exact_endpoint(self) -> None:
        result = compute_compound_growth(
            principal=1000.0,
            annual_rate=0.05,
            years=100.0,
            contribution_per_period=1.0,
            periods_per_year=365,
        )
        self.assertLessEqual(len(result["series"]), 241)
        self.assertEqual(result["series_returned_points"], len(result["series"]))
        self.assertEqual(result["series_total_points"], 36501)
        self.assertTrue(result["series_sampled"])
        self.assertEqual(result["series"][-1]["period"], 36500)
        self.assertAlmostEqual(result["series"][-1]["balance"], result["final_value"])

    def test_rejects_non_finite_inputs(self) -> None:
        for bad in (math.nan, math.inf, -math.inf):
            with self.subTest(value=bad):
                with self.assertRaises(CalculatorInputError) as ctx:
                    compute_compound_growth(
                        principal=bad,
                        annual_rate=0.05,
                        years=1.0,
                        contribution_per_period=0.0,
                        periods_per_year=12,
                    )
                self.assertEqual(ctx.exception.code, "invalid_input")

    def test_rejects_zero_or_negative_years(self) -> None:
        for years in (0.0, -1.0):
            with self.assertRaises(CalculatorInputError):
                compute_compound_growth(
                    principal=1000.0,
                    annual_rate=0.05,
                    years=years,
                    contribution_per_period=0.0,
                    periods_per_year=12,
                )

    def test_rejects_non_positive_periods_per_year(self) -> None:
        for ppy in (0, -1):
            with self.assertRaises(CalculatorInputError):
                compute_compound_growth(
                    principal=1000.0,
                    annual_rate=0.05,
                    years=1.0,
                    contribution_per_period=0.0,
                    periods_per_year=ppy,
                )

    def test_rejects_period_rate_at_or_below_minus_one(self) -> None:
        # annual -120% monthly => period rate -0.1 ok; annual -1200% monthly = -1.0 invalid
        with self.assertRaises(CalculatorInputError):
            compute_compound_growth(
                principal=1000.0,
                annual_rate=-12.0,
                years=1.0,
                contribution_per_period=0.0,
                periods_per_year=12,
            )


class TargetContributionTests(unittest.TestCase):
    def test_zero_rate_solves_linear_shortfall(self) -> None:
        result = solve_target_contribution(
            target=5000.0,
            principal=1000.0,
            annual_rate=0.0,
            years=2.0,
            periods_per_year=12,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["contribution_per_period"], 166.67)
        self.assertEqual(result["currency_precision_digits"], 2)
        self.assertEqual(result["contribution_rounding"], "ceiling")
        growth = compute_compound_growth(
            principal=1000.0,
            annual_rate=0.0,
            years=2.0,
            contribution_per_period=result["contribution_per_period"],
            periods_per_year=12,
        )
        self.assertGreaterEqual(growth["final_value"], 5000.0)

    def test_positive_rate_round_trip(self) -> None:
        contribution = 100.0
        growth = compute_compound_growth(
            principal=1000.0,
            annual_rate=0.06,
            years=5.0,
            contribution_per_period=contribution,
            periods_per_year=12,
        )
        target = growth["final_value"]
        solved = solve_target_contribution(
            target=target,
            principal=1000.0,
            annual_rate=0.06,
            years=5.0,
            periods_per_year=12,
        )
        self.assertEqual(solved["status"], "ok")
        self.assertEqual(solved["contribution_per_period"], contribution)

    def test_already_met_when_principal_growth_suffices(self) -> None:
        result = solve_target_contribution(
            target=1000.0,
            principal=1000.0,
            annual_rate=0.05,
            years=1.0,
            periods_per_year=12,
        )
        self.assertEqual(result["status"], "already_met")
        self.assertEqual(result["contribution_per_period"], 0.0)

    def test_rejects_nan_target(self) -> None:
        with self.assertRaises(CalculatorInputError) as ctx:
            solve_target_contribution(
                target=math.nan,
                principal=1000.0,
                annual_rate=0.05,
                years=1.0,
                periods_per_year=12,
            )
        self.assertEqual(ctx.exception.code, "invalid_input")


class TargetDurationTests(unittest.TestCase):
    def test_zero_rate_reachable(self) -> None:
        result = solve_target_duration(
            target=5000.0,
            principal=1000.0,
            annual_rate=0.0,
            contribution_per_period=100.0,
            periods_per_year=12,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["period_count"], 40)
        self.assertAlmostEqual(result["years"], 40 / 12, places=9)

    def test_zero_rate_unreachable_without_contribution(self) -> None:
        result = solve_target_duration(
            target=5000.0,
            principal=1000.0,
            annual_rate=0.0,
            contribution_per_period=0.0,
            periods_per_year=12,
        )
        self.assertEqual(result["status"], "unreachable")
        self.assertIsNone(result["period_count"])
        self.assertEqual(result["reason_code"], "non_positive_trajectory")

    def test_zero_rate_unreachable_with_negative_contribution(self) -> None:
        result = solve_target_duration(
            target=5000.0,
            principal=1000.0,
            annual_rate=0.0,
            contribution_per_period=-10.0,
            periods_per_year=12,
        )
        self.assertEqual(result["status"], "unreachable")

    def test_positive_rate_round_trip(self) -> None:
        growth = compute_compound_growth(
            principal=1000.0,
            annual_rate=0.08,
            years=3.0,
            contribution_per_period=50.0,
            periods_per_year=12,
        )
        target = growth["final_value"]
        solved = solve_target_duration(
            target=target,
            principal=1000.0,
            annual_rate=0.08,
            contribution_per_period=50.0,
            periods_per_year=12,
        )
        self.assertEqual(solved["status"], "ok")
        self.assertEqual(solved["period_count"], 36)

    def test_already_met(self) -> None:
        result = solve_target_duration(
            target=500.0,
            principal=1000.0,
            annual_rate=0.05,
            contribution_per_period=0.0,
            periods_per_year=12,
        )
        self.assertEqual(result["status"], "already_met")
        self.assertEqual(result["period_count"], 0)

    def test_negative_rate_with_large_contribution_can_reach(self) -> None:
        result = solve_target_duration(
            target=2000.0,
            principal=1000.0,
            annual_rate=-0.05,
            contribution_per_period=200.0,
            periods_per_year=12,
        )
        self.assertEqual(result["status"], "ok")
        self.assertIsInstance(result["period_count"], int)
        self.assertGreater(result["period_count"], 0)

    def test_rejects_infinity_contribution(self) -> None:
        with self.assertRaises(CalculatorInputError):
            solve_target_duration(
                target=5000.0,
                principal=1000.0,
                annual_rate=0.05,
                contribution_per_period=math.inf,
                periods_per_year=12,
            )

    def test_duration_cap_is_one_hundred_years_for_annual_frequency(self) -> None:
        result = solve_target_duration(
            target=1000.0,
            principal=0.0,
            annual_rate=0.0,
            contribution_per_period=1.0,
            periods_per_year=1,
        )
        self.assertEqual(result["status"], "unreachable")
        self.assertEqual(result["reason_code"], "max_years_exceeded")


if __name__ == "__main__":
    unittest.main()
