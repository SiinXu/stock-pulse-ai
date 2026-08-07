# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic restart-recovery contracts for AnalysisTaskQueue."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from src.services.task_queue import AnalysisTaskQueue, TaskStatus
from src.task_execution import TaskCommand, TaskNotFoundError


class DeferredExecutor:
    """Capture submitted work without running it until the test asks."""

    def __init__(self) -> None:
        self.calls: List[Any] = []
        self.shutdown_calls: List[Any] = []

    def submit(self, fn, *args, **kwargs):
        future: Future = Future()
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


@dataclass
class MemoryInflightStore:
    """In-memory checkpoint port simulating durable SQLite across process loss."""

    rows: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def try_upsert(self, fields: Dict[str, Any]) -> bool:
        task_id = str(fields["task_id"])
        payload = dict(fields)
        payload["metadata"] = dict(fields.get("metadata") or {})
        if "created_at" not in payload or payload["created_at"] is None:
            payload["created_at"] = datetime.now()
        payload["updated_at"] = payload.get("updated_at") or datetime.now()
        self.rows[task_id] = payload
        return True

    def try_delete(self, task_id: str) -> bool:
        self.rows.pop(str(task_id), None)
        return True

    def list_inflight(self) -> List[Any]:
        items = []
        for row in self.rows.values():
            items.append(
                SimpleNamespace(
                    task_id=row["task_id"],
                    kind=row["kind"],
                    status=row["status"],
                    stock_code=row.get("stock_code"),
                    recovery_class=row["recovery_class"],
                    dedupe_key=row.get("dedupe_key"),
                    idempotency_key=row.get("idempotency_key"),
                    idempotency_fingerprint=row.get("idempotency_fingerprint"),
                    failure_error_code=row.get("failure_error_code"),
                    none_is_success=bool(row.get("none_is_success", False)),
                    metadata=dict(row.get("metadata") or {}),
                    created_at=row.get("created_at") or datetime.now(),
                    updated_at=row.get("updated_at") or datetime.now(),
                )
            )
        return items


def _new_queue(store: MemoryInflightStore) -> AnalysisTaskQueue:
    AnalysisTaskQueue._instance = None
    queue = AnalysisTaskQueue(max_workers=2, inflight_store=store)
    queue._executor = DeferredExecutor()
    return queue


def _drop_queue(queue: AnalysisTaskQueue) -> None:
    """Simulate ungraceful process loss: abandon memory without terminalizing."""
    del queue
    AnalysisTaskQueue._instance = None


@pytest.fixture
def inflight_store() -> MemoryInflightStore:
    return MemoryInflightStore()


def test_recovery_matrix_classifies_kinds() -> None:
    assert AnalysisTaskQueue.recovery_class_for_kind("stock_analysis") == "requeue"
    assert AnalysisTaskQueue.recovery_class_for_kind("local_model_pull") == "interrupt"
    assert AnalysisTaskQueue.recovery_class_for_kind("model_pack_import") == "interrupt"
    assert AnalysisTaskQueue.recovery_class_for_kind("market_review") == "interrupt"
    assert AnalysisTaskQueue.recovery_class_for_kind("background") == "interrupt"


def test_inflight_stock_analysis_is_requeued_after_simulated_restart(
    inflight_store: MemoryInflightStore,
) -> None:
    queue = _new_queue(inflight_store)
    task = queue.submit_task("600519", stock_name="Moutai", force_refresh=True)
    task_id = task.task_id
    assert task_id in inflight_store.rows
    assert inflight_store.rows[task_id]["recovery_class"] == "requeue"
    assert inflight_store.rows[task_id]["status"] == TaskStatus.PENDING.value

    _drop_queue(queue)

    recovered = _new_queue(inflight_store)
    stats = recovered.recover_persisted_inflight()
    assert stats["requeued"] == 1
    assert stats["interrupted"] == 0

    restored = recovered.get_task(task_id)
    assert restored is not None
    assert restored.status in {TaskStatus.PENDING, TaskStatus.PROCESSING}
    assert restored.message_code == "task.recovered.requeued"
    assert restored.stock_code == "600519"
    assert len(recovered._executor.calls) == 1

    recovered.shutdown()
    AnalysisTaskQueue._instance = None


def test_inflight_non_idempotent_is_interrupted_after_restart(
    inflight_store: MemoryInflightStore,
) -> None:
    queue = _new_queue(inflight_store)
    task = queue.submit_background_task(
        lambda: {"ok": True},
        stock_code="LOCAL",
        report_type="local_model_pull",
        message="pulling",
    )
    task_id = task.task_id
    assert inflight_store.rows[task_id]["recovery_class"] == "interrupt"

    _drop_queue(queue)

    recovered = _new_queue(inflight_store)
    stats = recovered.recover_persisted_inflight()
    assert stats["interrupted"] == 1
    assert stats["requeued"] == 0

    restored = recovered.get_task(task_id)
    assert restored is not None
    assert restored.status == TaskStatus.INTERRUPTED
    assert restored.message_code == "task.interrupted.process_restart"
    assert task_id not in inflight_store.rows
    assert recovered._executor.calls == []

    recovered.shutdown()
    AnalysisTaskQueue._instance = None


def test_completed_task_is_not_resurrected(
    inflight_store: MemoryInflightStore,
) -> None:
    queue = _new_queue(inflight_store)
    task = queue.submit_task("000001")
    task_id = task.task_id
    assert task_id in inflight_store.rows

    command = queue._commands[task_id]
    queue._commands[task_id] = TaskCommand(
        kind=command.kind,
        run=lambda _context: {"result_ref": "hist-1", "stock_name": "PingAn"},
        metadata=command.metadata,
        dedupe_key=command.dedupe_key,
        idempotency_key=command.idempotency_key,
        idempotency_fingerprint=command.idempotency_fingerprint,
        failure_error_code=command.failure_error_code,
        none_is_success=False,
        retry_factory=command.retry_factory,
    )
    queue._executor.run(0)

    completed = queue.get_task(task_id)
    assert completed is not None
    assert completed.status == TaskStatus.COMPLETED
    assert task_id not in inflight_store.rows

    _drop_queue(queue)
    recovered = _new_queue(inflight_store)
    stats = recovered.recover_persisted_inflight()
    assert stats == {"requeued": 0, "interrupted": 0, "skipped": 0}
    with pytest.raises(TaskNotFoundError):
        recovered.get(task_id)

    recovered.shutdown()
    AnalysisTaskQueue._instance = None


def test_scheduler_reconcile_does_not_double_fire_after_recovery(
    inflight_store: MemoryInflightStore,
) -> None:
    """Restored same task id stays non-terminal so schedule occurrence is not lost."""
    queue = _new_queue(inflight_store)
    task = queue.submit_task("600519")
    task_id = task.task_id
    _drop_queue(queue)

    recovered = _new_queue(inflight_store)
    recovered.recover_persisted_inflight()
    snapshot = recovered.get(task_id)
    assert not snapshot.status.terminal

    class FakeScheduledService:
        def __init__(self) -> None:
            self.finished: List[Any] = []
            self.dispatched = 0

        def reconcile_like_production(self) -> str:
            try:
                current = recovered.get(task_id)
            except TaskNotFoundError:
                self.finished.append("execution_state_lost")
                return "interrupted_lost"
            if not current.status.terminal:
                return "wait"
            self.finished.append(current.status.value)
            self.dispatched += 1
            return "terminal_seen"

    service = FakeScheduledService()
    assert service.reconcile_like_production() == "wait"
    assert service.finished == []
    assert service.dispatched == 0
    assert len(recovered._executor.calls) == 1

    recovered.shutdown()
    AnalysisTaskQueue._instance = None


def test_graceful_shutdown_clears_checkpoints_without_requeue(
    inflight_store: MemoryInflightStore,
) -> None:
    queue = _new_queue(inflight_store)
    task = queue.submit_task("600519")
    task_id = task.task_id
    queue.shutdown()
    assert queue.get_task(task_id).status == TaskStatus.INTERRUPTED
    assert task_id not in inflight_store.rows

    AnalysisTaskQueue._instance = None
    recovered = _new_queue(inflight_store)
    stats = recovered.recover_persisted_inflight()
    assert stats["requeued"] == 0
    assert stats["interrupted"] == 0

    recovered.shutdown()
    AnalysisTaskQueue._instance = None


def test_processing_checkpoint_status_is_persisted(
    inflight_store: MemoryInflightStore,
) -> None:
    queue = _new_queue(inflight_store)
    task = queue.submit_task("600519")
    task_id = task.task_id
    with queue._data_lock:
        claimed = queue._claim_task_locked(task_id)
    assert claimed is not None
    assert inflight_store.rows[task_id]["status"] == TaskStatus.PROCESSING.value

    queue.shutdown()
    AnalysisTaskQueue._instance = None
