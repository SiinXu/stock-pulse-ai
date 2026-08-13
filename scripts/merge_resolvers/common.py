"""Shared primitives for the derived-file merge resolvers.

The resolvers in this package all follow the same contract:

* ``resolve()`` computes the merged content but never writes to disk.
* Any input the resolver does not fully understand raises :class:`Refusal`.
* ``resolve.py`` only writes once every requested file produced a
  :class:`Resolution`, so a refused batch leaves the working tree untouched.

Refusing is always safe: the pull request simply stays out of the merge train
and a human resolves it. Guessing is not safe, so every ambiguity in this
package is wired to a refusal rather than to a heuristic.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

CONFLICT_START = "<<<<<<<"
CONFLICT_BASE = "|||||||"
CONFLICT_SEP = "======="
CONFLICT_END = ">>>>>>>"


class Refusal(Exception):
    """Raised when a conflict is not safely resolvable by a resolver."""

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


class ResolverError(Exception):
    """Raised for internal failures (bad environment, unreadable git state)."""


@dataclass
class Resolution:
    """A computed, not-yet-written resolution for a single conflicted file."""

    path: str
    text: str
    detail: str
    notes: list[str] = field(default_factory=list)


@dataclass
class Context:
    """Execution context shared by every resolver in one batch."""

    repo_root: Path
    remeasure: bool = False

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            ["git", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            raise ResolverError(
                f"git {' '.join(args)} failed: {proc.stderr.strip()[-400:]}"
            )
        return proc

    def read_working(self, rel_path: str) -> str:
        return (self.repo_root / rel_path).read_text(encoding="utf-8")

    def stage(self, rel_path: str, stage: int) -> str | None:
        """Return index stage 1 (base) / 2 (ours) / 3 (theirs), or ``None``."""

        proc = self.git("show", f":{stage}:{rel_path}", check=False)
        if proc.returncode != 0:
            return None
        return proc.stdout

    def require_stages(self, rel_path: str) -> tuple[str, str, str]:
        base = self.stage(rel_path, 1)
        ours = self.stage(rel_path, 2)
        theirs = self.stage(rel_path, 3)
        missing = [
            name
            for name, value in (("base", base), ("ours", ours), ("theirs", theirs))
            if value is None
        ]
        if missing:
            raise Refusal(
                rel_path,
                "missing index stage(s) "
                + "/".join(missing)
                + " (add/add or delete/modify conflict needs a human)",
            )
        assert base is not None and ours is not None and theirs is not None
        return base, ours, theirs


def repo_root() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise ResolverError("not inside a git repository")
    return Path(proc.stdout.strip())


@dataclass
class Hunk:
    """One ``<<<<<<< / ======= / >>>>>>>`` block."""

    ours: list[str]
    theirs: list[str]
    base: list[str] | None
    line_number: int


Segment = str | Hunk


def parse_conflicts(path: str, text: str) -> list[Segment]:
    """Split ``text`` into literal lines and :class:`Hunk` objects.

    Refuses on malformed or nested markers rather than trying to recover.
    """

    lines = text.split("\n")
    segments: list[Segment] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith(CONFLICT_START):
            start_line = index + 1
            index += 1
            ours: list[str] = []
            while index < len(lines) and not (
                lines[index].startswith(CONFLICT_SEP)
                or lines[index].startswith(CONFLICT_BASE)
            ):
                if lines[index].startswith((CONFLICT_START, CONFLICT_END)):
                    raise Refusal(path, f"nested conflict marker at line {index + 1}")
                ours.append(lines[index])
                index += 1
            base: list[str] | None = None
            if index < len(lines) and lines[index].startswith(CONFLICT_BASE):
                base = []
                index += 1
                while index < len(lines) and not lines[index].startswith(CONFLICT_SEP):
                    if lines[index].startswith((CONFLICT_START, CONFLICT_END)):
                        raise Refusal(
                            path, f"nested conflict marker at line {index + 1}"
                        )
                    base.append(lines[index])
                    index += 1
            if index >= len(lines) or not lines[index].startswith(CONFLICT_SEP):
                raise Refusal(path, f"unterminated conflict hunk at line {start_line}")
            index += 1
            theirs: list[str] = []
            while index < len(lines) and not lines[index].startswith(CONFLICT_END):
                if lines[index].startswith((CONFLICT_START, CONFLICT_SEP)):
                    raise Refusal(path, f"nested conflict marker at line {index + 1}")
                theirs.append(lines[index])
                index += 1
            if index >= len(lines):
                raise Refusal(path, f"unterminated conflict hunk at line {start_line}")
            index += 1
            segments.append(Hunk(ours=ours, theirs=theirs, base=base, line_number=start_line))
            continue
        if line.startswith((CONFLICT_SEP, CONFLICT_END, CONFLICT_BASE)):
            raise Refusal(path, f"stray conflict marker at line {index + 1}")
        segments.append(line)
        index += 1
    return segments


def hunks(segments: Sequence[Segment]) -> list[Hunk]:
    return [segment for segment in segments if isinstance(segment, Hunk)]


def render(segments: Sequence[Segment], chooser: Callable[[Hunk], Iterable[str]]) -> str:
    """Rebuild file text, replacing each hunk with ``chooser(hunk)``."""

    out: list[str] = []
    for segment in segments:
        if isinstance(segment, Hunk):
            out.extend(chooser(segment))
        else:
            out.append(segment)
    return "\n".join(out)


def take_side(segments: Sequence[Segment], side: str) -> str:
    if side == "ours":
        return render(segments, lambda hunk: hunk.ours)
    if side == "theirs":
        return render(segments, lambda hunk: hunk.theirs)
    raise ValueError(f"unknown side: {side}")


def dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
