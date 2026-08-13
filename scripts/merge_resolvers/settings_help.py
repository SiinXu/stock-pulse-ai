"""Resolver for ``apps/dsa-web/src/locales/settingsHelp.<lang>.ts``.

Why neither side is correct
---------------------------
These files are the whole-repository settings help catalogue: one nested block
per configuration key, holding the title, summary, usage, value notes, impact
and caveats shown next to that setting. Every pull request that registers a
configuration key appends a block, so two pull requests append at the same
place in the same file. Keeping one side deletes the other side's help text and
the Settings page silently falls back to a bare key name.

The merged catalogue is the union of both sides' blocks.

Refusal conditions (documented contract)
----------------------------------------
* a hunk contains anything other than complete, brace-balanced entry blocks of
  the form ``'some.key': { ... },`` (blank lines are tolerated) — a change to
  the file header, the trailing ``};``, a comment, or a partially quoted block
  means the structure changed and needs a human;
* the same settings key appears on both sides with different bodies — that is
  an edit conflict on one entry, not two independent additions;
* an entry block is not terminated inside the hunk (its closing brace lives
  outside the conflict region), because the merged text could then be
  syntactically valid but semantically wrong.
"""

from __future__ import annotations

import re

from .common import Context, Hunk, Refusal, Resolution, parse_conflicts, render

NAME = "settings-help"
DESCRIPTION = "Union both sides' settings-help entry blocks, keyed by settings key."

_PATH = re.compile(r"^apps/dsa-web/src/locales/settingsHelp\.[A-Za-z-]+\.ts$")
_BLOCK_START = re.compile(r"^(\s*)(['\"])((?:[^'\"\\]|\\.)+)\2\s*:\s*\{\s*$")
_ONE_LINE = re.compile(r"^\s*(['\"])((?:[^'\"\\]|\\.)+)\1\s*:\s*.*,\s*$")


def matches(rel_path: str) -> bool:
    return bool(_PATH.match(rel_path))


def _blocks(
    rel_path: str, hunk: Hunk, side: str, lines: list[str]
) -> tuple[list[tuple[str, list[str]]], tuple[str, list[str]] | None]:
    """Split hunk lines into complete entry blocks plus one trailing open block.

    Git often cuts a hunk at the first differing line *inside* an appended
    block, so both sides can end with an entry whose closing brace lives in the
    shared context after the hunk. That shape is still purely additive, so it is
    supported explicitly rather than merged by accident.
    """

    blocks: list[tuple[str, list[str]]] = []
    open_block: tuple[str, list[str]] | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        start = _BLOCK_START.match(line)
        if start is not None:
            key = start.group(3)
            depth = 0
            body: list[str] = []
            while index < len(lines):
                current = lines[index]
                depth += current.count("{") - current.count("}")
                body.append(current)
                index += 1
                if depth <= 0:
                    break
            if depth > 0:
                if depth != 1 or index < len(lines):
                    raise Refusal(
                        rel_path,
                        f"hunk at line {hunk.line_number} ({side} side) ends inside "
                        f"the entry block for {key!r} at brace depth {depth}",
                    )
                open_block = (key, body)
                continue
            if not body[-1].rstrip().endswith(("},", "}")):
                raise Refusal(
                    rel_path,
                    f"hunk at line {hunk.line_number} ({side} side): entry {key!r} "
                    "does not end with a closing brace",
                )
            blocks.append((key, body))
            continue
        single = _ONE_LINE.match(line)
        if single is not None:
            blocks.append((single.group(2), [line]))
            index += 1
            continue
        raise Refusal(
            rel_path,
            f"hunk at line {hunk.line_number} ({side} side) is not a settings-help "
            f"entry block: {line.strip()[:100]!r}",
        )
    return blocks, open_block


def _merge_hunk(rel_path: str, hunk: Hunk, closer: str | None) -> list[str]:
    ours, our_open = _blocks(rel_path, hunk, "ours", hunk.ours)
    theirs, their_open = _blocks(rel_path, hunk, "theirs", hunk.theirs)

    if (our_open is None) != (their_open is None):
        raise Refusal(
            rel_path,
            f"hunk at line {hunk.line_number}: only one side ends inside an entry "
            "block, so the shared closing brace cannot serve both",
        )
    if our_open is not None and their_open is not None:
        if our_open[0] == their_open[0]:
            raise Refusal(
                rel_path,
                f"both sides open the entry {our_open[0]!r} with different bodies; "
                "this is an edit conflict, not two additions",
            )
        if closer is None:
            raise Refusal(
                rel_path,
                f"hunk at line {hunk.line_number} ends inside an entry block but the "
                "next shared line is not a closing brace",
            )

    merged: list[str] = []
    by_key: dict[str, list[str]] = {}
    for key, body in ours + theirs:
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = body
            merged.extend(body)
            continue
        if [line.strip() for line in existing] != [line.strip() for line in body]:
            raise Refusal(
                rel_path,
                f"both sides define the settings-help entry {key!r} differently; "
                "this is an edit conflict, not two additions",
            )

    if our_open is not None and their_open is not None and closer is not None:
        # Ours gets a copy of the shared closing brace; theirs is closed by the
        # shared brace that already follows the hunk.
        merged.extend(our_open[1])
        merged.append(closer)
        merged.extend(their_open[1])
    return merged


_CLOSER = re.compile(r"^\s*\},?\s*$")


def _closer_after(segments: list, position: int) -> str | None:
    """The shared closing-brace line that immediately follows a hunk."""

    for segment in segments[position + 1 :]:
        if isinstance(segment, Hunk):
            return None
        if not segment.strip():
            continue
        return segment if _CLOSER.match(segment) else None
    return None


def resolve(ctx: Context, rel_path: str) -> Resolution:
    conflicted = ctx.read_working(rel_path)
    segments = parse_conflicts(rel_path, conflicted)
    hunk_count = sum(1 for segment in segments if isinstance(segment, Hunk))
    if not hunk_count:
        return Resolution(
            path=rel_path, text=conflicted, detail="no conflict markers", notes=[]
        )

    merged: dict[int, list[str]] = {}
    entries = 0
    for position, segment in enumerate(segments):
        if isinstance(segment, Hunk):
            lines = _merge_hunk(rel_path, segment, _closer_after(segments, position))
            merged[id(segment)] = lines
            entries += sum(1 for line in lines if _BLOCK_START.match(line))

    text = render(segments, lambda hunk: merged[id(hunk)])
    return Resolution(
        path=rel_path,
        text=text,
        detail=f"merged {hunk_count} hunk(s) keeping {entries} help entr(ies)",
        notes=[],
    )
