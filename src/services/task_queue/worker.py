# -*- coding: utf-8 -*-
"""Command execution and terminalization methods for AnalysisTaskQueue."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.task_queue import (
        AnalysisRequestContext,
        Any,
        Callable,
        Dict,
        KnownTaskFailure,
        Optional,
        TaskCommand,
        TaskInfo,
        TaskRunContext,
        TaskStatus,
        TaskStatusEnum,
        Tuple,
        activate_run_diagnostic_context,
        copy,
        datetime,
        deep_freeze,
        deep_thaw,
        exception_chain_redaction_values,
        get_current_diagnostic_context,
        log_safe_exception,
        logger,
        logging,
        reset_run_diagnostic_context,
        sanitize_exception_chain,
    )

class _TaskQueueWorkerMethods:
    """Method group bound onto the public facade class."""

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

    def _commit_final_result(
        self,
        task_id: str,
        operation: Callable[[], Any],
    ) -> tuple[bool, Any]:
        """Linearize one bounded final side effect with task completion."""
        with self._data_lock:
            task = self._tasks.get(task_id)
            if task is None or task.status.terminal:
                return False, None
            if task.status == TaskStatus.CANCEL_REQUESTED:
                self._terminalize_locked(task, TaskStatus.CANCELLED)
                return False, None
            if task.status != TaskStatus.PROCESSING:
                return False, None

            result = operation()
            transitioned = self._terminalize_locked(
                task,
                TaskStatus.COMPLETED,
                result=result,
            )
            if transitioned:
                logger.info(
                    "[TaskQueue] Task completed: %s (%s)",
                    task_id,
                    task.stock_code,
                )
            return transitioned, result if transitioned else None

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
        # Crash-consistency boundary: processing claim is durable before runner work.
        self._persist_inflight_locked(
            task,
            command,
            status=TaskStatus.PROCESSING.value,
        )
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
        failure_message: Optional[str] = None,
        failure_message_code: Optional[str] = None,
        failure_message_params: Optional[Dict[str, Any]] = None,
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
            if task.failure_error_code == "llm_not_configured":
                # Known first-run configuration gap: surface the stable code on
                # message_code/error so polling, history, and run-flow can map UI copy.
                task.message = "No LLM model is configured"
                task.message_code = "llm_not_configured"
                task.message_params = (
                    {"stock_code": task.stock_code}
                    if task.kind == "stock_analysis"
                    else {}
                )
            elif failure_message_code:
                task.message = failure_message or "任务执行失败"
                task.message_code = failure_message_code
                task.message_params = copy.deepcopy(failure_message_params or {})
            elif task.kind == "stock_analysis":
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
        # Terminal outcomes must not remain eligible for restart recovery.
        self._clear_inflight_locked(task.task_id)
        self._broadcast_event(event_type, task.to_dict())
        return True

    def _run_analysis_command(
        self,
        context: TaskRunContext,
        request_context: Optional[AnalysisRequestContext] = None,
    ) -> Optional[Dict[str, Any]]:
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
            strict_skill_selection=bool(
                metadata.get("strict_skill_selection", False)
            ),
            analysis_phase=str(metadata.get("analysis_phase") or "auto"),
            query_source=str(metadata.get("query_source") or "api"),
            portfolio_context=copy.deepcopy(metadata.get("portfolio_context")),
            report_language=metadata.get("report_language"),
            use_memory=metadata.get("use_memory"),
            request_context=request_context,
        )
        if result is None:
            error_message = service.last_error or "分析返回空结果"
            from src.services.analysis_service import (
                LLM_NOT_CONFIGURED_ERROR_CODE,
                LOCAL_MARKET_DATA_MISSING_ERROR_CODE,
                is_llm_not_configured_error,
            )

            if is_llm_not_configured_error(service.last_error_code, error_message):
                raise KnownTaskFailure(
                    LLM_NOT_CONFIGURED_ERROR_CODE,
                    error_message,
                )
            if service.last_error_code == LOCAL_MARKET_DATA_MISSING_ERROR_CODE:
                raise KnownTaskFailure(
                    LOCAL_MARKET_DATA_MISSING_ERROR_CODE,
                    error_message,
                    message_params=getattr(service, "last_error_details", None),
                )
            raise RuntimeError(error_message)
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
            commit_final_result=lambda operation: self._commit_final_result(
                task_id,
                operation,
            ),
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
        except BaseException as exc:
            # broad-exception: fallback_recorded - worker failures become sanitized task state.
            redaction_values = exception_chain_redaction_values(exc)
            diagnostic_error = sanitize_exception_chain(
                exc,
                redaction_values=redaction_values,
            )
            known_failure_code = (
                exc.error_code
                if isinstance(exc, KnownTaskFailure) and exc.error_code
                else None
            )
            log_safe_exception(
                logger,
                "Task command failed",
                exc,
                error_code=known_failure_code or "task_command_failed",
                context={"task_id": task_id, "stock_code": stock_code},
                exception_redaction_values=redaction_values,
            )
            with self._data_lock:
                current = self._tasks.get(task_id)
                if current is not None:
                    if known_failure_code:
                        current.failure_error_code = known_failure_code
                    self._terminalize_locked(
                        current,
                        TaskStatus.FAILED,
                        diagnostic_error=diagnostic_error,
                        failure_message=(
                            exc.message if isinstance(exc, KnownTaskFailure) else None
                        ),
                        failure_message_code=known_failure_code,
                        failure_message_params=(
                            exc.message_params
                            if isinstance(exc, KnownTaskFailure)
                            else None
                        ),
                    )
            self._cleanup_old_tasks()
            return None
        finally:
            reset_run_diagnostic_context(diagnostic_token)

    @staticmethod
    def _run_completion_cleanup(callback: Callable[[], Any]) -> None:
        """Run resource cleanup without changing the command's terminal state."""
        try:
            callback()
        except Exception as exc:  # broad-exception: fallback_recorded - isolate cleanup failures
            log_safe_exception(
                logger,
                "Task completion cleanup failed",
                exc,
                error_code="task_completion_cleanup_failed",
                level=logging.WARNING,
                exception_redaction_values=exception_chain_redaction_values(exc),
            )
