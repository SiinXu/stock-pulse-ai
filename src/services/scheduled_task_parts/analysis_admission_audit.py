# -*- coding: utf-8 -*-
"""Analysis.submit audit around scheduled-task queue admission.

DAG-1 (#1062) records attempt before the fenced queue write and completion
after the fence commits, so SQLite is not double-locked. Consumers import
``src.services.scheduled_task_service``, not this module.
"""

from __future__ import annotations

from types import FunctionType
from typing import Any, Callable, Dict, Optional, Tuple, Type

# Facade-only helpers stay on ``scheduled_task_service``. Rebound methods
# resolve them from that module's global namespace.
_json_list = None  # type: ignore[assignment,misc]
ScheduledTaskContractError = None  # type: ignore[assignment,misc]
ScheduledTaskType = None  # type: ignore[assignment,misc]
logger = None  # type: ignore[assignment,misc]
log_safe_exception = None  # type: ignore[assignment,misc]
ScheduledRunStatus = None  # type: ignore[assignment,misc]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _AnalysisAdmissionAuditMethods:
    """Source descriptors rebound onto ``ScheduledTaskService`` by its facade."""

    def _security_audit_recorder(self):
        from src.services.security_audit_service import (
            get_security_audit_service,
            require_security_audit_recorder,
        )

        factory = self._security_audit_factory
        if factory is None:
            return require_security_audit_recorder(get_security_audit_service())
        return require_security_audit_recorder(factory())

    @staticmethod
    def _looks_like_owned_retry(run) -> bool:
        try:
            execution_history = _json_list(
                run.execution_task_ids_json,
                field_name="execution_task_ids",
            )
            owned_history = set(
                _json_list(
                    run.owned_execution_task_ids_json,
                    field_name="owned_execution_task_ids",
                )
            )
        except ScheduledTaskContractError:
            return False
        return bool(execution_history and execution_history[-1] in owned_history)

    def _audit_stock_code_for_run(self, run) -> str:
        return self._audit_submission_context_for_run(run)[0]

    def _audit_submission_context_for_run(self, run) -> tuple[str, str]:
        """Best-effort stock code and admitted report_type for analysis.submit."""
        task = self.repository.get_task(run.task_id)
        if task is None:
            return "unresolved", "detailed"
        try:
            payload = self._decode_payload(getattr(task, "payload_json", "") or "")
        except ScheduledTaskContractError:
            return "unresolved", "detailed"
        code = str(payload.get("stock_code") or "").strip() or "unresolved"
        task_type = str(getattr(task, "task_type", "") or "")
        if task_type == ScheduledTaskType.RESEARCH_BRIEF.value:
            return code, "brief"
        report_type = str(payload.get("report_type") or "detailed")
        return code, report_type or "detailed"

    def _begin_analysis_admission_audit(self, run) -> dict[str, Any]:
        """Persist analysis.submit attempt before the fenced queue write."""
        state: dict[str, Any] = {
            "attempted": False,
            "block_submit": False,
            "correlation_id": None,
            "stock_code": None,
            "queue_called": False,
            "accepted": False,
            "duplicate": False,
            "queue_failed": False,
            "metadata": None,
        }
        if self._looks_like_owned_retry(run):
            return state
        from src.services.analysis_submission_service import AnalysisSubmissionService
        from src.services.security_audit_service import (
            SecurityAuditService,
            SecurityAuditUnavailable,
        )

        stock_code, report_type = self._audit_submission_context_for_run(run)
        correlation_id = SecurityAuditService.new_correlation_id()
        metadata = AnalysisSubmissionService.bounded_audit_metadata(
            report_type=report_type,
            analysis_phase="auto",
            batch_size=1,
            query_source="scheduled_task",
        )
        state["correlation_id"] = correlation_id
        state["stock_code"] = stock_code
        state["metadata"] = metadata
        try:
            AnalysisSubmissionService.record_audit(
                self._security_audit_recorder(),
                phase="attempt",
                correlation_id=correlation_id,
                stock_code=stock_code,
                metadata=metadata,
                actor_type="scheduler",
                actor_id="scheduled_task",
            )
        except SecurityAuditUnavailable as exc:
            log_safe_exception(
                logger,
                "Scheduled task analysis admission audit unavailable",
                exc,
                error_code="security_audit_unavailable",
                context={"run_id": run.id, "task_id": run.task_id},
            )
            state["block_submit"] = True
            return state
        state["attempted"] = True
        return state

    def _complete_analysis_admission_audit(
        self,
        state: dict[str, Any],
        *,
        fence_applied: bool,
    ) -> None:
        if not state.get("attempted"):
            return
        from src.services.analysis_submission_service import AnalysisSubmissionService
        from src.services.security_audit_service import SecurityAuditUnavailable

        if state.get("accepted"):
            outcome, reason_code = "accepted", "task_accepted"
        elif state.get("duplicate"):
            outcome, reason_code = "rejected", "duplicate_task"
        elif state.get("queue_failed") or state.get("block_submit"):
            outcome, reason_code = "failure", "task_submission_failed"
        else:
            outcome, reason_code = "failure", "submission_not_resolved"
        try:
            AnalysisSubmissionService.record_audit(
                self._security_audit_recorder(),
                phase="completion",
                correlation_id=str(state["correlation_id"]),
                stock_code=str(state["stock_code"]),
                outcome=outcome,
                reason_code=reason_code,
                metadata=state.get("metadata") or {},
                actor_type="scheduler",
                actor_id="scheduled_task",
            )
        except SecurityAuditUnavailable as exc:
            log_safe_exception(
                logger,
                "Scheduled task analysis admission completion audit unavailable",
                exc,
                error_code="security_audit_unavailable",
                context={"correlation_id": state.get("correlation_id")},
            )

    def _submit_analysis_batch_with_audit(
        self,
        queue,
        submission: dict[str, Any],
        current_run,
        now,
        admission_audit: dict[str, Any],
    ) -> tuple[Any, Any, Optional[Dict[str, Any]]]:
        if admission_audit["block_submit"]:
            return None, None, self._dispatch_failure_fields(
                current_run,
                now,
                error_code="security_audit_unavailable",
            )
        try:
            accepted, duplicates = queue.submit_tasks_batch(**submission)
        except Exception as exc:  # broad-exception: fallback_recorded - canonical batch submission rolls back rejected queue state.
            log_safe_exception(
                logger,
                "Scheduled task dispatch admission failed",
                exc,
                error_code="scheduled_task_dispatch_failed",
                context={
                    "run_id": current_run.id,
                    "task_id": current_run.task_id,
                },
            )
            admission_audit["queue_failed"] = True
            return None, None, self._dispatch_failure_fields(
                current_run,
                now,
                error_code="scheduled_task_dispatch_failed",
            )
        admission_audit["queue_called"] = True
        metadata = admission_audit.get("metadata")
        if isinstance(metadata, dict):
            admission_audit["metadata"] = {
                **metadata,
                "report_type": str(submission.get("report_type") or "detailed"),
            }
        return accepted, duplicates, None

    def _run_admission_fence_with_audit(
        self,
        run,
        *,
        dispatch_token: str,
        now,
        update_factory,
        admission_audit: dict[str, Any],
    ):
        try:
            result = self.repository.update_run_under_definition_fence(
                run_id=run.id,
                expected_schema_version=run.definition_schema_version,
                expected_dispatch_token=dispatch_token,
                allowed_run_statuses=[ScheduledRunStatus.DISPATCHING.value],
                now=now,
                update_factory=update_factory,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - a durable dispatch reservation prevents blind replay after an uncertain commit.
            log_safe_exception(
                logger,
                "Scheduled task admission transaction failed closed",
                exc,
                error_code="scheduled_task_admission_state_uncertain",
                context={"run_id": run.id, "task_id": run.task_id},
            )
            self._complete_analysis_admission_audit(
                admission_audit,
                fence_applied=False,
            )
            return None
        self._complete_analysis_admission_audit(
            admission_audit,
            fence_applied=result.outcome == "applied",
        )
        return result


def _clone_facade_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
    *,
    qualname: str,
) -> FunctionType:
    cloned = FunctionType(
        function.__code__,
        global_namespace,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    cloned.__annotations__ = dict(function.__annotations__)
    cloned.__dict__.update(function.__dict__)
    cloned.__doc__ = function.__doc__
    cloned.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    cloned.__module__ = str(global_namespace["__name__"])
    cloned.__qualname__ = qualname
    if hasattr(function, "__type_params__"):
        cloned.__type_params__ = function.__type_params__
    return cloned


def _descriptor_function(descriptor: Any) -> Optional[FunctionType]:
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    if isinstance(descriptor, FunctionType):
        return descriptor
    return None


def _clone_facade_descriptor(
    descriptor: Any,
    global_namespace: Dict[str, Any],
    *,
    owner_qualname: str,
) -> Any:
    def clone(function: Optional[FunctionType]) -> Optional[FunctionType]:
        if function is None:
            return None
        return _clone_facade_function(
            function,
            global_namespace,
            qualname=f"{owner_qualname}.{function.__name__}",
        )

    if isinstance(descriptor, staticmethod):
        return staticmethod(clone(descriptor.__func__))
    if isinstance(descriptor, classmethod):
        return classmethod(clone(descriptor.__func__))
    if isinstance(descriptor, property):
        return property(
            clone(descriptor.fget),
            clone(descriptor.fset),
            clone(descriptor.fdel),
            descriptor.__doc__,
        )
    return clone(descriptor)


EXPECTED_ANALYSIS_ADMISSION_AUDIT_METHOD_NAMES = (
    "_security_audit_recorder",
    "_looks_like_owned_retry",
    "_audit_stock_code_for_run",
    "_audit_submission_context_for_run",
    "_begin_analysis_admission_audit",
    "_complete_analysis_admission_audit",
    "_submit_analysis_batch_with_audit",
    "_run_admission_fence_with_audit",
)


def bind_analysis_admission_audit_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    bound_names = []
    for name, descriptor in vars(_AnalysisAdmissionAuditMethods).items():
        if name.startswith("__") or _descriptor_function(descriptor) is None:
            continue
        setattr(
            target_class,
            name,
            _clone_facade_descriptor(
                descriptor,
                global_namespace,
                owner_qualname=target_class.__qualname__,
            ),
        )
        bound_names.append(name)
    return tuple(bound_names)


def _install_facade_reload_hook(hook: Callable[[], None]) -> None:
    global _FACADE_RELOAD_HOOK
    _FACADE_RELOAD_HOOK = hook


def _rebind_loaded_facade() -> None:
    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
