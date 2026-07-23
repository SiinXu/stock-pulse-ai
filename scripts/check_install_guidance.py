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

PIP_WORD_RE = re.compile(r"^pip(?:3(?:\.\d+)?)?(?:\.exe)?$", re.IGNORECASE)
PIP_MODULE_RE = re.compile(r"^pip(?:\.__main__)?$", re.IGNORECASE)
COMPACT_PIP_MODULE_RE = re.compile(r"^-mpip(?:\.__main__)?$", re.IGNORECASE)
PYTHON_WORD_RE = re.compile(
    r"^(?:python(?:3(?:\.\d+)?)?|py)(?:\.exe)?$",
    re.IGNORECASE,
)
PIP_COMBINABLE_FLAG_CHARS = frozenset("qvUI")
ENVIRONMENT_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=(?P<value>.+)$")
DOCKER_RUN_EXEC_RE = re.compile(
    r"^\s*RUN(?P<options>(?:\s+--[^\s]+)*)\s+(?P<body>\[.*\])\s*$",
    re.IGNORECASE,
)
COMMAND_SUBSTITUTION_MARKER = "__STOCKPULSE_COMMAND_SUBSTITUTION__"
SUBSTITUTION_PREFIXES = ("$(", "<(", ">(")
DYNAMIC_CONSTRAINT_RE = re.compile(r"\$|`|%|![^!]+!|[<>]\(")
SHELL_REDIRECTION_RE = re.compile(r"<<<|<<|<>|>>|>\||<|>")
YAML_FOLDED_MAPPING_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<sequence>-\s+)?[^:#\r\n][^:\r\n]*:\s*"
    r"(?:(?:&[^\s#]+|![^\s#]+)\s+)*>"
    r"(?P<modifiers>(?:[+-][1-9]?)|(?:[1-9][+-]?))?\s*(?:#.*)?$"
)
YAML_EMPTY_VALUE_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<sequence>-\s+)?[^:#\r\n][^:\r\n]*:\s*"
    r"(?:(?:&[^\s#]+|![^\s#]+)[ \t]+)*"
    r"(?:(?:&[^\s#]+|![^\s#]+)[ \t]*)?(?:#.*)?$"
)
YAML_FOLDED_VALUE_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]+)(?:(?:&[^\s#]+|![^\s#]+)\s+)*>"
    r"(?P<modifiers>(?:[+-][1-9]?)|(?:[1-9][+-]?))?\s*(?:#.*)?$"
)
YAML_NODE_PROPERTY_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]+)(?:(?:&[^\s#]+|![^\s#]+)[ \t]+)*"
    r"(?:&[^\s#]+|![^\s#]+)[ \t]*(?:#.*)?$"
)
SHELL_QUOTES = frozenset({"'", '"', "`"})
PRESENTATION_EDGE_CHARS = "*_()[]{}:,`"
MODULE_EDGE_CHARS = "*()[]{}:,`"
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


def _mapping_key_indent(header: re.Match[str]) -> int:
    """Return the YAML mapping-key column, including a sequence marker."""
    prefix = header.group("indent") + (header.groupdict().get("sequence") or "")
    return len(prefix.expandtabs(8))


def _explicit_scalar_indent(header: re.Match[str], parent_indent: int) -> int | None:
    """Return the content baseline declared by a block indentation indicator."""
    modifiers = header.groupdict().get("modifiers") or ""
    indicator = next((int(character) for character in modifiers if character.isdigit()), None)
    return parent_indent + indicator if indicator is not None else None


def _continued_folded_header(
    source_lines: list[str],
    index: int,
) -> tuple[re.Match[str], int] | None:
    """Recognize a folded value declared below an empty YAML mapping key."""
    header = YAML_FOLDED_VALUE_HEADER_RE.fullmatch(source_lines[index])
    if header is None:
        return None
    header_indent = _indent_width(header.group("indent"))
    cursor = index - 1
    while cursor >= 0:
        candidate = source_lines[cursor]
        if not candidate.strip() or candidate.lstrip().startswith("#"):
            cursor -= 1
            continue
        properties = YAML_NODE_PROPERTY_LINE_RE.fullmatch(candidate)
        if properties is not None and _indent_width(properties.group("indent")) == header_indent:
            cursor -= 1
            continue
        parent = YAML_EMPTY_VALUE_HEADER_RE.fullmatch(candidate)
        if parent is not None:
            parent_indent = _mapping_key_indent(parent)
            if header_indent > parent_indent:
                return header, parent_indent
        return None
    return None


def _folded_physical_lines(text: str) -> list[tuple[int, str]]:
    """Fold YAML ``>`` scalars as the runner does before shell execution."""
    source_lines = text.splitlines()
    normalized: list[tuple[int, str]] = []
    index = 0
    while index < len(source_lines):
        line = source_lines[index]
        header = YAML_FOLDED_MAPPING_HEADER_RE.fullmatch(line)
        parent_indent: int | None = None
        if header is not None:
            parent_indent = _mapping_key_indent(header)
        if header is None:
            continued_header = _continued_folded_header(source_lines, index)
            if continued_header is not None:
                header, parent_indent = continued_header
        if header is None or parent_indent is None:
            normalized.append((index + 1, line))
            index += 1
            continue

        normalized.append((index + 1, line))
        block_lines: list[str] = []
        block_start: int | None = None
        cursor = index + 1
        while cursor < len(source_lines):
            candidate = source_lines[cursor]
            if candidate.strip() and _indent_width(candidate) <= parent_indent:
                break
            if candidate.strip():
                block_start = block_start or cursor + 1
            block_lines.append(candidate)
            cursor += 1
        if block_start is not None:
            content_indent = _explicit_scalar_indent(header, parent_indent)
            if content_indent is None:
                content_indent = next(
                    _indent_width(block_line) for block_line in block_lines if block_line.strip()
                )
            folded = ""
            previous_indent: int | None = None
            blank_boundary = False
            for block_line in block_lines:
                if not block_line.strip():
                    blank_boundary = True
                    continue
                current_indent = _indent_width(block_line)
                if folded:
                    preserves_newline = (
                        blank_boundary
                        or current_indent != content_indent
                        or previous_indent != content_indent
                    )
                    folded += "\n" if preserves_newline else " "
                folded += block_line.strip()
                previous_indent = current_indent
                blank_boundary = False
            normalized.append((block_start, folded))
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


def _quoted_views(text: str) -> Iterable[str]:
    """Yield raw text and each quoted presentation span as independent shell views."""
    yield text
    quote: str | None = None
    content: list[str] = []
    escaped = False
    for character in text:
        if escaped:
            if quote is not None:
                content.append(character)
            escaped = False
            continue
        if character == "\\" and quote != "'":
            escaped = True
            continue
        if quote is None:
            if character in SHELL_QUOTES:
                quote = character
                content = []
            continue
        if character == quote:
            if content:
                yield "".join(content)
            quote = None
            content = []
            continue
        content.append(character)
    if quote is not None and content:
        yield "".join(content)


def _command_substitution_end(text: str, start: int) -> int | None:
    """Return the closing parenthesis for one balanced shell substitution."""
    depth = 1
    quote: str | None = None
    escaped = False
    index = start + 2
    while index < len(text):
        character = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if character == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote is not None:
            if character == quote:
                quote = None
            index += 1
            continue
        if character in SHELL_QUOTES:
            quote = character
            index += 1
            continue
        if text.startswith("$(", index):
            depth += 1
            index += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _command_views(text: str) -> Iterable[str]:
    """Yield an outer command and isolated command/process substitutions."""
    outer: list[str] = []
    substitutions: list[str] = []
    index = 0
    while index < len(text):
        prefix = text[index : index + 2]
        if prefix in SUBSTITUTION_PREFIXES:
            preceding_backslashes = 0
            cursor = index - 1
            while cursor >= 0 and text[cursor] == "\\":
                preceding_backslashes += 1
                cursor -= 1
            if preceding_backslashes % 2 == 0:
                end = _command_substitution_end(text, index)
                if end is not None:
                    substitutions.append(text[index + len(prefix) : end])
                    outer.append(COMMAND_SUBSTITUTION_MARKER)
                    index = end + 1
                    continue
        outer.append(text[index])
        index += 1

    yield "".join(outer)
    for substitution in substitutions:
        yield from _command_views(substitution)


def _shell_segments(text: str) -> Iterable[str]:
    """Split commands on unquoted separators, newlines, and shell comments."""
    current: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(text):
        character = text[index]
        if escaped:
            current.append(character)
            escaped = False
            index += 1
            continue
        if character == "\\" and quote != "'":
            current.append(character)
            escaped = True
            index += 1
            continue
        if quote is not None:
            current.append(character)
            if character == quote:
                quote = None
            index += 1
            continue
        if character in SHELL_QUOTES:
            quote = character
            current.append(character)
            index += 1
            continue
        if character == "#" and (not current or current[-1].isspace()):
            segment = "".join(current).strip()
            if segment:
                yield segment
            current = []
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if character in ";|&\r\n":
            segment = "".join(current).strip()
            if segment:
                yield segment
            current = []
            index += 1
            continue
        current.append(character)
        index += 1
    segment = "".join(current).strip()
    if segment:
        yield segment


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
            current.append(character)
            escaped = True
            continue
        if quote is not None:
            if character == quote:
                if quote == "`":
                    current.append(character)
                quote = None
            else:
                current.append(character)
            continue
        if character in SHELL_QUOTES:
            quote = character
            if character == "`":
                current.append(character)
            continue
        if character.isspace():
            if current:
                words.append("".join(current))
                current = []
            continue
        current.append(character)
    if current:
        words.append("".join(current))
    return words


def _presentation_word(word: str) -> str:
    """Remove surrounding prose punctuation without altering option syntax."""
    return word.strip(PRESENTATION_EDGE_CHARS)


def _module_word(word: str) -> str:
    """Remove prose punctuation while preserving ``pip.__main__`` underscores."""
    return word.strip(MODULE_EDGE_CHARS)


def _shell_unescaped_word(word: str) -> str:
    """Return the POSIX-shell interpretation of retained backslash escapes."""
    unescaped: list[str] = []
    index = 0
    while index < len(word):
        if word[index] == "\\" and index + 1 < len(word):
            index += 1
        unescaped.append(word[index])
        index += 1
    return "".join(unescaped)


def _word_variants(word: str, *, module: bool = False) -> tuple[str, ...]:
    """Return Windows-path-preserving and POSIX-unescaped word views."""
    cleaner = _module_word if module else _presentation_word
    preserved = cleaner(word)
    if "\\" not in word:
        return (preserved,)
    unescaped = cleaner(_shell_unescaped_word(word))
    return tuple(dict.fromkeys((preserved, unescaped)))


def _word_is(word: str, expected: str, *, module: bool = False) -> bool:
    """Match one shell word under either supported backslash interpretation."""
    expected = expected.lower()
    return any(
        candidate.lower() == expected
        for candidate in _word_variants(word, module=module)
    )


def _is_pip_executable(word: str) -> bool:
    """Recognize bare and path-qualified pip executables on Unix and Windows."""
    return any(
        PIP_WORD_RE.fullmatch(candidate.replace("\\", "/").rsplit("/", 1)[-1])
        for candidate in _word_variants(word)
    )


def _is_python_executable(word: str) -> bool:
    """Recognize bare and path-qualified Python launchers."""
    return any(
        PYTHON_WORD_RE.fullmatch(candidate.replace("\\", "/").rsplit("/", 1)[-1])
        for candidate in _word_variants(word)
    )


def _static_constraint_value(value: str) -> bool:
    """Require a non-option constraint path without runtime interpolation."""
    normalized = _presentation_word(_shell_unescaped_word(value))
    return bool(
        normalized
        and not normalized.startswith("-")
        and COMMAND_SUBSTITUTION_MARKER not in value
        and DYNAMIC_CONSTRAINT_RE.search(value) is None
    )


def _has_cli_build_constraint(words: list[str]) -> bool:
    """Recognize a complete pip build-constraint option token."""
    for index, raw_word in enumerate(words):
        variants = _word_variants(raw_word)
        if "--" in variants:
            break
        inline_values = [
            word.partition("=")[2]
            for word in variants
            if word.startswith("--build-constraint=")
        ]
        if inline_values:
            if any(_static_constraint_value(value) for value in inline_values):
                return True
            continue
        if "--build-constraint" in variants and index + 1 < len(words):
            if _static_constraint_value(words[index + 1]):
                return True
    return False


def _assignment_prefix_has_build_constraint(words: list[str]) -> bool:
    """Require every command-prefix word to be an environment assignment."""
    if words and _word_is(words[0], "RUN"):
        words = words[1:]
        while words and words[0].startswith("--mount="):
            words = words[1:]
    if words and _word_is(words[0], "env"):
        words = words[1:]
    if not words:
        return False

    assignments: dict[str, str] = {}
    for raw_word in words:
        word = _module_word(raw_word)
        assignment = ENVIRONMENT_ASSIGNMENT_RE.fullmatch(word)
        if assignment is None:
            return False
        assignments[word.partition("=")[0]] = assignment.group("value").strip()
    constraint = assignments.get("PIP_BUILD_CONSTRAINT", "")
    return _static_constraint_value(constraint)


def _requirements_value(value: str) -> bool:
    """Require a non-empty value for a pip requirements-file option."""
    return any(candidate and candidate != "--" for candidate in _word_variants(value))


def _has_requirements_option(words: list[str]) -> bool:
    """Recognize long, separated short, and compact short requirement options."""
    for index, raw_word in enumerate(words):
        variants = _word_variants(raw_word)
        if "--" in variants:
            break
        if any(word in {"-r", "--requirement"} for word in variants):
            if index + 1 < len(words) and _requirements_value(words[index + 1]):
                return True
            continue
        if any(
            word.startswith("--requirement=") and _requirements_value(word.partition("=")[2])
            for word in variants
        ):
            return True
        for word in variants:
            if not word.startswith("-") or word.startswith("--"):
                continue
            short_options = word[1:]
            requirement_index = short_options.find("r")
            if requirement_index < 0 or not set(
                short_options[:requirement_index]
            ).issubset(PIP_COMBINABLE_FLAG_CHARS):
                continue
            value = short_options[requirement_index + 1 :].removeprefix("=")
            if value:
                if _requirements_value(value):
                    return True
                continue
            if index + 1 < len(words) and _requirements_value(words[index + 1]):
                return True
    return False


def _python_pip_argument_start(words: list[str], python_index: int) -> int | None:
    """Return pip's first argument after valid Python launcher options."""
    cursor = python_index + 1
    options_with_value = {"-W", "-X", "--check-hash-based-pycs"}
    while cursor < len(words):
        variants = _word_variants(words[cursor], module=True)
        if any(COMPACT_PIP_MODULE_RE.fullmatch(word) for word in variants):
            return cursor + 1
        if "-m" in variants:
            if cursor + 1 < len(words) and any(
                PIP_MODULE_RE.fullmatch(word)
                for word in _word_variants(words[cursor + 1], module=True)
            ):
                return cursor + 2
            return None
        if "--" in variants or any(
            word == "-c" or word.startswith("-c") or word.startswith("-m")
            for word in variants
        ):
            return None
        if any(word in options_with_value for word in variants):
            cursor += 2
            continue
        if any(
            (word.startswith("-W") or word.startswith("-X")) and len(word) > 2
            for word in variants
        ) or any(word.startswith("--check-hash-based-pycs=") for word in variants):
            cursor += 1
            continue
        if any(word.startswith("-") for word in variants):
            cursor += 1
            continue
        return None
    return None


def _pip_invocations(words: list[str]) -> Iterable[tuple[int, list[str]]]:
    """Yield command-prefix indexes and arguments for supported pip entry points."""
    index = 0
    while index < len(words):
        if _is_python_executable(words[index]):
            argument_start = _python_pip_argument_start(words, index)
            if argument_start is not None:
                yield index, words[argument_start:]
            return
        if _is_pip_executable(words[index]):
            yield index, words[index + 1 :]
            return
        index += 1


def _without_shell_redirections(words: list[str]) -> list[str]:
    """Remove shell redirection operators and their non-argv targets."""
    filtered: list[str] = []
    skip_target = False
    for raw_word in words:
        if skip_target:
            skip_target = False
            continue
        word = _presentation_word(raw_word)
        redirection = SHELL_REDIRECTION_RE.search(word)
        if redirection is None:
            filtered.append(raw_word)
            continue
        prefix = word[: redirection.start()]
        target = word[redirection.end() :]
        if prefix and not prefix.isdigit():
            filtered.append(prefix)
        if not target:
            skip_target = True
    return filtered


def _docker_exec_words(segment: str) -> list[str] | None:
    """Parse a Docker exec-form RUN instruction into an argv-like word list."""
    match = DOCKER_RUN_EXEC_RE.fullmatch(segment)
    if match is None:
        return None
    try:
        arguments = json.loads(match.group("body"))
    except json.JSONDecodeError:
        return None
    if not isinstance(arguments, list) or not arguments or not all(
        isinstance(argument, str) for argument in arguments
    ):
        return None
    options = _shell_words(match.group("options"))
    return ["RUN", *options, *arguments]


def _unconstrained_install_count(segment: str) -> int:
    """Count unconstrained requirements installs in one lexical shell command."""
    docker_words = _docker_exec_words(segment)
    words = docker_words or _without_shell_redirections(_shell_words(segment))
    count = 0
    for invocation_start, tail in _pip_invocations(words):
        install_indexes = [
            index for index, word in enumerate(tail) if _word_is(word, "install")
        ]
        if not install_indexes:
            continue
        install_index = install_indexes[0]
        if not _has_requirements_option(tail[install_index + 1 :]):
            continue
        constrained = _has_cli_build_constraint(tail) or _assignment_prefix_has_build_constraint(
            words[:invocation_start]
        )
        if not constrained:
            count += 1
    return count


def _scan_paths(root: Path, relative_paths: Iterable[Path]) -> list[GuidanceMatch]:
    """Find raw requirements-install commands without an inline build constraint."""
    matches: list[GuidanceMatch] = []
    for relative_path in relative_paths:
        try:
            text = (root / relative_path).read_text(encoding="utf-8", errors="surrogateescape")
        except OSError as exc:
            raise ValueError(f"{relative_path}: cannot scan tracked text: {exc}") from exc
        for line_number, logical_line in _logical_lines(text):
            for command_view in _command_views(logical_line):
                for view in _quoted_views(command_view):
                    for segment in _shell_segments(view):
                        unconstrained_count = _unconstrained_install_count(segment)
                        if not unconstrained_count:
                            continue
                        for _ in range(unconstrained_count):
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

        requirement_value_variants = {
            "nonstandard requirements filename": "pi" "p install -r deps.txt\n",
            "dynamic requirements filename": (
                'REQ=requirements.txt; pi' 'p install -r "$REQ"\n'
            ),
        }
        for label, command in requirement_value_variants.items():
            fixture.write_text(command, encoding="utf-8")
            errors, _, _ = check_repository(root, exception_path, today, paths)
            if not any("not bounded" in error for error in errors):
                raise AssertionError(f"{label} bypass was accepted: {errors!r}")

        path_qualified_commands = {
            "absolute Unix pip": "/usr/bin/pi" "p install -r requirements.txt\n",
            "virtualenv Unix pip": ".venv/bin/pi" "p install -r requirements.txt\n",
            "virtualenv Unix pip3": ".venv/bin/pi" "p3 install -r requirements.txt\n",
            "virtualenv Windows pip": (
                ".venv\\Scripts\\pi" "p.exe install -r requirements.txt\n"
            ),
            "bare Windows pip": "pi" "p.exe install -r requirements.txt\n",
        }
        for label, command in path_qualified_commands.items():
            fixture.write_text(command, encoding="utf-8")
            errors, _, _ = check_repository(root, exception_path, today, paths)
            if not any("not bounded" in error for error in errors):
                raise AssertionError(f"{label} bypass was accepted: {errors!r}")

        escaped_shell_commands = {
            "escaped pip executable": "p" "\\ip install -r requirements.txt\n",
            "escaped install subcommand": "pi" "p in\\stall -r requirements.txt\n",
            "escaped requirements value": (
                "pi" "p install -r require\\ments.txt\n"
            ),
        }
        for label, command in escaped_shell_commands.items():
            fixture.write_text(command, encoding="utf-8")
            errors, _, _ = check_repository(root, exception_path, today, paths)
            if not any("not bounded" in error for error in errors):
                raise AssertionError(f"{label} bypass was accepted: {errors!r}")

        combined_short_options = "pi" "p install -qr requirements.txt\n"
        fixture.write_text(combined_short_options, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"combined short-option bypass was accepted: {errors!r}")

        argument_taking_short_option = "pi" "p install -cr requirements.txt\n"
        fixture.write_text(argument_taking_short_option, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if errors:
            raise AssertionError(f"non-requirement short-option cluster failed: {errors!r}")

        constrained_path_command = (
            "/usr/bin/pi" "p install --build-constraint build.txt -r requirements.txt\n"
        )
        fixture.write_text(constrained_path_command, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if errors:
            raise AssertionError(f"constrained path-qualified pip failed: {errors!r}")

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

        alternate_indicator_workflow = (
            "steps:\n  - run: >-2\n      pi" "p install\n      -r requirements.txt\n"
        )
        fixture.write_text(alternate_indicator_workflow, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"alternate folded indicator bypass was accepted: {errors!r}")

        explicit_indent_workflow = (
            "steps:\n  - run: >2\n"
            "        pi" "p install -r requirements.txt\n"
            "        echo --build-constraint decoy.txt\n"
        )
        fixture.write_text(explicit_indent_workflow, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"explicit folded indentation bypass was accepted: {errors!r}")

        anchored_folded_workflow = (
            "steps:\n  - run: &install >-\n      pi" "p install\n"
            "      -r requirements.txt\n  - run: *install\n"
        )
        fixture.write_text(anchored_folded_workflow, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"anchored folded workflow bypass was accepted: {errors!r}")

        next_line_folded_workflow = (
            "steps:\n  - run:\n      >-\n        pi" "p install\n"
            "        -r requirements.txt\n"
        )
        fixture.write_text(next_line_folded_workflow, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"next-line folded workflow bypass was accepted: {errors!r}")

        next_line_anchor_workflow = (
            "steps:\n  - run:\n      &install >-\n        pi" "p install\n"
            "        -r requirements.txt\n  - run: *install\n"
        )
        fixture.write_text(next_line_anchor_workflow, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"next-line anchor workflow bypass was accepted: {errors!r}")

        gapped_folded_workflow = (
            "steps:\n  - run:\n\n      # YAML permits comments before the value.\n"
            "      >-\n        pi" "p install\n        -r requirements.txt\n"
        )
        fixture.write_text(gapped_folded_workflow, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"gapped folded workflow bypass was accepted: {errors!r}")

        split_anchor_workflow = (
            "steps:\n  - run:\n      &install\n      >-\n        pi" "p install\n"
            "        -r requirements.txt\n  - run: *install\n"
        )
        fixture.write_text(split_anchor_workflow, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"split anchor workflow bypass was accepted: {errors!r}")

        folded_paragraph_bypass = (
            "steps:\n  - run: >\n      pi" "p install -r requirements.txt\n\n"
            "      echo --build-constraint decoy.txt\n"
        )
        fixture.write_text(folded_paragraph_bypass, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"folded paragraph bypass was accepted: {errors!r}")

        long_global_options = "--disable-pip-version-check " * 40
        long_before_install = f"pi" f"p {long_global_options}install -r requirements.txt\n"
        fixture.write_text(long_before_install, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"long pre-install command bypass was accepted: {errors!r}")

        long_install_options = "--upgrade " * 80
        long_after_install = f"pi" f"p install {long_install_options}-r requirements.txt\n"
        fixture.write_text(long_after_install, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"long install command bypass was accepted: {errors!r}")

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

        option_terminator_bypass = (
            "pi" "p install -r requirements.txt -- --build-constraint decoy.txt\n"
        )
        fixture.write_text(option_terminator_bypass, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"option-terminator bypass was accepted: {errors!r}")

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

        module_entry_points = {
            "compact Python module": "python -mpi" "p install -r requirements.txt\n",
            "pip main module": "python -m pi" "p.__main__ install -r requirements.txt\n",
            "isolated pip main module": (
                "python -I -m pi" "p.__main__ install -r requirements.txt\n"
            ),
            "version-selected Python launcher": (
                "py -3.11 -mpi" "p install -r requirements.txt\n"
            ),
            "Python option with value": (
                "python -W ignore -m pi" "p install -r requirements.txt\n"
            ),
            "path-qualified Python": (
                "/usr/bin/python3 -m pi" "p install -r requirements.txt\n"
            ),
        }
        for label, command in module_entry_points.items():
            fixture.write_text(command, encoding="utf-8")
            errors, _, _ = check_repository(root, exception_path, today, paths)
            if not any("not bounded" in error for error in errors):
                raise AssertionError(f"{label} bypass was accepted: {errors!r}")

        nested_install = "RESULT=$(pi" "p install -r requirements.txt)\n"
        fixture.write_text(nested_install, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"nested pip command bypass was accepted: {errors!r}")

        nested_constraint_decoy = (
            "pi" "p install -r requirements.txt $(true --build-constraint decoy.txt)\n"
        )
        fixture.write_text(nested_constraint_decoy, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"nested constraint decoy was accepted: {errors!r}")

        process_substitution_installs = {
            "input process substitution": (
                "cat <(pi" "p install -r requirements.txt)\n"
            ),
            "output process substitution": (
                "cat >(pi" "p install -r requirements.txt)\n"
            ),
        }
        for label, command in process_substitution_installs.items():
            fixture.write_text(command, encoding="utf-8")
            errors, _, _ = check_repository(root, exception_path, today, paths)
            if not any("not bounded" in error for error in errors):
                raise AssertionError(f"{label} bypass was accepted: {errors!r}")

        redirection_constraint_decoys = {
            "output redirection": (
                "pi" "p install -r requirements.txt > --build-constraint=decoy.txt\n"
            ),
            "file-descriptor redirection": (
                "pi" "p install -r requirements.txt 2> --build-constraint=decoy.txt\n"
            ),
            "attached output redirection": (
                "pi" "p install -r requirements.txt> --build-constraint=decoy.txt\n"
            ),
            "process-substitution redirection": (
                "pi" "p install -r requirements.txt < "
                "<(echo --build-constraint decoy.txt)\n"
            ),
        }
        for label, command in redirection_constraint_decoys.items():
            fixture.write_text(command, encoding="utf-8")
            errors, _, _ = check_repository(root, exception_path, today, paths)
            if not any("not bounded" in error for error in errors):
                raise AssertionError(f"{label} constraint decoy was accepted: {errors!r}")

        constrained_with_redirection = (
            "PIP_BUILD_CONSTRAINT=build.txt pi" "p install -r deps.txt > output.log\n"
        )
        fixture.write_text(constrained_with_redirection, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if errors:
            raise AssertionError(f"constrained redirected install failed: {errors!r}")

        dynamic_constraint_commands = {
            "environment variable": (
                "PIP_BUILD_CONSTRAINT=$UNSET pi" "p install -r requirements.txt\n"
            ),
            "command substitution": (
                "PIP_BUILD_CONSTRAINT=$(true) pi" "p install -r requirements.txt\n"
            ),
            "CLI variable": (
                "pi" "p install --build-constraint=$UNSET -r requirements.txt\n"
            ),
            "backtick command substitution": (
                "PIP_BUILD_CONSTRAINT=`true` pi" "p install -r requirements.txt\n"
            ),
            "CMD positional expansion": (
                "pi" "p install --build-constraint=%1 -r requirements.txt\n"
            ),
            "batch loop expansion": (
                "pi" "p install --build-constraint=%%A -r requirements.txt\n"
            ),
        }
        for label, command in dynamic_constraint_commands.items():
            fixture.write_text(command, encoding="utf-8")
            errors, _, _ = check_repository(root, exception_path, today, paths)
            if not any("not bounded" in error for error in errors):
                raise AssertionError(f"dynamic {label} constraint was accepted: {errors!r}")

        docker_exec_install = (
            'RUN ["pi' 'p", "install", "-r", "requirements.txt"]\n'
        )
        fixture.write_text(docker_exec_install, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"Docker exec-form bypass was accepted: {errors!r}")

        constrained_docker_exec = (
            'RUN ["pi' 'p", "install", "--build-constraint", "build.txt", '
            '"-r", "requirements.txt"]\n'
        )
        fixture.write_text(constrained_docker_exec, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if errors:
            raise AssertionError(f"constrained Docker exec form failed: {errors!r}")

        constrained_python_options = (
            "PIP_BUILD_CONSTRAINT=build.txt python -I -m pi"
            "p.__main__ install -r requirements.txt\n"
        )
        fixture.write_text(constrained_python_options, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if errors:
            raise AssertionError(f"constrained Python options failed: {errors!r}")

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

        quoted_separator_environment = (
            "DECOY='x|PIP_BUILD_CONSTRAINT=decoy.txt' pi" "p install -r requirements.txt\n"
        )
        fixture.write_text(quoted_separator_environment, encoding="utf-8")
        errors, _, _ = check_repository(root, exception_path, today, paths)
        if not any("not bounded" in error for error in errors):
            raise AssertionError(f"quoted separator assignment was accepted: {errors!r}")

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

    print("Install-guidance self-tests passed (79 cases).")


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
