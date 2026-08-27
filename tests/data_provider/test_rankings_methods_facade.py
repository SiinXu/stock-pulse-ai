# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for rankings extraction."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import src.data_provider.base as base
import src.data_provider.manager_parts.rankings_methods as rankings
from src.data_provider.base import BaseFetcher, DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "rankings_methods.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def test_rankings_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = rankings.EXPECTED_RANKINGS_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_public_rankings_signatures_are_unchanged() -> None:
    sector = inspect.signature(DataFetcherManager.get_sector_rankings)
    assert list(sector.parameters) == ["self", "n"]
    assert sector.parameters["n"].default == 5

    concept = inspect.signature(DataFetcherManager.get_concept_rankings)
    assert list(concept.parameters) == ["self", "n"]
    assert concept.parameters["n"].default == 5

    hot = inspect.signature(DataFetcherManager.get_hot_stocks)
    assert list(hot.parameters) == ["self", "n"]
    assert hot.parameters["n"].default == 10

    pool = inspect.signature(DataFetcherManager.get_limit_up_pool)
    assert list(pool.parameters) == ["self", "date", "n"]
    assert pool.parameters["date"].default is None
    assert pool.parameters["n"].default == 20


def test_copy_ranking_rows_remains_staticmethod() -> None:
    assert isinstance(vars(DataFetcherManager)["_copy_ranking_rows"], staticmethod)
    assert isinstance(
        vars(rankings._RankingsMethods)["_copy_ranking_rows"],
        staticmethod,
    )


def test_clear_concept_rankings_cache_for_tests_remains_classmethod() -> None:
    assert isinstance(
        vars(DataFetcherManager)["clear_concept_rankings_cache_for_tests"],
        classmethod,
    )
    assert isinstance(
        vars(rankings._RankingsMethods)["clear_concept_rankings_cache_for_tests"],
        classmethod,
    )


def test_rankings_methods_have_no_validation_wrapper_token() -> None:
    for name in rankings.EXPECTED_RANKINGS_METHOD_NAMES:
        method = DataFetcherManager.__dict__[name]
        assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_owner_module_exists_for_rankings_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "rankings_methods" in source
    assert "bind_rankings_methods_facade" in source
    assert "def _get_sector_rankings_with_meta(" not in source
    assert "def _copy_ranking_rows(" not in source
    assert "def clear_concept_rankings_cache_for_tests(" not in source
    # Shared names still exist on BaseFetcher; manager bodies must not remain.
    assert source.count("def get_sector_rankings(") == 1
    assert source.count("def get_concept_rankings(") == 1
    assert source.count("def get_hot_stocks(") == 1
    assert source.count("def get_limit_up_pool(") == 1
    importlib.import_module("src.data_provider.manager_parts.rankings_methods")


def test_base_fetcher_rankings_contract_stays_on_base_fetcher() -> None:
    for name in (
        "get_sector_rankings",
        "get_concept_rankings",
        "get_hot_stocks",
        "get_limit_up_pool",
    ):
        provider = _descriptor_function(vars(BaseFetcher)[name])
        manager = _descriptor_function(vars(DataFetcherManager)[name])
        assert provider is not manager
        assert provider.__qualname__ == f"BaseFetcher.{name}"
        assert manager.__qualname__ == f"DataFetcherManager.{name}"


def test_rankings_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(rankings._RankingsMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == rankings.__name__
    assert tuple(source_names) == rankings.EXPECTED_RANKINGS_METHOD_NAMES


def test_rankings_placeholders_preserve_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    assert names.index("get_board_context") < names.index("_get_sector_rankings_with_meta")
    assert names.index("_get_sector_rankings_with_meta") < names.index("get_sector_rankings")
    assert names.index("get_sector_rankings") < names.index("_copy_ranking_rows")
    assert names.index("_copy_ranking_rows") < names.index(
        "clear_concept_rankings_cache_for_tests"
    )
    assert names.index("clear_concept_rankings_cache_for_tests") < names.index(
        "get_concept_rankings"
    )
    assert names.index("get_concept_rankings") < names.index("get_hot_stocks")
    assert names.index("get_hot_stocks") < names.index("get_limit_up_pool")


def test_concept_rankings_cache_class_attributes_remain_on_facade() -> None:
    assert DataFetcherManager._CONCEPT_RANKINGS_CACHE_TTL_SECONDS == 300.0
    assert DataFetcherManager._CONCEPT_RANKINGS_EMPTY_CACHE_TTL_SECONDS == 30.0
    source_names = {
        name
        for name, descriptor in vars(rankings._RankingsMethods).items()
        if not name.startswith("__") and _descriptor_function(descriptor) is not None
    }
    assert "_CONCEPT_RANKINGS_CACHE_TTL_SECONDS" not in source_names
    assert "_CONCEPT_RANKINGS_EMPTY_CACHE_TTL_SECONDS" not in source_names
    assert "_concept_rankings_cache" not in source_names
    assert "_concept_rankings_cache_lock" not in source_names


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.rankings_methods as rankings",
                    "",
                    "names = rankings.EXPECTED_RANKINGS_METHOD_NAMES",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    original = getattr(",
                    "        descriptor,",
                    "        '_stockpulse_data_validation_original',",
                    "        None,",
                    "    )",
                    "    return original if original is not None else descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    facade = {}",
                    "    for name in names:",
                    "        source[name] = descriptor_function(",
                    "            vars(rankings._RankingsMethods)[name]",
                    "        )",
                    "        facade[name] = descriptor_function(",
                    "            vars(base.DataFetcherManager)[name]",
                    "        )",
                    "        assert facade[name] is not source[name]",
                    "        assert facade[name].__code__ is source[name].__code__",
                    "        assert facade[name].__globals__ is vars(base)",
                    "        assert facade[name].__module__ == 'src.data_provider.base'",
                    "        assert facade[name].__qualname__ == f'DataFetcherManager.{name}'",
                    "    assert isinstance(",
                    "        vars(base.DataFetcherManager)['_copy_ranking_rows'],",
                    "        staticmethod,",
                    "    )",
                    "    assert isinstance(",
                    "        vars(base.DataFetcherManager)[",
                    "            'clear_concept_rankings_cache_for_tests'",
                    "        ],",
                    "        classmethod,",
                    "    )",
                    "    return source, facade",
                    "",
                    body,
                )
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_owner_reload_rebinds_loaded_facade() -> None:
    _run_reload_contract(
        """
old_class = base.DataFetcherManager
before_source, before_facade = bindings()
rankings = importlib.reload(rankings)
assert base.DataFetcherManager is old_class
after_source, after_facade = bindings()
for name in names:
    assert after_source[name] is not before_source[name]
    assert after_facade[name] is not before_facade[name]
    assert after_facade[name].__code__ is after_source[name].__code__
"""
    )


def test_facade_then_owner_reload_keeps_one_current_contract() -> None:
    _run_reload_contract(
        """
old_class = base.DataFetcherManager
before_source, before_facade = bindings()
base = importlib.reload(base)
assert base.DataFetcherManager is not old_class
after_base_source, after_base_facade = bindings()
for name in names:
    assert after_base_source[name] is before_source[name]
    assert after_base_facade[name] is not before_facade[name]
reloaded_class = base.DataFetcherManager
rankings = importlib.reload(rankings)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_facade_patch_seam_intercepts_sector_rankings_meta() -> None:
    manager = DataFetcherManager(fetchers=[])
    sentinel_top = [{"name": "patched-top"}]
    sentinel_bottom = [{"name": "patched-bottom"}]
    with patch.object(
        DataFetcherManager,
        "_get_sector_rankings_with_meta",
        return_value=(sentinel_top, sentinel_bottom, [], ""),
    ) as mocked:
        top, bottom = manager.get_sector_rankings(3)
    assert top is sentinel_top
    assert bottom is sentinel_bottom
    mocked.assert_called_once_with(3)


def test_empty_provider_results_follow_existing_fallback_exits() -> None:
    class _EmptyRankingFetcher:
        name = "EmptyRankingFetcher"
        priority = 0

        def get_sector_rankings(self, n: int):
            return (None, None)

        def get_concept_rankings(self, n: int):
            return ([], [])

        def get_hot_stocks(self, n: int):
            return []

        def get_limit_up_pool(self, date=None, n: int = 20):
            return []

    DataFetcherManager.clear_concept_rankings_cache_for_tests()
    manager = DataFetcherManager(fetchers=[_EmptyRankingFetcher()])
    assert manager.get_sector_rankings(5) == ([], [])
    assert manager.get_concept_rankings(5) == ([], [])
    assert manager.get_hot_stocks(10) == []
    assert manager.get_limit_up_pool(n=20) == []
    DataFetcherManager.clear_concept_rankings_cache_for_tests()


def test_copy_ranking_rows_returns_shallow_copies() -> None:
    rows = [{"name": "白酒", "change": 1.2}]
    copied = DataFetcherManager._copy_ranking_rows(rows)
    assert copied == rows
    assert copied is not rows
    assert copied[0] is not rows[0]
    copied[0]["name"] = "mutated"
    assert rows[0]["name"] == "白酒"
    assert DataFetcherManager._copy_ranking_rows(None) == []


def test_concept_rankings_cache_is_shared_and_clearable() -> None:
    class _ConceptFetcher:
        name = "ConceptFetcher"
        priority = 0
        calls = 0

        def get_concept_rankings(self, n: int):
            type(self).calls += 1
            return ([{"name": "top", "n": n}], [{"name": "bottom", "n": n}])

    DataFetcherManager.clear_concept_rankings_cache_for_tests()
    _ConceptFetcher.calls = 0
    first = DataFetcherManager(fetchers=[_ConceptFetcher()])
    second = DataFetcherManager(fetchers=[_ConceptFetcher()])
    first_top, first_bottom = first.get_concept_rankings(5)
    second_top, second_bottom = second.get_concept_rankings(5)
    assert _ConceptFetcher.calls == 1
    assert first_top == second_top == [{"name": "top", "n": 5}]
    assert first_bottom == second_bottom == [{"name": "bottom", "n": 5}]
    assert first_top is not second_top
    DataFetcherManager.clear_concept_rankings_cache_for_tests()
    third = DataFetcherManager(fetchers=[_ConceptFetcher()])
    third.get_concept_rankings(5)
    assert _ConceptFetcher.calls == 2
    DataFetcherManager.clear_concept_rankings_cache_for_tests()


def test_package_export_still_exposes_data_fetcher_manager() -> None:
    from src.data_provider import DataFetcherManager as PackageManager

    assert PackageManager is DataFetcherManager
    assert inspect.isclass(PackageManager)
