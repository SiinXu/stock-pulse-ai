# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and circuit-parity guards for daily execution extraction."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pandas as pd

import src.data_provider.base as base
import src.data_provider.manager_parts.daily_provider_execution as daily_execution
from src.data_provider.base import DataFetcherManager
from src.data_provider.realtime_types import CircuitBreaker


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "daily_provider_execution.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        descriptor = descriptor.__func__
    elif isinstance(descriptor, property):
        descriptor = descriptor.fget
    original = getattr(descriptor, "_stockpulse_data_validation_original", None)
    return original if original is not None else descriptor


def _daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-07-20"],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "close": [10.2],
            "volume": [1000],
            "amount": [10200],
            "pct_chg": [2.0],
        }
    )


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _SequencedProvider:
    def __init__(self, name: str, priority: int, outcomes: list[object]) -> None:
        self.name = name
        self.priority = priority
        self.outcomes = list(outcomes)
        self.calls = 0

    def get_daily_data(self, **_kwargs) -> Optional[pd.DataFrame]:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome is None:
            return None
        assert isinstance(outcome, pd.DataFrame)
        return outcome.copy(deep=True)


def test_daily_execution_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = daily_execution.EXPECTED_DAILY_PROVIDER_EXECUTION_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_public_get_daily_data_signature_is_unchanged() -> None:
    signature = inspect.signature(DataFetcherManager.get_daily_data)
    assert list(signature.parameters) == [
        "self",
        "stock_code",
        "start_date",
        "end_date",
        "days",
    ]
    assert signature.parameters["start_date"].default is None
    assert signature.parameters["end_date"].default is None
    assert signature.parameters["days"].default == 30


def test_get_daily_data_final_exit_keeps_validation_wrapper() -> None:
    method = DataFetcherManager.__dict__["get_daily_data"]
    assert getattr(method, "_stockpulse_data_validation_wrapper_token", None) is not None
    original = getattr(method, "_stockpulse_data_validation_original")
    source = _descriptor_function(
        vars(daily_execution._DailyProviderExecutionMethods)["get_daily_data"]
    )
    assert original is not source
    assert original.__code__ is source.__code__


def test_owner_module_exists_for_daily_execution_extraction() -> None:
    assert OWNER_PATH.is_file()
    source = BASE_PATH.read_text(encoding="utf-8")
    assert "daily_provider_execution" in source
    assert "bind_daily_provider_execution_facade" in source
    assert "def _get_daily_data_from_providers(" not in source
    importlib.import_module("src.data_provider.manager_parts.daily_provider_execution")


def test_daily_execution_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(
        daily_execution._DailyProviderExecutionMethods
    ).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == daily_execution.__name__
    assert tuple(source_names) == daily_execution.EXPECTED_DAILY_PROVIDER_EXECUTION_METHOD_NAMES


def test_facade_patch_seam_intercepts_daily_provider_loop() -> None:
    sentinel = (_daily_frame(), "PatchedFetcher")
    manager = DataFetcherManager(fetchers=[])
    with patch.object(
        DataFetcherManager,
        "_get_daily_data_from_providers",
        return_value=sentinel,
    ) as mocked:
        frame, source = manager.get_daily_data("600519")
    assert source == "PatchedFetcher"
    assert list(frame["close"]) == [10.2]
    mocked.assert_called_once()


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.daily_provider_execution as daily_execution",
                    "",
                    "names = daily_execution.EXPECTED_DAILY_PROVIDER_EXECUTION_METHOD_NAMES",
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
                    "            vars(daily_execution._DailyProviderExecutionMethods)[name]",
                    "        )",
                    "        facade[name] = descriptor_function(",
                    "            vars(base.DataFetcherManager)[name]",
                    "        )",
                    "        assert facade[name] is not source[name]",
                    "        assert facade[name].__code__ is source[name].__code__",
                    "        assert facade[name].__globals__ is vars(base)",
                    "        assert facade[name].__module__ == 'src.data_provider.base'",
                    "        assert facade[name].__qualname__ == f'DataFetcherManager.{name}'",
                    "    daily = vars(base.DataFetcherManager)['get_daily_data']",
                    "    assert getattr(",
                    "        daily,",
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
daily_execution = importlib.reload(daily_execution)
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
daily_execution = importlib.reload(daily_execution)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_circuit_skip_parity_through_rebound_get_daily_data() -> None:
    clock = _Clock()
    breaker = CircuitBreaker(
        failure_threshold=2,
        cooldown_seconds=30.0,
        health_window_size=8,
        clock=clock,
    )
    primary = _SequencedProvider(
        "EfinanceFetcher",
        0,
        [TimeoutError("credential=must-not-leak"), TimeoutError("still down"), _daily_frame()],
    )
    backup = _SequencedProvider(
        "TencentFetcher",
        1,
        [_daily_frame(), _daily_frame(), _daily_frame()],
    )
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", breaker):
        for _ in range(2):
            frame, source = manager.get_daily_data("600519")
            assert not frame.empty
            assert source == "TencentFetcher"

        health_key = DataFetcherManager._daily_health_key(primary, "cn")
        assert breaker.get_status()[health_key] == CircuitBreaker.OPEN

        frame, source = manager.get_daily_data("600519")
        assert source == "TencentFetcher"
        assert primary.calls == 2

        clock.advance(30.0)
        frame, source = manager.get_daily_data("600519")
        assert source == "EfinanceFetcher"
        assert primary.calls == 3
        snapshot = DataFetcherManager.get_daily_source_health_snapshot()[health_key]
        assert snapshot["state"] == CircuitBreaker.CLOSED
        assert snapshot["consecutive_failures"] == 0


def test_package_export_still_exposes_data_fetcher_manager() -> None:
    from src.data_provider import DataFetcherManager as PackageManager

    assert PackageManager is DataFetcherManager
    assert inspect.isclass(PackageManager)
