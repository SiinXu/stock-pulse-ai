#!/usr/bin/env python3
"""Check safe diagnostics from one real authenticated Playwright failure."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from zipfile import is_zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.stage_playwright_diagnostics import (  # noqa: E402
    JPEG_SIGNATURE,
    PNG_SIGNATURE,
    WEBM_EBML_SIGNATURE,
    stage_playwright_diagnostics,
)


WEB_ROOT = REPO_ROOT / "apps" / "dsa-web"
GENERATED_SPEC = WEB_ROOT / "e2e" / "c07-failure-harness.generated.spec.ts"
SCANNER = REPO_ROOT / "scripts" / "scan_playwright_artifacts.py"
DEFAULT_CANARY = "stockpulse-c07-failure-canary-4f8219d37a6c"
MEDIA_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".webm"})
MEDIA_SIGNATURES = (PNG_SIGNATURE, JPEG_SIGNATURE, WEBM_EBML_SIGNATURE)
FAILURE_TEST_TITLE = "C-07 authenticated intentional failure harness"
INTENTIONAL_FAILURE_MARKER = "C07_EXPECTED_POST_AUTH_FAILURE"
SENSITIVE_ENV_NAME = re.compile(
    r"(?:API[_-]?KEY|AUTH|COOKIE|CREDENTIAL|PASSWORD|SECRET|SESSION|TOKEN)",
    re.IGNORECASE,
)
SPEC_SOURCE = (
    "import { expect, test } from '@playwright/test';\n"
    "import { loginAsE2eAdmin } from './auth-fixture';\n\n"
    f"test({FAILURE_TEST_TITLE!r}, async ({{ page }}) => {{\n"
    "  await loginAsE2eAdmin(page);\n"
    "  await expect(page).toHaveURL('/');\n"
    f"  throw new Error({INTENTIONAL_FAILURE_MARKER!r});\n"
    "});\n"
)


def _available_ports(count: int) -> tuple[int, ...]:
    listeners: list[socket.socket] = []
    try:
        for _index in range(count):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(("127.0.0.1", 0))
            listeners.append(listener)
        return tuple(int(listener.getsockname()[1]) for listener in listeners)
    finally:
        for listener in listeners:
            listener.close()


def _isolated_environment(run_id: str, canary: str) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not SENSITIVE_ENV_NAME.search(key)
    }
    interpreter_bin = str(Path(sys.executable).resolve().parent)
    existing_path = environment.get("PATH", "")
    environment["PATH"] = os.pathsep.join(
        part for part in (interpreter_bin, existing_path) if part
    )
    backend_port, frontend_port, provider_port = _available_ports(3)
    environment.update({
        "DSA_PLAYWRIGHT_ARTIFACT_CANARY": canary,
        "DSA_WEB_E2E_ALPHA_API_KEY": canary,
        "DSA_WEB_E2E_CREDENTIAL_BEARING": "true",
        "DSA_WEB_E2E_INTENTIONAL_FAILURE_HARNESS": "true",
        "DSA_WEB_E2E_RUN_ID": run_id,
        "DSA_WEB_E2E_TRACE": "off",
        "DSA_WEB_SMOKE_BACKEND_PORT": str(backend_port),
        "DSA_WEB_SMOKE_FRONTEND_PORT": str(frontend_port),
        "DSA_WEB_SMOKE_PASSWORD": "dsa-c07-failure-harness",
        "DSA_WEB_SMOKE_PROVIDER_PORT": str(provider_port),
    })
    return environment


def _resolved_result_root(run_id: str, result_parent: Path) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id) or run_id in {".", ".."}:
        raise ValueError(
            "run ID must resolve to one portable test-results child directory"
        )
    resolved_parent = result_parent.resolve()
    candidate = resolved_parent / run_id
    if candidate.is_symlink():
        raise ValueError("Playwright failure result directory cannot be a symbolic link")
    resolved_candidate = candidate.resolve()
    if resolved_candidate.parent != resolved_parent:
        raise ValueError("Playwright failure result directory escaped test-results")
    return resolved_candidate


def _remove_result_root(run_id: str, result_parent: Path) -> None:
    result_root = _resolved_result_root(run_id, result_parent)
    shutil.rmtree(result_root, ignore_errors=True)


def _run_scanner(root: Path, environment: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, str(SCANNER), str(root)],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Playwright artifact scanner rejected the harness diagnostics:\n"
            + result.stderr
        )


def _iter_report_specs(suites: object):
    if not isinstance(suites, list):
        return
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        specs = suite.get("specs")
        if isinstance(specs, list):
            yield from (spec for spec in specs if isinstance(spec, dict))
        yield from _iter_report_specs(suite.get("suites"))


def _has_intentional_failure(spec: dict[str, object]) -> bool:
    file_name = spec.get("file")
    normalized_file = str(file_name).replace("\\", "/") if file_name else ""
    if (
        spec.get("title") != FAILURE_TEST_TITLE
        or normalized_file.rsplit("/", 1)[-1] != GENERATED_SPEC.name
    ):
        return False

    tests = spec.get("tests")
    if not isinstance(tests, list):
        return False
    accepted_messages = {
        INTENTIONAL_FAILURE_MARKER,
        f"Error: {INTENTIONAL_FAILURE_MARKER}",
    }
    for test in tests:
        if (
            not isinstance(test, dict)
            or test.get("expectedStatus") != "passed"
            or test.get("status") != "unexpected"
        ):
            continue
        results = test.get("results")
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict) or result.get("status") != "failed":
                continue
            error = result.get("error")
            if not isinstance(error, dict):
                continue
            message = error.get("message")
            if isinstance(message, str) and message.strip() in accepted_messages:
                return True
    return False


def _assert_failure_report(result_root: Path) -> None:
    report_path = result_root / "playwright-results.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    stats = report.get("stats")
    if not isinstance(stats, dict) or stats.get("unexpected") != 1:
        raise RuntimeError("Playwright JSON reporter did not record the intentional failure")
    matching_failures = sum(
        _has_intentional_failure(spec)
        for spec in _iter_report_specs(report.get("suites"))
    )
    if matching_failures != 1:
        raise RuntimeError(
            "Playwright JSON reporter did not reach the intentional post-auth failure"
        )


def _assert_service_logs(result_root: Path) -> None:
    log_root = result_root / "service-logs"
    required = ("backend.log", "fake-provider.log", "vite.log")
    missing = [name for name in required if not (log_root / name).is_file()]
    if missing:
        raise RuntimeError(f"Playwright failure diagnostics are missing service logs: {missing}")


def _assert_no_trace_or_media(result_root: Path) -> None:
    for path in result_root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("Playwright failure diagnostics unexpectedly contain a symbolic link")
        if not path.is_file():
            continue
        sample = path.read_bytes()[:8192]
        if path.suffix.lower() == ".zip" or is_zipfile(path):
            raise RuntimeError("Credential-bearing failure diagnostics unexpectedly contain an archive")
        if path.suffix.lower() in MEDIA_SUFFIXES or sample.startswith(MEDIA_SIGNATURES):
            raise RuntimeError("Credential-bearing failure diagnostics unexpectedly contain media")


def verify_failure_diagnostics(run_id: str, *, keep_results: bool = False) -> Path:
    if GENERATED_SPEC.exists() or GENERATED_SPEC.is_symlink():
        raise RuntimeError(f"Refusing to overwrite existing harness spec: {GENERATED_SPEC}")

    result_parent = WEB_ROOT / "test-results"
    result_root = _resolved_result_root(run_id, result_parent)
    _remove_result_root(run_id, result_parent)
    environment = _isolated_environment(run_id, DEFAULT_CANARY)
    npm = shutil.which("npm", path=environment.get("PATH"))
    if not npm:
        raise RuntimeError("npm is required for the Playwright failure harness")

    try:
        GENERATED_SPEC.write_text(SPEC_SOURCE, encoding="utf-8")
        result = subprocess.run(
            [
                npm,
                "run",
                "test:smoke",
                "--",
                "e2e/c07-failure-harness.generated.spec.ts",
                "--workers=1",
                "--retries=0",
            ],
            cwd=WEB_ROOT,
            env=environment,
            check=False,
        )
        if result.returncode == 0:
            raise RuntimeError("Intentional Playwright failure unexpectedly exited successfully")
        if not result_root.is_dir():
            raise RuntimeError("Playwright did not create the expected failure run directory")

        _assert_failure_report(result_root)
        _assert_service_logs(result_root)
        _assert_no_trace_or_media(result_root)
        _run_scanner(result_root, environment)
        with tempfile.TemporaryDirectory(prefix="stockpulse-c07-staged-") as temporary:
            staging_root = Path(temporary) / "playwright-upload"
            manifest = stage_playwright_diagnostics(result_root, staging_root)
            if not any(entry["path"].startswith("service-logs/") for entry in manifest["files"]):
                raise RuntimeError("Staged failure diagnostics contain no service logs")
            _run_scanner(staging_root, environment)
    finally:
        GENERATED_SPEC.unlink(missing_ok=True)
        if not keep_results:
            _remove_result_root(run_id, result_parent)

    return result_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        default=f"c07-intentional-failure-{os.getpid()}",
    )
    parser.add_argument("--keep-results", action="store_true")
    args = parser.parse_args(argv)
    try:
        result_root = verify_failure_diagnostics(
            args.run_id,
            keep_results=args.keep_results,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"Playwright failure diagnostics verification failed: {error}", file=sys.stderr)
        return 1
    disposition = "retained" if args.keep_results else "cleaned"
    print(
        "Playwright authenticated failure diagnostics verified: "
        f"raw scan passed, staged scan passed, results {disposition} ({result_root.name})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
