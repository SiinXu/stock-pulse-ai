#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Guard: stable Web catalog codes and dual taxonomy maps stay aligned.

Fails when:
1. ``STABLE_ERROR_TEXT`` keys are missing from ``src/api/v1/error_taxonomy.py``
2. Backend ``ERROR_CODE_TAXONOMY`` entries use invalid category/severity/action
3. Backend and Web ``ERROR_CODE_TAXONOMY`` code sets or classification triples differ
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "apps" / "dsa-web" / "src" / "api" / "error" / "catalog.ts"
WEB_TAXONOMY_PATH = REPO_ROOT / "apps" / "dsa-web" / "src" / "api" / "error" / "taxonomy.ts"

_STABLE_KEY_RE = re.compile(
    r"^\s{2}([a-z][a-z0-9_]*)\s*:\s*createUiLanguageRecord",
    re.MULTILINE,
)
_WEB_CODE_ENTRY_RE = re.compile(
    r"^\s{2}([a-z][a-z0-9_]+):\s*entry\(\s*'([a-z_]+)',\s*'([a-z]+)',\s*'([a-z]+)'",
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


def _load_web_error_code_taxonomy() -> dict[str, tuple[str, str, str]]:
    """Parse ERROR_CODE_TAXONOMY entries from the Web mirror (not CATEGORY_TAXONOMY)."""
    text = WEB_TAXONOMY_PATH.read_text(encoding="utf-8")
    start = text.find("export const ERROR_CODE_TAXONOMY")
    if start < 0:
        raise SystemExit(f"ERROR_CODE_TAXONOMY not found in {WEB_TAXONOMY_PATH}")
    # End at UNKNOWN / CATEGORY maps that follow the code registry.
    end_markers = (
        "export const UNKNOWN_ERROR_CLASSIFICATION",
        "const CATEGORY_TAXONOMY",
        "const TAXONOMY_CATEGORIES",
    )
    end = len(text)
    for marker in end_markers:
        idx = text.find(marker, start + 1)
        if idx > 0:
            end = min(end, idx)
    block = text[start:end]
    return {
        code: (category, severity, action)
        for code, category, severity, action in _WEB_CODE_ENTRY_RE.findall(block)
    }


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    from src.api.v1.error_taxonomy import (  # noqa: WPS433
        ERROR_ACTIONS,
        ERROR_CATEGORIES,
        ERROR_CODE_TAXONOMY,
        ERROR_SEVERITIES,
        registered_error_codes,
    )

    stable_codes = _load_stable_catalog_codes()
    taxonomy_codes = registered_error_codes()
    web_map = _load_web_error_code_taxonomy()
    backend_map = {
        code: (entry.category, entry.severity, entry.default_action)
        for code, entry in ERROR_CODE_TAXONOMY.items()
    }

    missing_in_taxonomy = sorted(stable_codes - taxonomy_codes)
    invalid_entries: list[str] = []
    for code, entry in sorted(ERROR_CODE_TAXONOMY.items()):
        if entry.category not in ERROR_CATEGORIES:
            invalid_entries.append(f"{code}: invalid category {entry.category!r}")
        if entry.severity not in ERROR_SEVERITIES:
            invalid_entries.append(f"{code}: invalid severity {entry.severity!r}")
        if entry.default_action not in ERROR_ACTIONS:
            invalid_entries.append(
                f"{code}: invalid default_action {entry.default_action!r}"
            )

    only_backend = sorted(set(backend_map) - set(web_map))
    only_web = sorted(set(web_map) - set(backend_map))
    triple_mismatches: list[str] = []
    for code in sorted(set(backend_map) & set(web_map)):
        if backend_map[code] != web_map[code]:
            triple_mismatches.append(
                f"{code}: backend={backend_map[code]!r} web={web_map[code]!r}"
            )

    errors: list[str] = []
    if missing_in_taxonomy:
        errors.append(
            "Web STABLE_ERROR_TEXT codes missing from ERROR_CODE_TAXONOMY:\n  - "
            + "\n  - ".join(missing_in_taxonomy)
            + "\nAdd each code to src/api/v1/error_taxonomy.py (and the Web taxonomy mirror)."
        )
    if invalid_entries:
        errors.append(
            "Invalid taxonomy entries:\n  - " + "\n  - ".join(invalid_entries)
        )
    if only_backend:
        errors.append(
            "Backend ERROR_CODE_TAXONOMY codes missing from Web taxonomy.ts:\n  - "
            + "\n  - ".join(only_backend)
        )
    if only_web:
        errors.append(
            "Web ERROR_CODE_TAXONOMY codes missing from backend error_taxonomy.py:\n  - "
            + "\n  - ".join(only_web)
        )
    if triple_mismatches:
        errors.append(
            "Backend/Web classification triples differ (category, severity, action):\n  - "
            + "\n  - ".join(triple_mismatches)
        )

    if errors:
        print("error taxonomy guard FAILED:\n\n" + "\n\n".join(errors), file=sys.stderr)
        return 1

    print(
        f"error taxonomy guard OK: {len(stable_codes)} Web stable codes classified; "
        f"{len(taxonomy_codes)} dual-registry entries aligned "
        f"(category/severity/action parity)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
