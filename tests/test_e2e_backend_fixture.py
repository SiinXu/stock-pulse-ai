# -*- coding: utf-8 -*-
"""Isolation contract for the Playwright backend fixture."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "apps" / "dsa-web" / "e2e" / "run-backend-fixture.py"


def _load_fixture_module():
    spec = importlib.util.spec_from_file_location("dsa_e2e_backend_fixture", FIXTURE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_spawned_backend_ignores_ambient_product_dotenv(tmp_path, monkeypatch) -> None:
    fixture = _load_fixture_module()
    outer_dir = tmp_path / "outer"
    work_dir = outer_dir / "child-cwd"
    runtime_dir = tmp_path / "runtime"
    log_dir = tmp_path / "logs"
    work_dir.mkdir(parents=True)
    runtime_dir.mkdir()
    log_dir.mkdir()

    sentinel_backend = "sentinel_outer_backend"
    sentinel_channel = "sentinel_outer_channel"
    sentinel_key = "sentinel-not-a-real-secret"
    (outer_dir / ".env").write_text(
        "\n".join(
            (
                f"GENERATION_BACKEND={sentinel_backend}",
                f"LLM_CHANNELS={sentinel_channel}",
                f"LLM_SENTINEL_API_KEY={sentinel_key}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GENERATION_BACKEND", sentinel_backend)
    monkeypatch.setenv("LLM_CHANNELS", sentinel_channel)
    monkeypatch.setenv("LLM_SENTINEL_API_KEY", sentinel_key)

    values = fixture._runtime_values(runtime_dir, log_dir)
    env_file = runtime_dir / "playwright.env"
    env_file.write_text(
        "\n".join(
            f"{key}={fixture._quoted_env_value(value)}"
            for key, value in values.items()
        )
        + "\n",
        encoding="utf-8",
    )
    child_env = fixture._build_isolated_environment(values, env_file, runtime_dir)
    fixture._assert_isolated_environment(child_env, values, runtime_dir)

    assert child_env["LITELLM_MODE"] == "PRODUCTION"
    assert child_env["ADMIN_AUTH_ENABLED"] == "true"
    assert child_env["DATABASE_PATH"] == str(runtime_dir / "stock_analysis.db")
    assert "GENERATION_BACKEND" not in child_env
    assert "LLM_CHANNELS" not in child_env
    assert "LLM_SENTINEL_API_KEY" not in child_env

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import os",
                    "import sys",
                    f"sys.path.insert(0, {str(REPO_ROOT)!r})",
                    "import litellm",
                    "from src.config import Config",
                    "assert os.getenv('LITELLM_MODE') == 'PRODUCTION'",
                    "assert os.getenv('GENERATION_BACKEND') is None",
                    "assert os.getenv('LLM_CHANNELS') is None",
                    "assert os.getenv('LLM_SENTINEL_API_KEY') is None",
                    "assert os.getenv('ADMIN_AUTH_ENABLED') == 'true'",
                    "assert Config.get_instance().generation_backend == 'litellm'",
                )
            ),
        ],
        cwd=work_dir,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert probe.returncode == 0, "isolated backend subprocess probe failed"
