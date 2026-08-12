# -*- coding: utf-8 -*-
"""Parallel dependency-free data pulls with concurrency and budget guardrails.

Issue #1126 — analysis / agent fetch helpers may fan out independent data or
intel pulls. This module only coordinates *call sites*; each task must still
invoke the existing provider-governed path (``DataFetcherManager``, search
services, caches, circuits, and per-provider rate limiters). Parallelism must
never open a side-channel HTTP path around those layers.

Guardrails
----------
* **Global concurrency** — at most ``max_concurrent`` tasks run at once.
* **Per-provider concurrency** — tasks share a semaphore keyed by
  ``provider_key`` (logical provider or capability chain label). Default
  limit is 1 so a single provider is not stampeded from this coordinator.
* **Failure isolation** — one branch exception becomes a typed gap/error; other
  branches still complete.
* **Total budget** — optional wall-clock budget; tasks that have not started
  when the budget elapses are marked ``budget_skipped`` rather than started.
* **Serial fallback** — when ``enabled=False``, tasks run in declaration order
  on the calling thread (same merge contract).

Deterministic merge order
-------------------------
Results are always returned as an ordered mapping whose keys follow the
**declaration order of ``tasks``**, never completion order. Downstream
``AgentContext.data`` / stage IO writers should iterate that mapping (or the
declared key list) so parallel and serial runs produce identical key order.

Compatibility with ActualsFetcher coalesce
------------------------------------------
This coordinator does not replace process-local coalesce or short-TTL caches
used by prediction actuals (#1110). Overlapping symbol/as-of pulls should still
go through the provider manager (and ActualsFetcher when scoring); fan-out here
only runs dependency-free *distinct* tasks.
"""

from __future__ import annotations

import logging
import threading
import time

from src.utils.sanitize import log_safe_exception
from collections import OrderedDict
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


class FetchBranchStatus(str, Enum):
    """Typed outcome for one parallel (or serial) fetch branch."""

    OK = "ok"
    GAP = "gap"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    BUDGET_SKIPPED = "budget_skipped"


@dataclass(frozen=True)
class FetchTask:
    """One independent fetch unit.

    Parameters
    ----------
    key:
        Stable result key used for deterministic merge (e.g. ``realtime_quote``).
    fn:
        Zero-arg callable that performs the fetch. Must not bypass provider
        governance; callers pass closures around manager/service methods.
    provider_key:
        Logical rate-limit / concurrency partition. Tasks with the same key
        share the per-provider semaphore. Prefer capability-chain labels such
        as ``realtime``, ``chip``, ``fundamental`` when the concrete provider
        is chosen inside the manager fallback chain.
    optional:
        When True, a ``None`` return is status ``gap`` (expected absence).
        When False, ``None`` is still recorded as ``gap`` but marked
        non-optional in diagnostics so stage policy can degrade explicitly.
    """

    key: str
    fn: Callable[[], Any]
    provider_key: str = "default"
    optional: bool = True


@dataclass(frozen=True)
class ParallelFetchLimits:
    """Concurrency and budget caps for one fan-out wave."""

    max_concurrent: int = 3
    per_provider_limit: int = 1
    # 0 or negative disables the coordinator-level wall-clock budget.
    budget_seconds: float = 0.0

    def normalized(self) -> "ParallelFetchLimits":
        return ParallelFetchLimits(
            max_concurrent=max(1, int(self.max_concurrent)),
            per_provider_limit=max(1, int(self.per_provider_limit)),
            budget_seconds=float(self.budget_seconds or 0.0),
        )


@dataclass
class FetchBranchResult:
    """Typed result for one branch after execution or skip."""

    key: str
    status: FetchBranchStatus
    value: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    provider_key: str = "default"
    optional: bool = True
    duration_ms: float = 0.0
    started: bool = False

    @property
    def ok(self) -> bool:
        return self.status is FetchBranchStatus.OK

    @property
    def is_gap(self) -> bool:
        return self.status in {
            FetchBranchStatus.GAP,
            FetchBranchStatus.ERROR,
            FetchBranchStatus.TIMEOUT,
            FetchBranchStatus.SKIPPED,
            FetchBranchStatus.BUDGET_SKIPPED,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "status": self.status.value,
            "error": self.error,
            "error_code": self.error_code,
            "provider_key": self.provider_key,
            "optional": self.optional,
            "duration_ms": round(self.duration_ms, 3),
            "started": self.started,
            "has_value": self.value is not None,
        }


@dataclass
class ParallelFetchReport:
    """Full wave report with deterministic merge order."""

    results: "OrderedDict[str, FetchBranchResult]" = field(default_factory=OrderedDict)
    enabled: bool = True
    mode: str = "parallel"  # "parallel" | "serial"
    max_in_flight_observed: int = 0
    elapsed_ms: float = 0.0
    budget_seconds: float = 0.0
    budget_exhausted: bool = False

    def values_by_key(self) -> "OrderedDict[str, Any]":
        """Return declared-order mapping of branch values (may include None)."""
        ordered: "OrderedDict[str, Any]" = OrderedDict()
        for key, branch in self.results.items():
            ordered[key] = branch.value
        return ordered

    def gaps(self) -> List[FetchBranchResult]:
        return [branch for branch in self.results.values() if branch.is_gap]

    def to_diagnostics(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "enabled": self.enabled,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "budget_seconds": self.budget_seconds,
            "budget_exhausted": self.budget_exhausted,
            "max_in_flight_observed": self.max_in_flight_observed,
            "branch_order": list(self.results.keys()),
            "branches": [branch.to_dict() for branch in self.results.values()],
            "gap_keys": [branch.key for branch in self.gaps()],
        }


class _ProviderGate:
    """Per-provider semaphore registry shared for one wave."""

    def __init__(self, per_provider_limit: int) -> None:
        self._limit = max(1, int(per_provider_limit))
        self._lock = threading.Lock()
        self._semaphores: Dict[str, threading.Semaphore] = {}

    def _sem(self, provider_key: str) -> threading.Semaphore:
        key = str(provider_key or "default")
        with self._lock:
            sem = self._semaphores.get(key)
            if sem is None:
                sem = threading.Semaphore(self._limit)
                self._semaphores[key] = sem
            return sem

    def run(self, provider_key: str, fn: Callable[[], Any]) -> Any:
        sem = self._sem(provider_key)
        acquired = sem.acquire(blocking=True)
        if not acquired:
            raise RuntimeError("provider semaphore acquire failed")
        try:
            return fn()
        finally:
            sem.release()


def _execute_task(
    task: FetchTask,
    provider_gate: Optional[_ProviderGate],
) -> FetchBranchResult:
    started = time.perf_counter()
    try:
        if provider_gate is None:
            value = task.fn()
        else:
            value = provider_gate.run(task.provider_key, task.fn)
        duration_ms = (time.perf_counter() - started) * 1000.0
        if value is None:
            return FetchBranchResult(
                key=task.key,
                status=FetchBranchStatus.GAP,
                value=None,
                error="branch returned no data",
                error_code="parallel_fetch_gap",
                provider_key=task.provider_key,
                optional=task.optional,
                duration_ms=duration_ms,
                started=True,
            )
        return FetchBranchResult(
            key=task.key,
            status=FetchBranchStatus.OK,
            value=value,
            provider_key=task.provider_key,
            optional=task.optional,
            duration_ms=duration_ms,
            started=True,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - isolate branch
        duration_ms = (time.perf_counter() - started) * 1000.0
        message = str(exc) or exc.__class__.__name__
        error_code = (
            "parallel_fetch_timeout"
            if "timeout" in message.lower()
            else "parallel_fetch_error"
        )
        status = (
            FetchBranchStatus.TIMEOUT
            if error_code == "parallel_fetch_timeout"
            else FetchBranchStatus.ERROR
        )
        log_safe_exception(
            logger,
            "Parallel fetch branch failed",
            exc,
            error_code=error_code,
            level=logging.WARNING,
            context={"branch_key": task.key, "status": status.value},
        )
        return FetchBranchResult(
            key=task.key,
            status=status,
            value=None,
            error=message,
            error_code=error_code,
            provider_key=task.provider_key,
            optional=task.optional,
            duration_ms=duration_ms,
            started=True,
        )


def _budget_skipped(task: FetchTask) -> FetchBranchResult:
    return FetchBranchResult(
        key=task.key,
        status=FetchBranchStatus.BUDGET_SKIPPED,
        value=None,
        error="total fetch budget exhausted before branch started",
        error_code="parallel_fetch_budget_skipped",
        provider_key=task.provider_key,
        optional=task.optional,
        duration_ms=0.0,
        started=False,
    )


def _run_serial(
    tasks: List[FetchTask],
    limits: ParallelFetchLimits,
) -> ParallelFetchReport:
    wave_started = time.perf_counter()
    budget = limits.budget_seconds
    deadline = (wave_started + budget) if budget > 0 else None
    results: "OrderedDict[str, FetchBranchResult]" = OrderedDict()
    budget_exhausted = False

    for task in tasks:
        if deadline is not None and time.perf_counter() >= deadline:
            budget_exhausted = True
            results[task.key] = _budget_skipped(task)
            continue
        results[task.key] = _execute_task(task, provider_gate=None)

    elapsed_ms = (time.perf_counter() - wave_started) * 1000.0
    return ParallelFetchReport(
        results=results,
        enabled=False,
        mode="serial",
        max_in_flight_observed=1 if tasks else 0,
        elapsed_ms=elapsed_ms,
        budget_seconds=budget,
        budget_exhausted=budget_exhausted,
    )


def _run_parallel(
    tasks: List[FetchTask],
    limits: ParallelFetchLimits,
) -> ParallelFetchReport:
    wave_started = time.perf_counter()
    budget = limits.budget_seconds
    deadline = (wave_started + budget) if budget > 0 else None
    provider_gate = _ProviderGate(limits.per_provider_limit)
    results: "OrderedDict[str, FetchBranchResult]" = OrderedDict(
        (
            task.key,
            FetchBranchResult(
                key=task.key,
                status=FetchBranchStatus.SKIPPED,
                provider_key=task.provider_key,
                optional=task.optional,
            ),
        )
        for task in tasks
    )
    budget_exhausted = False
    max_in_flight = 0
    in_flight = 0
    in_flight_lock = threading.Lock()

    def _tracked(task: FetchTask) -> FetchBranchResult:
        nonlocal max_in_flight, in_flight
        with in_flight_lock:
            in_flight += 1
            if in_flight > max_in_flight:
                max_in_flight = in_flight
        try:
            return _execute_task(task, provider_gate)
        finally:
            with in_flight_lock:
                in_flight -= 1

    workers = min(limits.max_concurrent, max(1, len(tasks)))
    pending: List[FetchTask] = list(tasks)
    futures: Dict[Future, FetchTask] = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        while pending or futures:
            if deadline is not None and time.perf_counter() >= deadline:
                budget_exhausted = True
                for task in pending:
                    results[task.key] = _budget_skipped(task)
                pending.clear()
                if not futures:
                    break
                done, _not_done = wait(list(futures.keys()), return_when=FIRST_COMPLETED)
                for future in done:
                    task = futures.pop(future)
                    results[task.key] = future.result()
                continue

            while pending and len(futures) < workers:
                if deadline is not None and time.perf_counter() >= deadline:
                    break
                task = pending.pop(0)
                futures[executor.submit(_tracked, task)] = task

            if not futures:
                if pending and deadline is not None and time.perf_counter() >= deadline:
                    budget_exhausted = True
                    for task in pending:
                        results[task.key] = _budget_skipped(task)
                    pending.clear()
                break

            timeout = None
            if deadline is not None:
                timeout = max(0.0, deadline - time.perf_counter())
            done, _not_done = wait(
                list(futures.keys()),
                timeout=timeout,
                return_when=FIRST_COMPLETED,
            )
            if not done:
                continue
            for future in done:
                task = futures.pop(future)
                results[task.key] = future.result()

    elapsed_ms = (time.perf_counter() - wave_started) * 1000.0
    ordered: "OrderedDict[str, FetchBranchResult]" = OrderedDict()
    for task in tasks:
        ordered[task.key] = results[task.key]
    return ParallelFetchReport(
        results=ordered,
        enabled=True,
        mode="parallel",
        max_in_flight_observed=max_in_flight,
        elapsed_ms=elapsed_ms,
        budget_seconds=budget,
        budget_exhausted=budget_exhausted,
    )


def run_parallel_fetches(
    tasks: Iterable[FetchTask],
    *,
    enabled: bool = True,
    limits: Optional[ParallelFetchLimits] = None,
) -> ParallelFetchReport:
    """Run independent fetch tasks with guardrails.

    Empty task lists return an empty report. Duplicate keys raise ``ValueError``
    so merge order cannot silently overwrite branches.
    """
    task_list = list(tasks)
    if not task_list:
        return ParallelFetchReport(
            results=OrderedDict(),
            enabled=bool(enabled),
            mode="serial" if not enabled else "parallel",
        )

    seen: set[str] = set()
    for task in task_list:
        if not task.key:
            raise ValueError("FetchTask.key must be non-empty")
        if task.key in seen:
            raise ValueError(f"duplicate FetchTask key: {task.key!r}")
        seen.add(task.key)

    normalized = (limits or ParallelFetchLimits()).normalized()
    if not enabled:
        return _run_serial(task_list, normalized)
    return _run_parallel(task_list, normalized)


def merge_branch_values(
    report: ParallelFetchReport,
    *,
    keys: Optional[Iterable[str]] = None,
) -> "OrderedDict[str, Any]":
    """Deterministic value merge helper for AgentContext / stage IO.

    Iterates ``keys`` when provided, otherwise the report's declaration order.
    Missing keys are omitted (callers that need explicit None should use
    ``report.values_by_key()``).
    """
    ordered: "OrderedDict[str, Any]" = OrderedDict()
    source_keys = list(keys) if keys is not None else list(report.results.keys())
    for key in source_keys:
        branch = report.results.get(key)
        if branch is None:
            continue
        ordered[key] = branch.value
    return ordered


def limits_from_config(config: Any) -> ParallelFetchLimits:
    """Build limits from a Config-like object with graceful defaults."""
    return ParallelFetchLimits(
        max_concurrent=int(getattr(config, "analysis_parallel_fetch_max_concurrent", 3) or 3),
        per_provider_limit=int(
            getattr(config, "analysis_parallel_fetch_per_provider_limit", 1) or 1
        ),
        budget_seconds=float(
            getattr(config, "analysis_parallel_fetch_budget_seconds", 0.0) or 0.0
        ),
    ).normalized()


def is_parallel_fetch_enabled(config: Any) -> bool:
    """Return whether analysis parallel fetch is enabled on config."""
    return bool(getattr(config, "analysis_parallel_fetch_enabled", True))
