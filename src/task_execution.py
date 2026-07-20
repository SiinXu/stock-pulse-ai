# -*- coding: utf-8 -*-
"""Neutral task execution contracts shared by application adapters."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import Enum
from typing import Any, AsyncIterator, Iterator, Optional, Protocol, TypeVar, runtime_checkable


_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_T = TypeVar("_T")


class FrozenMapping(Mapping[Any, Any]):
    """Small immutable mapping used by deeply frozen task contracts."""

    __slots__ = ("_data", "_hash")

    def __init__(self, values: Mapping[Any, Any]):
        self._data = dict(values)
        self._hash: Optional[int] = None

    def __getitem__(self, key: Any) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __hash__(self) -> int:
        if self._hash is None:
            items = tuple(
                sorted(
                    ((key, value) for key, value in self._data.items()),
                    key=lambda item: repr(item[0]),
                )
            )
            self._hash = hash(items)
        return self._hash

    def __repr__(self) -> str:
        return f"FrozenMapping(keys={tuple(self._data)})"


def deep_freeze(value: _T) -> _T:
    """Return an immutable, detached representation of supported structured data."""
    if isinstance(value, Mapping):
        return FrozenMapping(
            {
                deep_freeze(key): deep_freeze(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze(item) for item in value)
    if value is None or isinstance(value, Enum):
        return value
    if type(value) in (str, bytes, int, float, bool, date, datetime):
        return value
    raise TypeError(f"Unsupported mutable task contract value: {type(value).__name__}")


def deep_thaw(value: _T) -> _T:
    """Return a detached mutable projection of deeply frozen contract data."""
    if isinstance(value, FrozenMapping):
        return {
            deep_thaw(key): deep_thaw(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [deep_thaw(item) for item in value]
    if isinstance(value, frozenset):
        return {deep_thaw(item) for item in value}
    return copy.deepcopy(value)


def _fingerprint_value(value: Any) -> Any:
    if isinstance(value, FrozenMapping):
        return {
            str(key): _fingerprint_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, tuple):
        return [_fingerprint_value(item) for item in value]
    if isinstance(value, frozenset):
        return sorted((_fingerprint_value(item) for item in value), key=repr)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported task fingerprint value: {type(value).__name__}")


class TaskStatusEnum(str, Enum):
    """Canonical process-local task lifecycle states."""

    PENDING = "pending"
    PROCESSING = "processing"
    CANCEL_REQUESTED = "cancel_requested"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"

    @property
    def terminal(self) -> bool:
        return self in {
            TaskStatusEnum.COMPLETED,
            TaskStatusEnum.FAILED,
            TaskStatusEnum.CANCELLED,
            TaskStatusEnum.INTERRUPTED,
        }


TaskStatus = TaskStatusEnum


class TaskEventType(str, Enum):
    """Canonical task lifecycle event identities."""

    CREATED = "created"
    SNAPSHOT = "snapshot"
    STARTED = "started"
    PROGRESS = "progress"
    CANCEL_REQUESTED = "cancel_requested"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"

    @property
    def terminal(self) -> bool:
        return self in {
            TaskEventType.COMPLETED,
            TaskEventType.FAILED,
            TaskEventType.CANCELLED,
            TaskEventType.INTERRUPTED,
        }


class TaskExecutionError(Exception):
    """Base class for stable task execution contract errors."""

    error_code = "task_execution_error"


class TaskNotFoundError(TaskExecutionError):
    error_code = "task_not_found"

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task does not exist: {task_id}")


class TaskIdempotencyConflictError(TaskExecutionError):
    error_code = "task_idempotency_conflict"

    def __init__(self, idempotency_key: str, existing_task_id: str):
        self.idempotency_key = idempotency_key
        self.existing_task_id = existing_task_id
        super().__init__(f"Task idempotency key conflicts with task {existing_task_id}")


class TaskRetryNotAllowedError(TaskExecutionError):
    error_code = "task_retry_not_allowed"

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task cannot be retried: {task_id}")


class TaskRetryUnsupportedError(TaskExecutionError):
    error_code = "task_retry_unsupported"

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Task has no retry factory: {task_id}")


class TaskQueueShutdownError(TaskExecutionError):
    error_code = "task_queue_shutdown"

    def __init__(self):
        super().__init__("Task queue is shut down")


class TaskStreamOverflowError(TaskExecutionError):
    error_code = "task_stream_overflow"

    def __init__(self):
        super().__init__("Task event stream consumer is too slow")


@dataclass(frozen=True)
class TaskCommand:
    """Immutable command submitted through the task execution port."""

    kind: str
    run: Callable[["TaskRunContext"], Any] = field(repr=False, compare=False)
    metadata: Mapping[str, Any] = field(default_factory=dict, repr=False)
    dedupe_key: Optional[str] = None
    trace_id: Optional[str] = None
    idempotency_key: str = field(default_factory=lambda: uuid.uuid4().hex, repr=False)
    idempotency_fingerprint: str = field(default="", repr=False)
    failure_error_code: str = "task_failed"
    none_is_success: bool = True
    retry_factory: Optional[Callable[[], "TaskCommand"]] = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        kind = str(self.kind or "").strip()
        if not kind:
            raise ValueError("Task command kind must not be blank")
        if not callable(self.run):
            raise TypeError("Task command run must be callable")
        if self.retry_factory is not None and not callable(self.retry_factory):
            raise TypeError("Task command retry_factory must be callable")
        if not _ERROR_CODE.fullmatch(str(self.failure_error_code or "")):
            raise ValueError("Task command failure_error_code is invalid")
        key = str(self.idempotency_key or "").strip()
        if not key:
            raise ValueError("Task command idempotency_key must not be blank")
        dedupe_key = str(self.dedupe_key or "").strip() or None
        trace_id = str(self.trace_id or "").strip() or None
        metadata = deep_freeze(dict(self.metadata))
        fingerprint = str(self.idempotency_fingerprint or "").strip()
        if not fingerprint:
            canonical = json.dumps(
                {
                    "kind": kind,
                    "metadata": _fingerprint_value(metadata),
                    "dedupe_key": dedupe_key,
                    "failure_error_code": self.failure_error_code,
                    "none_is_success": self.none_is_success,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            fingerprint = hashlib.sha256(canonical).hexdigest()
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "metadata", metadata)
        object.__setattr__(self, "dedupe_key", dedupe_key)
        object.__setattr__(self, "trace_id", trace_id)
        object.__setattr__(self, "idempotency_key", key)
        object.__setattr__(self, "idempotency_fingerprint", fingerprint)

    def for_retry(self) -> "TaskCommand":
        """Return a retry command with fresh trace and idempotency identities."""
        return replace(
            self,
            trace_id=None,
            idempotency_key=uuid.uuid4().hex,
            idempotency_fingerprint="",
        )


@dataclass(frozen=True)
class TaskSnapshot:
    """Immutable public snapshot of one task lifecycle."""

    id: str
    kind: str
    status: TaskStatusEnum
    progress: int
    result_ref: Optional[str]
    error_code: Optional[str]
    trace_id: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.status, TaskStatusEnum):
            object.__setattr__(self, "status", TaskStatusEnum(self.status))
        progress = int(self.progress)
        if not 0 <= progress <= 100:
            raise ValueError("Task snapshot progress must be between 0 and 100")
        object.__setattr__(self, "progress", progress)


@dataclass(frozen=True)
class TaskEvent:
    """Immutable sequenced lifecycle event."""

    sequence: int
    task_id: str
    type: TaskEventType
    snapshot: TaskSnapshot
    data: Mapping[str, Any] = field(default_factory=dict, repr=False)
    occurred_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("Task event sequence must not be negative")
        if not isinstance(self.type, TaskEventType):
            object.__setattr__(self, "type", TaskEventType(self.type))
        object.__setattr__(self, "data", deep_freeze(dict(self.data)))

    @property
    def terminal(self) -> bool:
        return self.type.terminal


@dataclass(frozen=True)
class TaskRunContext:
    """Runner-facing task identity and progress callbacks."""

    task_id: str
    trace_id: str
    command: TaskCommand = field(repr=False)
    update_progress: Callable[[int, Optional[str]], Any] = field(repr=False, compare=False)
    append_flow_event: Callable[[Mapping[str, Any]], Any] = field(repr=False, compare=False)
    is_cancel_requested: Callable[[], bool] = field(repr=False, compare=False)


TaskExecutionContext = TaskRunContext


@runtime_checkable
class TaskEventStream(Protocol):
    """Async receive contract for one bounded task event subscription."""

    def __aiter__(self) -> AsyncIterator[TaskEvent]:
        ...

    async def receive(self, timeout: Optional[float] = None) -> TaskEvent:
        ...

    async def aclose(self) -> None:
        ...


@runtime_checkable
class TaskExecutionPort(Protocol):
    """Application port for process-local task execution."""

    def submit(self, command: TaskCommand) -> str:
        ...

    def get(self, task_id: str) -> TaskSnapshot:
        ...

    def cancel(self, task_id: str) -> TaskSnapshot:
        ...

    def retry(self, task_id: str) -> str:
        ...

    def subscribe(self, task_id: str) -> TaskEventStream:
        ...

    def subscribe_all(self) -> TaskEventStream:
        ...

__all__ = [
    "FrozenMapping",
    "TaskCommand",
    "TaskEvent",
    "TaskEventStream",
    "TaskEventType",
    "TaskExecutionContext",
    "TaskExecutionError",
    "TaskExecutionPort",
    "TaskIdempotencyConflictError",
    "TaskNotFoundError",
    "TaskQueueShutdownError",
    "TaskRetryNotAllowedError",
    "TaskRetryUnsupportedError",
    "TaskRunContext",
    "TaskSnapshot",
    "TaskStatus",
    "TaskStatusEnum",
    "TaskStreamOverflowError",
    "deep_freeze",
    "deep_thaw",
]
