# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""HITL backend regression anchors (Lane 5 / human-approvals ops semantics).

Offline and deterministic: in-memory SQLite, no network, no live LLM.
Pins create → decide → audit trail and pipeline-deadline fail-closed waiting.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.config import Config
from src.repositories.approval_repo import ApprovalRepository
from src.repositories.security_audit_repo import SecurityAuditRepository
from src.schemas.approvals import (
    ApprovalContext,
    ApprovalDecision,
    ApprovalRiskSource,
    ApprovalStatus,
)
from src.services.approval_service import ApprovalService
from src.services.security_audit_service import SecurityAuditService
from src.storage import DatabaseManager


@pytest.fixture
def database():
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url="sqlite:///:memory:")
    yield manager
    DatabaseManager.reset_instance()
    Config.reset_instance()


def _context(
    *,
    risk_source: ApprovalRiskSource = ApprovalRiskSource.RISK_VETO,
) -> ApprovalContext:
    return ApprovalContext(
        stock_code="AAPL",
        original_signal="buy",
        conservative_signal="hold",
        risk_source=risk_source,
        risk_summary="A risk veto would replace the original buy signal.",
    )


def test_regression_create_approve_consume_records_audit_trail(database) -> None:
    """Anchor: create proposal → approve → consume with attributable audit events."""
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    audit_repository = SecurityAuditRepository(database)
    service = ApprovalService(
        ApprovalRepository(database),
        SecurityAuditService(audit_repository),
        clock=lambda: now,
    )

    proposal = service._create_or_reuse(
        execution_id="regression-approve-execution",
        context=_context(),
        expires_in_seconds=300,
        owner="local_admin",
    )
    assert proposal.status is ApprovalStatus.PENDING
    assert proposal.version == 1
    assert proposal.expires_at == now + timedelta(seconds=300)

    approved = service.decide(
        proposal.id,
        decision=ApprovalDecision.APPROVED,
        expected_version=proposal.version,
        owner="local_admin",
    )
    assert approved.status is ApprovalStatus.APPROVED
    assert approved.version == 2

    consumed = service._consume(
        approved,
        execution_id="regression-approve-execution",
        owner="local_admin",
    )
    assert consumed is not None
    assert consumed.consumed_at is not None

    events, total = audit_repository.list_events(page=1, page_size=100)
    assert total >= 6
    pairs = {(event.event_type, event.phase) for event in events}
    assert ("approval_proposal", "attempt") in pairs
    assert ("approval_proposal", "completion") in pairs
    assert ("approval_transition", "attempt") in pairs
    assert ("approval_transition", "completion") in pairs
    assert ("approval_consume", "attempt") in pairs
    assert ("approval_consume", "completion") in pairs

    transition_actors = {
        (event.actor.type, event.actor.id)
        for event in events
        if event.event_type == "approval_transition"
    }
    assert ("administrator", "local_admin") in transition_actors
    worker_actors = {
        (event.actor.type, event.actor.id)
        for event in events
        if event.event_type in {"approval_proposal", "approval_consume"}
    }
    assert ("runtime_principal", "approval_worker") in worker_actors

    serialized = " ".join(str(event.metadata) for event in events).lower()
    assert "prompt" not in serialized
    assert "cookie" not in serialized


def test_regression_create_reject_leaves_bypass_unauthorized_with_audit(
    database,
) -> None:
    """Anchor: reject is terminal; await path cannot authorize a bypass."""
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    repository = ApprovalRepository(database)
    audit_repository = SecurityAuditRepository(database)
    repository.put_rule(
        owner="local_admin",
        enabled=True,
        risk_sources=[ApprovalRiskSource.RISK_VETO],
        expires_in_seconds=300,
        expected_version=0,
        now=now,
    )

    decided = {"done": False}

    def decide_on_first_sleep(_seconds: float) -> None:
        if decided["done"]:
            return
        decided["done"] = True
        items = service.list_proposals(
            status=ApprovalStatus.PENDING, page=1, page_size=10
        ).items
        assert len(items) == 1
        service.decide(
            items[0].id,
            decision=ApprovalDecision.REJECTED,
            expected_version=items[0].version,
            owner="local_admin",
        )

    service = ApprovalService(
        repository,
        SecurityAuditService(audit_repository),
        clock=lambda: now,
        sleeper=decide_on_first_sleep,
        poll_interval_seconds=1.0,
    )

    result = service.await_risk_control_bypass(
        execution_id="regression-reject-execution",
        context=_context(),
        owner="local_admin",
    )
    assert result is None

    final = service.list_proposals(
        status=ApprovalStatus.REJECTED, page=1, page_size=10
    ).items
    assert len(final) == 1
    assert final[0].status is ApprovalStatus.REJECTED
    assert final[0].consumed_at is None

    events, _total = audit_repository.list_events(page=1, page_size=100)
    transition_completions = [
        event
        for event in events
        if event.event_type == "approval_transition" and event.phase == "completion"
    ]
    assert any(
        event.reason_code == "proposal_rejected" for event in transition_completions
    )


def test_regression_pipeline_deadline_stops_wait_without_authorizing(database) -> None:
    """Anchor: orchestrator deadline stop_waiting fails closed while still pending."""
    now = datetime(2026, 7, 26, tzinfo=timezone.utc)
    repository = ApprovalRepository(database)
    repository.put_rule(
        owner="local_admin",
        enabled=True,
        risk_sources=[ApprovalRiskSource.RISK_VETO],
        expires_in_seconds=300,
        expected_version=0,
        now=now,
    )

    # Fixed clock: proposal does not expire during the wait loop.
    service = ApprovalService(
        repository,
        MagicMock(),
        clock=lambda: now,
        sleeper=lambda _seconds: None,
        poll_interval_seconds=1.0,
    )

    calls = {"n": 0}

    def stop_after_one_poll() -> bool:
        calls["n"] += 1
        # First check may run before sleep; stop on second invocation to simulate
        # deadline hit during polling (pipeline budget exhausted).
        return calls["n"] >= 2

    result = service.await_risk_control_bypass(
        execution_id="regression-deadline-execution",
        context=_context(),
        owner="local_admin",
        stop_waiting_check=stop_after_one_poll,
    )
    assert result is None

    pending = service.list_proposals(
        status=ApprovalStatus.PENDING, page=1, page_size=10
    ).items
    assert len(pending) == 1
    assert pending[0].status is ApprovalStatus.PENDING
    assert pending[0].consumed_at is None
    # Lifetime still future: deadline abort is independent of expires_at.
    assert pending[0].expires_at > now
