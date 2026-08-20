#!/usr/bin/env python3
"""Fail-closed policy for the opt-in PR Review security-check job.

The privileged ``security-check`` path is checkout-free. GitHub Actions
implements it in ``.github/workflows/pr-review.yml`` via ``github-script`` and
the Pulls API. This module is the deterministic Python oracle for the same
predicates so tests can exercise invalid inputs without mocking checkout or
the GitHub API away.

Keep the JavaScript fragments below in lockstep with the workflow scripts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

PR_NUMBER_PATTERN = re.compile(r"\A[1-9][0-9]*\Z")
SENSITIVE_PATH_PATTERN = re.compile(
    r"^(\.github/workflows/.*\.yml|\.github/scripts/.*\.py)$"
)

# Substrings that must appear in the checkout-free security-check scripts.
JS_PR_NUMBER_TEST = "/^[1-9][0-9]*$/.test(prNumber)"
JS_PULLS_GET = "github.rest.pulls.get("
JS_LIST_FILES = "github.paginate(github.rest.pulls.listFiles"
JS_SENSITIVE_PATTERN = (
    r"/^(\.github\/workflows\/.*\.yml|\.github\/scripts\/.*\.py)$/"
)
JS_DEFAULT_BRANCH_COMPARE = "pull.base.ref === defaultBranch"
JS_FORK_COMPARE = (
    "String(pull.head.repo.id) !== String(context.payload.repository.id)"
)


def parse_pr_number(raw: object) -> int:
    """Return a positive integer PR number or raise for any other value."""
    if not isinstance(raw, str) or PR_NUMBER_PATTERN.fullmatch(raw) is None:
        raise ValueError("workflow_dispatch requires a positive integer pr_number")
    return int(raw)


def classify_fork(*, head_repo_id: object, repository_id: object) -> bool:
    """Classify a fork from API repository ids; missing ids fail closed."""
    if head_repo_id is None or repository_id is None:
        raise ValueError("repository metadata is unavailable")
    return str(head_repo_id) != str(repository_id)


def classify_default_branch_target(*, base_ref: object, default_branch: object) -> bool:
    """Match the PR base ref to the default branch with exact, case-sensitive equality."""
    if not isinstance(base_ref, str) or not base_ref:
        raise ValueError("pull request is missing head or base metadata")
    if not isinstance(default_branch, str) or not default_branch:
        raise ValueError("repository default branch is unavailable")
    return base_ref == default_branch


def sensitive_changed_files(filenames: Iterable[object]) -> list[str]:
    """Return sensitive paths from a Pulls ``listFiles`` filename inventory."""
    sensitive: list[str] = []
    for filename in filenames:
        if not isinstance(filename, str) or not filename:
            raise ValueError("a changed file is missing its filename")
        if SENSITIVE_PATH_PATTERN.fullmatch(filename):
            sensitive.append(filename)
    return sensitive
