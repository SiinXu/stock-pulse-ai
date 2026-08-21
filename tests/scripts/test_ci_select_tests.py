# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for selective CI test mapping."""

from __future__ import annotations

from pathlib import Path
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
    expected = [
        "tests/contract/test_provider_fallback.py",
        "tests/data_provider",
    ]
    for changed in ("src/data_provider/base.py", "src/data_provider/akshare_parts/symbols.py"):
        result = select_targets([changed])
        assert result == expected, changed


def test_diagnostics_schema_maps_to_run_diagnostics_and_services_tests() -> None:
    """Schema/facade edits must run the characterization suite, not only tests/services."""

    expected = [
        "tests/services",
        "tests/test_run_diagnostics_p1.py",
        "tests/test_run_diagnostics_p2.py",
    ]
    for changed in (
        "src/services/diagnostics/schema.py",
        "src/services/diagnostics/collect.py",
        "src/services/run_diagnostics.py",
    ):
        result = select_targets([changed])
        assert result == expected, changed


def test_src_market_maps_to_market_tests() -> None:
    result = select_targets(["src/market/analyzer.py"])
    assert result == ["tests/market", "tests/services"]
    assert "tests/test_market_analyzer.py" not in result


def test_src_schemas_maps_to_schema_tests() -> None:
    result = select_targets(["src/schemas/report_schema.py"])
    assert result == [
        "tests/api",
        "tests/schemas",
        "tests/test_api_schema_pydantic.py",
    ]


def test_src_agent_maps_to_agent_package_and_root_agent_tests() -> None:
    result = select_targets(["src/agent/orchestrator.py"])
    assert isinstance(result, list)
    assert "tests/agent" in result
    assert "tests/skill_opinion_outcomes" in result
    root_agent_tests = sorted(
        str(path.relative_to(ci_select_tests.REPO_ROOT)).replace("\\", "/")
        for path in ci_select_tests.REPO_ROOT.glob("tests/test_agent_*.py")
    )
    assert root_agent_tests, "expected tests/test_agent_*.py files for this pin"
    for path in root_agent_tests:
        assert path in result


def test_src_migrations_maps_to_existing_migration_tests() -> None:
    result = select_targets(["src/migrations/runner.py"])
    assert result == [
        "tests/test_approval_migration.py",
        "tests/test_investment_framework_migration.py",
        "tests/test_migration_cli_readonly.py",
        "tests/test_schema_migrations.py",
        "tests/test_storage.py",
    ]
    assert "tests/migrations" not in result


def test_docs_only_is_none() -> None:
    assert select_targets(["docs/CHANGELOG.md", "docs/FAQ.md"]) == []


def test_empty_paths_full() -> None:
    assert select_targets([]) == "FULL"


def test_unmapped_path_fails_closed_to_full_suite() -> None:
    assert select_targets(["no_such_top_level/foo.py"]) == "FULL"
    assert select_targets(["main.py"]) == "FULL"
    assert select_targets(["strategies/example.yaml"]) == "FULL"


def test_stale_mapping_all_missing_fails_closed_to_full_suite(monkeypatch) -> None:
    monkeypatch.setattr(
        ci_select_tests,
        "PATH_TO_TARGETS",
        (("stale_src/", ("tests/this_file_does_not_exist.py",)),)
        + ci_select_tests.PATH_TO_TARGETS,
    )
    assert select_targets(["stale_src/mod.py"]) == "FULL"


def test_empty_glob_mapping_fails_closed_to_full_suite(monkeypatch) -> None:
    monkeypatch.setattr(
        ci_select_tests,
        "PATH_TO_TARGETS",
        (("stale_src/", ("tests/no_such_glob_prefix_*.py",)),)
        + ci_select_tests.PATH_TO_TARGETS,
    )
    assert select_targets(["stale_src/mod.py"]) == "FULL"


def test_declared_mapping_targets_exist() -> None:
    root = Path(ci_select_tests.REPO_ROOT)
    for prefix, targets in ci_select_tests.PATH_TO_TARGETS:
        for target in targets:
            if not target:
                continue
            if any(char in target for char in "*?["):
                matches = list(root.glob(target))
                assert matches, f"{prefix} glob {target!r} matched nothing"
                continue
            assert (root / target).exists(), f"{prefix} maps to missing {target}"


def test_cli_paths_file_prints_full_for_unmapped(tmp_path, capsys) -> None:
    paths_file = tmp_path / "paths.txt"
    paths_file.write_text("unknown_tree/x.py\n", encoding="utf-8")
    assert ci_select_tests.main(["--paths-file", str(paths_file)]) == 0
    assert capsys.readouterr().out == "FULL\n"


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
