#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Map changed repository paths to a selective offline pytest target list.

Used by the PR-tier backend planner and selective job so most pull requests
avoid a full-suite run. The mapper fails closed to ``FULL`` when:

- mapping is uncertain (shared infrastructure, config, conftest)
- the merge-base cannot be proven
- a changed path matches no mapping
- a ``tests/`` path is not a collectable ``test_*.py`` module
- a mapping is an empty tuple outside ``NONE_PREFIXES``
- a mapping's targets are all missing or its globs match nothing

Hosted CI must schedule the four ``backend-tests`` shards for ``FULL``;
``offline-tests-selective`` refuses to run the unsharded suite. ``NONE`` is
allowed only for the explicit ``NONE_PREFIXES`` allowlist (``docs/`` and
``apps/dsa-web/``) excluding ``BACKEND_WEB_CONTRACT_PREFIXES`` (the
``backend_web_contract`` paths in ``.github/workflows/ci.yml``). Those
shared web/runtime files map to the backend tests that cover the contract.
Any other empty selection is ``FULL``.

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

# CLI ``NONE`` (empty pytest target list) is allowed only for these prefixes.
# Empty-tuple mappings outside this allowlist fail closed to ``FULL``.
# ``BACKEND_WEB_CONTRACT_PREFIXES`` live under ``apps/dsa-web/`` but are not
# NONE: they are the ``backend_web_contract`` filter in ci.yml.
NONE_PREFIXES: tuple[str, ...] = (
    "apps/dsa-web/",
    "docs/",
)

# Same path set as ci.yml ``backend_web_contract``. Longer prefixes listed
# before ``apps/dsa-web/`` in ``PATH_TO_TARGETS`` so first-match cannot yield
# NONE. Keep this tuple in lockstep with that YAML filter.
BACKEND_WEB_CONTRACT_PREFIXES: tuple[str, ...] = (
    "apps/dsa-web/public/",
    "apps/dsa-web/src/components/settings/llmProviderTemplates.ts",
    "apps/dsa-web/src/locales/settingsHelp.ts",
    "apps/dsa-web/src/locales/settingsHelp.en.ts",
    "apps/dsa-web/src/locales/settingsHelp.zh.ts",
    "apps/dsa-web/src/utils/systemConfigI18n.ts",
)

# First-match path map: longer prefixes must be listed before shorter ones
# (for example src/bot/ before src/). Changed path prefix → pytest roots.
PATH_TO_TARGETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("src/api/", ("tests/api", "tests/test_error_envelope_contract.py")),
    ("src/bot/", ("tests/bot", "tests/test_notification.py", "tests/test_notification_sender.py")),
    (
        "src/data_provider/",
        ("tests/data_provider", "tests/contract/test_provider_fallback.py"),
    ),
    (
        "src/agent/",
        ("tests/agent", "tests/skill_opinion_outcomes", "tests/test_agent_*.py"),
    ),
    ("src/services/diagnostics/", (
        "tests/test_run_diagnostics_p1.py",
        "tests/test_run_diagnostics_p2.py",
        "tests/services",
    )),
    ("src/services/run_diagnostics.py", (
        "tests/test_run_diagnostics_p1.py",
        "tests/test_run_diagnostics_p2.py",
        "tests/services",
    )),
    ("src/services/", ("tests/services",)),
    ("src/repositories/", ("tests/repositories", "tests/services")),
    ("src/schemas/", ("tests/schemas", "tests/test_api_schema_pydantic.py", "tests/api")),
    (
        "src/market/",
        (
            "tests/market",
            "tests/services",
            "tests/test_exception_log_callsite_guard.py",
        ),
    ),
    (
        "src/migrations/",
        (
            "tests/test_schema_migrations.py",
            "tests/test_migration_cli_readonly.py",
            "tests/test_approval_migration.py",
            "tests/test_investment_framework_migration.py",
            "tests/test_storage.py",
        ),
    ),
    ("src/storage", ("tests/test_storage.py", "tests/storage")),
    ("src/", ("tests/",)),
    ("scripts/", ("tests/scripts", "tests/test_ci_workflow.py")),
    (
        "apps/dsa-web/public/",
        (
            "tests/data/test_stock_index_loader.py",
            "tests/test_generate_index_from_csv.py",
        ),
    ),
    (
        "apps/dsa-web/src/components/settings/llmProviderTemplates.ts",
        (
            "tests/test_daily_analysis_workflow_llm_env.py",
            "tests/test_provider_catalog.py",
        ),
    ),
    (
        "apps/dsa-web/src/locales/settingsHelp.ts",
        (
            "tests/scripts/test_merge_resolvers.py",
            "tests/test_config_registry.py",
        ),
    ),
    (
        "apps/dsa-web/src/locales/settingsHelp.en.ts",
        (
            "tests/scripts/test_merge_resolvers.py",
            "tests/test_config_registry.py",
        ),
    ),
    (
        "apps/dsa-web/src/locales/settingsHelp.zh.ts",
        (
            "tests/scripts/test_merge_resolvers.py",
            "tests/test_config_registry.py",
        ),
    ),
    (
        "apps/dsa-web/src/utils/systemConfigI18n.ts",
        ("tests/test_config_registry.py",),
    ),
    ("apps/dsa-web/", ()),  # remaining web-only; backend selective returns empty → smoke only
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


def _matches_prefix(path: str, prefix: str) -> bool:
    return path == prefix.rstrip("/") or path.startswith(prefix)


def _forces_full(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(_matches_prefix(normalized, prefix) for prefix in FULL_SUITE_PREFIXES)


def _is_backend_web_contract(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(
        _matches_prefix(normalized, prefix) for prefix in BACKEND_WEB_CONTRACT_PREFIXES
    )


def _is_none_allowlisted(path: str) -> bool:
    normalized = path.replace("\\", "/")
    # Shared web/runtime contracts must not use the apps/dsa-web/ NONE map.
    if _is_backend_web_contract(normalized):
        return False
    return any(_matches_prefix(normalized, prefix) for prefix in NONE_PREFIXES)


def _is_collectable_pytest_module(path: str) -> bool:
    filename = path.rsplit("/", 1)[-1]
    return path.endswith(".py") and filename.startswith("test_")


def _is_glob(target: str) -> bool:
    return any(char in target for char in "*?[")


def _expand_target(target: str) -> set[str]:
    """Resolve one mapping target against the repo root.

    Literal paths are returned as-is. Glob patterns are expanded so a pattern
    cannot survive as a non-existent pytest argument.
    """
    if not target:
        return set()
    if not _is_glob(target):
        return {target}
    return {
        str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for path in REPO_ROOT.glob(target)
    }


def _targets_for_path(path: str) -> set[str]:
    normalized = path.replace("\\", "/")
    if normalized.startswith("tests/"):
        # Pytest only collects ``test_*.py`` in this repository. Helper
        # modules, nested conftest, fixtures, SQL/JSON/images, and other
        # support files can affect many consumers. Passing one of them as
        # the sole explicit target collects zero tests (pytest exit 5) or
        # skips the consumers. Their dependency surface is not encoded in
        # this lightweight mapper, so fail closed to the full suite.
        if _is_collectable_pytest_module(normalized):
            return {normalized}
        return {"FULL"}
    for prefix, targets in PATH_TO_TARGETS:
        if not _matches_prefix(normalized, prefix):
            continue
        selected = {target for target in targets if target}
        if selected:
            return selected
        # Empty mapping is NONE only on the explicit allowlist.
        if _is_none_allowlisted(normalized):
            return set()
        return {"FULL"}
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
    mapped_any = bool(selected)
    expanded: set[str] = set()
    for target in selected:
        expanded |= _expand_target(target)
        if "FULL" in expanded:
            return "FULL"
    # Drop missing extras so pytest does not fail collection on a stale sibling
    # target. If every mapped target is missing or every glob matched nothing,
    # fail closed to the full suite rather than selecting nothing.
    existing = sorted(
        target
        for target in expanded
        if (REPO_ROOT / target).exists()
    )
    if not existing:
        if mapped_any:
            return "FULL"
        # Empty selection is NONE only when every path is on the allowlist.
        if paths and all(_is_none_allowlisted(path) for path in paths):
            return []
        return "FULL"
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
