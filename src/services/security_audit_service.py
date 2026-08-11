# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed service for durable privileged-operation security auditing."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from threading import Lock
from typing import Any, Optional, Protocol, cast
import uuid
from weakref import WeakKeyDictionary

from src.repositories.security_audit_repo import SecurityAuditRepository
from src.schemas.security_audit import (
    SECURITY_AUDIT_RETENTION_DAYS,
    SecurityAuditEvent,
    SecurityAuditEventCreate,
    SecurityAuditEventPage,
    SecurityAuditOutcome,
)
from src.utils.sanitize import log_safe_exception, redact_sensitive_data


logger = logging.getLogger(__name__)

SECURITY_AUDIT_UNAVAILABLE = "security_audit_unavailable"


class SecurityAuditUnavailable(RuntimeError):
    """Stable failure raised when a required audit event cannot be persisted."""

    code = SECURITY_AUDIT_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__(SECURITY_AUDIT_UNAVAILABLE)


class SecurityAuditRecorder(Protocol):
    """Minimum fail-closed recorder contract required by privileged paths."""

    def record_attempt(self, **fields: Any) -> Any:
        """Persist an attempt event before a privileged operation."""

    def record_completion(self, **fields: Any) -> Any:
        """Persist a completion event after a privileged operation."""


def require_security_audit_recorder(value: object) -> SecurityAuditRecorder:
    """Return a structurally valid recorder or fail with the stable audit error."""
    if not callable(getattr(value, "record_attempt", None)) or not callable(
        getattr(value, "record_completion", None)
    ):
        raise SecurityAuditUnavailable()
    return cast(SecurityAuditRecorder, value)


class SecurityAuditService:
    """Sanitize, validate, retain, append, and query security audit events."""

    _shared_retention_lock = Lock()
    _retention_by_database: WeakKeyDictionary[object, dict[int, date]] = (
        WeakKeyDictionary()
    )

    def __init__(
        self,
        repository: Optional[SecurityAuditRepository] = None,
        *,
        retention_days: int = SECURITY_AUDIT_RETENTION_DAYS,
    ) -> None:
        if retention_days < 1:
            raise ValueError("security audit retention must be at least one day")
        self._repository = repository
        self._retention_days = int(retention_days)
        self._retention_applied_on: date | None = None
        self._retention_lock = Lock()

    @staticmethod
    def new_correlation_id() -> str:
        return uuid.uuid4().hex

    def record_attempt(
        self,
        *,
        event_type: str,
        actor_type: str,
        actor_id: str,
        execution_id: str,
        action: str,
        target_type: str,
        target_id: str,
        correlation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> SecurityAuditEvent:
        return self._record(
            event_type=event_type,
            phase="attempt",
            actor_type=actor_type,
            actor_id=actor_id,
            execution_id=execution_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            outcome="pending",
            reason_code="attempt_started",
            correlation_id=correlation_id,
            metadata=metadata,
        )

    def record_completion(
        self,
        *,
        event_type: str,
        actor_type: str,
        actor_id: str,
        execution_id: str,
        action: str,
        target_type: str,
        target_id: str,
        outcome: SecurityAuditOutcome,
        reason_code: str,
        correlation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> SecurityAuditEvent:
        return self._record(
            event_type=event_type,
            phase="completion",
            actor_type=actor_type,
            actor_id=actor_id,
            execution_id=execution_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            reason_code=reason_code,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    def list_events(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        event_type: str | None = None,
        outcome: str | None = None,
        correlation_id: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
    ) -> SecurityAuditEventPage:
        try:
            repository = self._get_repository()
            self._apply_retention_if_due(repository)
            items, total = repository.list_events(
                page=page,
                page_size=page_size,
                event_type=event_type,
                outcome=outcome,
                correlation_id=correlation_id,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
            )
            return SecurityAuditEventPage(
                items=items,
                page=page,
                page_size=page_size,
                total=total,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Normalize query/storage failures to the stable fail-closed contract.
            log_safe_exception(
                logger,
                "security_audit_query_failed",
                exc,
                error_code=SECURITY_AUDIT_UNAVAILABLE,
            )
            raise SecurityAuditUnavailable() from None

    def _record(
        self,
        *,
        event_type: str,
        phase: str,
        actor_type: str,
        actor_id: str,
        execution_id: str,
        action: str,
        target_type: str,
        target_id: str,
        outcome: SecurityAuditOutcome,
        reason_code: str,
        correlation_id: str,
        metadata: dict[str, Any] | None,
    ) -> SecurityAuditEvent:
        try:
            sanitized = redact_sensitive_data(
                {
                    "event_type": event_type,
                    "phase": phase,
                    "actor": {"type": actor_type, "id": actor_id},
                    "execution_id": execution_id,
                    "action": action,
                    "target": {"type": target_type, "id": target_id},
                    "outcome": outcome,
                    "reason_code": reason_code,
                    "correlation_id": correlation_id,
                    "metadata": metadata or {},
                }
            )
            event = SecurityAuditEventCreate.model_validate(sanitized)
            repository = self._get_repository()
            self._apply_retention_if_due(repository)
            return repository.append(event)
        except Exception as exc:  # broad-exception: fallback_recorded - Normalize validation/redaction/storage failures before a privileged action proceeds.
            log_safe_exception(
                logger,
                "security_audit_append_failed",
                exc,
                error_code=SECURITY_AUDIT_UNAVAILABLE,
            )
            raise SecurityAuditUnavailable() from None

    def _get_repository(self) -> SecurityAuditRepository:
        if self._repository is None:
            self._repository = SecurityAuditRepository()
        return self._repository

    def _apply_retention_if_due(self, repository: SecurityAuditRepository) -> None:
        now = datetime.now(timezone.utc)
        today = now.date()
        if self._retention_applied_on == today:
            return
        with self._retention_lock:
            if self._retention_applied_on == today:
                return
            if type(repository) is SecurityAuditRepository:
                with self._shared_retention_lock:
                    retained = self._retention_by_database.get(repository.db)
                    if (
                        retained is not None
                        and retained.get(self._retention_days) == today
                    ):
                        self._retention_applied_on = today
                        return
                    repository.apply_retention(
                        cutoff=now - timedelta(days=self._retention_days)
                    )
                    if retained is None:
                        retained = {}
                        self._retention_by_database[repository.db] = retained
                    retained[self._retention_days] = today
                    self._retention_applied_on = today
                    return
            repository.apply_retention(
                cutoff=now - timedelta(days=self._retention_days)
            )
            self._retention_applied_on = today


def get_security_audit_service() -> SecurityAuditService:
    """FastAPI/runtime dependency factory with lazy database initialization."""
    return SecurityAuditService()
