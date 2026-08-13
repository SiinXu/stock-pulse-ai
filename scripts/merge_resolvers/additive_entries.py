"""Resolve additive i18n key conflicts without accepting semantic edits."""

from __future__ import annotations

import re
from pathlib import Path

from .common import ConflictContext, ConflictHunk, RefusalError, parse_conflict_hunks


SUPPORTED_PATTERNS = (
    "apps/dsa-web/src/i18n/translations/*.ts",
    "apps/dsa-web/src/i18n/uiText.ts",
)
_ARRAY_ENTRY = re.compile(r'^\s*"([^"\\]+)"\s*,\s*$')
_MAP_ENTRY = re.compile(
    r'^\s*"([^"\\]+)"\s*:\s*"(?:\\.|[^"\\])*"\s*,\s*$'
)


def is_supported(path: Path) -> bool:
    value = path.as_posix()
    if value == "apps/dsa-web/src/i18n/uiText.ts":
        return True
    return (
        value.startswith("apps/dsa-web/src/i18n/translations/")
        and path.suffix == ".ts"
        and len(path.parts) == 6
    )


def _merge_hunk(path: Path, hunk: ConflictHunk) -> str:
    candidates: list[tuple[str, str, str]] = []
    shapes: set[str] = set()
    for origin, lines in (("ours", hunk.ours), ("theirs", hunk.theirs)):
        nonempty = [line for line in lines if line.strip()]
        if not nonempty:
            raise RefusalError(path, "additive conflict has an empty side")
        for line in nonempty:
            raw = line.rstrip("\n")
            array_match = _ARRAY_ENTRY.match(raw)
            map_match = _MAP_ENTRY.match(raw)
            if array_match:
                shapes.add("array")
                candidates.append((array_match.group(1), origin, line))
            elif map_match:
                shapes.add("map")
                candidates.append((map_match.group(1), origin, line))
            else:
                raise RefusalError(path, "hunk is not purely additive one-line entries")
    if len(shapes) != 1:
        raise RefusalError(path, "hunk mixes array and mapping entry shapes")

    entries: dict[str, tuple[str, str]] = {}
    for key, origin, line in candidates:
        if key in entries and entries[key][0] != origin:
            raise RefusalError(path, f"entry key {key!r} was changed on both sides")
        entries[key] = (origin, line if line.endswith("\n") else line + "\n")
    return "".join(entries[key][1] for key in sorted(entries, key=str.casefold))


def resolve(context: ConflictContext) -> str:
    if not is_supported(context.path):
        raise RefusalError(context.path, "unsupported additive-entry file")
    parts, hunk_count = parse_conflict_hunks(context.path, context.current)
    if hunk_count == 0:
        raise RefusalError(context.path, "file has no conflict hunks")
    output: list[str] = []
    for part in parts:
        output.append(part if isinstance(part, str) else _merge_hunk(context.path, part))
    return "".join(output)
