"""Entrypoint matrices for the fail-closed HTTP bind policy."""

from __future__ import annotations

import importlib.util
import json
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

sys.argv = [sys.argv[2], "server:app", "--host", sys.argv[1]]
fake_api_app = types.ModuleType("api.app")
fake_api_app.app = object()
sys.modules["api.app"] = fake_api_app
import server
"""

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            probe,
            host,
            str(Path(sys.executable).with_name("uvicorn")),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == expected_code
    if expected_code:
        assert "Refusing to start the HTTP service" in result.stderr


@pytest.mark.parametrize(
    ("uvicorn_env", "argv", "auth_enabled", "expected_code", "stderr_snippet"),
    [
        ({"UVICORN_HOST": "127.0.0.1"}, ["uvicorn", "server:app"], False, 0, None),
        (
            {"UVICORN_HOST": "0.0.0.0"},
            ["uvicorn", "server:app"],
            False,
            1,
            "requested bind is not local-only",
        ),
        (
            {"UVICORN_HOST": "0.0.0.0"},
            ["uvicorn", "server:app", "--host", "127.0.0.1"],
            False,
            0,
            None,
        ),
        (
            {"UVICORN_FD": "7"},
            ["uvicorn", "server:app"],
            False,
            1,
            "bind target could not be verified as local",
        ),
        (
            {"UVICORN_HOST": "0.0.0.0", "UVICORN_UDS": "/tmp/stockpulse.sock"},
            ["uvicorn", "server:app"],
            False,
            0,
            None,
        ),
        ({}, ["uvicorn-module", "server:app", "--host", "127.0.0.1"], False, 0, None),
        (
            {},
            ["custom-launcher"],
            False,
            1,
            "bind target could not be verified as local",
        ),
        (
            {},
            ["/opt/custom/server.py"],
            False,
            1,
            "bind target could not be verified as local",
        ),
        (
            {},
            ["/opt/custom/uvicorn", "server:app"],
            False,
            1,
            "bind target could not be verified as local",
        ),
        (
            {},
            ["/opt/custom/uvicorn/__main__.py", "server:app"],
            False,
            1,
            "bind target could not be verified as local",
        ),
        ({}, ["custom-launcher"], True, 0, None),
        # Explicit loopback under unrecognized launchers must boot without auth.
        (
            {},
            ["/opt/custom/uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8000"],
            False,
            0,
            None,
        ),
        (
            {},
            ["/opt/custom/uvicorn", "server:app", "--host", "localhost"],
            False,
            0,
            None,
        ),
        (
            {},
            ["/opt/custom/uvicorn", "server:app", "--host", "0.0.0.0"],
            False,
            1,
            "requested bind is not local-only",
        ),
        (
            {},
            [
                "/opt/custom/uvicorn",
                "server:app",
                "--host",
                "127.0.0.1",
                "--fd",
                "3",
            ],
            False,
            1,
            "bind target could not be verified as local",
        ),
        # gunicorn-style import: no parseable uvicorn bind flags → fail closed.
        (
            {},
            [
                "/usr/bin/gunicorn",
                "-k",
                "uvicorn.workers.UvicornWorker",
                "server:app",
            ],
            False,
            1,
            "bind target could not be verified as local",
        ),
        # Same worker shape with explicit loopback flags remains local-safe.
        (
            {},
            [
                "/usr/bin/gunicorn",
                "-k",
                "uvicorn.workers.UvicornWorker",
                "server:app",
                "--host",
                "127.0.0.1",
            ],
            False,
            0,
            None,
        ),
    ],
)
def test_server_module_uses_authoritative_uvicorn_bind_or_fails_closed(
    tmp_path: Path,
    uvicorn_env: dict[str, str],
    argv: list[str],
    auth_enabled: bool,
    expected_code: int,
    stderr_snippet: str | None,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"ADMIN_AUTH_ENABLED={'true' if auth_enabled else 'false'}\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    for key in ("UVICORN_HOST", "UVICORN_PORT", "UVICORN_UDS", "UVICORN_FD"):
        env.pop(key, None)
    env.update(
        {
            "ENV_FILE": str(env_file),
            "ALLOW_INSECURE_PUBLIC_BIND": "false",
            "PYTHONPATH": str(REPO_ROOT),
            **uvicorn_env,
        }
    )
    probe = """
import json
import sys
import types

sys.argv = json.loads(sys.argv[1])
fake_api_app = types.ModuleType("api.app")
fake_api_app.app = object()
sys.modules["api.app"] = fake_api_app
import server
"""

    resolved_argv = list(argv)
    if resolved_argv[0] == "uvicorn":
        resolved_argv[0] = str(Path(sys.executable).with_name("uvicorn"))
    elif resolved_argv[0] == "uvicorn-module":
        uvicorn_spec = importlib.util.find_spec("uvicorn")
        assert uvicorn_spec is not None and uvicorn_spec.origin is not None
        resolved_argv[0] = str(Path(uvicorn_spec.origin).with_name("__main__.py"))

    result = subprocess.run(
        [sys.executable, "-c", probe, json.dumps(resolved_argv)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == expected_code, (
        f"argv={resolved_argv!r} code={result.returncode} "
        f"stderr={result.stderr!r} stdout={result.stdout!r}"
    )
    if expected_code:
        assert "Refusing to start the HTTP service" in result.stderr
        if stderr_snippet is not None:
            assert stderr_snippet in result.stderr
