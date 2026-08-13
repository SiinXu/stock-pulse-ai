"""Recompute config-registry snapshot hashes from the merged registry."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .common import ConflictContext, RefusalError, parse_conflict_hunks


SUPPORTED_PATH = Path("tests/core/test_config_registry_public_exports.py")
_HASH = re.compile(r'^\s*"[0-9a-f]{64}"\s*$')
_ASSIGNMENT = re.compile(
    r"^EXPECTED_(?:REGISTERED_KEYS|SCHEMA)_SHA256\s*=\s*\(\s*$"
)


def _recover_structure(context: ConflictContext) -> str:
    parts, hunk_count = parse_conflict_hunks(context.path, context.current)
    if hunk_count == 0:
        raise RefusalError(context.path, "file has no conflict hunks")
    output: list[str] = []
    for part in parts:
        if isinstance(part, str):
            output.append(part)
            continue
        if part.ours == part.theirs:
            raise RefusalError(context.path, "both sides changed the same snapshot entry")
        for line in (*part.ours, *part.theirs):
            raw = line.rstrip("\n")
            if not (
                _HASH.match(raw)
                or _ASSIGNMENT.match(raw)
                or raw.strip() == ")"
                or not raw.strip()
            ):
                raise RefusalError(context.path, "snapshot hunk contains non-hash structure")
        output.extend(part.ours)
    return "".join(output)


def _compute_hashes(root: Path, path: Path) -> tuple[str, str]:
    code = (
        "import hashlib,json;import src.core.config_registry as r;"
        "j=lambda v,s=False:hashlib.sha256(json.dumps(v,sort_keys=s,separators=(',',':')).encode()).hexdigest();"
        "print(json.dumps([j(r.get_registered_field_keys()),j(r.build_schema_response(),True)]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip()[-1200:] or result.stdout.strip()[-1200:]
        raise RefusalError(path, f"config registry import/recompute failed: {detail}")
    try:
        keys, schema = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"invalid config registry probe output: {result.stdout[-500:]}") from exc
    return keys, schema


def _replace_one(path: Path, text: str, name: str, digest: str) -> str:
    pattern = re.compile(
        rf'({name}\s*=\s*\(\s*\n\s*")[0-9a-f]{{64}}("\s*\n\))'
    )
    output, count = pattern.subn(rf"\g<1>{digest}\g<2>", text)
    if count != 1:
        raise RefusalError(path, f"expected exactly one {name} assignment, found {count}")
    return output


def resolve(
    context: ConflictContext,
    root: Path,
    hash_provider: Callable[[Path, Path], tuple[str, str]] = _compute_hashes,
) -> str:
    if context.path != SUPPORTED_PATH:
        raise RefusalError(context.path, "unsupported config-registry snapshot")
    recovered = _recover_structure(context)
    keys, schema = hash_provider(root, context.path)
    recovered = _replace_one(
        context.path,
        recovered,
        "EXPECTED_REGISTERED_KEYS_SHA256",
        keys,
    )
    return _replace_one(
        context.path,
        recovered,
        "EXPECTED_SCHEMA_SHA256",
        schema,
    )
