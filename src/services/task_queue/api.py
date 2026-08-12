# -*- coding: utf-8 -*-
"""Enqueue, status, cancel/retry, and subscription API methods for AnalysisTaskQueue."""

from __future__ import annotations

class _TaskQueueApiMethods:
    """Method group bound onto the public facade class."""

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
            region=metadata.get("region"),
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
        self._clear_inflight_locked(task_id)

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
                existing_contract=AnalysisTaskCoalescingContract.from_command(
                    self._commands.get(existing_task_id)
                ),
                requested_contract=AnalysisTaskCoalescingContract.from_command(command),
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
        # Crash-consistency boundary: durable pending before executor admission.
        self._persist_inflight_locked(task, command, status=TaskStatus.PENDING.value)
        return task_id, task, True

    def _submit_staged_commands_locked(self, task_ids: List[str]) -> None:
        for task_id in task_ids:
            future = self.executor.submit(self._execute_command, task_id)
            self._futures[task_id] = future
            callback = self._commands[task_id].on_done
            if callback is not None:
                future.add_done_callback(
                    lambda _future, on_done=callback: self._run_completion_cleanup(
                        on_done
                    )
                )

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
                self._persist_inflight_locked(
                    task,
                    status=TaskStatus.CANCEL_REQUESTED.value,
                )
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

    def retry(
        self,
        task_id: str,
        *,
        wait_for_in_progress: bool = True,
    ) -> str:
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
                if not wait_for_in_progress:
                    raise TaskRetryInProgressError(task_id)
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
            shared_error: Optional[BaseException] = None
            with self._data_lock:
                current = self._retry_reservations.get(task_id)
                if current is reservation:
                    reservation.error = exc
                    del self._retry_reservations[task_id]
                    reservation.ready.set()
                elif reservation.error is not None:
                    shared_error = reservation.error
            if shared_error is not None and shared_error is not exc:
                raise shared_error
            raise

        return child_task_id

    def retry_nowait(self, task_id: str) -> str:
        """Retry without waiting behind another process-local admission owner."""
        return self.retry(task_id, wait_for_in_progress=False)

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
        use_memory: Optional[bool] = None,
        request_context: Optional[AnalysisRequestContext] = None,
        strict_skill_selection: bool = False,
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
            "strict_skill_selection": bool(strict_skill_selection),
            "report_language": report_language,
            "use_memory": use_memory,
            "context_bound": request_context is not None,
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
                strict_skill_selection=strict_skill_selection,
                report_language=report_language,
                use_memory=use_memory,
                request_context=request_context,
            )

        # Carry the contextual reply targets through a closure instead of the
        # frozen metadata: the DingTalk/Feishu/Telegram reply addresses must not
        # enter task snapshots, SSE payloads, or the idempotency fingerprint.
        def run(context: TaskRunContext) -> Optional[Dict[str, Any]]:
            return self._run_analysis_command(context, request_context=request_context)

        return TaskCommand(
            kind="stock_analysis",
            run=run,
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
        use_memory: Optional[bool] = None,
        request_context: Optional[AnalysisRequestContext] = None,
        *,
        strict_skill_selection: bool = False,
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
            request_context: Optional requester provenance and contextual reply
                targets used to push results back to the originating channel.

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
            strict_skill_selection=strict_skill_selection,
            report_language=report_language,
            use_memory=use_memory,
            request_context=request_context,
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
        use_memory: Optional[bool] = None,
        request_context: Optional[AnalysisRequestContext] = None,
        *,
        strict_skill_selection: bool = False,
    ) -> Tuple[List[TaskInfo], List[DuplicateTaskError]]:
        """
        Submit analysis tasks in batch.

        - Duplicate stocks are skipped and recorded in duplicates.
        - If executor submission fails, the current batch is rolled back.
        - ``request_context`` is shared by every command in the batch so Bot
          submissions keep pushing results to the originating conversation.
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
                strict_skill_selection=strict_skill_selection,
                report_language=report_language,
                use_memory=use_memory,
                request_context=request_context,
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
        region: Optional[str] = None,
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
            "region": region,
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
        except Exception as exc:  # broad-exception: fallback_recorded - ignore uncopyable run-stream events
            log_safe_exception(
                logger,
                "Task queue ignored uncopyable run-stream event",
                exc,
                error_code="task_queue_uncopyable_run_stream_event",
                level=logging.DEBUG,
                context={"task_id": task_id},
            )
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
