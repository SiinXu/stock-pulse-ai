# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for money-flow extraction."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import src.data_provider.base as base
import src.data_provider.manager_parts.money_flow_methods as money_flow
from src.data_provider.base import DataFetcherManager
from src.data_provider.money_flow_types import MoneyFlowStatus


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "money_flow_methods.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def test_money_flow_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = money_flow.EXPECTED_MONEY_FLOW_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_public_get_money_flow_signature_is_unchanged() -> None:
    signature = inspect.signature(DataFetcherManager.get_money_flow)
    assert list(signature.parameters) == ["self", "stock_code", "days"]
    assert signature.parameters["stock_code"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["days"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["days"].default == 5


def test_money_flow_timestamp_remains_staticmethod() -> None:
    assert isinstance(vars(DataFetcherManager)["_money_flow_timestamp"], staticmethod)
    assert isinstance(
        vars(money_flow._MoneyFlowMethods)["_money_flow_timestamp"],
        staticmethod,
    )


def test_get_money_flow_has_no_validation_wrapper_token() -> None:
    method = DataFetcherManager.__dict__["get_money_flow"]
    assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_owner_module_exists_for_money_flow_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "money_flow_methods" in source
    assert "bind_money_flow_methods_facade" in source
    assert "def get_money_flow(" not in source
    assert "def _money_flow_timestamp(" not in source
    importlib.import_module("src.data_provider.manager_parts.money_flow_methods")


def test_money_flow_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(money_flow._MoneyFlowMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == money_flow.__name__
    assert tuple(source_names) == money_flow.EXPECTED_MONEY_FLOW_METHOD_NAMES


def test_money_flow_placeholders_preserve_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    assert names.index("get_chip_distribution") < names.index("_money_flow_timestamp")
    assert names.index("_money_flow_timestamp") < names.index("get_money_flow")
    assert names.index("get_money_flow") < names.index("get_stock_name")
    assert names.index("_MONEY_FLOW_CACHE_TTL_SECONDS") < names.index("_money_flow_timestamp")
    assert names.index("_MONEY_FLOW_STALE_TTL_SECONDS") < names.index("_money_flow_timestamp")
    assert names.index("_MONEY_FLOW_CACHE_MAX_ENTRIES") < names.index("_money_flow_timestamp")


def test_money_flow_ttl_class_attributes_remain_on_facade() -> None:
    assert DataFetcherManager._MONEY_FLOW_CACHE_TTL_SECONDS == 600.0
    assert DataFetcherManager._MONEY_FLOW_STALE_TTL_SECONDS == 86400.0
    assert DataFetcherManager._MONEY_FLOW_CACHE_MAX_ENTRIES == 256
    source_names = {
        name
        for name, descriptor in vars(money_flow._MoneyFlowMethods).items()
        if not name.startswith("__") and _descriptor_function(descriptor) is not None
    }
    assert "_MONEY_FLOW_CACHE_TTL_SECONDS" not in source_names
    assert "_MONEY_FLOW_STALE_TTL_SECONDS" not in source_names
    assert "_MONEY_FLOW_CACHE_MAX_ENTRIES" not in source_names


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.money_flow_methods as money_flow",
                    "",
                    "names = money_flow.EXPECTED_MONEY_FLOW_METHOD_NAMES",
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
                    "            vars(money_flow._MoneyFlowMethods)[name]",
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
money_flow = importlib.reload(money_flow)
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
money_flow = importlib.reload(money_flow)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_facade_patch_seam_intercepts_money_flow_timestamp() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        DataFetcherManager,
        "_money_flow_timestamp",
        return_value="2026-08-27T00:00:00+00:00",
    ) as mocked:
        outcome = manager.get_money_flow("AAPL")
    mocked.assert_called_once()
    assert outcome.status == MoneyFlowStatus.NOT_SUPPORTED
    assert outcome.error_code == "money_flow_market_not_supported"
    assert outcome.fetched_at == "2026-08-27T00:00:00+00:00"


def test_unsupported_market_does_not_probe_providers() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        DataFetcherManager,
        "_get_fetchers_for_capability",
        side_effect=AssertionError("non-CN money flow must not probe providers"),
    ):
        outcome = manager.get_money_flow("AAPL")
    assert outcome.status == MoneyFlowStatus.NOT_SUPPORTED
    assert outcome.error_code == "money_flow_market_not_supported"


def test_package_export_still_exposes_data_fetcher_manager() -> None:
    from src.data_provider import DataFetcherManager as PackageManager

    assert PackageManager is DataFetcherManager
    assert inspect.isclass(PackageManager)
