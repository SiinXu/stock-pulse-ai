"""Regenerate OpenAPI and Web API types from the merged source tree."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from .common import ConflictContext, RefusalError, parse_conflict_hunks


OPENAPI_PATH = Path("apps/dsa-web/openapi.json")
TYPES_PATH = Path("apps/dsa-web/src/types/api.generated.ts")
SUPPORTED_PATHS = frozenset({OPENAPI_PATH, TYPES_PATH})


def _run(path: Path, command: list[str], cwd: Path) -> None:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip()[-1600:] or result.stdout.strip()[-1600:]
        raise RefusalError(path, f"generation command failed ({' '.join(command)}): {detail}")


def resolve(
    contexts: dict[Path, ConflictContext],
    root: Path,
) -> dict[Path, bytes]:
    if not contexts:
        raise RefusalError(OPENAPI_PATH, "no generated artifact conflict was provided")
    for path, context in contexts.items():
        if path not in SUPPORTED_PATHS:
            raise RefusalError(path, "unsupported generated artifact")
        _, hunk_count = parse_conflict_hunks(path, context.current)
        if hunk_count == 0:
            raise RefusalError(path, "file has no conflict hunks")
        if context.ours == context.theirs:
            raise RefusalError(path, "both sides changed the generated artifact identically")

    web_root = root / "apps" / "dsa-web"
    if not (web_root / "node_modules" / ".bin" / "openapi-typescript").exists():
        raise RefusalError(
            OPENAPI_PATH,
            "Web dependencies are missing; run 'cd apps/dsa-web && npm ci' first",
        )

    with tempfile.TemporaryDirectory(prefix="stockpulse-merge-openapi-") as temp_name:
        temp_root = Path(temp_name)
        openapi_output = temp_root / "openapi.json"
        types_output = temp_root / "api.generated.ts"
        _run(
            OPENAPI_PATH,
            [
                sys.executable,
                "scripts/export_openapi.py",
                "--output",
                str(openapi_output),
            ],
            root,
        )
        _run(
            TYPES_PATH,
            [
                "npm",
                "exec",
                "--no",
                "--",
                "openapi-typescript",
                str(openapi_output),
                "-o",
                str(types_output),
            ],
            web_root,
        )
        return {
            OPENAPI_PATH: openapi_output.read_bytes(),
            TYPES_PATH: types_output.read_bytes(),
        }
