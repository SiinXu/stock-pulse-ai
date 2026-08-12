# -*- coding: utf-8 -*-
"""In-memory state, event streams, and lifecycle store helpers for AnalysisTaskQueue."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.task_queue import (
        Any,
        Dict,
        List,
        TaskEvent,
        TaskEventType,
        TaskInfo,
        TaskNotFoundError,
        TaskQueueShutdownError,
        TaskSnapshot,
        TaskStatus,
        ThreadPoolExecutor,
        log_safe_exception,
        logger,
        logging,
    )

class _TaskQueueStoreMethods:
    """Method group bound onto the public facade class."""

    @property
    def executor(self) -> ThreadPoolExecutor:
        """懒加载线程池"""
        if self._shutdown:
            raise TaskQueueShutdownError()
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="analysis_task_"
            )
        return self._executor

    @property
    def max_workers(self) -> int:
        """Return current executor max worker setting."""
        return self._max_workers

    def _has_inflight_tasks_locked(self) -> bool:
        """Check whether queue has any pending/processing tasks."""
        if self._analyzing_stocks:
            return True
        return any(
            task.status in (
                TaskStatus.PENDING,
                TaskStatus.PROCESSING,
                TaskStatus.CANCEL_REQUESTED,
            )
            for task in self._tasks.values()
        )

    def _ensure_accepting_locked(self) -> None:
        if self._shutdown:
            raise TaskQueueShutdownError()

    def _pin_task_locked(self, task_id: str) -> None:
        """Prevent lifecycle cleanup while a lock-external operation owns a task."""
        if task_id not in self._tasks:
            raise TaskNotFoundError(task_id)
        self._task_lifecycle_pins[task_id] = (
            self._task_lifecycle_pins.get(task_id, 0) + 1
        )

    def _unpin_task_locked(self, task_id: str) -> bool:
        """Release one lifecycle owner and report whether the last owner left."""
        owners = self._task_lifecycle_pins.get(task_id, 0)
        if owners <= 0:
            raise RuntimeError(f"Task lifecycle pin is not owned: {task_id}")
        if owners == 1:
            del self._task_lifecycle_pins[task_id]
            return True
        self._task_lifecycle_pins[task_id] = owners - 1
        return False

    def _snapshot_locked(self, task: TaskInfo) -> TaskSnapshot:
        """Build a neutral immutable snapshot while holding the data lock."""
        error_code = task.public_error()
        if task.status == TaskStatus.INTERRUPTED:
            error_code = "task_interrupted"
        return TaskSnapshot(
            id=task.task_id,
            kind=task.kind,
            status=task.status,
            progress=task.progress,
            result_ref=task.result_ref,
            error_code=error_code,
            trace_id=task.trace_id or task.task_id,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    @staticmethod
    def _canonical_event_type(event_type: str, task: TaskInfo) -> TaskEventType:
        mapping = {
            "task_created": TaskEventType.CREATED,
            "task_started": TaskEventType.STARTED,
            "task_completed": TaskEventType.COMPLETED,
            "task_failed": TaskEventType.FAILED,
        }
        if event_type == "task_progress":
            if task.status == TaskStatus.CANCEL_REQUESTED:
                return TaskEventType.CANCEL_REQUESTED
            return TaskEventType.PROGRESS
        if event_type in mapping:
            canonical = mapping[event_type]
            if event_type == "task_failed":
                return {
                    TaskStatus.CANCELLED: TaskEventType.CANCELLED,
                    TaskStatus.INTERRUPTED: TaskEventType.INTERRUPTED,
                }.get(task.status, canonical)
            return canonical
        return TaskEventType.PROGRESS

    def _publish_event_locked(
        self,
        event_type: str,
        task: TaskInfo,
        data: Dict[str, Any],
    ) -> TaskEvent:
        """Record and schedule a detached event under the lifecycle lock."""
        self._event_sequence += 1
        event = TaskEvent(
            sequence=self._event_sequence,
            task_id=task.task_id,
            type=self._canonical_event_type(event_type, task),
            snapshot=self._snapshot_locked(task),
            data=data,
            occurred_at=task.updated_at,
        )
        history = self._event_history.setdefault(task.task_id, [])
        history.append(event)
        if len(history) > self._max_flow_events_per_task:
            del history[:-self._max_flow_events_per_task]

        if task.task_id in self._suppressed_event_tasks:
            self._suppressed_events.setdefault(task.task_id, []).append(event)
        else:
            self._schedule_event_locked(event)
        return event

    def _schedule_event_locked(self, event: TaskEvent) -> None:
        """Schedule one already-recorded event on every matching stream loop."""
        for stream in tuple(self._streams.values()):
            if not stream._matches(event) or event.sequence <= stream.cutoff:
                continue
            try:
                if stream.loop.is_closed():
                    self._streams.pop(stream.token, None)
                    stream._accepting = False
                    stream._closed = True
                    continue
                stream.loop.call_soon_threadsafe(stream._deliver, event)
            except RuntimeError as exc:
                self._streams.pop(stream.token, None)
                stream._accepting = False
                stream._closed = True
                log_safe_exception(
                    logger,
                    "Task event stream schedule failed",
                    exc,
                    error_code="task_event_loop_closed",
                    level=logging.DEBUG,
                    context={"event_type": event.type.value},
                )

    def _suppress_task_events_locked(self, task_ids: List[str]) -> None:
        for task_id in task_ids:
            self._suppressed_event_tasks.add(task_id)
            self._suppressed_events.setdefault(task_id, [])

    def _flush_task_events_locked(self, task_ids: List[str]) -> None:
        events: List[TaskEvent] = []
        for task_id in task_ids:
            self._suppressed_event_tasks.discard(task_id)
            events.extend(self._suppressed_events.pop(task_id, []))
        for event in sorted(events, key=lambda item: item.sequence):
            self._schedule_event_locked(event)

    def _discard_task_events_locked(self, task_ids: List[str]) -> None:
        for task_id in task_ids:
            self._suppressed_event_tasks.discard(task_id)
            self._suppressed_events.pop(task_id, None)

    def _detach_stream(self, token: str) -> None:
        with self._data_lock:
            self._streams.pop(token, None)

    def _cleanup_old_tasks(self) -> int:
        """Evict old terminal tasks and every index owned by those tasks."""
        with self._data_lock:
            if len(self._tasks) <= self._max_history:
                return 0

            terminal_tasks = sorted(
                (
                    task
                    for task in self._tasks.values()
                    if task.status.terminal
                    and task.task_id not in self._retry_reservations
                    and task.task_id not in self._task_lifecycle_pins
                    and task.task_id not in self._retry_children.values()
                    and task.task_id not in self._suppressed_event_tasks
                ),
                key=lambda task: task.created_at,
            )
            to_remove = len(self._tasks) - self._max_history
            removed = 0

            for task in terminal_tasks[:to_remove]:
                self._remove_task_locked(task.task_id)
                removed += 1

            if removed > 0:
                logger.debug(f"[TaskQueue] 清理了 {removed} 个过期任务")
            return removed

    def _remove_task_locked(self, task_id: str) -> None:
        """Remove one task and owner-check every related lifecycle index."""
        self._tasks.pop(task_id, None)
        self._commands.pop(task_id, None)
        self._futures.pop(task_id, None)
        self._event_history.pop(task_id, None)
        self._discard_task_events_locked([task_id])
        dedupe_key = self._task_dedupe_keys.pop(task_id, None)
        if dedupe_key and self._analyzing_stocks.get(dedupe_key) == task_id:
            del self._analyzing_stocks[dedupe_key]

        idempotency_key = self._task_idempotency_keys.pop(task_id, None)
        if idempotency_key:
            owner = self._idempotency_index.get(idempotency_key)
            if owner is not None and owner[0] == task_id:
                del self._idempotency_index[idempotency_key]

        self._retry_children.pop(task_id, None)
        for parent_id, child_id in tuple(self._retry_children.items()):
            if child_id == task_id:
                del self._retry_children[parent_id]

    def _snapshot_event_locked(self, task: TaskInfo, sequence: int) -> TaskEvent:
        return TaskEvent(
            sequence=sequence,
            task_id=task.task_id,
            type=TaskEventType.SNAPSHOT,
            snapshot=self._snapshot_locked(task),
            data=task.to_dict(),
            occurred_at=task.updated_at,
        )

    def _broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish one legacy-shaped lifecycle event through canonical streams."""
        task_id = str(data.get("task_id") or "")
        if not task_id:
            return
        with self._data_lock:
            task = self._tasks.get(task_id)
            if task is not None:
                self._publish_event_locked(event_type, task, data)
