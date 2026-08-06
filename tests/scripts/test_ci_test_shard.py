# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for duration-balanced CI sharding."""

from __future__ import annotations

from scripts.ci_test_shard import discover_test_files, partition_test_files


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
