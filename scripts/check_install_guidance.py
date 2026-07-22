#!/usr/bin/env python3
"""Reject unconstrained requirements-install guidance outside bounded exceptions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCEPTIONS = ROOT / "scripts" / "install_guidance_exceptions.json"
MAX_EXCEPTION_DAYS = 30
IGNORED_PATHS = frozenset({"CLAUDE.md", "docs/CHANGELOG.md"})

REQUIREMENTS_INSTALL_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:python(?:3(?:\.\d+)?)?\s+-m\s+)?pip3?\b"
    r"(?:(?![;&|#\r\n]).){0,256}?\binstall\b"
    r"(?:(?![;&|#\r\n]).){0,512}?"
    r"(?:-r(?:=|\s*)|--requirement(?:=|\s+))"
    r"[^\s`;&|#]*requirements[^\s`;&|#]*\.txt",
    re.IGNORECASE,
)
ENVIRONMENT_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=(?P<value>.+)$")
YAML_FOLDED_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:-\s+)?[^:#\r\n][^:\r\n]*:\s*>[1-9]?[+-]?\s*(?:#.*)?$"
)
SHELL_SEPARATOR_RE = re.compile(r"&&|\|\||[;|&]")
SHELL_COMMENT_RE = re.compile(r"\s+#")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ISSUE_RE = re.compile(r"^#[1-9][0-9]*$")


@dataclass(frozen=True)
class GuidanceMatch:
    """One raw requirements-install command found in a tracked text file."""

    path: str
    line_number: int
    text_sha256: str

    @property
    def key(self) -> tuple[str, str]:
        """Return the stable path-and-text identity for this match."""
        return (self.path, self.text_sha256)


@dataclass(frozen=True)
class GuidanceException:
    """One exact, bounded exception for cross-track install guidance."""

    path: str
    text_sha256: str
    occurrences: int
    expires: date
    owner: str
    issue: str
    reason: str

    @property
    def key(self) -> tuple[str, str]:
        """Return the exact exception lookup key."""
        return (self.path, self.text_sha256)


def _line_sha256(text: str) -> str:
    """Hash one normalized logical source line for a reviewable text identity."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _tracked_text_paths(root: Path) -> list[Path]:
    """Return every non-binary tracked path that may expose install guidance."""
    completed = subprocess.run(
        ["git", "grep", "-I", "-l", "-z", "-e", "", "--"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if completed.returncode not in {0, 1}:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"cannot enumerate git-tracked text: {stderr or completed.returncode}")
    paths: list[Path] = []
    for raw_path in completed.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if not raw_path or raw_path in IGNORED_PATHS:
            continue
        paths.append(Path(raw_path))
    return paths


def _continuation_marker(line: str, next_line: str | None) -> str | None:
    """Return a shell, PowerShell, or CMD continuation marker."""
    stripped = line.rstrip()
    trailing_backslashes = len(stripped) - len(stripped.rstrip("\\"))
    if trailing_backslashes % 2 == 1:
        return "\\"
    if next_line is None:
        return None
    next_is_continuation = bool(
        next_line[:1].isspace() or next_line.lstrip().startswith(("-", "/"))
    )
    if not next_is_continuation:
        return None
    for marker in ("`", "^"):
        trailing_markers = len(stripped) - len(stripped.rstrip(marker))
        if trailing_markers % 2 == 1:
            return marker
    return None


def _indent_width(line: str) -> int:
    """Return a stable indentation width for YAML block-boundary checks."""
    return len(line.expandtabs(8)) - len(line.lstrip(" \t").expandtabs(8))


def _folded_physical_lines(text: str) -> list[tuple[int, str]]:
    """Fold YAML ``>`` scalars as the runner does before shell execution."""
    source_lines = text.splitlines()
    normalized: list[tuple[int, str]] = []
    index = 0
    while index < len(source_lines):
        line = source_lines[index]
        header = YAML_FOLDED_HEADER_RE.fullmatch(line)
        if header is None:
            normalized.append((index + 1, line))
            index += 1
            continue

        normalized.append((index + 1, line))
        header_indent = _indent_width(header.group("indent"))
        block_parts: list[str] = []
        block_start: int | None = None
        cursor = index + 1
        while cursor < len(source_lines):
            candidate = source_lines[cursor]
            if candidate.strip() and _indent_width(candidate) <= header_indent:
                break
            if candidate.strip():
                block_start = block_start or cursor + 1
                block_parts.append(candidate.strip())
            cursor += 1
        if block_parts:
            normalized.append((block_start or index + 2, " ".join(block_parts)))
        index = cursor
    return normalized


def _logical_lines(text: str) -> Iterable[tuple[int, str]]:
    """Normalize folded YAML and explicit continuations into shell commands."""
    physical_lines = _folded_physical_lines(text)
    parts: list[str] = []
    start_line = 1
    for index, (line_number, physical_line) in enumerate(physical_lines):
        if not parts:
            start_line = line_number
        next_line = physical_lines[index + 1][1] if index + 1 < len(physical_lines) else None
        marker = _continuation_marker(physical_line, next_line)
        stripped = physical_line.rstrip()
        if marker is not None:
            stripped = stripped[: -len(marker)]
        parts.append(stripped.strip())
        if marker is not None:
            continue
        yield start_line, " ".join(part for part in parts if part)
        parts = []
    if parts:
        yield start_line, " ".join(part for part in parts if part)


def _command_segment(text: str, match: re.Match[str]) -> tuple[str, int]:
    """Return the shell command containing a requirements install, without comments."""
    start = 0
    for separator in SHELL_SEPARATOR_RE.finditer(text, 0, match.start()):
        start = separator.end()
    end = len(text)
    next_separator = SHELL_SEPARATOR_RE.search(text, match.end())
    if next_separator is not None:
        end = next_separator.start()
    segment = text[start:end]
    relative_match_start = match.start() - start
    comment = SHELL_COMMENT_RE.search(segment, relative_match_start)
    if comment is not None:
        segment = segment[: comment.start()]
    return segment, relative_match_start


def _shell_words(text: str) -> list[str]:
    """Split a shell fragment into tolerant, quote-aware words."""
    words: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    for character in text:
        if escaped:
            current.append(character)
            escaped = False
            continue
        if character == "\\" and quote != "'":
            escaped = True
            continue
        if quote is not None:
            if character == quote:
                quote = None
            else:
                current.append(character)
            continue
        if character in {"'", '"'}:
            quote = character
            continue
        if character.isspace():
            if current:
                words.append("".join(current))
                current = []
            continue
        current.append(character)
    if escaped:
        current.append("\\")
    if current:
        words.append("".join(current))
    return words


def _unclosed_quote_start(text: str) -> int | None:
    """Return the start of an outer presentation quote that remains open."""
    quote: str | None = None
    quote_start: int | None = None
    escaped = False
    for index, character in enumerate(text):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote != "'":
            escaped = True
            continue
        if quote is None and character in {"'", '"'}:
            quote = character
            quote_start = index
        elif quote is not None and character == quote:
            quote = None
            quote_start = None
    return quote_start


def _has_cli_build_constraint(command: str) -> bool:
    """Recognize a complete pip build-constraint option token."""
    words = _shell_words(command)
    for index, word in enumerate(words):
        if word.startswith("--build-constraint="):
            return bool(word.partition("=")[2])
        if word == "--build-constraint" and index + 1 < len(words):
            return bool(words[index + 1]) and not words[index + 1].startswith("-")
    return False


def _assignment_prefix_has_build_constraint(words: list[str]) -> bool:
    """Require every command-prefix word to be an environment assignment."""
    if words[:1] == ["RUN"]:
        words = words[1:]
        while words and words[0].startswith("--mount="):
            words = words[1:]
    if words[:1] == ["env"]:
        words = words[1:]
    if not words:
        return False

    assignments: dict[str, str] = {}
    for word in words:
        assignment = ENVIRONMENT_ASSIGNMENT_RE.fullmatch(word)
        if assignment is None:
            return False
        assignments[word.partition("=")[0]] = assignment.group("value").strip()
    return bool(assignments.get("PIP_BUILD_CONSTRAINT"))


def _has_environment_build_constraint(prefix: str) -> bool:
    """Recognize a command-prefix assignment, including quoted guidance text."""
    if _assignment_prefix_has_build_constraint(_shell_words(prefix)):
        return True
    quote_start = _unclosed_quote_start(prefix)
    return bool(
        quote_start is not None
        and _assignment_prefix_has_build_constraint(_shell_words(prefix[quote_start + 1 :]))
    )


def _has_build_constraint(text: str, match: re.Match[str]) -> bool:
    """Require a real CLI option or environment assignment in the same command."""
    segment, install_start = _command_segment(text, match)
    return _has_cli_build_constraint(segment[install_start:]) or _has_environment_build_constraint(
        segment[:install_start]
    )


def _scan_paths(root: Path, relative_paths: Iterable[Path]) -> list[GuidanceMatch]:
    """Find raw requirements-install commands without an inline build constraint."""
    matches: list[GuidanceMatch] = []
    for relative_path in relative_paths:
        try:
            text = (root / relative_path).read_text(encoding="utf-8", errors="surrogateescape")
        except OSError as exc:
            raise ValueError(f"{relative_path}: cannot scan tracked text: {exc}") from exc
        for line_number, logical_line in _logical_lines(text):
            for match in REQUIREMENTS_INSTALL_RE.finditer(logical_line):
                if _has_build_constraint(logical_line, match):
                    continue
                matches.append(
                    GuidanceMatch(
                        path=relative_path.as_posix(),
                        line_number=line_number,
                        text_sha256=_line_sha256(logical_line),
                    )
                )
    return matches


def _load_exceptions(
    path: Path,
    today: date,
) -> tuple[dict[tuple[str, str], GuidanceException], list[str]]:
    """Load exact guidance exceptions and enforce schema and time bounds."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"{path}: cannot load install-guidance exceptions: {exc}"]

    if not isinstance(raw, dict) or set(raw) != {"exceptions"} or not isinstance(raw["exceptions"], list):
        return {}, [f"{path}: expected one 'exceptions' array"]

    exceptions: dict[tuple[str, str], GuidanceException] = {}
    errors: list[str] = []
    required = {"path", "text_sha256", "occurrences", "expires", "owner", "issue", "reason"}
    for index, item in enumerate(raw["exceptions"]):
        label = f"{path}: exceptions[{index}]"
        if not isinstance(item, dict) or set(item) != required:
            errors.append(f"{label}: expected exactly {sorted(required)}")
            continue
        string_fields = required - {"occurrences"}
        if not all(isinstance(item[field], str) and item[field].strip() for field in string_fields):
            errors.append(f"{label}: every string field must be non-empty")
            continue
        relative_path = Path(item["path"])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            errors.append(f"{label}: path must be repository-relative without '..'")
            continue
        if not SHA256_RE.fullmatch(item["text_sha256"]):
            errors.append(f"{label}: text_sha256 must be 64 lowercase hexadecimal characters")
            continue
        if not isinstance(item["occurrences"], int) or isinstance(item["occurrences"], bool) or item["occurrences"] < 1:
            errors.append(f"{label}: occurrences must be a positive integer")
            continue
        if not ISSUE_RE.fullmatch(item["issue"]):
            errors.append(f"{label}: issue must use the '#123' form")
            continue
        try:
            expiry = date.fromisoformat(item["expires"])
        except ValueError:
            errors.append(f"{label}: expires must use YYYY-MM-DD")
            continue
        exception = GuidanceException(
            path=item["path"],
            text_sha256=item["text_sha256"],
            occurrences=item["occurrences"],
            expires=expiry,
            owner=item["owner"],
            issue=item["issue"],
            reason=item["reason"],
        )
        if exception.expires < today:
            errors.append(f"{label}: exception expired on {exception.expires.isoformat()}")
            continue
        if exception.expires > today + timedelta(days=MAX_EXCEPTION_DAYS):
            errors.append(f"{label}: exception exceeds the {MAX_EXCEPTION_DAYS}-day maximum")
            continue
        if exception.key in exceptions:
            errors.append(f"{label}: duplicate exception for {exception.key}")
            continue
        exceptions[exception.key] = exception
    return exceptions, errors


def check_repository(
    root: Path,
    exception_path: Path,
    current_date: date,
    relative_paths: Iterable[Path] | None = None,
) -> tuple[list[str], int, int]:
    """Validate all raw guidance against exact, live, and used exceptions."""
    exceptions, errors = _load_exceptions(exception_path, current_date)
    paths: list[Path] = []
    try:
        paths = list(relative_paths) if relative_paths is not None else _tracked_text_paths(root)
        matches = _scan_paths(root, paths)
    except ValueError as exc:
        return errors + [str(exc)], len(paths), 0

    matches_by_key: dict[tuple[str, str], list[GuidanceMatch]] = {}
    for match in matches:
        matches_by_key.setdefault(match.key, []).append(match)

    used: set[tuple[str, str]] = set()
    for key, grouped_matches in sorted(matches_by_key.items()):
        exception = exceptions.get(key)
        if exception is None:
            for match in grouped_matches:
                errors.append(
                    f"{match.path}:{match.line_number}: raw requirements-install guidance is not bounded "
                    f"(text_sha256={match.text_sha256})"
                )
            continue
        used.add(key)
        if len(grouped_matches) != exception.occurrences:
            errors.append(
                f"{exception_path}: exception for {key} expects {exception.occurrences} occurrences, "
                f"found {len(grouped_matches)}"
            )

    for key in sorted(set(exceptions) - used):
        errors.append(f"{exception_path}: unused install-guidance exception for {key}")
    return errors, len(paths), len(matches)


def _write_fixture_registry(path: Path, exceptions: list[dict[str, object]]) -> None:
    """Write one isolated exception fixture for self-tests."""
    path.write_text(json.dumps({"exceptions": exceptions}), encoding="utf-8")


def run_self_tests() -> None:
    """Exercise compliant, drift, count, schema, and expiry behavior."""
    today = date(2026, 7, 22)
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        fixture = root / "fixture.py"
        exception_path = root / "exceptions.json"
        paths = [Path("fixture.py")]

        fixture.write_text("pip install --build-constraint build.txt -r requirements.txt\n", encoding="utf-8")
        _write_fixture_registry(exception_path, [])
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if errors:
            raise AssertionError(f"compliant guidance failed: {errors!r}")

        raw_command = (
            "pip "
            "install -r requirements.txt"
        )
        raw_line = f'print("Run {raw_command}")'
        fixture.write_text(f"{raw_line}\n", encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"raw guidance was accepted: {errors!r}")

        exception: dict[str, object] = {
            "path": "fixture.py",
            "text_sha256": _line_sha256(raw_line),
            "occurrences": 1,
            "expires": "2026-08-20",
            "owner": "fixture-owner",
            "issue": "#400",
            "reason": "Fixture for bounded exception validation.",
        }
        _write_fixture_registry(exception_path, [exception])
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if errors:
            raise AssertionError(f"active exception failed: {errors!r}")

        fixture.write_text(f"{raw_line}\n{raw_line}\n", encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("expects 1 occurrences" in error for error in errors):
            raise AssertionError(f"occurrence drift was accepted: {errors!r}")

        drift_command = (
            "pip "
            "install -r other-requirements.txt"
        )
        fixture.write_text(f'print("Run {drift_command}")\n', encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors) or not any("unused" in error for error in errors):
            raise AssertionError(f"text drift was accepted: {errors!r}")

        fixture.write_text(f"{raw_line}\n", encoding="utf-8")
        exception["expires"] = "2026-07-21"
        _write_fixture_registry(exception_path, [exception])
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("expired" in error for error in errors):
            raise AssertionError(f"expired exception was accepted: {errors!r}")

        exception["expires"] = "2026-08-22"
        _write_fixture_registry(exception_path, [exception])
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("30-day maximum" in error for error in errors):
            raise AssertionError(f"overlong exception was accepted: {errors!r}")

        exception["expires"] = "2026-08-20"
        _write_fixture_registry(exception_path, [exception, exception])
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("duplicate exception" in error for error in errors):
            raise AssertionError(f"duplicate exception was accepted: {errors!r}")

        invalid_issue = dict(exception)
        invalid_issue["issue"] = "400"
        _write_fixture_registry(exception_path, [invalid_issue])
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("'#123'" in error for error in errors):
            raise AssertionError(f"invalid issue was accepted: {errors!r}")

        _write_fixture_registry(exception_path, [])
        raw_continuation = "pi" "p install \\\n  -r requirements.txt\n"
        fixture.write_text(raw_continuation, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"continued raw guidance was accepted: {errors!r}")

        raw_powershell_continuation = "pi" "p install `\n  -r requirements.txt\n"
        fixture.write_text(raw_powershell_continuation, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"PowerShell continuation bypass was accepted: {errors!r}")

        raw_compact_requirement = "pi" "p install -rrequirements.txt\n"
        fixture.write_text(raw_compact_requirement, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"compact requirement bypass was accepted: {errors!r}")

        raw_no_space_powershell = "pi" "p install`\n  -r requirements.txt\n"
        fixture.write_text(raw_no_space_powershell, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"no-space PowerShell bypass was accepted: {errors!r}")

        raw_cmd_continuation = "pi" "p install ^\n  -r requirements.txt\n"
        fixture.write_text(raw_cmd_continuation, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"CMD continuation bypass was accepted: {errors!r}")

        raw_folded_workflow = "steps:\n  - run: >-\n      pi" "p install\n      -r requirements.txt\n"
        fixture.write_text(raw_folded_workflow, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"folded workflow bypass was accepted: {errors!r}")

        comment_option_bypass = "pi" "p install -r requirements.txt # --build-constraint build.txt\n"
        fixture.write_text(comment_option_bypass, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"commented option bypass was accepted: {errors!r}")

        comment_environment_bypass = (
            "pi" "p install -r requirements.txt # PIP_BUILD_CONSTRAINT=build.txt\n"
        )
        fixture.write_text(comment_environment_bypass, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"commented environment bypass was accepted: {errors!r}")

        compliant_continuation = (
            "python -m pip install \\\n"
            "  --build-constraint build.txt \\\n"
            "  -r requirements.txt\n"
        )
        fixture.write_text(compliant_continuation, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if errors:
            raise AssertionError(f"compliant continued guidance failed: {errors!r}")

        raw_global_option = (
            "python -m pi" "p --disable-pip-version-check install -r requirements.txt\n"
        )
        fixture.write_text(raw_global_option, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"pip global-option bypass was accepted: {errors!r}")

        compliant_environment = (
            "PIP_BUILD_CONSTRAINT=build.txt python -m pip --disable-pip-version-check "
            "install -r requirements.txt\n"
        )
        fixture.write_text(compliant_environment, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if errors:
            raise AssertionError(f"compliant environment guidance failed: {errors!r}")

        decoy_environment = (
            'DECOY="PIP_BUILD_CONSTRAINT=decoy.txt" pi' "p install -r requirements.txt\n"
        )
        fixture.write_text(decoy_environment, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"decoy environment assignment was accepted: {errors!r}")

        positional_environment = (
            "echo PIP_BUILD_CONSTRAINT=decoy.txt pi" "p install -r requirements.txt\n"
        )
        fixture.write_text(positional_environment, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"positional environment assignment was accepted: {errors!r}")

        represented_environment = (
            'assert "PIP_BUILD_CONSTRAINT=build.txt pi' "p install -r requirements.txt\"\n"
        )
        fixture.write_text(represented_environment, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if errors:
            raise AssertionError(f"represented environment guidance failed: {errors!r}")

        decoy_cli_option = (
            'DECOY="--build-constraint decoy.txt" pi' "p install -r requirements.txt\n"
        )
        fixture.write_text(decoy_cli_option, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"decoy CLI option was accepted: {errors!r}")

        compliant_folded_workflow = (
            "steps:\n  - run: >\n      pip install --build-constraint build.txt\n"
            "      -r requirements.txt\n"
        )
        fixture.write_text(compliant_folded_workflow, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if errors:
            raise AssertionError(f"compliant folded workflow failed: {errors!r}")

        quoted_raw_guidance = "pi" 'p install -r "requirements.txt"\n'
        fixture.write_text(quoted_raw_guidance, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"quoted requirements path bypass was accepted: {errors!r}")

        inline_markdown = "Run `pi" "p install -r requirements.txt`\nNext line\n"
        logical_markdown = list(_logical_lines(inline_markdown))
        if len(logical_markdown) != 2:
            raise AssertionError(f"Markdown closing backtick was treated as continuation: {logical_markdown!r}")

        pipeline_bypass = (
            "echo --build-constraint build.txt | pi" "p install -r requirements.txt\n"
        )
        fixture.write_text(pipeline_bypass, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"cross-pipeline constraint bypass was accepted: {errors!r}")

        late_environment_bypass = (
            "pi" "p install -r requirements.txt PIP_BUILD_CONSTRAINT=build.txt\n"
        )
        fixture.write_text(late_environment_bypass, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"late environment assignment bypass was accepted: {errors!r}")

        discovery_root = root / "tracked-discovery"
        discovery_root.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=discovery_root, check=True)
        raw_discovery_guidance = "pi" "p install -r requirements.txt\n"
        expected_text_paths = {
            "Makefile",
            "install.bat",
            "install.cmd",
            "notes.unknown",
            "pyproject.toml",
            "setup.cfg",
        }
        for relative_path in expected_text_paths:
            (discovery_root / relative_path).write_text(raw_discovery_guidance, encoding="utf-8")
        (discovery_root / "binary.bin").write_bytes(b"\x00pi" b"p install -r requirements.txt\x00")
        (discovery_root / "docs").mkdir()
        (discovery_root / "docs" / "CHANGELOG.md").write_text(raw_discovery_guidance, encoding="utf-8")
        (discovery_root / "CLAUDE.md").write_text(raw_discovery_guidance, encoding="utf-8")
        subprocess.run(["git", "add", "--all"], cwd=discovery_root, check=True)
        discovered_paths = _tracked_text_paths(discovery_root)
        if {path.as_posix() for path in discovered_paths} != expected_text_paths:
            raise AssertionError(f"tracked text discovery drifted: {discovered_paths!r}")
        discovered_matches = _scan_paths(discovery_root, discovered_paths)
        if {match.path for match in discovered_matches} != expected_text_paths:
            raise AssertionError(f"cross-extension guidance was missed: {discovered_matches!r}")

    print("Install-guidance self-tests passed (30 cases).")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Run self-tests or validate repository install guidance."""
    args = parse_args()
    if args.self_test:
        run_self_tests()
        return 0
    errors, path_count, match_count = check_repository(ROOT, args.exceptions, date.today())
    if errors:
        print("Install-guidance validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        f"Install-guidance checks passed for {path_count} tracked text files "
        f"with {match_count} bounded references."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
