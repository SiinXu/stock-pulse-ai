"""Shared contracts and atomic write helpers for merge resolvers."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CONFLICT_START = "<<<<<<<"
CONFLICT_BASE = "|||||||"
CONFLICT_SEPARATOR = "======="
CONFLICT_END = ">>>>>>>"


class RefusalError(Exception):
    """Raised when a conflict is outside a resolver's safe contract."""

    def __init__(self, path: str | Path, reason: str):
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"{self.path}: {reason}")


@dataclass(frozen=True)
class ConflictContext:
    """The three index stages plus Git's current conflict-marker rendering."""

    path: Path
    base: str
    ours: str
    theirs: str
    current: str


@dataclass(frozen=True)
class ConflictHunk:
    ours: tuple[str, ...]
    theirs: tuple[str, ...]


def parse_conflict_hunks(path: Path, text: str) -> tuple[list[str | ConflictHunk], int]:
    """Parse standard or diff3 conflict markers without accepting malformed input."""

    lines = text.splitlines(keepends=True)
    parts: list[str | ConflictHunk] = []
    plain: list[str] = []
    index = 0
    hunk_count = 0

    def flush_plain() -> None:
        if plain:
            parts.append("".join(plain))
            plain.clear()

    while index < len(lines):
        line = lines[index]
        if not line.startswith(CONFLICT_START):
            if line.startswith((CONFLICT_BASE, CONFLICT_SEPARATOR, CONFLICT_END)):
                raise RefusalError(path, "malformed conflict markers")
            plain.append(line)
            index += 1
            continue

        flush_plain()
        hunk_count += 1
        index += 1
        ours: list[str] = []
        while index < len(lines) and not lines[index].startswith(
            (CONFLICT_BASE, CONFLICT_SEPARATOR)
        ):
            if lines[index].startswith((CONFLICT_START, CONFLICT_END)):
                raise RefusalError(path, "nested or malformed conflict markers")
            ours.append(lines[index])
            index += 1

        if index >= len(lines):
            raise RefusalError(path, "unterminated conflict hunk")
        if lines[index].startswith(CONFLICT_BASE):
            index += 1
            while index < len(lines) and not lines[index].startswith(CONFLICT_SEPARATOR):
                if lines[index].startswith((CONFLICT_START, CONFLICT_END)):
                    raise RefusalError(path, "nested or malformed diff3 conflict")
                index += 1
            if index >= len(lines):
                raise RefusalError(path, "diff3 hunk has no separator")

        index += 1
        theirs: list[str] = []
        while index < len(lines) and not lines[index].startswith(CONFLICT_END):
            if lines[index].startswith(
                (CONFLICT_START, CONFLICT_BASE, CONFLICT_SEPARATOR)
            ):
                raise RefusalError(path, "nested or malformed conflict markers")
            theirs.append(lines[index])
            index += 1
        if index >= len(lines):
            raise RefusalError(path, "unterminated conflict hunk")
        index += 1
        parts.append(ConflictHunk(tuple(ours), tuple(theirs)))

    flush_plain()
    return parts, hunk_count


def render_conflict_parts(parts: Iterable[str | ConflictHunk]) -> str:
    """Join conflict parts after every ConflictHunk has been replaced."""

    rendered: list[str] = []
    for part in parts:
        if isinstance(part, ConflictHunk):
            raise ValueError("unresolved ConflictHunk passed to render_conflict_parts")
        rendered.append(part)
    return "".join(rendered)


def ensure_no_conflict_markers(path: Path, text: str) -> None:
    if any(
        marker in text
        for marker in (CONFLICT_START, CONFLICT_BASE, CONFLICT_SEPARATOR, CONFLICT_END)
    ):
        raise RefusalError(path, "resolver output still contains conflict markers")


def run_git(root: Path, args: list[str], *, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def load_conflict_context(root: Path, relative_path: Path) -> ConflictContext:
    """Load an unmerged path from index stages 1/2/3."""

    stage_lines = run_git(root, ["ls-files", "-u", "--", relative_path.as_posix()])
    if not stage_lines.strip():
        raise RefusalError(relative_path, "path is not unmerged")

    stages = {
        int(line.split(None, 3)[2])
        for line in stage_lines.splitlines()
        if len(line.split(None, 3)) == 4
    }
    if stages != {1, 2, 3}:
        raise RefusalError(
            relative_path,
            f"expected index stages 1/2/3, found {sorted(stages)}",
        )

    def show(stage: int) -> str:
        return run_git(root, ["show", f":{stage}:{relative_path.as_posix()}"])

    current_path = root / relative_path
    try:
        current = current_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise RefusalError(relative_path, f"cannot read UTF-8 conflict file: {exc}") from exc

    return ConflictContext(
        path=relative_path,
        base=show(1),
        ours=show(2),
        theirs=show(3),
        current=current,
    )


def atomic_write_and_stage(root: Path, outputs: dict[Path, bytes]) -> None:
    """Replace all planned files, then atomically update Git's index.

    Git writes the index through a lock file. Worktree replacements are rolled
    back if any replacement or the single staging command fails.
    """

    if not outputs:
        return

    originals: dict[Path, bytes | None] = {}
    original_modes: dict[Path, int | None] = {}
    temp_paths: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for relative_path, body in outputs.items():
            target = root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            originals[relative_path] = target.read_bytes() if target.exists() else None
            original_modes[relative_path] = target.stat().st_mode if target.exists() else None
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{target.name}.merge-resolver-",
                dir=target.parent,
            )
            temp_path = Path(temp_name)
            temp_paths[relative_path] = temp_path
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            if target.exists():
                os.chmod(temp_path, target.stat().st_mode)

        for relative_path, temp_path in temp_paths.items():
            os.replace(temp_path, root / relative_path)
            replaced.append(relative_path)

        run_git(root, ["add", "--", *[path.as_posix() for path in outputs]])
    except Exception:
        for relative_path in reversed(replaced):
            target = root / relative_path
            original = originals[relative_path]
            if original is None:
                target.unlink(missing_ok=True)
                continue
            descriptor, rollback_name = tempfile.mkstemp(
                prefix=f".{target.name}.merge-resolver-rollback-",
                dir=target.parent,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
            if original_modes[relative_path] is not None:
                os.chmod(rollback_name, original_modes[relative_path])
            os.replace(rollback_name, target)
        raise
    finally:
        for temp_path in temp_paths.values():
            temp_path.unlink(missing_ok=True)
