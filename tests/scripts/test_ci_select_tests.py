# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for selective CI test mapping."""

from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

from scripts import ci_select_tests
from scripts.ci_select_tests import select_targets


def _backend_web_contract_filter_patterns() -> list[str]:
    workflow = yaml.safe_load(
        (ci_select_tests.REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
    )
    filter_step = next(
        step
        for step in workflow["jobs"]["changes"]["steps"]
        if step.get("id") == "filter"
    )
    filters = yaml.safe_load(filter_step["with"]["filters"])
    return list(filters["backend_web_contract"])


def _expand_ci_path_filter(pattern: str) -> list[str]:
    """Turn a dorny/paths-filter pattern into concrete repo paths to probe."""

    if pattern.endswith("/**"):
        root = pattern[: -len("/**")]
        matches = sorted(
            str(path.relative_to(ci_select_tests.REPO_ROOT)).replace("\\", "/")
            for path in (ci_select_tests.REPO_ROOT / root).rglob("*")
            if path.is_file()
        )
        assert matches, f"ci.yml backend_web_contract glob {pattern!r} matched nothing"
        return matches
    return [pattern]


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
    assert select_targets(["tests/analysis_quality/assertions.py"]) == "FULL"


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


def test_import_ratchet_scripts_map_to_scripts_tests() -> None:
    """Layer/cycle ratchet edits must collect tests/scripts, including inventory pins.

    ``scripts/`` first-matches to the ``tests/scripts`` directory plus the CI
    workflow suite. Collectable ``tests/scripts/test_*.py`` files map to
    themselves. A PR-shaped union of guard + test edits must still include
    both inventory modules so the shrink-only pins cannot drop out of
    selective CI.
    """

    scripts_expected = ["tests/scripts", "tests/test_ci_workflow.py"]
    for changed in (
        "scripts/check_layer_direction.py",
        "scripts/check_import_layers.py",
        "scripts/layer_direction_baseline.json",
        "scripts/import_layer_baseline.json",
    ):
        assert select_targets([changed]) == scripts_expected, changed

    assert select_targets(
        ["tests/scripts/test_check_layer_direction.py"]
    ) == ["tests/scripts/test_check_layer_direction.py"]
    assert select_targets(
        ["tests/scripts/test_check_import_layers.py"]
    ) == ["tests/scripts/test_check_import_layers.py"]

    combined = select_targets(
        [
            "scripts/check_layer_direction.py",
            "scripts/check_import_layers.py",
            "tests/scripts/test_check_layer_direction.py",
            "tests/scripts/test_check_import_layers.py",
        ]
    )
    assert combined != "FULL"
    assert isinstance(combined, list)
    assert "tests/scripts" in combined
    assert "tests/scripts/test_check_layer_direction.py" in combined
    assert "tests/scripts/test_check_import_layers.py" in combined
    assert "tests/test_ci_workflow.py" in combined


def test_web_only_is_none() -> None:
    assert select_targets(["apps/dsa-web/src/main.tsx"]) == []
    assert select_targets(["apps/dsa-web/src/App.tsx"]) == []


def test_backend_web_contract_prefixes_match_ci_yml_filter() -> None:
    """Mapper prefixes must stay in lockstep with ci.yml backend_web_contract."""

    patterns = _backend_web_contract_filter_patterns()
    expected = set()
    for pattern in patterns:
        if pattern.endswith("/**"):
            expected.add(pattern[: -len("**")])
        else:
            expected.add(pattern)
    assert set(ci_select_tests.BACKEND_WEB_CONTRACT_PREFIXES) == expected


def test_backend_web_contract_mappings_win_over_web_none() -> None:
    mapped_prefixes = [prefix for prefix, _targets in ci_select_tests.PATH_TO_TARGETS]
    web_none_index = mapped_prefixes.index("apps/dsa-web/")
    for prefix in ci_select_tests.BACKEND_WEB_CONTRACT_PREFIXES:
        assert prefix in mapped_prefixes, prefix
        assert mapped_prefixes.index(prefix) < web_none_index, prefix
        targets = next(
            item_targets
            for item_prefix, item_targets in ci_select_tests.PATH_TO_TARGETS
            if item_prefix == prefix
        )
        assert targets, prefix


def test_backend_web_contract_paths_select_backend_tests() -> None:
    """ci.yml backend_web_contract must never yield NONE (empty selection)."""

    public_expected = [
        "tests/data/test_stock_index_loader.py",
        "tests/test_generate_index_from_csv.py",
    ]
    settings_help_expected = [
        "tests/scripts/test_merge_resolvers.py",
        "tests/test_config_registry.py",
    ]
    cases = {
        "apps/dsa-web/public/stocks.index.json": public_expected,
        "apps/dsa-web/public/manifest.webmanifest": public_expected,
        "apps/dsa-web/src/components/settings/llmProviderTemplates.ts": [
            "tests/test_daily_analysis_workflow_llm_env.py",
            "tests/test_provider_catalog.py",
        ],
        "apps/dsa-web/src/locales/settingsHelp.ts": settings_help_expected,
        "apps/dsa-web/src/locales/settingsHelp.en.ts": settings_help_expected,
        "apps/dsa-web/src/locales/settingsHelp.zh.ts": settings_help_expected,
        "apps/dsa-web/src/utils/systemConfigI18n.ts": [
            "tests/test_config_registry.py",
        ],
    }
    for changed, expected in cases.items():
        result = select_targets([changed])
        assert result == expected, changed
        assert result != []
        assert result != "FULL"

    for pattern in _backend_web_contract_filter_patterns():
        for path in _expand_ci_path_filter(pattern):
            result = select_targets([path])
            assert result != [], path
            assert result != "FULL", path
            assert isinstance(result, list), path
            assert result, path


def test_backend_web_contract_mixed_with_generic_web_still_selects_tests() -> None:
    result = select_targets(
        [
            "apps/dsa-web/src/App.tsx",
            "apps/dsa-web/src/utils/systemConfigI18n.ts",
        ]
    )
    assert result == ["tests/test_config_registry.py"]


def test_backend_web_contract_empty_tuple_fails_closed_to_full_suite(
    monkeypatch,
) -> None:
    """Contract prefixes are outside the NONE allowlist; empty maps fail closed."""

    monkeypatch.setattr(
        ci_select_tests,
        "PATH_TO_TARGETS",
        (("apps/dsa-web/src/utils/systemConfigI18n.ts", ()),)
        + ci_select_tests.PATH_TO_TARGETS,
    )
    assert select_targets(["apps/dsa-web/src/utils/systemConfigI18n.ts"]) == "FULL"
    assert select_targets(["apps/dsa-web/src/App.tsx"]) == []


def test_tests_fixtures_fail_closed_to_full_suite() -> None:
    """Fixture-only PRs must not select NONE (collection smoke, then green)."""

    assert select_targets(["tests/fixtures/schema_migrations/v3_4_0.sql"]) == "FULL"
    assert select_targets(["tests/fixtures/provider_contracts/manifest.json"]) == "FULL"
    assert select_targets(["tests/fixtures/ocr/sample_chart_annotation.png"]) == "FULL"
    assert select_targets([
        "docs/CHANGELOG.md",
        "tests/fixtures/schema_migrations/v3_4_0.sql",
    ]) == "FULL"


def test_collectable_test_module_maps_to_itself() -> None:
    assert select_targets(["tests/test_storage.py"]) == ["tests/test_storage.py"]
    assert select_targets(["tests/api/test_api_health.py"]) == ["tests/api/test_api_health.py"]


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


def test_empty_tuple_mapping_outside_allowlist_fails_closed_to_full_suite(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ci_select_tests,
        "PATH_TO_TARGETS",
        (("src/market/", ()),) + ci_select_tests.PATH_TO_TARGETS,
    )
    assert select_targets(["src/market/analyzer.py"]) == "FULL"


def test_declared_mapping_targets_exist() -> None:
    root = Path(ci_select_tests.REPO_ROOT)
    empty_prefixes = []
    for prefix, targets in ci_select_tests.PATH_TO_TARGETS:
        if not targets:
            empty_prefixes.append(prefix)
            continue
        for target in targets:
            assert target, f"{prefix} includes an empty-string target"
            if any(char in target for char in "*?["):
                matches = list(root.glob(target))
                assert matches, f"{prefix} glob {target!r} matched nothing"
                continue
            assert (root / target).exists(), f"{prefix} maps to missing {target}"
    assert set(empty_prefixes) == set(ci_select_tests.NONE_PREFIXES)


def test_cli_paths_file_prints_full_for_unmapped(tmp_path, capsys) -> None:
    paths_file = tmp_path / "paths.txt"
    paths_file.write_text("unknown_tree/x.py\n", encoding="utf-8")
    assert ci_select_tests.main(["--paths-file", str(paths_file)]) == 0
    assert capsys.readouterr().out == "FULL\n"


def test_cli_paths_file_prints_full_for_tests_fixtures(tmp_path, capsys) -> None:
    paths_file = tmp_path / "paths.txt"
    paths_file.write_text(
        "tests/fixtures/schema_migrations/v3_4_0.sql\n",
        encoding="utf-8",
    )
    assert ci_select_tests.main(["--paths-file", str(paths_file)]) == 0
    assert capsys.readouterr().out == "FULL\n"


def test_cli_paths_file_prints_none_only_for_allowlist(tmp_path, capsys) -> None:
    paths_file = tmp_path / "paths.txt"
    paths_file.write_text("docs/CHANGELOG.md\napps/dsa-web/src/main.tsx\n", encoding="utf-8")
    assert ci_select_tests.main(["--paths-file", str(paths_file)]) == 0
    assert capsys.readouterr().out == "NONE\n"


def test_cli_paths_file_prints_targets_for_backend_web_contract(tmp_path, capsys) -> None:
    paths_file = tmp_path / "paths.txt"
    paths_file.write_text(
        "apps/dsa-web/src/utils/systemConfigI18n.ts\n",
        encoding="utf-8",
    )
    assert ci_select_tests.main(["--paths-file", str(paths_file)]) == 0
    assert capsys.readouterr().out == "tests/test_config_registry.py\n"


def test_backend_web_contract_unmapped_fails_closed_to_full_not_none(
    monkeypatch,
) -> None:
    """Dropping the specific mapping must not revive NONE via apps/dsa-web/."""

    monkeypatch.setattr(
        ci_select_tests,
        "PATH_TO_TARGETS",
        tuple(
            item
            for item in ci_select_tests.PATH_TO_TARGETS
            if item[0] not in ci_select_tests.BACKEND_WEB_CONTRACT_PREFIXES
        ),
    )
    assert select_targets(["apps/dsa-web/src/utils/systemConfigI18n.ts"]) == "FULL"
    assert select_targets(["apps/dsa-web/public/stocks.index.json"]) == "FULL"
    assert select_targets(["apps/dsa-web/src/App.tsx"]) == []


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
