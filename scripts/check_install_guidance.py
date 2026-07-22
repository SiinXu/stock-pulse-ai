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
TEXT_SUFFIXES = frozenset({".md", ".py", ".ps1", ".sh", ".ts", ".tsx", ".txt", ".yaml", ".yml"})
IGNORED_PATHS = frozenset({"CLAUDE.md", "docs/CHANGELOG.md"})

REQUIREMENTS_INSTALL_RE = re.compile(
    r"\b(?:python(?:3(?:\.\d+)?)?\s+-m\s+)?pip3?\s+install\b[^\r\n]*?"
    r"(?:-r|--requirement(?:=|\s+))\s*[^\s`\"']*requirements[^\s`\"']*\.txt",
    re.IGNORECASE,
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ISSUE_RE = re.compile(r"^#[1-9][0-9]*$")


@dataclass(frozen=True)
class GuidanceMatch:
    """One raw requirements-install line found in a tracked text file."""

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


def _line_sha256(line: str) -> str:
    """Hash one normalized source line for a reviewable text identity."""
    return hashlib.sha256(line.strip().encode("utf-8")).hexdigest()


def _tracked_text_paths(root: Path) -> list[Path]:
    """Return tracked text-like paths that may expose install guidance."""
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths: list[Path] = []
    for raw_path in completed.stdout.decode("utf-8").split("\0"):
        if not raw_path or raw_path in IGNORED_PATHS:
            continue
        path = Path(raw_path)
        if path.suffix in TEXT_SUFFIXES or path.name == "Dockerfile":
            paths.append(path)
    return paths


def _scan_paths(root: Path, relative_paths: Iterable[Path]) -> list[GuidanceMatch]:
    """Find raw requirements-install lines without an inline build constraint."""
    matches: list[GuidanceMatch] = []
    for relative_path in relative_paths:
        try:
            text = (root / relative_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"{relative_path}: cannot scan tracked text: {exc}") from exc
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not REQUIREMENTS_INSTALL_RE.search(line):
                continue
            if "--build-constraint" in line or "PIP_BUILD_CONSTRAINT" in line:
                continue
            matches.append(
                GuidanceMatch(
                    path=relative_path.as_posix(),
                    line_number=line_number,
                    text_sha256=_line_sha256(line),
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
    paths = list(relative_paths) if relative_paths is not None else _tracked_text_paths(root)
    try:
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

    print("Install-guidance self-tests passed (9 cases).")


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
