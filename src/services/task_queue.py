# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 异步任务队列
===================================

职责：
1. 管理异步分析任务的生命周期
2. 防止相同股票代码重复提交
3. 提供 SSE 事件广播机制
4. 任务完成后持久化到数据库
"""

from __future__ import annotations

import asyncio
import copy
import logging
import re
import threading
import uuid
import weakref
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any, Tuple, Literal, Callable

from data_provider.base import canonical_stock_code, normalize_stock_code
from src.task_execution import (
    TaskCommand,
    TaskEvent,
    TaskEventType,
    TaskIdempotencyConflictError,
    TaskNotFoundError,
    TaskQueueShutdownError,
    TaskRetryNotAllowedError,
    TaskRetryUnsupportedError,
    TaskRunContext,
    TaskSnapshot,
    TaskStatus,
    TaskStatusEnum,
    TaskStreamOverflowError,
    deep_freeze,
    deep_thaw,
)
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    get_current_diagnostic_context,
    reset_run_diagnostic_context,
)
from src.utils.analysis_metadata import SELECTION_SOURCES
from src.utils.sanitize import (
    exception_chain_redaction_values,
    log_safe_exception,
    sanitize_exception_chain,
)
from src.services.stock_code_utils import resolve_index_stock_code_for_analysis

logger = logging.getLogger(__name__)


_TASK_MESSAGE_SUFFIX_CODES: Tuple[Tuple[str, str], ...] = (
    ("正在准备分析任务", "task.analysis.preparing"),
    ("正在获取行情与筹码数据", "task.analysis.market_data"),
    ("行情数据准备完成", "task.analysis.market_data_ready"),
    ("正在聚合基本面与趋势数据", "task.analysis.fundamentals"),
    ("正在切换 Agent 分析链路", "task.analysis.agent"),
    ("正在检索新闻与舆情", "task.analysis.news"),
    ("正在整理分析上下文", "task.analysis.context"),
    ("正在请求 LLM 生成报告", "task.analysis.llm"),
    ("正在校验并整理分析结果", "task.analysis.validating"),
    ("正在保存分析报告", "task.analysis.saving"),
)


def _task_message_metadata(
    message: Optional[str],
    *,
    fallback_code: str,
) -> Tuple[str, Dict[str, Any]]:
    """Map legacy task copy to a stable UI message identity."""
    normalized = (message or "").strip()
    exact_codes = {
        "任务已加入队列": "task.queued",
        "正在分析中...": "task.analysis.processing",
        "分析完成": "task.analysis.completed",
        "任务执行中": "task.processing",
        "任务执行完成": "task.completed",
        "大盘复盘任务已提交": "task.market_review.queued",
        "AlphaSift 选股任务已提交": "task.screening.queued",
        "正在执行 AlphaSift 选股，外部数据源较慢时会持续后台运行": "task.screening.processing",
    }
    if normalized in exact_codes:
        return exact_codes[normalized], {}

    if normalized.startswith("选股已完成，正在整理 ") and normalized.endswith(" 条候选"):
        raw_count = normalized.removeprefix("选股已完成，正在整理 ").removesuffix(" 条候选")
        try:
            candidate_count: Any = int(raw_count)
        except ValueError:
            candidate_count = raw_count
        return "task.screening.organizing", {"candidate_count": candidate_count}

    for suffix, code in _TASK_MESSAGE_SUFFIX_CODES:
        if normalized == suffix:
            return code, {}
        marker = f"：{suffix}"
        if normalized.endswith(marker):
            subject = normalized[: -len(marker)].strip()
            return code, {"subject": subject} if subject else {}

    return fallback_code, {}


def _dedupe_stock_code_key(stock_code: str) -> str:
    """
    Build the internal duplicate-detection key for a stock code.

    The task queue should treat equivalent market code shapes as the same
    underlying stock, e.g. ``600519`` and ``600519.SH``.
    """
    return resolve_index_stock_code_for_analysis(normalize_stock_code(stock_code))


_STABLE_TASK_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def public_task_error(task: Any, default_error_code: str = "task_failed") -> Optional[str]:
    """Project a failed task to a stable public error code."""
    status = getattr(task, "status", None)
    status_value = status.value if isinstance(status, Enum) else str(status or "")
    if status_value != TaskStatus.FAILED.value:
        return None
    candidate = str(getattr(task, "failure_error_code", "") or "").strip()
    if not _STABLE_TASK_ERROR_CODE.fullmatch(candidate):
        candidate = default_error_code
    return candidate


def public_task_message(task: Any, default_failed_message: str = "任务执行失败") -> Optional[str]:
    """Project task copy while keeping failure diagnostics server-side."""
    status = getattr(task, "status", None)
    status_value = status.value if isinstance(status, Enum) else str(status or "")
    if status_value != TaskStatus.FAILED.value:
        return getattr(task, "message", None)
    if getattr(task, "message_code", None) == "task.analysis.failed":
        return "分析失败"
    return default_failed_message


@dataclass
class TaskInfo:
    """
    Task information dataclass.

    Used for API responses and internal task management.
    """
    task_id: str
    stock_code: str
    kind: str = "stock_analysis"
    stock_name: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    message: Optional[str] = None
    message_code: str = "task.queued"
    message_params: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[str] = None
    diagnostic_error: Optional[str] = field(default=None, repr=False)
    failure_error_code: str = field(default="analysis_failed", repr=False)
    report_type: str = "detailed"
    analysis_phase: str = "auto"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_ref: Optional[str] = None
    original_query: Optional[str] = None
    selection_source: Optional[str] = None
    query_source: str = "api"
    portfolio_context: Optional[Dict[str, Any]] = None
    skills: Optional[List[str]] = None
    report_language: Optional[str] = None
    trace_id: Optional[str] = None
    flow_events: List[Dict[str, Any]] = field(default_factory=list)

    def public_error(self) -> Optional[str]:
        """Return only a stable error code for public task payloads."""
        return public_task_error(self, default_error_code="task_failed")

    def public_message(self) -> Optional[str]:
        """Return status copy that cannot contain a provider exception."""
        return public_task_message(self)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task info into an API-friendly dictionary."""
        return {
            "task_id": self.task_id,
            "trace_id": self.trace_id or self.task_id,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.public_message(),
            "message_code": self.message_code,
            "message_params": copy.deepcopy(self.message_params),
            "report_type": self.report_type,
            "analysis_phase": self.analysis_phase,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.public_error(),
            "original_query": self.original_query,
            "selection_source": self.selection_source,
            "skills": self.skills,
        }
    
    def copy(self) -> 'TaskInfo':
        """Create a shallow copy of the task information."""
        return TaskInfo(
            task_id=self.task_id,
            stock_code=self.stock_code,
            kind=self.kind,
            stock_name=self.stock_name,
            status=self.status,
            progress=self.progress,
            message=self.message,
            message_code=self.message_code,
            message_params=copy.deepcopy(self.message_params),
            result=copy.deepcopy(self.result),
            error=self.error,
            diagnostic_error=self.diagnostic_error,
            failure_error_code=self.failure_error_code,
            report_type=self.report_type,
            analysis_phase=self.analysis_phase,
            created_at=self.created_at,
            updated_at=self.updated_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            result_ref=self.result_ref,
            original_query=self.original_query,
            selection_source=self.selection_source,
            query_source=self.query_source,
            portfolio_context=copy.deepcopy(self.portfolio_context),
            skills=copy.deepcopy(self.skills),
            report_language=self.report_language,
            trace_id=self.trace_id or self.task_id,
            flow_events=copy.deepcopy(self.flow_events),
        )


class DuplicateTaskError(Exception):
    """
    重复提交异常
    
    当股票已在分析中时抛出此异常
    """
    def __init__(self, stock_code: str, existing_task_id: str):
        self.stock_code = stock_code
        self.existing_task_id = existing_task_id
        super().__init__(f"股票 {stock_code} 正在分析中 (task_id: {existing_task_id})")


@dataclass
class _RetryReservation:
    """Coordinate concurrent retry callers without running factories under the queue lock."""

    ready: threading.Event = field(default_factory=threading.Event)
    child_task_id: Optional[str] = None
    error: Optional[BaseException] = None


_STREAM_EOF = object()


class _QueueTaskEventStream:
    """One loop-owned bounded task event stream."""

    def __init__(
        self,
        owner: 'AnalysisTaskQueue',
        *,
        task_id: Optional[str],
        cutoff: int,
        max_queue_size: int,
    ):
        self._owner = owner
        self._task_id = task_id
        self._cutoff = cutoff
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max(1, int(max_queue_size)))
        self._token = uuid.uuid4().hex
        self._accepting = True
        self._closed = False
        self._eof_after_drain = False

    @property
    def token(self) -> str:
        return self._token

    @property
    def task_id(self) -> Optional[str]:
        return self._task_id

    @property
    def cutoff(self) -> int:
        return self._cutoff

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    @property
    def closed(self) -> bool:
        return self._closed

    def __aiter__(self):
        return self

    async def __anext__(self) -> TaskEvent:
        try:
            return await self.receive()
        except StopAsyncIteration:
            raise StopAsyncIteration

    def _matches(self, event: TaskEvent) -> bool:
        return self._task_id is None or self._task_id == event.task_id

    def _enqueue_replay(self, event: TaskEvent, *, terminal_eof: bool = False) -> None:
        if self._queue.full():
            raise TaskStreamOverflowError()
        self._queue.put_nowait(event)
        if terminal_eof:
            self._accepting = False
            self._eof_after_drain = True

    def _clear_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    def _deliver(self, event: TaskEvent) -> None:
        if not self._accepting or self._closed or event.sequence <= self._cutoff:
            return
        if self._queue.full():
            self._owner._detach_stream(self._token)
            self._accepting = False
            self._clear_queue()
            if self._task_id is not None and event.terminal:
                self._queue.put_nowait(event)
                self._eof_after_drain = True
            else:
                self._queue.put_nowait(TaskStreamOverflowError())
            return
        self._queue.put_nowait(event)
        if self._task_id is not None and event.terminal:
            self._owner._detach_stream(self._token)
            self._accepting = False
            self._eof_after_drain = True

    def _close_local(self, error: Optional[BaseException] = None) -> None:
        if self._closed:
            return
        self._accepting = False
        self._closed = True
        self._clear_queue()
        self._queue.put_nowait(error or _STREAM_EOF)

    def _finish_local(self) -> None:
        """Stop after queued events drain without discarding a terminal event."""
        if self._closed:
            return
        self._accepting = False
        self._eof_after_drain = True
        if self._queue.empty():
            self._queue.put_nowait(_STREAM_EOF)

    def _schedule_finish(self) -> bool:
        try:
            if self._loop.is_closed():
                self._accepting = False
                self._closed = True
                return False
            self._loop.call_soon_threadsafe(self._finish_local)
            return True
        except RuntimeError:
            self._accepting = False
            self._closed = True
            return False

    async def receive(self, timeout: Optional[float] = None) -> TaskEvent:
        if self._closed and self._queue.empty():
            raise StopAsyncIteration
        waiter = self._queue.get()
        item = await waiter if timeout is None else await asyncio.wait_for(waiter, timeout)
        if item is _STREAM_EOF:
            self._closed = True
            raise StopAsyncIteration
        if isinstance(item, BaseException):
            self._closed = True
            raise item
        if self._eof_after_drain and self._queue.empty():
            self._closed = True
        return item

    async def aclose(self) -> None:
        if self._closed and self._queue.empty():
            return
        self._owner._detach_stream(self._token)
        self._close_local()


class AnalysisTaskQueue:
    """
    异步分析任务队列
    
    单例模式，全局唯一实例
    
    特性：
    1. 防止相同股票代码重复提交
    2. 线程池执行分析任务
    3. SSE 事件广播机制
    4. 任务完成后自动持久化
    """
    
    _instance: Optional['AnalysisTaskQueue'] = None
    _instance_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, max_workers: int = 3):
        # 防止重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        self._max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        
        # 核心数据结构
        self._tasks: Dict[str, TaskInfo] = {}           # task_id -> TaskInfo
        self._analyzing_stocks: Dict[str, str] = {}     # dedupe_key -> task_id
        self._futures: Dict[str, Future] = {}           # task_id -> Future
        self._commands: Dict[str, TaskCommand] = {}
        self._task_dedupe_keys: Dict[str, str] = {}
        self._idempotency_index: Dict[str, Tuple[str, str]] = {}
        self._task_idempotency_keys: Dict[str, str] = {}
        self._retry_reservations: Dict[str, _RetryReservation] = {}
        self._retry_children: Dict[str, str] = {}
        self._task_lifecycle_pins: Dict[str, int] = {}
        self._streams = weakref.WeakValueDictionary()
        self._event_history: Dict[str, List[TaskEvent]] = {}
        self._suppressed_event_tasks = set()
        self._suppressed_events: Dict[str, List[TaskEvent]] = {}
        self._event_sequence = 0
        self._event_stream_queue_size = 256
        self._shutdown = False
        
        # 线程安全锁
        self._data_lock = threading.RLock()
        
        # 任务历史保留数量（内存中）
        self._max_history = 100
        self._max_flow_events_per_task = 200
        
        self._initialized = True
        logger.info(f"[TaskQueue] 初始化完成，最大并发: {max_workers}")
    
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

    def sync_max_workers(
        self,
        max_workers: int,
        *,
        log: bool = True,
    ) -> Literal["applied", "unchanged", "deferred_busy"]:
        """
        Try to sync queue concurrency without replacing singleton instance.

        Returns:
            - "applied": new value applied immediately (idle queue only)
            - "unchanged": target equals current value or invalid target
            - "deferred_busy": queue is busy, apply is deferred
        """
        try:
            target = max(1, int(max_workers))
        except (TypeError, ValueError):
            if log:
                logger.warning("[TaskQueue] 忽略非法 MAX_WORKERS 值: %r", max_workers)
            return "unchanged"

        executor_to_shutdown: Optional[ThreadPoolExecutor] = None
        previous: int
        with self._data_lock:
            previous = self._max_workers
            if target == previous:
                return "unchanged"

            if self._has_inflight_tasks_locked():
                if log:
                    logger.info(
                        "[TaskQueue] 最大并发调整延后: 当前繁忙 (%s -> %s)",
                        previous,
                        target,
                    )
                return "deferred_busy"

            self._max_workers = target
            executor_to_shutdown = self._executor
            self._executor = None

        if executor_to_shutdown is not None:
            executor_to_shutdown.shutdown(wait=False)

        if log:
            logger.info("[TaskQueue] 最大并发已更新: %s -> %s", previous, target)
        return "applied"
    
    # ========== 任务提交与查询 ==========
    
    def is_analyzing(self, stock_code: str) -> bool:
        """
        检查股票是否正在分析中
        
        Args:
            stock_code: 股票代码
            
        Returns:
            True 表示正在分析中
        """
        dedupe_key = _dedupe_stock_code_key(stock_code)
        with self._data_lock:
            return dedupe_key in self._analyzing_stocks
    
    def get_analyzing_task_id(self, stock_code: str) -> Optional[str]:
        """
        获取正在分析该股票的任务 ID
        
        Args:
            stock_code: 股票代码
            
        Returns:
            任务 ID，如果没有则返回 None
        """
        dedupe_key = _dedupe_stock_code_key(stock_code)
        with self._data_lock:
            return self._analyzing_stocks.get(dedupe_key)

    def validate_selection_source(self, selection_source: Optional[str]) -> None:
        """
        Validate the selection source parameter.

        Args:
            selection_source: Selection source label.

        Raises:
            ValueError: Raised when the selection source is invalid.
        """
        if selection_source is not None and selection_source not in SELECTION_SOURCES:
            raise ValueError(
                f"Invalid selection_source: {selection_source}. "
                f"Must be one of {SELECTION_SOURCES}"
            )

    def _task_info_from_command_locked(self, task_id: str, command: TaskCommand) -> TaskInfo:
        metadata = deep_thaw(command.metadata)
        stock_code = str(metadata.get("stock_code") or command.kind).strip()
        message = metadata.get("message", "任务已加入队列")
        message_code, message_params = _task_message_metadata(
            message,
            fallback_code="task.queued",
        )
        now = datetime.now()
        return TaskInfo(
            task_id=task_id,
            trace_id=command.trace_id or task_id,
            kind=command.kind,
            stock_code=stock_code,
            stock_name=metadata.get("stock_name"),
            status=TaskStatus.PENDING,
            message=message,
            message_code=metadata.get("message_code") or message_code,
            message_params=copy.deepcopy(metadata.get("message_params") or message_params),
            failure_error_code=command.failure_error_code,
            report_type=str(metadata.get("report_type") or "detailed"),
            analysis_phase=str(metadata.get("analysis_phase") or "auto"),
            original_query=metadata.get("original_query"),
            selection_source=metadata.get("selection_source"),
            query_source=str(metadata.get("query_source") or "api"),
            portfolio_context=copy.deepcopy(metadata.get("portfolio_context")),
            skills=copy.deepcopy(metadata.get("skills")),
            report_language=metadata.get("report_language"),
            created_at=now,
            updated_at=now,
        )

    def _rollback_task_locked(self, task_id: str) -> None:
        future = self._futures.pop(task_id, None)
        if future is not None:
            future.cancel()
        self._tasks.pop(task_id, None)
        self._commands.pop(task_id, None)
        self._event_history.pop(task_id, None)
        self._discard_task_events_locked([task_id])
        dedupe_key = self._task_dedupe_keys.pop(task_id, None)
        if dedupe_key and self._analyzing_stocks.get(dedupe_key) == task_id:
            del self._analyzing_stocks[dedupe_key]
        idempotency_key = self._task_idempotency_keys.pop(task_id, None)
        if idempotency_key:
            owner = self._idempotency_index.get(idempotency_key)
            if owner and owner[0] == task_id:
                del self._idempotency_index[idempotency_key]

    def _stage_command_locked(
        self,
        command: TaskCommand,
        *,
        task_id: Optional[str] = None,
    ) -> Tuple[str, TaskInfo, bool]:
        self._ensure_accepting_locked()
        owner = self._idempotency_index.get(command.idempotency_key)
        if owner is not None:
            existing_task_id, fingerprint = owner
            if existing_task_id not in self._tasks:
                del self._idempotency_index[command.idempotency_key]
            elif fingerprint == command.idempotency_fingerprint:
                return existing_task_id, self._tasks[existing_task_id], False
            else:
                raise TaskIdempotencyConflictError(
                    command.idempotency_key,
                    existing_task_id,
                )

        if command.dedupe_key and command.dedupe_key in self._analyzing_stocks:
            existing_task_id = self._analyzing_stocks[command.dedupe_key]
            metadata = deep_thaw(command.metadata)
            raise DuplicateTaskError(
                str(metadata.get("stock_code") or command.dedupe_key),
                existing_task_id,
            )

        task_id = task_id or uuid.uuid4().hex
        if task_id in self._tasks:
            raise ValueError(f"任务 ID 已存在: {task_id}")
        task = self._task_info_from_command_locked(task_id, command)
        self._tasks[task_id] = task
        self._commands[task_id] = command
        self._idempotency_index[command.idempotency_key] = (
            task_id,
            command.idempotency_fingerprint,
        )
        self._task_idempotency_keys[task_id] = command.idempotency_key
        if command.dedupe_key:
            self._task_dedupe_keys[task_id] = command.dedupe_key
            self._analyzing_stocks[command.dedupe_key] = task_id
        return task_id, task, True

    def _submit_staged_commands_locked(self, task_ids: List[str]) -> None:
        for task_id in task_ids:
            future = self.executor.submit(self._execute_command, task_id)
            self._futures[task_id] = future

    def submit(self, command: TaskCommand) -> str:
        """Submit one immutable command through the canonical execution port."""
        if not isinstance(command, TaskCommand):
            raise TypeError("command must be a TaskCommand")
        cleanup_after_submit = False
        with self._data_lock:
            task_id, task, created = self._stage_command_locked(command)
            if not created:
                return task_id
            staged_task_ids = [task_id]
            self._suppress_task_events_locked(staged_task_ids)
            try:
                self._broadcast_event("task_created", task.to_dict())
                self._submit_staged_commands_locked(staged_task_ids)
            except BaseException:
                self._discard_task_events_locked(staged_task_ids)
                self._rollback_task_locked(task_id)
                raise
            self._flush_task_events_locked(staged_task_ids)
            cleanup_after_submit = task.status.terminal
        if cleanup_after_submit:
            self._cleanup_old_tasks()
        return task_id

    def get(self, task_id: str) -> TaskSnapshot:
        """Return a neutral immutable snapshot or raise a stable not-found error."""
        with self._data_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            return self._snapshot_locked(task)

    def _is_cancel_requested(self, task_id: str) -> bool:
        with self._data_lock:
            task = self._tasks.get(task_id)
            return bool(
                task
                and task.status in {
                    TaskStatus.CANCEL_REQUESTED,
                    TaskStatus.CANCELLED,
                    TaskStatus.INTERRUPTED,
                }
            )

    def cancel(self, task_id: str) -> TaskSnapshot:
        """Request cancellation with a monotonic first-terminal-wins transition."""
        future: Optional[Future]
        with self._data_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            if task.status.terminal:
                return self._snapshot_locked(task)
            if task.status != TaskStatus.CANCEL_REQUESTED:
                task.status = TaskStatus.CANCEL_REQUESTED
                task.updated_at = datetime.now()
                task.message = "任务请求取消"
                task.message_code = "task.cancel_requested"
                task.message_params = {}
                self._broadcast_event("task_progress", task.to_dict())
            future = self._futures.get(task_id)
            self._pin_task_locked(task_id)

        last_owner_left = False
        try:
            cancelled_before_start = bool(future and future.cancel())
            with self._data_lock:
                task = self._tasks[task_id]
                if cancelled_before_start and task.status == TaskStatus.CANCEL_REQUESTED:
                    self._terminalize_locked(task, TaskStatus.CANCELLED)
                snapshot = self._snapshot_locked(task)
        finally:
            with self._data_lock:
                last_owner_left = self._unpin_task_locked(task_id)
        if last_owner_left:
            self._cleanup_old_tasks()
        return snapshot

    def _submit_retry_child(
        self,
        parent_task_id: str,
        reservation: _RetryReservation,
        command: TaskCommand,
    ) -> str:
        """Atomically expose one reserved retry child and its parent ownership."""
        child_task_id = reservation.child_task_id
        if child_task_id is None:
            raise RuntimeError("Retry reservation has no child task ID")

        cleanup_after_submit = False
        with self._data_lock:
            current = self._retry_reservations.get(parent_task_id)
            if current is not reservation:
                if reservation.error is not None:
                    raise reservation.error
                raise TaskRetryNotAllowedError(parent_task_id)

            staged_task_id, task, created = self._stage_command_locked(
                command,
                task_id=child_task_id,
            )
            if not created or staged_task_id != child_task_id:
                raise RuntimeError("Retry child reservation was not created")

            staged_task_ids = [child_task_id]
            self._pin_task_locked(child_task_id)
            self._suppress_task_events_locked(staged_task_ids)
            try:
                self._broadcast_event("task_created", task.to_dict())
                self._submit_staged_commands_locked(staged_task_ids)
                self._flush_task_events_locked(staged_task_ids)
                self._retry_children[parent_task_id] = child_task_id
                del self._retry_reservations[parent_task_id]
                self._unpin_task_locked(child_task_id)
                reservation.ready.set()
                cleanup_after_submit = task.status.terminal
            except BaseException:
                self._discard_task_events_locked(staged_task_ids)
                self._rollback_task_locked(child_task_id)
                self._unpin_task_locked(child_task_id)
                raise

        if cleanup_after_submit:
            self._cleanup_old_tasks()
        return child_task_id

    def retry(self, task_id: str) -> str:
        """Retry a terminal task while coordinating concurrent callers."""
        waiter = False
        with self._data_lock:
            self._ensure_accepting_locked()
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            if task.status not in {
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.INTERRUPTED,
            }:
                raise TaskRetryNotAllowedError(task_id)
            child_task_id = self._retry_children.get(task_id)
            if child_task_id is not None:
                if child_task_id in self._tasks:
                    return child_task_id
                del self._retry_children[task_id]
            command = self._commands.get(task_id)
            if command is None or command.retry_factory is None:
                raise TaskRetryUnsupportedError(task_id)
            reservation = self._retry_reservations.get(task_id)
            if reservation is None:
                reservation = _RetryReservation(child_task_id=uuid.uuid4().hex)
                self._retry_reservations[task_id] = reservation
            else:
                waiter = True

        if waiter:
            reservation.ready.wait()
            if reservation.error is not None:
                raise reservation.error
            if reservation.child_task_id is None:
                raise TaskRetryNotAllowedError(task_id)
            return reservation.child_task_id

        try:
            retry_command = command.retry_factory()
            if not isinstance(retry_command, TaskCommand):
                raise TypeError("retry_factory must return TaskCommand")
            child_command = replace(
                retry_command,
                kind=command.kind,
                metadata=command.metadata,
                dedupe_key=command.dedupe_key,
                trace_id=None,
                idempotency_key=uuid.uuid4().hex,
                idempotency_fingerprint=command.idempotency_fingerprint,
                failure_error_code=command.failure_error_code,
                none_is_success=command.none_is_success,
                retry_factory=command.retry_factory,
            )
            child_task_id = self._submit_retry_child(
                task_id,
                reservation,
                child_command,
            )
        except BaseException as exc:
            raised_error = exc
            with self._data_lock:
                current = self._retry_reservations.get(task_id)
                if current is reservation:
                    reservation.error = exc
                    del self._retry_reservations[task_id]
                    reservation.ready.set()
                elif reservation.error is not None:
                    raised_error = reservation.error
            raise raised_error

        return child_task_id
    
    def _build_analysis_command(
        self,
        *,
        stock_code: str,
        stock_name: Optional[str],
        original_query: Optional[str],
        selection_source: Optional[str],
        query_source: str,
        portfolio_context: Optional[Dict[str, Any]],
        report_type: str,
        analysis_phase: str,
        force_refresh: bool,
        notify: bool,
        skills: Optional[List[str]],
        report_language: Optional[str],
    ) -> TaskCommand:
        metadata = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "original_query": original_query,
            "selection_source": selection_source,
            "query_source": query_source or "api",
            "portfolio_context": copy.deepcopy(portfolio_context),
            "report_type": report_type,
            "analysis_phase": analysis_phase or "auto",
            "force_refresh": bool(force_refresh),
            "notify": bool(notify),
            "skills": copy.deepcopy(skills),
            "report_language": report_language,
            "message": "任务已加入队列",
            "message_code": "task.queued",
            "message_params": {"stock_code": stock_code},
        }

        def retry_factory() -> TaskCommand:
            return self._build_analysis_command(
                stock_code=stock_code,
                stock_name=stock_name,
                original_query=original_query,
                selection_source=selection_source,
                query_source=query_source,
                portfolio_context=copy.deepcopy(portfolio_context),
                report_type=report_type,
                analysis_phase=analysis_phase,
                force_refresh=force_refresh,
                notify=notify,
                skills=copy.deepcopy(skills),
                report_language=report_language,
            )

        return TaskCommand(
            kind="stock_analysis",
            run=self._run_analysis_command,
            metadata=metadata,
            dedupe_key=_dedupe_stock_code_key(stock_code),
            failure_error_code="analysis_failed",
            none_is_success=False,
            retry_factory=retry_factory,
        )

    def submit_task(
        self,
        stock_code: str,
        stock_name: Optional[str] = None,
        original_query: Optional[str] = None,
        selection_source: Optional[str] = None,
        query_source: str = "api",
        portfolio_context: Optional[Dict[str, Any]] = None,
        report_type: str = "detailed",
        analysis_phase: str = "auto",
        force_refresh: bool = False,
        skills: Optional[List[str]] = None,
        report_language: Optional[str] = None,
    ) -> TaskInfo:
        """
        Submit a single analysis task.

        Args:
            stock_code: Stock code
            stock_name: Optional stock name
            original_query: Optional raw user input
            selection_source: Optional source label
            report_type: Report type
            analysis_phase: Requested analysis phase override
            force_refresh: Whether to bypass cache

        Returns:
            TaskInfo: Accepted task information

        Raises:
            DuplicateTaskError: Raised when the stock is already being analyzed
        """
        stock_code = resolve_index_stock_code_for_analysis(stock_code)
        if not stock_code:
            raise ValueError("股票代码不能为空或仅包含空白字符")

        accepted, duplicates = self.submit_tasks_batch(
            [stock_code],
            stock_name=stock_name,
            original_query=original_query,
            selection_source=selection_source,
            query_source=query_source,
            portfolio_context=portfolio_context,
            report_type=report_type,
            analysis_phase=analysis_phase,
            force_refresh=force_refresh,
            skills=skills,
            report_language=report_language,
        )
        if duplicates:
            raise duplicates[0]
        return accepted[0]

    def submit_tasks_batch(
        self,
        stock_codes: List[str],
        stock_name: Optional[str] = None,
        original_query: Optional[str] = None,
        selection_source: Optional[str] = None,
        query_source: str = "api",
        portfolio_context: Optional[Dict[str, Any]] = None,
        report_type: str = "detailed",
        analysis_phase: str = "auto",
        force_refresh: bool = False,
        notify: bool = True,
        skills: Optional[List[str]] = None,
        report_language: Optional[str] = None,
    ) -> Tuple[List[TaskInfo], List[DuplicateTaskError]]:
        """
        Submit analysis tasks in batch.

        - Duplicate stocks are skipped and recorded in duplicates.
        - If executor submission fails, the current batch is rolled back.
        """
        self.validate_selection_source(selection_source)

        accepted: List[TaskInfo] = []
        duplicates: List[DuplicateTaskError] = []
        created_task_ids: List[str] = []

        canonical_codes = [
            normalized for normalized in (resolve_index_stock_code_for_analysis(code) for code in stock_codes)
            if normalized
        ]

        commands = [
            self._build_analysis_command(
                stock_code=stock_code,
                stock_name=stock_name,
                original_query=original_query,
                selection_source=selection_source,
                query_source=query_source,
                portfolio_context=copy.deepcopy(portfolio_context),
                report_type=report_type,
                analysis_phase=analysis_phase,
                force_refresh=force_refresh,
                notify=notify,
                skills=copy.deepcopy(skills),
                report_language=report_language,
            )
            for stock_code in canonical_codes
        ]

        cleanup_after_submit = False
        with self._data_lock:
            self._ensure_accepting_locked()
            try:
                for stock_code, command in zip(canonical_codes, commands):
                    try:
                        task_id, task_info, created = self._stage_command_locked(command)
                    except DuplicateTaskError as exc:
                        duplicates.append(exc)
                        continue
                    if not created:
                        continue
                    accepted.append(task_info.copy())
                    created_task_ids.append(task_id)
                    logger.info(f"[TaskQueue] 任务已提交: {stock_code} -> {task_id}")

                self._suppress_task_events_locked(created_task_ids)
                for task_id in created_task_ids:
                    self._broadcast_event("task_created", self._tasks[task_id].to_dict())
                self._submit_staged_commands_locked(created_task_ids)
            except BaseException:
                self._discard_task_events_locked(created_task_ids)
                self._rollback_submitted_tasks_locked(created_task_ids)
                raise
            self._flush_task_events_locked(created_task_ids)
            cleanup_after_submit = any(
                self._tasks.get(task_id) is not None
                and self._tasks[task_id].status.terminal
                for task_id in created_task_ids
            )

        if cleanup_after_submit:
            self._cleanup_old_tasks()
        return accepted, duplicates

    def submit_background_task(
        self,
        run_task: Callable[[], Optional[Any]],
        *,
        stock_code: str,
        stock_name: Optional[str] = None,
        report_type: str = "detailed",
        message: Optional[str] = "任务已加入队列",
        task_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        failure_error_code: str = "task_failed",
        retry_factory: Optional[Callable[[], TaskCommand]] = None,
    ) -> TaskInfo:
        """
        Submit a generic background callable with task lifecycle tracking.

        This is used by callers that need task status visibility but do not
        map to standard per-stock async analysis flow.
        """
        metadata = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "report_type": report_type,
            "message": message,
        }

        command = TaskCommand(
            kind=report_type or "background",
            run=lambda _context: run_task(),
            metadata=metadata,
            trace_id=trace_id,
            failure_error_code=failure_error_code,
            none_is_success=False,
            retry_factory=retry_factory,
        )
        cleanup_after_submit = False
        with self._data_lock:
            accepted_id, task_info, created = self._stage_command_locked(
                command,
                task_id=task_id,
            )
            if not created:
                return self._tasks[accepted_id].copy()
            staged_task_ids = [accepted_id]
            self._suppress_task_events_locked(staged_task_ids)
            try:
                self._broadcast_event("task_created", task_info.to_dict())
                self._submit_staged_commands_locked(staged_task_ids)
            except BaseException:
                self._discard_task_events_locked(staged_task_ids)
                self._rollback_task_locked(accepted_id)
                raise
            self._flush_task_events_locked(staged_task_ids)
            accepted = self._tasks[accepted_id].copy()
            cleanup_after_submit = accepted.status.terminal
        if cleanup_after_submit:
            self._cleanup_old_tasks()
        return accepted

    def _rollback_submitted_tasks_locked(self, task_ids: List[str]) -> None:
        """回滚当前批次已创建但尚未稳定返回给调用方的任务。"""
        for task_id in task_ids:
            self._rollback_task_locked(task_id)
    
    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """
        获取任务信息
        
        Args:
            task_id: 任务 ID
            
        Returns:
            TaskInfo 或 None
        """
        with self._data_lock:
            task = self._tasks.get(task_id)
            return task.copy() if task else None

    def append_task_flow_event(
        self,
        task_id: str,
        flow_event: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Append a recent run-flow event to an active task and broadcast it.

        The event cache is deliberately bounded and fail-open; diagnostics must
        never affect the analysis pipeline.
        """
        try:
            event_payload = copy.deepcopy(flow_event)
        except Exception:
            logger.debug("[TaskQueue] 忽略不可复制的运行流事件: task_id=%s", task_id)
            return None

        with self._data_lock:
            task = self._tasks.get(task_id)
            if not task or task.status not in (TaskStatus.PENDING, TaskStatus.PROCESSING):
                return None
            task.flow_events.append(event_payload)
            if len(task.flow_events) > self._max_flow_events_per_task:
                task.flow_events = task.flow_events[-self._max_flow_events_per_task:]
            task.updated_at = datetime.now()
            task_snapshot = task.copy()
            payload = task_snapshot.to_dict()
            payload["flow_event"] = copy.deepcopy(event_payload)
            self._broadcast_event("task_progress", payload)
            return copy.deepcopy(event_payload)

    def get_task_flow_events(self, task_id: str) -> List[Dict[str, Any]]:
        """Return a copy of the recent run-flow events for a task."""
        with self._data_lock:
            task = self._tasks.get(task_id)
            if not task:
                return []
            return copy.deepcopy(task.flow_events)
    
    def list_pending_tasks(self) -> List[TaskInfo]:
        """
        获取所有进行中的任务（pending + processing）
        
        Returns:
            任务列表（副本）
        """
        with self._data_lock:
            return [
                task.copy() for task in self._tasks.values()
                if task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING, TaskStatus.CANCEL_REQUESTED)
            ]
    
    def list_all_tasks(self, limit: int = 50) -> List[TaskInfo]:
        """
        获取所有任务（按创建时间倒序）
        
        Args:
            limit: 返回数量限制
            
        Returns:
            任务列表（副本）
        """
        with self._data_lock:
            tasks = sorted(
                self._tasks.values(),
                key=lambda t: t.created_at,
                reverse=True
            )
            return [t.copy() for t in tasks[:limit]]
    
    def get_task_stats(self) -> Dict[str, int]:
        """
        获取任务统计信息
        
        Returns:
            统计信息字典
        """
        with self._data_lock:
            stats = {
                "total": len(self._tasks),
                "pending": 0,
                "processing": 0,
                "completed": 0,
                "failed": 0,
            }
            for task in self._tasks.values():
                stats[task.status.value] = stats.get(task.status.value, 0) + 1
            return stats

    def update_task_progress(
        self,
        task_id: str,
        progress: int,
        message: Optional[str] = None,
        *,
        message_code: Optional[str] = None,
        message_params: Optional[Dict[str, Any]] = None,
        event_type: str = "task_progress",
    ) -> Optional[TaskInfo]:
        """
        Update in-flight task progress and broadcast an SSE event.

        Only pending/processing tasks are updated. Progress is clamped to
        [0, 99] so terminal states remain controlled by completion/failure.
        """
        with self._data_lock:
            task = self._tasks.get(task_id)
            if not task or task.status not in (TaskStatus.PENDING, TaskStatus.PROCESSING):
                return None

            next_progress = max(task.progress, max(0, min(99, int(progress))))
            changed = False
            if next_progress != task.progress:
                task.progress = next_progress
                changed = True
            if message is not None and message != task.message:
                task.message = message
                changed = True
            resolved_code, resolved_params = _task_message_metadata(
                message,
                fallback_code=message_code or "task.processing",
            )
            next_message_code = message_code or resolved_code
            next_message_params = dict(message_params) if message_params is not None else resolved_params
            if next_message_code != task.message_code:
                task.message_code = next_message_code
                changed = True
            if next_message_params != task.message_params:
                task.message_params = next_message_params
                changed = True

            if not changed:
                return task.copy()

            task.updated_at = datetime.now()
            task_snapshot = task.copy()
            self._broadcast_event(event_type, task_snapshot.to_dict())
            return task_snapshot
    
    # ========== Task execution ==========

    def _claim_task_locked(
        self,
        task_id: str,
    ) -> Optional[Tuple[TaskInfo, TaskCommand]]:
        """Claim one pending task, or finish a pre-start cancellation."""
        task = self._tasks.get(task_id)
        if task is None or task.status.terminal:
            return None
        if task.status == TaskStatus.CANCEL_REQUESTED:
            self._terminalize_locked(task, TaskStatus.CANCELLED)
            return None
        if task.status != TaskStatus.PENDING:
            return None

        command = self._commands.get(task_id)
        if command is None:
            self._terminalize_locked(
                task,
                TaskStatus.FAILED,
                diagnostic_error="Task command is unavailable",
            )
            return None

        now = datetime.now()
        task.status = TaskStatus.PROCESSING
        task.started_at = now
        task.updated_at = now
        task.progress = max(task.progress, 10)
        if task.kind == "stock_analysis":
            task.message = "正在分析中..."
            task.message_code = "task.analysis.processing"
            task.message_params = {"stock_code": task.stock_code}
        else:
            task.message = "任务执行中"
            task.message_code = "task.processing"
            task.message_params = {}
        self._broadcast_event("task_started", task.to_dict())
        return task, command

    @staticmethod
    def _result_reference(result: Any) -> Optional[str]:
        if not isinstance(result, dict):
            return None
        for key in ("result_ref", "query_id", "id"):
            value = result.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return None

    def _terminalize_locked(
        self,
        task: TaskInfo,
        requested_status: TaskStatusEnum,
        *,
        result: Any = None,
        diagnostic_error: Optional[str] = None,
    ) -> bool:
        """Apply one terminal transition; the first lock winner owns the outcome."""
        if task.status.terminal:
            return False
        if not requested_status.terminal:
            raise ValueError(f"Task terminal status required: {requested_status.value}")

        status = requested_status
        if task.status == TaskStatus.CANCEL_REQUESTED and status != TaskStatus.INTERRUPTED:
            status = TaskStatus.CANCELLED

        detached_result = None
        result_ref = None
        if status == TaskStatus.COMPLETED:
            detached_result = deep_thaw(deep_freeze(result))
            result_ref = self._result_reference(detached_result)

        now = datetime.now()
        task.status = status
        task.updated_at = now
        task.completed_at = now
        task.diagnostic_error = diagnostic_error
        if status == TaskStatus.COMPLETED:
            task.progress = 100
            task.result = detached_result
            task.result_ref = result_ref
            task.error = None
            if isinstance(detached_result, dict):
                task.stock_name = detached_result.get("stock_name", task.stock_name)
            if task.kind == "stock_analysis":
                task.message = "分析完成"
                task.message_code = "task.analysis.completed"
                task.message_params = {"stock_code": task.stock_code}
            else:
                task.message = "任务执行完成"
                task.message_code = "task.completed"
                task.message_params = {}
            event_type = "task_completed"
        elif status == TaskStatus.FAILED:
            task.result = None
            task.result_ref = None
            task.error = task.failure_error_code
            if task.kind == "stock_analysis":
                task.message = "分析失败"
                task.message_code = "task.analysis.failed"
                task.message_params = {"stock_code": task.stock_code}
            else:
                task.message = "任务执行失败"
                task.message_code = "task.failed"
                task.message_params = {}
            event_type = "task_failed"
        elif status == TaskStatus.CANCELLED:
            task.result = None
            task.result_ref = None
            task.error = None
            task.message = "任务已取消"
            task.message_code = "task.cancelled"
            task.message_params = {}
            event_type = "task_failed"
        else:
            task.result = None
            task.result_ref = None
            task.error = None
            task.message = "任务因进程中断而停止"
            task.message_code = "task.interrupted"
            task.message_params = {}
            event_type = "task_failed"

        dedupe_key = self._task_dedupe_keys.get(task.task_id)
        if dedupe_key and self._analyzing_stocks.get(dedupe_key) == task.task_id:
            del self._analyzing_stocks[dedupe_key]
        self._broadcast_event(event_type, task.to_dict())
        return True

    def _run_analysis_command(self, context: TaskRunContext) -> Optional[Dict[str, Any]]:
        """Adapt the existing stock analysis service to a neutral command runner."""
        from src.services.analysis_service import AnalysisService

        metadata = deep_thaw(context.command.metadata)
        stock_code = str(metadata.get("stock_code") or "")
        service = AnalysisService()

        def on_progress(progress: int, message: str) -> None:
            context.update_progress(progress, message)

        result = service.analyze_stock(
            stock_code=stock_code,
            report_type=str(metadata.get("report_type") or "detailed"),
            force_refresh=bool(metadata.get("force_refresh")),
            query_id=context.task_id,
            trace_id=context.trace_id,
            send_notification=bool(metadata.get("notify", True)),
            progress_callback=on_progress,
            skills=copy.deepcopy(metadata.get("skills")),
            analysis_phase=str(metadata.get("analysis_phase") or "auto"),
            query_source=str(metadata.get("query_source") or "api"),
            portfolio_context=copy.deepcopy(metadata.get("portfolio_context")),
            report_language=metadata.get("report_language"),
        )
        if result is None:
            raise RuntimeError(service.last_error or "分析返回空结果")
        return result

    def _execute_command(self, task_id: str) -> Optional[Any]:
        """Run one accepted command through the canonical lifecycle engine."""
        with self._data_lock:
            claimed = self._claim_task_locked(task_id)
            if claimed is not None:
                task, command = claimed
                trace_id = task.trace_id or task_id
                stock_code = task.stock_code
                query_source = task.query_source or "api"
        if claimed is None:
            self._cleanup_old_tasks()
            return None

        context = TaskRunContext(
            task_id=task_id,
            trace_id=trace_id,
            command=command,
            update_progress=lambda progress, message=None: self.update_task_progress(
                task_id,
                progress,
                message,
            ),
            append_flow_event=lambda event: self.append_task_flow_event(task_id, dict(event)),
            is_cancel_requested=lambda: self._is_cancel_requested(task_id),
        )
        diagnostic_token = None
        try:
            if get_current_diagnostic_context() is None:
                diagnostic_token = activate_run_diagnostic_context(
                    trace_id=trace_id,
                    task_id=task_id,
                    query_id=task_id,
                    stock_code=stock_code,
                    trigger_source=query_source,
                    event_sink=lambda event: self.append_task_flow_event(task_id, event),
                )
            result = command.run(context)
            if result is None and not command.none_is_success:
                raise RuntimeError("任务返回空结果，未生成可持久化内容")

            with self._data_lock:
                current = self._tasks.get(task_id)
                transitioned = bool(
                    current
                    and self._terminalize_locked(
                        current,
                        TaskStatus.COMPLETED,
                        result=result,
                    )
                )
            if transitioned:
                logger.info("[TaskQueue] Task completed: %s (%s)", task_id, stock_code)
            self._cleanup_old_tasks()
            return result
        except BaseException as exc:  # noqa: B036 - worker failures become task state
            redaction_values = exception_chain_redaction_values(exc)
            diagnostic_error = sanitize_exception_chain(
                exc,
                redaction_values=redaction_values,
            )
            log_safe_exception(
                logger,
                "Task command failed",
                exc,
                error_code="task_command_failed",
                context={"task_id": task_id, "stock_code": stock_code},
                exception_redaction_values=redaction_values,
            )
            with self._data_lock:
                current = self._tasks.get(task_id)
                if current is not None:
                    self._terminalize_locked(
                        current,
                        TaskStatus.FAILED,
                        diagnostic_error=diagnostic_error,
                    )
            self._cleanup_old_tasks()
            return None
        finally:
            reset_run_diagnostic_context(diagnostic_token)
    
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

    # ========== Task event streams ==========

    def _snapshot_event_locked(self, task: TaskInfo, sequence: int) -> TaskEvent:
        return TaskEvent(
            sequence=sequence,
            task_id=task.task_id,
            type=TaskEventType.SNAPSHOT,
            snapshot=self._snapshot_locked(task),
            data=task.to_dict(),
            occurred_at=task.updated_at,
        )

    def subscribe(self, task_id: str) -> _QueueTaskEventStream:
        """Atomically subscribe to one task after replaying its current snapshot."""
        with self._data_lock:
            self._ensure_accepting_locked()
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            cutoff = self._event_sequence
            stream = _QueueTaskEventStream(
                self,
                task_id=task_id,
                cutoff=cutoff,
                max_queue_size=self._event_stream_queue_size,
            )
            if not task.status.terminal:
                self._streams[stream.token] = stream
            stream._enqueue_replay(
                self._snapshot_event_locked(task, cutoff),
                terminal_eof=task.status.terminal,
            )
            return stream

    def subscribe_all(self) -> _QueueTaskEventStream:
        """Atomically subscribe to all future events with active-task replay."""
        with self._data_lock:
            self._ensure_accepting_locked()
            cutoff = self._event_sequence
            active_tasks = [task for task in self._tasks.values() if not task.status.terminal]
            stream = _QueueTaskEventStream(
                self,
                task_id=None,
                cutoff=cutoff,
                max_queue_size=max(self._event_stream_queue_size, len(active_tasks) + 1),
            )
            self._streams[stream.token] = stream
            try:
                for task in active_tasks:
                    stream._enqueue_replay(self._snapshot_event_locked(task, cutoff))
            except BaseException:
                self._streams.pop(stream.token, None)
                stream._close_local()
                raise
            return stream

    def _broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish one legacy-shaped lifecycle event through canonical streams."""
        task_id = str(data.get("task_id") or "")
        if not task_id:
            return
        with self._data_lock:
            task = self._tasks.get(task_id)
            if task is not None:
                self._publish_event_locked(event_type, task, data)

    # ========== Cleanup ==========

    def shutdown(self) -> None:
        """Interrupt active work, wake waiters and close every event stream."""
        executor: Optional[ThreadPoolExecutor]
        with self._data_lock:
            if self._shutdown:
                return
            self._shutdown = True
            for task in tuple(self._tasks.values()):
                if not task.status.terminal:
                    self._terminalize_locked(task, TaskStatus.INTERRUPTED)

            shutdown_error = TaskQueueShutdownError()
            for reservation in self._retry_reservations.values():
                reservation.error = shutdown_error
                reservation.ready.set()
            self._retry_reservations.clear()

            streams = tuple(self._streams.values())
            self._streams.clear()
            for stream in streams:
                stream._schedule_finish()

            for future in self._futures.values():
                future.cancel()
            executor = self._executor
            self._executor = None

        if executor is not None:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                executor.shutdown(wait=False)
            logger.info(
                "[TaskQueue] Thread pool shutdown requested without waiting for active workers"
            )
        self._cleanup_old_tasks()


# ========== 便捷函数 ==========

def get_task_queue() -> AnalysisTaskQueue:
    """
    获取任务队列单例
    
    Returns:
        AnalysisTaskQueue 实例
    """
    queue = AnalysisTaskQueue()
    try:
        from src.config import get_config

        config = get_config()
        target_workers = max(1, int(getattr(config, "max_workers", queue.max_workers)))
        queue.sync_max_workers(target_workers, log=False)
    except Exception as exc:
        log_safe_exception(
            logger,
            "Task queue worker configuration lookup failed; keeping current concurrency",
            exc,
            error_code="task_queue_worker_config_lookup_failed",
            level=logging.DEBUG,
        )

    return queue
