"""Guard the hosted CI contract for two-tier and minimum Python gates."""

import re
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
        "🧪 Unit tests": "npm run test",
        "🏗️ Build": "npm run build",
        "📦 Bundle size budget": "node scripts/check-bundle-size.mjs --print",
    }
    frontend_steps = ["📥 Checkout", "🟢 Setup Node", *expected_commands]
    for name in frontend_steps:
        assert steps_by_name[name]["if"] == FRONTEND_EXECUTION_CONDITION
    for name, command in expected_commands.items():
        assert steps_by_name[name]["run"] == command


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


def _report_export_stack_job() -> dict:
    return _workflow()["jobs"]["report-export-stack"]


def _report_export_step(name_substring: str) -> dict:
    job = _report_export_stack_job()
    return next(
        step for step in job["steps"] if name_substring in step.get("name", "")
    )


def test_report_export_stack_font_install_retries_mirrors_and_stays_fail_closed() -> None:
    """Hosted Azure archive hangs must retry once, then still fail closed."""

    job = _report_export_stack_job()
    font_step = _report_export_step("Install host fonts")
    import_step = _report_export_step("Assert report-export imports")
    test_step = _report_export_step("Report export tests")
    run = font_step["run"]

    assert job["timeout-minutes"] == 25
    assert job["permissions"] == {"contents": "read"}
    assert job.get("continue-on-error", False) is False
    assert all(step.get("continue-on-error", False) is False for step in job["steps"])
    assert font_step.get("continue-on-error", False) is False

    retries_match = re.search(r"Acquire::Retries=(\d+)", run)
    http_timeout_match = re.search(r"Acquire::http::Timeout=(\d+)", run)
    https_timeout_match = re.search(r"Acquire::https::Timeout=(\d+)", run)
    assert retries_match is not None
    assert http_timeout_match is not None
    assert https_timeout_match is not None
    retries = int(retries_match.group(1))
    http_timeout = int(http_timeout_match.group(1))
    https_timeout = int(https_timeout_match.group(1))
    command_budgets = [
        int(match) for match in re.findall(r"timeout --kill-after=\d+s (\d+)s", run)
    ]

    assert 1 <= retries <= 3
    assert 5 <= http_timeout <= 20
    assert 5 <= https_timeout <= 20
    assert command_budgets
    assert max(command_budgets) <= 180
    assert min(command_budgets) >= 60
    # Two attempts of the defined update+install budgets plus kill-after
    # buffers must remain inside the 25-minute job timeout.
    assert (2 * sum(command_budgets)) + 40 < job["timeout-minutes"] * 60
    assert "300s" not in run
    assert "while true" not in run
    assert "|| true" not in run
    assert "continue-on-error" not in run

    assert "/etc/apt/apt-mirrors.txt" in run
    assert "azure.archive.ubuntu.com" in run
    assert "prefer_runner_public_archive" in run
    assert "/var/lib/apt/lists/partial" in run
    assert run.count("install_host_fonts") >= 3
    assert "fonts-dejavu-core" in run
    assert "fonts-noto-cjk" in run
    assert "dpkg -s fonts-dejavu-core fonts-noto-cjk" in run
    assert "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf" in run
    assert "NotoSansCJK" in run
    assert "exit 1" in run

    assert "is_html_dependency_available" in import_step["run"]
    assert "is_pdf_dependency_available" in import_step["run"]
    assert "must not skip HTML/PDF tests" in test_step["run"]
    assert "tests/services/test_report_export_service.py" in test_step["run"]
    assert "tests/api/test_report_export_api.py" in test_step["run"]
    assert "tests/config/test_report_export_config.py" in test_step["run"]
