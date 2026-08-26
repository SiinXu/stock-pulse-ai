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

# Immutable equal-weight model of hosted run 32963128085 empty-duration packing.
# Not live discovery and not .github/ci-test-durations.json keys.
_EMPTY_DURATION_HOTSPOT = "tests/test_exception_log_callsite_guard.py"
_EMPTY_DURATION_SIBLING = "tests/test_broad_exception_guard.py"
_EMPTY_DURATION_HISTORICAL_FILES = (
    "tests/frozen_empty_duration/test_early_a.py",
    "tests/frozen_empty_duration/test_early_b.py",
    "tests/frozen_empty_duration/test_early_c.py",
    _EMPTY_DURATION_SIBLING,
    "tests/test_core_placeholder_a.py",
    "tests/test_core_placeholder_b.py",
    "tests/test_core_placeholder_c.py",
    _EMPTY_DURATION_HOTSPOT,
)
_EMPTY_DURATION_HISTORICAL_OVERHEAD = 1.0
_EMPTY_DURATION_REFRESH_EXTRAS = (
    "tests/repositories/test_layered_memory_repo.py",
    "tests/schemas/test_layered_memory_persist.py",
    "tests/services/test_layered_memory_collection_service.py",
)
_EMPTY_DURATION_HOTSPOT_ADJACENT = (
    "tests/test_exception_aaa.py",
    "tests/test_exception_bbb.py",
    "tests/test_exception_ccc.py",
)


def _empty_duration_groups(files, overhead: float = _EMPTY_DURATION_HISTORICAL_OVERHEAD):
    groups, _totals = partition_test_files(
        files, {}, splits=4, initial_totals=[overhead, 0.0, 0.0, 0.0]
    )
    return groups


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
    """Equal 1.0 weights recreate the 32963128085 shard-1 timeout assignment."""

    groups = _empty_duration_groups(_EMPTY_DURATION_HISTORICAL_FILES)
    shard_one = set(groups[0])
    assert _EMPTY_DURATION_HOTSPOT in shard_one
    assert _EMPTY_DURATION_SIBLING in shard_one
    assert len(groups[0]) > 1


def test_empty_duration_refresh_inventory_does_not_change_frozen_reconstruction() -> None:
    """Duration-key refresh must not become the historical packing source."""

    frozen = _empty_duration_groups(_EMPTY_DURATION_HISTORICAL_FILES)
    assert _EMPTY_DURATION_HOTSPOT in frozen[0]
    assert _EMPTY_DURATION_SIBLING in frozen[0]

    shifted = _empty_duration_groups(
        [*_EMPTY_DURATION_HISTORICAL_FILES, *_EMPTY_DURATION_REFRESH_EXTRAS]
    )
    shifted_hot = next(group for group in shifted if _EMPTY_DURATION_HOTSPOT in group)
    assert _EMPTY_DURATION_HOTSPOT not in shifted[0]
    assert len(shifted_hot) > 1

    assert _empty_duration_groups(_EMPTY_DURATION_HISTORICAL_FILES) == frozen


def test_empty_duration_hotspot_adjacent_names_keep_hotspot_packed() -> None:
    """Sibling colocation is not a live empty-map invariant."""

    groups = _empty_duration_groups(
        [*_EMPTY_DURATION_HISTORICAL_FILES, *_EMPTY_DURATION_HOTSPOT_ADJACENT]
    )
    hot = next(group for group in groups if _EMPTY_DURATION_HOTSPOT in group)
    assert len(hot) > 1
    assert _EMPTY_DURATION_SIBLING not in hot
    assert _EMPTY_DURATION_HOTSPOT not in groups[0]


def test_empty_duration_live_hotspot_is_not_isolated() -> None:
    live_groups, _live_totals = partition_test_files(
        discover_test_files(), {}, splits=4, initial_totals=[30.0, 0.0, 0.0, 0.0]
    )
    live_hot = next(group for group in live_groups if _EMPTY_DURATION_HOTSPOT in group)
    assert len(live_hot) > 1


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
