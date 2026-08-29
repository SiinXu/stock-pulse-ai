# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and characterization for timeout/retry workers."""

from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from threading import BoundedSemaphore, Event
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import src.data_provider.base as base
import src.data_provider.manager_parts.fundamental_timeout_methods as timeout_methods
from src.data_provider.base import DataFetcherManager


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "fundamental_timeout_methods.py"
)

INSTANCE_NAMES = (
    "_run_with_timeout",
    "_run_with_retry",
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def test_timeout_methods_remain_on_data_fetcher_manager_facade() -> None:
    for name in timeout_methods.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_timeout_signatures_and_descriptor_kinds_are_unchanged() -> None:
    expected = {
        "_run_with_timeout": ["self", "task", "timeout_seconds", "task_name"],
        "_run_with_retry": ["self", "task", "timeout_seconds", "task_name"],
    }
    for name in timeout_methods.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES:
        descriptor = vars(DataFetcherManager)[name]
        source_descriptor = vars(timeout_methods._FundamentalTimeoutMethods)[name]
        assert name in INSTANCE_NAMES
        assert not isinstance(descriptor, (staticmethod, classmethod)), name
        assert not isinstance(source_descriptor, (staticmethod, classmethod)), name
        signature = inspect.signature(getattr(DataFetcherManager, name))
        assert list(signature.parameters) == expected[name], name
        for parameter in signature.parameters.values():
            assert parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, name


def test_moved_names_are_not_validation_wrapped() -> None:
    for name in timeout_methods.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES:
        method = DataFetcherManager.__dict__[name]
        assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is None


def test_owner_module_exists_for_timeout_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "fundamental_timeout_methods" in source
    assert "bind_fundamental_timeout_methods_facade" in source
    for name in timeout_methods.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES:
        assert f"def {name}(" not in source
        assert f"    {name} = None" in source
    importlib.import_module(
        "src.data_provider.manager_parts.fundamental_timeout_methods"
    )


def test_timeout_bodies_leave_manager_and_stay_callable_on_facade() -> None:
    tree = ast.parse(BASE_PATH.read_text(encoding="utf-8"))
    manager_defs = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "DataFetcherManager"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in timeout_methods.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES:
        assert name not in manager_defs, name
        assert callable(getattr(DataFetcherManager, name)), name


def test_timeout_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(
        timeout_methods._FundamentalTimeoutMethods
    ).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == timeout_methods.__name__
    assert tuple(source_names) == timeout_methods.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES


def test_timeout_placeholders_preserve_descriptor_order() -> None:
    names = list(vars(DataFetcherManager))
    expected = timeout_methods.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES
    assert names.index("get_market_stats") < names.index("_run_with_timeout")
    for left, right in zip(expected, expected[1:]):
        assert names.index(left) < names.index(right)
    assert names.index("_run_with_retry") < names.index("_get_fundamental_config")


def test_bind_returns_expected_names_in_class_body_order() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    bound = timeout_methods.bind_fundamental_timeout_methods_facade(
        dummy,
        vars(base),
    )
    assert bound == timeout_methods.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES


def test_assemble_raises_import_error_on_expected_name_mismatch() -> None:
    dummy = type("DummyDataFetcherManager", (), {})
    extra = lambda self: None  # noqa: E731
    timeout_methods._FundamentalTimeoutMethods._extra_timeout = extra
    try:
        bound = timeout_methods.bind_fundamental_timeout_methods_facade(
            dummy,
            vars(base),
        )
        with pytest.raises(
            ImportError,
            match="Unexpected DataFetcherManager fundamental timeout methods",
        ):
            if bound != timeout_methods.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES:
                raise ImportError(
                    "Unexpected DataFetcherManager fundamental timeout methods: "
                    f"{bound!r}"
                )
        assert "_extra_timeout" in bound
    finally:
        delattr(timeout_methods._FundamentalTimeoutMethods, "_extra_timeout")


def test_owner_module_declares_expected_names_only() -> None:
    tree = ast.parse(OWNER_PATH.read_text(encoding="utf-8"))
    defined = {
        node.name
        for cls in tree.body
        if isinstance(cls, ast.ClassDef) and cls.name == "_FundamentalTimeoutMethods"
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert defined == set(timeout_methods.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES)


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
                    "import src.data_provider.manager_parts.fundamental_timeout_methods as timeout_methods",
                    "",
                    "names = timeout_methods.EXPECTED_FUNDAMENTAL_TIMEOUT_METHOD_NAMES",
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
                    "            vars(timeout_methods._FundamentalTimeoutMethods)[name]",
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
timeout_methods = importlib.reload(timeout_methods)
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
timeout_methods = importlib.reload(timeout_methods)
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


def test_zero_timeout_does_not_start_thread_or_acquire_slot() -> None:
    manager = DataFetcherManager(fetchers=[])
    manager._fundamental_timeout_slots = BoundedSemaphore(1)
    started = []

    class RecordingThread:
        def __init__(self, *args, **kwargs):
            started.append(kwargs.get("name"))

        def start(self):
            raise AssertionError("zero timeout must not start a thread")

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return False

    with patch.object(base, "Thread", RecordingThread):
        result, err, duration_ms = manager._run_with_timeout(lambda: 1, 0, "hang")
    assert result is None
    assert err == "hang timeout"
    assert duration_ms == 0
    assert started == []

    unblock = Event()

    def _hanging_task():
        unblock.wait(timeout=0.5)
        return 1

    try:
        result2, err2, _ = manager._run_with_timeout(_hanging_task, 0.01, "hang")
        assert result2 is None
        assert "timeout" in (err2 or "")
        assert "worker pool exhausted" not in (err2 or "")
    finally:
        unblock.set()


def test_successful_task_returns_value_and_no_error() -> None:
    manager = DataFetcherManager(fetchers=[])
    result, err, duration_ms = manager._run_with_timeout(lambda: 42, 1.0, "ok")
    assert result == 42
    assert err is None
    assert duration_ms >= 0


def test_task_exception_releases_slot_for_later_acquire() -> None:
    manager = DataFetcherManager(fetchers=[])
    manager._fundamental_timeout_slots = BoundedSemaphore(1)

    def _boom():
        raise RuntimeError("task failed")

    result, err, duration_ms = manager._run_with_timeout(_boom, 1.0, "boom")
    assert result is None
    assert err == "task failed"
    assert duration_ms >= 0
    result2, err2, _ = manager._run_with_timeout(lambda: "ok", 1.0, "ok")
    assert result2 == "ok"
    assert err2 is None


def test_worker_start_failure_releases_slot() -> None:
    manager = DataFetcherManager(fetchers=[])
    manager._fundamental_timeout_slots = BoundedSemaphore(1)

    class FailingThread:
        def __init__(self, *args, **kwargs):
            return None

        def start(self):
            raise RuntimeError("cannot start")

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return False

    with patch.object(base, "Thread", FailingThread):
        result, err, duration_ms = manager._run_with_timeout(lambda: 1, 1.0, "startfail")
    assert result is None
    assert err == "cannot start"
    assert duration_ms >= 0
    result2, err2, _ = manager._run_with_timeout(lambda: "recovered", 1.0, "ok")
    assert result2 == "recovered"
    assert err2 is None


def test_retry_max_one_calls_timeout_once_on_fast_error() -> None:
    manager = DataFetcherManager(fetchers=[])
    cfg = SimpleNamespace(fundamental_retry_max=1)
    with patch.object(
        DataFetcherManager, "_get_fundamental_config", return_value=cfg
    ), patch.object(
        DataFetcherManager,
        "_run_with_timeout",
        return_value=(None, "boom", 5),
    ) as timeout_spy:
        result, err, duration_ms = manager._run_with_retry(lambda: None, 10.0, "x")
    assert result is None
    assert err == "boom"
    assert duration_ms == 5
    assert timeout_spy.call_count == 1


def test_retry_max_two_retries_fast_error_while_budget_remains() -> None:
    manager = DataFetcherManager(fetchers=[])
    cfg = SimpleNamespace(fundamental_retry_max=2)
    with patch.object(
        DataFetcherManager, "_get_fundamental_config", return_value=cfg
    ), patch.object(
        DataFetcherManager,
        "_run_with_timeout",
        return_value=(None, "boom", 5),
    ) as timeout_spy:
        result, err, duration_ms = manager._run_with_retry(lambda: None, 10.0, "x")
    assert result is None
    assert err == "boom"
    assert duration_ms == 10
    assert timeout_spy.call_count == 2


def test_retry_hang_timeout_does_not_start_a_second_attempt() -> None:
    manager = DataFetcherManager(fetchers=[])
    cfg = SimpleNamespace(fundamental_retry_max=2)
    unblock = Event()
    calls: list[int] = []

    def _hanging_task():
        calls.append(1)
        unblock.wait(timeout=0.5)
        return 1

    try:
        with patch.object(DataFetcherManager, "_get_fundamental_config", return_value=cfg):
            result, err, _ = manager._run_with_retry(_hanging_task, 0.01, "hang")
        assert result is None
        assert "timeout" in (err or "")
        assert len(calls) == 1
    finally:
        unblock.set()


def test_get_fundamental_config_patch_is_honored_by_retry() -> None:
    manager = DataFetcherManager(fetchers=[])
    cfg = SimpleNamespace(fundamental_retry_max=3)
    with patch.object(
        DataFetcherManager, "_get_fundamental_config", return_value=cfg
    ) as cfg_spy, patch.object(
        DataFetcherManager,
        "_run_with_timeout",
        return_value=(None, "boom", 1),
    ) as timeout_spy:
        manager._run_with_retry(lambda: 1, 10.0, "x")
    cfg_spy.assert_called()
    assert timeout_spy.call_count == 3


def test_run_with_timeout_patch_is_honored_by_retry() -> None:
    manager = DataFetcherManager(fetchers=[])
    sentinel = object()
    cfg = SimpleNamespace(fundamental_retry_max=1)
    with patch.object(
        DataFetcherManager, "_get_fundamental_config", return_value=cfg
    ), patch.object(
        DataFetcherManager,
        "_run_with_timeout",
        return_value=(sentinel, None, 7),
    ) as timeout_spy:
        result, err, duration_ms = manager._run_with_retry(lambda: None, 4.0, "named")
    timeout_spy.assert_called_once()
    assert timeout_spy.call_args.args[1:] == (4.0, "named")
    assert result is sentinel
    assert err is None
    assert duration_ms == 7
