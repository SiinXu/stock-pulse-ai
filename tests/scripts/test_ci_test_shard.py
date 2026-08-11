# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for duration-balanced CI sharding."""

from __future__ import annotations

import json

import pytest

from scripts.ci_test_shard import (
    discover_test_files,
    load_durations,
    partition_test_files,
)


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
