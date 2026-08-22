# -*- coding: utf-8 -*-
"""Scheduled-task create/enable/disable security-audit helpers.

DAG-2 (#1062) records ``scheduled_task.write`` attempt before the definition
write and completion afterward. Consumers import
``src.services.scheduled_task_service``, not this module.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from types import FunctionType
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Type

# Facade-only helpers stay on ``scheduled_task_service``. Rebound methods
# resolve them from that module's global namespace.
logger = None  # type: ignore[assignment,misc]
log_safe_exception = None  # type: ignore[assignment,misc]
next_daily_run_at = None  # type: ignore[assignment,misc]
MAX_SCHEDULED_TASK_EXECUTION_GENERATION = None  # type: ignore[assignment,misc]
ScheduledTaskNotFoundError = None  # type: ignore[assignment,misc]
ScheduledTaskContractError = None  # type: ignore[assignment,misc]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)

SCHEDULED_TASK_WRITE_EVENT_TYPE = "scheduled_task.write"
SCHEDULED_TASK_MUTATION_TARGET_TYPE = "scheduled_task"
DEFAULT_SCHEDULED_TASK_MUTATION_ACTOR_TYPE = "administrator"
DEFAULT_SCHEDULED_TASK_MUTATION_ACTOR_ID = "local_operator"
_MUTATION_ACTION_BY_OPERATION = {
    "create": "scheduled_task.create",
    "enable": "scheduled_task.enable",
    "disable": "scheduled_task.disable",
}
_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$")
_STABLE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_MAX_MUTATION_METADATA_KEYS = 16
_MAX_MUTATION_METADATA_STRING = 256


class ScheduledTaskMutationAuditCompletionUnavailable(RuntimeError):
    """Raised when the durable mutation succeeded but audit completion failed."""

    def __init__(self, item: Dict[str, Any]) -> None:
        super().__init__("security_audit_unavailable")
        self.item = item


def _bounded_mutation_identity(value: Any, *, fallback: str) -> str:
    candidate = value.strip() if type(value) is str else ""
    if candidate and _IDENTITY_PATTERN.fullmatch(candidate) is not None:
        return candidate[:128]
    return fallback


def _bounded_mutation_name(value: Any, *, fallback: str) -> str:
    candidate = value.strip().replace(" ", "_").lower() if type(value) is str else ""
    if candidate and _STABLE_NAME_PATTERN.fullmatch(candidate) is not None:
        return candidate[:64]
    sanitized = re.sub(r"[^a-z0-9_.-]", ".", candidate.lower())
    sanitized = sanitized.strip(".-")
    if sanitized and _STABLE_NAME_PATTERN.fullmatch(sanitized) is not None:
        return sanitized[:64]
    return fallback


def _bounded_mutation_metadata(metadata: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not metadata:
        return {}
    out: Dict[str, Any] = {}
    for key, raw in list(metadata.items())[:_MAX_MUTATION_METADATA_KEYS]:
        if type(key) is not str or not key or len(key) > 64:
            continue
        if raw is None or type(raw) in {bool, int}:
            out[key] = raw
            continue
        if type(raw) is str:
            out[key] = raw[:_MAX_MUTATION_METADATA_STRING]
            continue
    from src.utils.sanitize import redact_sensitive_data

    redacted = redact_sensitive_data(out)
    return redacted if isinstance(redacted, dict) else {}


def _mutation_metadata_from_contract(contract: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(contract, Mapping):
        return {}
    metadata: Dict[str, Any] = {}
    task_type = contract.get("task_type")
    if type(task_type) is str and task_type:
        metadata["task_type"] = task_type[:64]
    schema_version = contract.get("schema_version")
    if type(schema_version) is int:
        metadata["schema_version"] = schema_version
    enabled = contract.get("enabled")
    if type(enabled) is bool:
        metadata["enabled"] = enabled
    schedule = contract.get("schedule")
    if isinstance(schedule, Mapping):
        kind = schedule.get("kind")
        if type(kind) is str and kind:
            metadata["schedule_kind"] = kind[:64]
        market = schedule.get("calendar_market")
        if type(market) is str and market:
            metadata["calendar_market"] = market[:64]
    return metadata


def _mutation_error_audit_fields(exc: BaseException) -> tuple[str, str]:
    code = getattr(exc, "error_code", None)
    if code == "scheduled_task_not_found":
        return "rejected", "scheduled_task_not_found"
    if code == "scheduled_task_validation_error":
        return "rejected", "scheduled_task_validation_error"
    if code == "scheduled_task_schema_unsupported":
        return "rejected", "scheduled_task_schema_unsupported"
    if code == "scheduled_task_contract_error":
        return "failure", "scheduled_task_contract_error"
    return "failure", "scheduled_task_mutation_failed"


class _MutationAuditMethods:
    """Source descriptors rebound onto ``ScheduledTaskService`` by its facade."""

    def _resolve_mutation_audit_recorder(self, recorder: Any = None):
        if recorder is not None:
            from src.services.security_audit_service import (
                require_security_audit_recorder,
            )

            return require_security_audit_recorder(recorder)
        return self._security_audit_recorder()

    def _record_scheduled_task_mutation_audit(
        self,
        *,
        phase: str,
        operation: str,
        target_id: str,
        correlation_id: str,
        actor_type: str,
        actor_id: str,
        metadata: Mapping[str, Any] | None = None,
        outcome: str = "pending",
        reason_code: str = "attempt_started",
        recorder: Any = None,
    ) -> None:
        from src.services.security_audit_service import SecurityAuditUnavailable

        action = _MUTATION_ACTION_BY_OPERATION[operation]
        resolved_actor_type = _bounded_mutation_name(
            actor_type,
            fallback=DEFAULT_SCHEDULED_TASK_MUTATION_ACTOR_TYPE,
        )
        resolved_actor_id = _bounded_mutation_identity(
            actor_id,
            fallback=DEFAULT_SCHEDULED_TASK_MUTATION_ACTOR_ID,
        )
        resolved_target_id = _bounded_mutation_identity(
            target_id,
            fallback="unknown-task",
        )
        payload = _bounded_mutation_metadata(metadata)
        try:
            service = self._resolve_mutation_audit_recorder(recorder)
            common = dict(
                event_type=SCHEDULED_TASK_WRITE_EVENT_TYPE,
                actor_type=resolved_actor_type,
                actor_id=resolved_actor_id,
                execution_id=correlation_id,
                action=action,
                target_type=SCHEDULED_TASK_MUTATION_TARGET_TYPE,
                target_id=resolved_target_id,
                correlation_id=correlation_id,
                metadata=payload,
            )
            if phase == "attempt":
                service.record_attempt(**common)
                return
            service.record_completion(
                **common,
                outcome=outcome,
                reason_code=_bounded_mutation_name(
                    reason_code,
                    fallback="scheduled_task_mutation_failed",
                ),
            )
        except SecurityAuditUnavailable:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - mutation audit stays fail-closed.
            log_safe_exception(
                logger,
                "Scheduled task mutation audit unavailable",
                exc,
                error_code="security_audit_unavailable",
                context={"operation": operation, "phase": phase},
            )
            raise SecurityAuditUnavailable() from None

    def _complete_scheduled_task_mutation_success(
        self,
        *,
        operation: str,
        target_id: str,
        correlation_id: str,
        actor_type: str,
        actor_id: str,
        metadata: Mapping[str, Any] | None,
        reason_code: str,
        recorder: Any,
        item: Dict[str, Any],
    ) -> None:
        """Persist success completion; surface write-done/audit-failed distinctly."""
        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            self._record_scheduled_task_mutation_audit(
                phase="completion",
                operation=operation,
                target_id=target_id,
                correlation_id=correlation_id,
                actor_type=actor_type,
                actor_id=actor_id,
                metadata=metadata,
                outcome="success",
                reason_code=reason_code,
                recorder=recorder,
            )
        except SecurityAuditUnavailable as exc:
            log_safe_exception(
                logger,
                "Scheduled task mutation audit completion unavailable after mutation",
                exc,
                error_code="scheduled_task_mutation_audit_completion_unavailable",
                context={"operation": operation, "target_id": target_id},
            )
            raise ScheduledTaskMutationAuditCompletionUnavailable(item) from None

    def _complete_scheduled_task_mutation_failure(
        self,
        *,
        operation: str,
        target_id: str,
        correlation_id: str,
        actor_type: str,
        actor_id: str,
        metadata: Mapping[str, Any] | None,
        outcome: str,
        reason_code: str,
        recorder: Any,
    ) -> None:
        """Best-effort reject/failure completion; never mask the domain error."""
        from src.services.security_audit_service import SecurityAuditUnavailable

        try:
            self._record_scheduled_task_mutation_audit(
                phase="completion",
                operation=operation,
                target_id=target_id,
                correlation_id=correlation_id,
                actor_type=actor_type,
                actor_id=actor_id,
                metadata=metadata,
                outcome=outcome,
                reason_code=reason_code,
                recorder=recorder,
            )
        except SecurityAuditUnavailable as exc:
            log_safe_exception(
                logger,
                "Scheduled task mutation failure audit completion unavailable",
                exc,
                error_code="scheduled_task_mutation_failure_audit_unavailable",
                context={"operation": operation, "target_id": target_id},
            )

    def create_task(
        self,
        contract: Mapping[str, Any],
        *,
        now: Optional[datetime] = None,
        actor_type: str = DEFAULT_SCHEDULED_TASK_MUTATION_ACTOR_TYPE,
        actor_id: str = DEFAULT_SCHEDULED_TASK_MUTATION_ACTOR_ID,
        security_audit: Any = None,
    ) -> Dict[str, Any]:
        """Validate and persist one supported scheduled definition."""
        from src.services.security_audit_service import (
            SecurityAuditService,
            SecurityAuditUnavailable,
        )

        task_id = uuid.uuid4().hex
        correlation_id = SecurityAuditService.new_correlation_id()
        metadata = _mutation_metadata_from_contract(contract)
        self._record_scheduled_task_mutation_audit(
            phase="attempt",
            operation="create",
            target_id=task_id,
            correlation_id=correlation_id,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata=metadata,
            recorder=security_audit,
        )
        try:
            normalized = self._normalize_contract(contract)
            metadata = {
                **metadata,
                "task_type": normalized["task_type"],
                "schema_version": normalized["schema_version"],
                "enabled": normalized["enabled"],
                "schedule_kind": normalized["schedule_kind"],
                "calendar_market": normalized["calendar_market"],
            }
            now_value = self._now(now or self._clock())
            next_run = None
            if normalized["enabled"]:
                next_run = next_daily_run_at(
                    schedule_time=normalized["schedule_time"],
                    timezone_name=normalized["timezone"],
                    after=now_value,
                )
            row = self.repository.create_task(
                {
                    "id": task_id,
                    "schema_version": normalized["schema_version"],
                    "execution_generation": 1,
                    "name": normalized["name"],
                    "task_type": normalized["task_type"],
                    "schedule_kind": normalized["schedule_kind"],
                    "schedule_time": normalized["schedule_time"],
                    "timezone": normalized["timezone"],
                    "calendar_market": normalized["calendar_market"],
                    "non_trading_day_policy": normalized["non_trading_day_policy"],
                    "payload_json": json.dumps(
                        normalized["payload"],
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    "enabled": normalized["enabled"],
                    "max_attempts": normalized["max_attempts"],
                    "next_run_at": next_run,
                    "created_at": now_value,
                    "updated_at": now_value,
                }
            )
        except SecurityAuditUnavailable:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - complete the attempt before re-raising the mutation error.
            outcome, reason_code = _mutation_error_audit_fields(exc)
            log_safe_exception(
                logger,
                "Scheduled task create mutation failed",
                exc,
                error_code=reason_code,
                context={"operation": "create", "target_id": task_id},
            )
            self._complete_scheduled_task_mutation_failure(
                operation="create",
                target_id=task_id,
                correlation_id=correlation_id,
                actor_type=actor_type,
                actor_id=actor_id,
                metadata=metadata,
                outcome=outcome,
                reason_code=reason_code,
                recorder=security_audit,
            )
            raise
        item = self._task_item(row)
        self._complete_scheduled_task_mutation_success(
            operation="create",
            target_id=task_id,
            correlation_id=correlation_id,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata=metadata,
            reason_code="scheduled_task_created",
            recorder=security_audit,
            item=item,
        )
        return item

    def set_enabled(
        self,
        task_id: str,
        enabled: bool,
        *,
        now: Optional[datetime] = None,
        actor_type: str = DEFAULT_SCHEDULED_TASK_MUTATION_ACTOR_TYPE,
        actor_id: str = DEFAULT_SCHEDULED_TASK_MUTATION_ACTOR_ID,
        security_audit: Any = None,
    ) -> Dict[str, Any]:
        """Enable or disable one supported definition."""
        from src.services.security_audit_service import (
            SecurityAuditService,
            SecurityAuditUnavailable,
        )

        operation = "enable" if enabled else "disable"
        correlation_id = SecurityAuditService.new_correlation_id()
        metadata: Dict[str, Any] = {"requested_enabled": bool(enabled)}
        self._record_scheduled_task_mutation_audit(
            phase="attempt",
            operation=operation,
            target_id=task_id,
            correlation_id=correlation_id,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata=metadata,
            recorder=security_audit,
        )
        try:
            existing = self.repository.get_task(task_id)
            if existing is None:
                raise ScheduledTaskNotFoundError(task_id)
            contract = self._validate_persisted_task(existing)
            metadata = {
                **metadata,
                "task_type": contract["task_type"],
                "schema_version": contract["schema_version"],
                "enabled": bool(enabled),
                "schedule_kind": contract["schedule_kind"],
                "calendar_market": contract["calendar_market"],
                "idempotent": bool(existing.enabled) is bool(enabled),
            }
            if bool(existing.enabled) is bool(enabled):
                item = self._task_item(existing)
                success_reason_code = "already_enabled" if enabled else "already_disabled"
            elif (
                existing.execution_generation
                >= MAX_SCHEDULED_TASK_EXECUTION_GENERATION
                and enabled
            ):
                raise ScheduledTaskContractError(
                    "Scheduled task execution generation cannot advance"
                )
            else:
                now_value = self._now(now or self._clock())
                next_run = None
                if enabled:
                    next_run = next_daily_run_at(
                        schedule_time=contract["schedule_time"],
                        timezone_name=contract["timezone"],
                        after=now_value,
                    )
                row = self.repository.set_enabled(
                    task_id,
                    expected_schema_version=existing.schema_version,
                    expected_execution_generation=existing.execution_generation,
                    enabled=bool(enabled),
                    next_run_at=next_run,
                    updated_at=now_value,
                )
                if row is None:
                    current = self.repository.get_task(task_id)
                    if current is None:
                        raise ScheduledTaskNotFoundError(task_id)
                    self._validate_persisted_task(current)
                    raise ScheduledTaskContractError(
                        "Scheduled task definition changed during enablement"
                    )
                item = self._task_item(row)
                success_reason_code = (
                    "scheduled_task_enabled" if enabled else "scheduled_task_disabled"
                )
        except SecurityAuditUnavailable:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - complete the attempt before re-raising the mutation error.
            outcome, reason_code = _mutation_error_audit_fields(exc)
            log_safe_exception(
                logger,
                "Scheduled task enablement mutation failed",
                exc,
                error_code=reason_code,
                context={"operation": operation, "target_id": task_id},
            )
            self._complete_scheduled_task_mutation_failure(
                operation=operation,
                target_id=task_id,
                correlation_id=correlation_id,
                actor_type=actor_type,
                actor_id=actor_id,
                metadata=metadata,
                outcome=outcome,
                reason_code=reason_code,
                recorder=security_audit,
            )
            raise
        self._complete_scheduled_task_mutation_success(
            operation=operation,
            target_id=task_id,
            correlation_id=correlation_id,
            actor_type=actor_type,
            actor_id=actor_id,
            metadata=metadata,
            reason_code=success_reason_code,
            recorder=security_audit,
            item=item,
        )
        return item


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


EXPECTED_MUTATION_AUDIT_METHOD_NAMES = (
    "_resolve_mutation_audit_recorder",
    "_record_scheduled_task_mutation_audit",
    "_complete_scheduled_task_mutation_success",
    "_complete_scheduled_task_mutation_failure",
    "create_task",
    "set_enabled",
)


def bind_mutation_audit_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    bound_names = []
    for name, descriptor in vars(_MutationAuditMethods).items():
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
