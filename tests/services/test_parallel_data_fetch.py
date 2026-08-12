# -*- coding: utf-8 -*-
"""Offline contracts for parallel dependency-free data pulls (Issue #1126)."""

from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace

from src.services.parallel_data_fetch import (
    FetchBranchStatus,
    FetchTask,
    ParallelFetchLimits,
    is_parallel_fetch_enabled,
    limits_from_config,
    merge_branch_values,
    run_parallel_fetches,
)


class ParallelDataFetchTests(unittest.TestCase):
    def test_global_concurrency_cap_enforced(self) -> None:
        peak = {"n": 0}
        lock = threading.Lock()
        barrier_hold = threading.Event()

        def make_fn(label: str):
            def _fn():
                with lock:
                    # Count threads that have entered before any exit.
                    active = getattr(make_fn, "_active", 0) + 1
                    make_fn._active = active  # type: ignore[attr-defined]
                    peak["n"] = max(peak["n"], active)
                barrier_hold.wait(timeout=2.0)
                with lock:
                    make_fn._active = getattr(make_fn, "_active", 1) - 1  # type: ignore[attr-defined]
                return label

            return _fn

        make_fn._active = 0  # type: ignore[attr-defined]
        tasks = [
            FetchTask(key=f"k{i}", fn=make_fn(f"v{i}"), provider_key=f"p{i}")
            for i in range(6)
        ]
        # Release after a short delay so the pool can fill to the cap.
        def _release():
            time.sleep(0.05)
            barrier_hold.set()

        releaser = threading.Thread(target=_release, daemon=True)
        releaser.start()
        report = run_parallel_fetches(
            tasks,
            enabled=True,
            limits=ParallelFetchLimits(max_concurrent=2, per_provider_limit=8),
        )
        releaser.join(timeout=2.0)
        self.assertEqual(report.mode, "parallel")
        self.assertLessEqual(report.max_in_flight_observed, 2)
        self.assertLessEqual(peak["n"], 2)
        self.assertEqual(list(report.results.keys()), [f"k{i}" for i in range(6)])
        self.assertEqual(
            [branch.value for branch in report.results.values()],
            [f"v{i}" for i in range(6)],
        )

    def test_per_provider_limit_serializes_same_key(self) -> None:
        peak = {"n": 0}
        lock = threading.Lock()
        active = {"n": 0}

        def shared_provider_call():
            with lock:
                active["n"] += 1
                peak["n"] = max(peak["n"], active["n"])
            time.sleep(0.05)
            with lock:
                active["n"] -= 1
            return "ok"

        tasks = [
            FetchTask(key="a", fn=shared_provider_call, provider_key="same"),
            FetchTask(key="b", fn=shared_provider_call, provider_key="same"),
            FetchTask(key="c", fn=shared_provider_call, provider_key="same"),
        ]
        report = run_parallel_fetches(
            tasks,
            enabled=True,
            limits=ParallelFetchLimits(max_concurrent=3, per_provider_limit=1),
        )
        self.assertEqual(peak["n"], 1)
        self.assertTrue(all(branch.ok for branch in report.results.values()))

    def test_failure_isolation_surfaces_typed_gap(self) -> None:
        def ok_branch():
            return {"price": 10}

        def boom():
            raise RuntimeError("provider down")

        report = run_parallel_fetches(
            [
                FetchTask(key="realtime_quote", fn=ok_branch, provider_key="realtime"),
                FetchTask(key="chip_distribution", fn=boom, provider_key="chip"),
                FetchTask(key="fundamental_context", fn=lambda: {"status": "ok"}, provider_key="fundamental"),
            ],
            enabled=True,
            limits=ParallelFetchLimits(max_concurrent=3, per_provider_limit=1),
        )
        self.assertTrue(report.results["realtime_quote"].ok)
        self.assertTrue(report.results["fundamental_context"].ok)
        failed = report.results["chip_distribution"]
        self.assertEqual(failed.status, FetchBranchStatus.ERROR)
        self.assertIsNone(failed.value)
        self.assertEqual(failed.error_code, "parallel_fetch_error")
        self.assertIn("chip_distribution", report.to_diagnostics()["gap_keys"])

    def test_parallel_and_serial_merge_order_and_values_match(self) -> None:
        counter = {"n": 0}
        lock = threading.Lock()

        def make_fn(value: str):
            def _fn():
                with lock:
                    counter["n"] += 1
                # Slight jitter so completion order differs from declaration.
                time.sleep(0.01 if value != "mid" else 0.03)
                return value

            return _fn

        tasks = [
            FetchTask(key="realtime_quote", fn=make_fn("rt"), provider_key="realtime"),
            FetchTask(key="chip_distribution", fn=make_fn("chip"), provider_key="chip"),
            FetchTask(key="fundamental_context", fn=make_fn("mid"), provider_key="fundamental"),
        ]
        limits = ParallelFetchLimits(max_concurrent=3, per_provider_limit=1)
        parallel = run_parallel_fetches(tasks, enabled=True, limits=limits)
        serial = run_parallel_fetches(tasks, enabled=False, limits=limits)

        self.assertEqual(list(parallel.results.keys()), list(serial.results.keys()))
        self.assertEqual(
            list(parallel.values_by_key().values()),
            list(serial.values_by_key().values()),
        )
        self.assertEqual(serial.mode, "serial")
        self.assertEqual(parallel.mode, "parallel")
        merged = merge_branch_values(parallel)
        self.assertEqual(list(merged.keys()), [
            "realtime_quote",
            "chip_distribution",
            "fundamental_context",
        ])

    def test_budget_skips_not_yet_started_branches(self) -> None:
        started = []
        lock = threading.Lock()

        def slow(label: str):
            def _fn():
                with lock:
                    started.append(label)
                time.sleep(0.2)
                return label

            return _fn

        tasks = [
            FetchTask(key="a", fn=slow("a"), provider_key="p1"),
            FetchTask(key="b", fn=slow("b"), provider_key="p2"),
            FetchTask(key="c", fn=slow("c"), provider_key="p3"),
            FetchTask(key="d", fn=slow("d"), provider_key="p4"),
        ]
        report = run_parallel_fetches(
            tasks,
            enabled=True,
            limits=ParallelFetchLimits(
                max_concurrent=1,
                per_provider_limit=1,
                budget_seconds=0.05,
            ),
        )
        self.assertTrue(report.budget_exhausted)
        statuses = {key: branch.status for key, branch in report.results.items()}
        self.assertIn(FetchBranchStatus.BUDGET_SKIPPED, statuses.values())
        # At least one branch should have completed or started; skipped ones never start.
        for key, branch in report.results.items():
            if branch.status is FetchBranchStatus.BUDGET_SKIPPED:
                self.assertFalse(branch.started)
                self.assertIsNone(branch.value)
                self.assertEqual(branch.error_code, "parallel_fetch_budget_skipped")

    def test_none_return_is_gap_not_silent_success(self) -> None:
        report = run_parallel_fetches(
            [FetchTask(key="chip_distribution", fn=lambda: None, provider_key="chip")],
            enabled=True,
        )
        branch = report.results["chip_distribution"]
        self.assertEqual(branch.status, FetchBranchStatus.GAP)
        self.assertFalse(branch.ok)
        self.assertIsNone(branch.value)

    def test_duplicate_keys_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_parallel_fetches(
                [
                    FetchTask(key="x", fn=lambda: 1, provider_key="a"),
                    FetchTask(key="x", fn=lambda: 2, provider_key="b"),
                ]
            )

    def test_limits_from_config_and_enabled_flag(self) -> None:
        cfg = SimpleNamespace(
            analysis_parallel_fetch_enabled=False,
            analysis_parallel_fetch_max_concurrent=2,
            analysis_parallel_fetch_per_provider_limit=1,
            analysis_parallel_fetch_budget_seconds=12.5,
        )
        self.assertFalse(is_parallel_fetch_enabled(cfg))
        limits = limits_from_config(cfg)
        self.assertEqual(limits.max_concurrent, 2)
        self.assertEqual(limits.per_provider_limit, 1)
        self.assertEqual(limits.budget_seconds, 12.5)

        report = run_parallel_fetches(
            [FetchTask(key="only", fn=lambda: "v", provider_key="p")],
            enabled=is_parallel_fetch_enabled(cfg),
            limits=limits,
        )
        self.assertEqual(report.mode, "serial")
        self.assertEqual(report.results["only"].value, "v")


if __name__ == "__main__":
    unittest.main()
