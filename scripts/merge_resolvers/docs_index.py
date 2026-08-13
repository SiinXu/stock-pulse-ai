"""Merge synchronized additive rows in the bilingual documentation indexes."""

from __future__ import annotations

import re
from pathlib import Path

from .common import ConflictContext, ConflictHunk, RefusalError, parse_conflict_hunks


ZH_PATH = Path("docs/INDEX.md")
EN_PATH = Path("docs/INDEX_EN.md")
SUPPORTED_PATHS = frozenset({ZH_PATH, EN_PATH})
_ROW = re.compile(r"^\| \[[^\]]+\]\(([^)]+)\).+\|\s*$")


def _merge_rows(path: Path, hunk: ConflictHunk) -> str:
    ours = [line for line in hunk.ours if line.strip()]
    theirs = [line for line in hunk.theirs if line.strip()]
    if not ours or not theirs:
        raise RefusalError(path, "index conflict must contain added rows on both sides")

    rows: dict[str, str] = {}
    origins: dict[str, str] = {}
    for origin, lines in (("ours", ours), ("theirs", theirs)):
        for line in lines:
            match = _ROW.match(line.rstrip("\n"))
            if not match:
                raise RefusalError(path, "conflict contains a non-table-row line")
            key = match.group(1)
            normalized = line if line.endswith("\n") else line + "\n"
            if key in rows and origins[key] != origin:
                raise RefusalError(path, f"document target {key!r} was added on both sides")
            rows[key] = normalized
            origins[key] = origin
    return "".join(rows[key] for key in sorted(rows, key=str.casefold))


def resolve_pair(contexts: dict[Path, ConflictContext]) -> dict[Path, str]:
    if set(contexts) != SUPPORTED_PATHS:
        missing = sorted(path.as_posix() for path in SUPPORTED_PATHS - set(contexts))
        raise RefusalError(
            next(iter(contexts), ZH_PATH),
            f"bilingual indexes must be resolved together; missing {', '.join(missing)}",
        )

    outputs: dict[Path, str] = {}
    side_addition_counts: dict[Path, tuple[int, int]] = {}
    for path in (ZH_PATH, EN_PATH):
        context = contexts[path]
        parts, hunk_count = parse_conflict_hunks(path, context.current)
        if hunk_count == 0:
            raise RefusalError(path, "file has no conflict hunks")
        rendered: list[str] = []
        ours_count = theirs_count = 0
        for part in parts:
            if isinstance(part, str):
                rendered.append(part)
                continue
            ours_count += len([line for line in part.ours if line.strip()])
            theirs_count += len([line for line in part.theirs if line.strip()])
            rendered.append(_merge_rows(path, part))
        outputs[path] = "".join(rendered)
        side_addition_counts[path] = (ours_count, theirs_count)

    if side_addition_counts[ZH_PATH] != side_addition_counts[EN_PATH]:
        raise RefusalError(
            ZH_PATH,
            "Chinese and English index conflicts add different row counts",
        )
    return outputs
