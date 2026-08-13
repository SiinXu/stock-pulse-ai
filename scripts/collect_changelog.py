#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Collect docs/changelog.d fragments into docs/CHANGELOG.md [Unreleased].

Stops concurrent PRs from editing one shared CHANGELOG.md and re-triggering
full CI via a misleading GitHub DIRTY status (see #1284).

Usage:
  python scripts/collect_changelog.py --check
  python scripts/collect_changelog.py --consume
  python scripts/collect_changelog.py --require-entry --base origin/main
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRAGMENTS_DIR = REPO_ROOT / "docs" / "changelog.d"
CHANGELOG_PATH = REPO_ROOT / "docs" / "CHANGELOG.md"

ALLOWED_TYPES = ("Added", "Changed", "Fixed", "Docs", "Tests", "Chore")
ENTRY_RE = re.compile(
    r"^- \[(?P<type>Added|Changed|Fixed|Docs|Tests|Chore)\] (?P<body>\S.*)$"
)
UNRELEASED_HEADER_RE = re.compile(r"^## \[Unreleased\]\s*$", re.MULTILINE)
NEXT_SECTION_RE = re.compile(r"^## \[", re.MULTILINE)

PRODUCT_PREFIXES = (
    "src/", "api/", "bot/", "data_provider/", "apps/", "strategies/",
    "templates/", "main.py", "server.py", "webui.py", "scripts/",
    ".github/workflows/",
)
IGNORE_PREFIXES = (
    "docs/changelog.d/", "docs/CHANGELOG.md", "tests/", ".claude/",
    ".github/instructions/", ".github/copilot-instructions.md",
    ".github/PULL_REQUEST_TEMPLATE.md", "AGENTS.md", "CLAUDE.md",
)


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


class FragmentError(Exception):
    def __init__(self, path: Path, line_no: int, message: str) -> None:
        super().__init__(f"{_display_path(path)}:{line_no}: {message}")
        self.path = path
        self.line_no = line_no


def list_fragment_files(directory: Path = FRAGMENTS_DIR) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix == ".md" and p.name != "README.md"
    )


def parse_fragment(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.rstrip()
        if not line or line.startswith("#"):
            continue
        match = ENTRY_RE.match(line)
        if match is None:
            raise FragmentError(
                path, line_no,
                "expected `- [Type] English description` with Type in "
                + "/".join(ALLOWED_TYPES),
            )
        body = match.group("body").strip()
        if not body:
            raise FragmentError(path, line_no, "description body must not be empty")
        entry_type = match.group("type")
        entries.append((entry_type, f"- [{entry_type}] {body}"))
    if not entries:
        raise FragmentError(path, 1, "fragment must contain at least one changelog entry")
    return entries


def validate_fragments(directory: Path = FRAGMENTS_DIR) -> list[tuple[str, str]]:
    collected: list[tuple[str, str]] = []
    for path in list_fragment_files(directory):
        collected.extend(parse_fragment(path))
    by_type: dict[str, list[str]] = defaultdict(list)
    for entry_type, line in collected:
        by_type[entry_type].append(line)
    ordered: list[tuple[str, str]] = []
    for entry_type in ALLOWED_TYPES:
        for line in by_type.get(entry_type, []):
            ordered.append((entry_type, line))
    return ordered


def insert_unreleased_entries(changelog_text: str, lines: list[str]) -> str:
    match = UNRELEASED_HEADER_RE.search(changelog_text)
    if match is None:
        raise ValueError("docs/CHANGELOG.md is missing an ## [Unreleased] section")
    header_end = match.end()
    rest = changelog_text[header_end:]
    next_match = NEXT_SECTION_RE.search(rest)
    if next_match is None:
        section_body, after = rest, ""
    else:
        section_body, after = rest[: next_match.start()], rest[next_match.start() :]
    existing = {line.rstrip() for line in section_body.splitlines() if line.strip()}
    new_lines = [line for line in lines if line not in existing]
    if not new_lines:
        return changelog_text
    body_stripped = section_body.lstrip("\n")
    insertion = "\n".join(new_lines) + "\n"
    if body_stripped:
        new_section = "\n" + insertion + body_stripped
        if not new_section.endswith("\n"):
            new_section += "\n"
    else:
        new_section = "\n" + insertion + "\n"
    return changelog_text[:header_end] + new_section + after


def consume_fragments(
    directory: Path = FRAGMENTS_DIR,
    changelog_path: Path = CHANGELOG_PATH,
) -> int:
    ordered = validate_fragments(directory)
    if not ordered:
        print("[collect_changelog] no fragments to consume")
        return 0
    lines = [line for _, line in ordered]
    original = changelog_path.read_text(encoding="utf-8")
    updated = insert_unreleased_entries(original, lines)
    if updated != original:
        changelog_path.write_text(updated, encoding="utf-8")
        print(
            f"[collect_changelog] wrote {len(lines)} entries into "
            f"{_display_path(changelog_path)}"
        )
    else:
        print("[collect_changelog] CHANGELOG already contained all fragment entries")
    removed = 0
    for path in list_fragment_files(directory):
        path.unlink()
        removed += 1
        print(f"[collect_changelog] removed {_display_path(path)}")
    print(f"[collect_changelog] consumed {removed} fragment file(s)")
    return 0


def git_diff_names(base: str) -> list[str] | None:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            cwd=REPO_ROOT, check=False, capture_output=True, text=True,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def is_product_path(path: str) -> bool:
    if any(path == p or path.startswith(p) for p in IGNORE_PREFIXES):
        return False
    return any(path == p or path.startswith(p) for p in PRODUCT_PREFIXES)


def require_entry_for_diff(changed: list[str]) -> int:
    product = [path for path in changed if is_product_path(path)]
    if not product:
        print("[collect_changelog] no product-code paths in diff; entry not required")
        return 0
    has_fragment = any(
        path.startswith("docs/changelog.d/") and path.endswith(".md")
        and not path.endswith("README.md")
        for path in changed
    )
    has_legacy = "docs/CHANGELOG.md" in changed
    if has_fragment or has_legacy:
        mode = "fragment" if has_fragment else "legacy docs/CHANGELOG.md"
        print(f"[collect_changelog] product-code change covered by {mode}")
        return 0
    print(
        "[collect_changelog] ERROR: product-code changes require a changelog entry.\n"
        "  Add docs/changelog.d/<slug>.md with one or more lines:\n"
        "    - [Type] English description (Refs #N).\n"
        "  Allowed Type: Added/Changed/Fixed/Docs/Tests/Chore.\n"
        "  In-flight PRs may still edit docs/CHANGELOG.md directly "
        "(temporary compatibility).\n"
        f"  Product paths: {', '.join(product[:12])}"
        f"{'...' if len(product) > 12 else ''}",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--consume", action="store_true")
    mode.add_argument("--require-entry", action="store_true")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--fragments-dir", type=Path, default=None)
    parser.add_argument("--changelog", type=Path, default=None)
    args = parser.parse_args(argv)
    directory = args.fragments_dir or FRAGMENTS_DIR
    changelog_path = args.changelog or CHANGELOG_PATH
    try:
        if args.check:
            ordered = validate_fragments(directory)
            n_files = len(list_fragment_files(directory))
            print(f"[collect_changelog] ok: {len(ordered)} entr(y/ies) in {n_files} file(s)")
            return 0
        if args.consume:
            return consume_fragments(directory=directory, changelog_path=changelog_path)
        if args.require_entry:
            validate_fragments(directory)
            changed = git_diff_names(args.base)
            if changed is None:
                print(
                    "[collect_changelog] WARNING: could not resolve git diff; "
                    "skipping product-code entry requirement",
                    file=sys.stderr,
                )
                return 0
            return require_entry_for_diff(changed)
    except FragmentError as exc:
        print(f"[collect_changelog] ERROR: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[collect_changelog] ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
