# -*- coding: utf-8 -*-
"""Scheduled-task admission field builders.

Issue #1086 extracts the four admission-status field builders from
``src.services.scheduled_task_service``. Claim, dispatch, tick, reconcile,
and module-level JSON/int helpers stay on the compatibility facade.
Consumers import ``src.services.scheduled_task_service``, not this module.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import FunctionType
from typing import Any, Callable, Dict, Optional, Tuple, Type

from src.schemas.scheduled_task import (
    SCHEDULED_TASK_RETRY_DELAY_SECONDS,
    ScheduledRunStatus,
)

# Facade-only helpers stay on ``scheduled_task_service``. Rebound methods
# resolve them from that module's global namespace.
_json_list = None  # type: ignore[assignment,misc]
_exact_persisted_int = None  # type: ignore[assignment,misc]
_MAX_DISPATCH_FAILURES = None  # type: ignore[assignment,misc]
_MAX_ATTEMPTS = None  # type: ignore[assignment,misc]

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _AdmissionFieldMethods:
    """Source descriptors rebound onto ``ScheduledTaskService`` by its facade."""

    @staticmethod
    def _conflict_wait_fields(now: datetime) -> Dict[str, Any]:
        return {
            "status": ScheduledRunStatus.RETRY_WAIT.value,
            "dispatch_token": None,
            "error_code": "scheduled_task_execution_conflict",
            "next_attempt_at": now
            + timedelta(seconds=SCHEDULED_TASK_RETRY_DELAY_SECONDS),
            "finished_at": None,
            "updated_at": now,
        }

    @staticmethod
    def _interrupted_admission_fields(
        now: datetime,
        *,
        error_code: str,
    ) -> Dict[str, Any]:
        return {
            "status": ScheduledRunStatus.INTERRUPTED.value,
            "dispatch_token": None,
            "error_code": error_code,
            "next_attempt_at": None,
            "finished_at": now,
            "updated_at": now,
        }

    @staticmethod
    def _dispatch_failure_fields(
        run,
        now: datetime,
        *,
        error_code: str,
    ) -> Dict[str, Any]:
        failure_count = _exact_persisted_int(
            run.dispatch_failure_count,
            field_name="run dispatch failure count",
            minimum=0,
            maximum=_MAX_DISPATCH_FAILURES,
        ) + 1
        terminal = failure_count >= _MAX_DISPATCH_FAILURES
        return {
            "status": (
                ScheduledRunStatus.FAILED.value
                if terminal
                else ScheduledRunStatus.RETRY_WAIT.value
            ),
            "dispatch_token": None,
            "dispatch_failure_count": failure_count,
            "error_code": error_code,
            "next_attempt_at": (
                None
                if terminal
                else now + timedelta(seconds=SCHEDULED_TASK_RETRY_DELAY_SECONDS)
            ),
            "finished_at": now if terminal else None,
            "updated_at": now,
        }

    @staticmethod
    def _running_admission_fields(
        run,
        now: datetime,
        *,
        execution_id: str,
        owned: bool,
    ) -> Dict[str, Any]:
        execution_history = _json_list(
            run.execution_task_ids_json,
            field_name="execution_task_ids",
        )
        owned_history = _json_list(
            run.owned_execution_task_ids_json,
            field_name="owned_execution_task_ids",
        )
        return {
            "status": ScheduledRunStatus.RUNNING.value,
            "dispatch_token": None,
            "attempt_count": _exact_persisted_int(
                run.attempt_count,
                field_name="run attempt count",
                minimum=0,
                maximum=_MAX_ATTEMPTS,
            ) + 1,
            "execution_task_ids_json": json.dumps(
                execution_history + [execution_id]
            ),
            "owned_execution_task_ids_json": json.dumps(
                owned_history + ([execution_id] if owned else [])
            ),
            "error_code": None,
            "next_attempt_at": None,
            "started_at": run.started_at or now,
            "finished_at": None,
            "updated_at": now,
        }


def _clone_facade_function(
    function: FunctionType,
    global_namespace: Dict[str, Any],
    *,
    qualname: str,
) -> FunctionType:
    """Clone one method so global lookups retain facade seams."""
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


EXPECTED_ADMISSION_FIELD_METHOD_NAMES = (
    "_conflict_wait_fields",
    "_interrupted_admission_fields",
    "_dispatch_failure_fields",
    "_running_admission_fields",
)


def bind_admission_fields_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind admission-field descriptors without changing the service interface."""
    bound_names = []
    for name, descriptor in vars(_AdmissionFieldMethods).items():
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
    """Register the loaded facade assembly callback for owner reloads."""
    global _FACADE_RELOAD_HOOK
    _FACADE_RELOAD_HOOK = hook


def _rebind_loaded_facade() -> None:
    """Refresh a registered facade after this owner module is reloaded."""
    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
