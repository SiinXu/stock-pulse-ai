# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for prefetch extraction."""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.data_provider.base as base
import src.data_provider.manager_parts.prefetch_methods as prefetch
from src.data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "prefetch_methods.py"
)

INSTANCE_NAMES = (
    "prefetch_realtime_quotes",
    "prefetch_daily_klines",
)
FIVE_CODES = ["600519", "000001", "300750", "000858", "601318"]


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def _bare_manager() -> DataFetcherManager:
    return DataFetcherManager.__new__(DataFetcherManager)


def _realtime_config(**overrides):
    payload = {
        "prefetch_realtime_quotes": True,
        "enable_realtime_quote": True,
        "realtime_source_priority": "efinance,tencent",
        "tickflow_batch_size": 50,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class _FakeTickFlowFetcher:
    def __init__(self) -> None:
        self.quote_calls: list[tuple] = []
        self.daily_calls: list[tuple] = []
        self.quote_error: Exception | None = None
        self.daily_error: Exception | None = None

    def prefetch_realtime_quotes(self, stock_codes, batch_size=None):
        if self.quote_error is not None:
            raise self.quote_error
        self.quote_calls.append((list(stock_codes), batch_size))
        return len(stock_codes)

    def prefetch_daily_klines(self, stock_codes, days=30):
        if self.daily_error is not None:
            raise self.daily_error
        self.daily_calls.append((list(stock_codes), days))
        return len(stock_codes)


def test_prefetch_methods_remain_on_data_fetcher_manager_facade() -> None:
    for name in prefetch.EXPECTED_PREFETCH_METHOD_NAMES:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_prefetch_signatures_and_descriptor_kinds_are_unchanged() -> None:
    expected = {
        "prefetch_realtime_quotes": ["self", "stock_codes"],
        "prefetch_daily_klines": ["self", "stock_codes", "days"],
    }
    for name in prefetch.EXPECTED_PREFETCH_METHOD_NAMES:
        descriptor = vars(DataFetcherManager)[name]
        source_descriptor = vars(prefetch._PrefetchMethods)[name]
        assert name in INSTANCE_NAMES
        assert not isinstance(descriptor, (staticmethod, classmethod)), name
        assert not isinstance(source_descriptor, (staticmethod, classmethod)), name
        signature = inspect.signature(getattr(DataFetcherManager, name))
        assert list(signature.parameters) == expected[name], name
        for parameter in signature.parameters.values():
            assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name
        assert signature.return_annotation in {int, "int"}
    days = inspect.signature(DataFetcherManager.prefetch_daily_klines).parameters["days"]
    assert days.default == 30


def test_moved_names_are_not_validation_wrapped() -> None:
    for name in prefetch.EXPECTED_PREFETCH_METHOD_NAMES:
        method = DataFetcherManager.__dict__[name]
        assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_owner_module_exists_for_prefetch_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "prefetch_methods" in source
    assert "bind_prefetch_methods_facade" in source
    for name in prefetch.EXPECTED_PREFETCH_METHOD_NAMES:
        assert f"def {name}(" not in source
        assert f"    {name} = None" in source
    assert "def _init_default_fetchers(" in source
    assert "def __init__(" in source
    assert "def __del__(" in source
    importlib.import_module("src.data_provider.manager_parts.prefetch_methods")


def test_prefetch_bodies_leave_manager_and_stay_callable_on_facade() -> None:
    tree = ast.parse(BASE_PATH.read_text(encoding="utf-8"))
    manager_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "DataFetcherManager"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in prefetch.EXPECTED_PREFETCH_METHOD_NAMES:
        assert name not in manager_defs, name
        assert callable(getattr(DataFetcherManager, name)), name
    assert "_init_default_fetchers" in manager_defs
    assert "__init__" in manager_defs
    assert "__del__" in manager_defs


def test_prefetch_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(prefetch._PrefetchMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == prefetch.__name__
    assert tuple(source_names) == prefetch.EXPECTED_PREFETCH_METHOD_NAMES


def test_prefetch_placeholders_preserve_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    expected = prefetch.EXPECTED_PREFETCH_METHOD_NAMES
    assert names.index("available_fetchers") < names.index("prefetch_realtime_quotes")
    for left, right in zip(expected, expected[1:]):
        assert names.index(left) < names.index(right)
    assert names.index("prefetch_daily_klines") < names.index("_SUPPLEMENT_FIELDS")


def test_bind_returns_expected_names_in_class_body_order() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    bound = prefetch.bind_prefetch_methods_facade(
        dummy,
        vars(base),
    )
    assert bound == prefetch.EXPECTED_PREFETCH_METHOD_NAMES


def test_assemble_raises_import_error_on_expected_name_mismatch() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    extra = lambda self: 0  # noqa: E731
    prefetch._PrefetchMethods._extra_prefetch = extra
    try:
        bound = prefetch.bind_prefetch_methods_facade(
            dummy,
            vars(base),
        )
        with pytest.raises(
            ImportError,
            match="Unexpected DataFetcherManager prefetch methods",
        ):
            if bound != prefetch.EXPECTED_PREFETCH_METHOD_NAMES:
                raise ImportError(
                    "Unexpected DataFetcherManager prefetch methods: "
                    f"{bound!r}"
                )
        assert "_extra_prefetch" in bound
    finally:
        delattr(prefetch._PrefetchMethods, "_extra_prefetch")


def test_owner_module_declares_expected_names_only() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_PrefetchMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(prefetch.EXPECTED_PREFETCH_METHOD_NAMES)


def test_owner_module_has_zero_bare_get_config_and_forbidden_imports() -> None:
    source = OWNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_prefixes = (
        "src.config",
        "src.core",
        "src.services",
        "src.data_provider.base",
    )
    assert "from src.config import get_config" not in source
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
                    "import src.data_provider.manager_parts.prefetch_methods as prefetch",
                    "",
                    "names = prefetch.EXPECTED_PREFETCH_METHOD_NAMES",
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
                    "            vars(prefetch._PrefetchMethods)[name]",
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
prefetch = importlib.reload(prefetch)
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
prefetch = importlib.reload(prefetch)
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


def test_realtime_prefetch_uses_facade_normalize_stock_code_patch() -> None:
    manager = _bare_manager()
    manager.is_market_data_local_only = lambda: False
    manager._get_fundamental_config = lambda: _realtime_config()
    seen: list[str] = []

    def _quote(code: str):
        seen.append(code)
        return {"price": 1}

    manager.get_realtime_quote = _quote
    with patch.object(base, "normalize_stock_code", return_value="600519") as mocked:
        count = DataFetcherManager.prefetch_realtime_quotes(
            manager,
            ["SH600519", "000001", "300750", "000858", "601318"],
        )
    assert mocked.call_count == 5
    mocked.assert_any_call("SH600519")
    assert seen == ["600519"]
    assert count == 5


def test_realtime_prefetch_skips_when_local_only() -> None:
    manager = _bare_manager()
    manager.is_market_data_local_only = lambda: True
    manager._get_fundamental_config = lambda: (_ for _ in ()).throw(
        AssertionError("local_only must not read config")
    )
    assert DataFetcherManager.prefetch_realtime_quotes(manager, FIVE_CODES) == 0


def test_realtime_prefetch_skips_when_disabled_or_realtime_off() -> None:
    manager = _bare_manager()
    manager.is_market_data_local_only = lambda: False
    manager._get_fundamental_config = lambda: _realtime_config(
        prefetch_realtime_quotes=False
    )
    assert DataFetcherManager.prefetch_realtime_quotes(manager, FIVE_CODES) == 0

    manager._get_fundamental_config = lambda: _realtime_config(
        enable_realtime_quote=False
    )
    assert DataFetcherManager.prefetch_realtime_quotes(manager, FIVE_CODES) == 0


def test_realtime_prefetch_skips_without_early_source_or_small_batch() -> None:
    manager = _bare_manager()
    manager.is_market_data_local_only = lambda: False
    manager._get_fundamental_config = lambda: _realtime_config(
        realtime_source_priority="tencent,akshare_sina,efinance"
    )
    assert DataFetcherManager.prefetch_realtime_quotes(manager, FIVE_CODES) == 0

    manager._get_fundamental_config = lambda: _realtime_config()
    assert DataFetcherManager.prefetch_realtime_quotes(manager, FIVE_CODES[:4]) == 0


def test_tickflow_realtime_prefetch_uses_batch_and_swallows_failure() -> None:
    manager = _bare_manager()
    fetcher = _FakeTickFlowFetcher()
    manager.is_market_data_local_only = lambda: False
    manager._get_fundamental_config = lambda: _realtime_config(
        realtime_source_priority="tickflow,tencent"
    )
    manager._get_fetcher_by_name = (
        lambda name, capability=None: fetcher if name == "TickFlowFetcher" else None
    )
    manager._call_fetcher_method = lambda target, method, *args, **kwargs: getattr(
        target, method
    )(*args, **kwargs)

    count = DataFetcherManager.prefetch_realtime_quotes(manager, FIVE_CODES)
    assert count == 5
    assert fetcher.quote_calls == [(FIVE_CODES, 50)]

    fetcher.quote_error = RuntimeError("tickflow boom")
    assert DataFetcherManager.prefetch_realtime_quotes(manager, FIVE_CODES) == 0


def test_realtime_prefetch_first_quote_failure_falls_back_to_zero() -> None:
    manager = _bare_manager()
    manager.is_market_data_local_only = lambda: False
    manager._get_fundamental_config = lambda: _realtime_config()
    manager.get_realtime_quote = lambda code: None
    assert DataFetcherManager.prefetch_realtime_quotes(manager, FIVE_CODES) == 0

    def _raise(_code: str):
        raise RuntimeError("quote boom")

    manager.get_realtime_quote = _raise
    assert DataFetcherManager.prefetch_realtime_quotes(manager, FIVE_CODES) == 0


def test_daily_prefetch_skips_local_only_and_missing_fetcher() -> None:
    manager = _bare_manager()
    manager.is_market_data_local_only = lambda: True
    called: list[str] = []
    manager._get_fetcher_by_name = lambda *args, **kwargs: called.append("hit")
    assert DataFetcherManager.prefetch_daily_klines(manager, FIVE_CODES) == 0
    assert called == []

    manager.is_market_data_local_only = lambda: False
    manager._get_fetcher_by_name = lambda *args, **kwargs: None
    assert DataFetcherManager.prefetch_daily_klines(manager, FIVE_CODES, days=10) == 0


def test_daily_prefetch_delegates_days_and_swallows_failure() -> None:
    manager = _bare_manager()
    fetcher = _FakeTickFlowFetcher()
    manager.is_market_data_local_only = lambda: False
    manager._get_fetcher_by_name = (
        lambda name, capability=None: fetcher if name == "TickFlowFetcher" else None
    )
    manager._call_fetcher_method = lambda target, method, *args, **kwargs: getattr(
        target, method
    )(*args, **kwargs)

    count = DataFetcherManager.prefetch_daily_klines(manager, FIVE_CODES[:2], days=12)
    assert count == 2
    assert fetcher.daily_calls == [(FIVE_CODES[:2], 12)]

    fetcher.daily_error = RuntimeError("daily boom")
    assert DataFetcherManager.prefetch_daily_klines(manager, FIVE_CODES[:2]) == 0
