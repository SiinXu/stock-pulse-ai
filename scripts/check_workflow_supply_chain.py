#!/usr/bin/env python3
"""Enforce immutable GitHub Actions references and least-privilege tokens."""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW_DIR = ROOT / ".github" / "workflows"
DEFAULT_EXCEPTIONS = ROOT / "scripts" / "workflow_supply_chain_exceptions.json"
MAX_EXCEPTION_DAYS = 30

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
DOCKER_DIGEST_RE = re.compile(r"^docker://.+@sha256:[0-9a-f]{64}$")
PIP_INSTALL_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:python(?:3(?:\.\d+)?)?\s+-m\s+)?pip3?\b"
    r"(?:(?![;&|#\r\n]).){0,256}?\binstall\b",
    re.IGNORECASE,
)
SECRET_EXPRESSION_RE = re.compile(r"\$\{\{[\s\S]*?\bsecrets\b[\s\S]*?\}\}")

PR_REVIEW_WORKFLOW = ".github/workflows/pr-review.yml"
TRUSTED_REVIEW_CHECKOUT_ID = "trusted-review-inputs"
PULL_REQUEST_REVIEW_CHECKOUT_ID = "pull-request-analysis-inputs"
FETCH_REVIEW_BASE_ID = "fetch-analysis-base"
SETUP_REVIEW_PYTHON_ID = "setup-review-python"
TRUSTED_REVIEW_INSTALL_ID = "install-trusted-review-dependencies"
TRUSTED_REVIEW_STEP_ID = "run-ai-review"
UPLOAD_REVIEW_RESULT_ID = "upload-ai-review-result"
TRUSTED_REVIEW_STEP_ORDER = (
    TRUSTED_REVIEW_CHECKOUT_ID,
    PULL_REQUEST_REVIEW_CHECKOUT_ID,
    FETCH_REVIEW_BASE_ID,
    SETUP_REVIEW_PYTHON_ID,
    TRUSTED_REVIEW_INSTALL_ID,
    TRUSTED_REVIEW_STEP_ID,
    UPLOAD_REVIEW_RESULT_ID,
)
TRUSTED_REVIEW_SPARSE_PATHS = frozenset(
    {
        ".github/scripts",
        ".github/requirements-review.txt",
        "constraints.txt",
        "build-constraints.txt",
    }
)
TRUSTED_REVIEW_INSTALL_LINES = (
    "python -m pip install --upgrade --constraint main-scripts/constraints.txt pip",
    "python -m pip install --build-constraint main-scripts/build-constraints.txt "
    "-r main-scripts/.github/requirements-review.txt",
    "python -m pip check",
)
TRUSTED_REVIEW_RUN_LINES = (
    "set -euo pipefail",
    'trusted_output="${RUNNER_TEMP}/ai_review_result.txt"',
    'rm -rf -- "${trusted_output}" ai_review_result.txt',
    "python ../main-scripts/.github/scripts/ai_review.py",
    "if [[ -e ai_review_result.txt || -L ai_review_result.txt ]]; then",
    "if [[ ! -f ai_review_result.txt || -L ai_review_result.txt ]]; then",
    'echo "AI review output must be a regular file"',
    "exit 1",
    "fi",
    'mv -- ai_review_result.txt "${trusted_output}"',
    "fi",
)
TRUSTED_REVIEW_REF = "${{ github.event.pull_request.base.sha || github.sha }}"
PULL_REQUEST_REVIEW_REF = "${{ github.event.pull_request.head.sha || github.sha }}"
FETCH_REVIEW_BASE_COMMAND = (
    "git fetch origin ${{ github.base_ref || 'main' }}:"
    "refs/remotes/origin/${{ github.base_ref || 'main' }}"
)
TRUSTED_REVIEW_JOB_IF_LINES = (
    "needs.security-check.outputs.safe_to_run == 'true' &&",
    "needs.security-check.outputs.is_fork != 'true' &&",
    "needs.auto-check.result == 'success' &&",
    "needs.auto-check.outputs.has_reviewable_changes == 'true' &&",
    "vars.ENABLE_AI_REVIEW != 'false'",
)
TRUSTED_REVIEW_ENV = {
    "GITHUB_BASE_REF": "${{ github.base_ref || 'main' }}",
    "GEMINI_API_KEY": "${{ secrets.GEMINI_API_KEY }}",
    "GEMINI_MODEL": "${{ vars.GEMINI_MODEL || 'gemini-2.5-flash' }}",
    "GEMINI_MODEL_FALLBACK": "${{ vars.GEMINI_MODEL_FALLBACK || 'gemini-2.5-flash' }}",
    "OPENAI_API_KEY": "${{ secrets.OPENAI_API_KEY }}",
    "OPENAI_BASE_URL": "${{ vars.OPENAI_BASE_URL }}",
    "OPENAI_MODEL": "${{ vars.OPENAI_MODEL }}",
    "AI_REVIEW_STRICT": "${{ vars.AI_REVIEW_STRICT || 'false' }}",
    "CI_SYNTAX_OK": "${{ needs.auto-check.outputs.syntax_ok || '' }}",
    "CI_HAS_PY_CHANGES": "${{ needs.auto-check.outputs.has_py_changes || 'false' }}",
    "CI_AUTO_CHECK_RESULT": "${{ needs.auto-check.result || '' }}",
}

# Every job permission is part of the reviewed contract, including read access.
APPROVED_JOB_PERMISSIONS = frozenset(
    {
        (".github/workflows/00-daily-analysis.yml", "analyze", "contents", "read"),
        (".github/workflows/auto-tag.yml", "tag", "contents", "write"),
        (".github/workflows/ci.yml", "changes", "contents", "read"),
        (".github/workflows/ci.yml", "changes", "pull-requests", "read"),
        (".github/workflows/ci.yml", "ai-governance", "contents", "read"),
        (".github/workflows/ci.yml", "backend-gate", "contents", "read"),
        (".github/workflows/ci.yml", "pydanticai-installed", "contents", "read"),
        (".github/workflows/ci.yml", "docker-build", "contents", "read"),
        (".github/workflows/ci.yml", "web-gate", "contents", "read"),
        (".github/workflows/ci.yml", "web-e2e", "contents", "read"),
        (".github/workflows/create-release.yml", "release", "contents", "write"),
        (".github/workflows/desktop-release.yml", "build-windows", "contents", "read"),
        (".github/workflows/desktop-release.yml", "build-macos", "contents", "read"),
        (".github/workflows/desktop-release.yml", "publish-release", "contents", "write"),
        (".github/workflows/docker-publish.yml", "build-and-push", "contents", "read"),
        (".github/workflows/docker-publish.yml", "build-and-push", "packages", "write"),
        (".github/workflows/ghcr-dockerhub.yml", "build-and-push", "contents", "read"),
        (".github/workflows/ghcr-dockerhub.yml", "build-and-push", "packages", "write"),
        (".github/workflows/issue-claim.yml", "claim", "issues", "write"),
        (".github/workflows/network-smoke.yml", "smoke", "contents", "read"),
        (".github/workflows/pr-review.yml", "security-check", "contents", "read"),
        (".github/workflows/pr-review.yml", "auto-check", "contents", "read"),
        (".github/workflows/pr-review.yml", "ai-review", "contents", "read"),
        (".github/workflows/pr-review.yml", "labeler", "pull-requests", "write"),
        (".github/workflows/pr-review.yml", "comment", "pull-requests", "write"),
        (".github/workflows/stale.yml", "stale", "issues", "write"),
        (".github/workflows/stale.yml", "stale", "pull-requests", "write"),
    }
)


@dataclass(frozen=True)
class ActionException:
    workflow: str
    action: str
    ref: str
    expires: date
    owner: str
    reason: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.workflow, self.action, self.ref)


def _load_exceptions(path: Path, today: date) -> tuple[dict[tuple[str, str, str], ActionException], list[str]]:
    errors: list[str] = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"{path}: cannot load exception registry: {exc}"]

    if not isinstance(raw, dict) or set(raw) != {"exceptions"} or not isinstance(raw["exceptions"], list):
        return {}, [f"{path}: expected one 'exceptions' array"]

    exceptions: dict[tuple[str, str, str], ActionException] = {}
    required = {"workflow", "action", "ref", "expires", "owner", "reason"}
    for index, item in enumerate(raw["exceptions"]):
        label = f"{path}: exceptions[{index}]"
        if not isinstance(item, dict) or set(item) != required:
            errors.append(f"{label}: expected exactly {sorted(required)}")
            continue
        if not all(isinstance(item[field], str) and item[field].strip() for field in required):
            errors.append(f"{label}: every field must be a non-empty string")
            continue
        try:
            expiry = date.fromisoformat(item["expires"])
        except ValueError:
            errors.append(f"{label}: expires must use YYYY-MM-DD")
            continue
        exception = ActionException(
            workflow=item["workflow"],
            action=item["action"],
            ref=item["ref"],
            expires=expiry,
            owner=item["owner"],
            reason=item["reason"],
        )
        if exception.expires < today:
            errors.append(f"{label}: exception expired on {exception.expires.isoformat()}")
            continue
        if exception.expires > today + timedelta(days=MAX_EXCEPTION_DAYS):
            errors.append(f"{label}: exception exceeds the {MAX_EXCEPTION_DAYS}-day maximum")
            continue
        if exception.key in exceptions:
            errors.append(f"{label}: duplicate exception for {exception.key}")
            continue
        exceptions[exception.key] = exception
    return exceptions, errors


def _mapping_values(node: MappingNode, key: str) -> list[Node]:
    return [value for candidate, value in node.value if isinstance(candidate, ScalarNode) and candidate.value == key]


def _named_mapping_value(node: MappingNode, key: str) -> MappingNode | None:
    """Return one named child mapping when it is declared exactly once."""
    values = _mapping_values(node, key)
    if len(values) == 1 and isinstance(values[0], MappingNode):
        return values[0]
    return None


def _scalar_value(node: MappingNode, key: str) -> str | None:
    """Return one named scalar value when it is declared exactly once."""
    values = _mapping_values(node, key)
    if len(values) == 1 and isinstance(values[0], ScalarNode):
        return values[0].value
    return None


def _mapping_keys(node: MappingNode) -> list[str] | None:
    """Return mapping keys while preserving duplicates, or None for complex keys."""
    keys: list[str] = []
    for key, _ in node.value:
        if not isinstance(key, ScalarNode):
            return None
        keys.append(key.value)
    return keys


def _mapping_shape_errors(node: MappingNode, expected: set[str], label: str) -> list[str]:
    """Require an exact mapping key set so unreviewed execution knobs fail closed."""
    keys = _mapping_keys(node)
    if keys is None or len(keys) != len(set(keys)) or set(keys) != expected:
        return [f"{label} must declare exactly {sorted(expected)}"]
    return []


def _scalar_mapping(node: MappingNode, key: str) -> dict[str, str] | None:
    """Return one exact scalar-to-scalar child mapping without duplicate keys."""
    mapping = _named_mapping_value(node, key)
    if mapping is None:
        return None
    values: dict[str, str] = {}
    for candidate, value in mapping.value:
        if not isinstance(candidate, ScalarNode) or not isinstance(value, ScalarNode):
            return None
        if candidate.value in values:
            return None
        values[candidate.value] = value.value
    return values


def _scalar_sequence(node: MappingNode, key: str) -> tuple[str, ...] | None:
    """Return one sequence containing only scalar values."""
    values = _mapping_values(node, key)
    if len(values) != 1 or not isinstance(values[0], SequenceNode):
        return None
    if not all(isinstance(value, ScalarNode) for value in values[0].value):
        return None
    return tuple(value.value for value in values[0].value)


def _pinned_action(step: MappingNode, expected_action: str) -> bool:
    """Report whether a step uses the expected external Action at an immutable SHA."""
    target = _scalar_value(step, "uses") or ""
    action, separator, ref = target.rpartition("@")
    return bool(separator and action == expected_action and SHA_RE.fullmatch(ref))


def _contains_secret_expression(node: Node) -> bool:
    """Report whether a YAML node contains a GitHub secret expression."""
    if isinstance(node, ScalarNode):
        return bool(SECRET_EXPRESSION_RE.search(node.value))
    if isinstance(node, MappingNode):
        return any(
            _contains_secret_expression(key) or _contains_secret_expression(value)
            for key, value in node.value
        )
    if isinstance(node, SequenceNode):
        return any(_contains_secret_expression(value) for value in node.value)
    return False


def _uses_nodes(node: Node) -> Iterable[ScalarNode]:
    if isinstance(node, MappingNode):
        for key, value in node.value:
            if isinstance(key, ScalarNode) and key.value == "uses" and isinstance(value, ScalarNode):
                yield value
            yield from _uses_nodes(value)
    elif isinstance(node, SequenceNode):
        for value in node.value:
            yield from _uses_nodes(value)


def _permission_errors(
    document: Node,
    relative_path: str,
) -> tuple[list[str], set[tuple[str, str, str, str]]]:
    errors: list[str] = []
    actual_permissions: set[tuple[str, str, str, str]] = set()
    if not isinstance(document, MappingNode):
        return [f"{relative_path}: workflow document must be a mapping"], actual_permissions

    top_level = _mapping_values(document, "permissions")
    if len(top_level) != 1:
        errors.append(f"{relative_path}: expected exactly one top-level permissions declaration")
    elif not isinstance(top_level[0], MappingNode) or top_level[0].value:
        errors.append(
            f"{relative_path}:{top_level[0].start_mark.line + 1}: top-level permissions must be exactly {{}}"
        )

    jobs_values = _mapping_values(document, "jobs")
    if len(jobs_values) != 1 or not isinstance(jobs_values[0], MappingNode):
        errors.append(f"{relative_path}: expected exactly one jobs mapping")
        return errors, actual_permissions
    jobs = jobs_values[0]
    if not jobs.value:
        errors.append(f"{relative_path}: jobs mapping contains no jobs")
        return errors, actual_permissions

    seen_jobs: set[str] = set()
    for job_key, job_value in jobs.value:
        if not isinstance(job_key, ScalarNode) or not isinstance(job_value, MappingNode):
            errors.append(f"{relative_path}:{job_key.start_mark.line + 1}: each job must be a named mapping")
            continue
        job_name = job_key.value
        if job_name in seen_jobs:
            errors.append(f"{relative_path}:{job_key.start_mark.line + 1}: duplicate job '{job_name}'")
        seen_jobs.add(job_name)
        declarations = _mapping_values(job_value, "permissions")
        if len(declarations) != 1 or not isinstance(declarations[0], MappingNode):
            errors.append(
                f"{relative_path}:{job_key.start_mark.line + 1}: "
                f"job '{job_name}' must declare exactly one job-level permissions mapping"
            )
            continue

        permissions = declarations[0]
        seen_scopes: set[str] = set()
        for scope_node, access_node in permissions.value:
            if not isinstance(scope_node, ScalarNode) or not isinstance(access_node, ScalarNode):
                errors.append(
                    f"{relative_path}:{scope_node.start_mark.line + 1}: invalid permission entry for job '{job_name}'"
                )
                continue
            scope = scope_node.value
            access = access_node.value
            if scope in seen_scopes:
                errors.append(
                    f"{relative_path}:{scope_node.start_mark.line + 1}: duplicate '{scope}' permission for job '{job_name}'"
                )
            seen_scopes.add(scope)
            if access not in {"read", "write", "none"}:
                errors.append(
                    f"{relative_path}:{access_node.start_mark.line + 1}: invalid '{access}' access for job '{job_name}'"
                )
            else:
                actual_permissions.add((relative_path, job_name, scope, access))
    return errors, actual_permissions


def _action_errors(
    document: Node,
    lines: list[str],
    relative_path: str,
    exceptions: dict[tuple[str, str, str], ActionException],
    used_exceptions: set[tuple[str, str, str]],
) -> list[str]:
    errors: list[str] = []
    for uses_node in _uses_nodes(document):
        index = uses_node.start_mark.line
        target = uses_node.value
        if target.startswith("./"):
            continue
        release = lines[index].partition("#")[2].strip()
        if not RELEASE_RE.fullmatch(release):
            errors.append(f"{relative_path}:{index + 1}: '{target}' must retain an exact upstream release comment")
        if target.startswith("docker://"):
            if not DOCKER_DIGEST_RE.fullmatch(target):
                errors.append(f"{relative_path}:{index + 1}: Docker Action '{target}' must use an immutable digest")
            continue
        action, separator, ref = target.rpartition("@")
        if not separator or not action or not ref:
            errors.append(f"{relative_path}:{index + 1}: malformed external Action reference '{target}'")
            continue
        if SHA_RE.fullmatch(ref):
            continue

        key = (relative_path, action, ref)
        if key in exceptions:
            used_exceptions.add(key)
            continue
        errors.append(f"{relative_path}:{index + 1}: '{target}' is not pinned to a 40-character commit SHA")
    return errors


def _trusted_review_dependency_errors(document: Node, relative_path: str) -> list[str]:
    """Keep the secret-bearing review job on one exact trusted execution path."""
    if relative_path != PR_REVIEW_WORKFLOW or not isinstance(document, MappingNode):
        return []

    errors: list[str] = []
    for forbidden_key in ("defaults", "env"):
        if _mapping_values(document, forbidden_key):
            errors.append(f"{relative_path}: workflow-level '{forbidden_key}' is not allowed")

    jobs = _named_mapping_value(document, "jobs")
    ai_review = _named_mapping_value(jobs, "ai-review") if jobs is not None else None
    if ai_review is None:
        return [f"{relative_path}: missing the reviewed 'ai-review' job"]
    errors.extend(
        _mapping_shape_errors(
            ai_review,
            {"name", "runs-on", "needs", "if", "permissions", "steps"},
            f"{relative_path}: ai-review job",
        )
    )
    if _scalar_value(ai_review, "runs-on") != "ubuntu-latest":
        errors.append(f"{relative_path}: ai-review must use the reviewed ubuntu-latest runner")
    if _scalar_sequence(ai_review, "needs") != ("security-check", "auto-check"):
        errors.append(f"{relative_path}: ai-review must retain its exact prerequisite jobs")
    job_if = _scalar_value(ai_review, "if") or ""
    job_if_lines = tuple(line.strip() for line in job_if.splitlines() if line.strip())
    if job_if_lines != TRUSTED_REVIEW_JOB_IF_LINES:
        errors.append(f"{relative_path}: ai-review must retain its exact fork and static-check gate")

    steps_values = _mapping_values(ai_review, "steps")
    if len(steps_values) != 1 or not isinstance(steps_values[0], SequenceNode):
        return [f"{relative_path}: ai-review must declare one steps sequence"]
    steps = [step for step in steps_values[0].value if isinstance(step, MappingNode)]
    if len(steps) != len(steps_values[0].value):
        errors.append(f"{relative_path}: every ai-review step must be a mapping")

    step_ids = tuple(_scalar_value(step, "id") or "" for step in steps)
    if step_ids != TRUSTED_REVIEW_STEP_ORDER:
        errors.append(
            f"{relative_path}: ai-review must retain the exact reviewed step order "
            f"{list(TRUSTED_REVIEW_STEP_ORDER)}"
        )
    identified_steps = {
        step_id: step for step_id, step in zip(step_ids, steps) if step_id and step_ids.count(step_id) == 1
    }

    checkout_step = identified_steps.get(TRUSTED_REVIEW_CHECKOUT_ID)
    if checkout_step is not None:
        errors.extend(
            _mapping_shape_errors(
                checkout_step,
                {"name", "id", "uses", "with"},
                f"{relative_path}: trusted review checkout step",
            )
        )
        if not _pinned_action(checkout_step, "actions/checkout"):
            errors.append(f"{relative_path}: trusted review inputs must use pinned actions/checkout")
        checkout_with = _scalar_mapping(checkout_step, "with")
        if checkout_with is None or set(checkout_with) != {
            "ref",
            "sparse-checkout",
            "sparse-checkout-cone-mode",
            "path",
        }:
            errors.append(f"{relative_path}: trusted review checkout must declare exact inputs")
        else:
            sparse_paths = {
                line.strip() for line in checkout_with["sparse-checkout"].splitlines() if line.strip()
            }
            if checkout_with["ref"] != TRUSTED_REVIEW_REF:
                errors.append(f"{relative_path}: review dependencies must be pinned to the trusted base commit")
            if checkout_with["path"] != "main-scripts":
                errors.append(f"{relative_path}: trusted review checkout path must be 'main-scripts'")
            if sparse_paths != TRUSTED_REVIEW_SPARSE_PATHS:
                errors.append(
                    f"{relative_path}: trusted review checkout must contain exactly "
                    f"{sorted(TRUSTED_REVIEW_SPARSE_PATHS)}"
                )
            if checkout_with["sparse-checkout-cone-mode"] != "false":
                errors.append(f"{relative_path}: trusted review checkout must disable sparse-checkout cone mode")

    pr_checkout_step = identified_steps.get(PULL_REQUEST_REVIEW_CHECKOUT_ID)
    if pr_checkout_step is not None:
        errors.extend(
            _mapping_shape_errors(
                pr_checkout_step,
                {"name", "id", "uses", "with"},
                f"{relative_path}: pull-request analysis checkout step",
            )
        )
        if not _pinned_action(pr_checkout_step, "actions/checkout"):
            errors.append(f"{relative_path}: pull-request analysis must use pinned actions/checkout")
        if _scalar_mapping(pr_checkout_step, "with") != {
            "ref": PULL_REQUEST_REVIEW_REF,
            "fetch-depth": "0",
            "path": "pr-code",
        }:
            errors.append(f"{relative_path}: pull-request checkout must retain its exact analysis-only inputs")

    fetch_step = identified_steps.get(FETCH_REVIEW_BASE_ID)
    if fetch_step is not None:
        errors.extend(
            _mapping_shape_errors(
                fetch_step,
                {"name", "id", "working-directory", "run"},
                f"{relative_path}: fetch analysis base step",
            )
        )
        if (
            _scalar_value(fetch_step, "working-directory") != "pr-code"
            or _scalar_value(fetch_step, "run") != FETCH_REVIEW_BASE_COMMAND
        ):
            errors.append(f"{relative_path}: base fetch must retain its exact analysis-only command")

    setup_step = identified_steps.get(SETUP_REVIEW_PYTHON_ID)
    if setup_step is not None:
        errors.extend(
            _mapping_shape_errors(
                setup_step,
                {"name", "id", "uses", "with"},
                f"{relative_path}: setup review Python step",
            )
        )
        if not _pinned_action(setup_step, "actions/setup-python"):
            errors.append(f"{relative_path}: review runtime must use pinned actions/setup-python")
        if _scalar_mapping(setup_step, "with") != {"python-version": "3.11"}:
            errors.append(f"{relative_path}: review runtime must retain Python 3.11")

    install_step = identified_steps.get(TRUSTED_REVIEW_INSTALL_ID)
    if install_step is not None:
        errors.extend(
            _mapping_shape_errors(
                install_step,
                {"name", "id", "run"},
                f"{relative_path}: trusted dependency install step",
            )
        )
        install_run = _scalar_value(install_step, "run") or ""
        install_lines = tuple(line.strip() for line in install_run.splitlines() if line.strip())
        if install_lines != TRUSTED_REVIEW_INSTALL_LINES:
            errors.append(
                f"{relative_path}: ai-review dependency step must use the trusted manifest, lock, "
                "build constraint, and pip check"
            )

    review_step = identified_steps.get(TRUSTED_REVIEW_STEP_ID)
    if review_step is not None:
        errors.extend(
            _mapping_shape_errors(
                review_step,
                {"name", "id", "working-directory", "env", "run"},
                f"{relative_path}: secret-bearing review step",
            )
        )
        if _scalar_value(review_step, "working-directory") != "pr-code":
            errors.append(f"{relative_path}: AI review must retain its analysis working directory")
        if _scalar_mapping(review_step, "env") != TRUSTED_REVIEW_ENV:
            errors.append(f"{relative_path}: AI review must retain its exact reviewed environment")
        review_run = _scalar_value(review_step, "run") or ""
        review_lines = tuple(line.strip() for line in review_run.splitlines() if line.strip())
        if review_lines != TRUSTED_REVIEW_RUN_LINES:
            errors.append(
                f"{relative_path}: AI review must execute the trusted-base script and isolate its output"
            )
        if not _contains_secret_expression(review_step):
            errors.append(f"{relative_path}: reviewed AI step no longer contains the expected secret boundary")

    upload_step = identified_steps.get(UPLOAD_REVIEW_RESULT_ID)
    if upload_step is not None:
        errors.extend(
            _mapping_shape_errors(
                upload_step,
                {"name", "id", "uses", "if", "with"},
                f"{relative_path}: review result upload step",
            )
        )
        if not _pinned_action(upload_step, "actions/upload-artifact"):
            errors.append(f"{relative_path}: review result must use pinned actions/upload-artifact")
        if _scalar_value(upload_step, "if") != "always()":
            errors.append(f"{relative_path}: review result upload must retain its always() condition")
        if _scalar_mapping(upload_step, "with") != {
            "name": "ai-review-result",
            "path": "${{ runner.temp }}/ai_review_result.txt",
            "if-no-files-found": "ignore",
        }:
            errors.append(f"{relative_path}: review result upload must retain its exact artifact inputs")

    for step_id, step in zip(step_ids, steps):
        uses = _scalar_value(step, "uses") or ""
        if uses.startswith("./"):
            errors.append(f"{relative_path}: ai-review must not execute local Actions")
        if step_id != TRUSTED_REVIEW_STEP_ID and _contains_secret_expression(step):
            errors.append(f"{relative_path}: only the reviewed AI step may reference secrets")
        run = _scalar_value(step, "run") or ""
        if PIP_INSTALL_RE.search(run) and step_id != TRUSTED_REVIEW_INSTALL_ID:
            errors.append(
                f"{relative_path}: only the reviewed dependency step may install packages in ai-review"
            )
    return errors


def check_repository(
    root: Path,
    workflow_dir: Path,
    exception_path: Path,
    *,
    today: date | None = None,
    approved_job_permissions: frozenset[tuple[str, str, str, str]] = APPROVED_JOB_PERMISSIONS,
) -> list[str]:
    current_date = today or date.today()
    exceptions, errors = _load_exceptions(exception_path, current_date)
    used_exceptions: set[tuple[str, str, str]] = set()
    actual_permissions: set[tuple[str, str, str, str]] = set()
    workflow_files = sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")))
    if not workflow_files:
        errors.append(f"{workflow_dir}: no workflow files found")
        return errors

    for workflow_path in workflow_files:
        relative_path = workflow_path.relative_to(root).as_posix()
        workflow_text = workflow_path.read_text(encoding="utf-8")
        lines = workflow_text.splitlines()
        try:
            document = yaml.compose(workflow_text)
        except yaml.YAMLError as exc:
            errors.append(f"{relative_path}: invalid YAML: {exc}")
            continue
        if document is None:
            errors.append(f"{relative_path}: workflow document is empty")
            continue
        permission_errors, workflow_permissions = _permission_errors(document, relative_path)
        errors.extend(permission_errors)
        actual_permissions.update(workflow_permissions)
        errors.extend(_action_errors(document, lines, relative_path, exceptions, used_exceptions))
        errors.extend(_trusted_review_dependency_errors(document, relative_path))

    for path, job, scope, access in sorted(actual_permissions - approved_job_permissions):
        errors.append(f"{path}: job '{job}' has unapproved '{scope}: {access}' permission")
    for path, job, scope, access in sorted(approved_job_permissions - actual_permissions):
        errors.append(
            f"{path}: approved permission '{job}/{scope}: {access}' is not present; update the reviewed allowlist"
        )
    for key in sorted(set(exceptions) - used_exceptions):
        errors.append(f"{exception_path}: unused Action exception for {key}")
    return errors


def _fixture_errors(
    workflow: str,
    *,
    exceptions: Iterable[dict[str, str]] = (),
    today: date,
    approved_permissions: frozenset[tuple[str, str, str, str]],
    workflow_name: str = "fixture.yml",
) -> list[str]:
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        workflow_dir = root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        (workflow_dir / workflow_name).write_text(workflow, encoding="utf-8")
        exception_path = root / "exceptions.json"
        exception_path.write_text(json.dumps({"exceptions": list(exceptions)}), encoding="utf-8")
        return check_repository(
            root,
            workflow_dir,
            exception_path,
            today=today,
            approved_job_permissions=approved_permissions,
        )


def _expect_failure(errors: list[str], expected: str) -> None:
    if not any(expected in error for error in errors):
        raise AssertionError(f"expected error containing {expected!r}, got {errors!r}")


def run_self_tests() -> None:
    today = date(2030, 1, 15)
    sha = "a" * 40
    fixture_path = ".github/workflows/fixture.yml"
    read_permissions = frozenset({(fixture_path, "check", "contents", "read")})
    compliant = f"""name: Fixture
permissions: {{}}
on: workflow_dispatch
jobs:
  check:
    permissions:
      contents: read
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{sha} # v5.1.0
"""

    def fixture_errors(
        workflow: str,
        *,
        exceptions: Iterable[dict[str, str]] = (),
        approved_permissions: frozenset[tuple[str, str, str, str]] = read_permissions,
    ) -> list[str]:
        return _fixture_errors(
            workflow,
            exceptions=exceptions,
            today=today,
            approved_permissions=approved_permissions,
        )

    if errors := fixture_errors(compliant):
        raise AssertionError(f"compliant fixture failed: {errors!r}")

    updated = compliant.replace(sha, "b" * 40).replace("v5.1.0", "v5.2.0")
    if errors := fixture_errors(updated):
        raise AssertionError(f"representative pin update failed: {errors!r}")

    movable = compliant.replace(f"actions/checkout@{sha}", "actions/checkout@v5")
    _expect_failure(fixture_errors(movable), "is not pinned")
    flow_movable = movable.replace("- uses: actions/checkout@v5 # v5.1.0", "- {uses: actions/checkout@v5} # v5.1.0")
    _expect_failure(fixture_errors(flow_movable), "is not pinned")
    _expect_failure(fixture_errors(compliant.replace("permissions: {}\n", "", 1)), "top-level")
    _expect_failure(
        fixture_errors(compliant.replace("    permissions:\n      contents: read\n", "")),
        "job-level permissions",
    )
    _expect_failure(
        fixture_errors(compliant.replace("permissions: {}", "permissions:\n  contents: write")),
        "top-level permissions must be exactly",
    )
    _expect_failure(fixture_errors(compliant.replace(" # v5.1.0", "")), "release comment")
    _expect_failure(fixture_errors(compliant.replace("# v5.1.0", "# v5")), "release comment")
    _expect_failure(fixture_errors(compliant.replace("# v5.1.0", "# 5")), "release comment")

    read_expanded = compliant.replace("contents: read", "contents: read\n      actions: read")
    _expect_failure(fixture_errors(read_expanded), "unapproved 'actions: read'")

    exception = {
        "workflow": fixture_path,
        "action": "actions/checkout",
        "ref": "v5",
        "expires": (today + timedelta(days=7)).isoformat(),
        "owner": "security-maintainers",
        "reason": "Temporary fixture for exception-path validation.",
    }
    if errors := fixture_errors(movable, exceptions=[exception]):
        raise AssertionError(f"active exception fixture failed: {errors!r}")
    exception["expires"] = (today - timedelta(days=1)).isoformat()
    _expect_failure(fixture_errors(movable, exceptions=[exception]), "exception expired")
    exception["expires"] = (today + timedelta(days=MAX_EXCEPTION_DAYS + 1)).isoformat()
    _expect_failure(fixture_errors(movable, exceptions=[exception]), "30-day maximum")

    write_fixture = compliant.replace("contents: read", "issues: write")
    _expect_failure(fixture_errors(write_fixture), "unapproved 'issues: write'")
    approved_write = frozenset({(fixture_path, "check", "issues", "write")})
    if errors := fixture_errors(write_fixture, approved_permissions=approved_write):
        raise AssertionError(f"approved write fixture failed: {errors!r}")

    trusted_path = PR_REVIEW_WORKFLOW
    trusted_permissions = frozenset({(trusted_path, "ai-review", "contents", "read")})
    trusted_if_lines = "\n".join(f"      {line}" for line in TRUSTED_REVIEW_JOB_IF_LINES)
    trusted_env_lines = "\n".join(f"          {key}: {value}" for key, value in TRUSTED_REVIEW_ENV.items())
    trusted_review = f"""name: PR Review
permissions: {{}}
on: pull_request
jobs:
  ai-review:
    name: AI review
    runs-on: ubuntu-latest
    needs: [security-check, auto-check]
    if: |
{trusted_if_lines}
    permissions:
      contents: read
    steps:
      - name: Checkout trusted inputs
        id: {TRUSTED_REVIEW_CHECKOUT_ID}
        uses: actions/checkout@{sha} # v5.1.0
        with:
          ref: {TRUSTED_REVIEW_REF}
          sparse-checkout: |
            .github/scripts
            .github/requirements-review.txt
            constraints.txt
            build-constraints.txt
          sparse-checkout-cone-mode: false
          path: main-scripts
      - name: Checkout pull request code
        id: {PULL_REQUEST_REVIEW_CHECKOUT_ID}
        uses: actions/checkout@{sha} # v5.1.0
        with:
          ref: {PULL_REQUEST_REVIEW_REF}
          fetch-depth: 0
          path: pr-code
      - name: Fetch base branch
        id: {FETCH_REVIEW_BASE_ID}
        working-directory: pr-code
        run: {FETCH_REVIEW_BASE_COMMAND}
      - name: Set up Python
        id: {SETUP_REVIEW_PYTHON_ID}
        uses: actions/setup-python@{sha} # v6.0.0
        with:
          python-version: '3.11'
      - name: Install trusted dependencies
        id: {TRUSTED_REVIEW_INSTALL_ID}
        run: |
          {TRUSTED_REVIEW_INSTALL_LINES[0]}
          {TRUSTED_REVIEW_INSTALL_LINES[1]}
          {TRUSTED_REVIEW_INSTALL_LINES[2]}
      - name: Run AI review
        id: {TRUSTED_REVIEW_STEP_ID}
        working-directory: pr-code
        env:
{trusted_env_lines}
        run: |
          {TRUSTED_REVIEW_RUN_LINES[0]}
          {TRUSTED_REVIEW_RUN_LINES[1]}
          {TRUSTED_REVIEW_RUN_LINES[2]}
          {TRUSTED_REVIEW_RUN_LINES[3]}
          {TRUSTED_REVIEW_RUN_LINES[4]}
            {TRUSTED_REVIEW_RUN_LINES[5]}
              {TRUSTED_REVIEW_RUN_LINES[6]}
              {TRUSTED_REVIEW_RUN_LINES[7]}
            {TRUSTED_REVIEW_RUN_LINES[8]}
            {TRUSTED_REVIEW_RUN_LINES[9]}
          {TRUSTED_REVIEW_RUN_LINES[10]}
      - name: Upload review result
        id: {UPLOAD_REVIEW_RESULT_ID}
        uses: actions/upload-artifact@{sha} # v4.0.0
        if: always()
        with:
          name: ai-review-result
          path: ${{{{ runner.temp }}}}/ai_review_result.txt
          if-no-files-found: ignore
"""

    def trusted_errors(workflow: str) -> list[str]:
        """Validate one isolated secret-bearing review workflow fixture."""
        return _fixture_errors(
            workflow,
            today=today,
            approved_permissions=trusted_permissions,
            workflow_name="pr-review.yml",
        )

    if errors := trusted_errors(trusted_review):
        raise AssertionError(f"trusted review fixture failed: {errors!r}")
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                "main-scripts/.github/requirements-review.txt",
                "pr-code/requirements.txt",
            )
        ),
        "trusted manifest",
    )
    _expect_failure(
        trusted_errors(trusted_review.replace("            build-constraints.txt\n", "")),
        "contain exactly",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                "            build-constraints.txt\n",
                "            build-constraints.txt\n            docs\n",
            )
        ),
        "contain exactly",
    )
    _expect_failure(
        trusted_errors(trusted_review.replace("          sparse-checkout-cone-mode: false\n", "")),
        "declare exact inputs",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                "      - name: Install trusted dependencies\n",
                "      - name: Premature secret use\n"
                "        env:\n"
                "          TOKEN: ${{ secrets.REVIEW_TOKEN }}\n"
                "        run: echo guarded\n"
                "      - name: Install trusted dependencies\n",
            )
        ),
        "only the reviewed AI step may reference secrets",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                "    runs-on: ubuntu-latest\n",
                "    runs-on: ubuntu-latest\n"
                "    env:\n"
                "      TOKEN: ${{ secrets.REVIEW_TOKEN }}\n",
            )
        ),
        "ai-review job must declare exactly",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                "      - name: Install trusted dependencies\n",
                "      - name: Bracket-syntax secret use\n"
                "        id: unreviewed-bracket-secret\n"
                "        env:\n"
                "          TOKEN: ${{ secrets['REVIEW_TOKEN'] }}\n"
                "        run: echo guarded\n"
                "      - name: Install trusted dependencies\n",
            )
        ),
        "only the reviewed AI step may reference secrets",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                "      - name: Run AI review\n",
                "      - name: Install pull-request plugin\n"
                "        run: python3 -m pip "
                "install -r pr-code/requirements.txt\n"
                "      - name: Run AI review\n",
            )
        ),
        "only the reviewed dependency step",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                "      - name: Run AI review\n",
                "      - name: Install pull-request plugin with pip options\n"
                "        run: python -m pip --disable-pip-version-check "
                "install -r pr-code/requirements.txt\n"
                "      - name: Run AI review\n",
            )
        ),
        "only the reviewed dependency step",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                "      - name: Upload review result\n",
                "      - name: Run pull-request local action\n"
                "        id: unreviewed-local-action\n"
                "        uses: ./pr-code/malicious-action\n"
                "        env:\n"
                "          TOKEN: ${{ secrets.REVIEW_TOKEN }}\n"
                "      - name: Upload review result\n",
            )
        ),
        "must not execute local Actions",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                "        if: always()\n",
                "        if: always()\n"
                "        env:\n"
                "          TOKEN: ${{ secrets.REVIEW_TOKEN }}\n",
            )
        ),
        "only the reviewed AI step may reference secrets",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                "    runs-on: ubuntu-latest\n",
                "    runs-on: ubuntu-latest\n"
                "    env:\n"
                "      PYTHONPATH: pr-code\n",
            )
        ),
        "ai-review job must declare exactly",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                f"          CI_AUTO_CHECK_RESULT: {TRUSTED_REVIEW_ENV['CI_AUTO_CHECK_RESULT']}\n"
                "        run: |\n",
                f"          CI_AUTO_CHECK_RESULT: {TRUSTED_REVIEW_ENV['CI_AUTO_CHECK_RESULT']}\n"
                "          PYTHONPATH: pr-code\n"
                "        run: |\n",
            )
        ),
        "exact reviewed environment",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                f"          {TRUSTED_REVIEW_RUN_LINES[2]}\n",
                "",
            )
        ),
        "isolate its output",
    )
    _expect_failure(
        trusted_errors(
            trusted_review.replace(
                "          path: ${{ runner.temp }}/ai_review_result.txt\n",
                "          path: pr-code/ai_review_result.txt\n",
            )
        ),
        "exact artifact inputs",
    )
    _expect_failure(
        trusted_errors(trusted_review.replace(f"id: {FETCH_REVIEW_BASE_ID}", f"id: {SETUP_REVIEW_PYTHON_ID}")),
        "exact reviewed step order",
    )
    print("Workflow supply-chain self-tests passed (33 cases).")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow-dir", type=Path, default=DEFAULT_WORKFLOW_DIR)
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        run_self_tests()
        return 0
    errors = check_repository(ROOT, args.workflow_dir, args.exceptions)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    workflow_count = len(tuple(args.workflow_dir.glob("*.yml"))) + len(tuple(args.workflow_dir.glob("*.yaml")))
    print(f"Workflow supply-chain checks passed for {workflow_count} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
