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
from typing import (
    TYPE_CHECKING,
    Optional,
    Dict,
    List,
    Any,
    Tuple,
    Literal,
    Callable,
    Mapping,
    Protocol,
)

if TYPE_CHECKING:
    from src.services.task_queue import AnalysisTaskQueue

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

logger = logging.getLogger(__name__)

# Kinds that may be rebuilt from durable metadata after a process restart.
# Everything else is marked ``interrupted`` so operators never see a silent drop
# or a fake completion. This stays process-local (ADR-004 / ADR-008).
_REQUEUEABLE_TASK_KINDS = frozenset({"stock_analysis"})
_RECOVERY_CLASS_REQUEUE = "requeue"
_RECOVERY_CLASS_INTERRUPT = "interrupt"
_MESSAGE_CODE_RECOVERED_REQUEUED = "task.recovered.requeued"
_MESSAGE_CODE_INTERRUPTED_PROCESS_RESTART = "task.interrupted.process_restart"


class TaskQueueInflightStore(Protocol):
    """Minimal checkpoint port used by restart recovery."""

    def try_upsert(self, fields: Dict[str, Any]) -> bool: ...

    def try_delete(self, task_id: str) -> bool: ...

    def list_inflight(self) -> List[Any]: ...


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


class KnownTaskFailure(Exception):
    """Command failure that already carries a stable public error code."""

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        message_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = str(error_code or "").strip() or "task_failed"
        self.message = str(message or "").strip() or self.error_code
        self.message_params = copy.deepcopy(message_params or {})


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
    message_code = getattr(task, "message_code", None)
    if message_code == "llm_not_configured":
        return "No LLM model is configured"
    if message_code == "local_market_data_missing":
        return "Local market data does not cover the requested analysis window"
    if message_code == "task.analysis.failed":
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
    region: Optional[str] = None
    flow_events: List[Dict[str, Any]] = field(default_factory=list)

    def public_error(self) -> Optional[str]:
        """Return only a stable error code for public task payloads."""
        return public_task_error(self, default_error_code="task_failed")

    def public_message(self) -> Optional[str]:
        """Return status copy that cannot contain a provider exception."""
        return public_task_message(self)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task info into an API-friendly dictionary."""
        payload = {
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
        if self.region is not None:
            payload["region"] = self.region
        return payload
    
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
            region=self.region,
            flow_events=copy.deepcopy(self.flow_events),
        )


@dataclass(frozen=True)
class AnalysisTaskCoalescingContract:
    """Immutable result and side-effect contract for one stock analysis."""

    stock_code: str
    report_type: str
    analysis_phase: str
    force_refresh: bool
    notify: bool
    skills: Any
    report_language: Optional[str]
    use_memory: Optional[bool]
    portfolio_context: Any
    query_source: str
    context_bound: bool
    strict_skill_selection: bool = False

    @classmethod
    def from_metadata(
        cls,
        metadata: Mapping[str, Any],
    ) -> Optional['AnalysisTaskCoalescingContract']:
        """Build the normalized execution contract from command metadata."""
        stock_code = _dedupe_stock_code_key(
            str(metadata.get("stock_code") or "")
        )
        if not stock_code:
            return None
        raw_skills = metadata.get("skills")
        raw_use_memory = metadata.get("use_memory")
        raw_report_language = metadata.get("report_language")
        return cls(
            stock_code=stock_code,
            report_type=ReportType.from_str(
                str(metadata.get("report_type") or "detailed")
            ).value,
            analysis_phase=str(metadata.get("analysis_phase") or "auto"),
            force_refresh=bool(metadata.get("force_refresh", False)),
            notify=bool(metadata.get("notify", True)),
            skills=deep_freeze(raw_skills),
            strict_skill_selection=bool(
                metadata.get("strict_skill_selection", False)
            ),
            report_language=(
                normalize_report_language(raw_report_language, default="")
                if raw_report_language is not None
                else None
            ),
            use_memory=(
                bool(raw_use_memory) if raw_use_memory is not None else None
            ),
            portfolio_context=deep_freeze(metadata.get("portfolio_context")),
            query_source=str(metadata.get("query_source") or "api"),
            context_bound=bool(metadata.get("context_bound", False)),
        )

    @classmethod
    def from_command(
        cls,
        command: Optional[TaskCommand],
    ) -> Optional['AnalysisTaskCoalescingContract']:
        """Build the normalized execution contract from an immutable command."""
        if command is None or command.kind != "stock_analysis":
            return None
        metadata = deep_thaw(command.metadata)
        return cls.from_metadata(metadata)


class DuplicateTaskError(Exception):
    """Raised when a stock already has an active analysis task."""

    def __init__(
        self,
        stock_code: str,
        existing_task_id: str,
        *,
        existing_contract: Optional[AnalysisTaskCoalescingContract] = None,
        requested_contract: Optional[AnalysisTaskCoalescingContract] = None,
    ):
        self.stock_code = stock_code
        self.existing_task_id = existing_task_id
        self.existing_contract = existing_contract
        self.requested_contract = requested_contract
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


# Preserve the legacy facade identities used by introspection and pickle.
for _legacy_facade_member in (
    AnalysisTaskCoalescingContract,
    DuplicateTaskError,
    KnownTaskFailure,
    TaskInfo,
    TaskQueueInflightStore,
    _QueueTaskEventStream,
    _RetryReservation,
    _dedupe_stock_code_key,
    _task_message_metadata,
    public_task_error,
    public_task_message,
):
    _legacy_facade_member.__module__ = "src.services.task_queue"

del _legacy_facade_member
