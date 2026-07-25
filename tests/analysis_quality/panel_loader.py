# -*- coding: utf-8 -*-
"""Load the offline analysis quality panel fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "analysis_quality"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"


def load_manifest() -> Dict[str, Any]:
    """Return the panel manifest as a plain dict."""
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"manifest must be an object: {MANIFEST_PATH}")
    return data


def load_case(relative_file: str) -> Dict[str, Any]:
    """Load one panel case JSON relative to the fixture root."""
    path = FIXTURE_ROOT / relative_file
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"case must be an object: {path}")
    return data


def iter_panel_cases() -> Iterable[Dict[str, Any]]:
    """Yield each case dict from the manifest in declared order."""
    manifest = load_manifest()
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("analysis quality manifest must declare a non-empty cases list")
    for entry in cases:
        if not isinstance(entry, Mapping):
            raise TypeError(f"manifest case entry must be an object: {entry!r}")
        relative = entry.get("file")
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError(f"manifest case entry missing file: {entry!r}")
        case = load_case(relative)
        case_id = case.get("id") or entry.get("id")
        if case_id is None:
            raise ValueError(f"case missing id: {relative}")
        case.setdefault("id", case_id)
        yield case


def list_panel_case_ids() -> List[str]:
    """Return declared case ids in manifest order."""
    return [str(case["id"]) for case in iter_panel_cases()]
