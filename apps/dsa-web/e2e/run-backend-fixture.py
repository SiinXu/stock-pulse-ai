#!/usr/bin/env python3
"""Prepare and run the isolated backend used by Playwright E2E tests."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import traceback
from typing import IO, Dict


REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_ROOT = REPO_ROOT / "apps" / "dsa-web"
OUTPUT_ROOT = WEB_ROOT / "test-results"
REPORT_MARKER = "E2E_MARKDOWN_FIXTURE"
REPORT_ZH_MARKER = "E2E_ZH_REPORT_BODY_MARKER"
REPORT_EN_MARKER = "E2E_EN_REPORT_BODY_MARKER"

# The fixture imports the real application in-process to seed a report. Build a
# controlled environment before those imports so developer credentials and
# product config (LLM_*, provider keys, auth/database paths, proxies, etc.) can
# never leak into either the seed step or the backend child process.
PASSTHROUGH_ENV_KEYS = frozenset({
    "CI",
    "COMSPEC",
    "CONDA_PREFIX",
    "FORCE_COLOR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "NO_COLOR",
    "PATH",
    "PATHEXT",
    "PYTHONIOENCODING",
    "PYTHONUTF8",
    "SHELL",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TMP",
    "TMPDIR",
    "TZ",
    "USER",
    "VIRTUAL_ENV",
    "WINDIR",
})
ISOLATED_HOME_ENV_KEYS = frozenset({
    "APPDATA",
    "HOME",
    "LOCALAPPDATA",
    "USERPROFILE",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
})


def _quoted_env_value(value: str) -> str:
    """Quote one value for the isolated dotenv fixture."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _resolve_output_child(raw_value: str, default_name: str) -> Path:
    """Resolve an E2E output path and keep it below ``OUTPUT_ROOT``."""
    candidate = Path(raw_value).expanduser() if raw_value else OUTPUT_ROOT / default_name
    resolved = candidate.resolve()
    output_root = OUTPUT_ROOT.resolve()
    if resolved == output_root or output_root not in resolved.parents:
        raise ValueError(f"E2E runtime path must be below {output_root}: {resolved}")
    return resolved


def _runtime_values(runtime_dir: Path, log_dir: Path) -> Dict[str, str]:
    """Build the deterministic application configuration for Playwright."""
    return {
        "ADMIN_AUTH_ENABLED": "true",
        "DATABASE_PATH": str(runtime_dir / "stock_analysis.db"),
        # LiteLLM DEV mode implicitly searches parent directories for `.env`.
        # The fixture owns its complete environment, so disable that side effect.
        "LITELLM_MODE": "PRODUCTION",
        "LOG_DIR": str(log_dir / "backend-app"),
        "LLM_CONFIG_MODE": "auto",
        "PREFETCH_REALTIME_QUOTES": "false",
        "SCHEDULE_ENABLED": "false",
        "STOCK_INDEX_REMOTE_UPDATE_ENABLED": "false",
        "WEBUI_AUTO_BUILD": "false",
    }


def _build_isolated_environment(
    values: Dict[str, str],
    env_file: Path,
    runtime_dir: Path,
) -> Dict[str, str]:
    """Build a child environment without ambient product credentials."""
    child_env = {
        key: value
        for key, value in os.environ.items()
        if key in PASSTHROUGH_ENV_KEYS
    }
    child_env.update(values)
    child_env.update({
        "ENV_FILE": str(env_file),
        "HOME": str(runtime_dir / "home"),
        "USERPROFILE": str(runtime_dir / "home"),
        "APPDATA": str(runtime_dir / "home" / "appdata"),
        "LOCALAPPDATA": str(runtime_dir / "home" / "local-appdata"),
        "XDG_CACHE_HOME": str(runtime_dir / "home" / ".cache"),
        "XDG_CONFIG_HOME": str(runtime_dir / "home" / ".config"),
        "PYTHONUNBUFFERED": "1",
    })
    return child_env


def _assert_isolated_environment(
    child_env: Dict[str, str],
    values: Dict[str, str],
    runtime_dir: Path,
) -> None:
    """Fail fast if the backend fixture escapes its isolation boundary."""
    allowed_keys = (
        PASSTHROUGH_ENV_KEYS
        | ISOLATED_HOME_ENV_KEYS
        | set(values)
        | {"ENV_FILE", "PYTHONUNBUFFERED"}
    )
    unexpected = sorted(set(child_env) - allowed_keys)
    if unexpected:
        raise RuntimeError(f"Unexpected ambient keys in E2E backend environment: {unexpected}")

    resolved_runtime = runtime_dir.resolve()
    for key in ("DATABASE_PATH", "ENV_FILE", *ISOLATED_HOME_ENV_KEYS):
        resolved = Path(child_env[key]).resolve()
        if resolved_runtime not in resolved.parents:
            raise RuntimeError(f"{key} escaped the isolated E2E runtime: {resolved}")

    if child_env.get("ADMIN_AUTH_ENABLED") != "true":
        raise RuntimeError("Playwright backend authentication must be explicitly enabled")


def _prepare_runtime(runtime_dir: Path, log_dir: Path, log: IO[str]) -> Dict[str, str]:
    """Create isolated auth/data state and seed a deterministic report."""
    shutil.rmtree(runtime_dir, ignore_errors=True)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "home").mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    values = _runtime_values(runtime_dir, log_dir)
    env_file = runtime_dir / "playwright.env"
    env_file.write_text(
        "\n".join(f"{key}={_quoted_env_value(value)}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )

    child_env = _build_isolated_environment(values, env_file, runtime_dir)
    _assert_isolated_environment(child_env, values, runtime_dir)
    os.environ.clear()
    os.environ.update(child_env)

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from src.analyzer import AnalysisResult
    from src.config import Config
    from src.services.history_service import HistoryService
    from src.storage import DatabaseManager

    Config._instance = None
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    seeded_reports = [
        AnalysisResult(
            code="600519",
            name="E2E Chinese Report",
            sentiment_score=66,
            trend_prediction="震荡",
            operation_advice="观望",
            analysis_summary=f"{REPORT_ZH_MARKER}: 中文报告正文。",
            report_language="zh",
            model_used="e2e/fake-report-model",
        ),
        AnalysisResult(
            code="MSFT",
            name="E2E English Report",
            sentiment_score=68,
            trend_prediction="Range-bound",
            operation_advice="Hold",
            analysis_summary=f"{REPORT_EN_MARKER}: deterministic English report body.",
            report_language="en",
            model_used="e2e/fake-report-model",
        ),
        # Keep the Markdown fixture last so existing tests that select the
        # newest history item continue to exercise the same report.
        AnalysisResult(
            code="AAPL",
            name="E2E Fixture",
            sentiment_score=62,
            trend_prediction="震荡",
            operation_advice="观望",
            analysis_summary=f"{REPORT_MARKER}: deterministic report content.",
            report_language="zh",
            model_used="e2e/fake-report-model",
        ),
    ]
    record_ids = []
    for index, result in enumerate(seeded_reports, start=1):
        record_ids.append(db.save_analysis_history(
            result=result,
            query_id=f"e2e-report-{index}",
            report_type="full",
            news_content="E2E fixture news",
            context_snapshot=None,
            save_snapshot=False,
        ))
    record_id = record_ids[-1]
    if record_id <= 0:
        raise RuntimeError("Failed to seed the Playwright report fixture")

    expected_markers = (REPORT_ZH_MARKER, REPORT_EN_MARKER, REPORT_MARKER)
    for seeded_record_id, expected_marker in zip(record_ids, expected_markers):
        markdown = HistoryService(db).get_markdown_report(str(seeded_record_id)) or ""
        if expected_marker not in markdown:
            raise RuntimeError(
                f"Seeded Playwright report {seeded_record_id} cannot render {expected_marker}"
            )

    DatabaseManager.reset_instance()
    Config._instance = None
    # Imports must not be allowed to extend the environment passed to the real
    # backend process. Reapply the pre-import allowlist after fixture seeding.
    os.environ.clear()
    os.environ.update(child_env)
    print(
        (
            f"[e2e-backend] prepared isolated runtime and report records {record_ids}; "
            f"environment keys={len(child_env)}"
        ),
        file=log,
        flush=True,
    )
    return child_env


def _stop_child(child: subprocess.Popen[bytes], signum: int) -> None:
    """Forward a shutdown signal to the backend child when it is alive."""
    if child.poll() is None:
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass


def main() -> int:
    """Run the isolated backend until Playwright stops the fixture."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    runtime_dir = _resolve_output_child(
        os.getenv("DSA_WEB_E2E_RUNTIME_DIR", ""),
        "runtime",
    )
    log_dir = _resolve_output_child(
        os.getenv("DSA_WEB_E2E_LOG_DIR", ""),
        "service-logs",
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    backend_log_path = log_dir / "backend.log"

    child: subprocess.Popen[bytes] | None = None
    stopping = False
    with backend_log_path.open("a", encoding="utf-8", buffering=1) as log:
        try:
            child_env = _prepare_runtime(runtime_dir, log_dir, log)
            command = [
                sys.executable,
                str(REPO_ROOT / "main.py"),
                "--webui-only",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port),
            ]
            print(f"[e2e-backend] starting backend on 127.0.0.1:{args.port}", file=log)
            child = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                env=child_env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )

            def handle_signal(signum: int, _frame: object) -> None:
                """Mark fixture shutdown and forward the received signal."""
                nonlocal stopping
                stopping = True
                if child is not None:
                    _stop_child(child, signum)

            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
            return_code = child.wait()
            return 0 if stopping else return_code
        except Exception:
            traceback.print_exc(file=log)
            return 1
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            shutil.rmtree(runtime_dir, ignore_errors=True)
            print("[e2e-backend] removed isolated runtime data", file=log, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
