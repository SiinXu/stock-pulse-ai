# -*- coding: utf-8 -*-
"""Transport-neutral orchestration for durable analysis submissions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from src.report_language import normalize_report_language
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
)
from src.services.task_queue import get_task_queue as _default_get_task_queue
from data_provider.base import normalize_stock_code


@dataclass(frozen=True)
class AnalysisSubmissionCommand:
    """Validated values needed to enqueue one durable analysis batch."""

    stock_codes: tuple[str, ...]
    report_type: str = "detailed"
    analysis_phase: str = "auto"
    force_refresh: bool = False
    notify: bool = True
    stock_name: str | None = None
    original_query: str | None = None
    selection_source: str | None = None
    report_language: str | None = None
    skills: tuple[str, ...] | None = None
    use_memory: bool | None = None


@dataclass(frozen=True)
class AnalysisSubmissionResult:
    """Queue-owned results kept independent from HTTP response models."""

    accepted_tasks: tuple[Any, ...]
    duplicate_errors: tuple[Any, ...]


class AnalysisSubmissionService:
    """Submit analysis work once for all delivery adapters."""

    def __init__(self, *, get_task_queue: Callable[[], Any] | None = None) -> None:
        self.get_task_queue = get_task_queue or _default_get_task_queue

    @staticmethod
    def record_audit(
        service: SecurityAuditRecorder,
        *,
        phase: str,
        correlation_id: str,
        stock_code: str,
        outcome: str = "pending",
        reason_code: str = "attempt_started",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        common = dict(
            event_type="analysis.submit",
            actor_type="api_client",
            actor_id="analysis_submitter",
            execution_id=correlation_id,
            action="analysis.submit",
            target_type="stock",
            target_id=stock_code,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )
        if phase == "attempt":
            service.record_attempt(**common)
        else:
            service.record_completion(
                **common,
                outcome=outcome,
                reason_code=reason_code,
            )

    def submit(
        self,
        command: AnalysisSubmissionCommand,
        *,
        security_audit: SecurityAuditRecorder,
    ) -> AnalysisSubmissionResult:
        """Persist a batch submission and its complete audit lifecycle."""
        stock_codes = list(command.stock_codes)
        is_single = len(stock_codes) == 1
        preserve_batch_metadata = command.selection_source in {"import", "image"}
        report_language = normalize_report_language(command.report_language, default="")

        submit_kwargs: dict[str, Any] = {
            "stock_codes": stock_codes,
            "stock_name": command.stock_name if is_single else None,
            "original_query": (
                command.original_query
                if is_single or preserve_batch_metadata
                else None
            ),
            "selection_source": (
                command.selection_source
                if is_single or preserve_batch_metadata
                else None
            ),
            "report_type": command.report_type,
            "analysis_phase": command.analysis_phase,
            "force_refresh": command.force_refresh,
            "notify": command.notify,
        }
        if report_language:
            submit_kwargs["report_language"] = report_language
        if command.skills is not None:
            submit_kwargs["skills"] = list(command.skills)
        if command.use_memory is not None:
            submit_kwargs["use_memory"] = command.use_memory

        correlations = {
            stock_code: SecurityAuditService.new_correlation_id()
            for stock_code in stock_codes
        }
        audit_metadata = {
            "report_type": command.report_type,
            "analysis_phase": command.analysis_phase,
            "batch_size": len(stock_codes),
        }
        for stock_code in stock_codes:
            self.record_audit(
                security_audit,
                phase="attempt",
                correlation_id=correlations[stock_code],
                stock_code=stock_code,
                metadata=audit_metadata,
            )

        try:
            accepted_tasks, duplicate_errors = (
                self.get_task_queue().submit_tasks_batch(**submit_kwargs)
            )
        except Exception:
            for stock_code in stock_codes:
                self.record_audit(
                    security_audit,
                    phase="completion",
                    correlation_id=correlations[stock_code],
                    stock_code=stock_code,
                    outcome="failure",
                    reason_code="task_submission_failed",
                    metadata=audit_metadata,
                )
            raise

        accepted_codes = {
            normalize_stock_code(task.stock_code) for task in accepted_tasks
        }
        duplicate_codes = {
            normalize_stock_code(duplicate.stock_code)
            for duplicate in duplicate_errors
        }
        for stock_code in stock_codes:
            normalized_stock_code = normalize_stock_code(stock_code)
            if normalized_stock_code in accepted_codes:
                outcome, reason_code = "accepted", "task_accepted"
            elif normalized_stock_code in duplicate_codes:
                outcome, reason_code = "rejected", "duplicate_task"
            else:
                outcome, reason_code = "failure", "submission_not_resolved"
            self.record_audit(
                security_audit,
                phase="completion",
                correlation_id=correlations[stock_code],
                stock_code=stock_code,
                outcome=outcome,
                reason_code=reason_code,
                metadata=audit_metadata,
            )

        return AnalysisSubmissionResult(
            accepted_tasks=tuple(accepted_tasks),
            duplicate_errors=tuple(duplicate_errors),
        )


def build_submission_command(
    *,
    stock_codes: Sequence[str],
    report_type: str = "detailed",
    analysis_phase: str = "auto",
    force_refresh: bool = False,
    notify: bool = True,
    stock_name: str | None = None,
    original_query: str | None = None,
    selection_source: str | None = None,
    report_language: str | None = None,
    skills: Sequence[str] | None = None,
    use_memory: bool | None = None,
) -> AnalysisSubmissionCommand:
    """Snapshot caller-owned values before handing them to the queue."""
    return AnalysisSubmissionCommand(
        stock_codes=tuple(stock_codes),
        report_type=report_type,
        analysis_phase=analysis_phase,
        force_refresh=force_refresh,
        notify=notify,
        stock_name=stock_name,
        original_query=original_query,
        selection_source=selection_source,
        report_language=report_language,
        skills=tuple(skills) if skills is not None else None,
        use_memory=use_memory,
    )
