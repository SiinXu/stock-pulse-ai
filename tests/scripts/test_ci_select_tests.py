# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for selective CI test mapping."""

from __future__ import annotations

from scripts.ci_select_tests import select_targets


def test_api_paths_map_to_api_tests() -> None:
    result = select_targets(["api/v1/endpoints/analysis.py"])
    assert result != "FULL"
    assert isinstance(result, list)
    assert any(path.startswith("tests/api") or path == "tests/api" for path in result)


def test_config_forces_full_suite() -> None:
    assert select_targets(["src/config.py"]) == "FULL"
    assert select_targets(["tests/conftest.py"]) == "FULL"
    assert select_targets([".github/workflows/ci.yml"]) == "FULL"


def test_docs_only_is_none() -> None:
    assert select_targets(["docs/CHANGELOG.md", "docs/FAQ.md"]) == []


def test_empty_paths_full() -> None:
    assert select_targets([]) == "FULL"
