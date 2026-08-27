# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for fundamental context extraction."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import src.data_provider.base as base
import src.data_provider.manager_parts.fundamental_context_methods as fundamental_context
from src.data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "fundamental_context_methods.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def _pipeline_config(**overrides):
    values = dict(
        enable_fundamental_pipeline=True,
        fundamental_cache_ttl_seconds=0,
        fundamental_stage_timeout_seconds=1.5,
        fundamental_fetch_timeout_seconds=0.8,
        fundamental_retry_max=1,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_fundamental_context_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = fundamental_context.EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_public_get_fundamental_context_signature_is_unchanged() -> None:
    signature = inspect.signature(DataFetcherManager.get_fundamental_context)
    assert list(signature.parameters) == ["self", "stock_code", "budget_seconds"]
    assert signature.parameters["stock_code"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["budget_seconds"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["budget_seconds"].default is None


def test_get_fundamental_context_final_exit_keeps_validation_wrapper() -> None:
    method = DataFetcherManager.__dict__["get_fundamental_context"]
    assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is not None
    original = getattr(method, "_stockpulse_data_validation_original")
    source = _descriptor_function(
        vars(fundamental_context._FundamentalContextMethods)["get_fundamental_context"]
    )
    assert original is not source
    assert original.__code__ is source.__code__


def test_owner_module_exists_for_fundamental_context_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "fundamental_context_methods" in source
    assert "bind_fundamental_context_methods_facade" in source
    assert "def get_fundamental_context(" not in source
    assert "def _normalize_source_chain(" not in source
    importlib.import_module("src.data_provider.manager_parts.fundamental_context_methods")


def test_fundamental_context_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(fundamental_context._FundamentalContextMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == fundamental_context.__name__
    assert tuple(source_names) == fundamental_context.EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.fundamental_context_methods as fundamental_context",
                    "",
                    "names = fundamental_context.EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES",
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
                    "            vars(fundamental_context._FundamentalContextMethods)[name]",
                    "        )",
                    "        facade[name] = descriptor_function(",
                    "            vars(base.DataFetcherManager)[name]",
                    "        )",
                    "        assert facade[name] is not source[name]",
                    "        assert facade[name].__code__ is source[name].__code__",
                    "        assert facade[name].__globals__ is vars(base)",
                    "        assert facade[name].__module__ == 'src.data_provider.base'",
                    "        assert facade[name].__qualname__ == f'DataFetcherManager.{name}'",
                    "    method = vars(base.DataFetcherManager)['get_fundamental_context']",
                    "    assert getattr(",
                    "        method,",
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
fundamental_context = importlib.reload(fundamental_context)
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
fundamental_context = importlib.reload(fundamental_context)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_facade_patch_seam_intercepts_market_not_supported_builder() -> None:
    manager = DataFetcherManager(fetchers=[])
    sentinel = {"market": "crypto", "status": "not_supported"}
    with patch("src.config.get_config", return_value=_pipeline_config()), patch.object(
        DataFetcherManager,
        "_build_market_not_supported",
        return_value=sentinel,
    ) as mocked:
        ctx = manager.get_fundamental_context("crypto:BTC")
    assert ctx is sentinel
    mocked.assert_called_once_with(
        market="crypto",
        reason="equity fundamentals do not apply to crypto assets",
    )


def test_disabled_pipeline_uses_market_not_supported_without_offshore_load() -> None:
    manager = DataFetcherManager(fetchers=[])
    sentinel = {"market": "cn", "status": "not_supported"}
    with patch(
        "src.config.get_config",
        return_value=_pipeline_config(enable_fundamental_pipeline=False),
    ), patch.object(
        DataFetcherManager,
        "_build_offshore_fundamental_context",
        side_effect=AssertionError("disabled pipeline must not load offshore context"),
    ), patch.object(
        DataFetcherManager,
        "_build_market_not_supported",
        return_value=sentinel,
    ) as mocked:
        ctx = manager.get_fundamental_context("600519")
    assert ctx is sentinel
    mocked.assert_called_once_with(
        market="cn",
        reason="fundamental pipeline disabled",
    )


def test_normalize_source_chain_defaults_empty_and_passthrough() -> None:
    default = [{"provider": "akshare", "result": "ok", "duration_ms": 12}]
    assert DataFetcherManager._normalize_source_chain(None, "akshare", "ok", 12) == default
    assert DataFetcherManager._normalize_source_chain([], "akshare", "ok", 12) == default
    assert DataFetcherManager._normalize_source_chain(
        [{"provider": "tushare", "result": "partial", "duration_ms": 3}],
        "akshare",
        "ok",
        12,
    ) == [{"provider": "tushare", "result": "partial", "duration_ms": 3}]


def test_should_cache_fundamental_context_keeps_failed_and_ok_rules() -> None:
    assert DataFetcherManager._should_cache_fundamental_context({"status": "ok"}) is True
    assert DataFetcherManager._should_cache_fundamental_context({"status": "failed"}) is False
    assert DataFetcherManager._should_cache_fundamental_context("not-a-dict") is False
    assert DataFetcherManager._should_cache_fundamental_context(
        {"status": "partial", "valuation": {"data": {"pe_ratio": 12.0}}}
    ) is True
    assert DataFetcherManager._should_cache_fundamental_context(
        {"status": "partial", "valuation": {"data": {}}}
    ) is False


def test_has_meaningful_payload_still_uses_rebound_try_scalar_isna() -> None:
    assert DataFetcherManager._has_meaningful_payload(np.nan) is False
    assert DataFetcherManager._has_meaningful_payload("白酒") is True


def test_package_export_still_exposes_data_fetcher_manager() -> None:
    from src.data_provider import DataFetcherManager as PackageManager

    assert PackageManager is DataFetcherManager
    assert inspect.isclass(PackageManager)
