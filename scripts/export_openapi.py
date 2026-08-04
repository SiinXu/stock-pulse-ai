#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Export a deterministic OpenAPI document from the FastAPI app.

Runs fully offline: isolates ENV_FILE / DATABASE_PATH / home directories,
installs the lightweight litellm stub used by contract tests, and never
opens network sockets or a real product database.

Usage::

    python scripts/export_openapi.py
    python scripts/export_openapi.py --output apps/dsa-web/openapi.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "apps" / "dsa-web" / "openapi.json"

# Ambient keys safe to keep for Python / the OS. Everything else is stripped so
# developer credentials and product config cannot affect the schema dump.
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
    "PYTHONPATH",
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


def _isolated_runtime_values(runtime_dir: Path) -> Dict[str, str]:
    """Deterministic application configuration for schema export."""
    return {
        "ADMIN_AUTH_ENABLED": "false",
        "DATABASE_PATH": str(runtime_dir / "openapi-export.db"),
        "ENV_FILE": str(runtime_dir / ".env"),
        "HOME": str(runtime_dir / "home"),
        "USERPROFILE": str(runtime_dir / "home"),
        "APPDATA": str(runtime_dir / "home" / "appdata"),
        "LOCALAPPDATA": str(runtime_dir / "home" / "local-appdata"),
        "XDG_CACHE_HOME": str(runtime_dir / "home" / ".cache"),
        "XDG_CONFIG_HOME": str(runtime_dir / "home" / ".config"),
        "LOG_DIR": str(runtime_dir / "logs"),
        "LLM_CONFIG_MODE": "auto",
        "PREFETCH_REALTIME_QUOTES": "false",
        "SCHEDULE_ENABLED": "false",
        "STOCK_INDEX_REMOTE_UPDATE_ENABLED": "false",
        "WEBUI_AUTO_BUILD": "false",
        "PROVIDER_DAILY_CACHE_ENABLED": "false",
        "PYTHONUNBUFFERED": "1",
    }


def _apply_isolated_environment(runtime_dir: Path) -> None:
    """Replace process env with an offline, credential-free fixture."""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "home").mkdir(parents=True, exist_ok=True)
    (runtime_dir / "logs").mkdir(parents=True, exist_ok=True)

    env_file = runtime_dir / ".env"
    env_file.write_text(
        "STOCK_LIST=600519\n"
        "ADMIN_AUTH_ENABLED=false\n"
        "SCHEDULE_ENABLED=false\n"
        "WEBUI_AUTO_BUILD=false\n"
        "PREFETCH_REALTIME_QUOTES=false\n"
        "STOCK_INDEX_REMOTE_UPDATE_ENABLED=false\n"
        "PROVIDER_DAILY_CACHE_ENABLED=false\n",
        encoding="utf-8",
    )

    isolated = {
        key: value
        for key, value in os.environ.items()
        if key in PASSTHROUGH_ENV_KEYS
    }
    isolated.update(_isolated_runtime_values(runtime_dir))
    os.environ.clear()
    os.environ.update(isolated)


def _load_app():
    """Import create_app after isolation; stub optional heavy deps."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    # Contract tests use the same lightweight stub so litellm need not be
    # installed for pure schema export.
    from tests.litellm_stub import ensure_litellm_stub

    ensure_litellm_stub()

    from api.app import create_app

    return create_app()


def export_openapi_dict() -> dict:
    """Build and return the OpenAPI schema as a plain dict."""
    app = _load_app()
    return app.openapi()


def dump_openapi(output: Path) -> Path:
    """Write a stable, sorted-key OpenAPI JSON document."""
    schema = export_openapi_dict()
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output.write_text(text, encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Destination JSON path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="stockpulse-openapi-export-") as tmp:
        runtime_dir = Path(tmp)
        _apply_isolated_environment(runtime_dir)
        path = dump_openapi(args.output.resolve() if args.output.is_absolute() else (Path.cwd() / args.output).resolve())

    print(f"Wrote deterministic OpenAPI schema to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
