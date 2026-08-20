#!/usr/bin/env python3
"""Fail-closed policy for the opt-in PR Review security-check job.

The privileged ``security-check`` path is checkout-free. GitHub Actions
implements it in ``.github/workflows/pr-review.yml`` via ``github-script`` and
the GitHub API. This module is the deterministic Python oracle for the same
predicates so tests can exercise invalid inputs and mutation races without
mocking checkout away.

Inventory is SHA-pinned ``repos.compareCommits(base_sha, head_sha)``.
``pulls.listFiles`` cannot pin a SHA; a re-get equality guard alone does not
close a B→A→B ABA race. Keep the JavaScript fragments below in lockstep with
the workflow script.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterable, Mapping, Sequence
import re

PR_NUMBER_PATTERN = re.compile(r"\A[1-9][0-9]*\Z")
SENSITIVE_PATH_PATTERN = re.compile(
    r"^(\.github/workflows/.*\.yml|\.github/scripts/.*\.py)$"
)
# GitHub compare returns at most 300 files; a full page is treated as truncated.
COMPARE_FILE_LIMIT = 300

# Substrings that must appear in the checkout-free security-check script.
JS_PR_NUMBER_TEST = "/^[1-9][0-9]*$/.test(prNumber)"
JS_PULLS_GET = "github.rest.pulls.get("
JS_COMPARE_COMMITS = "github.rest.repos.compareCommits("
JS_COMPARE_BASE = "base: firstPull.base.sha"
JS_COMPARE_HEAD = "head: firstPull.head.sha"
JS_LIST_FILES = "github.paginate(github.rest.pulls.listFiles"
JS_SENSITIVE_PATTERN = (
    r"/^(\.github\/workflows\/.*\.yml|\.github\/scripts\/.*\.py)$/"
)
JS_DEFAULT_BRANCH_COMPARE = "pull.base.ref === defaultBranch"
JS_FORK_COMPARE = (
    "String(pull.head.repo.id) !== String(context.payload.repository.id)"
)
JS_SNAPSHOT_EQUALITY = (
    "firstPull.head.sha !== secondPull.head.sha || "
    "firstPull.base.sha !== secondPull.base.sha || "
    "firstPull.base.ref !== secondPull.base.ref"
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
    """Return sensitive paths from a SHA-pinned compare filename inventory."""
    sensitive: list[str] = []
    for filename in filenames:
        if not isinstance(filename, str) or not filename:
            raise ValueError("a changed file is missing its filename")
        if SENSITIVE_PATH_PATTERN.fullmatch(filename):
            sensitive.append(filename)
    return sensitive


@dataclass(frozen=True)
class PullRecord:
    """One ``pulls.get`` payload used by the security-check snapshot."""

    head_sha: str
    base_sha: str
    base_ref: str
    head_repo_id: object
    head_owner_login: str


@dataclass(frozen=True)
class SecuritySnapshot:
    """Outputs emitted only after a verified SHA-pinned inventory."""

    is_fork: bool
    is_default_branch: bool
    base_sha: str
    head_sha: str
    filenames: tuple[str, ...]
    sensitive_files: tuple[str, ...]
    safe_to_run: bool


def require_pull_metadata(pull: PullRecord | None) -> PullRecord:
    """Fail closed when head/base SHAs, ref, repo id, or owner login are missing."""
    if pull is None:
        raise ValueError("pull request is missing head or base metadata")
    if (
        not pull.head_sha
        or not pull.base_sha
        or not pull.base_ref
        or pull.head_repo_id is None
        or not pull.head_owner_login
    ):
        raise ValueError("pull request is missing head or base metadata")
    return pull


def compare_head_spec(pull: PullRecord, _repository_id: object) -> str:
    """Return the compare head pin: the captured commit SHA.

    GitHub's compare ``basehead`` fork qualifier is documented as
    ``USERNAME:BRANCH``, which is mutable. The same endpoint description
    allows commit SHAs in the same repository network, so this oracle pins
    ``pulls.get`` ``head.sha`` with no owner-colon prefix.
    """
    return pull.head_sha


@dataclass
class MutatingPullsApi:
    """Test double: ``get`` follows a mutable timeline; ``compare`` is SHA-keyed.

    ``list_files`` models unpinned ``pulls.listFiles`` and must not be consulted
    by ``capture_security_snapshot``. Call counts make that contract testable.
    """

    get_timeline: list[PullRecord | BaseException]
    compare_files: Mapping[tuple[str, str], Sequence[object] | BaseException]
    list_files_timeline: list[Sequence[object] | BaseException] = field(default_factory=list)
    truncated_compares: set[tuple[str, str]] = field(default_factory=set)
    get_calls: int = 0
    compare_calls: list[tuple[str, str]] = field(default_factory=list)
    list_files_calls: int = 0

    def get(self) -> PullRecord:
        self.get_calls += 1
        if not self.get_timeline:
            raise ValueError("Unable to read pull request: unknown")
        item = self.get_timeline.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def compare(self, base_sha: str, head_spec: str) -> list[object]:
        key = (base_sha, head_spec)
        self.compare_calls.append(key)
        if key not in self.compare_files:
            raise ValueError("Unable to compare pinned SHAs: unknown")
        item = self.compare_files[key]
        if isinstance(item, BaseException):
            raise item
        files = list(item)
        if key in self.truncated_compares or len(files) >= COMPARE_FILE_LIMIT:
            raise ValueError("Unable to compare pinned SHAs: file inventory is truncated")
        return files

    def list_files(self) -> list[object]:
        """Unpinned current PR files. Security snapshot must not call this."""
        self.list_files_calls += 1
        if not self.list_files_timeline:
            raise ValueError("Unable to list files: unknown")
        item = self.list_files_timeline.pop(0)
        if isinstance(item, BaseException):
            raise item
        return list(item)


def capture_security_snapshot(
    *,
    pr_number: object,
    default_branch: object,
    repository_id: object,
    api: MutatingPullsApi,
) -> SecuritySnapshot:
    """Mirror the workflow snapshot: get → SHA-pinned compare → re-get equality.

    Outputs are produced only after the second get matches the first. File
    inventory comes from ``compare(first.base_sha, pinned head)``, not from
    unpinned ``listFiles``. Re-get equality fail-closes non-returning drift; it
    is not what binds inventory to checkout SHAs under B→A→B ABA.
    """
    parse_pr_number(pr_number)
    if not isinstance(default_branch, str) or not default_branch:
        raise ValueError("repository default branch is unavailable")
    if repository_id is None:
        raise ValueError("repository metadata is unavailable")

    first = require_pull_metadata(api.get())
    head_spec = compare_head_spec(first, repository_id)
    filenames = api.compare(first.base_sha, head_spec)
    if len(filenames) >= COMPARE_FILE_LIMIT:
        raise ValueError("Unable to compare pinned SHAs: file inventory is truncated")
    sensitive = tuple(sensitive_changed_files(filenames))

    second = require_pull_metadata(api.get())
    if (
        first.head_sha != second.head_sha
        or first.base_sha != second.base_sha
        or first.base_ref != second.base_ref
        or str(first.head_repo_id) != str(second.head_repo_id)
    ):
        raise ValueError("pull request changed during the API snapshot")

    return SecuritySnapshot(
        is_fork=classify_fork(head_repo_id=second.head_repo_id, repository_id=repository_id),
        is_default_branch=classify_default_branch_target(
            base_ref=second.base_ref, default_branch=default_branch
        ),
        base_sha=second.base_sha,
        head_sha=second.head_sha,
        filenames=tuple(str(name) for name in filenames),
        sensitive_files=sensitive,
        safe_to_run=True,
    )
