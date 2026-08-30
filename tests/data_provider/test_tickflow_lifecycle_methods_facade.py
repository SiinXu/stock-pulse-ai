# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for TickFlow lifecycle extraction."""

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
import src.data_provider.manager_parts.tickflow_lifecycle_methods as tickflow_lifecycle
from src.data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "tickflow_lifecycle_methods.py"
)

INSTANCE_NAMES = (
    "_get_tickflow_fetcher",
    "close",
)


class _DummyTickFlowFetcher:
    def __init__(self) -> None:
        self.closed = False
        self.close_calls = 0
        self.close_error: Exception | None = None

    def close(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def _bare_manager() -> DataFetcherManager:
    manager = DataFetcherManager.__new__(DataFetcherManager)
    manager._tickflow_fetcher = None
    manager._tickflow_api_key = None
    manager._tickflow_lock = None
    return manager


def test_tickflow_lifecycle_methods_remain_on_data_fetcher_manager_facade() -> None:
    for name in tickflow_lifecycle.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_tickflow_lifecycle_signatures_and_descriptor_kinds_are_unchanged() -> None:
    expected = {
        "_get_tickflow_fetcher": ["self"],
        "close": ["self"],
    }
    for name in tickflow_lifecycle.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES:
        descriptor = vars(DataFetcherManager)[name]
        source_descriptor = vars(tickflow_lifecycle._TickFlowLifecycleMethods)[name]
        assert name in INSTANCE_NAMES
        assert not isinstance(descriptor, (staticmethod, classmethod)), name
        assert not isinstance(source_descriptor, (staticmethod, classmethod)), name
        signature = inspect.signature(getattr(DataFetcherManager, name))
        assert list(signature.parameters) == expected[name], name
        for parameter in signature.parameters.values():
            assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name
        if name == "close":
            assert signature.return_annotation in {None, "None"}


def test_moved_names_are_not_validation_wrapped() -> None:
    for name in tickflow_lifecycle.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES:
        method = DataFetcherManager.__dict__[name]
        assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_owner_module_exists_for_tickflow_lifecycle_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "tickflow_lifecycle_methods" in source
    assert "bind_tickflow_lifecycle_methods_facade" in source
    for name in tickflow_lifecycle.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES:
        assert f"def {name}(" not in source
        assert f"    {name} = None" in source
    assert "def __del__(" in source
    importlib.import_module(
        "src.data_provider.manager_parts.tickflow_lifecycle_methods"
    )


def test_tickflow_lifecycle_bodies_leave_manager_and_stay_callable_on_facade() -> None:
    tree = ast.parse(BASE_PATH.read_text(encoding="utf-8"))
    manager_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "DataFetcherManager"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in tickflow_lifecycle.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES:
        assert name not in manager_defs, name
        assert callable(getattr(DataFetcherManager, name)), name
    assert "__del__" in manager_defs


def test_tickflow_lifecycle_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(
        tickflow_lifecycle._TickFlowLifecycleMethods
    ).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == tickflow_lifecycle.__name__
    assert tuple(source_names) == tickflow_lifecycle.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES


def test_tickflow_lifecycle_placeholders_preserve_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    expected = tickflow_lifecycle.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES
    assert names.index("_cache_stock_name") < names.index("_get_tickflow_fetcher")
    for left, right in zip(expected, expected[1:]):
        assert names.index(left) < names.index(right)
    assert names.index("close") < names.index("__del__")


def test_bind_returns_expected_names_in_class_body_order() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    bound = tickflow_lifecycle.bind_tickflow_lifecycle_methods_facade(
        dummy,
        vars(base),
    )
    assert bound == tickflow_lifecycle.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES


def test_assemble_raises_import_error_on_expected_name_mismatch() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    extra = lambda self: None  # noqa: E731
    tickflow_lifecycle._TickFlowLifecycleMethods._extra_lifecycle = extra
    try:
        bound = tickflow_lifecycle.bind_tickflow_lifecycle_methods_facade(
            dummy,
            vars(base),
        )
        with pytest.raises(
            ImportError,
            match="Unexpected DataFetcherManager TickFlow lifecycle methods",
        ):
            if bound != tickflow_lifecycle.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES:
                raise ImportError(
                    "Unexpected DataFetcherManager TickFlow lifecycle methods: "
                    f"{bound!r}"
                )
        assert "_extra_lifecycle" in bound
    finally:
        delattr(tickflow_lifecycle._TickFlowLifecycleMethods, "_extra_lifecycle")


def test_owner_module_declares_expected_names_only() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_TickFlowLifecycleMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(tickflow_lifecycle.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES)


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
                    "import src.data_provider.manager_parts.tickflow_lifecycle_methods as tickflow_lifecycle",
                    "",
                    "names = tickflow_lifecycle.EXPECTED_TICKFLOW_LIFECYCLE_METHOD_NAMES",
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
                    "            vars(tickflow_lifecycle._TickFlowLifecycleMethods)[name]",
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
tickflow_lifecycle = importlib.reload(tickflow_lifecycle)
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
tickflow_lifecycle = importlib.reload(tickflow_lifecycle)
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


def test_empty_api_key_returns_none_and_closes_stale_fetcher() -> None:
    manager = _bare_manager()
    stale = _DummyTickFlowFetcher()
    manager._tickflow_fetcher = stale
    manager._tickflow_api_key = "old-key"
    manager._get_fundamental_config = lambda: SimpleNamespace(tickflow_api_key="")

    result = DataFetcherManager._get_tickflow_fetcher(manager)

    assert result is None
    assert stale.closed
    assert manager._tickflow_fetcher is None
    assert manager._tickflow_api_key is None
    assert manager._tickflow_lock is not None


def test_empty_api_key_swallows_stale_close_failure() -> None:
    manager = _bare_manager()
    stale = _DummyTickFlowFetcher()
    stale.close_error = RuntimeError("stale close boom")
    manager._tickflow_fetcher = stale
    manager._tickflow_api_key = "old-key"
    manager._get_fundamental_config = lambda: SimpleNamespace(tickflow_api_key=None)

    result = DataFetcherManager._get_tickflow_fetcher(manager)

    assert result is None
    assert stale.close_calls == 1
    assert manager._tickflow_fetcher is None
    assert manager._tickflow_api_key is None


def test_registry_hit_wins_over_lazy_tickflow_fetcher() -> None:
    manager = _bare_manager()
    registry = object()
    current = _DummyTickFlowFetcher()
    manager._tickflow_fetcher = current
    manager._tickflow_api_key = "tf-secret"
    manager._get_fundamental_config = lambda: SimpleNamespace(tickflow_api_key="tf-secret")
    manager._get_fetcher_by_name = lambda name: registry if name == "TickFlowFetcher" else None

    result = DataFetcherManager._get_tickflow_fetcher(manager)

    assert result is registry
    assert current.close_calls == 0
    assert manager._tickflow_fetcher is current


def test_same_key_reuses_current_fetcher() -> None:
    manager = _bare_manager()
    current = _DummyTickFlowFetcher()
    manager._tickflow_fetcher = current
    manager._tickflow_api_key = "tf-secret"
    manager._get_fundamental_config = lambda: SimpleNamespace(tickflow_api_key="tf-secret")
    manager._get_fetcher_by_name = lambda name: None

    result = DataFetcherManager._get_tickflow_fetcher(manager)

    assert result is current
    assert current.close_calls == 0


def test_key_change_closes_previous_and_constructs_replacement() -> None:
    manager = _bare_manager()
    previous = _DummyTickFlowFetcher()
    replacement = object()
    manager._tickflow_fetcher = previous
    manager._tickflow_api_key = "old-key"
    manager._get_fetcher_by_name = lambda name: None
    config = SimpleNamespace(
        tickflow_api_key="new-key",
        tickflow_kline_adjust="forward",
        tickflow_batch_daily_enabled=False,
        tickflow_batch_size=50,
        tickflow_priority=7,
    )
    manager._get_fundamental_config = lambda: config

    with patch("src.data_provider.tickflow_fetcher.TickFlowFetcher") as constructed:
        constructed.return_value = replacement
        result = DataFetcherManager._get_tickflow_fetcher(manager)

    assert result is replacement
    assert previous.closed
    constructed.assert_called_once_with(
        api_key="new-key",
        kline_adjust="forward",
        batch_daily_enabled=False,
        batch_size=50,
        priority=7,
    )
    assert manager._tickflow_fetcher is replacement
    assert manager._tickflow_api_key == "new-key"


def test_construct_failure_clears_handles_and_returns_none() -> None:
    manager = _bare_manager()
    manager._get_fetcher_by_name = lambda name: None
    manager._get_fundamental_config = lambda: SimpleNamespace(
        tickflow_api_key="tf-secret",
        tickflow_kline_adjust="none",
        tickflow_batch_daily_enabled=True,
        tickflow_batch_size=100,
        tickflow_priority=2,
    )

    with patch(
        "src.data_provider.tickflow_fetcher.TickFlowFetcher",
        side_effect=RuntimeError("init boom"),
    ):
        result = DataFetcherManager._get_tickflow_fetcher(manager)

    assert result is None
    assert manager._tickflow_fetcher is None
    assert manager._tickflow_api_key is None


def test_close_clears_handles_and_is_best_effort() -> None:
    manager = _bare_manager()
    current = _DummyTickFlowFetcher()
    current.close_error = RuntimeError("close boom")
    manager._tickflow_fetcher = current
    manager._tickflow_api_key = "tf-secret"

    DataFetcherManager.close(manager)

    assert current.close_calls == 1
    assert manager._tickflow_fetcher is None
    assert manager._tickflow_api_key is None
    assert manager._tickflow_lock is not None


def test_facade_del_still_calls_rebound_close() -> None:
    function = _descriptor_function(vars(DataFetcherManager)["__del__"])
    assert inspect.isfunction(function)
    assert function.__module__ == "src.data_provider.base"
    assert function.__qualname__ == "DataFetcherManager.__del__"
    source = inspect.getsource(function)
    assert "self.close()" in source
    assert "except Exception" in source
