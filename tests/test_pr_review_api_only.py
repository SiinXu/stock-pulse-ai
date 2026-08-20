# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Guards for the checkout-free, SHA-pinned PR Review security-check contract."""

from __future__ import annotations

import pytest
import yaml

from scripts.check_workflow_supply_chain import (
    DEFAULT_EXCEPTIONS,
    ROOT,
    check_repository,
)
from scripts.pr_review_security_policy import (
    COMPARE_FILE_LIMIT,
    JS_COMPARE_BASE,
    JS_COMPARE_COMMITS,
    JS_DEFAULT_BRANCH_COMPARE,
    JS_FORK_COMPARE,
    JS_LIST_FILES,
    JS_PR_NUMBER_TEST,
    JS_PULLS_GET,
    JS_SENSITIVE_PATTERN,
    JS_SNAPSHOT_EQUALITY,
    MutatingPullsApi,
    PullRecord,
    capture_security_snapshot,
    classify_default_branch_target,
    classify_fork,
    parse_pr_number,
    sensitive_changed_files,
)


WORKFLOW_PATH = ROOT / ".github" / "workflows" / "pr-review.yml"
SENSITIVE_PATH = ".github/workflows/pr-review.yml"
SAFE_PATH = "README.md"
BASE_SHA = "base-sha"
HEAD_A = "head-safe-a"
HEAD_B = "head-sensitive-b"


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


def _pull(head_sha: str, *, base_sha: str = BASE_SHA, base_ref: str = "main", repo_id: object = 1) -> PullRecord:
    return PullRecord(
        head_sha=head_sha,
        base_sha=base_sha,
        base_ref=base_ref,
        head_repo_id=repo_id,
        head_owner_login="SiinXu",
    )


def _snapshot(
    api: MutatingPullsApi,
    *,
    pr_number: str = "1426",
    default_branch: str = "main",
    repository_id: object = 1,
):
    return capture_security_snapshot(
        pr_number=pr_number,
        default_branch=default_branch,
        repository_id=repository_id,
        api=api,
    )


def test_pr_review_dispatch_requires_pr_number() -> None:
    document = _load_workflow()
    # PyYAML 1.1 treats the key `on` as boolean True.
    on_block = document.get("on", document.get(True))
    assert on_block is not None
    assert list(on_block) == ["workflow_dispatch"]
    pr_number = on_block["workflow_dispatch"]["inputs"]["pr_number"]
    assert pr_number["required"] is True
    assert pr_number["type"] == "string"


def test_security_check_is_checkout_free_sha_pinned_snapshot() -> None:
    job = _security_check_job()
    assert job["permissions"] == {"contents": "read", "pull-requests": "read"}
    outputs = job["outputs"]
    assert isinstance(outputs, dict)
    assert outputs["base_sha"] == "${{ steps.snapshot.outputs.base_sha }}"
    assert outputs["head_sha"] == "${{ steps.snapshot.outputs.head_sha }}"
    assert outputs["safe_to_run"] == "${{ steps.snapshot.outputs.safe_to_run }}"
    steps = job["steps"]
    assert isinstance(steps, list)
    assert [step["id"] for step in steps] == ["snapshot"]
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
    snapshot = scripts["snapshot"]
    assert snapshot.count(JS_PULLS_GET) == 2
    assert JS_COMPARE_COMMITS in snapshot
    assert JS_COMPARE_BASE in snapshot
    assert JS_LIST_FILES not in snapshot
    assert JS_SNAPSHOT_EQUALITY in snapshot
    assert JS_FORK_COMPARE in snapshot
    assert JS_DEFAULT_BRANCH_COMPARE in snapshot
    assert "core.setOutput('base_sha', pull.base.sha);" in snapshot
    assert "core.setOutput('head_sha', pull.head.sha);" in snapshot
    assert "github.sha" not in snapshot
    assert "toLowerCase()" not in snapshot
    assert JS_SENSITIVE_PATTERN in snapshot
    assert "core.setFailed(`Unable to read pull request ${prNumber}: ${status}`)" in snapshot
    assert (
        "core.setFailed(`Unable to compare pinned SHAs for pull request ${prNumber}: ${status}`)"
        in snapshot
    )
    assert snapshot.index(JS_COMPARE_COMMITS) < snapshot.index("secondResponse")
    sha_outputs_index = snapshot.index("core.setOutput('base_sha', pull.base.sha);")
    equality_index = snapshot.index(JS_SNAPSHOT_EQUALITY)
    assert equality_index < sha_outputs_index


def test_ai_review_checkouts_use_api_shas_without_dispatch_fallback() -> None:
    document = _load_workflow()
    jobs = document["jobs"]
    assert isinstance(jobs, dict)
    ai_review = jobs["ai-review"]
    assert isinstance(ai_review, dict)
    steps = {step["id"]: step for step in ai_review["steps"]}
    trusted_ref = steps["trusted-review-inputs"]["with"]["ref"]
    analysis_ref = steps["pull-request-analysis-inputs"]["with"]["ref"]
    assert trusted_ref == "${{ needs.security-check.outputs.base_sha }}"
    assert analysis_ref == "${{ needs.security-check.outputs.head_sha }}"
    assert "github.sha" not in trusted_ref
    assert "github.sha" not in analysis_ref
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "github.event.pull_request.head.sha || github.sha" not in workflow_text
    assert "github.event.pull_request.base.sha || github.sha" not in workflow_text


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


def test_unchanged_success_uses_sha_pinned_compare_not_list_files() -> None:
    api = MutatingPullsApi(
        get_timeline=[_pull(HEAD_A), _pull(HEAD_A)],
        compare_files={(BASE_SHA, HEAD_A): (SAFE_PATH,)},
        list_files_timeline=[(SENSITIVE_PATH,)],
    )
    result = _snapshot(api)
    assert result.head_sha == HEAD_A
    assert result.base_sha == BASE_SHA
    assert result.filenames == (SAFE_PATH,)
    assert result.sensitive_files == ()
    assert result.safe_to_run is True
    assert result.is_fork is False
    assert result.is_default_branch is True
    assert api.list_files_calls == 0
    assert api.compare_calls == [(BASE_SHA, HEAD_A)]
    assert api.get_calls == 2


def test_aba_sensitive_b_then_safe_a_then_b_keeps_pinned_b_inventory() -> None:
    """B→A→B: gets return B both times, so re-get equality would accept.

    Unpinned listFiles can still return A's safe files in that window.
    SHA-pinned compare of B must keep B's sensitive inventory.
    """
    api = MutatingPullsApi(
        get_timeline=[_pull(HEAD_B), _pull(HEAD_B)],
        compare_files={
            (BASE_SHA, HEAD_B): (SENSITIVE_PATH,),
            (BASE_SHA, HEAD_A): (SAFE_PATH,),
        },
        list_files_timeline=[(SAFE_PATH,)],
    )
    result = _snapshot(api)
    assert result.head_sha == HEAD_B
    assert result.sensitive_files == (SENSITIVE_PATH,)
    assert result.filenames == (SENSITIVE_PATH,)
    assert api.list_files_calls == 0
    assert api.compare_calls == [(BASE_SHA, HEAD_B)]
    assert SAFE_PATH not in result.filenames


def test_sensitive_b_then_safe_a_drift_fails_closed_without_outputs() -> None:
    api = MutatingPullsApi(
        get_timeline=[_pull(HEAD_B), _pull(HEAD_A)],
        compare_files={
            (BASE_SHA, HEAD_B): (SENSITIVE_PATH,),
            (BASE_SHA, HEAD_A): (SAFE_PATH,),
        },
        list_files_timeline=[(SAFE_PATH,)],
    )
    with pytest.raises(ValueError, match="changed during the API snapshot"):
        _snapshot(api)
    assert api.compare_calls == [(BASE_SHA, HEAD_B)]
    assert api.list_files_calls == 0


def test_safe_a_then_sensitive_b_drift_fails_closed_without_outputs() -> None:
    api = MutatingPullsApi(
        get_timeline=[_pull(HEAD_A), _pull(HEAD_B)],
        compare_files={
            (BASE_SHA, HEAD_A): (SAFE_PATH,),
            (BASE_SHA, HEAD_B): (SENSITIVE_PATH,),
        },
        list_files_timeline=[(SENSITIVE_PATH,)],
    )
    with pytest.raises(ValueError, match="changed during the API snapshot"):
        _snapshot(api)
    assert api.compare_calls == [(BASE_SHA, HEAD_A)]
    assert api.list_files_calls == 0


def test_base_sha_drift_fails_closed() -> None:
    api = MutatingPullsApi(
        get_timeline=[_pull(HEAD_A, base_sha="base-one"), _pull(HEAD_A, base_sha="base-two")],
        compare_files={("base-one", HEAD_A): (SAFE_PATH,)},
    )
    with pytest.raises(ValueError, match="changed during the API snapshot"):
        _snapshot(api)


def test_base_ref_drift_fails_closed() -> None:
    api = MutatingPullsApi(
        get_timeline=[_pull(HEAD_A, base_ref="main"), _pull(HEAD_A, base_ref="develop")],
        compare_files={(BASE_SHA, HEAD_A): (SAFE_PATH,)},
    )
    with pytest.raises(ValueError, match="changed during the API snapshot"):
        _snapshot(api)


def test_first_get_api_failure_fails_closed() -> None:
    api = MutatingPullsApi(
        get_timeline=[ValueError("Unable to read pull request: 403")],
        compare_files={},
    )
    with pytest.raises(ValueError, match="Unable to read pull request"):
        _snapshot(api)
    assert api.compare_calls == []


def test_compare_api_failure_fails_closed() -> None:
    api = MutatingPullsApi(
        get_timeline=[_pull(HEAD_A), _pull(HEAD_A)],
        compare_files={(BASE_SHA, HEAD_A): ValueError("Unable to compare pinned SHAs: 404")},
    )
    with pytest.raises(ValueError, match="Unable to compare pinned SHAs"):
        _snapshot(api)


def test_second_get_api_failure_fails_closed() -> None:
    api = MutatingPullsApi(
        get_timeline=[_pull(HEAD_A), ValueError("Unable to read pull request: 502")],
        compare_files={(BASE_SHA, HEAD_A): (SAFE_PATH,)},
    )
    with pytest.raises(ValueError, match="Unable to read pull request"):
        _snapshot(api)
    assert api.compare_calls == [(BASE_SHA, HEAD_A)]


def test_truncated_compare_fails_closed() -> None:
    api = MutatingPullsApi(
        get_timeline=[_pull(HEAD_A), _pull(HEAD_A)],
        compare_files={(BASE_SHA, HEAD_A): tuple(f"file-{index}.py" for index in range(COMPARE_FILE_LIMIT))},
        truncated_compares={(BASE_SHA, HEAD_A)},
    )
    with pytest.raises(ValueError, match="file inventory is truncated"):
        _snapshot(api)


def test_fork_compare_pins_owner_and_sha() -> None:
    fork = _pull(HEAD_B, repo_id=99)
    api = MutatingPullsApi(
        get_timeline=[fork, fork],
        compare_files={(BASE_SHA, f"SiinXu:{HEAD_B}"): (SENSITIVE_PATH,)},
        list_files_timeline=[(SAFE_PATH,)],
    )
    result = _snapshot(api, repository_id=1)
    assert result.is_fork is True
    assert result.head_sha == HEAD_B
    assert result.sensitive_files == (SENSITIVE_PATH,)
    assert api.compare_calls == [(BASE_SHA, f"SiinXu:{HEAD_B}")]
    assert api.list_files_calls == 0
