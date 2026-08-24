# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fundamental aggregation cache as_of + in-flight coalesce (issue #1292 slice 3)."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import patch

import src.data_provider.base as base
import src.data_provider.manager_parts.fundamental_cache_methods as fundamental_cache
from src.data_provider.base import DataFetcherManager
from src.data_provider.pull_coalesce import get_provider_pull_coalesce


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "fundamental_cache_methods.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


class _Clock:
    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def tick(self, seconds: float) -> None:
        self.value += seconds


class _Wall:
    def __init__(self, start: Optional[datetime] = None) -> None:
        self.value = start or datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def tick(self, seconds: float) -> None:
        self.value = self.value + timedelta(seconds=seconds)


class _RecordingLoader:
    def __init__(
        self,
        result: Any = None,
        *,
        error: Optional[BaseException] = None,
        delay_event: Optional[threading.Event] = None,
        release_event: Optional[threading.Event] = None,
    ) -> None:
        self.result = result if result is not None else _ok_context()
        self.error = error
        self.delay_event = delay_event
        self.release_event = release_event
        self.calls = 0
        self._lock = threading.Lock()
        self.owner_ids: List[int] = []

    def __call__(self) -> Any:
        with self._lock:
            self.calls += 1
            self.owner_ids.append(id(self.result))
        if self.delay_event is not None:
            self.delay_event.set()
        if self.release_event is not None:
            self.release_event.wait(timeout=5.0)
        if self.error is not None:
            raise self.error
        return self.result


def _ok_context(*, label: str = "ok") -> dict:
    return {
        "status": "ok",
        "label": label,
        "valuation": {"data": {"pe_ratio": 12.0}},
        "growth": {"data": {"revenue_yoy": 1.0}},
        "earnings": {"data": {}},
        "institution": {"data": {}},
        "capital_flow": {"data": {}},
        "dragon_tiger": {"data": {}},
        "boards": {"data": {}},
    }


def _failed_context() -> dict:
    return {
        "status": "failed",
        "valuation": {"data": {}},
        "growth": {"data": {}},
        "earnings": {"data": {}},
        "institution": {"data": {}},
        "capital_flow": {"data": {}},
        "dragon_tiger": {"data": {}},
        "boards": {"data": {}},
    }


def _manager() -> DataFetcherManager:
    manager = DataFetcherManager(fetchers=[])
    manager._fundamental_cache_clock = _Clock()
    manager._fundamental_cache_wall_clock = _Wall()
    return manager


def _load(
    manager: DataFetcherManager,
    loader,
    *,
    stock_code: str = "600519",
    budget_seconds: float = 1.5,
    market: str = "cn",
    cache_ttl: int = 120,
    cache_max_entries: int = 256,
):
    return manager._get_or_load_fundamental_context(
        stock_code,
        budget_seconds,
        loader,
        market=market,
        cache_ttl=cache_ttl,
        cache_max_entries=cache_max_entries,
    )


def _cn_cfg(*, ttl: int = 120) -> SimpleNamespace:
    return SimpleNamespace(
        enable_fundamental_pipeline=True,
        fundamental_cache_ttl_seconds=ttl,
        fundamental_stage_timeout_seconds=1.5,
        fundamental_fetch_timeout_seconds=0.8,
        fundamental_retry_max=1,
        fundamental_cache_max_entries=256,
    )


def _ok_bundle() -> dict:
    return {
        "status": "ok",
        "growth": {"revenue_yoy": 10.1, "net_profit_yoy": 8.5},
        "earnings": {"forecast_summary": "预增"},
        "institution": {"institution_holding_change": 1.2},
        "source_chain": ["growth:akshare"],
        "errors": [],
    }


def _ok_quote():
    return SimpleNamespace(
        pe_ratio=12.3,
        pb_ratio=2.1,
        total_mv=1.0e11,
        circ_mv=7.0e10,
        source=SimpleNamespace(value="tencent"),
    )


def test_fundamental_cache_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = fundamental_cache.EXPECTED_FUNDAMENTAL_CACHE_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_owner_module_exists_for_fundamental_cache_extraction() -> None:
    assert OWNER_PATH.is_file()
    assert "fundamental_cache_methods" in BASE_PATH.read_text(encoding="utf-8")
    importlib.import_module("src.data_provider.manager_parts.fundamental_cache_methods")


def test_fundamental_cache_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(fundamental_cache._FundamentalCacheMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == fundamental_cache.__name__
    assert tuple(source_names) == fundamental_cache.EXPECTED_FUNDAMENTAL_CACHE_METHOD_NAMES


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.fundamental_cache_methods as fundamental_cache",
                    "",
                    "names = fundamental_cache.EXPECTED_FUNDAMENTAL_CACHE_METHOD_NAMES",
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
                    "            vars(fundamental_cache._FundamentalCacheMethods)[name]",
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
fundamental_cache = importlib.reload(fundamental_cache)
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
fundamental_cache = importlib.reload(fundamental_cache)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_cache_key_includes_as_of_market_and_budget() -> None:
    manager = _manager()
    key = manager._get_fundamental_cache_key(
        "600519",
        1.5,
        market="cn",
        ttl_seconds=120,
    )
    assert "600519" in key
    assert "market=cn" in key
    assert "budget=15" in key
    assert "as_of=" in key


def test_ttl_hit_inside_window_and_miss_after_expiry() -> None:
    manager = _manager()
    loader = _RecordingLoader()
    first = _load(manager, loader)
    second = _load(manager, loader)
    assert loader.calls == 1
    assert first == second
    manager._fundamental_cache_clock.tick(121)
    third = _load(manager, loader)
    assert loader.calls == 2
    assert third["status"] == "ok"


def test_as_of_bucket_advance_misses_while_ttl_not_expired() -> None:
    manager = _manager()
    loader = _RecordingLoader()
    _load(manager, loader)
    assert loader.calls == 1
    manager._fundamental_cache_wall_clock.tick(120)
    manager._fundamental_cache_clock.tick(1)
    _load(manager, loader)
    assert loader.calls == 2


def test_budget_bucket_still_isolates_after_as_of() -> None:
    manager = _manager()
    loader = _RecordingLoader()
    _load(manager, loader, budget_seconds=0.4)
    _load(manager, loader, budget_seconds=1.5)
    assert loader.calls == 2


def test_concurrent_same_key_coalesces_to_one_load() -> None:
    manager = _manager()
    started = threading.Event()
    release = threading.Event()
    loader = _RecordingLoader(delay_event=started, release_event=release)
    results: List[Any] = [None, None, None]
    errors: List[BaseException] = []

    def _worker(index: int) -> None:
        try:
            results[index] = _load(manager, loader)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(index,)) for index in range(3)]
    for thread in threads:
        thread.start()
    assert started.wait(timeout=2.0)
    release.set()
    for thread in threads:
        thread.join(timeout=5.0)

    assert errors == []
    assert loader.calls == 1
    assert results[0]["status"] == "ok"
    assert results[1]["status"] == "ok"
    assert results[2]["status"] == "ok"
    assert results[1] is not results[0]
    assert results[2] is not results[0]


def test_failed_context_is_not_cached() -> None:
    manager = _manager()
    loader = _RecordingLoader(result=_failed_context())
    first = _load(manager, loader)
    second = _load(manager, loader)
    assert first["status"] == "failed"
    assert second["status"] == "failed"
    assert loader.calls == 2


def test_owner_exception_unblocks_waiters_and_is_not_stored() -> None:
    manager = _manager()
    started = threading.Event()
    release = threading.Event()
    loader = _RecordingLoader(
        error=RuntimeError("adapter down"),
        delay_event=started,
        release_event=release,
    )
    errors: List[BaseException] = []

    def _worker() -> None:
        try:
            _load(manager, loader)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    assert started.wait(timeout=2.0)
    release.set()
    for thread in threads:
        thread.join(timeout=5.0)
    assert loader.calls == 1
    assert len(errors) == 2
    assert all(isinstance(exc, RuntimeError) for exc in errors)

    retry = _RecordingLoader(result=_ok_context())
    recovered = _load(manager, retry)
    assert retry.calls == 1
    assert recovered["status"] == "ok"


def test_cache_hit_and_waiters_return_deepcopy_owner_keeps_original() -> None:
    manager = _manager()
    payload = _ok_context(label="owner")
    loader = _RecordingLoader(result=payload)
    owner = _load(manager, loader)
    assert owner is payload
    hit = _load(manager, loader)
    assert hit is not payload
    hit["label"] = "mutated"
    again = _load(manager, loader)
    assert again["label"] == "owner"
    assert payload["label"] == "owner"


def test_ttl_zero_sequential_does_not_store() -> None:
    manager = _manager()
    loader = _RecordingLoader()
    _load(manager, loader, cache_ttl=0)
    _load(manager, loader, cache_ttl=0)
    assert loader.calls == 2


def test_ttl_zero_concurrent_still_coalesces_without_store() -> None:
    manager = _manager()
    started = threading.Event()
    release = threading.Event()
    loader = _RecordingLoader(delay_event=started, release_event=release)
    results: List[Any] = [None, None]

    def _worker(index: int) -> None:
        results[index] = _load(manager, loader, cache_ttl=0)

    threads = [threading.Thread(target=_worker, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    assert started.wait(timeout=2.0)
    release.set()
    for thread in threads:
        thread.join(timeout=5.0)
    assert loader.calls == 1
    assert results[0] is not results[1]
    later = _RecordingLoader()
    _load(manager, later, cache_ttl=0)
    assert later.calls == 1


def test_cn_and_offshore_paths_call_shared_helper() -> None:
    manager = DataFetcherManager(fetchers=[])
    sentinel = {"status": "ok", "market": "sentinel"}
    cfg = _cn_cfg()
    with patch("src.config.get_config", return_value=cfg), patch.object(
        DataFetcherManager,
        "_get_or_load_fundamental_context",
        return_value=sentinel,
    ) as mocked:
        cn = manager.get_fundamental_context("600519", budget_seconds=1.5)
        offshore = manager.get_fundamental_context("AAPL", budget_seconds=1.5)
    assert cn is sentinel
    assert offshore is sentinel
    assert mocked.call_count == 2
    for call in mocked.call_args_list:
        kwargs = call.kwargs
        assert kwargs.get("config") is cfg
        assert "cache_ttl" not in kwargs
        assert "cache_max_entries" not in kwargs


def test_cn_get_fundamental_context_coalesces_adapter_calls() -> None:
    manager = DataFetcherManager(fetchers=[])
    started = threading.Event()
    release = threading.Event()
    calls = {"n": 0}
    lock = threading.Lock()

    def _bundle(_code: str):
        with lock:
            calls["n"] += 1
        started.set()
        assert release.wait(timeout=5.0)
        return _ok_bundle()

    with patch("src.config.get_config", return_value=_cn_cfg()), patch.object(
        manager, "get_realtime_quote", return_value=_ok_quote()
    ), patch(
        "src.data_provider.fundamental_adapter.AkshareFundamentalAdapter.get_fundamental_bundle",
        side_effect=_bundle,
    ), patch.object(
        manager, "get_capital_flow_context", return_value={"status": "ok", "data": {"net": 1}, "source_chain": []}
    ), patch.object(
        manager, "get_dragon_tiger_context", return_value={"status": "ok", "data": {"net": 1}, "source_chain": []}
    ), patch.object(
        manager, "get_board_context", return_value={"status": "ok", "data": {"name": "白酒"}, "source_chain": []}
    ):
        results: List[Any] = [None, None]

        def _worker(index: int) -> None:
            results[index] = manager.get_fundamental_context("600519", budget_seconds=1.5)

        threads = [threading.Thread(target=_worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        assert started.wait(timeout=2.0)
        release.set()
        for thread in threads:
            thread.join(timeout=5.0)

    assert calls["n"] == 1
    assert results[0]["status"] == "ok"
    assert results[1]["status"] == "ok"
    assert results[0] is not results[1]


def test_offshore_get_fundamental_context_coalesces_adapter_calls() -> None:
    manager = DataFetcherManager(fetchers=[])
    started = threading.Event()
    release = threading.Event()
    calls = {"n": 0}
    lock = threading.Lock()
    bundle = {
        "status": "ok",
        "growth": {"revenue_yoy": 16.5, "net_profit_yoy": 19.3, "roe": 141.4},
        "earnings": {"financial_report": {"revenue": 1.0, "currency": "USD"}},
        "belong_boards": [{"name": "Technology", "type": "行业"}],
        "source_chain": [],
        "errors": [],
    }

    def _bundle(_code: str):
        with lock:
            calls["n"] += 1
        started.set()
        assert release.wait(timeout=5.0)
        return bundle

    with patch("src.config.get_config", return_value=_cn_cfg()), patch.object(
        manager, "get_realtime_quote", return_value=_ok_quote()
    ), patch(
        "src.data_provider.yfinance_fundamental_adapter.YfinanceFundamentalAdapter.get_fundamental_bundle",
        side_effect=_bundle,
    ):
        results: List[Any] = [None, None]

        def _worker(index: int) -> None:
            results[index] = manager.get_fundamental_context("AAPL", budget_seconds=1.5)

        threads = [threading.Thread(target=_worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        assert started.wait(timeout=2.0)
        release.set()
        for thread in threads:
            thread.join(timeout=5.0)

    assert calls["n"] == 1
    assert results[0]["status"] == "ok"
    assert results[1]["status"] == "ok"
    assert results[0] is not results[1]


def test_omitted_ttl_uses_injected_config() -> None:
    manager = _manager()
    cfg = SimpleNamespace(
        fundamental_cache_ttl_seconds=90,
        fundamental_cache_max_entries=8,
    )
    injected = manager._get_fundamental_cache_key(
        "600519", 1.5, market="cn", config=cfg
    )
    explicit = manager._get_fundamental_cache_key(
        "600519", 1.5, market="cn", ttl_seconds=90
    )
    assert injected == explicit

    loader = _RecordingLoader()
    manager._get_or_load_fundamental_context(
        "600519",
        1.5,
        loader,
        market="cn",
        config=cfg,
    )
    manager._get_or_load_fundamental_context(
        "600519",
        1.5,
        loader,
        market="cn",
        config=cfg,
    )
    assert loader.calls == 1
    manager._fundamental_cache_clock.tick(91)
    manager._get_or_load_fundamental_context(
        "600519",
        1.5,
        loader,
        market="cn",
        config=cfg,
    )
    assert loader.calls == 2


def test_omitted_ttl_uses_manager_fundamental_config() -> None:
    manager = _manager()
    cfg = SimpleNamespace(
        fundamental_cache_ttl_seconds=60,
        fundamental_cache_max_entries=4,
    )
    with patch.object(manager, "_get_fundamental_config", return_value=cfg):
        injected = manager._get_fundamental_cache_key("600519", 1.5, market="cn")
        explicit = manager._get_fundamental_cache_key(
            "600519", 1.5, market="cn", ttl_seconds=60
        )
    assert injected == explicit


def test_omitted_ttl_fails_when_supported_config_owner_absent() -> None:
    class _NoOwner:
        pass

    try:
        fundamental_cache._resolve_fundamental_config(_NoOwner())
    except AttributeError as exc:
        message = str(exc)
        assert "injected config" in message
        assert "DataFetcherManager._get_fundamental_config" in message
    else:
        raise AssertionError("missing supported config owner must fail clearly")

    manager = _manager()
    with patch.object(DataFetcherManager, "_get_fundamental_config", None):
        try:
            manager._get_fundamental_cache_key("600519", 1.5, market="cn")
        except AttributeError as exc:
            message = str(exc)
            assert "injected config" in message
            assert "DataFetcherManager._get_fundamental_config" in message
        else:
            raise AssertionError("missing manager config owner must fail clearly")


def test_explicit_cache_settings_skip_config_resolver() -> None:
    manager = _manager()
    calls = {"n": 0}

    def _resolve(*_args: Any, **_kwargs: Any) -> Any:
        calls["n"] += 1
        raise AssertionError("resolver must not run when ttl and max_entries are explicit")

    loader = _RecordingLoader()
    manager._get_or_load_fundamental_context(
        "600519",
        1.5,
        loader,
        market="cn",
        cache_ttl=120,
        cache_max_entries=256,
        _resolve=_resolve,
    )
    manager._get_fundamental_cache_key(
        "600519",
        1.5,
        market="cn",
        ttl_seconds=120,
        _resolve=_resolve,
    )
    assert calls["n"] == 0


def test_does_not_reuse_realtime_chip_pull_coalesce_singleton() -> None:
    manager = _manager()
    coalesce = get_provider_pull_coalesce()
    before = coalesce.stats()
    _load(manager, _RecordingLoader())
    after = coalesce.stats()
    assert after["loads"] == before["loads"]
    assert after["stores"] == before["stores"]
    assert after["hits"] == before["hits"]
