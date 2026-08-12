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

Implementation is split by responsibility under this package:
``models`` / ``store`` / ``worker`` / ``recovery`` / ``api``.
This module remains the stable import facade.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from src.utils.sanitize import log_safe_exception
from src.repositories.task_queue_inflight_repo import TaskQueueInflightCheckpoint
import re
import threading
import uuid
import weakref
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any, Tuple, Literal, Callable, Mapping, Protocol

from data_provider.base import canonical_stock_code, normalize_stock_code
from src.enums import ReportType
from src.report_language import normalize_report_language
from src.schemas.request_context import AnalysisRequestContext
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    get_current_diagnostic_context,
    reset_run_diagnostic_context,
)
from src.services.stock_code_utils import resolve_index_stock_code_for_analysis
from src.task_execution import (
    TaskCommand,
    TaskEvent,
    TaskEventType,
    TaskIdempotencyConflictError,
    TaskNotFoundError,
    TaskQueueShutdownError,
    TaskRetryInProgressError,
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
from src.utils.analysis_metadata import SELECTION_SOURCES
from src.utils.sanitize import (
    exception_chain_redaction_values,
    log_safe_exception,
    sanitize_exception_chain,
)

from src.services.task_queue.models import (
    AnalysisTaskCoalescingContract,
    DuplicateTaskError,
    KnownTaskFailure,
    TaskInfo,
    TaskQueueInflightStore,
    _MESSAGE_CODE_INTERRUPTED_PROCESS_RESTART,
    _MESSAGE_CODE_RECOVERED_REQUEUED,
    _QueueTaskEventStream,
    _RECOVERY_CLASS_INTERRUPT,
    _RECOVERY_CLASS_REQUEUE,
    _REQUEUEABLE_TASK_KINDS,
    _RetryReservation,
    _STABLE_TASK_ERROR_CODE,
    _STREAM_EOF,
    _TASK_MESSAGE_SUFFIX_CODES,
    _dedupe_stock_code_key,
    _task_message_metadata,
    public_task_error,
    public_task_message,
)

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        max_workers: int = 3,
        *,
        inflight_store: Optional[TaskQueueInflightStore] = None,
    ):
        # Prevent repeated initialization.
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None

        # Core Data Structure
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
        self._inflight_store: Optional[TaskQueueInflightStore] = inflight_store
        self._inflight_store_resolved = inflight_store is not None
        self._recovery_applied = False

        # Thread-safe lock
        self._data_lock = threading.RLock()

        # Task Historical Retention Quantity (In Memory)
        self._max_history = 100
        self._max_flow_events_per_task = 200

        self._initialized = True
        logger.info(f"[TaskQueue] 初始化完成，最大并发: {max_workers}")


# Bind responsibility-split methods onto the facade class (behavior-preserving).
from src.services.task_queue.binding import bind_part_class as _bind_part_class
from src.services.task_queue.recovery import _TaskQueueRecoveryMethods as _TQRecovery
from src.services.task_queue.store import _TaskQueueStoreMethods as _TQStore
from src.services.task_queue.worker import _TaskQueueWorkerMethods as _TQWorker
from src.services.task_queue.api import _TaskQueueApiMethods as _TQApi

for _part in (_TQRecovery, _TQStore, _TQWorker, _TQApi):
    _bind_part_class(
        _part,
        AnalysisTaskQueue,
        globals(),
        module_name=__name__,
        owner_name="AnalysisTaskQueue",
    )

del _bind_part_class, _TQRecovery, _TQStore, _TQWorker, _TQApi, _part


# ========== Convenience Functions ==========

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
    except Exception as exc:  # broad-exception: fallback_recorded - keep current concurrency on config lookup failure
        log_safe_exception(
            logger,
            "Task queue worker configuration lookup failed; keeping current concurrency",
            exc,
            error_code="task_queue_worker_config_lookup_failed",
            level=logging.DEBUG,
        )

    return queue


__all__ = (
    "AnalysisTaskCoalescingContract",
    "AnalysisTaskQueue",
    "DuplicateTaskError",
    "KnownTaskFailure",
    "TaskInfo",
    "TaskQueueInflightStore",
    "TaskStatus",
    "get_task_queue",
    "public_task_error",
    "public_task_message",
    "_dedupe_stock_code_key",
    "_task_message_metadata",
)
