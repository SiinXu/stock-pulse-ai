"""Recompute the playground catalog's derived length assertion."""

from __future__ import annotations

import re
from pathlib import Path

from .common import ConflictContext, RefusalError, parse_conflict_hunks


SUPPORTED_PATH = Path("apps/dsa-web/src/playground/__tests__/catalog.test.ts")
CATALOG_PATH = Path("apps/dsa-web/src/playground/catalog.ts")
_EXPECTED = re.compile(
    r"^(\s*)expect\(PLAYGROUND_CATALOG\)\.toHaveLength\((\d+)\);\s*$"
)
_CATALOG_ENTRY = re.compile(r"^\s{2}(?:common|entry)\(")


def count_catalog_entries(path: Path, text: str) -> int:
    marker = "export const PLAYGROUND_CATALOG:"
    start = text.find(marker)
    if start < 0:
        raise RefusalError(path, "PLAYGROUND_CATALOG declaration is missing")
    end = text.find("\n];", start)
    if end < 0:
        raise RefusalError(path, "PLAYGROUND_CATALOG terminator is missing")
    body = text[start:end]
    count = sum(1 for line in body.splitlines() if _CATALOG_ENTRY.match(line))
    if count == 0:
        raise RefusalError(path, "PLAYGROUND_CATALOG contains no recognized entries")
    return count


def resolve(context: ConflictContext, root: Path) -> str:
    parts, hunk_count = parse_conflict_hunks(context.path, context.current)
    if hunk_count == 0:
        raise RefusalError(context.path, "file has no conflict hunks")
    try:
        catalog_text = (root / CATALOG_PATH).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RefusalError(context.path, f"cannot read merged catalog: {exc}") from exc
    count = count_catalog_entries(CATALOG_PATH, catalog_text)

    rendered: list[str] = []
    for part in parts:
        if isinstance(part, str):
            rendered.append(part)
            continue
        ours = [line for line in part.ours if line.strip()]
        theirs = [line for line in part.theirs if line.strip()]
        if len(ours) != 1 or len(theirs) != 1:
            raise RefusalError(context.path, "catalog hunk is not one length assertion per side")
        ours_match = _EXPECTED.match(ours[0].rstrip("\n"))
        theirs_match = _EXPECTED.match(theirs[0].rstrip("\n"))
        if not ours_match or not theirs_match:
            raise RefusalError(context.path, "catalog hunk contains non-length-assertion code")
        if ours_match.group(2) == theirs_match.group(2):
            raise RefusalError(context.path, "both sides changed the catalog count to the same value")
        rendered.append(
            f"{ours_match.group(1)}expect(PLAYGROUND_CATALOG).toHaveLength({count});\n"
        )
    return "".join(rendered)
