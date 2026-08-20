# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Facade identity, reload, and cache-contract guards for money-flow extraction."""

from __future__ import annotations

import importlib
import inspect
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.core.trading_calendar import get_effective_trading_date
import src.data_provider.base as base
import src.data_provider.manager_parts.money_flow_cache_methods as money_flow_cache
from src.data_provider.base import DataFetcherManager
from src.data_provider.money_flow_types import (
    MoneyFlowOutcome,
    MoneyFlowSnapshot,
    MoneyFlowStatus,
)


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "src" / "data_provider" / "base.py"
OWNER_PATH = (
    ROOT
    / "src"
    / "data_provider"
    / "manager_parts"
    / "money_flow_cache_methods.py"
)


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


class _MoneyFlowFetcher:
    def __init__(self, name: str, result):
        self.name = name
        self.priority = 0
        self._result = result
        self.calls = 0

    def get_money_flow(self, stock_code: str, days: int = 5):
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _snapshot(*, date: str | None = None) -> MoneyFlowSnapshot:
    return MoneyFlowSnapshot(
        code="600519",
        date=date or get_effective_trading_date("cn").isoformat(),
        source="fixture",
        main_net_inflow_ratio=1.0,
        bucket_definition="fixture_v1;amount_unit=unknown;ratio_unit=percent",
        as_of=datetime.now(timezone.utc).isoformat(),
        requested_days=5,
        observed_days=5,
        completeness="complete",
    )


def _identity_key(
    *,
    code: str = "600519",
    market: str = "cn",
    session: str = "2026-08-01",
    days: int = 5,
    calibration: str = "v1",
):
    return (code, market, session, days, (("FlowFetcher", calibration),))


def test_money_flow_cache_methods_remain_on_data_fetcher_manager_facade() -> None:
    required = money_flow_cache.EXPECTED_MONEY_FLOW_CACHE_METHOD_NAMES
    for name in required:
        method = getattr(DataFetcherManager, name)
        assert callable(method), name
        function = _descriptor_function(vars(DataFetcherManager)[name])
        assert function.__module__ == "src.data_provider.base", name
        assert function.__qualname__ == f"DataFetcherManager.{name}", name
        assert function.__globals__ is vars(base), name


def test_owner_module_exists_for_money_flow_cache_extraction() -> None:
    assert OWNER_PATH.is_file()
    assert "money_flow_cache_methods" in BASE_PATH.read_text(encoding="utf-8")
    importlib.import_module("src.data_provider.manager_parts.money_flow_cache_methods")


def test_money_flow_cache_source_descriptors_share_code_not_identity() -> None:
    source_names = []
    for name, source_descriptor in vars(money_flow_cache._MoneyFlowCacheMethods).items():
        source_function = _descriptor_function(source_descriptor)
        if name.startswith("__") or not inspect.isfunction(source_function):
            continue
        source_names.append(name)
        facade_function = _descriptor_function(vars(DataFetcherManager)[name])
        assert facade_function is not source_function
        assert facade_function.__code__ is source_function.__code__
        assert source_function.__module__ == money_flow_cache.__name__
    assert tuple(source_names) == money_flow_cache.EXPECTED_MONEY_FLOW_CACHE_METHOD_NAMES


def test_facade_patch_seam_intercepts_money_flow_cache_lookup() -> None:
    snapshot = _snapshot()
    fetcher = _MoneyFlowFetcher("FlowFetcher", snapshot)
    manager = DataFetcherManager(fetchers=[fetcher])
    sentinel = MoneyFlowOutcome(
        status=MoneyFlowStatus.PARTIAL,
        code="600519",
        market="cn",
        requested_days=5,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        snapshot=snapshot,
        provider_date=snapshot.date,
        age_days=0,
    )
    with patch.object(
        DataFetcherManager,
        "_money_flow_cache_lookup",
        return_value=sentinel,
    ) as mocked:
        outcome = manager.get_money_flow("600519")
    assert outcome.cache_state == "fresh"
    assert outcome.snapshot is snapshot
    mocked.assert_called_once()
    assert fetcher.calls == 0


def _run_reload_contract(body: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "\n".join(
                (
                    "import importlib",
                    "import src.data_provider.base as base",
                    "import src.data_provider.manager_parts.money_flow_cache_methods as money_flow_cache",
                    "",
                    "names = money_flow_cache.EXPECTED_MONEY_FLOW_CACHE_METHOD_NAMES",
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
                    "            vars(money_flow_cache._MoneyFlowCacheMethods)[name]",
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
money_flow_cache = importlib.reload(money_flow_cache)
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
money_flow_cache = importlib.reload(money_flow_cache)
assert base.DataFetcherManager is reloaded_class
after_owner_source, after_owner_facade = bindings()
for name in names:
    assert after_owner_source[name] is not after_base_source[name]
    assert after_owner_facade[name] is not after_base_facade[name]
    assert after_owner_facade[name].__code__ is after_owner_source[name].__code__
"""
    )


def test_fresh_hit_increments_stats_without_a_second_provider_call() -> None:
    fetcher = _MoneyFlowFetcher("FlowFetcher", _snapshot())
    manager = DataFetcherManager(fetchers=[fetcher])
    first = manager.get_money_flow("600519")
    second = manager.get_money_flow("600519")
    assert first.cache_state == "miss"
    assert second.cache_state == "fresh"
    assert fetcher.calls == 1
    stats = manager.get_money_flow_cache_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["entries"] == 1


def test_invalidate_drops_symbol_entries_and_forces_a_refetch() -> None:
    fetcher = _MoneyFlowFetcher("FlowFetcher", _snapshot())
    manager = DataFetcherManager(fetchers=[fetcher])
    manager.get_money_flow("600519")
    other_key = _identity_key(code="000001")
    manager._money_flow_cache_store(other_key, SimpleNamespace(snapshot=None))
    assert manager.invalidate_money_flow_cache("600519") == 1
    assert manager.get_money_flow_cache_stats()["entries"] == 1
    manager.get_money_flow("600519")
    assert fetcher.calls == 2
    assert manager.invalidate_money_flow_cache() == 2


def test_stale_lookup_matches_session_identity_not_effective_date() -> None:
    manager = DataFetcherManager(fetchers=[])
    older = SimpleNamespace(label="older")
    newer = SimpleNamespace(label="newer")
    now = time.time()
    manager._money_flow_cache_store(_identity_key(session="2026-08-01"), older)
    manager._money_flow_cache[_identity_key(session="2026-08-01")]["stored_at"] = now - 20
    manager._money_flow_cache_store(_identity_key(session="2026-08-02"), newer)
    manager._money_flow_cache[_identity_key(session="2026-08-02")]["stored_at"] = now - 10
    found = manager._money_flow_cache_lookup(
        _identity_key(session="2026-08-03"),
        allow_stale=True,
    )
    assert found is newer
    missing = manager._money_flow_cache_lookup(
        _identity_key(session="2026-08-03", calibration="v2"),
        allow_stale=True,
    )
    assert missing is None


def test_stale_get_money_flow_never_crosses_calibration_identity() -> None:
    fetcher = _MoneyFlowFetcher("FlowFetcher", _snapshot())
    fetcher.money_flow_calibration_identity = "fixture-v1"
    manager = DataFetcherManager(fetchers=[fetcher])
    assert manager.get_money_flow("600519").snapshot is not None
    manager._MONEY_FLOW_CACHE_TTL_SECONDS = -1
    fetcher.money_flow_calibration_identity = "fixture-v2"
    fetcher._result = RuntimeError("upstream down")
    outcome = manager.get_money_flow("600519")
    assert outcome.status == MoneyFlowStatus.FETCH_FAILED
    assert outcome.cache_state == "miss"


def test_store_evicts_oldest_entry_when_over_max_size() -> None:
    manager = DataFetcherManager(fetchers=[])
    manager._MONEY_FLOW_CACHE_MAX_ENTRIES = 2
    first = SimpleNamespace(label="first")
    second = SimpleNamespace(label="second")
    third = SimpleNamespace(label="third")
    now = time.time()
    manager._money_flow_cache_store(_identity_key(code="000001"), first)
    manager._money_flow_cache[_identity_key(code="000001")]["stored_at"] = now - 2
    manager._money_flow_cache_store(_identity_key(code="000002"), second)
    manager._money_flow_cache[_identity_key(code="000002")]["stored_at"] = now - 1
    manager._money_flow_cache_store(_identity_key(code="000003"), third)
    stats = manager.get_money_flow_cache_stats()
    assert stats["entries"] == 2
    assert _identity_key(code="000001") not in manager._money_flow_cache
    assert manager._money_flow_cache_lookup(_identity_key(code="000002")) is second
    assert manager._money_flow_cache_lookup(_identity_key(code="000003")) is third


def test_lookup_honors_fresh_and_stale_ttl() -> None:
    manager = DataFetcherManager(fetchers=[])
    outcome = SimpleNamespace(label="cached")
    key = _identity_key()
    manager._money_flow_cache_store(key, outcome)
    manager._money_flow_cache[key]["stored_at"] = time.time() - (
        manager._MONEY_FLOW_CACHE_TTL_SECONDS + 1
    )
    assert manager._money_flow_cache_lookup(key) is None
    assert manager._money_flow_cache_lookup(key, allow_stale=True) is outcome
    manager._money_flow_cache[key]["stored_at"] = time.time() - (
        manager._MONEY_FLOW_STALE_TTL_SECONDS + 1
    )
    assert manager._money_flow_cache_lookup(key, allow_stale=True) is None


def test_invalidate_uses_facade_normalize_stock_code_patch() -> None:
    manager = DataFetcherManager(fetchers=[])
    manager._money_flow_cache_store(_identity_key(), SimpleNamespace(snapshot=None))
    with patch.object(base, "normalize_stock_code", return_value="000001") as mocked:
        removed = manager.invalidate_money_flow_cache("SH600519")
    mocked.assert_called_once_with("SH600519")
    assert removed == 0
    assert manager.get_money_flow_cache_stats()["entries"] == 1
    assert manager.invalidate_money_flow_cache("SH600519") == 1
    assert manager.get_money_flow_cache_stats()["entries"] == 0
