# -*- coding: utf-8 -*-
"""Scheduled-task contract normalization and schema-fence recovery.

Method bodies are rebound onto ``ScheduledTaskService`` by the compatibility
facade so free-name lookups and test patches stay on
``src.services.scheduled_task_service``. Mirrors ``admission_fields`` /
``analysis_admission_audit`` / ``mutation_audit`` in this package, and shares
their clone helpers rather than adding another copy.

Admission, claim/dispatch, tick, and reconcile stay on the facade;
``_recover_supported_schema_fences`` reaches ``repository``,
``_validate_persisted_task``, and ``_run_item`` through ``self`` at call time.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Type

from .admission_fields import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols stay on ``scheduled_task_service``. Rebound methods
# resolve them from that module's global namespace.
MARKET_EXCHANGE = None  # type: ignore[assignment,misc]
NonTradingDayPolicy = None  # type: ignore[assignment,misc]
SCHEDULED_RESEARCH_TASK_SCHEMA_VERSION = None  # type: ignore[assignment,misc]
SCHEDULED_TASK_SCHEMA_VERSION = None  # type: ignore[assignment,misc]
STOCK_ANALYSIS_SCHEDULED_TASK_SCHEMA_VERSION = None  # type: ignore[assignment,misc]
SUPPORTED_SCHEDULED_TASK_SCHEMA_VERSIONS = None  # type: ignore[assignment,misc]
ScheduleKind = None  # type: ignore[assignment,misc]
ScheduledRunStatus = None  # type: ignore[assignment,misc]
ScheduledTaskContractError = Exception  # type: ignore[assignment,misc]
ScheduledTaskType = None  # type: ignore[assignment,misc]
ScheduledTaskValidationError = Exception  # type: ignore[assignment,misc]
_MAX_ATTEMPTS = None  # type: ignore[assignment,misc]
_REPORT_TYPES = None  # type: ignore[assignment,misc]
_exact_persisted_int = None  # type: ignore[assignment,misc]
get_market_for_stock = None  # type: ignore[assignment,misc]
log_safe_exception = None  # type: ignore[assignment,misc]
next_daily_run_at = None  # type: ignore[assignment,misc]
resolve_index_stock_code_for_analysis = None  # type: ignore[assignment,misc]
validate_daily_time = None  # type: ignore[assignment,misc]
validate_timezone = None  # type: ignore[assignment,misc]

logger = logging.getLogger("src.services.scheduled_task_service")

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _ContractNormalizationMethods:
    """Source descriptors rebound onto ``ScheduledTaskService`` by its facade."""

    @staticmethod
    def _schema_is_supported(schema_version: Any) -> bool:
        """Classify exact supported versions while keeping future rows opaque."""
        exact_version = _exact_persisted_int(
            schema_version,
            field_name="schema version",
            minimum=1,
        )
        if exact_version in SUPPORTED_SCHEDULED_TASK_SCHEMA_VERSIONS:
            return True
        if exact_version > SCHEDULED_TASK_SCHEMA_VERSION:
            return False
        raise ScheduledTaskContractError(
            "Persisted scheduled task schema version is invalid"
        )

    @staticmethod
    def _normalize_contract(contract: Mapping[str, Any]) -> Dict[str, Any]:
        if not isinstance(contract, Mapping):
            raise ScheduledTaskValidationError("Scheduled task must be an object")
        schema_version = contract.get(
            "schema_version",
            STOCK_ANALYSIS_SCHEDULED_TASK_SCHEMA_VERSION,
        )
        if (
            type(schema_version) is not int
            or schema_version not in SUPPORTED_SCHEDULED_TASK_SCHEMA_VERSIONS
        ):
            raise ScheduledTaskValidationError(
                f"Unsupported scheduled task schema_version: {schema_version}"
            )

        name = str(contract.get("name") or "").strip()
        if not name or len(name) > 128:
            raise ScheduledTaskValidationError(
                "Scheduled task name must contain 1 to 128 characters"
            )

        task_type = str(
            contract.get("task_type") or ScheduledTaskType.STOCK_ANALYSIS.value
        ).strip()
        supported_task_types = {member.value for member in ScheduledTaskType}
        if task_type not in supported_task_types:
            raise ScheduledTaskValidationError(
                f"Unsupported scheduled task type: {task_type}"
            )
        expected_schema_version = (
            STOCK_ANALYSIS_SCHEDULED_TASK_SCHEMA_VERSION
            if task_type == ScheduledTaskType.STOCK_ANALYSIS.value
            else SCHEDULED_RESEARCH_TASK_SCHEMA_VERSION
        )
        if schema_version != expected_schema_version:
            raise ScheduledTaskValidationError(
                f"{task_type} requires schema_version {expected_schema_version}"
            )

        schedule = contract.get("schedule")
        if not isinstance(schedule, Mapping):
            raise ScheduledTaskValidationError("Scheduled task schedule is required")
        schedule_kind = str(
            schedule.get("kind") or ScheduleKind.DAILY.value
        ).strip()
        if schedule_kind != ScheduleKind.DAILY.value:
            raise ScheduledTaskValidationError(
                f"Unsupported schedule kind: {schedule_kind}"
            )
        try:
            schedule_time = validate_daily_time(str(schedule.get("time") or ""))
            timezone_name = validate_timezone(str(schedule.get("timezone") or ""))
        except ValueError as exc:
            raise ScheduledTaskValidationError(str(exc)) from exc
        calendar_market = str(schedule.get("calendar_market") or "").strip().lower()
        if calendar_market not in MARKET_EXCHANGE:
            raise ScheduledTaskValidationError(
                f"Unsupported schedule calendar_market: {calendar_market}"
            )
        non_trading_day_policy = str(
            schedule.get("non_trading_day_policy")
            or NonTradingDayPolicy.SKIP.value
        ).strip()
        if non_trading_day_policy not in {
            policy.value for policy in NonTradingDayPolicy
        }:
            raise ScheduledTaskValidationError(
                "non_trading_day_policy must be skip or run"
            )

        payload = contract.get("payload")
        if not isinstance(payload, Mapping):
            raise ScheduledTaskValidationError("Scheduled task payload is required")
        allowed_payload_keys = {"stock_code", "notify"}
        if task_type == ScheduledTaskType.STOCK_ANALYSIS.value:
            allowed_payload_keys.add("report_type")
        unexpected_keys = set(payload) - allowed_payload_keys
        if unexpected_keys:
            raise ScheduledTaskValidationError(
                f"Unsupported {task_type} payload fields: "
                + ", ".join(sorted(str(key) for key in unexpected_keys))
            )
        stock_code = resolve_index_stock_code_for_analysis(
            str(payload.get("stock_code") or "").strip()
        )
        if not stock_code or len(stock_code) > 32:
            raise ScheduledTaskValidationError(
                "payload.stock_code must contain 1 to 32 characters"
            )
        inferred_market = get_market_for_stock(stock_code)
        if inferred_market is None:
            raise ScheduledTaskValidationError(
                "payload.stock_code must identify a supported stock market"
            )
        if inferred_market != calendar_market:
            raise ScheduledTaskValidationError(
                "payload.stock_code market must match schedule.calendar_market"
            )
        notify = payload.get("notify", True)
        if not isinstance(notify, bool):
            raise ScheduledTaskValidationError("payload.notify must be a boolean")
        normalized_payload = {
            "stock_code": stock_code,
            "notify": notify,
        }
        if task_type == ScheduledTaskType.STOCK_ANALYSIS.value:
            report_type = str(
                payload.get("report_type") or "detailed"
            ).strip().lower()
            if report_type not in _REPORT_TYPES:
                raise ScheduledTaskValidationError(
                    f"Unsupported report_type: {report_type}"
                )
            normalized_payload["report_type"] = report_type

        enabled = contract.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ScheduledTaskValidationError("enabled must be a boolean")
        max_attempts = contract.get("max_attempts", 1)
        if type(max_attempts) is not int:
            raise ScheduledTaskValidationError("max_attempts must be an integer")
        if not 1 <= max_attempts <= _MAX_ATTEMPTS:
            raise ScheduledTaskValidationError(
                f"max_attempts must be between 1 and {_MAX_ATTEMPTS}"
            )

        return {
            "schema_version": schema_version,
            "name": name,
            "task_type": task_type,
            "schedule_kind": schedule_kind,
            "schedule_time": schedule_time,
            "timezone": timezone_name,
            "calendar_market": calendar_market,
            "non_trading_day_policy": non_trading_day_policy,
            "payload": normalized_payload,
            "enabled": enabled,
            "max_attempts": max_attempts,
        }

    def _recover_supported_schema_fences(self, now: datetime) -> int:
        """Advance slots fenced only because an older binary lacked the schema."""
        recovered = 0
        try:
            rows = self.repository.list_schema_unsupported_fences(
                now=now,
                supported_schema_versions=sorted(
                    SUPPORTED_SCHEDULED_TASK_SCHEMA_VERSIONS
                ),
            )
        except Exception as exc:  # broad-exception: fallback_recorded - polling retries rollback-fence discovery on the next interval.
            log_safe_exception(
                logger,
                "Scheduled task schema-fence discovery failed; polling will retry",
                exc,
                error_code="scheduled_task_schema_fence_discovery_failed",
            )
            return 0
        for task, run in rows:
            try:
                contract = self._validate_persisted_task(task)
                self._run_item(run)
                if (
                    run.status != ScheduledRunStatus.INTERRUPTED.value
                    or run.error_code != "scheduled_task_schema_unsupported"
                    or run.task_id != task.id
                    or run.scheduled_for != task.next_run_at
                    or run.definition_schema_version != task.schema_version
                    or run.definition_generation != task.execution_generation
                ):
                    raise ScheduledTaskContractError(
                        "Persisted schema fence snapshot is inconsistent"
                    )
                next_run = next_daily_run_at(
                    schedule_time=contract["schedule_time"],
                    timezone_name=contract["timezone"],
                    after=max(now, task.next_run_at),
                )
                if self.repository.advance_schema_unsupported_fence(
                    task_id=task.id,
                    expected_schema_version=task.schema_version,
                    expected_execution_generation=task.execution_generation,
                    expected_next_run_at=task.next_run_at,
                    expected_run_id=run.id,
                    next_run_at=next_run,
                    updated_at=now,
                ):
                    recovered += 1
            except ScheduledTaskContractError as exc:
                try:
                    disabled = self.repository.disable_corrupt_task(
                        task_id=task.id,
                        expected_schema_version=task.schema_version,
                        expected_execution_generation=(
                            task.execution_generation
                        ),
                        expected_next_run_at=task.next_run_at,
                        updated_at=now,
                    )
                except Exception as quarantine_exc:  # broad-exception: fallback_recorded - polling retries failed corrupt-fence quarantine.
                    log_safe_exception(
                        logger,
                        "Scheduled task corrupt schema-fence quarantine failed",
                        quarantine_exc,
                        error_code=(
                            "scheduled_task_schema_fence_quarantine_failed"
                        ),
                        context={"task_id": task.id, "run_id": run.id},
                    )
                else:
                    if disabled:
                        recovered += 1
                log_safe_exception(
                    logger,
                    "Invalid scheduled task schema fence quarantined",
                    exc,
                    error_code="scheduled_task_schema_fence_invalid",
                    context={"task_id": task.id, "run_id": run.id},
                    level=logging.WARNING,
                )
            except Exception as exc:  # broad-exception: fallback_recorded - one corrupt rollback fence must not block unrelated schedules.
                log_safe_exception(
                    logger,
                    "Scheduled task schema-fence recovery failed closed",
                    exc,
                    error_code="scheduled_task_schema_fence_recovery_failed",
                    context={"task_id": task.id, "run_id": run.id},
                    level=logging.WARNING,
                )
        return recovered

EXPECTED_CONTRACT_NORMALIZATION_METHOD_NAMES: Tuple[str, ...] = (
    "_schema_is_supported",
    "_normalize_contract",
    "_recover_supported_schema_fences",
)


def bind_contract_normalization_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind contract-normalization descriptors without changing the service interface."""
    bound_names = []
    for name, descriptor in vars(_ContractNormalizationMethods).items():
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
