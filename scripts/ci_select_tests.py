#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Map changed repository paths to a selective offline pytest target list.

Used by the PR-tier backend gate so most pull requests avoid a full-suite
run. When mapping is uncertain (shared infrastructure, config, conftest),
the script prints ``FULL`` and exits 0 so the caller falls back to the full
offline suite.

Usage:
  python scripts/ci_select_tests.py --base origin/main
  python scripts/ci_select_tests.py --paths-file <file>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]

# Any of these prefixes force the full offline suite (coverage + complete matrix).
FULL_SUITE_PREFIXES: tuple[str, ...] = (
    "setup.cfg",
    "pyproject.toml",
    "mypy.ini",
    "constraints.txt",
    "build-constraints.txt",
    "requirements.txt",
    ".github/requirements-ci.txt",
    "scripts/ci_gate.sh",
    "scripts/check_coverage_floor.py",
    "scripts/coverage_floor_baseline.json",
    "scripts/check_broad_exceptions.py",
    "scripts/broad_exception_baseline.json",
    "tests/conftest.py",
    "src/config.py",
    "src/config_parts/",
    "src/core/config_registry",
    ".github/workflows/ci.yml",
)

# Longest-prefix path map: changed path prefix → pytest roots (dirs or files).
PATH_TO_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("api/", ("tests/api", "tests/test_error_envelope_contract.py")),
    ("bot/", ("tests/bot", "tests/test_notification.py", "tests/test_notification_sender.py")),
    ("data_provider/", ("tests/data_provider",)),
    ("src/agent/", ("tests/agent", "tests/skill_opinion_outcomes")),
    ("src/services/", ("tests/services",)),
    ("src/repositories/", ("tests/repositories", "tests/services")),
    ("src/schemas/", ("tests/test_api_schema_pydantic.py", "tests/api")),
    ("src/market/", ("tests/services", "tests/test_market_analyzer.py")),
    ("src/migrations/", ("tests/migrations", "tests/test_storage.py")),
    ("src/storage", ("tests/test_storage.py", "tests/storage")),
    ("src/", ("tests/",)),
    ("scripts/", ("tests/scripts", "tests/test_ci_workflow.py")),
    ("tests/", ()),  # filled from the changed path itself
    ("apps/dsa-web/", ()),  # web-only; backend selective returns empty → smoke only
    ("docs/", ()),
    (".github/", ("tests/test_ci_workflow.py",)),
)


def _git_diff_names(base: str) -> list[str] | None:
    merge_base = subprocess.run(
        ["git", "merge-base", "HEAD", base],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if merge_base.returncode != 0 or not merge_base.stdout.strip():
        return None
    ref = merge_base.stdout.strip()
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{ref}...HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _forces_full(path: str) -> bool:
    normalized = path.replace("\\", "/")
    for prefix in FULL_SUITE_PREFIXES:
        if normalized == prefix or normalized.startswith(prefix):
            return True
    return False


def _targets_for_path(path: str) -> set[str]:
    normalized = path.replace("\\", "/")
    if normalized.startswith("tests/") and normalized.endswith(".py"):
        return {normalized}
    for prefix, targets in PATH_TO_TARGETS:
        if normalized == prefix.rstrip("/") or normalized.startswith(prefix):
            return {target for target in targets if target}
    # Unknown top-level paths → full suite for safety.
    return {"FULL"}


def select_targets(paths: Sequence[str]) -> list[str] | str:
    """Return sorted pytest targets, or the string FULL."""
    if not paths:
        return "FULL"
    selected: set[str] = set()
    for path in paths:
        if _forces_full(path):
            return "FULL"
        selected |= _targets_for_path(path)
        if "FULL" in selected:
            return "FULL"
    # Drop missing paths so pytest does not fail collection on stale maps.
    existing = sorted(
        target
        for target in selected
        if (REPO_ROOT / target).exists()
    )
    if not existing:
        # Docs/web-only changes: no backend pytest targets.
        return []
    return existing


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Git base ref for changed-path discovery (default: origin/main)",
    )
    parser.add_argument(
        "--paths-file",
        type=Path,
        help="Optional file listing changed paths (one per line)",
    )
    parser.add_argument(
        "--print-null",
        action="store_true",
        help="Print targets NUL-separated (for xargs -0)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.paths_file is not None:
        paths = [
            line.strip()
            for line in args.paths_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        paths = _git_diff_names(args.base)
        if paths is None:
            # A shallow or otherwise incomplete PR graph cannot safely prove
            # which tests cover the change. Fail closed to the full suite.
            print("FULL")
            return 0
    result = select_targets(paths)
    if result == "FULL":
        print("FULL")
        return 0
    if not result:
        print("NONE")
        return 0
    if args.print_null:
        sys.stdout.write("\0".join(result) + "\0")
    else:
        print(" ".join(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
