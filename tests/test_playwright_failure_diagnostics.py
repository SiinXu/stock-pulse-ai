from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import check_playwright_failure_diagnostics as failure_diagnostics


def _write_failure_report(
    result_root: Path,
    *,
    message: str,
    snippet: str | None = None,
    title: str = failure_diagnostics.FAILURE_TEST_TITLE,
) -> None:
    error: dict[str, str] = {"message": message}
    if snippet is not None:
        error["snippet"] = snippet
    expanded_error = {"message": message}
    if snippet is not None:
        expanded_error["message"] += f"\n\n{snippet}"
    report = {
        "stats": {"unexpected": 1},
        "suites": [
            {
                "specs": [
                    {
                        "file": (
                            "e2e/"
                            + failure_diagnostics.GENERATED_SPEC.name
                        ),
                        "title": title,
                        "tests": [
                            {
                                "expectedStatus": "passed",
                                "status": "unexpected",
                                "results": [
                                    {
                                        "status": "failed",
                                        "error": error,
                                        "errors": [expanded_error],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ],
    }
    result_root.mkdir()
    (result_root / "playwright-results.json").write_text(
        json.dumps(report),
        encoding="utf-8",
    )


def test_failure_report_requires_the_post_auth_marker(tmp_path: Path) -> None:
    result_root = tmp_path / "expected-failure"
    _write_failure_report(
        result_root,
        message=f"Error: {failure_diagnostics.INTENTIONAL_FAILURE_MARKER}",
    )

    failure_diagnostics._assert_failure_report(result_root)


def test_failure_report_rejects_an_earlier_login_failure(tmp_path: Path) -> None:
    result_root = tmp_path / "login-failure"
    _write_failure_report(
        result_root,
        message="Error: login did not complete",
        snippet=(
            "throw new Error("
            f"'{failure_diagnostics.INTENTIONAL_FAILURE_MARKER}'"
            ");"
        ),
    )

    with pytest.raises(RuntimeError, match="did not reach the intentional post-auth"):
        failure_diagnostics._assert_failure_report(result_root)


def test_failure_report_rejects_marker_from_another_spec(tmp_path: Path) -> None:
    result_root = tmp_path / "wrong-spec"
    _write_failure_report(
        result_root,
        message=f"Error: {failure_diagnostics.INTENTIONAL_FAILURE_MARKER}",
        title="unrelated failure",
    )

    with pytest.raises(RuntimeError, match="did not reach the intentional post-auth"):
        failure_diagnostics._assert_failure_report(result_root)


def test_failure_harness_rejects_parent_run_id_before_deletion(tmp_path: Path) -> None:
    result_parent = tmp_path / "test-results"
    result_parent.mkdir()
    marker = tmp_path / "keep.txt"
    marker.write_text("keep\n", encoding="utf-8")

    with pytest.raises(ValueError, match="one portable test-results child"):
        failure_diagnostics._remove_result_root("..", result_parent)

    assert marker.read_text(encoding="utf-8") == "keep\n"
    assert result_parent.is_dir()


def test_failure_harness_rejects_current_directory_run_id(tmp_path: Path) -> None:
    result_parent = tmp_path / "test-results"
    result_parent.mkdir()

    with pytest.raises(ValueError, match="one portable test-results child"):
        failure_diagnostics._resolved_result_root(".", result_parent)

    assert result_parent.is_dir()


def test_failure_harness_revalidates_symlink_before_deletion(tmp_path: Path) -> None:
    result_parent = tmp_path / "test-results"
    result_parent.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("keep\n", encoding="utf-8")
    (result_parent / "linked-run").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="cannot be a symbolic link"):
        failure_diagnostics._remove_result_root("linked-run", result_parent)

    assert marker.read_text(encoding="utf-8") == "keep\n"


def test_failure_harness_prepends_the_active_interpreter_to_the_callers_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    portable_path = os.pathsep.join((
        str(tmp_path / "python-bin"),
        str(tmp_path / "node-bin"),
    ))
    monkeypatch.setenv("PATH", portable_path)

    environment = failure_diagnostics._isolated_environment(
        "portable-run",
        "stockpulse-portable-test-canary",
    )

    path_entries = environment["PATH"].split(os.pathsep)
    assert path_entries[0] == str(Path(sys.executable).resolve().parent)
    assert os.pathsep.join(path_entries[1:]) == portable_path
    source = Path(failure_diagnostics.__file__).read_text(encoding="utf-8")
    unix_user_root = str(Path(os.sep) / "Users") + os.sep
    windows_user_root = "C:" + chr(92) + "Users" + chr(92)
    assert unix_user_root not in source
    assert windows_user_root not in source


@pytest.mark.parametrize(
    (
        "run_id",
        "port_environment",
        "run_directory_name",
        "link_result_root",
        "expected_error",
    ),
    [
        (
            "symlink-policy",
            {},
            "symlink-policy",
            False,
            "Playwright run directory cannot be a symbolic link.",
        ),
        (
            None,
            {
                "DSA_WEB_SMOKE_BACKEND_PORT": "018100",
                "DSA_WEB_SMOKE_FRONTEND_PORT": "014173",
                "DSA_WEB_SMOKE_PROVIDER_PORT": "018101",
            },
            "18100-14173-18101",
            False,
            "Playwright run directory cannot be a symbolic link.",
        ),
        (
            "symlink-policy",
            {},
            "symlink-policy",
            True,
            "Playwright test-results directory cannot be a symbolic link.",
        ),
    ],
    ids=("explicit-run-id", "numeric-default-run-id", "result-root-symlink"),
)
def test_repository_playwright_entrypoint_rejects_a_symlink_before_cli_resolution(
    tmp_path: Path,
    run_id: str | None,
    port_environment: dict[str, str],
    run_directory_name: str,
    link_result_root: bool,
    expected_error: str,
) -> None:
    source_e2e_root = failure_diagnostics.WEB_ROOT / "e2e"
    source_entrypoint = source_e2e_root / "run-playwright-tests.mjs"
    web_root = tmp_path / "isolated-web"
    e2e_root = web_root / "e2e"
    e2e_root.mkdir(parents=True)
    shutil.copy2(source_entrypoint, e2e_root / source_entrypoint.name)
    source_paths = source_e2e_root / "playwright-result-paths.mjs"
    shutil.copy2(source_paths, e2e_root / source_paths.name)
    result_parent = web_root / "test-results"
    outside = tmp_path / "outside"
    outside.mkdir()
    if link_result_root:
        result_parent.symlink_to(outside, target_is_directory=True)
    else:
        result_parent.mkdir()
        (result_parent / run_directory_name).symlink_to(
            outside,
            target_is_directory=True,
        )
    environment = os.environ.copy()
    environment.update({
        "DSA_WEB_E2E_CREDENTIAL_BEARING": "true",
        "DSA_WEB_E2E_TRACE": "off",
    })
    environment.update(port_environment)
    if run_id is None:
        environment.pop("DSA_WEB_E2E_RUN_ID", None)
    else:
        environment["DSA_WEB_E2E_RUN_ID"] = run_id

    result = subprocess.run(
        ["node", "e2e/run-playwright-tests.mjs", "--list"],
        cwd=web_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert "Cannot find module '@playwright/test/cli'" not in result.stderr
    assert list(outside.iterdir()) == []
