# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression tests for the API error taxonomy and envelope integration."""

from __future__ import annotations

import re
from pathlib import Path

from api.v1.error_taxonomy import (
    ERROR_ACTIONS,
    ERROR_CATEGORIES,
    ERROR_CODE_TAXONOMY,
    ERROR_SEVERITIES,
    classify_error_code,
    is_classified_error_code,
    registered_error_codes,
)
from api.v1.errors import api_error, error_body, normalize_error_body

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO_ROOT / "apps" / "dsa-web" / "src" / "api" / "error" / "catalog.ts"
_STABLE_KEY_RE = re.compile(
    r"^\s{2}([a-z][a-z0-9_]*)\s*:\s*createUiLanguageRecord",
    re.MULTILINE,
)


def _stable_catalog_codes() -> set[str]:
    text = CATALOG_PATH.read_text(encoding="utf-8")
    start = text.find("export const STABLE_ERROR_TEXT")
    end = text.find("export const EN_ERROR_TEXT", start)
    if end < 0:
        end = text.find("const EN_ERROR_TEXT", start)
    block = text[start:end if end > 0 else len(text)]
    return set(_STABLE_KEY_RE.findall(block))


def test_taxonomy_entries_use_allowed_vocabulary() -> None:
    for code, entry in ERROR_CODE_TAXONOMY.items():
        assert entry.category in ERROR_CATEGORIES, code
        assert entry.severity in ERROR_SEVERITIES, code
        assert entry.default_action in ERROR_ACTIONS, code


def test_web_stable_codes_are_classified() -> None:
    missing = sorted(_stable_catalog_codes() - registered_error_codes())
    assert missing == [], f"Unclassified STABLE_ERROR_TEXT codes: {missing}"


def test_classify_known_and_unknown_codes() -> None:
    known = classify_error_code("llm_not_configured")
    assert known.category == "capability"
    assert known.severity == "error"
    assert known.default_action == "settings"
    assert known.docs_path is not None
    unknown = classify_error_code("totally_novel_code_xyz")
    assert unknown.category == "internal"
    assert not is_classified_error_code("totally_novel_code_xyz")
    assert is_classified_error_code("rate_limited")


def test_error_body_attaches_taxonomy_without_replacing_error_code() -> None:
    body = error_body("llm_not_configured", "No model configured", params={"hint": "configure"})
    assert body["error"] == "llm_not_configured"
    assert body["category"] == "capability"
    assert body["severity"] == "error"
    assert body["params"] == {"hint": "configure"}
    assert body["message"] == "No model configured"
    assert body["detail"] == body["details"]


def test_error_body_preserves_explicit_valid_taxonomy_override() -> None:
    body = error_body("analysis_failed", "failed", category="provider_network", severity="warning")
    assert body["error"] == "analysis_failed"
    assert body["category"] == "provider_network"
    assert body["severity"] == "warning"


def test_error_body_ignores_invalid_taxonomy_override() -> None:
    body = error_body("not_found", "missing", category="not-a-real-category", severity="loud")
    assert body["category"] == "not_found"
    assert body["severity"] == "warning"


def test_normalize_error_body_does_not_dump_taxonomy_into_params() -> None:
    body = normalize_error_body(
        {
            "error": "duplicate_task",
            "message": "busy",
            "category": "busy",
            "severity": "warning",
            "existing_task_id": "task-1",
        },
        default_error="unknown_error",
        default_message="failed",
    )
    assert body["error"] == "duplicate_task"
    assert body["category"] == "busy"
    assert body["severity"] == "warning"
    assert body["params"]["existing_task_id"] == "task-1"
    assert "category" not in body["params"]
    assert "severity" not in body["params"]


def test_api_error_detail_includes_taxonomy() -> None:
    exc = api_error(422, "validation_error", "bad input")
    assert isinstance(exc.detail, dict)
    assert exc.detail["error"] == "validation_error"
    assert exc.detail["category"] == "validation"
    assert exc.detail["severity"] == "error"
