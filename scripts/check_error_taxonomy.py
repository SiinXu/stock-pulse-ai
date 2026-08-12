#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Guard: stable Web error codes must be classified in the API taxonomy."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "apps" / "dsa-web" / "src" / "api" / "error" / "catalog.ts"

_STABLE_KEY_RE = re.compile(
    r"^\s{2}([a-z][a-z0-9_]*)\s*:\s*createUiLanguageRecord",
    re.MULTILINE,
)


def _load_stable_catalog_codes() -> set[str]:
    text = CATALOG_PATH.read_text(encoding="utf-8")
    stable_start = text.find("export const STABLE_ERROR_TEXT")
    if stable_start < 0:
        raise SystemExit(f"STABLE_ERROR_TEXT not found in {CATALOG_PATH}")
    stable_end = text.find("export const EN_ERROR_TEXT", stable_start)
    if stable_end < 0:
        stable_end = text.find("const EN_ERROR_TEXT", stable_start)
    if stable_end < 0:
        stable_end = len(text)
    block = text[stable_start:stable_end]
    return set(_STABLE_KEY_RE.findall(block))


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    from api.v1.error_taxonomy import (  # noqa: WPS433
        ERROR_ACTIONS,
        ERROR_CATEGORIES,
        ERROR_CODE_TAXONOMY,
        ERROR_SEVERITIES,
        registered_error_codes,
    )

    stable_codes = _load_stable_catalog_codes()
    taxonomy_codes = registered_error_codes()
    missing_in_taxonomy = sorted(stable_codes - taxonomy_codes)
    invalid_entries = []
    for code, entry in sorted(ERROR_CODE_TAXONOMY.items()):
        if entry.category not in ERROR_CATEGORIES:
            invalid_entries.append(f"{code}: invalid category {entry.category!r}")
        if entry.severity not in ERROR_SEVERITIES:
            invalid_entries.append(f"{code}: invalid severity {entry.severity!r}")
        if entry.default_action not in ERROR_ACTIONS:
            invalid_entries.append(f"{code}: invalid default_action {entry.default_action!r}")

    errors = []
    if missing_in_taxonomy:
        errors.append(
            "Web STABLE_ERROR_TEXT codes missing from ERROR_CODE_TAXONOMY:\n  - "
            + "\n  - ".join(missing_in_taxonomy)
            + "\nAdd each code to api/v1/error_taxonomy.py (and the Web taxonomy mirror)."
        )
    if invalid_entries:
        errors.append("Invalid taxonomy entries:\n  - " + "\n  - ".join(invalid_entries))
    if errors:
        print("error taxonomy guard FAILED:\n\n" + "\n\n".join(errors), file=sys.stderr)
        return 1
    print(
        f"error taxonomy guard OK: {len(stable_codes)} Web stable codes classified; "
        f"{len(taxonomy_codes)} taxonomy entries valid."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
