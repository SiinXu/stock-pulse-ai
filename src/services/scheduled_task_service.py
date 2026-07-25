"""Deterministic persisted scheduling built on the canonical analysis queue."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Mapping, Optional

from src.core.trading_calendar import (
    MARKET_EXCHANGE,
    MARKET_TIMEZONE,
    MarketSessionStatus,
    classify_market_session,
    get_market_for_stock,
)
from src.repositories.scheduled_task_repo import ScheduledTaskRepository
from src.schemas.scheduled_task import (
    NonTradingDayPolicy,
    SCHEDULED_NOTIFICATION_STATUSES,
    SCHEDULED_TASK_RETRY_DELAY_SECONDS,
    SCHEDULED_TASK_SCHEMA_VERSION,
    ScheduleKind,
    ScheduledRunStatus,
    ScheduledTaskType,
    as_utc_aware,
    as_utc_naive,
    next_daily_run_at,
    scheduled_local_date,
    validate_daily_time,
    validate_timezone,
)
from src.services.run_diagnostics import sanitize_diagnostic_text
from src.services.task_queue import DuplicateTaskError
from src.services.stock_code_utils import resolve_index_stock_code_for_analysis
from src.task_execution import TaskNotFoundError, TaskRetryInProgressError, TaskStatus
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

_REPORT_TYPES = frozenset({"brief", "simple", "detailed", "full"})
_MAX_ATTEMPTS = 3
_MAX_DISPATCH_FAILURES = 3
_MAX_NOTIFICATION_CHANNELS = 16


class ScheduledTaskError(Exception):
    """Base error carrying a stable public code."""

    error_code = "scheduled_task_error"


class ScheduledTaskValidationError(ScheduledTaskError):
    """Raised when a requested version-one definition is invalid."""

    error_code = "scheduled_task_validation_error"


class ScheduledTaskNotFoundError(ScheduledTaskError):
    """Raised when a requested definition does not exist."""

    error_code = "scheduled_task_not_found"

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(f"Scheduled task does not exist: {task_id}")


class ScheduledTaskContractError(ScheduledTaskError):
    """Raised when persisted version-one data violates its contract."""

    error_code = "scheduled_task_contract_error"


class ScheduledTaskUnsupportedSchemaError(ScheduledTaskError):
    """Raised when a mutation requires a newer definition schema."""

    error_code = "scheduled_task_schema_unsupported"

    def __init__(self, task_id: str, schema_version: Any) -> None:
        self.task_id = task_id
        self.schema_version = schema_version
        super().__init__(
            f"Scheduled task {task_id} uses unsupported schema_version: "
            f"{schema_version}"
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_list(raw_value: str, *, field_name: str) -> list[str]:
    try:
        value = json.loads(raw_value or "[]")
    except (TypeError, ValueError) as exc:
        raise ScheduledTaskContractError(
            f"Persisted {field_name} is not valid JSON"
        ) from exc
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ScheduledTaskContractError(
            f"Persisted {field_name} must be a list of non-empty strings"
        )
    return list(value)


def _sanitized_channels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    channels = []
    seen = set()
    for item in value:
        if type(item) is not str:
            continue
        channel = sanitize_diagnostic_text(item, max_length=64)
        channel = str(channel or "").strip()
        if not channel or channel in seen:
            continue
        seen.add(channel)
        channels.append(channel)
        if len(channels) >= _MAX_NOTIFICATION_CHANNELS:
            break
    return channels


class ScheduledTaskService:
    """Create, claim, dispatch, and reconcile version-one scheduled tasks."""

    def __init__(
        self,
        *,
        repository: Optional[ScheduledTaskRepository] = None,
        repository_factory: Callable[[], ScheduledTaskRepository] = ScheduledTaskRepository,
        task_queue: Any = None,
        clock=_utc_now,
        market_session_provider=classify_market_session,
    ) -> None:
        self._repository = repository
        self._repository_factory = repository_factory
        self._repository_lock = threading.Lock()
        self._task_queue = task_queue
        self._clock = clock
        self._market_session_provider = market_session_provider
        self._tick_lock = threading.Lock()

    @property
    def repository(self) -> ScheduledTaskRepository:
        """Initialize persistence only when a request or background tick needs it."""
        repository = self._repository
        if repository is None:
            with self._repository_lock:
                repository = self._repository
                if repository is None:
                    repository = self._repository_factory()
                    self._repository = repository
        return repository

    def _queue(self):
        if self._task_queue is not None:
            return self._task_queue
        from src.application_services import get_application_services

        return get_application_services().task_queue

    @staticmethod
    def _now(value: Optional[datetime] = None) -> datetime:
        return as_utc_naive(value or _utc_now())

    @staticmethod
    def _aware_or_none(value: Optional[datetime]) -> Optional[datetime]:
        return as_utc_aware(value) if value is not None else None

    @staticmethod
    def _decode_payload(raw_value: str) -> Dict[str, Any]:
        try:
            payload = json.loads(raw_value)
        except (TypeError, ValueError) as exc:
            raise ScheduledTaskContractError(
                "Persisted scheduled task payload is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ScheduledTaskContractError(
                "Persisted scheduled task payload must be an object"
            )
        return payload

    @classmethod
    def _validate_persisted_task(cls, row) -> Dict[str, Any]:
        if row.schema_version != SCHEDULED_TASK_SCHEMA_VERSION:
            raise ScheduledTaskUnsupportedSchemaError(
                str(row.id or ""),
                row.schema_version,
            )
        payload = cls._decode_payload(row.payload_json)
        try:
            normalized = cls._normalize_contract({
                "schema_version": row.schema_version,
                "name": row.name,
                "task_type": row.task_type,
                "schedule": {
                    "kind": row.schedule_kind,
                    "time": row.schedule_time,
                    "timezone": row.timezone,
                    "calendar_market": row.calendar_market,
                    "non_trading_day_policy": row.non_trading_day_policy,
                },
                "payload": payload,
                "enabled": bool(row.enabled),
                "max_attempts": row.max_attempts,
            })
        except ScheduledTaskValidationError as exc:
            raise ScheduledTaskContractError(
                "Persisted scheduled task contract is unsupported or corrupt"
            ) from exc

        expected_values = {
            "schema_version": row.schema_version,
            "name": row.name,
            "task_type": row.task_type,
            "schedule_kind": row.schedule_kind,
            "schedule_time": row.schedule_time,
            "timezone": row.timezone,
            "calendar_market": row.calendar_market,
            "non_trading_day_policy": row.non_trading_day_policy,
            "payload": payload,
            "enabled": bool(row.enabled),
            "max_attempts": row.max_attempts,
        }
        if any(normalized[key] != value for key, value in expected_values.items()):
            raise ScheduledTaskContractError(
                "Persisted scheduled task contract is not canonical"
            )
        task_id = str(row.id or "")
        if not task_id or len(task_id) > 32:
            raise ScheduledTaskContractError("Persisted scheduled task id is invalid")
        if row.created_at is None or row.updated_at is None:
            raise ScheduledTaskContractError(
                "Persisted scheduled task timestamps are incomplete"
            )
        if bool(row.enabled) != (row.next_run_at is not None):
            raise ScheduledTaskContractError(
                "Persisted scheduled task enablement is inconsistent"
            )
        try:
            execution_generation = int(row.execution_generation)
        except (TypeError, ValueError) as exc:
            raise ScheduledTaskContractError(
                "Persisted scheduled task execution generation is invalid"
            ) from exc
        if execution_generation < 1:
            raise ScheduledTaskContractError(
                "Persisted scheduled task execution generation is invalid"
            )
        return normalized

    @classmethod
    def _task_item(cls, row) -> Dict[str, Any]:
        if row.schema_version != SCHEDULED_TASK_SCHEMA_VERSION:
            return {
                "compatibility": "unsupported_schema",
                "id": str(row.id or ""),
                "schema_version": row.schema_version,
                "name": str(row.name or ""),
                "enabled": bool(row.enabled),
                "next_run_at": cls._aware_or_none(row.next_run_at),
                "created_at": cls._aware_or_none(row.created_at),
                "updated_at": cls._aware_or_none(row.updated_at),
            }
        contract = cls._validate_persisted_task(row)
        return {
            "compatibility": "supported",
            "id": row.id,
            "schema_version": contract["schema_version"],
            "name": contract["name"],
            "task_type": contract["task_type"],
            "schedule": {
                "kind": contract["schedule_kind"],
                "time": contract["schedule_time"],
                "timezone": contract["timezone"],
                "calendar_market": contract["calendar_market"],
                "non_trading_day_policy": contract["non_trading_day_policy"],
            },
            "payload": contract["payload"],
            "enabled": contract["enabled"],
            "max_attempts": contract["max_attempts"],
            "next_run_at": cls._aware_or_none(row.next_run_at),
            "created_at": cls._aware_or_none(row.created_at),
            "updated_at": cls._aware_or_none(row.updated_at),
        }

    @classmethod
    def _run_item(cls, row) -> Dict[str, Any]:
        try:
            status = ScheduledRunStatus(row.status)
        except ValueError as exc:
            raise ScheduledTaskContractError(
                "Persisted scheduled task run status is invalid"
            ) from exc
        execution_task_ids = _json_list(
            row.execution_task_ids_json,
            field_name="execution_task_ids",
        )
        owned_execution_task_ids = _json_list(
            row.owned_execution_task_ids_json,
            field_name="owned_execution_task_ids",
        )
        if not set(owned_execution_task_ids).issubset(execution_task_ids):
            raise ScheduledTaskContractError(
                "Persisted scheduled task run ownership is invalid"
            )
        attempt_count = int(row.attempt_count)
        if not 0 <= attempt_count <= _MAX_ATTEMPTS:
            raise ScheduledTaskContractError(
                "Persisted scheduled task run attempt count is invalid"
            )
        dispatch_failure_count = int(row.dispatch_failure_count)
        if not 0 <= dispatch_failure_count <= _MAX_DISPATCH_FAILURES:
            raise ScheduledTaskContractError(
                "Persisted scheduled task run dispatch failure count is invalid"
            )
        try:
            definition_schema_version = int(row.definition_schema_version)
            definition_generation = int(row.definition_generation)
        except (TypeError, ValueError) as exc:
            raise ScheduledTaskContractError(
                "Persisted scheduled task run definition snapshot is invalid"
            ) from exc
        if definition_schema_version < 1 or definition_generation < 1:
            raise ScheduledTaskContractError(
                "Persisted scheduled task run definition snapshot is invalid"
            )
        dispatch_token = row.dispatch_token
        if status == ScheduledRunStatus.DISPATCHING:
            if not isinstance(dispatch_token, str) or not dispatch_token:
                raise ScheduledTaskContractError(
                    "Persisted scheduled task dispatch reservation is invalid"
                )
        elif dispatch_token is not None:
            raise ScheduledTaskContractError(
                "Persisted scheduled task dispatch reservation is stale"
            )
        notification_status = row.notification_status
        if (
            notification_status is not None
            and notification_status not in SCHEDULED_NOTIFICATION_STATUSES
        ):
            raise ScheduledTaskContractError(
                "Persisted scheduled task notification status is invalid"
            )
        notification_channels = _json_list(
            row.notification_channels_json,
            field_name="notification_channels",
        )
        failed_notification_channels = _json_list(
            row.notification_failed_channels_json,
            field_name="notification_failed_channels",
        )
        if not set(failed_notification_channels).issubset(notification_channels):
            raise ScheduledTaskContractError(
                "Persisted scheduled task notification channels are invalid"
            )
        return {
            "id": row.id,
            "task_id": row.task_id,
            "scheduled_for": cls._aware_or_none(row.scheduled_for),
            "status": status.value,
            "attempt_count": attempt_count,
            "dispatch_failure_count": dispatch_failure_count,
            "execution_task_ids": execution_task_ids,
            "result_refs": _json_list(
                row.result_refs_json,
                field_name="result_refs",
            ),
            "notification_status": notification_status,
            "notification_channels": notification_channels,
            "notification_failed_channels": failed_notification_channels,
            "error_code": row.error_code,
            "next_attempt_at": cls._aware_or_none(row.next_attempt_at),
            "started_at": cls._aware_or_none(row.started_at),
            "finished_at": cls._aware_or_none(row.finished_at),
            "created_at": cls._aware_or_none(row.created_at),
            "updated_at": cls._aware_or_none(row.updated_at),
        }

    @staticmethod
    def _normalize_contract(contract: Mapping[str, Any]) -> Dict[str, Any]:
        if not isinstance(contract, Mapping):
            raise ScheduledTaskValidationError("Scheduled task must be an object")
        schema_version = contract.get(
            "schema_version",
            SCHEDULED_TASK_SCHEMA_VERSION,
        )
        if schema_version != SCHEDULED_TASK_SCHEMA_VERSION:
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
        if task_type != ScheduledTaskType.STOCK_ANALYSIS.value:
            raise ScheduledTaskValidationError(
                f"Unsupported scheduled task type: {task_type}"
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
        allowed_payload_keys = {"stock_code", "report_type", "notify"}
        unexpected_keys = set(payload) - allowed_payload_keys
        if unexpected_keys:
            raise ScheduledTaskValidationError(
                "Unsupported stock analysis payload fields: "
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
        report_type = str(payload.get("report_type") or "detailed").strip().lower()
        if report_type not in _REPORT_TYPES:
            raise ScheduledTaskValidationError(
                f"Unsupported report_type: {report_type}"
            )
        notify = payload.get("notify", True)
        if not isinstance(notify, bool):
            raise ScheduledTaskValidationError("payload.notify must be a boolean")

        enabled = contract.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ScheduledTaskValidationError("enabled must be a boolean")
        max_attempts = contract.get("max_attempts", 1)
        if isinstance(max_attempts, bool):
            raise ScheduledTaskValidationError("max_attempts must be an integer")
        try:
            max_attempts = int(max_attempts)
        except (TypeError, ValueError) as exc:
            raise ScheduledTaskValidationError(
                "max_attempts must be an integer"
            ) from exc
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
            "payload": {
                "stock_code": stock_code,
                "report_type": report_type,
                "notify": notify,
            },
            "enabled": enabled,
            "max_attempts": max_attempts,
        }

    def create_task(
        self,
        contract: Mapping[str, Any],
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Validate and persist one version-one scheduled definition."""
        normalized = self._normalize_contract(contract)
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
                "id": uuid.uuid4().hex,
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
        return self._task_item(row)

    def list_tasks(
        self,
        *,
        enabled: Optional[bool] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """List supported and opaque future definitions safely."""
        rows = self.repository.list_tasks(enabled=enabled, limit=limit)
        return {
            "items": [self._task_item(row) for row in rows],
            "total": self.repository.count_tasks(enabled=enabled),
        }

    def get_task(self, task_id: str) -> Dict[str, Any]:
        """Return one supported or opaque future definition."""
        row = self.repository.get_task(task_id)
        if row is None:
            raise ScheduledTaskNotFoundError(task_id)
        return self._task_item(row)

    def get_status(self, task_id: str) -> Dict[str, Any]:
        """Return one definition together with its latest occurrence."""
        task = self.get_task(task_id)
        runs = self.repository.list_runs(task_id, limit=1)
        return {
            "task": task,
            "latest_run": self._run_item(runs[0]) if runs else None,
        }

    def set_enabled(
        self,
        task_id: str,
        enabled: bool,
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Enable or disable one supported definition."""
        existing = self.repository.get_task(task_id)
        if existing is None:
            raise ScheduledTaskNotFoundError(task_id)
        contract = self._validate_persisted_task(existing)
        if bool(existing.enabled) is bool(enabled):
            return self._task_item(existing)
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
        return self._task_item(row)

    def list_runs(self, task_id: str, *, limit: int = 100) -> Dict[str, Any]:
        """List occurrence records without interpreting definition payloads."""
        if self.repository.get_task(task_id) is None:
            raise ScheduledTaskNotFoundError(task_id)
        rows = self.repository.list_runs(task_id, limit=limit)
        return {
            "items": [self._run_item(row) for row in rows],
            "total": self.repository.count_runs(task_id),
        }

    def has_enabled_tasks(self) -> bool:
        """Return whether persistence contains any enabled definition."""
        return self.repository.has_enabled_tasks()

    def next_run_at(self) -> Optional[datetime]:
        """Return the next executable v1 occurrence, ignoring future schemas."""
        rows = self.repository.list_tasks(enabled=True, limit=500)
        supported_rows = []
        for row in rows:
            try:
                self._validate_persisted_task(row)
            except ScheduledTaskUnsupportedSchemaError:
                continue
            supported_rows.append(row)
        values = [
            row.next_run_at
            for row in supported_rows
            if row.next_run_at is not None
        ]
        return self._aware_or_none(min(values)) if values else None

    def tick(self, *, now: Optional[datetime] = None) -> Dict[str, int]:
        """Reconcile active runs, then atomically claim every due occurrence."""
        if not self._tick_lock.acquire(blocking=False):
            return {"reconciled": 0, "claimed": 0, "skipped": 0}
        try:
            now_value = self._now(now or self._clock())
            try:
                reconciled = self._reconcile_active_runs(now_value)
            except Exception as exc:  # broad-exception: fallback_recorded - the owned polling loop retries database discovery next interval.
                log_safe_exception(
                    logger,
                    "Scheduled task discovery failed; polling will retry",
                    exc,
                    error_code="scheduled_task_discovery_failed",
                )
                return {"reconciled": 0, "claimed": 0, "skipped": 0}
            claimed = 0
            skipped = 0
            try:
                due_tasks = self.repository.list_due_tasks(now=now_value)
            except Exception as exc:  # broad-exception: fallback_recorded - the owned polling loop retries due lookup next interval.
                log_safe_exception(
                    logger,
                    "Scheduled task due lookup failed; polling will retry",
                    exc,
                    error_code="scheduled_task_due_lookup_failed",
                )
                return {
                    "reconciled": reconciled,
                    "claimed": 0,
                    "skipped": 0,
                }
            for task in due_tasks:
                try:
                    result = self._claim_and_dispatch(task, now_value)
                    if result == "claimed":
                        claimed += 1
                    elif result == "skipped":
                        skipped += 1
                except ScheduledTaskUnsupportedSchemaError as exc:
                    fenced = self._record_unsupported_due_task(task, now_value)
                    if fenced:
                        skipped += 1
                        log_safe_exception(
                            logger,
                            "Unsupported scheduled task occurrence fenced",
                            exc,
                            error_code="scheduled_task_schema_unsupported",
                            context={"task_id": task.id},
                            level=logging.WARNING,
                        )
                except ScheduledTaskContractError as exc:
                    quarantined = self._quarantine_due_task(task, now_value)
                    log_safe_exception(
                        logger,
                        "Scheduled task definition quarantined",
                        exc,
                        error_code="scheduled_task_definition_quarantined",
                        context={"task_id": task.id},
                        level=logging.WARNING,
                    )
                    if quarantined:
                        skipped += 1
                except Exception as exc:  # broad-exception: fallback_recorded - isolate one persisted definition and log a stable task id.
                    log_safe_exception(
                        logger,
                        "Scheduled task occurrence handling failed",
                        exc,
                        error_code="scheduled_task_occurrence_failed",
                        context={"task_id": task.id},
                    )
            return {
                "reconciled": reconciled,
                "claimed": claimed,
                "skipped": skipped,
            }
        finally:
            self._tick_lock.release()

    def _reconcile_active_runs(self, now: datetime) -> int:
        reconciled = 0
        for run in self.repository.list_active_runs():
            try:
                task = self.repository.get_task(run.task_id)
                if task is None:
                    self._finish_run(
                        run.id,
                        status=ScheduledRunStatus.INTERRUPTED,
                        now=now,
                        error_code="scheduled_task_definition_missing",
                    )
                else:
                    try:
                        self._validate_persisted_task(task)
                    except ScheduledTaskUnsupportedSchemaError as exc:
                        self._finish_run(
                            run.id,
                            status=ScheduledRunStatus.INTERRUPTED,
                            now=now,
                            error_code="scheduled_task_schema_unsupported",
                        )
                        log_safe_exception(
                            logger,
                            "Scheduled task run interrupted by unsupported schema",
                            exc,
                            error_code="scheduled_task_schema_unsupported",
                            context={"task_id": task.id, "run_id": run.id},
                            level=logging.WARNING,
                        )
                    except ScheduledTaskContractError as exc:
                        disabled = self.repository.set_enabled(
                            task.id,
                            expected_schema_version=task.schema_version,
                            expected_execution_generation=(
                                task.execution_generation
                            ),
                            enabled=False,
                            next_run_at=None,
                            updated_at=now,
                        )
                        if disabled is None:
                            self._reconcile_definition_after_cas_miss(run, now)
                        else:
                            self._finish_run(
                                run.id,
                                status=ScheduledRunStatus.INTERRUPTED,
                                now=now,
                                error_code="scheduled_task_definition_invalid",
                            )
                            log_safe_exception(
                                logger,
                                "Scheduled task definition disabled during reconciliation",
                                exc,
                                error_code="scheduled_task_definition_quarantined",
                                context={"task_id": task.id, "run_id": run.id},
                                level=logging.WARNING,
                            )
                    else:
                        self._reconcile_run(run, task, now)
                reconciled += 1
            except Exception as exc:  # broad-exception: fallback_recorded - one corrupt run must not block other due tasks.
                log_safe_exception(
                    logger,
                    "Scheduled task run reconciliation failed",
                    exc,
                    error_code="scheduled_task_reconciliation_failed",
                    context={"run_id": run.id, "task_id": run.task_id},
                )
        return reconciled

    def _reconcile_definition_after_cas_miss(self, run, now: datetime) -> None:
        """Reclassify a definition changed after active-run validation."""
        current = self.repository.get_task(run.task_id)
        if current is None:
            self._finish_run(
                run.id,
                status=ScheduledRunStatus.INTERRUPTED,
                now=now,
                error_code="scheduled_task_definition_missing",
            )
            return
        try:
            self._validate_persisted_task(current)
        except ScheduledTaskUnsupportedSchemaError as exc:
            self._finish_run(
                run.id,
                status=ScheduledRunStatus.INTERRUPTED,
                now=now,
                error_code="scheduled_task_schema_unsupported",
            )
            log_safe_exception(
                logger,
                "Scheduled task run interrupted after definition schema changed",
                exc,
                error_code="scheduled_task_schema_unsupported",
                context={"task_id": current.id, "run_id": run.id},
                level=logging.WARNING,
            )
        except ScheduledTaskContractError:
            raise ScheduledTaskContractError(
                "Scheduled task definition changed during quarantine"
            )
        else:
            self._reconcile_run(run, current, now)

    def _record_unsupported_due_task(self, task, now: datetime) -> bool:
        """Fence one unsupported due slot without mutating its definition."""
        scheduled_for = task.next_run_at
        if scheduled_for is None:
            return False
        run = self.repository.record_unmodified_interrupted_occurrence(
            task_id=task.id,
            expected_schema_version=task.schema_version,
            expected_execution_generation=task.execution_generation,
            expected_next_run_at=scheduled_for,
            run_fields={
                "id": uuid.uuid4().hex,
                "task_id": task.id,
                "scheduled_for": scheduled_for,
                "definition_schema_version": task.schema_version,
                "definition_generation": task.execution_generation,
                "dispatch_token": None,
                "status": ScheduledRunStatus.INTERRUPTED.value,
                "attempt_count": 0,
                "dispatch_failure_count": 0,
                "execution_task_ids_json": "[]",
                "owned_execution_task_ids_json": "[]",
                "result_refs_json": "[]",
                "notification_status": None,
                "notification_channels_json": "[]",
                "notification_failed_channels_json": "[]",
                "error_code": "scheduled_task_schema_unsupported",
                "next_attempt_at": None,
                "started_at": None,
                "finished_at": now,
                "created_at": now,
                "updated_at": now,
            },
        )
        return run is not None

    def _reclassify_due_after_cas_miss(
        self,
        task_id: str,
        now: datetime,
    ) -> Optional[str]:
        """Re-read a due definition after another writer changed its schema."""
        current = self.repository.get_task(task_id)
        if (
            current is None
            or not bool(current.enabled)
            or current.next_run_at is None
            or current.next_run_at > now
        ):
            return None
        try:
            self._validate_persisted_task(current)
        except ScheduledTaskUnsupportedSchemaError:
            return (
                "skipped"
                if self._record_unsupported_due_task(current, now)
                else None
            )
        except ScheduledTaskContractError:
            return (
                "skipped"
                if self._quarantine_due_task(
                    current,
                    now,
                    reclassify_on_miss=False,
                )
                else None
            )
        return None

    def _quarantine_due_task(
        self,
        task,
        now: datetime,
        *,
        reclassify_on_miss: bool = True,
    ) -> bool:
        scheduled_for = task.next_run_at
        if scheduled_for is None:
            return False
        run = self.repository.quarantine_due_task(
            task_id=task.id,
            expected_schema_version=task.schema_version,
            expected_execution_generation=task.execution_generation,
            expected_next_run_at=scheduled_for,
            run_fields={
                "id": uuid.uuid4().hex,
                "task_id": task.id,
                "scheduled_for": scheduled_for,
                "definition_schema_version": task.schema_version,
                "definition_generation": task.execution_generation,
                "dispatch_token": None,
                "status": ScheduledRunStatus.INTERRUPTED.value,
                "attempt_count": 0,
                "dispatch_failure_count": 0,
                "execution_task_ids_json": "[]",
                "owned_execution_task_ids_json": "[]",
                "result_refs_json": "[]",
                "notification_status": None,
                "notification_channels_json": "[]",
                "notification_failed_channels_json": "[]",
                "error_code": "scheduled_task_definition_invalid",
                "next_attempt_at": None,
                "started_at": None,
                "finished_at": now,
                "created_at": now,
                "updated_at": now,
            },
            updated_at=now,
        )
        if run is not None:
            return True
        if reclassify_on_miss:
            return self._reclassify_due_after_cas_miss(task.id, now) == "skipped"
        return False

    def _classify_market_session(self, market: str, local_date) -> MarketSessionStatus:
        try:
            return MarketSessionStatus(
                self._market_session_provider(market, local_date)
            )
        except Exception as exc:  # broad-exception: fallback_recorded - scheduled financial work fails closed when classification is unavailable.
            log_safe_exception(
                logger,
                "Scheduled task calendar classification failed closed",
                exc,
                error_code="scheduled_task_calendar_lookup_failed",
                context={"market": market},
                level=logging.WARNING,
            )
            return MarketSessionStatus.UNKNOWN

    def _claim_and_dispatch(self, task, now: datetime) -> Optional[str]:
        contract = self._validate_persisted_task(task)
        scheduled_for = task.next_run_at
        if scheduled_for is None:
            return None
        next_run = next_daily_run_at(
            schedule_time=contract["schedule_time"],
            timezone_name=contract["timezone"],
            after=max(now, scheduled_for),
        )
        local_date = scheduled_local_date(
            scheduled_for,
            timezone_name=MARKET_TIMEZONE[contract["calendar_market"]],
        )
        terminal_status = None
        terminal_error = None
        if contract["non_trading_day_policy"] == NonTradingDayPolicy.SKIP.value:
            session_status = self._classify_market_session(
                contract["calendar_market"],
                local_date,
            )
            if session_status == MarketSessionStatus.CLOSED:
                terminal_status = ScheduledRunStatus.SKIPPED
                terminal_error = "non_trading_day"
            elif session_status == MarketSessionStatus.UNKNOWN:
                terminal_status = ScheduledRunStatus.INTERRUPTED
                terminal_error = "scheduled_task_calendar_unavailable"
        run_id = uuid.uuid4().hex
        run_status = terminal_status or ScheduledRunStatus.DISPATCHING
        dispatch_token = uuid.uuid4().hex if terminal_status is None else None
        run = self.repository.claim_due_occurrence(
            task_id=task.id,
            expected_schema_version=task.schema_version,
            expected_execution_generation=task.execution_generation,
            expected_next_run_at=scheduled_for,
            next_run_at=next_run,
            run_fields={
                "id": run_id,
                "task_id": task.id,
                "scheduled_for": scheduled_for,
                "definition_schema_version": task.schema_version,
                "definition_generation": task.execution_generation,
                "dispatch_token": dispatch_token,
                "status": run_status.value,
                "attempt_count": 0,
                "dispatch_failure_count": 0,
                "execution_task_ids_json": "[]",
                "owned_execution_task_ids_json": "[]",
                "result_refs_json": "[]",
                "notification_status": None,
                "notification_channels_json": "[]",
                "notification_failed_channels_json": "[]",
                "error_code": terminal_error,
                "next_attempt_at": None,
                "started_at": None if terminal_status is not None else now,
                "finished_at": now if terminal_status is not None else None,
                "created_at": now,
                "updated_at": now,
            },
            updated_at=now,
        )
        if run is None:
            return self._reclassify_due_after_cas_miss(task.id, now)
        if terminal_status is not None:
            return "skipped"
        self._admit_run(run, now)
        return "claimed"

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
        failure_count = int(run.dispatch_failure_count) + 1
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
            "attempt_count": int(run.attempt_count) + 1,
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

    def _admit_run(self, run, now: datetime) -> None:
        """Resolve one reserved occurrence to a durable queue execution identity."""
        dispatch_token = str(run.dispatch_token or "")
        if not dispatch_token:
            self._finish_run(
                run.id,
                status=ScheduledRunStatus.INTERRUPTED,
                now=now,
                error_code="scheduled_task_dispatch_reservation_invalid",
            )
            return
        queue = self._queue()

        def update_factory(task, current_run) -> Dict[str, Any]:
            try:
                contract = self._validate_persisted_task(task)
            except ScheduledTaskContractError as exc:
                task.enabled = False
                task.execution_generation = int(task.execution_generation) + 1
                task.next_run_at = None
                task.updated_at = now
                log_safe_exception(
                    logger,
                    "Scheduled task definition disabled before queue admission",
                    exc,
                    error_code="scheduled_task_definition_quarantined",
                    context={"task_id": task.id, "run_id": current_run.id},
                    level=logging.WARNING,
                )
                return self._interrupted_admission_fields(
                    now,
                    error_code="scheduled_task_definition_invalid",
                )

            if int(current_run.attempt_count) >= int(task.max_attempts):
                return {
                    **self._interrupted_admission_fields(
                        now,
                        error_code="scheduled_task_execution_attempts_exhausted",
                    ),
                    "status": ScheduledRunStatus.FAILED.value,
                }

            execution_history = _json_list(
                current_run.execution_task_ids_json,
                field_name="execution_task_ids",
            )
            owned_history = set(_json_list(
                current_run.owned_execution_task_ids_json,
                field_name="owned_execution_task_ids",
            ))
            retry_owned_execution = bool(
                execution_history and execution_history[-1] in owned_history
            )

            if retry_owned_execution:
                try:
                    retry_nowait = getattr(queue, "retry_nowait", None)
                    execution_id = (
                        retry_nowait(execution_history[-1])
                        if callable(retry_nowait)
                        else queue.retry(execution_history[-1])
                    )
                except TaskRetryInProgressError:
                    return self._conflict_wait_fields(now)
                except DuplicateTaskError as exc:
                    if exc.existing_contract != exc.requested_contract:
                        return self._conflict_wait_fields(now)
                    execution_id = exc.existing_task_id
                    owned = False
                except TaskNotFoundError:
                    return self._interrupted_admission_fields(
                        now,
                        error_code="scheduled_task_execution_state_lost",
                    )
                except Exception as exc:  # broad-exception: fallback_recorded - canonical retry rejection is persisted and retried independently from execution attempts.
                    log_safe_exception(
                        logger,
                        "Scheduled task retry admission failed",
                        exc,
                        error_code="scheduled_task_retry_failed",
                        context={
                            "run_id": current_run.id,
                            "task_id": current_run.task_id,
                        },
                    )
                    return self._dispatch_failure_fields(
                        current_run,
                        now,
                        error_code="scheduled_task_retry_failed",
                    )
                else:
                    owned = True
                if not isinstance(execution_id, str) or not execution_id:
                    return self._interrupted_admission_fields(
                        now,
                        error_code="scheduled_task_retry_state_lost",
                    )
                return self._running_admission_fields(
                    current_run,
                    now,
                    execution_id=execution_id,
                    owned=owned,
                )

            payload = contract["payload"]
            try:
                accepted, duplicates = queue.submit_tasks_batch(
                    stock_codes=[str(payload["stock_code"])],
                    query_source="scheduled_task",
                    report_type=str(payload.get("report_type") or "detailed"),
                    notify=bool(payload.get("notify", True)),
                )
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
                return self._dispatch_failure_fields(
                    current_run,
                    now,
                    error_code="scheduled_task_dispatch_failed",
                )

            accepted = list(accepted or [])
            duplicates = list(duplicates or [])
            if len(accepted) + len(duplicates) != 1:
                if accepted:
                    return self._interrupted_admission_fields(
                        now,
                        error_code="scheduled_task_dispatch_state_lost",
                    )
                return self._dispatch_failure_fields(
                    current_run,
                    now,
                    error_code="scheduled_task_dispatch_failed",
                )
            if duplicates:
                duplicate = duplicates[0]
                if duplicate.existing_contract != duplicate.requested_contract:
                    return self._conflict_wait_fields(now)
                execution_id = duplicate.existing_task_id
                owned = False
            else:
                execution_id = accepted[0].task_id
                owned = True
            if not isinstance(execution_id, str) or not execution_id:
                return self._interrupted_admission_fields(
                    now,
                    error_code="scheduled_task_dispatch_state_lost",
                )
            return self._running_admission_fields(
                current_run,
                now,
                execution_id=execution_id,
                owned=owned,
            )

        try:
            result = self.repository.update_run_under_definition_fence(
                run_id=run.id,
                expected_schema_version=SCHEDULED_TASK_SCHEMA_VERSION,
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
            return

        if result.outcome == "applied":
            if (
                result.run is not None
                and result.task is not None
                and result.run.status == ScheduledRunStatus.RUNNING.value
            ):
                self._reconcile_run(result.run, result.task, now)
            return
        self._finalize_admission_fence_miss(
            run,
            dispatch_token=dispatch_token,
            outcome=result.outcome,
            now=now,
        )

    def _finalize_admission_fence_miss(
        self,
        run,
        *,
        dispatch_token: str,
        outcome: str,
        now: datetime,
    ) -> None:
        execution_ids = _json_list(
            run.execution_task_ids_json,
            field_name="execution_task_ids",
        )
        phase = "retry" if execution_ids else "dispatch"
        error_codes = {
            "task_missing": "scheduled_task_definition_missing",
            "schema_changed": "scheduled_task_schema_unsupported",
            "generation_changed": f"scheduled_task_definition_changed_before_{phase}",
            "disabled": f"scheduled_task_disabled_before_{phase}",
        }
        error_code = error_codes.get(outcome)
        if error_code is None:
            return
        self.repository.finalize_dispatch_reservation(
            run_id=run.id,
            dispatch_token=dispatch_token,
            fields=self._interrupted_admission_fields(
                now,
                error_code=error_code,
            ),
        )

    @staticmethod
    def _notification_outcome(
        *,
        requested: bool,
        result: Any,
    ) -> tuple[str, list[str], list[str]]:
        if not requested:
            return "not_requested", [], []
        if not isinstance(result, Mapping):
            return "unknown", [], []
        diagnostic_summary = result.get("diagnostic_summary")
        if not isinstance(diagnostic_summary, Mapping):
            return "unknown", [], []
        components = diagnostic_summary.get("components")
        if not isinstance(components, Mapping):
            return "unknown", [], []
        notification = components.get("notification")
        if not isinstance(notification, Mapping):
            return "unknown", [], []
        status = notification.get("status")
        if status not in SCHEDULED_NOTIFICATION_STATUSES - {"not_requested"}:
            return "unknown", [], []
        details = notification.get("details")
        details = details if isinstance(details, Mapping) else {}
        channels = _sanitized_channels(details.get("channels"))
        failed_channels = _sanitized_channels(details.get("failed"))
        if status == "failed" and not failed_channels:
            failed_channels = list(channels)
        elif status != "degraded":
            failed_channels = []
        for channel in failed_channels:
            if (
                channel not in channels
                and len(channels) < _MAX_NOTIFICATION_CHANNELS
            ):
                channels.append(channel)
        failed_channels = [
            channel for channel in failed_channels if channel in channels
        ]
        return str(status), channels, failed_channels

    def _completed_notification_fields(
        self,
        *,
        queue: Any,
        execution_id: str,
        requested: bool,
    ) -> Dict[str, Any]:
        result = None
        if requested:
            accessor = getattr(queue, "get_task", None)
            if callable(accessor):
                try:
                    task_info = accessor(execution_id)
                    result = getattr(task_info, "result", None)
                except Exception as exc:  # broad-exception: fallback_recorded - malformed or evicted full results degrade only the notification projection.
                    log_safe_exception(
                        logger,
                        "Scheduled task notification result projection unavailable",
                        exc,
                        error_code="scheduled_task_notification_projection_failed",
                        context={"execution_id": execution_id},
                        level=logging.WARNING,
                    )
        status, channels, failed_channels = self._notification_outcome(
            requested=requested,
            result=result,
        )
        return {
            "notification_status": status,
            "notification_channels_json": json.dumps(channels),
            "notification_failed_channels_json": json.dumps(failed_channels),
        }

    def _reconcile_run(self, run, task, now: datetime) -> None:
        status = ScheduledRunStatus(run.status)
        if status == ScheduledRunStatus.DISPATCHING:
            dispatch_token = str(run.dispatch_token or "")
            if dispatch_token:
                self.repository.finalize_dispatch_reservation(
                    run_id=run.id,
                    dispatch_token=dispatch_token,
                    fields=self._interrupted_admission_fields(
                        now,
                        error_code="scheduled_task_dispatch_interrupted",
                    ),
                )
            else:
                self._finish_run(
                    run.id,
                    status=ScheduledRunStatus.INTERRUPTED,
                    now=now,
                    error_code="scheduled_task_dispatch_interrupted",
                )
            return
        if status == ScheduledRunStatus.RETRY_WAIT:
            execution_ids = _json_list(
                run.execution_task_ids_json,
                field_name="execution_task_ids",
            )
            phase = "retry" if execution_ids else "dispatch"
            if not bool(task.enabled):
                self._finish_run(
                    run.id,
                    status=ScheduledRunStatus.INTERRUPTED,
                    now=now,
                    error_code=f"scheduled_task_disabled_before_{phase}",
                )
                return
            if int(task.execution_generation) != int(run.definition_generation):
                self._finish_run(
                    run.id,
                    status=ScheduledRunStatus.INTERRUPTED,
                    now=now,
                    error_code=f"scheduled_task_definition_changed_before_{phase}",
                )
                return
            if run.next_attempt_at is not None and run.next_attempt_at > now:
                return
            dispatch_token = uuid.uuid4().hex
            reserved = self.repository.reserve_run_admission(
                run_id=run.id,
                dispatch_token=dispatch_token,
                now=now,
            )
            if reserved is not None:
                self._admit_run(reserved, now)
            return
        if status != ScheduledRunStatus.RUNNING:
            return

        execution_ids = _json_list(
            run.execution_task_ids_json,
            field_name="execution_task_ids",
        )
        if not execution_ids:
            self._finish_run(
                run.id,
                status=ScheduledRunStatus.FAILED,
                now=now,
                error_code="scheduled_task_execution_contract_invalid",
            )
            return
        queue = self._queue()
        try:
            current_execution_id = execution_ids[-1]
            snapshot = queue.get(current_execution_id)
        except TaskNotFoundError:
            self._finish_run(
                run.id,
                status=ScheduledRunStatus.INTERRUPTED,
                now=now,
                error_code="scheduled_task_execution_state_lost",
            )
            return

        if not snapshot.status.terminal:
            return
        if snapshot.status == TaskStatus.COMPLETED:
            contract = self._validate_persisted_task(task)
            result_refs = [snapshot.result_ref] if snapshot.result_ref else []
            notification_fields = self._completed_notification_fields(
                queue=queue,
                execution_id=current_execution_id,
                requested=bool(contract["payload"].get("notify", True)),
            )
            self.repository.update_run(
                run.id,
                {
                    "status": ScheduledRunStatus.SUCCEEDED.value,
                    "dispatch_token": None,
                    "result_refs_json": json.dumps(result_refs),
                    **notification_fields,
                    "error_code": None,
                    "next_attempt_at": None,
                    "finished_at": now,
                    "updated_at": now,
                },
            )
            return

        if not bool(task.enabled):
            self._finish_run(
                run.id,
                status=ScheduledRunStatus.INTERRUPTED,
                now=now,
                error_code="scheduled_task_disabled_before_retry",
            )
            return
        if int(task.execution_generation) != int(run.definition_generation):
            self._finish_run(
                run.id,
                status=ScheduledRunStatus.INTERRUPTED,
                now=now,
                error_code="scheduled_task_definition_changed_before_retry",
            )
            return

        owned_ids = set(
            _json_list(
                run.owned_execution_task_ids_json,
                field_name="owned_execution_task_ids",
            )
        )
        error_code = snapshot.error_code or "scheduled_task_execution_failed"
        if current_execution_id not in owned_ids:
            if int(run.attempt_count) < int(task.max_attempts):
                self.repository.update_run(
                    run.id,
                    {
                        "status": ScheduledRunStatus.RETRY_WAIT.value,
                        "dispatch_token": None,
                        "error_code": "scheduled_task_coalesced_execution_failed",
                        "next_attempt_at": now
                        + timedelta(seconds=SCHEDULED_TASK_RETRY_DELAY_SECONDS),
                        "finished_at": None,
                        "updated_at": now,
                    },
                )
            else:
                self._finish_run(
                    run.id,
                    status=ScheduledRunStatus.FAILED,
                    now=now,
                    error_code="scheduled_task_coalesced_execution_failed",
                )
        elif int(run.attempt_count) < int(task.max_attempts):
            self.repository.update_run(
                run.id,
                {
                    "status": ScheduledRunStatus.RETRY_WAIT.value,
                    "dispatch_token": None,
                    "error_code": error_code,
                    "next_attempt_at": now
                    + timedelta(seconds=SCHEDULED_TASK_RETRY_DELAY_SECONDS),
                    "finished_at": None,
                    "updated_at": now,
                },
            )
        else:
            self._finish_run(
                run.id,
                status=ScheduledRunStatus.FAILED,
                now=now,
                error_code=error_code,
            )

    def _finish_run(
        self,
        run_id: str,
        *,
        status: ScheduledRunStatus,
        now: datetime,
        error_code: str,
        attempt_count: Optional[int] = None,
    ) -> None:
        fields: Dict[str, Any] = {
            "status": status.value,
            "dispatch_token": None,
            "error_code": error_code,
            "next_attempt_at": None,
            "finished_at": now,
            "updated_at": now,
        }
        if attempt_count is not None:
            fields["attempt_count"] = attempt_count
        self.repository.update_run(run_id, fields)


__all__ = [
    "ScheduledTaskContractError",
    "ScheduledTaskError",
    "ScheduledTaskNotFoundError",
    "ScheduledTaskService",
    "ScheduledTaskUnsupportedSchemaError",
    "ScheduledTaskValidationError",
]
