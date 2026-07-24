"""Entrypoint matrices for the fail-closed HTTP bind policy."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

import webui


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("host", "auth_enabled", "expected_code", "uvicorn_called"),
    [
        ("127.0.0.1", False, 0, True),
        ("0.0.0.0", False, 2, False),
        ("0.0.0.0", True, 0, True),
    ],
)
def test_webui_entrypoint_bind_matrix(
    host: str,
    auth_enabled: bool,
    expected_code: int,
    uvicorn_called: bool,
) -> None:
    with patch.dict(
        os.environ,
        {
            "WEBUI_HOST": host,
            "WEBUI_PORT": "8000",
            "ALLOW_INSECURE_PUBLIC_BIND": "false",
        },
        clear=False,
    ), patch("src.config.setup_env"), patch("src.logging_config.setup_logging"), patch(
        "src.auth.is_auth_enabled", return_value=auth_enabled
    ), patch("uvicorn.run") as run:
        assert webui.main() == expected_code

    assert run.called is uvicorn_called


@pytest.mark.parametrize(
    ("host", "auth_enabled", "expected_code"),
    [
        ("127.0.0.1", False, 0),
        ("0.0.0.0", False, 1),
        ("0.0.0.0", True, 0),
    ],
)
def test_server_module_bind_matrix(
    tmp_path: Path,
    host: str,
    auth_enabled: bool,
    expected_code: int,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"ADMIN_AUTH_ENABLED={'true' if auth_enabled else 'false'}\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "ENV_FILE": str(env_file),
            "ALLOW_INSECURE_PUBLIC_BIND": "false",
            "PYTHONPATH": str(REPO_ROOT),
        }
    )
    probe = """
import sys
import types

sys.argv = ["uvicorn", "server:app", "--host", sys.argv[1]]
fake_api_app = types.ModuleType("api.app")
fake_api_app.app = object()
sys.modules["api.app"] = fake_api_app
import server
"""

    result = subprocess.run(
        [sys.executable, "-c", probe, host],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == expected_code
    if expected_code:
        assert "Refusing to start the HTTP service" in result.stderr
