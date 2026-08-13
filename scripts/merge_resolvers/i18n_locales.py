"""Resolver for the flat i18n locale tables under ``apps/dsa-web/src/i18n/``.

Why neither side is correct
---------------------------
Each locale file is one flat, sorted table holding *every* translation key in
the product. Two pull requests that each add a feature add disjoint sets of
keys to the same region of the same file. Keeping one side silently deletes the
other side's translations, and the UI then falls back to raw key names at
runtime; a line-level union keeps duplicates, which is also wrong for a
``const`` object.

The merged table is the union of both sides' entries, de-duplicated by key and
re-sorted.

Refusal conditions (documented contract)
----------------------------------------
* any non-blank line in a hunk is not a single flat entry line — either
  ``"key",`` in a key registry array or ``"key": "value",`` in a translation
  map. Nested objects, comments, spread operators, or type annotations mean the
  structure changed and a human must look;
* the same key appears on both sides with different values — that is a genuine
  translation conflict, not two independent additions.

This is a hardened port of the ad-hoc ``resolve_i18n.py`` used on merge train
#1312. The original validated and wrote in a single pass, so refusing the last
file left the earlier ones half-written; here nothing is written until the
whole batch is accepted.
"""

from __future__ import annotations

import re

from .common import Context, Hunk, Refusal, Resolution, parse_conflicts, render

NAME = "i18n-locales"
DESCRIPTION = "Union both sides' translation entries, de-duplicate, restore sorting."

# Only the flat tables. ``apps/dsa-web/src/locales/`` holds nested help maps
# and structured catalogues that this resolver must not touch; the nested
# settings-help catalogue has its own resolver.
_PREFIXES = ("apps/dsa-web/src/i18n/",)
_ENTRY = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"\s*(?::\s*.*,?\s*|,\s*)$')


def matches(rel_path: str) -> bool:
    return rel_path.endswith(".ts") and any(
        rel_path.startswith(prefix) for prefix in _PREFIXES
    )


def _entries(rel_path: str, hunk: Hunk, side: str, lines: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in lines:
        if not line.strip():
            continue
        match = _ENTRY.match(line)
        if match is None:
            raise Refusal(
                rel_path,
                f"hunk at line {hunk.line_number} ({side} side) is not a flat "
                f"entry line: {line.strip()[:100]!r}",
            )
        out.append((match.group(1), line))
    return out


def _merge_hunk(rel_path: str, hunk: Hunk) -> list[str]:
    ours = _entries(rel_path, hunk, "ours", hunk.ours)
    theirs = _entries(rel_path, hunk, "theirs", hunk.theirs)

    by_key: dict[str, str] = {}
    for key, line in ours + theirs:
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = line
            continue
        if existing.strip() != line.strip():
            raise Refusal(
                rel_path,
                f"both sides define {key!r} with different values; "
                "this is a translation conflict, not two additions",
            )
    return [by_key[key] for key in sorted(by_key)]


def resolve(ctx: Context, rel_path: str) -> Resolution:
    conflicted = ctx.read_working(rel_path)
    segments = parse_conflicts(rel_path, conflicted)
    hunk_count = sum(1 for segment in segments if isinstance(segment, Hunk))
    if not hunk_count:
        return Resolution(
            path=rel_path, text=conflicted, detail="no conflict markers", notes=[]
        )

    merged: dict[int, list[str]] = {}
    total = 0
    for segment in segments:
        if isinstance(segment, Hunk):
            lines = _merge_hunk(rel_path, segment)
            merged[id(segment)] = lines
            total += len(lines)

    text = render(segments, lambda hunk: merged[id(hunk)])
    return Resolution(
        path=rel_path,
        text=text,
        detail=f"merged {hunk_count} hunk(s) into {total} entries",
        notes=[],
    )
