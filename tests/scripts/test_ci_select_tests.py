# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for selective CI test mapping."""

from __future__ import annotations

import subprocess

from scripts import ci_select_tests
from scripts.ci_select_tests import select_targets


def test_src_bot_maps_to_bot_selective_targets() -> None:
    """src/bot/ must win over the catch-all src/ prefix (first-match)."""

    moved = select_targets(["src/bot/dispatcher.py"])
    expected = [
        "tests/bot",
        "tests/test_notification.py",
        "tests/test_notification_sender.py",
    ]
    assert moved == expected
    assert "tests/" not in moved


def test_src_api_paths_map_to_api_tests() -> None:
    result = select_targets(["src/api/v1/endpoints/analysis.py"])
    assert result != "FULL"
    assert isinstance(result, list)
    assert any(path.startswith("tests/api") or path == "tests/api" for path in result)


def test_config_forces_full_suite() -> None:
    assert select_targets(["src/config.py"]) == "FULL"
    assert select_targets(["tests/conftest.py"]) == "FULL"
    assert select_targets([".github/workflows/ci.yml"]) == "FULL"


def test_non_collectable_test_support_forces_full_suite() -> None:
    assert select_targets(["tests/system_config_service_test_support.py"]) == "FULL"
    assert select_targets(["tests/services/conftest.py"]) == "FULL"


def test_data_provider_roots_map_to_provider_tests() -> None:
    for changed in ("src/data_provider/base.py", "src/data_provider/akshare_parts/symbols.py"):
        result = select_targets([changed])
        assert result == ["tests/data_provider"], changed


def test_docs_only_is_none() -> None:
    assert select_targets(["docs/CHANGELOG.md", "docs/FAQ.md"]) == []


def test_empty_paths_full() -> None:
    assert select_targets([]) == "FULL"


def test_missing_merge_base_fails_closed_to_full_suite(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="no merge base",
        ),
    )

    assert ci_select_tests._git_diff_names("origin/main") is None
    assert ci_select_tests.main(["--base", "origin/main"]) == 0
    assert capsys.readouterr().out == "FULL\n"
