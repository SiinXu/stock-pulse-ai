#!/usr/bin/env python3
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Advisory inventory of dsa-web API modules vs OpenAPI migration pattern.

Default mode prints pending modules and exits 0.
Pass --fail-on-pending only when maintainers choose to make this a gate.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "dsa-web" / "src" / "api"

SKIP_FILES = {
    "error.ts",
    "index.ts",
    "utils.ts",
    "parseCamelCasePayload.ts",
}

DOCUMENTED_SKIPS = {
    "reasoningTraceExport.ts": "binary blob download path",
}


def classify(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    name = path.name
    if name in SKIP_FILES:
        return "infra"
    if name in DOCUMENTED_SKIPS:
        return "skip"
    has_generated = "api.generated" in text or "types/api.generated" in text
    has_validation = bool(
        re.search(
            r"parseCamelCasePayload|assertCamelCasePayload|api_response_validation_failed|safeParse",
            text,
        )
    )
    has_unchecked_cast = bool(re.search(r"toCamelCase\s*<", text)) and not has_validation
    if has_generated and has_validation:
        return "migrated"
    if has_validation and not has_generated:
        return "validation_only"
    if has_generated and not has_validation:
        return "types_only"
    if has_unchecked_cast:
        return "unchecked"
    return "review"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-on-pending",
        action="store_true",
        help="Exit 1 when any non-skip pending module remains (owner-gated).",
    )
    args = parser.parse_args()

    modules = sorted(p for p in API_DIR.glob("*.ts") if p.is_file())
    buckets: dict[str, list[str]] = {
        "migrated": [],
        "validation_only": [],
        "types_only": [],
        "unchecked": [],
        "review": [],
        "skip": [],
        "infra": [],
    }
    for path in modules:
        buckets[classify(path)].append(path.name)

    print("dsa-web API OpenAPI migration inventory")
    print(f"root: {API_DIR.relative_to(ROOT)}")
    for key in ("migrated", "validation_only", "types_only", "unchecked", "review", "skip", "infra"):
        items = buckets[key]
        print(f"\n[{key}] ({len(items)})")
        for name in items:
            note = DOCUMENTED_SKIPS.get(name, "")
            print(f"  - {name}" + (f"  # {note}" if note else ""))

    pending = (
        buckets["validation_only"]
        + buckets["types_only"]
        + buckets["unchecked"]
        + buckets["review"]
    )
    print(f"\npending_count={len(pending)} migrated_count={len(buckets['migrated'])}")
    if args.fail_on_pending and pending:
        print("FAIL: pending modules remain (--fail-on-pending)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
