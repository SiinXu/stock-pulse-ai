"""Resolver for ``apps/dsa-web/src/playground/__tests__/catalog.test.ts``.

Why neither side is correct
---------------------------
The test pins the total size of the Playground component catalog with
``expect(PLAYGROUND_CATALOG).toHaveLength(N)``. ``catalog.ts`` itself merges
cleanly (two pull requests append different components), but the single integer
``N`` cannot hold both results. Keeping main's ``N`` fails the test by the
branch's additions and keeping the branch's ``N`` fails it by main's, so both
sides are wrong by construction.

The correct ``N`` is the length of the catalog built from the merged tree. When
``apps/dsa-web/node_modules`` is available this resolver bundles the merged
``catalog.ts`` with esbuild and counts the entries directly; otherwise it falls
back to the three-way arithmetic ``ours + theirs - base``, which is only valid
when both sides added entries.

Refusal conditions (documented contract)
----------------------------------------
* a hunk contains anything other than ``toHaveLength(<int>)`` assertion lines
  (the two sides must be identical once the integers are blanked);
* the two sides carry a different number of count assertions;
* either side *lowered* a count relative to the merge base — a removal is not
  an append and the arithmetic no longer holds;
* the count cannot be recomputed and the base stage is unavailable;
* the recomputed catalog length and the three-way arithmetic disagree by more
  than nothing — the resolver reports the recomputed (ground-truth) value but
  refuses if the recompute itself fails.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .common import Context, Hunk, Refusal, Resolution, parse_conflicts, render

NAME = "playground-catalog"
DESCRIPTION = "Recompute the Playground catalog length from the merged tree."

RELATIVE_PATH = "apps/dsa-web/src/playground/__tests__/catalog.test.ts"
CATALOG_SOURCE = "apps/dsa-web/src/playground/catalog.ts"
WEB_ROOT = "apps/dsa-web"

_LENGTH = re.compile(r"toHaveLength\((\d+)\)")

_COUNT_JS = r"""
const { buildSync } = require('esbuild');
const result = buildSync({
  entryPoints: [process.argv[2]],
  bundle: true,
  write: false,
  format: 'cjs',
  platform: 'node',
  logLevel: 'silent',
});
const module_ = { exports: {} };
new Function('module', 'exports', 'require', result.outputFiles[0].text)(
  module_, module_.exports, require,
);
process.stdout.write(String(module_.exports.PLAYGROUND_CATALOG.length));
"""


def matches(rel_path: str) -> bool:
    return rel_path == RELATIVE_PATH


def _blank(lines: list[str]) -> list[str]:
    return [_LENGTH.sub("toHaveLength(N)", line) for line in lines]


def _counts(lines: list[str]) -> list[int]:
    return [int(match) for line in lines for match in _LENGTH.findall(line)]


def _recompute(ctx: Context) -> int | None:
    web_root = ctx.repo_root / WEB_ROOT
    if not (web_root / "node_modules" / "esbuild").is_dir():
        return None
    script = web_root / ".merge-resolver-catalog-count.cjs"
    try:
        script.write_text(_COUNT_JS, encoding="utf-8")
        proc = subprocess.run(
            ["node", str(script), str(ctx.repo_root / CATALOG_SOURCE)],
            cwd=web_root,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    finally:
        script.unlink(missing_ok=True)
    if proc.returncode != 0 or not proc.stdout.strip().isdigit():
        return None
    return int(proc.stdout.strip())


def resolve(ctx: Context, rel_path: str) -> Resolution:
    conflicted = ctx.read_working(rel_path)
    segments = parse_conflicts(rel_path, conflicted)
    conflict_hunks = [segment for segment in segments if isinstance(segment, Hunk)]
    if not conflict_hunks:
        return Resolution(
            path=rel_path, text=conflicted, detail="no conflict markers", notes=[]
        )

    for hunk in conflict_hunks:
        if _blank(hunk.ours) != _blank(hunk.theirs):
            raise Refusal(
                rel_path,
                f"hunk at line {hunk.line_number} differs in more than the "
                "toHaveLength() counts; this is a real test conflict",
            )
        our_counts, their_counts = _counts(hunk.ours), _counts(hunk.theirs)
        if not our_counts or len(our_counts) != len(their_counts):
            raise Refusal(
                rel_path,
                f"hunk at line {hunk.line_number} does not contain a matching "
                "pair of toHaveLength() assertions",
            )

    base_text = ctx.stage(rel_path, 1)
    base_counts = _counts(base_text.split("\n")) if base_text is not None else []

    recomputed = _recompute(ctx)
    notes: list[str] = []

    def merged_lines(hunk: Hunk) -> list[str]:
        our_counts = _counts(hunk.ours)
        their_counts = _counts(hunk.theirs)
        values: list[int] = []
        for index, (ours, theirs) in enumerate(zip(our_counts, their_counts)):
            base = base_counts[index] if index < len(base_counts) else None
            if recomputed is not None:
                values.append(recomputed)
                continue
            if base is None:
                raise Refusal(
                    rel_path,
                    "cannot recompute the catalog length (no esbuild) and the "
                    "merge base is unavailable",
                )
            if ours < base or theirs < base:
                raise Refusal(
                    rel_path,
                    f"a side lowered the catalog count ({base} -> {ours}/{theirs}); "
                    "entries were removed, so the additive merge does not hold",
                )
            values.append(ours + theirs - base)
        iterator = iter(values)
        return [
            _LENGTH.sub(lambda _: f"toHaveLength({next(iterator)})", line)
            for line in hunk.ours
        ]

    text = render(segments, merged_lines)

    if recomputed is not None:
        arithmetic = [
            ours + theirs - base
            for hunk in conflict_hunks
            for ours, theirs, base in zip(
                _counts(hunk.ours), _counts(hunk.theirs), base_counts
            )
        ]
        if arithmetic and any(value != recomputed for value in arithmetic):
            notes.append(
                f"recomputed catalog length {recomputed} differs from the "
                f"three-way arithmetic {arithmetic}; using the measured value"
            )
        detail = f"recomputed catalog length = {recomputed} from the merged tree"
    else:
        detail = "no esbuild available; used three-way additive arithmetic"
        notes.append("catalog length not verified against the merged catalog.ts")

    return Resolution(path=rel_path, text=text, detail=detail, notes=notes)
