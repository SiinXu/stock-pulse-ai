# -*- coding: utf-8 -*-
"""Restart recovery and durable inflight checkpoint methods for AnalysisTaskQueue."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.task_queue import (
        Any,
        Dict,
        Optional,
        TaskCommand,
        TaskInfo,
        TaskQueueInflightCheckpoint,
        TaskQueueInflightStore,
        TaskStatus,
        _MESSAGE_CODE_INTERRUPTED_PROCESS_RESTART,
        _MESSAGE_CODE_RECOVERED_REQUEUED,
        _RECOVERY_CLASS_INTERRUPT,
        _RECOVERY_CLASS_REQUEUE,
        _REQUEUEABLE_TASK_KINDS,
        copy,
        datetime,
        deep_thaw,
        log_safe_exception,
        logger,
        logging,
        replace,
    )

class _TaskQueueRecoveryMethods:
    """Method group bound onto the public facade class."""

    def _get_inflight_store(self) -> Optional[TaskQueueInflightStore]:
        """Resolve the checkpoint store lazily so tests can inject a fake."""
        if self._inflight_store_resolved:
            return self._inflight_store
        self._inflight_store_resolved = True
        try:
            from src.repositories.task_queue_inflight_repo import (
                TaskQueueInflightRepository,
            )

            self._inflight_store = TaskQueueInflightRepository()
        except Exception as exc:  # broad-exception: fallback_recorded - recovery is best-effort when DB is unavailable
            log_safe_exception(
                logger,
                "Task queue inflight store initialization failed",
                exc,
                error_code="task_queue_inflight_store_init_failed",
                level=logging.WARNING,
            )
            self._inflight_store = None
        return self._inflight_store

    @staticmethod
    def recovery_class_for_kind(kind: str) -> str:
        """Return the restart recovery policy for a task kind."""
        if str(kind or "") in _REQUEUEABLE_TASK_KINDS:
            return _RECOVERY_CLASS_REQUEUE
        return _RECOVERY_CLASS_INTERRUPT

    def _checkpoint_fields_locked(
        self,
        task: TaskInfo,
        command: Optional[TaskCommand] = None,
        *,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build durable checkpoint fields for one non-terminal task."""
        command = command or self._commands.get(task.task_id)
        metadata = deep_thaw(command.metadata) if command is not None else {
            "stock_code": task.stock_code,
            "stock_name": task.stock_name,
            "report_type": task.report_type,
            "analysis_phase": task.analysis_phase,
            "original_query": task.original_query,
            "selection_source": task.selection_source,
            "query_source": task.query_source,
            "portfolio_context": copy.deepcopy(task.portfolio_context),
            "skills": copy.deepcopy(task.skills),
            "report_language": task.report_language,
            "region": task.region,
        }
        return {
            "task_id": task.task_id,
            "kind": task.kind,
            "status": status or task.status.value,
            "stock_code": task.stock_code,
            "recovery_class": self.recovery_class_for_kind(task.kind),
            "dedupe_key": self._task_dedupe_keys.get(task.task_id)
            or (command.dedupe_key if command is not None else None),
            "idempotency_key": self._task_idempotency_keys.get(task.task_id)
            or (command.idempotency_key if command is not None else None),
            "idempotency_fingerprint": (
                command.idempotency_fingerprint if command is not None else None
            ),
            "failure_error_code": (
                command.failure_error_code
                if command is not None
                else task.failure_error_code
            ),
            "none_is_success": bool(
                command.none_is_success if command is not None else False
            ),
            "metadata": metadata,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }

    def _persist_inflight_locked(
        self,
        task: TaskInfo,
        command: Optional[TaskCommand] = None,
        *,
        status: Optional[str] = None,
    ) -> None:
        """Persist a non-terminal checkpoint (best-effort, never blocks workers)."""
        if task.status.terminal:
            return
        store = self._get_inflight_store()
        if store is None:
            return
        store.try_upsert(self._checkpoint_fields_locked(task, command, status=status))

    def _clear_inflight_locked(self, task_id: str) -> None:
        """Drop the durable checkpoint after terminalization or rollback."""
        store = self._get_inflight_store()
        if store is None:
            return
        store.try_delete(task_id)

    def recover_persisted_inflight(self) -> Dict[str, int]:
        """Reconcile durable in-flight checkpoints left by a previous process.

        Safe-to-requeue kinds are re-admitted with the same task id and a recovery
        marker. Non-resumable kinds become terminal ``interrupted`` with an explicit
        message code. Completed work never appears in the checkpoint table.

        Must run before scheduled-task reconciliation so schedule occurrence fences
        observe restored execution ids instead of ``execution_state_lost``.
        """
        stats = {"requeued": 0, "interrupted": 0, "skipped": 0}
        with self._data_lock:
            if self._recovery_applied:
                return stats
            if self._shutdown:
                self._recovery_applied = True
                return stats
            self._recovery_applied = True
            store = self._get_inflight_store()
            if store is None:
                return stats
            try:
                checkpoints = list(store.list_inflight())
            except Exception as exc:  # broad-exception: fallback_recorded - recovery must not prevent startup
                log_safe_exception(
                    logger,
                    "Task queue restart recovery listing failed",
                    exc,
                    error_code="task_queue_restart_recovery_list_failed",
                    level=logging.WARNING,
                )
                return stats

            for checkpoint in checkpoints:
                task_id = str(getattr(checkpoint, "task_id", "") or "").strip()
                if not task_id:
                    stats["skipped"] += 1
                    continue
                if task_id in self._tasks:
                    stats["skipped"] += 1
                    continue
                kind = str(getattr(checkpoint, "kind", "") or "")
                recovery_class = str(
                    getattr(checkpoint, "recovery_class", "") or ""
                ) or self.recovery_class_for_kind(kind)
                status_value = str(getattr(checkpoint, "status", "") or "")
                if (
                    recovery_class == _RECOVERY_CLASS_REQUEUE
                    and kind in _REQUEUEABLE_TASK_KINDS
                    and status_value != TaskStatus.CANCEL_REQUESTED.value
                ):
                    if self._recover_requeue_checkpoint_locked(checkpoint):
                        stats["requeued"] += 1
                    else:
                        self._recover_interrupt_checkpoint_locked(checkpoint)
                        stats["interrupted"] += 1
                else:
                    self._recover_interrupt_checkpoint_locked(checkpoint)
                    stats["interrupted"] += 1

        if stats["requeued"] or stats["interrupted"]:
            logger.info(
                "[TaskQueue] Restart recovery complete: requeued=%s interrupted=%s skipped=%s",
                stats["requeued"],
                stats["interrupted"],
                stats["skipped"],
            )
        return stats

    def _recover_requeue_checkpoint_locked(self, checkpoint: TaskQueueInflightCheckpoint) -> bool:
        """Rebuild and re-admit one requeueable stock-analysis command."""
        task_id = str(checkpoint.task_id)
        metadata = dict(getattr(checkpoint, "metadata", None) or {})
        stock_code = str(
            metadata.get("stock_code")
            or getattr(checkpoint, "stock_code", "")
            or ""
        ).strip()
        if not stock_code:
            return False
        try:
            command = self._build_analysis_command(
                stock_code=stock_code,
                stock_name=metadata.get("stock_name"),
                original_query=metadata.get("original_query"),
                selection_source=metadata.get("selection_source"),
                query_source=str(metadata.get("query_source") or "api"),
                portfolio_context=copy.deepcopy(metadata.get("portfolio_context")),
                report_type=str(metadata.get("report_type") or "detailed"),
                analysis_phase=str(metadata.get("analysis_phase") or "auto"),
                force_refresh=bool(metadata.get("force_refresh")),
                notify=bool(metadata.get("notify", True)),
                skills=copy.deepcopy(metadata.get("skills")),
                report_language=metadata.get("report_language"),
                use_memory=metadata.get("use_memory"),
                request_context=None,
                strict_skill_selection=bool(
                    metadata.get("strict_skill_selection", False)
                ),
            )
            if getattr(checkpoint, "idempotency_key", None):
                command = replace(
                    command,
                    idempotency_key=str(checkpoint.idempotency_key),
                    idempotency_fingerprint=str(
                        checkpoint.idempotency_fingerprint
                        or command.idempotency_fingerprint
                    ),
                )
            staged_id, task, created = self._stage_command_locked(
                command,
                task_id=task_id,
            )
            if not created or staged_id != task_id:
                return False
            task.message = "任务已从进程重启中恢复并重新排队"
            task.message_code = _MESSAGE_CODE_RECOVERED_REQUEUED
            task.message_params = {"stock_code": stock_code}
            task.updated_at = datetime.now()
            if getattr(checkpoint, "created_at", None) is not None:
                task.created_at = checkpoint.created_at
            staged_task_ids = [task_id]
            self._suppress_task_events_locked(staged_task_ids)
            try:
                self._broadcast_event("task_created", task.to_dict())
                self._submit_staged_commands_locked(staged_task_ids)
                self._persist_inflight_locked(task, command, status=TaskStatus.PENDING.value)
            except BaseException:
                self._discard_task_events_locked(staged_task_ids)
                self._rollback_task_locked(task_id)
                raise
            self._flush_task_events_locked(staged_task_ids)
            logger.info(
                "[TaskQueue] Recovered requeueable task after restart: %s (%s)",
                task_id,
                stock_code,
            )
            return True
        except Exception as exc:  # broad-exception: fallback_recorded - fall through to interrupt
            log_safe_exception(
                logger,
                "Task queue requeue recovery failed; marking interrupted",
                exc,
                error_code="task_queue_requeue_recovery_failed",
                level=logging.WARNING,
                context={"task_id": task_id, "stock_code": stock_code},
            )
            return False

    def _recover_interrupt_checkpoint_locked(self, checkpoint: TaskQueueInflightCheckpoint) -> None:
        """Materialize one non-resumable checkpoint as terminal interrupted."""
        task_id = str(checkpoint.task_id)
        metadata = dict(getattr(checkpoint, "metadata", None) or {})
        stock_code = str(
            metadata.get("stock_code")
            or getattr(checkpoint, "stock_code", "")
            or task_id
        )
        now = datetime.now()
        task = TaskInfo(
            task_id=task_id,
            kind=str(getattr(checkpoint, "kind", "") or "background"),
            stock_code=stock_code,
            stock_name=metadata.get("stock_name"),
            status=TaskStatus.INTERRUPTED,
            progress=0,
            message="任务因进程重启中断，无法安全恢复",
            message_code=_MESSAGE_CODE_INTERRUPTED_PROCESS_RESTART,
            message_params={"stock_code": stock_code} if stock_code else {},
            report_type=str(metadata.get("report_type") or "detailed"),
            analysis_phase=str(metadata.get("analysis_phase") or "auto"),
            original_query=metadata.get("original_query"),
            selection_source=metadata.get("selection_source"),
            query_source=str(metadata.get("query_source") or "api"),
            portfolio_context=copy.deepcopy(metadata.get("portfolio_context")),
            skills=copy.deepcopy(metadata.get("skills")),
            report_language=metadata.get("report_language"),
            region=metadata.get("region"),
            failure_error_code=str(
                getattr(checkpoint, "failure_error_code", None) or "task_interrupted"
            ),
            created_at=getattr(checkpoint, "created_at", None) or now,
            updated_at=now,
            completed_at=now,
            trace_id=task_id,
        )
        self._tasks[task_id] = task
        self._broadcast_event("task_failed", task.to_dict())
        self._clear_inflight_locked(task_id)
        logger.info(
            "[TaskQueue] Marked non-resumable task interrupted after restart: %s (%s)",
            task_id,
            task.kind,
        )
