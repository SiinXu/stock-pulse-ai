"""State-machine, ownership, persistence, and audit tests for approvals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import MagicMock

from pydantic import ValidationError
import pytest
from sqlalchemy.exc import OperationalError

from src.config import Config
from src.repositories.approval_repo import (
    ApprovalInvalidTransitionError,
    ApprovalNotFoundError,
    ApprovalRepository,
    ApprovalVersionConflictError,
)
from src.repositories.security_audit_repo import SecurityAuditRepository
from src.schemas.approvals import (
    ApprovalContext,
    ApprovalDecision,
    ApprovalRiskSource,
    ApprovalStatus,
)
from src.services.approval_service import (
    ApprovalService,
    ApprovalServiceInvalidTransitionError,
    ApprovalServiceVersionConflictError,
)
from src.services.security_audit_service import SecurityAuditService
from src.storage import DatabaseManager
from tests.security_audit_test_utils import SecurityAuditRecorderStub


@pytest.fixture
def database():
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    yield manager
    DatabaseManager.reset_instance()
    Config.reset_instance()


def _context() -> ApprovalContext:
    return ApprovalContext(
        stock_code="AAPL",
        original_signal="buy",
        conservative_signal="hold",
        risk_source=ApprovalRiskSource.RISK_VETO,
        risk_summary="A risk veto would replace the original buy signal.",
    )


def test_rule_defaults_off_and_updates_with_cas(database) -> None:
    repository = ApprovalRepository(database)
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)

    default = repository.get_rule(owner="owner-a")
    assert default.enabled is False
    assert default.version == 0
    updated = repository.put_rule(
        owner="owner-a",
        enabled=True,
        risk_sources=[ApprovalRiskSource.RISK_VETO],
        expires_in_seconds=300,
        expected_version=0,
        now=now,
    )
    assert updated.enabled is True
    assert updated.version == 1

    with pytest.raises(ApprovalVersionConflictError) as stale:
        repository.put_rule(
            owner="owner-a",
            enabled=False,
            risk_sources=[ApprovalRiskSource.RISK_DOWNGRADE],
            expires_in_seconds=30,
            expected_version=0,
            now=now,
        )
    assert stale.value.current_version == 1


def test_proposal_is_owner_scoped_terminal_and_consumed_once(database) -> None:
    repository = ApprovalRepository(database)
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    proposal, created = repository.create_or_get_proposal(
        proposal_id="a" * 32,
        owner="owner-a",
        risk_source=ApprovalRiskSource.RISK_VETO,
        idempotency_key="b" * 64,
        execution_id="execution-a",
        context=_context(),
        expires_at=now + timedelta(minutes=5),
        now=now,
    )
    assert created is True
    replay, created = repository.create_or_get_proposal(
        proposal_id="c" * 32,
        owner="owner-a",
        risk_source=ApprovalRiskSource.RISK_VETO,
        idempotency_key="b" * 64,
        execution_id="execution-a",
        context=_context(),
        expires_at=now + timedelta(minutes=5),
        now=now,
    )
    assert created is False
    assert replay.id == proposal.id

    with pytest.raises(ApprovalNotFoundError):
        repository.get_proposal(owner="owner-b", proposal_id=proposal.id)
    approved = repository.transition(
        owner="owner-a",
        proposal_id=proposal.id,
        expected_version=1,
        target_status=ApprovalStatus.APPROVED,
        now=now,
    )
    assert approved.version == 2
    assert repository.transition(
        owner="owner-a",
        proposal_id=proposal.id,
        expected_version=1,
        target_status=ApprovalStatus.APPROVED,
        now=now,
    ) == approved
    with pytest.raises(ApprovalInvalidTransitionError):
        repository.transition(
            owner="owner-a",
            proposal_id=proposal.id,
            expected_version=2,
            target_status=ApprovalStatus.REJECTED,
            now=now,
        )

    consumed = repository.consume(
        owner="owner-a",
        proposal_id=proposal.id,
        expected_version=2,
        now=now,
    )
    assert consumed.version == 3
    assert consumed.consumed_at is not None
    with pytest.raises(ApprovalInvalidTransitionError):
        repository.consume(
            owner="owner-a",
            proposal_id=proposal.id,
            expected_version=3,
            now=now,
        )


def test_service_expires_after_restart_and_audits_bounded_metadata(database) -> None:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    clock_value = [now]
    audit = SecurityAuditRecorderStub()
    first = ApprovalService(
        ApprovalRepository(database),
        audit,
        clock=lambda: clock_value[0],
    )
    first.put_rule(
        enabled=True,
        risk_sources=[ApprovalRiskSource.RISK_VETO],
        expires_in_seconds=30,
        expected_version=0,
    )
    proposal = first._create_or_reuse(
        execution_id="durable-execution",
        context=_context(),
        expires_in_seconds=30,
        owner="local_admin",
    )

    clock_value[0] = now + timedelta(seconds=31)
    restarted = ApprovalService(
        ApprovalRepository(database),
        audit,
        clock=lambda: clock_value[0],
    )
    expired = restarted.get_proposal(proposal.id)
    assert expired.status is ApprovalStatus.EXPIRED
    assert expired.version == 2
    assert all("prompt" not in str(event).lower() for event in audit.attempts)
    assert all("credential" not in str(event).lower() for event in audit.completions)


def test_service_rejects_stale_decision_but_replays_same_terminal_decision(database) -> None:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    service = ApprovalService(
        ApprovalRepository(database),
        SecurityAuditRecorderStub(),
        clock=lambda: now,
    )
    proposal = service._create_or_reuse(
        execution_id="decision-execution",
        context=_context(),
        expires_in_seconds=300,
        owner="local_admin",
    )
    approved = service.decide(
        proposal.id,
        decision=ApprovalDecision.APPROVED,
        expected_version=1,
    )
    replayed = service.decide(
        proposal.id,
        decision=ApprovalDecision.APPROVED,
        expected_version=1,
    )
    assert replayed == approved
    with pytest.raises(ApprovalServiceVersionConflictError):
        service.put_rule(
            enabled=True,
            risk_sources=[ApprovalRiskSource.RISK_VETO],
            expires_in_seconds=300,
            expected_version=99,
        )


def test_expired_approval_never_consumes(database) -> None:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    repository = ApprovalRepository(database)
    proposal, _ = repository.create_or_get_proposal(
        proposal_id="d" * 32,
        owner="local_admin",
        risk_source=ApprovalRiskSource.RISK_DOWNGRADE,
        idempotency_key="e" * 64,
        execution_id="expired-execution",
        context=ApprovalContext(
            stock_code="600519",
            original_signal="hold",
            conservative_signal="sell",
            risk_source=ApprovalRiskSource.RISK_DOWNGRADE,
            risk_summary="A risk downgrade would make the signal conservative.",
        ),
        expires_at=now,
        now=now - timedelta(seconds=30),
    )
    approved = repository.transition(
        owner="local_admin",
        proposal_id=proposal.id,
        expected_version=1,
        target_status=ApprovalStatus.APPROVED,
        now=now - timedelta(seconds=1),
    )
    with pytest.raises(ApprovalInvalidTransitionError):
        repository.consume(
            owner="local_admin",
            proposal_id=proposal.id,
            expected_version=approved.version,
            now=now,
        )


def test_worker_poll_decision_and_one_shot_completion(database) -> None:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    audit = SecurityAuditRecorderStub()
    service: ApprovalService

    def decide_during_poll(_seconds: float) -> None:
        pending = service.list_proposals(status=ApprovalStatus.PENDING).items
        if pending:
            service.decide(
                pending[0].id,
                decision=ApprovalDecision.APPROVED,
                expected_version=pending[0].version,
            )

    service = ApprovalService(
        ApprovalRepository(database),
        audit,
        clock=lambda: now,
        sleeper=decide_during_poll,
        poll_interval_seconds=0.01,
    )
    service.put_rule(
        enabled=True,
        risk_sources=[ApprovalRiskSource.RISK_VETO],
        expires_in_seconds=300,
        expected_version=0,
    )
    consumed = service.await_risk_control_bypass(
        execution_id="worker-execution",
        context=_context(),
    )
    assert consumed is not None
    assert consumed.status is ApprovalStatus.APPROVED
    assert consumed.consumed_at is not None
    assert service.await_risk_control_bypass(
        execution_id="worker-execution",
        context=_context(),
    ) is None
    assert {
        event["event_type"] for event in audit.attempts
    } >= {
        "approval_proposal",
        "approval_transition",
        "approval_consume",
        "approval_completion",
    }


def test_concurrent_opposite_decisions_and_consumers_linearize(tmp_path) -> None:
    DatabaseManager.reset_instance()
    Config.reset_instance()
    database = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'concurrent.sqlite'}")
    repository = ApprovalRepository(database)
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    proposal, _ = repository.create_or_get_proposal(
        proposal_id="f" * 32,
        owner="local_admin",
        risk_source=ApprovalRiskSource.RISK_VETO,
        idempotency_key="1" * 64,
        execution_id="concurrent-execution",
        context=_context(),
        expires_at=now + timedelta(minutes=5),
        now=now,
    )
    barrier = threading.Barrier(2)

    def decide(target: ApprovalStatus):
        barrier.wait()
        try:
            return repository.transition(
                owner="local_admin",
                proposal_id=proposal.id,
                expected_version=1,
                target_status=target,
                now=now,
            )
        except (ApprovalInvalidTransitionError, ApprovalVersionConflictError) as exc:
            return exc

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(
                decide,
                (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED),
            ))
        winners = [item for item in results if not isinstance(item, Exception)]
        assert len(winners) == 1
        final = repository.get_proposal(
            owner="local_admin",
            proposal_id=proposal.id,
        )
        assert final.status in {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}
        assert final.version == 2

        if final.status is ApprovalStatus.APPROVED:
            consume_barrier = threading.Barrier(2)

            def consume():
                consume_barrier.wait()
                try:
                    return repository.consume(
                        owner="local_admin",
                        proposal_id=proposal.id,
                        expected_version=2,
                        now=now,
                    )
                except (ApprovalInvalidTransitionError, ApprovalVersionConflictError) as exc:
                    return exc

            with ThreadPoolExecutor(max_workers=2) as pool:
                consume_results = tuple(pool.map(lambda _: consume(), range(2)))
            assert len([
                item for item in consume_results if not isinstance(item, Exception)
            ]) == 1
            assert repository.get_proposal(
                owner="local_admin",
                proposal_id=proposal.id,
            ).version == 3
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def test_real_security_audit_records_transition_consume_and_completion(database) -> None:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    audit_repository = SecurityAuditRepository(database)
    service = ApprovalService(
        ApprovalRepository(database),
        SecurityAuditService(audit_repository),
        clock=lambda: now,
    )
    proposal = service._create_or_reuse(
        execution_id="audited-execution",
        context=_context(),
        expires_in_seconds=300,
        owner="local_admin",
    )
    approved = service.decide(
        proposal.id,
        decision=ApprovalDecision.APPROVED,
        expected_version=proposal.version,
    )
    consumed = service._consume(
        approved,
        execution_id="audited-execution",
        owner="local_admin",
    )
    assert consumed is not None

    events, total = audit_repository.list_events(page=1, page_size=100)
    assert total == 8
    assert {
        (event.event_type, event.phase)
        for event in events
    } == {
        ("approval_proposal", "attempt"),
        ("approval_proposal", "completion"),
        ("approval_transition", "attempt"),
        ("approval_transition", "completion"),
        ("approval_consume", "attempt"),
        ("approval_consume", "completion"),
        ("approval_completion", "attempt"),
        ("approval_completion", "completion"),
    }
    serialized = " ".join(str(event.metadata) for event in events).lower()
    assert "prompt" not in serialized
    assert "cookie" not in serialized
    assert "credential" not in serialized
    actors = {
        event.event_type: (event.actor.type, event.actor.id)
        for event in events
    }
    assert actors["approval_transition"] == ("administrator", "local_admin")
    for worker_event in (
        "approval_proposal",
        "approval_consume",
        "approval_completion",
    ):
        assert actors[worker_event] == ("runtime_principal", "approval_worker")


def test_audit_completion_failure_never_authorizes_bypass(database) -> None:
    class CompletionFailureAudit(SecurityAuditRecorderStub):
        def record_completion(self, **fields):
            super().record_completion(**fields)
            raise RuntimeError("audit unavailable")

    repository = ApprovalRepository(database)
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    repository.put_rule(
        owner="local_admin",
        enabled=True,
        risk_sources=[ApprovalRiskSource.RISK_VETO],
        expires_in_seconds=300,
        expected_version=0,
        now=now,
    )
    service = ApprovalService(
        repository,
        CompletionFailureAudit(),
        clock=lambda: now,
        sleeper=lambda _seconds: None,
    )

    assert service.await_risk_control_bypass(
        execution_id="audit-failure-execution",
        context=_context(),
    ) is None
    persisted = service.list_proposals().items
    assert len(persisted) == 1
    assert persisted[0].consumed_at is None


def test_filtered_pagination_converges_all_restart_overdue_rows(database) -> None:
    repository = ApprovalRepository(database)
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    for index in range(51):
        token = f"{index:064x}"
        repository.create_or_get_proposal(
            proposal_id=f"{index:032x}",
            owner="local_admin",
            risk_source=ApprovalRiskSource.RISK_VETO,
            idempotency_key=token,
            execution_id=f"restart-{index}",
            context=_context(),
            expires_at=now - timedelta(seconds=1),
            now=now - timedelta(minutes=1),
        )
    service = ApprovalService(
        repository,
        SecurityAuditRecorderStub(),
        clock=lambda: now,
    )

    pending = service.list_proposals(
        status=ApprovalStatus.PENDING,
        page=1,
        page_size=1,
    )
    expired = service.list_proposals(
        status=ApprovalStatus.EXPIRED,
        page=1,
        page_size=100,
    )

    assert pending.items == []
    assert pending.total == 0
    assert len(expired.items) == 51
    assert expired.total == 51
    assert {item.status for item in expired.items} == {ApprovalStatus.EXPIRED}


def test_decision_cas_cannot_approve_after_expiry_boundary(database) -> None:
    repository = ApprovalRepository(database)
    expiry = datetime(2026, 7, 25, 18, 0, tzinfo=timezone.utc)
    proposal, _ = repository.create_or_get_proposal(
        proposal_id="7" * 32,
        owner="local_admin",
        risk_source=ApprovalRiskSource.RISK_VETO,
        idempotency_key="8" * 64,
        execution_id="expiry-race",
        context=_context(),
        expires_at=expiry,
        now=expiry - timedelta(minutes=1),
    )
    clock_values = iter(
        (
            expiry - timedelta(microseconds=1),
            expiry + timedelta(microseconds=1),
            expiry + timedelta(microseconds=1),
            expiry + timedelta(microseconds=1),
        )
    )
    service = ApprovalService(
        repository,
        SecurityAuditRecorderStub(),
        clock=lambda: next(clock_values),
    )

    with pytest.raises(ApprovalServiceInvalidTransitionError, match="expired"):
        service.decide(
            proposal.id,
            decision=ApprovalDecision.APPROVED,
            expected_version=proposal.version,
        )
    persisted = repository.get_proposal(
        owner="local_admin",
        proposal_id=proposal.id,
    )
    assert persisted.status is ApprovalStatus.EXPIRED
    assert persisted.version == 2


@pytest.mark.parametrize("boundary", ["cancelled", "deadline"])
def test_boundary_wins_when_approval_arrives_during_poll(
    database,
    boundary: str,
) -> None:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    boundary_reached = [False]
    service: ApprovalService

    def approve_during_sleep(_seconds: float) -> None:
        pending = service.list_proposals(status=ApprovalStatus.PENDING).items
        service.decide(
            pending[0].id,
            decision=ApprovalDecision.APPROVED,
            expected_version=pending[0].version,
        )
        boundary_reached[0] = True

    service = ApprovalService(
        ApprovalRepository(database),
        SecurityAuditRecorderStub(),
        clock=lambda: now,
        sleeper=approve_during_sleep,
        poll_interval_seconds=0.01,
    )
    service.put_rule(
        enabled=True,
        risk_sources=[ApprovalRiskSource.RISK_VETO],
        expires_in_seconds=300,
        expected_version=0,
    )

    consumed = service.await_risk_control_bypass(
        execution_id=f"{boundary}-during-poll",
        context=_context(),
        cancelled_check=(
            (lambda: boundary_reached[0]) if boundary == "cancelled" else None
        ),
        stop_waiting_check=(
            (lambda: boundary_reached[0]) if boundary == "deadline" else None
        ),
    )

    assert consumed is None
    proposal = service.list_proposals().items[0]
    assert proposal.status is ApprovalStatus.APPROVED
    assert proposal.consumed_at is None


def test_runtime_cancellation_uses_worker_audit_identity(database) -> None:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    audit = SecurityAuditRecorderStub()
    service = ApprovalService(
        ApprovalRepository(database),
        audit,
        clock=lambda: now,
    )
    service.put_rule(
        enabled=True,
        risk_sources=[ApprovalRiskSource.RISK_VETO],
        expires_in_seconds=300,
        expected_version=0,
    )

    consumed = service.await_risk_control_bypass(
        execution_id="cancelled-before-poll",
        context=_context(),
        cancelled_check=lambda: True,
    )

    assert consumed is None
    proposal = service.list_proposals().items[0]
    assert proposal.status is ApprovalStatus.CANCELLED
    cancellation_attempt = next(
        event for event in audit.attempts
        if event["action"] == "cancel_approval"
    )
    cancellation_completion = next(
        event for event in audit.completions
        if event["action"] == "cancel_approval"
    )
    assert cancellation_attempt["actor_type"] == "runtime_principal"
    assert cancellation_attempt["actor_id"] == "approval_worker"
    assert cancellation_completion["actor_type"] == "runtime_principal"
    assert cancellation_completion["actor_id"] == "approval_worker"
    assert cancellation_completion["reason_code"] == "proposal_cancelled"


def test_storage_failures_receive_denied_audit_completions() -> None:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    audit = SecurityAuditRecorderStub()
    repository = MagicMock()
    repository.create_or_get_proposal.side_effect = OperationalError(
        "insert",
        {},
        RuntimeError("database locked"),
    )
    service = ApprovalService(
        repository,
        audit,
        clock=lambda: now,
    )

    with pytest.raises(OperationalError):
        service._create_or_reuse(
            execution_id="storage-failure",
            context=_context(),
            expires_in_seconds=300,
            owner="local_admin",
        )

    assert len(audit.attempts) == 1
    assert len(audit.completions) == 1
    assert audit.completions[0]["reason_code"] == "proposal_storage_failure"
    assert audit.completions[0]["outcome"] == "denied"


def test_rule_validation_rejects_duplicate_risk_sources_before_write(database) -> None:
    repository = ApprovalRepository(database)
    service = ApprovalService(
        repository,
        SecurityAuditRecorderStub(),
        clock=lambda: datetime(2026, 7, 25, tzinfo=timezone.utc),
    )

    with pytest.raises(ValidationError):
        service.put_rule(
            enabled=True,
            risk_sources=[
                ApprovalRiskSource.RISK_VETO,
                ApprovalRiskSource.RISK_VETO,
            ],
            expires_in_seconds=300,
            expected_version=0,
        )
    assert repository.get_rule(owner="local_admin").version == 0
