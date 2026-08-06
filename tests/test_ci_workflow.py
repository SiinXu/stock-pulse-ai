"""Guard the hosted CI contract for the minimum supported Python runtime."""

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


def test_python_minimum_job_uses_smoke_on_pr_and_full_offline_on_push():
    """PR uses 3.10 smoke; push-to-main keeps a full offline suite on the floor."""

    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
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

    assert backend_job["needs"] == ["changes", "ai-governance"]
    assert backend_job["if"] == "needs.changes.outputs.backend == 'true'"
    assert "backend" in changes_job["outputs"]
    assert "docker" in changes_job["outputs"]
    assert changes_job["outputs"]["backend"].startswith(
        "${{ steps.backend-filter.outputs.backend_non_web == 'true'"
    )

    setup_steps = [
        step
        for step in job["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert len(setup_steps) == 1
    assert setup_steps[0]["with"]["python-version"] == "3.10"

    backend_setup_steps = [
        step
        for step in backend_job["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert len(backend_setup_steps) == 1
    assert backend_setup_steps[0]["with"]["python-version"] == "3.11"

    run_commands = [step["run"] for step in job["steps"] if "run" in step]
    assert any("--constraint constraints.txt" in command for command in run_commands)
    assert any(
        "--build-constraint build-constraints.txt" in command
        for command in run_commands
    )
    assert any("-r .github/requirements-ci.txt" in command for command in run_commands)
    assert any("python -m pip check" in command for command in run_commands)

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

    selective_backend = [
        step
        for step in backend_job["steps"]
        if "offline-tests-selective" in step.get("run", "")
    ]
    assert len(selective_backend) == 1
    assert selective_backend[0]["if"] == "github.event_name == 'pull_request'"

    full_backend = [
        step
        for step in backend_job["steps"]
        if step.get("run", "").strip() == "./scripts/ci_gate.sh offline-tests"
    ]
    assert len(full_backend) == 1
    assert full_backend[0]["if"] == "github.event_name != 'pull_request'"


def test_docker_build_skips_when_docker_paths_unchanged():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["docker-build"]
    assert job["needs"] == ["changes", "ai-governance"]
    assert job["if"] == "needs.changes.outputs.docker == 'true'"


def test_ci_gate_offline_suite_emits_slow_test_durations():
    script = (REPOSITORY_ROOT / "scripts" / "ci_gate.sh").read_text(encoding="utf-8")
    assert "--durations=30" in script
    assert "--durations-min=0.5" in script


def test_pytest_testpaths_scopes_to_tests_package():
    setup_cfg = (REPOSITORY_ROOT / "setup.cfg").read_text(encoding="utf-8")
    assert "testpaths = tests" in setup_cfg
