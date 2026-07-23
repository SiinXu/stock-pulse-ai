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
    r"\b(?:python(?:3(?:\.\d+)?)?\s+-m\s+)?pip3?\s+install\b"
)

PR_REVIEW_WORKFLOW = ".github/workflows/pr-review.yml"
TRUSTED_REVIEW_CHECKOUT_ID = "trusted-review-inputs"
TRUSTED_REVIEW_INSTALL_ID = "install-trusted-review-dependencies"
TRUSTED_REVIEW_STEP_ID = "run-ai-review"
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
TRUSTED_REVIEW_REF = "${{ github.event.pull_request.base.sha || github.sha }}"

# Every job permission is part of the reviewed contract, including read access.
APPROVED_JOB_PERMISSIONS = frozenset(
    {
        (".github/workflows/00-daily-analysis.yml", "analyze", "contents", "read"),
        (".github/workflows/auto-tag.yml", "tag", "contents", "write"),
        (".github/workflows/ci.yml", "changes", "contents", "read"),
        (".github/workflows/ci.yml", "changes", "pull-requests", "read"),
        (".github/workflows/ci.yml", "ai-governance", "contents", "read"),
        (".github/workflows/ci.yml", "backend-gate", "contents", "read"),
        (".github/workflows/ci.yml", "python-minimum", "contents", "read"),
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


def _contains_secret_expression(node: Node) -> bool:
    """Report whether a YAML node contains a GitHub secret expression."""
    if isinstance(node, ScalarNode):
        return "secrets." in node.value
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
    """Keep secret-bearing review installs on immutable trusted-base inputs."""
    if relative_path != PR_REVIEW_WORKFLOW or not isinstance(document, MappingNode):
        return []

    errors: list[str] = []
    jobs = _named_mapping_value(document, "jobs")
    ai_review = _named_mapping_value(jobs, "ai-review") if jobs is not None else None
    if ai_review is None:
        return [f"{relative_path}: missing the reviewed 'ai-review' job"]

    steps_values = _mapping_values(ai_review, "steps")
    if len(steps_values) != 1 or not isinstance(steps_values[0], SequenceNode):
        return [f"{relative_path}: ai-review must declare one steps sequence"]
    steps = [step for step in steps_values[0].value if isinstance(step, MappingNode)]

    identified_steps: dict[str, tuple[int, MappingNode]] = {}
    for index, step in enumerate(steps):
        step_id = _scalar_value(step, "id")
        if step_id is not None:
            identified_steps[step_id] = (index, step)

    checkout_index: int | None = None
    checkout_entry = identified_steps.get(TRUSTED_REVIEW_CHECKOUT_ID)
    if checkout_entry is None:
        errors.append(f"{relative_path}: ai-review is missing its trusted-base checkout")
    else:
        checkout_index, checkout_step = checkout_entry
        checkout_action = _scalar_value(checkout_step, "uses") or ""
        if not checkout_action.startswith("actions/checkout@"):
            errors.append(f"{relative_path}: trusted review inputs must use actions/checkout")
        checkout_with = _named_mapping_value(checkout_step, "with")
        if checkout_with is None:
            errors.append(f"{relative_path}: trusted review checkout must declare inputs")
        else:
            if _scalar_value(checkout_with, "ref") != TRUSTED_REVIEW_REF:
                errors.append(f"{relative_path}: review dependencies must be pinned to the trusted base commit")
            if _scalar_value(checkout_with, "path") != "main-scripts":
                errors.append(f"{relative_path}: trusted review checkout path must be 'main-scripts'")
            sparse_checkout = _scalar_value(checkout_with, "sparse-checkout") or ""
            sparse_paths = {line.strip() for line in sparse_checkout.splitlines() if line.strip()}
            if sparse_paths != TRUSTED_REVIEW_SPARSE_PATHS:
                errors.append(
                    f"{relative_path}: trusted review checkout must contain exactly "
                    f"{sorted(TRUSTED_REVIEW_SPARSE_PATHS)}"
                )
            if _scalar_value(checkout_with, "sparse-checkout-cone-mode") != "false":
                errors.append(f"{relative_path}: trusted review checkout must disable sparse-checkout cone mode")

    install_entry = identified_steps.get(TRUSTED_REVIEW_INSTALL_ID)
    review_entry = identified_steps.get(TRUSTED_REVIEW_STEP_ID)
    if install_entry is None:
        errors.append(f"{relative_path}: ai-review is missing its reviewed dependency install step")
    else:
        install_index, install_step = install_entry
        install_run = _scalar_value(install_step, "run") or ""
        install_lines = tuple(line.strip() for line in install_run.splitlines() if line.strip())
        if install_lines != TRUSTED_REVIEW_INSTALL_LINES:
            errors.append(
                f"{relative_path}: ai-review dependency step must use the trusted manifest, lock, "
                "build constraint, and pip check"
            )
        if _mapping_values(install_step, "working-directory"):
            errors.append(f"{relative_path}: trusted dependency install must not run from PR-controlled code")
        if _contains_secret_expression(install_step):
            errors.append(f"{relative_path}: dependency installation must run before secrets are injected")
        if review_entry is not None and install_index >= review_entry[0]:
            errors.append(f"{relative_path}: dependency installation must precede the secret-bearing review step")
        if checkout_index is not None and checkout_index >= install_index:
            errors.append(f"{relative_path}: trusted dependency checkout must precede installation")

        job_env = _named_mapping_value(ai_review, "env")
        if job_env is not None and _contains_secret_expression(job_env):
            errors.append(f"{relative_path}: ai-review must not inject secrets at job scope")
        for prior_step in steps[:install_index]:
            if _contains_secret_expression(prior_step):
                errors.append(f"{relative_path}: dependency installation must precede every secret-bearing step")

    if review_entry is None:
        errors.append(f"{relative_path}: ai-review is missing its secret-bearing review step")
    else:
        _, review_step = review_entry
        if not _contains_secret_expression(review_step):
            errors.append(f"{relative_path}: reviewed AI step no longer contains the expected secret boundary")
        if _scalar_value(review_step, "run") != "python ../main-scripts/.github/scripts/ai_review.py":
            errors.append(f"{relative_path}: AI review must execute the trusted-base script")

    for step in steps:
        run = _scalar_value(step, "run") or ""
        if PIP_INSTALL_RE.search(run) and _scalar_value(step, "id") != TRUSTED_REVIEW_INSTALL_ID:
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
    trusted_review = f"""name: PR Review
permissions: {{}}
on: pull_request
jobs:
  ai-review:
    permissions:
      contents: read
    runs-on: ubuntu-latest
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
          OPENAI_API_KEY: ${{{{ secrets.OPENAI_API_KEY }}}}
        run: python ../main-scripts/.github/scripts/ai_review.py
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
        "disable sparse-checkout cone mode",
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
        "precede every secret-bearing step",
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
        "must not inject secrets at job scope",
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
    print("Workflow supply-chain self-tests passed (24 cases).")


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
