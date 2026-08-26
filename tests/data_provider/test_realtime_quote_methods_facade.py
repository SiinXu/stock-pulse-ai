# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for realtime quote extraction."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import src.data_provider.base as base
import src.data_provider.manager_parts.realtime_quote_methods as realtime_quote
from src.data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "realtime_quote_methods.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def test_realtime_quote_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = realtime_quote.EXPECTED_REALTIME_QUOTE_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_public_get_realtime_quote_signature_is_unchanged() -> None:
    signature = inspect.signature(DataFetcherManager.get_realtime_quote)
    assert list(signature.parameters) == ["self", "stock_code", "log_final_failure"]
    assert signature.parameters["stock_code"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["log_final_failure"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["log_final_failure"].default is True


def test_get_realtime_quote_final_exit_keeps_validation_wrapper() -> None:
    method = DataFetcherManager.__dict__["get_realtime_quote"]
    assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is not None
    original = getattr(method, "_stockpulse_data_validation_original")
    source = _descriptor_function(
        vars(realtime_quote._RealtimeQuoteMethods)["get_realtime_quote"]
    )
    assert original is not source
    assert original.__code__ is source.__code__


def test_owner_module_exists_for_realtime_quote_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "realtime_quote_methods" in source
    assert "bind_realtime_quote_methods_facade" in source
    assert "def get_realtime_quote(" not in source
    importlib.import_module("src.data_provider.manager_parts.realtime_quote_methods")


def test_realtime_quote_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(realtime_quote._RealtimeQuoteMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == realtime_quote.__name__
    assert tuple(source_names) == realtime_quote.EXPECTED_REALTIME_QUOTE_METHOD_NAMES


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.realtime_quote_methods as realtime_quote",
                    "",
                    "names = realtime_quote.EXPECTED_REALTIME_QUOTE_METHOD_NAMES",
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
                    "            vars(realtime_quote._RealtimeQuoteMethods)[name]",
                    "        )",
                    "        facade[name] = descriptor_function(",
                    "            vars(base.DataFetcherManager)[name]",
                    "        )",
                    "        assert facade[name] is not source[name]",
                    "        assert facade[name].__code__ is source[name].__code__",
                    "        assert facade[name].__globals__ is vars(base)",
                    "        assert facade[name].__module__ == 'src.data_provider.base'",
                    "        assert facade[name].__qualname__ == f'DataFetcherManager.{name}'",
                    "    quote = vars(base.DataFetcherManager)['get_realtime_quote']",
                    "    assert getattr(",
                    "        quote,",
                    "        '_stockpulse_data_validation_wrapper_token',",
                    "        None,",
                    "    ) is not None",
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
realtime_quote = importlib.reload(realtime_quote)
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
realtime_quote = importlib.reload(realtime_quote)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_disabled_realtime_quote_returns_none_without_provider_calls() -> None:
    manager = DataFetcherManager(fetchers=[])
    with patch("src.config.get_config") as mock_get_config:
        mock_get_config.return_value = SimpleNamespace(enable_realtime_quote=False)
        with patch.object(
            DataFetcherManager,
            "_get_fetchers_for_capability",
            side_effect=AssertionError("disabled quotes must not probe providers"),
        ):
            assert manager.get_realtime_quote("600519") is None


def test_package_export_still_exposes_data_fetcher_manager() -> None:
    from src.data_provider import DataFetcherManager as PackageManager

    assert PackageManager is DataFetcherManager
    assert inspect.isclass(PackageManager)
