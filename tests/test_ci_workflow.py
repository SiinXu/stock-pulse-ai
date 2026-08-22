"""Guard the hosted CI contract for two-tier and minimum Python gates."""

import re
from fnmatch import fnmatch
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
FRONTEND_EXECUTION_CONDITION = (
    "${{ needs.ai-governance.result == 'success' && "
    "needs.changes.result == 'success' && "
    "needs.changes.outputs.frontend == 'true' }}"
)
OCR_EXECUTION_CONDITION = (
    "${{ needs.ai-governance.result == 'success' && "
    "needs.changes.result == 'success' && "
    "needs.changes.outputs.ocr_extractor == 'true' }}"
)
DESKTOP_EXECUTION_CONDITION = (
    "${{ needs.ai-governance.result == 'success' && "
    "needs.changes.result == 'success' && "
    "needs.changes.outputs.desktop == 'true' }}"
)
OCR_EXTRACTOR_TEST_FILES = (
    "tests/services/test_image_stock_extractor_litellm.py",
    "tests/services/test_image_stock_extractor_contract.py",
    "tests/services/test_ocr_extraction_service.py",
    "tests/agent/tools/test_ocr_tools.py",
    "tests/agent/tools/test_ocr_tool_surface_runtime.py",
    "tests/config/test_ocr_config.py",
    "tests/plugins/test_ocr_agent_tool.py",
)
OCR_EXTRACTOR_SOURCE_FILES = (
    "src/services/image_stock_extractor.py",
    "src/services/ocr_extraction_service.py",
    "src/agent/tools/ocr_tools.py",
    "src/plugins/builtin/ocr.py",
    "src/api/v1/endpoints/stocks.py",
)
OCR_EXTRACTOR_FIXTURE_PATHS = (
    "tests/fixtures/ocr/**",
    "tests/fixtures/multimodal/sample_financial_report.pdf",
)
OCR_EXTRACTOR_PATH_FILTER = (
    *OCR_EXTRACTOR_SOURCE_FILES,
    *OCR_EXTRACTOR_TEST_FILES,
    *OCR_EXTRACTOR_FIXTURE_PATHS,
    "requirements-ocr.txt",
    ".github/workflows/ci.yml",
)
DESKTOP_PATH_FILTER = (
    "apps/dsa-desktop/**",
    "scripts/run-desktop.ps1",
    "scripts/build-desktop*.ps1",
    "scripts/build-desktop*.sh",
    "scripts/build-all.ps1",
    "scripts/build-all-macos.sh",
    "scripts/build-backend.ps1",
    "scripts/build-backend-macos.sh",
    "scripts/verify-desktop-updater-artifacts.ps1",
    "scripts/prepare-embedded-ollama.js",
    "requirements-desktop.txt",
    "THIRD_PARTY_NOTICES",
    ".github/workflows/desktop-release.yml",
    ".github/workflows/ci.yml",
)
DESKTOP_TEST_PINNED_REPO_FILES = (
    "scripts/verify-desktop-updater-artifacts.ps1",
    "scripts/build-backend-macos.sh",
    "scripts/build-desktop-macos.sh",
    "scripts/prepare-embedded-ollama.js",
    "THIRD_PARTY_NOTICES",
    ".github/workflows/desktop-release.yml",
)


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _assert_job_fail_closed(job: dict) -> None:
    assert job.get("continue-on-error", False) is False
    assert all(step.get("continue-on-error", False) is False for step in job["steps"])


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
    assert job["timeout-minutes"] <= 45
    _assert_job_fail_closed(job)
    runs = [step.get("run", "") for step in job["steps"] if "run" in step]
    assert sum("offline-tests-selective" in command for command in runs) == 1
    assert not any(
        command.strip() == "./scripts/ci_gate.sh offline-tests" for command in runs
    )
    assert not any("--depth=1" in command for command in runs)
    assert not any("origin/main" in command for command in runs)
    selective = next(
        step
        for step in job["steps"]
        if "offline-tests-selective" in step.get("run", "")
    )
    assert selective["env"]["CI_SELECT_BASE"] == (
        "${{ github.event.pull_request.base.sha }}"
    )
    assert selective.get("continue-on-error", False) is False


def test_backend_web_contract_filter_still_schedules_backend_jobs() -> None:
    """Shared web/runtime contract files must keep backend validation scheduled."""

    workflow = _workflow()
    changes = workflow["jobs"]["changes"]
    assert "backend_web_contract" in changes["outputs"]["backend"]
    filter_step = next(
        step for step in changes["steps"] if step.get("id") == "filter"
    )
    filters = yaml.safe_load(filter_step["with"]["filters"])
    contract_paths = filters["backend_web_contract"]
    assert "apps/dsa-web/public/**" in contract_paths
    assert any(path.endswith("llmProviderTemplates.ts") for path in contract_paths)
    assert any(path.endswith("systemConfigI18n.ts") for path in contract_paths)
    planner = next(
        step for step in changes["steps"] if step.get("id") == "backend-selection"
    )
    assert "backend_web_contract" in planner["if"]


def test_changes_job_plans_full_pr_suite_before_scheduling_backend_jobs() -> None:
    workflow = _workflow()
    job = workflow["jobs"]["changes"]

    assert "backend_full" in job["outputs"]
    assert job["outputs"]["backend_full"] == (
        "${{ steps.backend-selection.outputs.full || 'true' }}"
    )
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
    assert planner["env"]["CI_SELECT_BASE"] == (
        "${{ github.event.pull_request.base.sha }}"
    )
    assert "--depth=1" not in planner["run"]
    assert "origin/main" not in planner["run"]


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
    checkout = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["fetch-depth"] == 0
    upload = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    assert upload["with"]["include-hidden-files"] is True
    assert upload["with"]["if-no-files-found"] == "error"
    _assert_job_fail_closed(job)


def test_offline_pytest_jobs_fetch_full_git_history() -> None:
    """Ported-from tests walk git log; depth 1 drops ancestor squash trailers."""

    workflow = _workflow()
    for job_id in ("backend-gate", "backend-tests", "python-minimum-tests"):
        job = workflow["jobs"][job_id]
        checkout = next(
            step
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        )
        assert checkout.get("with", {}).get("fetch-depth") == 0, job_id


def test_backend_tests_shards_cover_every_offline_test_module_once() -> None:
    """PR FULL and push-to-main reuse the same 4-way partition; no module dropped."""

    from scripts.ci_test_shard import (
        discover_test_files,
        load_durations,
        partition_test_files,
    )

    workflow = _workflow()
    job = workflow["jobs"]["backend-tests"]
    assert job["strategy"]["matrix"]["shard"] == [1, 2, 3, 4]

    files = discover_test_files()
    groups, _totals = partition_test_files(
        files,
        load_durations(),
        splits=4,
        initial_totals=[0.0, 0.0, 0.0, 0.0],
    )
    covered = [path for group in groups for path in group]
    assert sorted(covered) == sorted(files)
    assert all(group for group in groups)
    assert len(covered) == len(set(covered))


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
    _assert_job_fail_closed(job)
    runs = [step.get("run", "") for step in job["steps"] if "run" in step]
    assert sum("offline-tests-combine" in command for command in runs) == 1


def test_pr_full_fallback_uses_sharded_backend_tests_not_unsharded_suite() -> None:
    """PR FULL must reuse backend-tests shards; the 45-minute job cannot run it."""

    workflow = _workflow()
    selective = workflow["jobs"]["backend-gate"]
    shards = workflow["jobs"]["backend-tests"]
    aggregator = workflow["jobs"]["backend-gate-main"]

    assert selective["name"] == aggregator["name"] == "backend-gate"
    assert "backend_full != 'true'" in selective["if"]
    assert "backend_full == 'true'" in shards["if"]
    assert "backend_full == 'true'" in aggregator["if"]
    assert "always()" in aggregator["if"]
    assert shards["timeout-minutes"] == 30
    assert shards["strategy"]["fail-fast"] is False
    assert shards["strategy"]["matrix"]["shard"] == [1, 2, 3, 4]
    _assert_job_fail_closed(selective)
    _assert_job_fail_closed(shards)
    _assert_job_fail_closed(aggregator)

    selective_runs = [step.get("run", "") for step in selective["steps"] if "run" in step]
    shard_runs = [step.get("run", "") for step in shards["steps"] if "run" in step]
    assert any("offline-tests-selective" in command for command in selective_runs)
    assert any("offline-tests-shard" in command for command in shard_runs)
    assert not any(
        "offline-tests-shard" in command for command in selective_runs
    )
    assert not any(
        command.strip() == "./scripts/ci_gate.sh offline-tests" for command in selective_runs
    )
    assert not any(
        command.strip() == "./scripts/ci_gate.sh offline-tests" for command in shard_runs
    )


def test_backend_gate_aggregator_cannot_mask_failed_or_cancelled_shard() -> None:
    """Required check backend-gate must fail when any PR/push shard is not success."""

    workflow = _workflow()
    job = workflow["jobs"]["backend-gate-main"]
    require = next(
        step for step in job["steps"] if step.get("name") == "✅ Require shard success"
    )

    assert "if" not in require
    assert require.get("continue-on-error", False) is False
    env = require["env"]
    assert env["TESTS_RESULT"] == "${{ needs.backend-tests.result }}"
    assert env["AI_RESULT"] == "${{ needs.ai-governance.result }}"
    script = require["run"]
    assert '[ "${TESTS_RESULT}" != "success" ]' in script
    assert "backend-tests shards failed" in script
    assert "exit 1" in script
    assert "continue-on-error" not in script
    assert "|| true" not in script


def test_offline_tests_selective_refuses_unsharded_full_suite() -> None:
    """FULL inside offline-tests-selective must fail closed, not run offline_test_suite."""

    script = (REPOSITORY_ROOT / "scripts" / "ci_gate.sh").read_text(encoding="utf-8")
    selective = script.split("offline_test_suite_selective() {", 1)[1].split(
        "offline_test_suite_shard() {", 1
    )[0]
    assert 'if [ "${selection}" = "FULL" ]; then' in selective
    assert "return 1" in selective.split("FULL", 1)[1].split("NONE", 1)[0]
    call_lines = [
        line.strip()
        for line in selective.splitlines()
        if line.strip() == "offline_test_suite"
        or line.strip().startswith("offline_test_suite ")
    ]
    assert call_lines == []
    assert "continue-on-error" not in selective
    assert "offline-tests-shard" in selective.split("FULL", 1)[1].split("NONE", 1)[0]


def test_python_min_smoke_script_still_executes_import_and_contract_suite() -> None:
    script = (REPOSITORY_ROOT / "scripts" / "ci_gate.sh").read_text(encoding="utf-8")
    smoke = script.split("python_min_smoke() {", 1)[1].split("run_all() {", 1)[0]
    assert "from src.api.app import app" in smoke
    assert "tests/test_ci_workflow.py" in smoke
    assert "tests/test_api_schema_pydantic.py" in smoke
    assert "tests/test_error_envelope_contract.py" in smoke
    assert "|| true" not in smoke


def test_python_minimum_pr_smoke_remains_honest() -> None:
    """PR still runs a real 3.10 smoke; it must not skip, degrade, or go unsharded-full."""

    workflow = _workflow()
    job = workflow["jobs"]["python-minimum"]
    changes_job = workflow["jobs"]["changes"]

    assert job["name"] == "python-minimum"
    assert job["needs"] == ["changes", "ai-governance", "python-minimum-tests"]
    assert job["if"] == "always() && needs.changes.outputs.backend == 'true'"
    assert job["permissions"] == {"contents": "read"}
    _assert_job_fail_closed(job)
    assert job["timeout-minutes"] <= 20
    assert "backend" in changes_job["outputs"]
    assert "docker" in changes_job["outputs"]

    setup_steps = [
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert len(setup_steps) == 1
    assert setup_steps[0]["with"]["python-version"] == "3.10"
    assert setup_steps[0]["if"] == "github.event_name == 'pull_request'"

    smoke_steps = [
        step
        for step in job["steps"]
        if step.get("run", "").strip() == "./scripts/ci_gate.sh python-min-smoke"
    ]
    assert len(smoke_steps) == 1
    assert smoke_steps[0]["if"] == "github.event_name == 'pull_request'"
    assert smoke_steps[0].get("continue-on-error", False) is False

    unsharded = [
        step
        for step in job["steps"]
        if "./scripts/ci_gate.sh offline-tests" in step.get("run", "")
        and "offline-tests-shard" not in step.get("run", "")
        and "offline-tests-selective" not in step.get("run", "")
        and "offline-tests-combine" not in step.get("run", "")
    ]
    assert unsharded == []


def test_python_minimum_push_covers_sharded_python_310_suite() -> None:
    """Push-to-main must still execute the full offline suite on Python 3.10."""

    workflow = _workflow()
    job = workflow["jobs"]["python-minimum-tests"]
    backend_shards = workflow["jobs"]["backend-tests"]

    assert job["name"] == "python-minimum-tests (${{ matrix.shard }}/4)"
    assert job["needs"] == ["changes", "ai-governance"]
    assert job["if"] == (
        "needs.changes.outputs.backend == 'true' && github.event_name == 'push'"
    )
    assert job["permissions"] == {"contents": "read"}
    _assert_job_fail_closed(job)
    assert backend_shards["timeout-minutes"] == 30
    assert job["timeout-minutes"] == 45
    assert job["timeout-minutes"] > backend_shards["timeout-minutes"]
    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["matrix"]["shard"] == [1, 2, 3, 4]

    setup_steps = [
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert len(setup_steps) == 1
    assert setup_steps[0]["with"]["python-version"] == "3.10"

    checkout = next(
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"]["fetch-depth"] == 0

    shard_steps = [
        step
        for step in job["steps"]
        if "offline-tests-shard" in step.get("run", "")
    ]
    assert len(shard_steps) == 1
    env = shard_steps[0]["env"]
    assert env["PYTEST_SPLITS"] == "4"
    assert env["PYTEST_GROUP"] == "${{ matrix.shard }}"
    assert env["PYTEST_FIRST_SHARD_OVERHEAD"] == "0"
    assert "COVERAGE_SHARD_DIR" in env

    runs = [step.get("run", "") for step in job["steps"] if "run" in step]
    assert not any("ci_gate.sh syntax" in command for command in runs)
    assert not any("ci_gate.sh flake8" in command for command in runs)
    assert not any("ci_gate.sh deterministic" in command for command in runs)
    assert not any(
        command.strip() == "./scripts/ci_gate.sh offline-tests" for command in runs
    )
    assert not any(
        step.get("uses", "").startswith("actions/upload-artifact@")
        for step in job["steps"]
    )


def test_python_minimum_shards_cover_every_offline_test_module_once() -> None:
    """The 3.10 push matrix reuses the same 4-way partitioner as backend-tests."""

    from scripts.ci_test_shard import (
        discover_test_files,
        load_durations,
        partition_test_files,
    )

    workflow = _workflow()
    job = workflow["jobs"]["python-minimum-tests"]
    backend = workflow["jobs"]["backend-tests"]
    assert job["strategy"]["matrix"]["shard"] == backend["strategy"]["matrix"]["shard"]

    files = discover_test_files()
    groups, _totals = partition_test_files(
        files,
        load_durations(),
        splits=4,
        initial_totals=[0.0, 0.0, 0.0, 0.0],
    )
    covered = [path for group in groups for path in group]
    assert sorted(covered) == sorted(files)
    assert all(group for group in groups)


def test_python_minimum_shard_timeout_covers_py310_shard_two_cost() -> None:
    """3.10 shard 2 is ~28-30 min on hosted runners; a 30-minute job bound cancels it.

    Hosted counterexample: main run 32269161288 job 96121339880 cancelled at
    30:24 after the test step ran 29:16, still passing tests at 99%. Prior
    post-#1378 main runs finished the same shard in 29:24 / 29:27 / 29:52.
    Keep four shards, full coverage, and fail-closed aggregation; do not
    restore the unsharded 60-minute python-minimum job.
    """

    workflow = _workflow()
    py310 = workflow["jobs"]["python-minimum-tests"]
    py311 = workflow["jobs"]["backend-tests"]
    aggregator = workflow["jobs"]["python-minimum"]

    assert py311["timeout-minutes"] == 30
    assert py310["timeout-minutes"] == 45
    assert py310["timeout-minutes"] > py311["timeout-minutes"]
    assert py310["timeout-minutes"] < 60
    assert py310["strategy"]["fail-fast"] is False
    assert py310["strategy"]["matrix"]["shard"] == [1, 2, 3, 4]
    _assert_job_fail_closed(py310)
    _assert_job_fail_closed(aggregator)


def test_python_minimum_aggregator_cannot_mask_failed_or_cancelled_shard() -> None:
    """Required check python-minimum must fail when any 3.10 shard is not success."""

    workflow = _workflow()
    job = workflow["jobs"]["python-minimum"]
    require = next(
        step
        for step in job["steps"]
        if step.get("name") == "✅ Require python-minimum prerequisites"
    )

    assert "if" not in require
    assert require.get("continue-on-error", False) is False
    env = require["env"]
    assert env["TESTS_RESULT"] == "${{ needs.python-minimum-tests.result }}"
    assert env["AI_RESULT"] == "${{ needs.ai-governance.result }}"
    assert env["EVENT_NAME"] == "${{ github.event_name }}"
    script = require["run"]
    assert '[ "${EVENT_NAME}" = "push" ]' in script
    assert '[ "${TESTS_RESULT}" != "success" ]' in script
    assert "python-minimum-tests shards failed" in script
    assert "exit 1" in script
    assert "continue-on-error" not in script
    assert "|| true" not in script


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
        "⏱ Runtime performance budgets": (
            "node scripts/check-runtime-performance.mjs --print --warmup 1 --repeat 3"
        ),
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


def test_web_gate_runtime_budgets_use_per_scenario_gates_not_global_soft():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    web_job = workflow["jobs"]["web-gate"]
    steps = web_job["steps"]
    runtime = next(
        step for step in steps if step.get("name") == "⏱ Runtime performance budgets"
    )
    unit = next(step for step in steps if step.get("name") == "🧪 Unit tests")
    build = next(step for step in steps if step.get("name") == "🏗️ Build")

    assert steps.index(unit) < steps.index(runtime) < steps.index(build)
    assert runtime["run"] == (
        "node scripts/check-runtime-performance.mjs --print --warmup 1 --repeat 3"
    )
    assert "--soft" not in runtime["run"]
    assert runtime["if"] == FRONTEND_EXECUTION_CONDITION
    assert runtime.get("continue-on-error", False) is False


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


def test_ci_gate_deterministic_fail_closes_config_registry_gaps() -> None:
    """A documented env key missing from the registry must fail the CI path."""

    script = (REPOSITORY_ROOT / "scripts" / "ci_gate.sh").read_text(encoding="utf-8")
    deterministic = script.split("deterministic_checks() {", 1)[1].split(
        "_run_pytest_offline() {", 1
    )[0]
    assert "python scripts/check_config_access.py --self-test" in deterministic
    assert "python scripts/check_config_access.py" in deterministic
    assert "python scripts/check_config_doc_consistency.py --self-test" in deterministic
    assert (
        "python scripts/check_config_doc_consistency.py --fail-on all" in deterministic
    )
    checker_lines = [
        line.strip()
        for line in deterministic.splitlines()
        if "check_config_doc_consistency.py" in line
    ]
    assert checker_lines == [
        "python scripts/check_config_doc_consistency.py --self-test",
        "python scripts/check_config_doc_consistency.py --fail-on all",
    ]
    assert all("|| true" not in line for line in checker_lines)
    access_idx = deterministic.find("python scripts/check_config_access.py\n")
    consistency_idx = deterministic.find(
        "python scripts/check_config_doc_consistency.py --self-test"
    )
    assert access_idx != -1
    assert consistency_idx != -1
    assert access_idx < consistency_idx


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


def _ocr_stock_extractor_job() -> dict:
    return _workflow()["jobs"]["ocr-stock-extractor"]


def _desktop_gate_job() -> dict:
    return _workflow()["jobs"]["desktop-gate"]


def _path_filters() -> dict:
    changes = _workflow()["jobs"]["changes"]
    filter_step = next(step for step in changes["steps"] if step.get("id") == "filter")
    return yaml.safe_load(filter_step["with"]["filters"])


def _assert_path_filter_entry_exists(relative: str) -> None:
    if relative.endswith("/**"):
        directory = REPOSITORY_ROOT / relative[:-3]
        assert directory.is_dir(), relative
        return
    if "*" in relative:
        matches = list(REPOSITORY_ROOT.glob(relative))
        assert matches, relative
        return
    assert (REPOSITORY_ROOT / relative).is_file(), relative


def _path_filter_covers(relative: str, filters: set[str]) -> bool:
    for entry in filters:
        if entry.endswith("/**"):
            prefix = entry[:-2]  # keep the trailing slash
            if relative.startswith(prefix):
                return True
            continue
        if fnmatch(relative, entry):
            return True
    return False


def test_changes_job_exposes_ocr_and_desktop_path_filters() -> None:
    workflow = _workflow()
    changes = workflow["jobs"]["changes"]
    filters = _path_filters()

    assert changes["outputs"]["ocr_extractor"] == (
        "${{ steps.filter.outputs.ocr_extractor }}"
    )
    assert changes["outputs"]["desktop"] == "${{ steps.filter.outputs.desktop }}"
    assert set(filters["ocr_extractor"]) == set(OCR_EXTRACTOR_PATH_FILTER)
    assert set(filters["desktop"]) == set(DESKTOP_PATH_FILTER)
    for relative in (*OCR_EXTRACTOR_PATH_FILTER, *DESKTOP_PATH_FILTER):
        _assert_path_filter_entry_exists(relative)


def test_desktop_path_filter_covers_files_pinned_by_desktop_unit_tests() -> None:
    """Changing repo-root files that npm test reads must not skip desktop-gate."""

    filters = set(_path_filters()["desktop"])
    main_test = (
        REPOSITORY_ROOT / "apps" / "dsa-desktop" / "tests" / "main.test.js"
    ).read_text(encoding="utf-8")
    macos_test = (
        REPOSITORY_ROOT / "apps" / "dsa-desktop" / "tests" / "macos-packaging.test.js"
    ).read_text(encoding="utf-8")
    ollama_test = (
        REPOSITORY_ROOT
        / "apps"
        / "dsa-desktop"
        / "tests"
        / "embedded-ollama-build.test.js"
    ).read_text(encoding="utf-8")

    assert "verify-desktop-updater-artifacts.ps1" in main_test
    assert "build-backend-macos.sh" in macos_test
    assert "build-desktop-macos.sh" in macos_test
    assert "prepare-embedded-ollama" in ollama_test
    assert "THIRD_PARTY_NOTICES" in ollama_test
    assert "desktop-release.yml" in main_test

    for relative in DESKTOP_TEST_PINNED_REPO_FILES:
        _assert_path_filter_entry_exists(relative)
        assert _path_filter_covers(relative, filters), relative

    build_all_macos = (REPOSITORY_ROOT / "scripts" / "build-all-macos.sh").read_text(
        encoding="utf-8"
    )
    build_all_windows = (REPOSITORY_ROOT / "scripts" / "build-all.ps1").read_text(
        encoding="utf-8"
    )
    assert "build-backend-macos.sh" in build_all_macos
    assert "build-backend.ps1" in build_all_windows
    assert _path_filter_covers("scripts/build-backend-macos.sh", filters)
    assert _path_filter_covers("scripts/build-backend.ps1", filters)


def test_ocr_path_filter_covers_files_executed_by_ocr_job() -> None:
    """OCR job pytest files, sources, and fixtures must all trigger the matrix."""

    filters = set(_path_filters()["ocr_extractor"])
    ocr_job = _ocr_stock_extractor_job()
    test_step = next(
        step
        for step in ocr_job["steps"]
        if step.get("name")
        == "✅ OCR stock-extractor tests (dependency skips are failures)"
    )
    for relative in OCR_EXTRACTOR_TEST_FILES:
        assert relative in test_step["run"]
        assert relative in filters
    for relative in OCR_EXTRACTOR_SOURCE_FILES:
        assert relative in filters
    extraction_test = (
        REPOSITORY_ROOT / "tests" / "services" / "test_ocr_extraction_service.py"
    ).read_text(encoding="utf-8")
    assert "fixtures" in extraction_test and "multimodal" in extraction_test
    assert "sample_financial_report.pdf" in extraction_test
    assert "tests/fixtures/ocr/**" in filters
    assert "tests/fixtures/multimodal/sample_financial_report.pdf" in filters


def test_ocr_stock_extractor_is_path_triggered_fail_closed_and_offline() -> None:
    job = _ocr_stock_extractor_job()
    steps_by_name = {step["name"]: step for step in job["steps"]}
    validation = steps_by_name["🔒 Validate ocr-stock-extractor prerequisites"]
    no_ocr = steps_by_name["No OCR extractor changes"]
    test_step = steps_by_name["✅ OCR stock-extractor tests (dependency skips are failures)"]
    import_step = steps_by_name["🔎 Assert OCR imports"]
    tesseract_step = steps_by_name["🔤 Install Tesseract OCR engine"]

    assert job["name"] == "ocr-stock-extractor"
    assert job["needs"] == ["changes", "ai-governance"]
    assert job["if"] == "${{ always() && !cancelled() }}"
    assert job["timeout-minutes"] <= 25
    assert job["permissions"] == {"contents": "read"}
    _assert_job_fail_closed(job)
    assert "secrets." not in yaml.safe_dump(job)
    assert validation["if"] == (
        "${{ always() && (needs.ai-governance.result != 'success' || "
        "needs.changes.result != 'success' || "
        "(needs.changes.outputs.ocr_extractor != 'true' && "
        "needs.changes.outputs.ocr_extractor != 'false')) }}"
    )
    assert validation["run"].rstrip().endswith("exit 1")
    assert no_ocr["if"] == (
        "${{ needs.ai-governance.result == 'success' && "
        "needs.changes.result == 'success' && "
        "needs.changes.outputs.ocr_extractor == 'false' }}"
    )
    assert "exit 1" not in no_ocr["run"]
    assert test_step["if"] == OCR_EXECUTION_CONDITION
    assert import_step["if"] == OCR_EXECUTION_CONDITION
    assert tesseract_step["if"] == OCR_EXECUTION_CONDITION
    assert '-m "not network"' in test_step["run"]
    assert "pytest -m network" not in test_step["run"]
    for relative in OCR_EXTRACTOR_TEST_FILES:
        assert relative in test_step["run"]
    assert "must execute stock-extractor tests, not skip them" in test_step["run"]
    assert "system Tesseract + pytesseract not installed" in test_step["run"]
    assert "assess_ocr_dependencies" in import_step["run"]
    assert "requirements-ocr.txt" in steps_by_name[
        "📦 Install dependencies (native + optional OCR)"
    ]["run"]
    assert "tesseract-ocr-eng" in tesseract_step["run"]
    assert "|| true" not in tesseract_step["run"]
    assert "continue-on-error" not in tesseract_step["run"]
    assert "/etc/apt/apt-mirrors.txt" in tesseract_step["run"]
    assert "azure.archive.ubuntu.com" in tesseract_step["run"]
    assert "prefer_runner_public_archive" in tesseract_step["run"]
    assert "/var/lib/apt/lists/partial" in tesseract_step["run"]


def test_desktop_gate_runs_existing_unit_tests_without_packaging() -> None:
    job = _desktop_gate_job()
    steps_by_name = {step["name"]: step for step in job["steps"]}
    validation = steps_by_name["🔒 Validate desktop-gate prerequisites"]
    no_desktop = steps_by_name["No desktop changes"]
    install = steps_by_name["📦 Install"]
    unit = steps_by_name["🧪 Unit tests"]

    assert job["name"] == "desktop-gate"
    assert job["needs"] == ["changes", "ai-governance"]
    assert job["if"] == "${{ always() && !cancelled() }}"
    assert job["timeout-minutes"] <= 20
    assert job["permissions"] == {"contents": "read"}
    assert job["defaults"]["run"]["working-directory"] == "apps/dsa-desktop"
    _assert_job_fail_closed(job)
    assert "secrets." not in yaml.safe_dump(job)
    assert validation["if"] == (
        "${{ always() && (needs.ai-governance.result != 'success' || "
        "needs.changes.result != 'success' || "
        "(needs.changes.outputs.desktop != 'true' && "
        "needs.changes.outputs.desktop != 'false')) }}"
    )
    assert validation["working-directory"] == "."
    assert validation["run"].rstrip().endswith("exit 1")
    assert no_desktop["if"] == (
        "${{ needs.ai-governance.result == 'success' && "
        "needs.changes.result == 'success' && "
        "needs.changes.outputs.desktop == 'false' }}"
    )
    assert no_desktop["working-directory"] == "."
    assert "exit 1" not in no_desktop["run"]
    assert install["if"] == DESKTOP_EXECUTION_CONDITION
    assert unit["if"] == DESKTOP_EXECUTION_CONDITION
    assert install["run"] == "npm ci"
    assert unit["run"] == "npm test"
    assert install["env"]["ELECTRON_SKIP_BINARY_DOWNLOAD"] == "1"
    assert unit["env"]["ELECTRON_SKIP_BINARY_DOWNLOAD"] == "1"
    runs = [step.get("run", "") for step in job["steps"] if "run" in step]
    assert "npm run build" not in runs
    assert not any("electron-builder" in command for command in runs)
    assert not any("prepare:ollama" in command for command in runs)
    assert not any("build-all" in command for command in runs)
