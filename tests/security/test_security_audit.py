# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persistence, redaction, retention, and failure tests for security audit v1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from src.repositories.security_audit_repo import SecurityAuditRepository
from src.schemas.security_audit import (
    SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS,
    SecurityAuditEventCreate,
)
from src.services.security_audit_service import (
    SecurityAuditService,
    SecurityAuditUnavailable,
    require_security_audit_recorder,
)
from src.storage import DatabaseManager


@pytest.fixture
def isolated_database(tmp_path):
    DatabaseManager.reset_instance()
    manager = DatabaseManager(f"sqlite:///{tmp_path / 'security-audit.sqlite'}")
    try:
        yield manager
    finally:
        DatabaseManager.reset_instance()


class _CapturingSecurityAuditRepository(SecurityAuditRepository):
    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__(db_manager)
        self.appended_event: SecurityAuditEventCreate | None = None

    def append(self, event: SecurityAuditEventCreate):
        self.appended_event = event
        return super().append(event)


class _CountingRetentionRepository(SecurityAuditRepository):
    def __init__(self, db_manager: DatabaseManager, *, fail_first: bool = False) -> None:
        super().__init__(db_manager)
        self.retention_calls = 0
        self.fail_first = fail_first

    def apply_retention(self, *, cutoff):
        self.retention_calls += 1
        if self.fail_first and self.retention_calls == 1:
            raise RuntimeError("retention unavailable")
        return super().apply_retention(cutoff=cutoff)


def _record_attempt(service: SecurityAuditService, **overrides):
    fields = {
        "event_type": "auth.login",
        "actor_type": "remote_client",
        "actor_id": "client:fixture",
        "execution_id": "execution-fixture",
        "action": "auth.login",
        "target_type": "admin_session",
        "target_id": "primary",
        "correlation_id": "0123456789abcdef0123456789abcdef",
        "metadata": {},
    }
    fields.update(overrides)
    return service.record_attempt(**fields)


def test_service_redacts_before_repository_and_raw_sqlite_persistence(isolated_database) -> None:
    repository = _CapturingSecurityAuditRepository(isolated_database)
    service = SecurityAuditService(repository)
    secret = "sk_live_abcdefghijklmnop"

    persisted = _record_attempt(
        service,
        metadata={
            "api_key": secret,
            "cookie": f"dsa_session={secret}",
            "reference": f"https://user:{secret}@example.com/report?token={secret}",
        },
    )

    assert persisted.metadata["api_key"] == "[REDACTED]"
    assert repository.appended_event is not None
    assert secret not in repr(repository.appended_event.model_dump())
    with isolated_database.get_session() as session:
        raw = session.execute(
            text(
                "SELECT actor_id, execution_id, target_id, metadata_json "
                "FROM security_audit_events WHERE id = :event_id"
            ),
            {"event_id": persisted.id},
        ).one()
    rendered = " ".join(str(value) for value in raw)
    assert secret not in rendered
    assert "user:" not in rendered
    assert "token=" not in rendered
    assert "[REDACTED]" in rendered


def test_retention_and_query_are_bounded(isolated_database) -> None:
    repository = SecurityAuditRepository(isolated_database)
    service = SecurityAuditService(repository, retention_days=90)
    old = SecurityAuditEventCreate(
        occurred_at=datetime.now(timezone.utc) - timedelta(days=91),
        event_type="auth.login",
        phase="attempt",
        actor={"type": "remote_client", "id": "client:old"},
        execution_id="old-execution",
        action="auth.login",
        target={"type": "admin_session", "id": "primary"},
        outcome="pending",
        reason_code="attempt_started",
        correlation_id="abcdef0123456789abcdef0123456789",
    )
    repository.append(old)
    current = _record_attempt(service)

    page = service.list_events(page=1, page_size=100)

    assert page.total == 1
    assert [event.id for event in page.items] == [current.id]
    assert page.page_size == 100


def test_retention_runs_once_per_utc_day_for_reused_service(isolated_database) -> None:
    repository = _CountingRetentionRepository(isolated_database)
    service = SecurityAuditService(repository)

    first = _record_attempt(service)
    second = _record_attempt(
        service,
        correlation_id="fedcba9876543210fedcba9876543210",
    )
    page = service.list_events(page=1, page_size=100)

    assert repository.retention_calls == 1
    assert page.total == 2
    assert {event.id for event in page.items} == {first.id, second.id}

    service._retention_applied_on = datetime.now(timezone.utc).date() - timedelta(days=1)
    _record_attempt(
        service,
        correlation_id="00112233445566778899aabbccddeeff",
    )

    assert repository.retention_calls == 2


def test_retention_failure_is_retried_before_later_append(isolated_database) -> None:
    repository = _CountingRetentionRepository(isolated_database, fail_first=True)
    service = SecurityAuditService(repository)

    with pytest.raises(SecurityAuditUnavailable):
        _record_attempt(service)

    persisted = _record_attempt(service)

    assert repository.retention_calls == 2
    assert persisted.action == "auth.login"


class _FailingRepository:
    def apply_retention(self, *, cutoff):
        del cutoff
        return 0

    def append(self, event):
        del event
        raise RuntimeError("database contains password=do-not-log")


def test_append_failure_is_normalized_to_stable_unavailable(caplog) -> None:
    service = SecurityAuditService(_FailingRepository())

    with pytest.raises(SecurityAuditUnavailable) as exc_info:
        _record_attempt(service)

    assert str(exc_info.value) == "security_audit_unavailable"
    assert "do-not-log" not in caplog.text


@pytest.mark.parametrize(
    "recorder",
    [None, object(), {"record_attempt": lambda: None}],
)
def test_required_recorder_rejects_missing_or_malformed_dependencies(recorder) -> None:
    with pytest.raises(SecurityAuditUnavailable) as exc_info:
        require_security_audit_recorder(recorder)

    assert str(exc_info.value) == "security_audit_unavailable"


def test_metadata_contract_rejects_unbounded_or_non_json_values() -> None:
    service = SecurityAuditService(_FailingRepository())
    with pytest.raises(ValueError, match="too many keys"):
        SecurityAuditEventCreate(
            event_type="auth.login",
            phase="attempt",
            actor={"type": "remote_client", "id": "client:test"},
            execution_id="execution",
            action="auth.login",
            target={"type": "admin_session", "id": "primary"},
            outcome="pending",
            reason_code="attempt_started",
            correlation_id="0123456789abcdef0123456789abcdef",
            metadata={f"key_{index}": index for index in range(17)},
        )


def test_metadata_list_contract_accepts_bound_and_rejects_overflow() -> None:
    common = {
        "event_type": "system_config.write",
        "phase": "attempt",
        "actor": {"type": "administrator", "id": "local_operator"},
        "execution_id": "execution",
        "action": "system_config.write",
        "target": {"type": "system_config", "id": "runtime"},
        "outcome": "pending",
        "reason_code": "attempt_started",
        "correlation_id": "0123456789abcdef0123456789abcdef",
    }
    bounded_keys = [
        f"CONFIG_KEY_{index}"
        for index in range(SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS)
    ]

    event = SecurityAuditEventCreate(
        **common,
        metadata={"keys": bounded_keys},
    )

    assert event.metadata["keys"] == bounded_keys
    with pytest.raises(ValueError, match="too many items"):
        SecurityAuditEventCreate(
            **common,
            metadata={"keys": [*bounded_keys, "CONFIG_KEY_OVERFLOW"]},
        )
