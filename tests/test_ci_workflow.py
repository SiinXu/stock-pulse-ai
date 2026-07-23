"""Guard the hosted CI contract for the minimum supported Python runtime."""

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


def test_python_minimum_job_runs_full_backend_gate_on_python_3_10():
    """Keep a blocking full backend gate on the declared Python floor."""

    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    job = workflow["jobs"]["python-minimum"]
    backend_job = workflow["jobs"]["backend-gate"]

    assert job["name"] == "python-minimum"
    assert job["needs"] == ["ai-governance"]
    assert job["permissions"] == {"contents": "read"}
    assert "if" not in job
    assert job.get("continue-on-error", False) is False
    assert all(
        step.get("continue-on-error", False) is False for step in job["steps"]
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
    gate_steps = [
        step
        for step in job["steps"]
        if step.get("run", "").strip() == "./scripts/ci_gate.sh"
    ]
    assert len(gate_steps) == 1
    assert "if" not in gate_steps[0]
