# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline characterization for Tushare stock-name and stock-list extraction."""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

import src.data_provider.tushare_fetcher as tushare_fetcher
import src.data_provider.tushare_parts.stock_identity as stock_identity
from src.data_provider.tushare_fetcher import (
    TushareFetcher,
    _EXPECTED_STOCK_IDENTITY_METHOD_NAMES,
)


ROOT = Path(__file__).resolve().parents[2]
OWNER_PATH = ROOT / "src" / "data_provider" / "tushare_parts" / "stock_identity.py"
FACADE_PATH = ROOT / "src" / "data_provider" / "tushare_fetcher.py"


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    return descriptor


def _make_fetcher() -> TushareFetcher:
    with patch.object(TushareFetcher, "_init_api", return_value=None):
        fetcher = TushareFetcher()
    fetcher._api = MagicMock()
    return fetcher


def test_stock_identity_methods_remain_on_tushare_fetcher_facade() -> None:
    for name in _EXPECTED_STOCK_IDENTITY_METHOD_NAMES:
        method = getattr(TushareFetcher, name)
        assert callable(method), name
        function = _descriptor_function(vars(TushareFetcher)[name])
        assert function.__module__ == "src.data_provider.tushare_fetcher", name
        assert function.__qualname__ == f"TushareFetcher.{name}", name
        assert function.__globals__ is vars(tushare_fetcher), name


def test_stock_identity_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(stock_identity._StockIdentityMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(TushareFetcher)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == stock_identity.__name__
    assert tuple(source_names) == _EXPECTED_STOCK_IDENTITY_METHOD_NAMES


def test_owner_module_does_not_import_facade() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert all("tushare_fetcher" not in name for name in imported)
    facade_source = FACADE_PATH.read_text(encoding="utf-8")
    assert "def get_stock_name(" not in facade_source
    assert "def get_stock_list(" not in facade_source
    assert "stock_identity" in facade_source


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.tushare_fetcher as facade",
                    "import src.data_provider.tushare_parts.stock_identity as owner",
                    "",
                    "names = facade._EXPECTED_STOCK_IDENTITY_METHOD_NAMES",
                    "",
                    "def descriptor_function(descriptor):",
                    "    if isinstance(descriptor, (staticmethod, classmethod)):",
                    "        descriptor = descriptor.__func__",
                    "    return descriptor",
                    "",
                    "def bindings():",
                    "    source = {}",
                    "    bound = {}",
                    "    for name in names:",
                    "        source[name] = descriptor_function(",
                    "            vars(owner._StockIdentityMethods)[name]",
                    "        )",
                    "        bound[name] = descriptor_function(",
                    "            vars(facade.TushareFetcher)[name]",
                    "        )",
                    "        assert bound[name] is not source[name]",
                    "        assert bound[name].__code__ is source[name].__code__",
                    "        assert bound[name].__globals__ is vars(facade)",
                    "        assert bound[name].__module__ == 'src.data_provider.tushare_fetcher'",
                    "        assert bound[name].__qualname__ == f'TushareFetcher.{name}'",
                    "    return source, bound",
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
old_class = facade.TushareFetcher
before_source, before_bound = bindings()
owner = importlib.reload(owner)
assert facade.TushareFetcher is old_class
after_source, after_bound = bindings()
for name in names:
    assert after_source[name] is not before_source[name]
    assert after_bound[name] is not before_bound[name]
    assert after_bound[name].__code__ is after_source[name].__code__
"""
    )


def test_facade_then_owner_reload_keeps_one_current_contract() -> None:
    _run_reload_contract(
        """
old_class = facade.TushareFetcher
before_source, before_bound = bindings()
facade = importlib.reload(facade)
assert facade.TushareFetcher is not old_class
after_facade_source, after_facade_bound = bindings()
for name in names:
    assert after_facade_source[name] is before_source[name]
    assert after_facade_bound[name] is not before_bound[name]
reloaded_class = facade.TushareFetcher
owner = importlib.reload(owner)
assert facade.TushareFetcher is reloaded_class
after_owner_source, after_owner_bound = bindings()
for name in names:
    assert after_owner_source[name] is not after_facade_source[name]
    assert after_owner_bound[name] is not after_facade_bound[name]
    assert after_owner_bound[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_cache_hit_skips_rate_limit_and_api() -> None:
    fetcher = _make_fetcher()
    fetcher._stock_name_cache = {"600519": "贵州茅台"}
    with patch.object(
        fetcher,
        "_check_rate_limit",
        side_effect=AssertionError("cache hit must not rate-limit"),
    ):
        assert fetcher.get_stock_name("600519") == "贵州茅台"
    fetcher._api.stock_basic.assert_not_called()
    fetcher._api.hk_basic.assert_not_called()
    fetcher._api.fund_basic.assert_not_called()


def test_get_stock_list_populates_shared_name_cache() -> None:
    fetcher = _make_fetcher()
    fetcher._api.stock_basic.return_value = pd.DataFrame(
        {
            "ts_code": ["600519.SH", "000001.SZ"],
            "name": ["贵州茅台", "平安银行"],
            "industry": ["白酒", "银行"],
            "area": ["贵州", "深圳"],
            "market": ["主板", "主板"],
        }
    )
    with patch.object(fetcher, "_check_rate_limit"):
        listed = fetcher.get_stock_list()
    assert listed is not None
    assert list(listed.columns) == ["code", "name", "industry", "area", "market"]
    assert list(listed["code"]) == ["600519", "000001"]
    assert fetcher._stock_name_cache["600519"] == "贵州茅台"
    assert fetcher._stock_name_cache["000001"] == "平安银行"
    with patch.object(
        fetcher,
        "_check_rate_limit",
        side_effect=AssertionError("list populate must be visible to later get_stock_name"),
    ):
        assert fetcher.get_stock_name("600519") == "贵州茅台"
    fetcher._api.stock_basic.assert_called_once()


def test_get_stock_name_hk_branch_uses_hk_basic() -> None:
    fetcher = _make_fetcher()
    fetcher._api.hk_basic.return_value = pd.DataFrame(
        {"ts_code": ["00700.HK"], "name": ["腾讯控股"]}
    )
    with patch.object(fetcher, "_check_rate_limit") as rate_limit, patch.object(
        fetcher,
        "_convert_hk_stock_code_for_tushare",
        return_value="00700.HK",
    ) as convert_hk:
        assert fetcher.get_stock_name("HK00700") == "腾讯控股"
    rate_limit.assert_called_once()
    convert_hk.assert_called_once_with("HK00700")
    fetcher._api.hk_basic.assert_called_once_with(
        ts_code="00700.HK",
        fields="ts_code,name",
    )
    fetcher._api.stock_basic.assert_not_called()
    fetcher._api.fund_basic.assert_not_called()
    assert fetcher._stock_name_cache["HK00700"] == "腾讯控股"


def test_get_stock_name_etf_branch_uses_fund_basic() -> None:
    fetcher = _make_fetcher()
    fetcher._api.fund_basic.return_value = pd.DataFrame(
        {"ts_code": ["510300.SH"], "name": ["沪深300ETF"]}
    )
    with patch.object(fetcher, "_check_rate_limit") as rate_limit, patch.object(
        fetcher,
        "_convert_stock_code",
        return_value="510300.SH",
    ) as convert_code:
        assert fetcher.get_stock_name("510300") == "沪深300ETF"
    rate_limit.assert_called_once()
    convert_code.assert_called_once_with("510300")
    fetcher._api.fund_basic.assert_called_once_with(
        ts_code="510300.SH",
        fields="ts_code,name",
    )
    fetcher._api.stock_basic.assert_not_called()
    fetcher._api.hk_basic.assert_not_called()


def test_get_stock_name_a_share_branch_uses_stock_basic() -> None:
    fetcher = _make_fetcher()
    fetcher._api.stock_basic.return_value = pd.DataFrame(
        {"ts_code": ["600519.SH"], "name": ["贵州茅台"]}
    )
    with patch.object(fetcher, "_check_rate_limit") as rate_limit, patch.object(
        fetcher,
        "_convert_stock_code",
        return_value="600519.SH",
    ) as convert_code:
        assert fetcher.get_stock_name("600519") == "贵州茅台"
    rate_limit.assert_called_once()
    convert_code.assert_called_once_with("600519")
    fetcher._api.stock_basic.assert_called_once_with(
        ts_code="600519.SH",
        fields="ts_code,name",
    )
    fetcher._api.hk_basic.assert_not_called()
    fetcher._api.fund_basic.assert_not_called()


def test_uninitialized_api_returns_none_without_cache_or_rate_limit() -> None:
    fetcher = _make_fetcher()
    fetcher._api = None
    fetcher._stock_name_cache = {"600519": "贵州茅台"}
    with patch.object(
        fetcher,
        "_check_rate_limit",
        side_effect=AssertionError("uninitialized API must not rate-limit"),
    ):
        assert fetcher.get_stock_name("600519") is None
        assert fetcher.get_stock_list() is None


def test_stock_name_and_list_exceptions_fail_open() -> None:
    fetcher = _make_fetcher()
    fetcher._api.stock_basic.side_effect = RuntimeError("tushare unavailable")
    with patch.object(fetcher, "_check_rate_limit"), patch.object(
        fetcher,
        "_convert_stock_code",
        return_value="600519.SH",
    ):
        assert fetcher.get_stock_name("600519") is None
        assert fetcher.get_stock_list() is None
