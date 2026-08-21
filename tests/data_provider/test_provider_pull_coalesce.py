# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic tests for provider short-TTL + in-flight coalesce (issue #1292)."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import patch

from src.data_provider.base import DataFetcherManager
from src.data_provider.pull_coalesce import (
    REALTIME_QUOTE_CAPABILITY,
    ProviderPullCoalesce,
    reset_provider_pull_coalesce_for_tests,
)
from src.data_provider.realtime_types import (
    CircuitBreaker,
    RealtimeSource,
    UnifiedRealtimeQuote,
)


class _Clock:
    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def tick(self, seconds: float) -> None:
        self.value += seconds


class _RecordingLoader:
    def __init__(
        self,
        result: Any = "ok",
        *,
        error: Optional[BaseException] = None,
        delay_event: Optional[threading.Event] = None,
        release_event: Optional[threading.Event] = None,
    ) -> None:
        self.result = result
        self.error = error
        self.delay_event = delay_event
        self.release_event = release_event
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self) -> Any:
        with self._lock:
            self.calls += 1
        if self.delay_event is not None:
            self.delay_event.set()
        if self.release_event is not None:
            self.release_event.wait(timeout=5.0)
        if self.error is not None:
            raise self.error
        return self.result


class _DummyFetcher:
    def __init__(
        self,
        name: str,
        priority: int,
        result=None,
        error: Optional[BaseException] = None,
        *,
        breaker: Optional[CircuitBreaker] = None,
        breaker_key: str = "",
        delay_event: Optional[threading.Event] = None,
        release_event: Optional[threading.Event] = None,
    ) -> None:
        self.name = name
        self.priority = priority
        self._result = result
        self._error = error
        self.breaker = breaker
        self.breaker_key = breaker_key or f"{name.lower()}_rt"
        self.delay_event = delay_event
        self.release_event = release_event
        self.calls = 0
        self._lock = threading.Lock()

    def get_realtime_quote(self, *args, **kwargs):
        with self._lock:
            self.calls += 1
        if self.delay_event is not None:
            self.delay_event.set()
        if self.release_event is not None:
            self.release_event.wait(timeout=5.0)
        if self.breaker is not None and not self.breaker.is_available(self.breaker_key):
            raise RuntimeError("circuit_open")
        if self._error is not None:
            if self.breaker is not None:
                self.breaker.record_failure(self.breaker_key, "provider_error")
            raise self._error
        if self.breaker is not None:
            self.breaker.record_success(self.breaker_key)
        return self._result


def _quote(code: str = "600519", price: float = 1688.0) -> UnifiedRealtimeQuote:
    return UnifiedRealtimeQuote(
        code=code,
        name="贵州茅台",
        source=RealtimeSource.EFINANCE,
        price=price,
        change_pct=1.2,
    )


def _manager(fetchers) -> DataFetcherManager:
    return DataFetcherManager(fetchers=fetchers)


def test_concurrent_same_key_coalesces_to_one_load() -> None:
    started = threading.Event()
    release = threading.Event()
    loader = _RecordingLoader(
        result={"price": 1},
        delay_event=started,
        release_event=release,
    )
    cache = ProviderPullCoalesce(ttl_seconds=5.0)
    results: List[Any] = [None, None, None]
    errors: List[BaseException] = []

    def _worker(index: int) -> None:
        try:
            results[index] = cache.get_or_load(
                provider="EfinanceFetcher",
                symbol="600519",
                as_of="2026-08-21T12:00:00Z",
                capability=REALTIME_QUOTE_CAPABILITY,
                loader=loader,
            )
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
    assert results == [{"price": 1}, {"price": 1}, {"price": 1}]
    assert cache.stats()["coalesced"] == 2
    assert cache.stats()["loads"] == 1
    assert cache.stats()["stores"] == 1


def test_delayed_claim_after_owner_stores_reuses_warm_cache() -> None:
    started = threading.Event()
    release = threading.Event()
    loader = _RecordingLoader(
        result="ok",
        delay_event=started,
        release_event=release,
    )
    cache = ProviderPullCoalesce(ttl_seconds=5.0)
    enter_claim = threading.Event()
    allow_claim = threading.Event()
    begin_calls = {"n": 0}
    original_begin = cache._begin_inflight

    def gated_begin(key):
        begin_calls["n"] += 1
        if begin_calls["n"] > 1:
            enter_claim.set()
            assert allow_claim.wait(timeout=5.0)
        return original_begin(key)

    setattr(cache, "_begin_inflight", gated_begin)

    results: List[Any] = [None, None]
    errors: List[BaseException] = []

    def _worker(index: int) -> None:
        try:
            results[index] = cache.get_or_load(
                provider="EfinanceFetcher",
                symbol="600519",
                as_of="2026-08-21T12:00:00Z",
                capability=REALTIME_QUOTE_CAPABILITY,
                loader=loader,
            )
        except BaseException as exc:
            errors.append(exc)

    owner = threading.Thread(target=_worker, args=(0,))
    late = threading.Thread(target=_worker, args=(1,))
    owner.start()
    assert started.wait(timeout=2.0)
    late.start()
    assert enter_claim.wait(timeout=2.0)
    release.set()
    owner.join(timeout=5.0)
    allow_claim.set()
    late.join(timeout=5.0)

    assert errors == []
    assert results == ["ok", "ok"]
    assert loader.calls == 1
    assert cache.stats()["loads"] == 1
    assert cache.stats()["stores"] == 1
    assert cache.stats()["hits"] == 1


def test_cached_quote_is_isolated_from_caller_mutation() -> None:
    quote = _quote()
    cache = ProviderPullCoalesce(ttl_seconds=5.0)
    first = cache.get_or_load(
        provider="EfinanceFetcher",
        symbol="600519",
        as_of="2026-08-21T12:00:00Z",
        capability=REALTIME_QUOTE_CAPABILITY,
        loader=_RecordingLoader(result=quote),
        is_success=lambda value: value is not None and value.has_basic_data(),
    )
    assert first is quote
    first.price = 1.0
    second = cache.get_or_load(
        provider="EfinanceFetcher",
        symbol="600519",
        as_of="2026-08-21T12:00:00Z",
        capability=REALTIME_QUOTE_CAPABILITY,
        loader=_RecordingLoader(result=_quote(price=9.0)),
        is_success=lambda value: value is not None and value.has_basic_data(),
    )
    assert second is not first
    assert second.price == 1688.0


def test_ttl_expiry_and_new_as_of_are_misses() -> None:
    clock = _Clock()
    loader = _RecordingLoader(result="first")
    cache = ProviderPullCoalesce(ttl_seconds=5.0, clock=clock)

    first = cache.get_or_load(
        provider="EfinanceFetcher",
        symbol="SH600519",
        as_of="2026-08-21T12:00:00Z",
        capability=REALTIME_QUOTE_CAPABILITY,
        loader=loader,
    )
    second = cache.get_or_load(
        provider="EfinanceFetcher",
        symbol="600519",
        as_of="2026-08-21T12:00:00Z",
        capability=REALTIME_QUOTE_CAPABILITY,
        loader=loader,
    )
    assert first == "first"
    assert second == "first"
    assert loader.calls == 1

    later = cache.get_or_load(
        provider="EfinanceFetcher",
        symbol="600519",
        as_of="2026-08-21T12:00:05Z",
        capability=REALTIME_QUOTE_CAPABILITY,
        loader=_RecordingLoader(result="later"),
    )
    assert later == "later"

    other_capability = cache.get_or_load(
        provider="EfinanceFetcher",
        symbol="600519",
        as_of="2026-08-21T12:00:00Z",
        capability="chip_distribution",
        loader=_RecordingLoader(result="chip"),
    )
    assert other_capability == "chip"

    clock.tick(5.0)
    expired_loader = _RecordingLoader(result="expired")
    expired = cache.get_or_load(
        provider="EfinanceFetcher",
        symbol="600519",
        as_of="2026-08-21T12:00:00Z",
        capability=REALTIME_QUOTE_CAPABILITY,
        loader=expired_loader,
    )
    assert expired == "expired"
    assert expired_loader.calls == 1


def test_exception_and_empty_results_are_not_cached_as_success() -> None:
    cache = ProviderPullCoalesce(ttl_seconds=5.0)
    failing = _RecordingLoader(error=RuntimeError("provider down"))

    raised = 0
    for _ in range(2):
        try:
            cache.get_or_load(
                provider="EfinanceFetcher",
                symbol="600519",
                as_of="2026-08-21T12:00:00Z",
                capability=REALTIME_QUOTE_CAPABILITY,
                loader=failing,
            )
        except RuntimeError:
            raised += 1
    assert raised == 2
    assert failing.calls == 2
    assert cache.stats()["stores"] == 0
    assert cache.stats()["entries"] == 0

    empty = _RecordingLoader(result=None)
    assert (
        cache.get_or_load(
            provider="AkshareFetcher:em",
            symbol="600519",
            as_of="2026-08-21T12:00:00Z",
            capability=REALTIME_QUOTE_CAPABILITY,
            loader=empty,
        )
        is None
    )
    assert (
        cache.get_or_load(
            provider="AkshareFetcher:em",
            symbol="600519",
            as_of="2026-08-21T12:00:00Z",
            capability=REALTIME_QUOTE_CAPABILITY,
            loader=empty,
        )
        is None
    )
    assert empty.calls == 2


def test_waiter_timeout_does_not_poison_shared_work() -> None:
    started = threading.Event()
    release = threading.Event()
    loader = _RecordingLoader(
        result="shared",
        delay_event=started,
        release_event=release,
    )
    cache = ProviderPullCoalesce(ttl_seconds=5.0)
    owner_result: List[Any] = []
    waiter_error: List[BaseException] = []

    def _owner() -> None:
        owner_result.append(
            cache.get_or_load(
                provider="EfinanceFetcher",
                symbol="600519",
                as_of="2026-08-21T12:00:00Z",
                capability=REALTIME_QUOTE_CAPABILITY,
                loader=loader,
            )
        )

    owner = threading.Thread(target=_owner)
    owner.start()
    assert started.wait(timeout=2.0)

    try:
        cache.get_or_load(
            provider="EfinanceFetcher",
            symbol="600519",
            as_of="2026-08-21T12:00:00Z",
            capability=REALTIME_QUOTE_CAPABILITY,
            loader=loader,
            wait_timeout=0.05,
        )
    except TimeoutError as exc:
        waiter_error.append(exc)

    release.set()
    owner.join(timeout=5.0)
    late = cache.get_or_load(
        provider="EfinanceFetcher",
        symbol="600519",
        as_of="2026-08-21T12:00:00Z",
        capability=REALTIME_QUOTE_CAPABILITY,
        loader=loader,
    )

    assert waiter_error and isinstance(waiter_error[0], TimeoutError)
    assert owner_result == ["shared"]
    assert late == "shared"
    assert loader.calls == 1
    assert cache.stats()["stores"] == 1


@patch("src.config.get_config")
def test_wired_realtime_path_coalesces_and_keeps_fallback(mock_get_config) -> None:
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,akshare_em",
    )
    started = threading.Event()
    release = threading.Event()
    primary = _DummyFetcher(
        "EfinanceFetcher",
        0,
        error=RuntimeError("efinance timeout"),
        delay_event=started,
        release_event=release,
    )
    backup = _DummyFetcher("AkshareFetcher", 1, result=_quote())
    manager = _manager([primary, backup])

    results: List[Any] = [None, None]
    errors: List[BaseException] = []

    def _worker(index: int) -> None:
        try:
            results[index] = manager.get_realtime_quote("600519")
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=_worker, args=(0,)),
        threading.Thread(target=_worker, args=(1,)),
    ]
    for thread in threads:
        thread.start()
    assert started.wait(timeout=2.0)
    release.set()
    for thread in threads:
        thread.join(timeout=5.0)

    assert errors == []
    assert results[0] is not None and results[1] is not None
    assert results[0].price == 1688.0
    assert results[1].price == 1688.0
    assert results[0].fallback_from == "efinance"
    assert primary.calls == 1
    assert backup.calls == 1

    sequential = manager.get_realtime_quote("600519")
    assert sequential is not None
    assert sequential.price == 1688.0
    assert primary.calls == 2
    assert backup.calls == 1


@patch("src.config.get_config")
def test_wired_realtime_breaker_still_skips_open_provider(mock_get_config) -> None:
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,akshare_em",
    )
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    breaker.record_failure("efinance_rt", "timeout")
    assert not breaker.is_available("efinance_rt")

    primary = _DummyFetcher(
        "EfinanceFetcher",
        0,
        result=_quote(price=1.0),
        breaker=breaker,
        breaker_key="efinance_rt",
    )
    backup = _DummyFetcher("AkshareFetcher", 1, result=_quote(price=2.0))
    manager = _manager([primary, backup])

    quote = manager.get_realtime_quote("600519")
    assert quote is not None
    assert quote.price == 2.0
    assert quote.fallback_from == "efinance"
    assert primary.calls == 1
    assert backup.calls == 1

    again = manager.get_realtime_quote("600519")
    assert again is not None
    assert again.price == 2.0
    assert primary.calls == 2
    assert backup.calls == 1
    assert not breaker.is_available("efinance_rt")


@patch("src.config.get_config")
def test_wired_realtime_ttl_expiry_reloads(mock_get_config) -> None:
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance",
    )
    clock = _Clock()

    def _wall() -> datetime:
        return datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)

    reset_provider_pull_coalesce_for_tests(
        ttl_seconds=5.0,
        clock=clock,
        wall_clock=_wall,
    )
    primary = _DummyFetcher("EfinanceFetcher", 0, result=_quote())
    manager = _manager([primary])

    first = manager.get_realtime_quote("600519")
    second = manager.get_realtime_quote("600519")
    assert first is not None and second is not None
    assert primary.calls == 1

    clock.tick(5.0)
    third = manager.get_realtime_quote("600519")
    assert third is not None
    assert primary.calls == 2
