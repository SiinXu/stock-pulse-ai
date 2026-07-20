# -*- coding: utf-8 -*-
"""Focused contracts for the process-local task execution port."""

import asyncio
import gc
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from src.services.task_queue import (
    AnalysisTaskQueue,
    DuplicateTaskError,
    TaskStatus,
)
from src.task_execution import (
    TaskCommand,
    TaskEvent,
    TaskEventType,
    TaskExecutionPort,
    TaskIdempotencyConflictError,
    TaskNotFoundError,
    TaskQueueShutdownError,
    TaskRetryNotAllowedError,
    TaskRetryUnsupportedError,
    TaskStatusEnum,
    TaskStreamOverflowError,
    deep_thaw,
)


class DeferredExecutor:
    """Capture submitted calls and run them deterministically from a test."""

    def __init__(self) -> None:
        self.calls = []
        self.shutdown_calls = []

    def submit(self, fn, *args, **kwargs):
        future = Future()
        self.calls.append((fn, args, kwargs, future))
        return future

    def run(self, index: int = 0):
        fn, args, kwargs, future = self.calls[index]
        if not future.set_running_or_notify_cancel():
            return None
        try:
            result = fn(*args, **kwargs)
        except BaseException as exc:  # pragma: no cover - queue absorbs runner failures
            future.set_exception(exc)
            return None
        future.set_result(result)
        return result

    def shutdown(self, wait=True, cancel_futures=False) -> None:
        self.shutdown_calls.append((wait, cancel_futures))
        if cancel_futures:
            for _fn, _args, _kwargs, future in self.calls:
                future.cancel()


class SynchronousExecutor:
    """Execute immediately while returning a completed Future."""

    def submit(self, fn, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # pragma: no cover - queue absorbs runner failures
            future.set_exception(exc)
        return future

    def shutdown(self, wait=True, cancel_futures=False) -> None:
        del wait, cancel_futures


class ClaimedExecutor(DeferredExecutor):
    """Return an already-running Future while deferring the callable body."""

    def submit(self, fn, *args, **kwargs):
        future = Future()
        future.set_running_or_notify_cancel()
        self.calls.append((fn, args, kwargs, future))
        return future

    def run(self, index: int = 0):
        fn, args, kwargs, future = self.calls[index]
        result = fn(*args, **kwargs)
        future.set_result(result)
        return result


class SelfCopyingMutable:
    """Mutable test value that tries to defeat copy-based detachment."""

    def __init__(self) -> None:
        self.items = []

    def __deepcopy__(self, memo):
        del memo
        return self


class TransformingDeepcopyMutable:
    """Unsupported value whose deepcopy result tries to look supported."""

    def __deepcopy__(self, memo):
        del memo
        return {"escaped": True}


@pytest.fixture
def task_queue():
    original = AnalysisTaskQueue._instance
    AnalysisTaskQueue._instance = None
    queue = AnalysisTaskQueue(max_workers=2)
    try:
        yield queue
    finally:
        queue.shutdown()
        AnalysisTaskQueue._instance = original


def make_command(run, **overrides) -> TaskCommand:
    values = {
        "kind": "unit_test",
        "run": run,
        "metadata": {"stock_code": "UNIT"},
    }
    values.update(overrides)
    return TaskCommand(**values)


def test_status_order_and_contract_values_are_canonical() -> None:
    assert TaskStatus is TaskStatusEnum
    assert [status.value for status in TaskStatusEnum] == [
        "pending",
        "processing",
        "cancel_requested",
        "completed",
        "failed",
        "cancelled",
        "interrupted",
    ]


def test_queue_implements_task_execution_port(task_queue) -> None:
    assert isinstance(task_queue, TaskExecutionPort)


def test_command_and_snapshots_detach_mutable_values(task_queue) -> None:
    executor = DeferredExecutor()
    task_queue._executor = executor
    metadata = {"stock_code": "UNIT", "nested": {"items": [1]}}
    command = make_command(lambda _context: {"ok": True}, metadata=metadata)
    metadata["nested"]["items"].append(2)

    task_id = task_queue.submit(command)
    snapshot = task_queue.get(task_id)

    assert deep_thaw(command.metadata) == {
        "stock_code": "UNIT",
        "nested": {"items": [1]},
    }
    with pytest.raises(FrozenInstanceError):
        snapshot.progress = 42


def test_command_metadata_rejects_self_copying_custom_values() -> None:
    with pytest.raises(TypeError, match="SelfCopyingMutable"):
        make_command(
            lambda _context: None,
            metadata={"stock_code": "UNIT", "nested": SelfCopyingMutable()},
            idempotency_fingerprint="explicit-fingerprint",
        )


def test_event_data_rejects_self_copying_custom_values(task_queue) -> None:
    executor = DeferredExecutor()
    task_queue._executor = executor
    task_id = task_queue.submit(make_command(lambda _context: None))

    with pytest.raises(TypeError, match="SelfCopyingMutable"):
        TaskEvent(
            sequence=1,
            task_id=task_id,
            type=TaskEventType.PROGRESS,
            snapshot=task_queue.get(task_id),
            data={"nested": SelfCopyingMutable()},
        )


def test_queue_event_data_validates_original_value_before_copying(task_queue) -> None:
    executor = DeferredExecutor()
    task_queue._executor = executor
    task_id = task_queue.submit(make_command(lambda _context: None))

    with pytest.raises(TypeError, match="TransformingDeepcopyMutable"):
        task_queue._broadcast_event(
            "task_progress",
            {"task_id": task_id, "nested": TransformingDeepcopyMutable()},
        )


def test_idempotent_submit_reuses_owner_without_event_or_executor(task_queue) -> None:
    executor = DeferredExecutor()
    task_queue._executor = executor
    events = []
    task_queue._broadcast_event = lambda event_type, data: events.append((event_type, data))
    first = make_command(
        lambda _context: {"ok": True},
        idempotency_key="same-request",
    )
    equivalent = make_command(
        lambda _context: {"different_runner": True},
        idempotency_key="same-request",
    )

    task_id = task_queue.submit(first)
    assert task_queue.submit(equivalent) == task_id
    assert len(executor.calls) == 1
    assert [event_type for event_type, _data in events] == ["task_created"]

    conflicting = make_command(
        lambda _context: None,
        metadata={"stock_code": "OTHER"},
        idempotency_key="same-request",
    )
    with pytest.raises(TaskIdempotencyConflictError) as exc_info:
        task_queue.submit(conflicting)
    assert exc_info.value.existing_task_id == task_id


def test_generic_none_succeeds_but_legacy_background_none_fails(task_queue) -> None:
    task_queue._executor = SynchronousExecutor()

    generic_id = task_queue.submit(make_command(lambda _context: None))
    background = task_queue.submit_background_task(
        lambda: None,
        stock_code="market_review",
    )

    assert task_queue.get(generic_id).status == TaskStatus.COMPLETED
    assert task_queue.get(background.task_id).status == TaskStatus.FAILED
    with pytest.raises(TaskRetryUnsupportedError):
        task_queue.retry(background.task_id)


def test_synchronous_executor_preserves_created_before_lifecycle_events(
    task_queue,
    monkeypatch,
) -> None:
    class AnalysisServiceStub:
        last_error = None

        def analyze_stock(self, **kwargs):
            return {"stock_code": kwargs["stock_code"]}

    monkeypatch.setitem(
        sys.modules,
        "src.services.analysis_service",
        SimpleNamespace(AnalysisService=AnalysisServiceStub),
    )
    task_queue._executor = SynchronousExecutor()

    first_id = task_queue.submit(make_command(lambda _context: {"ok": 1}))
    accepted, duplicates = task_queue.submit_tasks_batch(["600519", "000858"])

    first_types = [event.type for event in task_queue._event_history[first_id]]
    assert first_types == [
        TaskEventType.CREATED,
        TaskEventType.STARTED,
        TaskEventType.COMPLETED,
    ]
    assert duplicates == []
    batch_events = sorted(
        (
            event
            for task in accepted
            for event in task_queue._event_history[task.task_id]
        ),
        key=lambda event: event.sequence,
    )
    assert [event.type for event in batch_events[:2]] == [
        TaskEventType.CREATED,
        TaskEventType.CREATED,
    ]


def test_batch_executor_failure_rolls_back_without_delivering_staged_events(task_queue) -> None:
    class FailSecondExecutor(DeferredExecutor):
        def submit(self, fn, *args, **kwargs):
            if len(self.calls) == 1:
                raise RuntimeError("executor unavailable")
            return super().submit(fn, *args, **kwargs)

    executor = FailSecondExecutor()
    task_queue._executor = executor
    delivered = []
    task_queue._schedule_event_locked = delivered.append

    with pytest.raises(RuntimeError, match="executor unavailable"):
        task_queue.submit_tasks_batch(["600519", "000858"])

    assert delivered == []
    assert task_queue._tasks == {}
    assert task_queue._commands == {}
    assert task_queue._task_dedupe_keys == {}
    assert task_queue._analyzing_stocks == {}
    assert task_queue._futures == {}
    assert task_queue._idempotency_index == {}
    assert task_queue._suppressed_event_tasks == set()
    assert task_queue._suppressed_events == {}


def test_uncopyable_result_becomes_failed_without_completed_event(task_queue) -> None:
    class UncopyableResult:
        def __deepcopy__(self, memo):
            del memo
            raise RuntimeError("cannot detach result")

    task_queue._executor = SynchronousExecutor()
    task_id = task_queue.submit(make_command(lambda _context: UncopyableResult()))

    assert task_queue.get(task_id).status == TaskStatus.FAILED
    terminal_events = [
        event
        for event in task_queue._event_history[task_id]
        if event.terminal
    ]
    assert [event.type for event in terminal_events] == [TaskEventType.FAILED]


def test_nested_self_copying_result_becomes_failed_without_aliasing(task_queue) -> None:
    shared = SelfCopyingMutable()
    task_queue._executor = SynchronousExecutor()
    task_id = task_queue.submit(
        make_command(lambda _context: {"nested": {"shared": shared}})
    )

    assert task_queue.get(task_id).status == TaskStatus.FAILED
    assert task_queue.get_task(task_id).result is None
    shared.items.append("late mutation")
    assert task_queue.get_task(task_id).result is None
    terminal_events = [
        event
        for event in task_queue._event_history[task_id]
        if event.terminal
    ]
    assert [event.type for event in terminal_events] == [TaskEventType.FAILED]


def test_prestart_cancel_never_invokes_runner_and_rejects_late_updates(task_queue) -> None:
    executor = DeferredExecutor()
    task_queue._executor = executor
    invoked = []
    task_id = task_queue.submit(make_command(lambda _context: invoked.append(True)))

    snapshot = task_queue.cancel(task_id)

    assert snapshot.status == TaskStatus.CANCELLED
    assert executor.run() is None
    assert invoked == []
    assert task_queue.update_task_progress(task_id, 50, "late") is None
    assert task_queue.append_task_flow_event(task_id, {"late": True}) is None
    assert task_queue._task_lifecycle_pins == {}
    terminal_events = [event for event in task_queue._event_history[task_id] if event.terminal]
    assert [event.type for event in terminal_events] == [TaskEventType.CANCELLED]


def test_worker_claimed_prestart_cancel_runs_cleanup(task_queue) -> None:
    executor = ClaimedExecutor()
    task_queue._executor = executor
    task_queue._max_history = 0
    invoked = []
    task_id = task_queue.submit(make_command(lambda _context: invoked.append(True)))

    assert task_queue.cancel(task_id).status == TaskStatus.CANCEL_REQUESTED
    executor.run()

    assert invoked == []
    assert task_id not in task_queue._tasks
    assert task_id not in task_queue._commands
    assert task_id not in task_queue._futures
    assert task_id not in task_queue._event_history
    assert task_id not in task_queue._task_idempotency_keys


def test_concurrent_cancel_callers_keep_claimed_task_pinned_until_snapshots(
    task_queue,
) -> None:
    cancel_lock = threading.Lock()
    all_cancel_callers_entered = threading.Event()
    release_cancel = threading.Event()
    cancel_callers = 0

    class BlockingCancelFuture(Future):
        def cancel(self) -> bool:
            nonlocal cancel_callers
            with cancel_lock:
                cancel_callers += 1
                if cancel_callers == 2:
                    all_cancel_callers_entered.set()
            assert release_cancel.wait(timeout=2)
            return False

    class BlockingClaimedExecutor(ClaimedExecutor):
        def submit(self, fn, *args, **kwargs):
            future = BlockingCancelFuture()
            future.set_running_or_notify_cancel()
            self.calls.append((fn, args, kwargs, future))
            return future

    executor = BlockingClaimedExecutor()
    task_queue._executor = executor
    task_queue._max_history = 0
    task_id = task_queue.submit(make_command(lambda _context: {"ok": True}))
    snapshots = []
    errors = []

    def cancel() -> None:
        try:
            snapshots.append(task_queue.cancel(task_id))
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    callers = [threading.Thread(target=cancel) for _ in range(2)]
    for caller in callers:
        caller.start()
    try:
        assert all_cancel_callers_entered.wait(timeout=2)
        executor.run()
        assert task_id in task_queue._tasks
        assert task_queue._task_lifecycle_pins[task_id] == 2
    finally:
        release_cancel.set()
        for caller in callers:
            caller.join(timeout=2)

    assert errors == []
    assert len(snapshots) == 2
    assert all(snapshot.status == TaskStatus.CANCELLED for snapshot in snapshots)
    assert task_id not in task_queue._tasks
    assert task_queue._task_lifecycle_pins == {}


def test_cancel_wins_over_late_completion_with_one_terminal_event(task_queue) -> None:
    started = threading.Event()
    release = threading.Event()

    def run(context):
        started.set()
        assert release.wait(timeout=2)
        return {"ok": True, "cancel_seen": context.is_cancel_requested()}

    task_id = task_queue.submit(make_command(run))
    assert started.wait(timeout=2)
    assert task_queue.cancel(task_id).status == TaskStatus.CANCEL_REQUESTED
    release.set()
    task_queue._futures[task_id].result(timeout=2)

    assert task_queue.get(task_id).status == TaskStatus.CANCELLED
    terminal_events = [event for event in task_queue._event_history[task_id] if event.terminal]
    assert [event.type for event in terminal_events] == [TaskEventType.CANCELLED]


def test_completed_task_rejects_retry(task_queue) -> None:
    task_queue._executor = SynchronousExecutor()
    task_id = task_queue.submit(make_command(lambda _context: {"ok": True}))

    with pytest.raises(TaskRetryNotAllowedError):
        task_queue.retry(task_id)


def test_concurrent_retry_callers_share_child_under_synchronous_cleanup_pressure(
    task_queue,
) -> None:
    task_queue._executor = SynchronousExecutor()
    task_queue._max_history = 1
    factory_entered = threading.Event()
    release_factory = threading.Event()
    factory_calls = []

    def retry_factory() -> TaskCommand:
        factory_calls.append(True)
        factory_entered.set()
        assert release_factory.wait(timeout=2)
        return make_command(
            lambda _context: {"ok": True},
            kind="ignored_kind",
            metadata={"stock_code": "IGNORED"},
            dedupe_key="ignored_dedupe",
        )

    parent_command = make_command(
        lambda _context: (_ for _ in ()).throw(RuntimeError("first run failed")),
        dedupe_key="shared-dedupe",
        retry_factory=retry_factory,
    )
    parent_id = task_queue.submit(parent_command)
    assert task_queue.get(parent_id).status == TaskStatus.FAILED

    child_ids = []
    errors = []

    def retry() -> None:
        try:
            child_ids.append(task_queue.retry(parent_id))
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    owner = threading.Thread(target=retry)
    waiter = threading.Thread(target=retry)
    owner.start()
    assert factory_entered.wait(timeout=2)
    waiter.start()
    release_factory.set()
    owner.join(timeout=2)
    waiter.join(timeout=2)

    assert errors == []
    assert len(factory_calls) == 1
    assert len(set(child_ids)) == 1
    child_id = child_ids[0]
    child_command = task_queue._commands[child_id]
    assert child_command.kind == parent_command.kind
    assert child_command.dedupe_key == parent_command.dedupe_key
    assert child_command.idempotency_fingerprint == parent_command.idempotency_fingerprint
    assert child_command.idempotency_key != parent_command.idempotency_key
    assert task_queue.get(child_id).trace_id == child_id
    assert parent_id not in task_queue._tasks
    assert child_id in task_queue._tasks
    assert task_queue._retry_children == {}
    assert task_queue._task_lifecycle_pins == {}


def test_retry_executor_failure_rolls_back_reserved_child_and_pin(task_queue) -> None:
    class RejectingExecutor:
        def submit(self, fn, *args, **kwargs):
            del fn, args, kwargs
            raise RuntimeError("executor unavailable")

        def shutdown(self, wait=True, cancel_futures=False) -> None:
            del wait, cancel_futures

    task_queue._executor = SynchronousExecutor()
    parent_id = task_queue.submit(
        make_command(
            lambda _context: (_ for _ in ()).throw(RuntimeError("failed")),
            retry_factory=lambda: make_command(lambda _context: {"ok": True}),
        )
    )
    task_queue._executor = RejectingExecutor()

    with pytest.raises(RuntimeError, match="executor unavailable"):
        task_queue.retry(parent_id)

    assert set(task_queue._tasks) == {parent_id}
    assert task_queue._retry_reservations == {}
    assert task_queue._retry_children == {}
    assert task_queue._task_lifecycle_pins == {}


def test_shutdown_wakes_retry_owner_and_waiter_with_same_error(task_queue) -> None:
    task_queue._executor = SynchronousExecutor()
    factory_entered = threading.Event()
    release_factory = threading.Event()

    def retry_factory() -> TaskCommand:
        factory_entered.set()
        assert release_factory.wait(timeout=2)
        return make_command(lambda _context: {"ok": True})

    parent_id = task_queue.submit(
        make_command(
            lambda _context: (_ for _ in ()).throw(RuntimeError("failed")),
            retry_factory=retry_factory,
        )
    )
    errors = []

    def retry() -> None:
        try:
            task_queue.retry(parent_id)
        except BaseException as exc:
            errors.append(exc)

    owner = threading.Thread(target=retry)
    waiter = threading.Thread(target=retry)
    owner.start()
    assert factory_entered.wait(timeout=2)
    waiter.start()
    task_queue.shutdown()
    release_factory.set()
    owner.join(timeout=2)
    waiter.join(timeout=2)

    assert len(errors) == 2
    assert all(isinstance(error, TaskQueueShutdownError) for error in errors)
    assert parent_id not in task_queue._retry_reservations


def test_retry_preserves_unrelated_dedupe_collision(task_queue) -> None:
    task_queue._executor = SynchronousExecutor()

    def retry_factory() -> TaskCommand:
        return make_command(lambda _context: {"ok": True})

    parent_id = task_queue.submit(
        make_command(
            lambda _context: (_ for _ in ()).throw(RuntimeError("failed")),
            dedupe_key="shared-dedupe",
            retry_factory=retry_factory,
        )
    )
    deferred = DeferredExecutor()
    task_queue._executor = deferred
    unrelated_id = task_queue.submit(
        make_command(lambda _context: {"ok": True}, dedupe_key="shared-dedupe")
    )

    with pytest.raises(DuplicateTaskError) as exc_info:
        task_queue.retry(parent_id)
    assert exc_info.value.existing_task_id == unrelated_id
    assert parent_id not in task_queue._retry_reservations
    assert task_queue._task_lifecycle_pins == {}


def test_task_stream_replays_snapshot_times_out_and_reaches_terminal_eof(task_queue) -> None:
    executor = DeferredExecutor()
    task_queue._executor = executor
    task_id = task_queue.submit(make_command(lambda _context: {"ok": True}))

    async def scenario() -> None:
        stream = task_queue.subscribe(task_id)
        replay = await stream.receive()
        assert replay.type == TaskEventType.SNAPSHOT
        assert replay.snapshot.status == TaskStatus.PENDING

        with pytest.raises(asyncio.TimeoutError):
            await stream.receive(timeout=0.001)
        assert stream.token in task_queue._streams

        task_queue.update_task_progress(task_id, 40, "running")
        await asyncio.sleep(0)
        progress = await stream.receive(timeout=1)
        assert progress.type == TaskEventType.PROGRESS
        assert deep_thaw(progress.data)["progress"] == 40

        task_queue.cancel(task_id)
        await asyncio.sleep(0)
        cancel_requested = await stream.receive(timeout=1)
        cancelled = await stream.receive(timeout=1)
        assert cancel_requested.type == TaskEventType.CANCEL_REQUESTED
        assert cancelled.type == TaskEventType.CANCELLED
        with pytest.raises(StopAsyncIteration):
            await stream.receive()
        assert stream.token not in task_queue._streams

    asyncio.run(scenario())


def test_terminal_stream_replays_once_and_unknown_task_is_stable(task_queue) -> None:
    task_queue._executor = SynchronousExecutor()
    task_id = task_queue.submit(make_command(lambda _context: {"ok": True}))

    async def scenario() -> None:
        stream = task_queue.subscribe(task_id)
        replay = await stream.receive()
        assert replay.type == TaskEventType.SNAPSHOT
        assert replay.snapshot.status == TaskStatus.COMPLETED
        with pytest.raises(StopAsyncIteration):
            await stream.receive()
        with pytest.raises(TaskNotFoundError):
            task_queue.subscribe("missing-task")

    asyncio.run(scenario())


def test_abandoned_task_and_global_streams_are_not_retained(task_queue) -> None:
    executor = DeferredExecutor()
    task_queue._executor = executor
    task_id = task_queue.submit(make_command(lambda _context: {"ok": True}))

    async def create_and_abandon_streams():
        task_stream = task_queue.subscribe(task_id)
        global_stream = task_queue.subscribe_all()
        tokens = (task_stream.token, global_stream.token)
        assert all(token in task_queue._streams for token in tokens)
        return tokens

    tokens = asyncio.run(create_and_abandon_streams())
    gc.collect()

    assert all(token not in task_queue._streams for token in tokens)


def test_slow_stream_is_detached_with_overflow_error(task_queue) -> None:
    executor = DeferredExecutor()
    task_queue._executor = executor
    task_queue._event_stream_queue_size = 1
    task_id = task_queue.submit(make_command(lambda _context: {"ok": True}))

    async def scenario() -> None:
        stream = task_queue.subscribe(task_id)
        task_queue.update_task_progress(task_id, 20, "overflow")
        await asyncio.sleep(0)
        with pytest.raises(TaskStreamOverflowError):
            await stream.receive()
        assert stream.token not in task_queue._streams

    asyncio.run(scenario())


def test_global_stream_overflow_is_explicit_instead_of_normal_terminal_eof(task_queue) -> None:
    executor = DeferredExecutor()
    task_queue._executor = executor
    task_queue._event_stream_queue_size = 1

    async def scenario() -> None:
        stream = task_queue.subscribe_all()
        task_queue.submit(make_command(lambda _context: {"ok": True}))
        executor.run()
        await asyncio.sleep(0)
        with pytest.raises(TaskStreamOverflowError):
            await stream.receive()
        assert stream.token not in task_queue._streams

    asyncio.run(scenario())


def test_shutdown_interrupts_tasks_exposes_error_and_closes_stream(task_queue) -> None:
    executor = DeferredExecutor()
    task_queue._executor = executor
    task_id = task_queue.submit(make_command(lambda _context: {"ok": True}))

    async def scenario() -> None:
        stream = task_queue.subscribe(task_id)
        replay = await stream.receive()
        assert replay.type == TaskEventType.SNAPSHOT

        task_queue.shutdown()
        await asyncio.sleep(0)
        interrupted = await stream.receive(timeout=1)
        assert interrupted.type == TaskEventType.INTERRUPTED
        assert interrupted.snapshot.error_code == "task_interrupted"
        with pytest.raises(StopAsyncIteration):
            await stream.receive()

    asyncio.run(scenario())

    snapshot = task_queue.get(task_id)
    assert snapshot.status == TaskStatus.INTERRUPTED
    assert snapshot.error_code == "task_interrupted"
    assert task_queue._is_cancel_requested(task_id)
    assert executor.shutdown_calls == [(False, True)]
    with pytest.raises(TaskQueueShutdownError):
        task_queue.submit(make_command(lambda _context: None))


def test_real_thread_pool_shutdown_returns_before_blocked_runner_exits(task_queue) -> None:
    started = threading.Event()
    release = threading.Event()
    cancellation_observations = []
    task_queue._executor = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="task_shutdown_test_",
    )

    def run(context):
        started.set()
        assert release.wait(timeout=5)
        cancellation_observations.append(context.is_cancel_requested())
        return {"ok": True}

    task_id = task_queue.submit(make_command(run))
    future = task_queue._futures[task_id]
    assert started.wait(timeout=2)

    try:
        before = time.monotonic()
        task_queue.shutdown()
        elapsed = time.monotonic() - before

        assert elapsed < 1
        assert task_queue.get(task_id).status == TaskStatus.INTERRUPTED
    finally:
        release.set()
        future.result(timeout=2)

    assert cancellation_observations == [True]


def test_cleanup_removes_all_owner_indexes(task_queue) -> None:
    task_queue._executor = SynchronousExecutor()
    task_queue._max_history = 1
    first = make_command(
        lambda _context: (_ for _ in ()).throw(RuntimeError("first")),
        idempotency_key="first-key",
    )
    second = make_command(
        lambda _context: (_ for _ in ()).throw(RuntimeError("second")),
        idempotency_key="second-key",
    )

    first_id = task_queue.submit(first)
    second_id = task_queue.submit(second)

    assert first_id not in task_queue._tasks
    assert first_id not in task_queue._commands
    assert first_id not in task_queue._futures
    assert first_id not in task_queue._event_history
    assert first_id not in task_queue._task_idempotency_keys
    assert "first-key" not in task_queue._idempotency_index
    assert second_id in task_queue._tasks
