"""Resolver for ``docs/INDEX.md`` and ``docs/INDEX_EN.md``.

Why neither side is correct
---------------------------
Both files are the repository-wide table of contents. A pull request that adds
a document appends one row to each table, and git puts two independently
appended rows in the same slot. ``--ours`` loses the incoming document,
``--theirs`` loses whatever main added since the branch point, and both leave
the bilingual pair out of sync.

The merged table is the union of both sides' rows, in their existing insertion
order, which this resolver reconstructs.

Refusal conditions (documented contract)
----------------------------------------
* any non-blank line inside a hunk is not a markdown table row (``| ... |``) —
  a prose, heading, or table-header change is not an append and needs a human;
* a hunk contains a table separator row (``| --- |``) — the table structure,
  not its contents, is in conflict;
* both sides carry a row whose first cell (the document link) is the same but
  whose full text differs — that is a genuine edit conflict on one entry, not
  two independent appends;
* the Chinese and English index are both in the batch but the merge adds a
  different number of rows to each — the repository's bilingual documentation
  rule requires the pair to move together.
"""

from __future__ import annotations

import re

from .common import Context, Hunk, Refusal, Resolution, parse_conflicts, render

NAME = "docs-index"
DESCRIPTION = "Union appended markdown index rows; keep the bilingual pair balanced."

CHINESE_INDEX = "docs/INDEX.md"
ENGLISH_INDEX = "docs/INDEX_EN.md"
SUPPORTED = (CHINESE_INDEX, ENGLISH_INDEX)

_ROW = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
_FIRST_CELL = re.compile(r"^\s*\|([^|]*)\|")


def matches(rel_path: str) -> bool:
    return rel_path in SUPPORTED


def _check_rows(rel_path: str, hunk: Hunk, side: str, lines: list[str]) -> list[str]:
    rows = []
    for line in lines:
        if not line.strip():
            continue
        if not _ROW.match(line):
            raise Refusal(
                rel_path,
                f"hunk at line {hunk.line_number} ({side} side) contains a "
                f"non-table line: {line.strip()[:80]!r}",
            )
        if _SEPARATOR.match(line):
            raise Refusal(
                rel_path,
                f"hunk at line {hunk.line_number} touches the table separator row; "
                "the table structure is in conflict",
            )
        rows.append(line)
    return rows


def _key(row: str) -> str:
    match = _FIRST_CELL.match(row)
    return (match.group(1) if match else row).strip()


def _merge_hunk(rel_path: str, hunk: Hunk) -> tuple[list[str], int]:
    ours = _check_rows(rel_path, hunk, "ours", hunk.ours)
    theirs = _check_rows(rel_path, hunk, "theirs", hunk.theirs)

    merged: list[str] = []
    by_key: dict[str, str] = {}
    added = 0
    for source, rows in (("ours", ours), ("theirs", theirs)):
        for row in rows:
            key = _key(row)
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = row
                merged.append(row)
                if source == "theirs":
                    added += 1
                continue
            if existing.strip() != row.strip():
                raise Refusal(
                    rel_path,
                    f"both sides changed the index entry {key!r} differently; "
                    "this is an edit conflict, not two appends",
                )
    return merged, added


def resolve(ctx: Context, rel_path: str) -> Resolution:
    conflicted = ctx.read_working(rel_path)
    segments = parse_conflicts(rel_path, conflicted)
    if all(isinstance(segment, str) for segment in segments):
        return Resolution(
            path=rel_path, text=conflicted, detail="no conflict markers", notes=[]
        )

    added_total = 0
    merged_cache: dict[int, list[str]] = {}
    for segment in segments:
        if isinstance(segment, Hunk):
            merged, added = _merge_hunk(rel_path, segment)
            merged_cache[id(segment)] = merged
            added_total += added

    text = render(segments, lambda hunk: merged_cache[id(hunk)])
    return Resolution(
        path=rel_path,
        text=text,
        detail=f"merged {len(merged_cache)} hunk(s); {added_total} incoming row(s)",
        notes=[f"incoming-rows={added_total}"],
    )


def validate_batch(ctx: Context, resolutions: dict[str, Resolution]) -> None:
    """Enforce the bilingual invariant when both index files are in the batch."""

    if CHINESE_INDEX not in resolutions or ENGLISH_INDEX not in resolutions:
        return

    def added(path: str) -> int:
        for note in resolutions[path].notes:
            if note.startswith("incoming-rows="):
                return int(note.split("=", 1)[1])
        return 0

    chinese, english = added(CHINESE_INDEX), added(ENGLISH_INDEX)
    if chinese != english:
        raise Refusal(
            f"{CHINESE_INDEX} + {ENGLISH_INDEX}",
            f"the merge adds {chinese} row(s) to the Chinese index but "
            f"{english} to the English index; the bilingual documentation index "
            "must stay in step",
        )
