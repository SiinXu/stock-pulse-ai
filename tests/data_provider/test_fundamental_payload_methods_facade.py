# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for fundamental payload helpers."""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import src.data_provider.base as base
import src.data_provider.manager_parts.fundamental_payload_methods as payload
from src.data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "fundamental_payload_methods.py"
)

STATIC_NAMES = (
    "_normalize_source_chain",
    "_block_status",
    "_build_fundamental_block",
    "_has_meaningful_payload",
    "_infer_block_status",
    "_should_cache_fundamental_context",
)
INSTANCE_NAMES = ("_build_market_not_supported",)
BLANK_STRINGS = ("", " ", "-", "nan", "none", "null", "n/a", "na", "NaN", "N/A")


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def test_payload_methods_remain_on_data_fetcher_manager_facade() -> None:
    for name in payload.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_payload_signatures_and_descriptor_kinds_are_unchanged() -> None:
    expected = {
        "_normalize_source_chain": ["entries", "provider", "result", "duration_ms"],
        "_block_status": ["payload", "available"],
        "_build_fundamental_block": ["status", "payload", "source_chain", "errors"],
        "_has_meaningful_payload": ["payload"],
        "_infer_block_status": ["payload", "fallback_status"],
        "_should_cache_fundamental_context": ["context"],
        "_build_market_not_supported": ["self", "market", "reason"],
    }
    defaults = {
        "_block_status": {"available": True},
        "_build_fundamental_block": {
            "payload": None,
            "source_chain": None,
            "errors": None,
        },
    }
    for name in payload.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES:
        descriptor = vars(DataFetcherManager)[name]
        source_descriptor = vars(payload._FundamentalPayloadMethods)[name]
        if name in STATIC_NAMES:
            assert isinstance(descriptor, staticmethod), name
            assert isinstance(source_descriptor, staticmethod), name
        else:
            assert name in INSTANCE_NAMES
            assert not isinstance(descriptor, (staticmethod, classmethod)), name
            assert not isinstance(source_descriptor, (staticmethod, classmethod)), name
        signature = inspect.signature(getattr(DataFetcherManager, name))
        assert list(signature.parameters) == expected[name], name
        for parameter in signature.parameters.values():
            assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name
        for parameter_name, default in defaults.get(name, {}).items():
            assert signature.parameters[parameter_name].default is default, name


def test_moved_names_are_not_validation_wrapped() -> None:
    for name in payload.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES:
        method = DataFetcherManager.__dict__[name]
        assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_owner_module_exists_for_payload_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "fundamental_payload_methods" in source
    assert "bind_fundamental_payload_methods_facade" in source
    for name in payload.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES:
        assert f"def {name}(" not in source
        assert f"    {name} = None" in source
    importlib.import_module(
        "src.data_provider.manager_parts.fundamental_payload_methods"
    )


def test_payload_bodies_leave_manager_and_stay_callable_on_facade() -> None:
    tree = ast.parse(BASE_PATH.read_text(encoding="utf-8"))
    manager_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "DataFetcherManager"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in payload.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES:
        assert name not in manager_defs, name
        assert callable(getattr(DataFetcherManager, name)), name


def test_payload_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(payload._FundamentalPayloadMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == payload.__name__
    assert tuple(source_names) == payload.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES


def test_payload_placeholders_preserve_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    expected = payload.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES
    assert names.index("_get_fundamental_config") < names.index(expected[0])
    for left, right in zip(expected, expected[1:]):
        assert names.index(left) < names.index(right)
    assert names.index("_build_market_not_supported") < names.index(
        "_build_offshore_fundamental_context"
    )


def test_bind_returns_expected_names_in_class_body_order() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    bound = payload.bind_fundamental_payload_methods_facade(
        dummy,
        vars(base),
    )
    assert bound == payload.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES


def test_assemble_raises_import_error_on_expected_name_mismatch() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    extra = staticmethod(lambda: None)
    payload._FundamentalPayloadMethods._extra_payload = extra
    try:
        bound = payload.bind_fundamental_payload_methods_facade(
            dummy,
            vars(base),
        )
        with pytest.raises(
            ImportError,
            match="Unexpected DataFetcherManager fundamental payload methods",
        ):
            if bound != payload.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES:
                raise ImportError(
                    "Unexpected DataFetcherManager fundamental payload methods: "
                    f"{bound!r}"
                )
        assert "_extra_payload" in bound
    finally:
        delattr(payload._FundamentalPayloadMethods, "_extra_payload")


def test_owner_module_declares_expected_names_only() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_FundamentalPayloadMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(payload.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES)


def test_owner_module_has_zero_bare_get_config_and_forbidden_imports() -> None:
    source = OWNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_prefixes = (
        "src.config",
        "src.core",
        "src.services",
        "src.data_provider.base",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "get_config"
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            assert not any(
                node.module == prefix or node.module.startswith(prefix + ".")
                for prefix in forbidden_prefixes
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == prefix or alias.name.startswith(prefix + ".")
                    for prefix in forbidden_prefixes
                )


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.fundamental_payload_methods as payload",
                    "",
                    "names = payload.EXPECTED_FUNDAMENTAL_PAYLOAD_METHOD_NAMES",
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
                    "            vars(payload._FundamentalPayloadMethods)[name]",
                    "        )",
                    "        facade[name] = descriptor_function(",
                    "            vars(base.DataFetcherManager)[name]",
                    "        )",
                    "        assert facade[name] is not source[name]",
                    "        assert facade[name].__code__ is source[name].__code__",
                    "        assert facade[name].__globals__ is vars(base)",
                    "        assert facade[name].__module__ == 'src.data_provider.base'",
                    "        assert facade[name].__qualname__ == f'DataFetcherManager.{name}'",
                    "        assert getattr(",
                    "            vars(base.DataFetcherManager)[name],",
                    "            '_stockpulse_data_validation_wrapper_token',",
                    "            None,",
                    "        ) is None",
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
payload = importlib.reload(payload)
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
payload = importlib.reload(payload)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_package_export_still_exposes_data_fetcher_manager() -> None:
    from src.data_provider import DataFetcherManager as PackageManager

    assert PackageManager is DataFetcherManager
    assert inspect.isclass(PackageManager)


def test_normalize_source_chain_none_empty_scalar_and_dict_fallbacks() -> None:
    default = DataFetcherManager._normalize_source_chain(None, "akshare", "ok", 12)
    assert default == [{"provider": "akshare", "result": "ok", "duration_ms": 12}]
    skipped = DataFetcherManager._normalize_source_chain([None], "akshare", "ok", 12)
    assert skipped == default
    scalar = DataFetcherManager._normalize_source_chain("tushare", "akshare", "ok", 12)
    assert scalar == [{"provider": "tushare", "result": "ok", "duration_ms": 12}]
    mixed = DataFetcherManager._normalize_source_chain(
        [{"provider": "x"}, {"result": "partial"}, {}],
        "akshare",
        "ok",
        12,
    )
    assert mixed == [
        {"provider": "x", "result": "ok", "duration_ms": 12},
        {"provider": "akshare", "result": "partial", "duration_ms": 12},
        {"provider": "akshare", "result": "ok", "duration_ms": 12},
    ]


def test_block_status_not_supported_partial_and_ok() -> None:
    assert DataFetcherManager._block_status({"pe": 10}, available=False) == "not_supported"
    assert DataFetcherManager._block_status({}, available=True) == "partial"
    assert DataFetcherManager._block_status({"pe": 10}) == "ok"


def test_build_fundamental_block_defaults_and_explicit_fields() -> None:
    empty = DataFetcherManager._build_fundamental_block("partial")
    assert empty == {
        "status": "partial",
        "coverage": {"status": "partial"},
        "source_chain": [],
        "errors": [],
        "data": {},
    }
    chain = [{"provider": "akshare", "result": "ok", "duration_ms": 1}]
    filled = DataFetcherManager._build_fundamental_block(
        "ok",
        {"pe": 10},
        chain,
        ["warn"],
    )
    assert filled["status"] == "ok"
    assert filled["coverage"]["status"] == "ok"
    assert filled["source_chain"] is chain
    assert filled["errors"] == ["warn"]
    assert filled["data"] == {"pe": 10}


def test_has_meaningful_payload_blank_nested_and_patched_isna() -> None:
    assert DataFetcherManager._has_meaningful_payload(None) is False
    for blank in BLANK_STRINGS:
        assert DataFetcherManager._has_meaningful_payload(blank) is False, blank
    assert DataFetcherManager._has_meaningful_payload(pd.DataFrame()) is False
    assert DataFetcherManager._has_meaningful_payload({"a": None, "b": ""}) is False
    assert DataFetcherManager._has_meaningful_payload({"a": {"b": "白酒"}}) is True
    assert DataFetcherManager._has_meaningful_payload([None, "-"]) is False
    assert DataFetcherManager._has_meaningful_payload([None, "白酒"]) is True
    assert DataFetcherManager._has_meaningful_payload(pd.Series([None, np.nan])) is False
    assert DataFetcherManager._has_meaningful_payload(pd.Series([None, "白酒"])) is True
    assert DataFetcherManager._has_meaningful_payload(np.array([None, np.nan])) is False
    assert DataFetcherManager._has_meaningful_payload(np.array([None, "白酒"])) is True
    assert DataFetcherManager._has_meaningful_payload(np.nan) is False
    with patch.object(
        DataFetcherManager,
        "_try_scalar_isna",
        return_value=True,
    ) as mocked:
        assert DataFetcherManager._has_meaningful_payload(object()) is False
    mocked.assert_called_once()
    assert mocked.call_args.args[0].__class__ is object
    assert mocked.call_args.args[1] == "fundamental_payload"


def test_infer_block_status_meaningful_kept_and_other_fallback() -> None:
    assert DataFetcherManager._infer_block_status({"pe": 10}, "partial") == "ok"
    assert DataFetcherManager._infer_block_status({}, "failed") == "failed"
    assert DataFetcherManager._infer_block_status({}, "partial") == "partial"
    assert DataFetcherManager._infer_block_status({}, "not_supported") == "not_supported"
    assert DataFetcherManager._infer_block_status({}, "unknown") == "partial"


def test_should_cache_fundamental_context_ok_failed_non_dict_and_blocks() -> None:
    assert DataFetcherManager._should_cache_fundamental_context({"status": "ok"}) is True
    assert DataFetcherManager._should_cache_fundamental_context({"status": "failed"}) is False
    assert DataFetcherManager._should_cache_fundamental_context("not-a-dict") is False
    assert DataFetcherManager._should_cache_fundamental_context(
        {"status": "partial", "valuation": {"data": {"pe": 10}}}
    ) is True
    assert DataFetcherManager._should_cache_fundamental_context(
        {"status": "partial", "valuation": {"data": {}}}
    ) is False


def test_build_market_not_supported_etf_vs_non_etf() -> None:
    manager = DataFetcherManager(fetchers=[])
    etf = manager._build_market_not_supported("etf", "etf skip")
    assert etf["status"] == "partial"
    assert etf["valuation"]["status"] == "partial"
    for block in ("growth", "earnings", "institution", "capital_flow", "dragon_tiger", "boards"):
        assert etf[block]["status"] == "not_supported"
        assert etf[block]["data"] == {}
        assert etf["coverage"][block] == "not_supported"
    assert etf["coverage"]["valuation"] == "partial"
    assert etf["errors"] == ["etf skip"]

    us = manager._build_market_not_supported("us", "us skip")
    assert us["status"] == "not_supported"
    for block in (
        "valuation",
        "growth",
        "earnings",
        "institution",
        "capital_flow",
        "dragon_tiger",
        "boards",
    ):
        assert us[block]["status"] == "not_supported"
        assert us["coverage"][block] == "not_supported"
    assert us["errors"] == ["us skip"]


def test_build_market_not_supported_calls_rebound_build_fundamental_block() -> None:
    manager = DataFetcherManager(fetchers=[])
    sentinel = {
        "status": "patched",
        "coverage": {"status": "patched"},
        "source_chain": [],
        "errors": [],
        "data": {},
    }
    with patch.object(
        manager,
        "_build_fundamental_block",
        return_value=sentinel,
    ) as mocked:
        ctx = manager._build_market_not_supported("cn", "reason")
    assert mocked.call_count == 7
    assert ctx["valuation"] is sentinel
    assert ctx["status"] == "not_supported"
