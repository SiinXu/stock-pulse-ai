#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Report progressive SPDX-License-Identifier coverage for maintainers.

This is a coverage *signal*, not a full-repo legal audit and not a CI gate.
See docs/license-ownership-inventory.md.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*([^\s*]+)")
DEFAULT_GLOBS = ("*.py", "*.ts", "*.tsx", "*.js", "*.mjs", "*.cjs")


def _git_ls_files(globs: tuple[str, ...]) -> list[str]:
    """List tracked files matching the given pathspecs."""
    completed = subprocess.run(
        ["git", "ls-files", "--", *globs],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git ls-files failed")
    return [line for line in completed.stdout.splitlines() if line]


def _scan(paths: list[str]) -> tuple[Counter[str], list[str], int]:
    """Return (license counts, tagged paths, untagged count)."""
    counts: Counter[str] = Counter()
    tagged: list[str] = []
    untagged = 0
    for relative in paths:
        path = ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            untagged += 1
            continue
        # Prefer the first SPDX header (typical file header placement).
        match = SPDX_RE.search(text)
        if match is None:
            untagged += 1
            continue
        license_id = match.group(1).strip()
        counts[license_id] += 1
        tagged.append(relative)
    return counts, tagged, untagged


def main(argv: list[str] | None = None) -> int:
    """Print a progressive SPDX coverage summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--show-tagged",
        action="store_true",
        help="print every tagged path (default: summary only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="when --show-tagged, print at most N paths (0 = all)",
    )
    args = parser.parse_args(argv)

    paths = _git_ls_files(DEFAULT_GLOBS)
    counts, tagged, untagged = _scan(paths)
    total = len(paths)
    tagged_n = len(tagged)
    ratio = (tagged_n / total * 100.0) if total else 0.0

    print("SPDX coverage report (progressive; not a full legal audit)")
    print(f"root: {ROOT}")
    print(f"tracked source files ({', '.join(DEFAULT_GLOBS)}): {total}")
    print(f"with SPDX-License-Identifier: {tagged_n} ({ratio:.1f}%)")
    print(f"without SPDX header: {untagged}")
    if counts:
        print("license ids (first header per file):")
        for license_id, count in counts.most_common():
            print(f"  {license_id}: {count}")
    else:
        print("license ids: (none found)")
    print()
    print("Process doc: docs/license-ownership-inventory.md")
    print("Do not treat this ratio as completion of a full-repo audit.")

    if args.show_tagged:
        print()
        print("tagged paths:")
        shown = tagged if args.limit <= 0 else tagged[: args.limit]
        for relative in shown:
            print(f"  {relative}")
        if args.limit > 0 and len(tagged) > args.limit:
            print(f"  ... ({len(tagged) - args.limit} more)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
