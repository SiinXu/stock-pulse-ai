from __future__ import annotations

import json
import os
from pathlib import Path
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


def test_repository_playwright_config_rejects_a_symlinked_run_directory(
    tmp_path: Path,
) -> None:
    web_root = failure_diagnostics.WEB_ROOT
    result_parent = web_root / "test-results"
    result_parent.mkdir(exist_ok=True)
    run_id = f"symlink-policy-{os.getpid()}-{tmp_path.name}"
    run_directory = result_parent / run_id
    run_directory.symlink_to(tmp_path, target_is_directory=True)
    environment = os.environ.copy()
    environment.update({
        "DSA_WEB_E2E_CREDENTIAL_BEARING": "true",
        "DSA_WEB_E2E_RUN_ID": run_id,
        "DSA_WEB_E2E_TRACE": "off",
    })

    try:
        result = subprocess.run(
            ["node", "e2e/run-playwright-tests.mjs", "--list"],
            cwd=web_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        run_directory.unlink(missing_ok=True)

    assert result.returncode != 0
    assert "Playwright run directory cannot be a symbolic link." in result.stderr
    assert list(tmp_path.iterdir()) == []
