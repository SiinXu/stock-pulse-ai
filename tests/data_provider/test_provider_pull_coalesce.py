# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic tests for provider short-TTL + in-flight coalesce (issue #1292)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable, List, Optional
from unittest.mock import patch

from src.data_provider.base import DataFetcherManager
from src.data_provider.pull_coalesce import (
    CHIP_DISTRIBUTION_CAPABILITY,
    REALTIME_QUOTE_CAPABILITY,
    ProviderPullCoalesce,
    get_provider_pull_coalesce,
    reset_provider_pull_coalesce_for_tests,
)
from src.data_provider.realtime_types import (
    ChipDistribution,
    CircuitBreaker,
    RealtimeSource,
    UnifiedRealtimeQuote,
    get_chip_circuit_breaker,
)


class _Clock:
    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def tick(self, seconds: float) -> None:
        self.value += seconds


def _frozen_wall() -> datetime:
    return datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)


def _freeze_provider_pull_clocks(*, clock: Optional[_Clock] = None) -> _Clock:
    """Inject monotonic TTL clock and frozen wall current_as_of for wired tests.

    Wired realtime/chip paths omit as_of, so keys use wall-clock 5s buckets while
    expiry uses monotonic time. Tests that treat a later manager call as a TTL
    hit must freeze both clocks. A bare reset restores live wall time.
    """
    injected = clock if clock is not None else _Clock()
    reset_provider_pull_coalesce_for_tests(
        ttl_seconds=5.0,
        clock=injected,
        wall_clock=_frozen_wall,
    )
    return injected


def _wait_for_provider_pull_coalesced(
    *,
    min_count: int = 1,
    timeout: float = 2.0,
    extra: Optional[Callable[[], str]] = None,
) -> None:
    """Wait until waiters have joined in-flight work before releasing the owner.

    Wired overlap tests block the owner inside the provider loader. Releasing
    that owner before a waiter claims the shared slot lets the waiter become a
    second owner of an uncached failure. Poll singleton stats with a bounded
    Event yield so a timeout reports the last observed counts.
    """
    deadline = time.monotonic() + timeout
    last_stats: dict[str, int] = {}
    probe = threading.Event()
    while True:
        last_stats = get_provider_pull_coalesce().stats()
        if last_stats.get("coalesced", 0) >= min_count:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        probe.wait(timeout=min(0.01, remaining))
    detail = extra() if extra is not None else ""
    extra_text = f"; {detail}" if detail else ""
    raise AssertionError(
        "timed out waiting for provider pull coalesced>="
        f"{min_count}; last stats={last_stats}{extra_text}"
    )


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


def test_wall_as_of_bucket_advance_misses_without_monotonic_expiry() -> None:
    clock = _Clock()
    wall = {"now": datetime(2026, 8, 21, 12, 0, 0, tzinfo=timezone.utc)}

    def _wall() -> datetime:
        return wall["now"]

    cache = ProviderPullCoalesce(ttl_seconds=5.0, clock=clock, wall_clock=_wall)
    first_loader = _RecordingLoader(result="first")
    first = cache.get_or_load(
        provider="EfinanceFetcher",
        symbol="600519",
        capability=REALTIME_QUOTE_CAPABILITY,
        loader=first_loader,
    )
    assert first == "first"
    assert first_loader.calls == 1

    wall["now"] = datetime(2026, 8, 21, 12, 0, 5, tzinfo=timezone.utc)
    second_loader = _RecordingLoader(result="second")
    second = cache.get_or_load(
        provider="EfinanceFetcher",
        symbol="600519",
        capability=REALTIME_QUOTE_CAPABILITY,
        loader=second_loader,
    )
    assert second == "second"
    assert second_loader.calls == 1
    assert first_loader.calls == 1
    assert clock.value == 0.0


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


def test_chip_wait_timeout_is_not_part_of_coalesce_key() -> None:
    """Different wait_timeouts still share one chip load; isolation is per waiter.

    Agent-layer category timeouts are not a cache-key axis. Putting timeout
    identity in the key would split concurrent same-symbol chip pulls.
    """
    started = threading.Event()
    release = threading.Event()
    loader = _RecordingLoader(
        result="chip-shared",
        delay_event=started,
        release_event=release,
    )
    cache = ProviderPullCoalesce(ttl_seconds=5.0)
    owner_result: List[Any] = []
    waiter_error: List[BaseException] = []
    key_kwargs = {
        "provider": "TushareFetcher",
        "symbol": "600519",
        "as_of": "2026-08-21T12:00:00Z",
        "capability": CHIP_DISTRIBUTION_CAPABILITY,
    }
    assert len(cache.build_key(**key_kwargs)) == 4

    def _owner() -> None:
        owner_result.append(
            cache.get_or_load(
                **key_kwargs,
                loader=loader,
                wait_timeout=2.0,
            )
        )

    owner = threading.Thread(target=_owner)
    owner.start()
    assert started.wait(timeout=2.0)

    try:
        cache.get_or_load(
            **key_kwargs,
            loader=loader,
            wait_timeout=0.05,
        )
    except TimeoutError as exc:
        waiter_error.append(exc)

    release.set()
    owner.join(timeout=5.0)

    assert waiter_error and isinstance(waiter_error[0], TimeoutError)
    assert owner_result == ["chip-shared"]
    assert loader.calls == 1
    assert cache.stats()["coalesced"] == 1
    assert cache.stats()["loads"] == 1
    assert cache.stats()["stores"] == 1


@patch("src.config.get_config")
def test_wired_realtime_path_coalesces_and_keeps_fallback(mock_get_config) -> None:
    mock_get_config.return_value = SimpleNamespace(
        enable_realtime_quote=True,
        realtime_source_priority="efinance,akshare_em",
    )
    _freeze_provider_pull_clocks()
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
    # Prime composition-root config on this thread. Isolated cold runs otherwise
    # spend the started.wait budget inside the first get_application_services()
    # call and never enter the dummy primary.
    assert manager._get_fundamental_config().enable_realtime_quote is True

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
    _wait_for_provider_pull_coalesced(
        min_count=1,
        extra=lambda: (
            f"primary.calls={primary.calls} backup.calls={backup.calls} "
            f"started={started.is_set()} release={release.is_set()} "
            f"alive={[thread.is_alive() for thread in threads]}"
        ),
    )
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
    assert get_provider_pull_coalesce().stats()["coalesced"] >= 1

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
    _freeze_provider_pull_clocks()
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
    clock = _freeze_provider_pull_clocks()
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


class _ChipDummyFetcher:
    def __init__(
        self,
        name: str,
        priority: int,
        result=None,
        error: Optional[BaseException] = None,
        *,
        delay_event: Optional[threading.Event] = None,
        release_event: Optional[threading.Event] = None,
    ) -> None:
        self.name = name
        self.priority = priority
        self._result = result
        self._error = error
        self.delay_event = delay_event
        self.release_event = release_event
        self.calls = 0
        self._lock = threading.Lock()

    def get_chip_distribution(self, stock_code: str):
        with self._lock:
            self.calls += 1
        if self.delay_event is not None:
            self.delay_event.set()
        if self.release_event is not None:
            self.release_event.wait(timeout=5.0)
        if self._error is not None:
            raise self._error
        return self._result


def _chip(
    code: str = "600519",
    avg_cost: float = 12.3,
    concentration_90: float = 0.13,
) -> ChipDistribution:
    return ChipDistribution(
        code=code,
        profit_ratio=0.61,
        avg_cost=avg_cost,
        concentration_90=concentration_90,
    )


def _enable_chip_config():
    return SimpleNamespace(enable_chip_distribution=True)


@patch("src.config.get_config")
def test_wired_chip_path_coalesces_same_key_concurrency(mock_get_config) -> None:
    mock_get_config.return_value = _enable_chip_config()
    get_chip_circuit_breaker().reset()
    _freeze_provider_pull_clocks()
    started = threading.Event()
    release = threading.Event()
    result = _chip()
    primary = _ChipDummyFetcher(
        "TushareFetcher",
        0,
        result=result,
        delay_event=started,
        release_event=release,
    )
    manager = _manager([primary])
    results: List[Any] = [None, None, None]
    errors: List[BaseException] = []

    def _worker(index: int) -> None:
        try:
            results[index] = manager.get_chip_distribution("600519")
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
    assert primary.calls == 1
    assert all(item is not None for item in results)
    assert all(item.avg_cost == 12.3 for item in results)
    assert all(item.concentration_90 == 0.13 for item in results)
    owner_hits = [item for item in results if item is result]
    waiter_hits = [item for item in results if item is not result]
    assert len(owner_hits) == 1
    assert len(waiter_hits) == 2
    assert all(item == result for item in waiter_hits)
    stats = get_provider_pull_coalesce().stats()
    assert stats["loads"] == 1
    assert stats["coalesced"] >= 1


@patch("src.config.get_config")
def test_wired_chip_ttl_hit_expiry_and_mutation_isolation(mock_get_config) -> None:
    mock_get_config.return_value = _enable_chip_config()
    get_chip_circuit_breaker().reset()
    clock = _freeze_provider_pull_clocks()
    result = _chip()
    primary = _ChipDummyFetcher("TushareFetcher", 0, result=result)
    manager = _manager([primary])

    first = manager.get_chip_distribution("600519")
    assert first is result
    first.avg_cost = 1.0
    second = manager.get_chip_distribution("600519")
    assert primary.calls == 1
    assert second is not first
    assert second is not result
    assert second.avg_cost == 12.3
    assert first is result
    assert first.avg_cost == 1.0

    clock.tick(5.0)
    third = manager.get_chip_distribution("600519")
    assert third is not None
    assert primary.calls == 2


@patch("src.config.get_config")
def test_wired_chip_placeholder_and_empty_are_not_cached(mock_get_config) -> None:
    mock_get_config.return_value = _enable_chip_config()
    get_chip_circuit_breaker().reset()
    _freeze_provider_pull_clocks()
    placeholder = ChipDistribution(code="600519")
    backup_chip = _chip(avg_cost=15.0)
    primary = _ChipDummyFetcher("TushareFetcher", 0, result=placeholder)
    backup = _ChipDummyFetcher("AkshareFetcher", 1, result=backup_chip)
    manager = _manager([primary, backup])

    first = manager.get_chip_distribution("600519")
    assert first is backup_chip
    assert primary.calls == 1
    assert backup.calls == 1
    second = manager.get_chip_distribution("600519")
    assert primary.calls == 2
    assert backup.calls == 1
    assert second is not backup_chip
    assert second.avg_cost == 15.0

    get_chip_circuit_breaker().reset()
    _freeze_provider_pull_clocks()
    started = threading.Event()
    release = threading.Event()
    empty_primary = _ChipDummyFetcher(
        "TushareFetcher",
        0,
        result=None,
        delay_event=started,
        release_event=release,
    )
    concurrent_backup_chip = _chip(avg_cost=16.0)
    concurrent_backup = _ChipDummyFetcher(
        "AkshareFetcher",
        1,
        result=concurrent_backup_chip,
    )
    concurrent_manager = _manager([empty_primary, concurrent_backup])
    results: List[Any] = [None, None]
    errors: List[BaseException] = []

    def _worker(index: int) -> None:
        try:
            results[index] = concurrent_manager.get_chip_distribution("600519")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    assert started.wait(timeout=2.0)
    release.set()
    for thread in threads:
        thread.join(timeout=5.0)

    assert errors == []
    assert empty_primary.calls == 1
    assert concurrent_backup.calls == 1
    assert concurrent_backup_chip in results
    assert all(item is not None and item.avg_cost == 16.0 for item in results)


@patch("src.config.get_config")
def test_wired_chip_open_circuit_skips_provider_before_coalesce(
    mock_get_config,
) -> None:
    mock_get_config.return_value = _enable_chip_config()
    breaker = get_chip_circuit_breaker()
    breaker.reset()
    _freeze_provider_pull_clocks()
    source_key = "tushare_chip"
    breaker.record_failure(source_key, "provider_error")
    breaker.record_failure(source_key, "provider_error")
    assert not breaker.is_available(source_key)

    cheap = _chip(avg_cost=1.0)
    valid = _chip(avg_cost=18.0)
    primary = _ChipDummyFetcher("TushareFetcher", 0, result=cheap)
    backup = _ChipDummyFetcher("AkshareFetcher", 1, result=valid)
    manager = _manager([primary, backup])

    first = manager.get_chip_distribution("600519")
    assert first is valid
    assert primary.calls == 0
    assert backup.calls == 1
    assert not breaker.is_available(source_key)

    second = manager.get_chip_distribution("600519")
    assert second is not None
    assert second.avg_cost == 18.0
    assert primary.calls == 0
    assert backup.calls == 1


@patch("src.config.get_config")
def test_wired_chip_exceptions_do_not_poison_cache(mock_get_config) -> None:
    mock_get_config.return_value = _enable_chip_config()
    get_chip_circuit_breaker().reset()
    _freeze_provider_pull_clocks()
    backup_chip = _chip(avg_cost=19.0)
    primary = _ChipDummyFetcher(
        "TushareFetcher",
        0,
        error=RuntimeError("chip down"),
    )
    backup = _ChipDummyFetcher("AkshareFetcher", 1, result=backup_chip)
    manager = _manager([primary, backup])

    first = manager.get_chip_distribution("600519")
    second = manager.get_chip_distribution("600519")
    assert first is backup_chip
    assert second is not backup_chip
    assert second.avg_cost == 19.0
    assert primary.calls == 2
    assert backup.calls == 1
    primary_keys = [
        key
        for key in get_provider_pull_coalesce()._cache
        if key[0] == "TushareFetcher"
    ]
    assert primary_keys == []

    get_chip_circuit_breaker().reset()
    _freeze_provider_pull_clocks()
    started = threading.Event()
    release = threading.Event()
    raising = _ChipDummyFetcher(
        "TushareFetcher",
        0,
        error=RuntimeError("chip down"),
        delay_event=started,
        release_event=release,
    )
    concurrent_backup_chip = _chip(avg_cost=20.0)
    concurrent_backup = _ChipDummyFetcher(
        "AkshareFetcher",
        1,
        result=concurrent_backup_chip,
    )
    concurrent_manager = _manager([raising, concurrent_backup])
    results: List[Any] = [None, None]
    errors: List[BaseException] = []

    def _worker(index: int) -> None:
        try:
            results[index] = concurrent_manager.get_chip_distribution("600519")
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    assert started.wait(timeout=2.0)
    release.set()
    for thread in threads:
        thread.join(timeout=5.0)

    assert errors == []
    assert raising.calls == 1
    assert concurrent_backup.calls == 1
    assert concurrent_backup_chip in results

    get_chip_circuit_breaker().reset()
    later = concurrent_manager.get_chip_distribution("600519")
    assert later is not None
    assert raising.calls == 2
    assert concurrent_backup.calls == 1


@patch("src.config.get_config")
def test_wired_chip_owner_identity_preserved_on_first_success(
    mock_get_config,
) -> None:
    mock_get_config.return_value = _enable_chip_config()
    get_chip_circuit_breaker().reset()
    _freeze_provider_pull_clocks()
    result = _chip()
    primary = _ChipDummyFetcher("TushareFetcher", 0, result=result)
    manager = _manager([primary])

    first = manager.get_chip_distribution("600519")
    assert first is primary._result
    first.avg_cost = 99.0
    second = manager.get_chip_distribution("600519")
    assert second is not first
    assert second.avg_cost == 12.3
    assert primary.calls == 1


@patch("src.config.get_config")
def test_wired_chip_store_does_not_satisfy_realtime_pull(mock_get_config) -> None:
    mock_get_config.return_value = SimpleNamespace(
        enable_chip_distribution=True,
        enable_realtime_quote=True,
        realtime_source_priority="efinance",
    )
    get_chip_circuit_breaker().reset()
    _freeze_provider_pull_clocks()
    chip_fetcher = _ChipDummyFetcher("TushareFetcher", 0, result=_chip())
    quote_fetcher = _DummyFetcher("EfinanceFetcher", 0, result=_quote())
    manager = _manager([chip_fetcher, quote_fetcher])

    chip = manager.get_chip_distribution("600519")
    assert chip is chip_fetcher._result
    assert chip_fetcher.calls == 1
    quote = manager.get_realtime_quote("600519")
    assert quote is not None
    assert quote_fetcher.calls == 1
    chip_again = manager.get_chip_distribution("600519")
    assert chip_again is not None
    assert chip_fetcher.calls == 1
    assert quote_fetcher.calls == 1
    capabilities = {key[3] for key in get_provider_pull_coalesce()._cache}
    assert CHIP_DISTRIBUTION_CAPABILITY in capabilities
    assert REALTIME_QUOTE_CAPABILITY in capabilities
