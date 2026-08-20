# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, patch, and edge guards for belong-board extraction."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import src.data_provider.base as base
import src.data_provider.manager_parts.belong_board_methods as belong_board
from src.data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "belong_board_methods.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


class _BoardFetcher:
    def __init__(self, name: str, result):
        self.name = name
        self.priority = 0
        self._result = result
        self.calls = 0

    def get_belong_board(self, _stock_code: str):
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_belong_board_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = belong_board.EXPECTED_BELONG_BOARD_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_owner_module_exists_for_belong_board_extraction() -> None:
    assert OWNER_PATH.is_file()
    assert "belong_board_methods" in BASE_PATH.read_text(encoding="utf-8")
    importlib.import_module("src.data_provider.manager_parts.belong_board_methods")


def test_belong_board_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(belong_board._BelongBoardMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == belong_board.__name__
    assert tuple(source_names) == belong_board.EXPECTED_BELONG_BOARD_METHOD_NAMES


def test_facade_patch_seam_intercepts_normalize_belong_boards() -> None:
    fetcher = _BoardFetcher("BoardFetcher", [{"name": "ignored"}])
    manager = DataFetcherManager(fetchers=[fetcher])
    sentinel = [{"name": "patched", "type": "概念"}]
    with patch.object(
        DataFetcherManager,
        "_normalize_belong_boards",
        return_value=sentinel,
    ) as mocked:
        boards = manager.get_belong_boards("600519")
    assert boards == sentinel
    mocked.assert_called_once()
    assert fetcher.calls == 1


def test_facade_pd_isna_patch_still_intercepts_missing_board_value() -> None:
    sentinel = object()
    with patch.object(base.pd, "isna", return_value=True) as mocked:
        assert DataFetcherManager._is_missing_board_value(sentinel) is True
    mocked.assert_called()


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.belong_board_methods as belong_board",
                    "",
                    "names = belong_board.EXPECTED_BELONG_BOARD_METHOD_NAMES",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        return descriptor.__func__",
                    "    return descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    facade = {}",
                    "    for name in names:",
                    "        source[name] = descriptor_function(",
                    "            vars(belong_board._BelongBoardMethods)[name]",
                    "        )",
                    "        facade[name] = descriptor_function(",
                    "            vars(base.DataFetcherManager)[name]",
                    "        )",
                    "        assert facade[name] is not source[name]",
                    "        assert facade[name].__code__ is source[name].__code__",
                    "        assert facade[name].__globals__ is vars(base)",
                    "        assert facade[name].__module__ == 'src.data_provider.base'",
                    "        assert facade[name].__qualname__ == f'DataFetcherManager.{name}'",
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
belong_board = importlib.reload(belong_board)
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
belong_board = importlib.reload(belong_board)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_try_scalar_isna_none_nan_and_container_counterexamples() -> None:
    assert DataFetcherManager._try_scalar_isna(None, "board_value") is True
    assert DataFetcherManager._try_scalar_isna(np.nan, "board_value") is True
    assert DataFetcherManager._try_scalar_isna(float("nan"), "board_value") is True
    pandas_scalar = pd.Series([np.nan], dtype="float64").iloc[0]
    assert DataFetcherManager._try_scalar_isna(pandas_scalar, "board_value") is True
    zero_dim = np.array(np.nan)
    assert DataFetcherManager._try_scalar_isna(zero_dim, "board_value") is True
    assert DataFetcherManager._try_scalar_isna(np.array([np.nan, 1.0]), "board_value") is None
    assert DataFetcherManager._try_scalar_isna([], "board_value") is None
    assert DataFetcherManager._try_scalar_isna({"name": "白酒"}, "board_value") is None
    assert DataFetcherManager._try_scalar_isna(pd.DataFrame({"name": ["白酒"]}), "board_value") is None
    assert DataFetcherManager._try_scalar_isna("白酒", "board_value") is False
    assert DataFetcherManager._try_scalar_isna(object(), "board_value") is False


def test_is_missing_board_value_string_and_object_counterexamples() -> None:
    for value in (None, np.nan, "", "  ", "null", "NaN", " n/a ", "none", "NA"):
        assert DataFetcherManager._is_missing_board_value(value) is True, value
    assert DataFetcherManager._is_missing_board_value("白酒") is False
    assert DataFetcherManager._is_missing_board_value(object()) is False
    nested = [{"name": "白酒"}]
    assert DataFetcherManager._is_missing_board_value(nested) is False


def test_normalize_belong_boards_none_nan_string_list_dict_nested() -> None:
    normalize = DataFetcherManager._normalize_belong_boards
    assert normalize(None) == []
    assert normalize(np.nan) == []
    assert normalize("") == []
    assert normalize("  ") == []
    assert normalize("白酒") == [{"name": "白酒"}]
    assert normalize(["白酒", "  ", None, "消费", "白酒"]) == [
        {"name": "白酒"},
        {"name": "消费"},
    ]
    assert normalize({"name": "白酒", "code": "BK0815", "type": "行业"}) == [
        {"name": "白酒", "code": "BK0815", "type": "行业"},
    ]
    assert normalize(
        [
            {"name": "白酒", "children": [{"name": "ignored-nested"}]},
            {"board_name": "消费", "code": None, "type": "  "},
            {"name": None, "code": "BK0000"},
            {"所属板块": "新能源"},
        ]
    ) == [
        {"name": "白酒"},
        {"name": "消费"},
        {"name": "新能源"},
    ]
    assert normalize([{"name": "白酒"}, {"name": "白酒"}]) == [{"name": "白酒"}]


def test_normalize_belong_boards_dataframe_and_pandas_scalar() -> None:
    normalize = DataFetcherManager._normalize_belong_boards
    empty = pd.DataFrame(columns=["板块名称", "板块代码", "板块类型"])
    assert normalize(empty) == []
    frame = pd.DataFrame(
        [
            {"板块名称": "白酒", "板块代码": "BK0815", "板块类型": "行业"},
            {"板块名称": np.nan, "板块代码": "BK0000", "板块类型": "概念"},
            {"板块名称": "消费", "板块代码": pd.NA, "板块类型": "  "},
            {"板块名称": "白酒", "板块代码": "DUP", "板块类型": "行业"},
        ]
    )
    assert normalize(frame) == [
        {"name": "白酒", "code": "BK0815", "type": "行业"},
        {"name": "消费"},
    ]
    nameless = pd.DataFrame([{"板块代码": "BK0815"}])
    assert normalize(nameless) == []
    pandas_scalar = pd.Series(["白酒"], dtype="object").iloc[0]
    assert normalize(pandas_scalar) == [{"name": "白酒"}]


def test_get_belong_boards_uses_facade_normalize_and_skips_missing_payloads() -> None:
    empty = _BoardFetcher("EmptyBoardFetcher", None)
    nan_frame = _BoardFetcher(
        "NanBoardFetcher",
        pd.DataFrame([{"name": np.nan}]),
    )
    nested = _BoardFetcher(
        "NestedBoardFetcher",
        [
            {"name": None},
            {"name": "白酒", "children": [{"name": "ignored"}]},
            "消费",
        ],
    )
    manager = DataFetcherManager(fetchers=[empty, nan_frame, nested])
    boards = manager.get_belong_boards("600519")
    assert boards == [{"name": "白酒"}, {"name": "消费"}]
    assert empty.calls == 1
    assert nan_frame.calls == 1
    assert nested.calls == 1


def test_get_belong_boards_does_not_normalize_non_cn_symbols() -> None:
    fetcher = _BoardFetcher("BoardFetcher", [{"name": "should-not-run"}])
    manager = DataFetcherManager(fetchers=[fetcher])
    assert manager.get_belong_boards("AAPL") == []
    assert manager.get_belong_boards("HK00700") == []
    assert fetcher.calls == 0


def test_has_meaningful_payload_still_uses_rebound_try_scalar_isna() -> None:
    assert DataFetcherManager._has_meaningful_payload(np.nan) is False
    assert DataFetcherManager._has_meaningful_payload("白酒") is True
    with patch.object(
        DataFetcherManager,
        "_try_scalar_isna",
        return_value=True,
    ) as mocked:
        assert DataFetcherManager._has_meaningful_payload(object()) is False
    mocked.assert_called_once()
    assert mocked.call_args.args[1] == "fundamental_payload"
