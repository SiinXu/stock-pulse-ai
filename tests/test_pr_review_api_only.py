# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Guards for the checkout-free, API-only PR Review security-check contract."""

from __future__ import annotations

import pytest
import yaml

from scripts.check_workflow_supply_chain import (
    DEFAULT_EXCEPTIONS,
    ROOT,
    check_repository,
)
from scripts.pr_review_security_policy import (
    JS_DEFAULT_BRANCH_COMPARE,
    JS_FORK_COMPARE,
    JS_LIST_FILES,
    JS_PR_NUMBER_TEST,
    JS_PULLS_GET,
    JS_SENSITIVE_PATTERN,
    classify_default_branch_target,
    classify_fork,
    parse_pr_number,
    sensitive_changed_files,
)


WORKFLOW_PATH = ROOT / ".github" / "workflows" / "pr-review.yml"


def _load_workflow() -> dict[object, object]:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _security_check_job() -> dict[str, object]:
    document = _load_workflow()
    jobs = document["jobs"]
    assert isinstance(jobs, dict)
    job = jobs["security-check"]
    assert isinstance(job, dict)
    return job


def _security_scripts() -> dict[str, str]:
    job = _security_check_job()
    steps = job["steps"]
    assert isinstance(steps, list)
    scripts: dict[str, str] = {}
    for step in steps:
        assert isinstance(step, dict)
        step_id = step["id"]
        assert isinstance(step_id, str)
        with_block = step["with"]
        assert isinstance(with_block, dict)
        script = with_block["script"]
        assert isinstance(script, str)
        scripts[step_id] = script
    return scripts


def test_pr_review_dispatch_requires_pr_number() -> None:
    document = _load_workflow()
    # PyYAML 1.1 treats the key `on` as boolean True.
    on_block = document.get("on", document.get(True))
    assert on_block is not None
    assert list(on_block) == ["workflow_dispatch"]
    pr_number = on_block["workflow_dispatch"]["inputs"]["pr_number"]
    assert pr_number["required"] is True
    assert pr_number["type"] == "string"


def test_security_check_is_checkout_free_and_api_only() -> None:
    job = _security_check_job()
    steps = job["steps"]
    assert isinstance(steps, list)
    assert [step["id"] for step in steps] == ["trust", "check_sensitive"]
    for step in steps:
        assert "run" not in step
        uses = step["uses"]
        assert uses.startswith("actions/github-script@")
        assert "actions/checkout@" not in uses
        blob = uses + "\n" + step["with"]["script"]
        assert "git diff" not in blob
        assert "git fetch" not in blob
        assert "git checkout" not in blob
        assert "git clone" not in blob
        assert JS_PR_NUMBER_TEST in step["with"]["script"]

    scripts = _security_scripts()
    assert JS_PULLS_GET in scripts["trust"]
    assert JS_FORK_COMPARE in scripts["trust"]
    assert JS_DEFAULT_BRANCH_COMPARE in scripts["trust"]
    assert "toLowerCase()" not in scripts["trust"]
    assert JS_LIST_FILES in scripts["check_sensitive"]
    assert JS_SENSITIVE_PATTERN in scripts["check_sensitive"]
    assert "core.setFailed(`Unable to read pull request ${prNumber}: ${status}`)" in scripts["trust"]
    assert "core.setFailed(`Unable to list files for pull request ${prNumber}: ${status}`)" in scripts[
        "check_sensitive"
    ]


def test_pr_review_workflow_supply_chain_contract() -> None:
    errors = check_repository(ROOT, ROOT / ".github" / "workflows", DEFAULT_EXCEPTIONS)
    assert errors == []


@pytest.mark.parametrize(
    "raw",
    ["", "0", "-1", "01", "1.5", "1a", "+1", " 1", "1 ", "pr-1", "1\n"],
)
def test_parse_pr_number_fails_closed(raw: str) -> None:
    with pytest.raises(ValueError, match="positive integer pr_number"):
        parse_pr_number(raw)


@pytest.mark.parametrize("raw, expected", [("1", 1), ("42", 42), ("1422", 1422)])
def test_parse_pr_number_accepts_positive_integers(raw: str, expected: int) -> None:
    assert parse_pr_number(raw) == expected


def test_classify_fork_and_default_branch_from_api_metadata() -> None:
    assert classify_fork(head_repo_id=2, repository_id=1) is True
    assert classify_fork(head_repo_id="1", repository_id=1) is False
    with pytest.raises(ValueError, match="repository metadata"):
        classify_fork(head_repo_id=None, repository_id=1)

    assert classify_default_branch_target(base_ref="main", default_branch="main") is True
    assert classify_default_branch_target(base_ref="MAIN", default_branch="main") is False
    with pytest.raises(ValueError, match="default branch"):
        classify_default_branch_target(base_ref="main", default_branch="")
    with pytest.raises(ValueError, match="head or base metadata"):
        classify_default_branch_target(base_ref="", default_branch="main")


def test_sensitive_changed_files_uses_local_regex_on_api_filenames() -> None:
    assert sensitive_changed_files(
        [
            ".github/workflows/pr-review.yml",
            ".github/workflows/ci.yaml",
            ".github/scripts/ai_review.py",
            "src/api/main.py",
            "docs/CONTRIBUTING.md",
        ]
    ) == [
        ".github/workflows/pr-review.yml",
        ".github/scripts/ai_review.py",
    ]
    with pytest.raises(ValueError, match="missing its filename"):
        sensitive_changed_files([""])
    with pytest.raises(ValueError, match="missing its filename"):
        sensitive_changed_files([None])
