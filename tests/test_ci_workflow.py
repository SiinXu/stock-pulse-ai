"""Guard the hosted CI contract for two-tier and minimum Python gates."""

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
FRONTEND_EXECUTION_CONDITION = (
    "${{ needs.ai-governance.result == 'success' && "
    "needs.changes.result == 'success' && "
    "needs.changes.outputs.frontend == 'true' }}"
)


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_ci_uses_supported_pull_request_and_push_events_only() -> None:
    workflow = _workflow()
    # PyYAML loads the bare key `on:` as boolean True.
    assert set(workflow[True]) == {"pull_request", "push"}


def test_backend_gate_pr_is_selective() -> None:
    workflow = _workflow()
    job = workflow["jobs"]["backend-gate"]

    assert job["name"] == "backend-gate"
    assert job["needs"] == ["changes", "ai-governance"]
    assert job["if"] == (
        "github.event_name == 'pull_request' && "
        "needs.changes.outputs.backend == 'true' && "
        "needs.changes.outputs.backend_full != 'true'"
    )
    runs = [step.get("run", "") for step in job["steps"] if "run" in step]
    assert sum("offline-tests-selective" in command for command in runs) == 1
    assert not any(
        command.strip() == "./scripts/ci_gate.sh offline-tests" for command in runs
    )


def test_changes_job_plans_full_pr_suite_before_scheduling_backend_jobs() -> None:
    workflow = _workflow()
    job = workflow["jobs"]["changes"]

    assert "backend_full" in job["outputs"]
    checkout = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["fetch-depth"] == 0
    planner = next(
        step for step in job["steps"] if step.get("id") == "backend-selection"
    )
    assert "ci_select_tests.py" in planner["run"]
    assert 'echo "full=true" >> "${GITHUB_OUTPUT}"' in planner["run"]


def test_backend_tests_are_sharded_for_full_prs_and_push_to_main() -> None:
    workflow = _workflow()
    job = workflow["jobs"]["backend-tests"]

    assert job["needs"] == ["changes", "ai-governance"]
    assert job["if"] == (
        "needs.changes.outputs.backend == 'true' && "
        "(github.event_name == 'push' || "
        "(github.event_name == 'pull_request' && "
        "needs.changes.outputs.backend_full == 'true'))"
    )
    assert job["strategy"]["matrix"]["shard"] == [1, 2, 3, 4]
    runs = [step.get("run", "") for step in job["steps"] if "run" in step]
    assert sum("offline-tests-shard" in command for command in runs) == 1
    upload = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert upload["with"]["include-hidden-files"] is True
    assert upload["with"]["if-no-files-found"] == "error"


def test_backend_gate_summary_combines_coverage_after_all_shards() -> None:
    workflow = _workflow()
    job = workflow["jobs"]["backend-gate-main"]

    assert job["name"] == "backend-gate"
    assert job["needs"] == ["changes", "ai-governance", "backend-tests"]
    assert job["if"] == (
        "always() && needs.changes.outputs.backend == 'true' && "
        "(github.event_name == 'push' || "
        "(github.event_name == 'pull_request' && "
        "needs.changes.outputs.backend_full == 'true'))"
    )
    runs = [step.get("run", "") for step in job["steps"] if "run" in step]
    assert sum("offline-tests-combine" in command for command in runs) == 1


def test_python_minimum_job_uses_smoke_on_pr_and_full_offline_on_push() -> None:
    """PR uses 3.10 smoke; push-to-main keeps a full offline suite on the floor."""

    workflow = _workflow()
    job = workflow["jobs"]["python-minimum"]
    backend_job = workflow["jobs"]["backend-gate"]
    changes_job = workflow["jobs"]["changes"]

    assert job["name"] == "python-minimum"
    assert job["needs"] == ["changes", "ai-governance"]
    assert job["if"] == "needs.changes.outputs.backend == 'true'"
    assert job["permissions"] == {"contents": "read"}
    assert job.get("continue-on-error", False) is False
    assert all(
        step.get("continue-on-error", False) is False for step in job["steps"]
    )

    assert backend_job["timeout-minutes"] >= 45
    assert job["timeout-minutes"] >= 45
    assert "backend" in changes_job["outputs"]
    assert "docker" in changes_job["outputs"]

    setup_steps = [
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert len(setup_steps) == 1
    assert setup_steps[0]["with"]["python-version"] == "3.10"

    smoke_steps = [
        step
        for step in job["steps"]
        if step.get("run", "").strip() == "./scripts/ci_gate.sh python-min-smoke"
    ]
    assert len(smoke_steps) == 1
    assert smoke_steps[0]["if"] == "github.event_name == 'pull_request'"

    full_steps = [
        step
        for step in job["steps"]
        if step.get("run", "").strip() == "./scripts/ci_gate.sh offline-tests"
    ]
    assert len(full_steps) == 1
    assert full_steps[0]["if"] == "github.event_name != 'pull_request'"


def test_docker_build_skips_when_docker_paths_unchanged():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["docker-build"]
    assert job["needs"] == ["changes", "ai-governance"]
    assert job["if"] == "needs.changes.outputs.docker == 'true'"


def test_docker_path_filter_watches_packaging_metadata():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    filter_step = next(
        step
        for step in workflow["jobs"]["changes"]["steps"]
        if step.get("id") == "filter"
    )
    filters = yaml.safe_load(filter_step["with"]["filters"])
    docker_paths = set(filters["docker"])
    assert {"pyproject.toml", "README.md", "LICENSE"} <= docker_paths


def test_editable_installs_are_no_deps_and_build_constrained():
    install_files = (
        "scripts/ci_gate.sh",
        "docker/Dockerfile",
        "scripts/build-backend-macos.sh",
        "scripts/build-backend.ps1",
    )
    for relative in install_files:
        text = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", "//")):
                continue
            if stripped.startswith(("throw ", "echo ", "Write-Host")):
                continue
            if "install" in line and "-e ." in line:
                lines.append(line)
        assert lines, relative
        for line in lines:
            assert "--no-deps" in line, (relative, line)
            assert (
                "--build-constraint" in line
                or "PIP_BUILD_CONSTRAINT=build-constraints.txt" in line
            ), (relative, line)


def test_web_gate_runs_full_matrix_for_frontend_changes():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    changes_job = workflow["jobs"]["changes"]
    web_job = workflow["jobs"]["web-gate"]
    steps_by_name = {step["name"]: step for step in web_job["steps"]}

    filter_step = next(
        step for step in changes_job["steps"] if step.get("id") == "filter"
    )
    filters = yaml.safe_load(filter_step["with"]["filters"])
    assert filters["frontend"] == ["apps/dsa-web/**"]

    expected_commands = {
        "📦 Install": "npm ci",
        "🔎 Lint": "npm run lint",
        "🌐 i18n guards": "npm run test:i18n",
        "🧪 Unit tests": "npm run test:coverage",
        "🏗️ Build": "npm run build",
        "📦 Bundle size budget": "node scripts/check-bundle-size.mjs --print",
    }
    frontend_steps = ["📥 Checkout", "🟢 Setup Node", *expected_commands]
    for name in frontend_steps:
        assert steps_by_name[name]["if"] == FRONTEND_EXECUTION_CONDITION
    for name, command in expected_commands.items():
        assert steps_by_name[name]["run"] == command


def test_web_gate_uses_coverage_instead_of_a_second_unit_suite():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    web_job = workflow["jobs"]["web-gate"]
    runs = [step.get("run") for step in web_job["steps"] if "run" in step]

    assert runs.count("npm run test:coverage") == 1
    assert "npm run test" not in runs


def test_web_gate_enforces_bundle_budget_immediately_after_build():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    web_job = workflow["jobs"]["web-gate"]
    steps = web_job["steps"]

    build_indexes = [
        index
        for index, step in enumerate(steps)
        if step.get("run") == "npm run build"
    ]
    budget_indexes = [
        index
        for index, step in enumerate(steps)
        if step.get("name") == "📦 Bundle size budget"
    ]

    assert len(build_indexes) == 1
    assert len(budget_indexes) == 1
    assert budget_indexes[0] == build_indexes[0] + 1

    budget_step = steps[budget_indexes[0]]
    assert budget_step["run"] == "node scripts/check-bundle-size.mjs --print"
    assert budget_step["if"] == FRONTEND_EXECUTION_CONDITION
    assert web_job.get("continue-on-error", False) is False
    assert all(
        step.get("continue-on-error", False) is False for step in steps
    )


def test_web_gate_concludes_successfully_without_frontend_changes():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    web_job = workflow["jobs"]["web-gate"]
    steps_by_name = {step["name"]: step for step in web_job["steps"]}

    assert web_job["name"] == "web-gate"
    assert web_job["needs"] == ["changes", "ai-governance"]
    assert web_job["if"] == "${{ always() && !cancelled() }}"
    no_frontend = steps_by_name["No frontend changes"]
    assert no_frontend["if"] == (
        "${{ needs.ai-governance.result == 'success' && "
        "needs.changes.result == 'success' && "
        "needs.changes.outputs.frontend == 'false' }}"
    )
    assert no_frontend["working-directory"] == "."
    assert "No frontend changes were detected." in no_frontend["run"]
    assert '>> "$GITHUB_STEP_SUMMARY"' in no_frontend["run"]
    assert "exit 1" not in no_frontend["run"]


def test_web_gate_fails_closed_when_change_detection_fails_or_is_unavailable():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    web_job = workflow["jobs"]["web-gate"]
    validation = next(
        step
        for step in web_job["steps"]
        if step["name"] == "🔒 Validate web-gate prerequisites"
    )

    assert validation["if"] == (
        "${{ always() && (needs.ai-governance.result != 'success' || "
        "needs.changes.result != 'success' || "
        "(needs.changes.outputs.frontend != 'true' && "
        "needs.changes.outputs.frontend != 'false')) }}"
    )
    assert validation["working-directory"] == "."
    assert "fails closed" in validation["run"]
    assert validation["run"].rstrip().endswith("exit 1")


def test_ci_gate_offline_suite_emits_slow_test_durations():
    script = (REPOSITORY_ROOT / "scripts" / "ci_gate.sh").read_text(encoding="utf-8")
    assert "--durations=30" in script
    assert "--durations-min=0.5" in script


def test_ci_gate_keeps_shard_variables_out_of_single_node_suite():
    script = (REPOSITORY_ROOT / "scripts" / "ci_gate.sh").read_text(encoding="utf-8")
    single_node = script.split("offline_test_suite() {", 1)[1].split(
        "offline_test_suite_selective() {", 1
    )[0]
    sharded = script.split("offline_test_suite_shard() {", 1)[1].split(
        "offline_test_suite_combine() {", 1
    )[0]

    assert "shard_dir" not in single_node
    assert "${group}" not in single_node
    assert '--cov-report="json:${coverage_report}"' in single_node
    assert '--cov-report="json:${shard_dir}/coverage-shard-${group}.json"' in sharded


def test_pytest_testpaths_scopes_to_tests_package():
    setup_cfg = (REPOSITORY_ROOT / "setup.cfg").read_text(encoding="utf-8")
    assert "testpaths = tests" in setup_cfg
