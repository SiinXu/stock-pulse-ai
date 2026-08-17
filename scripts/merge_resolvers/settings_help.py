"""Union additive settings-help catalogue blocks without accepting edit conflicts."""

from __future__ import annotations

import re
from pathlib import Path

from .common import ConflictContext, ConflictHunk, RefusalError, parse_conflict_hunks


SUPPORTED_PATTERNS = ("apps/dsa-web/src/locales/settingsHelp.<lang>.ts",)
_PATH = re.compile(r"^apps/dsa-web/src/locales/settingsHelp\.[A-Za-z-]+\.ts$")
_BLOCK_START = re.compile(r"^(\s*)(['\"])((?:[^'\"\\]|\\.)+)\2\s*:\s*\{\s*$")
_CLOSER = re.compile(r"^\s*\},?\s*$")


def is_supported(path: Path) -> bool:
    return bool(_PATH.match(path.as_posix()))


def _raw_lines(lines: tuple[str, ...]) -> list[str]:
    return [line if line.endswith("\n") else f"{line}\n" for line in lines]


def _blocks(
    path: Path,
    side: str,
    lines: list[str],
) -> tuple[list[tuple[str, list[str]]], tuple[str, list[str]] | None]:
    """Split one hunk side into complete entry blocks plus one trailing open block."""

    blocks: list[tuple[str, list[str]]] = []
    open_block: tuple[str, list[str]] | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        start = _BLOCK_START.match(line.rstrip("\n"))
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
                    raise RefusalError(
                        path,
                        f"{side} side ends inside entry {key!r} at brace depth {depth}",
                    )
                open_block = (key, body)
                continue
            if not body[-1].rstrip().endswith(("},", "}")):
                raise RefusalError(
                    path,
                    f"{side} side entry {key!r} does not end with a closing brace",
                )
            blocks.append((key, body))
            continue
        raise RefusalError(
            path,
            f"{side} side is not a settings-help entry block: {line.strip()[:100]!r}",
        )
    return blocks, open_block


def _closer_after(parts: list[str | ConflictHunk], index: int) -> str | None:
    if index + 1 >= len(parts):
        return None
    nxt = parts[index + 1]
    if isinstance(nxt, ConflictHunk):
        return None
    for line in nxt.splitlines(keepends=True):
        if not line.strip():
            continue
        return line if _CLOSER.match(line.rstrip("\n")) else None
    return None


def _merge_hunk(path: Path, hunk: ConflictHunk, closer: str | None) -> str:
    ours_lines = _raw_lines(hunk.ours)
    theirs_lines = _raw_lines(hunk.theirs)
    if not any(line.strip() for line in ours_lines) or not any(
        line.strip() for line in theirs_lines
    ):
        raise RefusalError(path, "settings-help conflict has an empty side")

    ours, our_open = _blocks(path, "ours", ours_lines)
    theirs, their_open = _blocks(path, "theirs", theirs_lines)

    if (our_open is None) != (their_open is None):
        raise RefusalError(
            path,
            "only one side ends inside an entry block, so the shared closing "
            "brace cannot serve both",
        )
    if our_open is not None and their_open is not None:
        if our_open[0] == their_open[0]:
            raise RefusalError(
                path,
                f"both sides open the entry {our_open[0]!r} with different bodies",
            )
        if closer is None:
            raise RefusalError(
                path,
                "hunk ends inside an entry block but the next shared line is "
                "not a closing brace",
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
            raise RefusalError(
                path,
                f"both sides define the settings-help entry {key!r} differently",
            )

    if our_open is not None and their_open is not None and closer is not None:
        merged.extend(our_open[1])
        merged.append(closer if closer.endswith("\n") else f"{closer}\n")
        merged.extend(their_open[1])

    if not merged:
        raise RefusalError(path, "settings-help merge produced no entries")
    return "".join(merged)


def resolve(context: ConflictContext) -> str:
    if not is_supported(context.path):
        raise RefusalError(context.path, "unsupported settings-help file")
    parts, hunk_count = parse_conflict_hunks(context.path, context.current)
    if hunk_count == 0:
        raise RefusalError(context.path, "file has no conflict hunks")

    rendered: list[str] = []
    for index, part in enumerate(parts):
        if isinstance(part, str):
            rendered.append(part)
            continue
        rendered.append(_merge_hunk(context.path, part, _closer_after(parts, index)))
    return "".join(rendered)
