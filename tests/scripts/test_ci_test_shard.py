# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for duration-balanced CI sharding."""

from __future__ import annotations

import json
import statistics

import pytest

from scripts.ci_test_shard import (
    BACKEND_FIRST_SHARD_OVERHEAD_SECONDS,
    discover_test_files,
    load_durations,
    partition_test_files,
)

# Committed weights must stay useful, but new modules may use median fallback
# until a hosted run refreshes .github/ci-test-durations.json.
MIN_KNOWN_DURATION_COVERAGE = 0.95


def test_partition_covers_all_modules_exactly_once() -> None:
    files = ["tests/a/test_a.py", "tests/b/test_b.py", "tests/c/test_c.py", "tests/d/test_d.py"]
    durations = {
        "tests/a/test_a.py": 10.0,
        "tests/b/test_b.py": 1.0,
        "tests/c/test_c.py": 5.0,
        "tests/d/test_d.py": 5.0,
    }
    groups, totals = partition_test_files(files, durations, splits=2)
    flat = [path for group in groups for path in group]
    assert sorted(flat) == sorted(files)
    assert all(total > 0 for total in totals)
    assert len(groups) == 2


def test_discover_finds_repo_tests() -> None:
    found = discover_test_files()
    assert found
    assert all(path.startswith("tests/") and path.endswith(".py") for path in found)


def test_greedy_partition_isolates_a_dominant_module() -> None:
    files = [
        "tests/test_a.py",
        "tests/test_b.py",
        "tests/test_c.py",
        "tests/test_hot.py",
    ]
    durations = {
        "tests/test_a.py": 10.0,
        "tests/test_b.py": 10.0,
        "tests/test_c.py": 10.0,
        "tests/test_hot.py": 900.0,
    }
    groups, totals = partition_test_files(files, durations, splits=4)
    hot_index = next(i for i, group in enumerate(groups) if "tests/test_hot.py" in group)
    assert groups[hot_index] == ["tests/test_hot.py"]
    assert totals[hot_index] == 900.0
    flat = [path for group in groups for path in group]
    assert sorted(flat) == sorted(files)


def test_empty_duration_fallback_colocates_hosted_shard_one_hotspots() -> None:
    """Equal 1.0 weights recreate the 32963128085 shard-1 timeout assignment.

    Lock the counterexample to the committed duration snapshot. Unknown
    modules may use median fallback before a hosted refresh; they must not
    shift this empty-map assignment. An alphabetically early extra file is
    the deterministic counterexample (PR #1527 ``tests/agent/test_red_team.py``).
    """

    snapshot = load_durations()
    assert snapshot, "empty duration weights regress to the equal-1.0 shard-1 timeout"
    files = [path for path in discover_test_files() if path in snapshot]
    groups, _totals = partition_test_files(
        files, {}, splits=4, initial_totals=[30.0, 0.0, 0.0, 0.0]
    )
    shard_one = set(groups[0])
    assert "tests/test_exception_log_callsite_guard.py" in shard_one
    assert "tests/test_broad_exception_guard.py" in shard_one

    shifted_groups, _shifted_totals = partition_test_files(
        [*files, "tests/agent/test_unknown_new.py"],
        {},
        splits=4,
        initial_totals=[30.0, 0.0, 0.0, 0.0],
    )
    assert "tests/test_exception_log_callsite_guard.py" not in set(shifted_groups[0])


def test_unknown_module_receives_median_weight_and_is_assigned_once() -> None:
    files = [
        "tests/test_a.py",
        "tests/test_b.py",
        "tests/test_c.py",
        "tests/test_unknown_new.py",
    ]
    durations = {
        "tests/test_a.py": 10.0,
        "tests/test_b.py": 20.0,
        "tests/test_c.py": 30.0,
    }
    median = statistics.median(durations.values())
    groups, totals = partition_test_files(files, durations, splits=4)
    explicit_groups, explicit_totals = partition_test_files(
        files, {**durations, "tests/test_unknown_new.py": median}, splits=4
    )
    assigned = [path for group in groups for path in group]
    assert assigned.count("tests/test_unknown_new.py") == 1
    assert sorted(assigned) == sorted(files)
    assert groups == explicit_groups
    assert totals == explicit_totals


def test_committed_durations_cover_modules_and_fit_backend_job_bound() -> None:
    files = discover_test_files()
    durations = load_durations()
    assert durations, "empty duration weights regress to the equal-1.0 shard-1 timeout"
    known = [path for path in files if path in durations]
    assert len(known) / len(files) >= MIN_KNOWN_DURATION_COVERAGE
    assert durations["tests/test_exception_log_callsite_guard.py"] >= 600.0

    groups, totals = partition_test_files(
        files,
        durations,
        splits=4,
        initial_totals=[BACKEND_FIRST_SHARD_OVERHEAD_SECONDS, 0.0, 0.0, 0.0],
    )
    covered = [path for group in groups for path in group]
    assert sorted(covered) == sorted(files)
    assert len(covered) == len(set(covered))
    assert all(group for group in groups)
    assert max(totals) < 20 * 60
    hot_shard = next(
        group for group in groups if "tests/test_exception_log_callsite_guard.py" in group
    )
    assert hot_shard == ["tests/test_exception_log_callsite_guard.py"]


def test_partition_is_deterministic_and_accounts_for_first_shard_overhead() -> None:
    files = ["tests/test_c.py", "tests/test_a.py", "tests/test_b.py"]
    durations = {path: 10.0 for path in files}

    first = partition_test_files(files, durations, splits=2, initial_totals=[15.0, 0.0])
    second = partition_test_files(
        list(reversed(files)), durations, splits=2, initial_totals=[15.0, 0.0]
    )

    assert first == second
    assert first[1][0] == 25.0
    assert first[0][0] == ["tests/test_c.py"]


@pytest.mark.parametrize("duration", [True, 0, -1, float("nan"), float("inf")])
def test_load_durations_rejects_non_positive_or_non_finite_values(
    tmp_path, duration: object
) -> None:
    path = tmp_path / "durations.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "durations": {"tests/test_example.py": duration},
            },
            allow_nan=True,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid duration"):
        load_durations(path)


@pytest.mark.parametrize("total", [True, -1, float("nan"), float("inf")])
def test_partition_rejects_invalid_initial_totals(total: object) -> None:
    with pytest.raises(ValueError, match="initial_totals"):
        partition_test_files(
            ["tests/test_example.py"],
            {},
            splits=1,
            initial_totals=[total],
        )
