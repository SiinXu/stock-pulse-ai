# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-safe Human-in-the-Loop approval gate service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import time
from typing import Callable, Optional

from sqlalchemy.exc import SQLAlchemyError

from src.repositories.approval_repo import (
    ApprovalExpiredError,
    ApprovalInvalidTransitionError,
    ApprovalNotFoundError,
    ApprovalRepository,
    ApprovalRepositoryError,
    ApprovalVersionConflictError,
)
from src.schemas.approvals import (
    APPROVAL_ACTION_RISK_CONTROL_BYPASS,
    APPROVAL_MAX_PAGE_SIZE,
    LOCAL_ADMIN_OWNER,
    ApprovalContext,
    ApprovalDecision,
    ApprovalProposal,
    ApprovalProposalPage,
    ApprovalRiskSource,
    ApprovalRule,
    ApprovalStatus,
)
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    require_security_audit_recorder,
)
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)
_WORKER_ACTOR_TYPE = "runtime_principal"
_WORKER_ACTOR_ID = "approval_worker"


class ApprovalServiceError(RuntimeError):
    error_code = "approval_operation_failed"


class ApprovalServiceNotFoundError(ApprovalServiceError):
    error_code = "approval_not_found"


class ApprovalServiceVersionConflictError(ApprovalServiceError):
    error_code = "approval_version_conflict"

    def __init__(self, current_version: int):
        self.current_version = current_version
        super().__init__("Approval version conflict")


class ApprovalServiceInvalidTransitionError(ApprovalServiceError):
    error_code = "approval_invalid_transition"


class ApprovalService:
    """Coordinates persistence, expiry, one-time consumption, and audit."""

    def __init__(
        self,
        repository: Optional[ApprovalRepository] = None,
        audit: Optional[SecurityAuditRecorder] = None,
        *,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("approval poll interval must be positive")
        self._repository = repository or ApprovalRepository()
        self._audit = require_security_audit_recorder(audit or SecurityAuditService())
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sleep = sleeper or time.sleep
        self._poll_interval_seconds = float(poll_interval_seconds)

    def get_rule(self, *, owner: str = LOCAL_ADMIN_OWNER) -> ApprovalRule:
        return self._repository.get_rule(owner=owner)

    def put_rule(
        self,
        *,
        enabled: bool,
        risk_sources: list[ApprovalRiskSource],
        expires_in_seconds: int,
        expected_version: int,
        owner: str = LOCAL_ADMIN_OWNER,
    ) -> ApprovalRule:
        validated = ApprovalRule(
            owner=owner,
            enabled=enabled,
            risk_sources=risk_sources,
            expires_in_seconds=expires_in_seconds,
            version=expected_version,
        )
        correlation = self._audit_attempt(
            event_type="approval_rule",
            execution_id=f"approval-rule:{owner}",
            action="update_approval_rule",
            target_type="approval_rule",
            target_id=APPROVAL_ACTION_RISK_CONTROL_BYPASS,
            metadata={"expected_version": expected_version},
        )
        try:
            result = self._repository.put_rule(
                owner=owner,
                enabled=validated.enabled,
                risk_sources=validated.risk_sources,
                expires_in_seconds=validated.expires_in_seconds,
                expected_version=validated.version,
                now=self._now(),
            )
        except ApprovalVersionConflictError as exc:
            self._audit_completion(
                correlation=correlation,
                event_type="approval_rule",
                execution_id=f"approval-rule:{owner}",
                action="update_approval_rule",
                target_type="approval_rule",
                target_id=APPROVAL_ACTION_RISK_CONTROL_BYPASS,
                outcome="rejected",
                reason_code="version_conflict",
                metadata={"current_version": exc.current_version},
            )
            raise ApprovalServiceVersionConflictError(exc.current_version) from exc
        except (ApprovalRepositoryError, SQLAlchemyError):
            self._audit_completion(
                correlation=correlation,
                event_type="approval_rule",
                execution_id=f"approval-rule:{owner}",
                action="update_approval_rule",
                target_type="approval_rule",
                target_id=APPROVAL_ACTION_RISK_CONTROL_BYPASS,
                outcome="rejected",
                reason_code="rule_storage_failure",
                metadata={},
            )
            raise
        self._audit_completion(
            correlation=correlation,
            event_type="approval_rule",
            execution_id=f"approval-rule:{owner}",
            action="update_approval_rule",
            target_type="approval_rule",
            target_id=APPROVAL_ACTION_RISK_CONTROL_BYPASS,
            outcome="success",
            reason_code="rule_updated",
            metadata={"version": result.version, "enabled": result.enabled},
        )
        return result

    def list_proposals(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        status: ApprovalStatus | None = None,
        owner: str = LOCAL_ADMIN_OWNER,
    ) -> ApprovalProposalPage:
        safe_page = max(1, int(page))
        safe_size = max(1, min(int(page_size), APPROVAL_MAX_PAGE_SIZE))
        self._expire_due_pending(owner=owner)
        items, total = self._repository.list_proposals(
            owner=owner,
            page=safe_page,
            page_size=safe_size,
            status=status,
        )
        return ApprovalProposalPage(
            items=items,
            page=safe_page,
            page_size=safe_size,
            total=total,
        )

    def get_proposal(
        self,
        proposal_id: str,
        *,
        owner: str = LOCAL_ADMIN_OWNER,
    ) -> ApprovalProposal:
        try:
            proposal = self._repository.get_proposal(
                owner=owner,
                proposal_id=proposal_id,
            )
        except ApprovalNotFoundError as exc:
            raise ApprovalServiceNotFoundError("Approval proposal not found") from exc
        return self._expire_if_due(proposal, owner=owner)

    def decide(
        self,
        proposal_id: str,
        *,
        decision: ApprovalDecision,
        expected_version: int,
        owner: str = LOCAL_ADMIN_OWNER,
    ) -> ApprovalProposal:
        proposal = self.get_proposal(proposal_id, owner=owner)
        target = ApprovalStatus(decision.value)
        if proposal.status is target:
            return proposal
        correlation = self._audit_attempt(
            event_type="approval_transition",
            execution_id=f"approval-decision:{proposal_id}",
            action="decide_approval",
            target_type="approval_proposal",
            target_id=proposal_id,
            metadata={
                "expected_version": expected_version,
                "target_status": target.value,
            },
        )
        try:
            result = self._repository.transition(
                owner=owner,
                proposal_id=proposal_id,
                expected_version=expected_version,
                target_status=target,
                now=self._now(),
            )
        except ApprovalExpiredError as exc:
            self._record_rejected_transition(
                correlation,
                proposal_id,
                "proposal_expired",
                {},
            )
            current = self._repository.get_proposal(
                owner=owner,
                proposal_id=proposal_id,
            )
            self._expire_if_due(current, owner=owner)
            raise ApprovalServiceInvalidTransitionError(str(exc)) from exc
        except ApprovalVersionConflictError as exc:
            self._record_rejected_transition(
                correlation,
                proposal_id,
                "version_conflict",
                {"current_version": exc.current_version},
            )
            raise ApprovalServiceVersionConflictError(exc.current_version) from exc
        except ApprovalInvalidTransitionError as exc:
            self._record_rejected_transition(
                correlation,
                proposal_id,
                "invalid_transition",
                {},
            )
            raise ApprovalServiceInvalidTransitionError(str(exc)) from exc
        except (ApprovalRepositoryError, SQLAlchemyError):
            self._record_rejected_transition(
                correlation,
                proposal_id,
                "transition_storage_failure",
                {},
            )
            raise
        self._audit_completion(
            correlation=correlation,
            event_type="approval_transition",
            execution_id=f"approval-decision:{proposal_id}",
            action="decide_approval",
            target_type="approval_proposal",
            target_id=proposal_id,
            outcome="accepted",
            reason_code=f"proposal_{target.value}",
            metadata={"version": result.version, "status": result.status.value},
        )
        return result

    def await_risk_control_bypass(
        self,
        *,
        execution_id: str,
        context: ApprovalContext,
        cancelled_check: Callable[[], bool] | None = None,
        stop_waiting_check: Callable[[], bool] | None = None,
        owner: str = LOCAL_ADMIN_OWNER,
    ) -> ApprovalProposal | None:
        """Return a consumed approved proposal, or ``None`` conservatively."""
        try:
            rule = self.get_rule(owner=owner)
            if not rule.enabled or context.risk_source not in rule.risk_sources:
                return None
            proposal = self._create_or_reuse(
                execution_id=execution_id,
                context=context,
                expires_in_seconds=rule.expires_in_seconds,
                owner=owner,
            )
            while True:
                proposal = self._expire_if_due(proposal, owner=owner)
                if cancelled_check is not None and cancelled_check():
                    if proposal.status is ApprovalStatus.PENDING:
                        self._cancel_pending(proposal, owner=owner)
                    return None
                if stop_waiting_check is not None and stop_waiting_check():
                    return None
                if proposal.status is ApprovalStatus.APPROVED:
                    return self._consume(proposal, execution_id=execution_id, owner=owner)
                if proposal.status is not ApprovalStatus.PENDING:
                    return None
                remaining = (proposal.expires_at - self._now()).total_seconds()
                if remaining <= 0:
                    proposal = self._expire_if_due(proposal, owner=owner)
                    continue
                self._sleep(min(self._poll_interval_seconds, remaining))
                proposal = self._repository.get_proposal(
                    owner=owner,
                    proposal_id=proposal.id,
                )
        except (
            ApprovalRepositoryError,
            ApprovalServiceError,
        ):
            return None
        except Exception as exc:  # broad-exception: fallback_recorded - Log the unknown gate failure and preserve the caller's conservative risk result.
            log_safe_exception(
                logger,
                "Risk-control approval service failed closed",
                exc,
                error_code="approval_service_failed_closed",
            )
            # The runtime boundary is deliberately fail-safe: an unknown
            # storage/audit/clock failure must retain the conservative result.
            return None

    def _create_or_reuse(
        self,
        *,
        execution_id: str,
        context: ApprovalContext,
        expires_in_seconds: int,
        owner: str,
    ) -> ApprovalProposal:
        canonical = json.dumps(
            {
                "action": APPROVAL_ACTION_RISK_CONTROL_BYPASS,
                "context": context.model_dump(mode="json"),
                "execution_id": execution_id,
                "owner": owner,
            },
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        idempotency_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        proposal_id = idempotency_key[:32]
        now = self._now()
        correlation = self._audit_attempt(
            event_type="approval_proposal",
            execution_id=execution_id,
            action="create_approval_proposal",
            target_type="approval_proposal",
            target_id=proposal_id,
            metadata={"risk_source": context.risk_source.value},
            actor_type=_WORKER_ACTOR_TYPE,
            actor_id=_WORKER_ACTOR_ID,
        )
        try:
            proposal, created = self._repository.create_or_get_proposal(
                proposal_id=proposal_id,
                owner=owner,
                risk_source=context.risk_source,
                idempotency_key=idempotency_key,
                execution_id=execution_id,
                context=context,
                expires_at=now + timedelta(seconds=expires_in_seconds),
                now=now,
            )
        except (ApprovalRepositoryError, SQLAlchemyError):
            self._audit_completion(
                correlation=correlation,
                event_type="approval_proposal",
                execution_id=execution_id,
                action="create_approval_proposal",
                target_type="approval_proposal",
                target_id=proposal_id,
                outcome="denied",
                reason_code="proposal_storage_failure",
                metadata={},
                actor_type=_WORKER_ACTOR_TYPE,
                actor_id=_WORKER_ACTOR_ID,
            )
            raise
        self._audit_completion(
            correlation=correlation,
            event_type="approval_proposal",
            execution_id=execution_id,
            action="create_approval_proposal",
            target_type="approval_proposal",
            target_id=proposal.id,
            outcome="accepted",
            reason_code="proposal_created" if created else "proposal_reused",
            metadata={"status": proposal.status.value, "version": proposal.version},
            actor_type=_WORKER_ACTOR_TYPE,
            actor_id=_WORKER_ACTOR_ID,
        )
        return proposal

    def _expire_if_due(
        self,
        proposal: ApprovalProposal,
        *,
        owner: str,
    ) -> ApprovalProposal:
        if (
            proposal.status is not ApprovalStatus.PENDING
            or proposal.expires_at > self._now()
        ):
            return proposal
        correlation = self._audit_attempt(
            event_type="approval_transition",
            execution_id=f"approval-expiry:{proposal.id}",
            action="expire_approval",
            target_type="approval_proposal",
            target_id=proposal.id,
            metadata={"expected_version": proposal.version},
            actor_type=_WORKER_ACTOR_TYPE,
            actor_id=_WORKER_ACTOR_ID,
        )
        try:
            expired = self._repository.transition(
                owner=owner,
                proposal_id=proposal.id,
                expected_version=proposal.version,
                target_status=ApprovalStatus.EXPIRED,
                now=self._now(),
            )
        except ApprovalVersionConflictError as exc:
            self._audit_completion(
                correlation=correlation,
                event_type="approval_transition",
                execution_id=f"approval-expiry:{proposal.id}",
                action="expire_approval",
                target_type="approval_proposal",
                target_id=proposal.id,
                outcome="rejected",
                reason_code="version_conflict",
                metadata={"current_version": exc.current_version},
                actor_type=_WORKER_ACTOR_TYPE,
                actor_id=_WORKER_ACTOR_ID,
            )
            return self._repository.get_proposal(
                owner=owner,
                proposal_id=proposal.id,
            )
        except (ApprovalRepositoryError, SQLAlchemyError):
            self._audit_completion(
                correlation=correlation,
                event_type="approval_transition",
                execution_id=f"approval-expiry:{proposal.id}",
                action="expire_approval",
                target_type="approval_proposal",
                target_id=proposal.id,
                outcome="denied",
                reason_code="expiry_storage_failure",
                metadata={},
                actor_type=_WORKER_ACTOR_TYPE,
                actor_id=_WORKER_ACTOR_ID,
            )
            raise
        self._audit_completion(
            correlation=correlation,
            event_type="approval_transition",
            execution_id=f"approval-expiry:{proposal.id}",
            action="expire_approval",
            target_type="approval_proposal",
            target_id=proposal.id,
            outcome="accepted",
            reason_code="proposal_expired",
            metadata={"version": expired.version},
            actor_type=_WORKER_ACTOR_TYPE,
            actor_id=_WORKER_ACTOR_ID,
        )
        return expired

    def _expire_due_pending(self, *, owner: str) -> None:
        """Converge all overdue pending rows before filtering or pagination."""
        due_at = self._now()
        while True:
            batch = self._repository.list_due_pending(
                owner=owner,
                due_at=due_at,
                limit=100,
            )
            if not batch:
                return
            for proposal in batch:
                self._expire_if_due(proposal, owner=owner)

    def _cancel_pending(self, proposal: ApprovalProposal, *, owner: str) -> None:
        correlation = self._audit_attempt(
            event_type="approval_transition",
            execution_id=f"approval-cancel:{proposal.id}",
            action="cancel_approval",
            target_type="approval_proposal",
            target_id=proposal.id,
            metadata={"expected_version": proposal.version},
            actor_type=_WORKER_ACTOR_TYPE,
            actor_id=_WORKER_ACTOR_ID,
        )
        try:
            cancelled = self._repository.transition(
                owner=owner,
                proposal_id=proposal.id,
                expected_version=proposal.version,
                target_status=ApprovalStatus.CANCELLED,
                now=self._now(),
            )
        except (
            ApprovalExpiredError,
            ApprovalInvalidTransitionError,
            ApprovalNotFoundError,
            ApprovalVersionConflictError,
        ) as exc:
            self._audit_completion(
                correlation=correlation,
                event_type="approval_transition",
                execution_id=f"approval-cancel:{proposal.id}",
                action="cancel_approval",
                target_type="approval_proposal",
                target_id=proposal.id,
                outcome="rejected",
                reason_code="cancellation_conflict",
                metadata={},
                actor_type=_WORKER_ACTOR_TYPE,
                actor_id=_WORKER_ACTOR_ID,
            )
            return
        except (ApprovalRepositoryError, SQLAlchemyError):
            self._audit_completion(
                correlation=correlation,
                event_type="approval_transition",
                execution_id=f"approval-cancel:{proposal.id}",
                action="cancel_approval",
                target_type="approval_proposal",
                target_id=proposal.id,
                outcome="denied",
                reason_code="cancellation_storage_failure",
                metadata={},
                actor_type=_WORKER_ACTOR_TYPE,
                actor_id=_WORKER_ACTOR_ID,
            )
            return
        self._audit_completion(
            correlation=correlation,
            event_type="approval_transition",
            execution_id=f"approval-cancel:{proposal.id}",
            action="cancel_approval",
            target_type="approval_proposal",
            target_id=proposal.id,
            outcome="accepted",
            reason_code="proposal_cancelled",
            metadata={"version": cancelled.version},
            actor_type=_WORKER_ACTOR_TYPE,
            actor_id=_WORKER_ACTOR_ID,
        )

    def _consume(
        self,
        proposal: ApprovalProposal,
        *,
        execution_id: str,
        owner: str,
    ) -> ApprovalProposal | None:
        correlation = self._audit_attempt(
            event_type="approval_consume",
            execution_id=execution_id,
            action="consume_approval",
            target_type="approval_proposal",
            target_id=proposal.id,
            metadata={"expected_version": proposal.version},
            actor_type=_WORKER_ACTOR_TYPE,
            actor_id=_WORKER_ACTOR_ID,
        )
        try:
            consumed = self._repository.consume(
                owner=owner,
                proposal_id=proposal.id,
                expected_version=proposal.version,
                now=self._now(),
            )
        except (
            ApprovalInvalidTransitionError,
            ApprovalVersionConflictError,
            ApprovalNotFoundError,
        ):
            self._audit_completion(
                correlation=correlation,
                event_type="approval_consume",
                execution_id=execution_id,
                action="consume_approval",
                target_type="approval_proposal",
                target_id=proposal.id,
                outcome="denied",
                reason_code="consume_rejected",
                metadata={},
                actor_type=_WORKER_ACTOR_TYPE,
                actor_id=_WORKER_ACTOR_ID,
            )
            return None
        except (ApprovalRepositoryError, SQLAlchemyError):
            self._audit_completion(
                correlation=correlation,
                event_type="approval_consume",
                execution_id=execution_id,
                action="consume_approval",
                target_type="approval_proposal",
                target_id=proposal.id,
                outcome="denied",
                reason_code="consume_storage_failure",
                metadata={},
                actor_type=_WORKER_ACTOR_TYPE,
                actor_id=_WORKER_ACTOR_ID,
            )
            raise
        self._audit_completion(
            correlation=correlation,
            event_type="approval_consume",
            execution_id=execution_id,
            action="consume_approval",
            target_type="approval_proposal",
            target_id=proposal.id,
            outcome="success",
            reason_code="approval_consumed",
            metadata={"version": consumed.version},
            actor_type=_WORKER_ACTOR_TYPE,
            actor_id=_WORKER_ACTOR_ID,
        )
        completion = self._audit_attempt(
            event_type="approval_completion",
            execution_id=execution_id,
            action=APPROVAL_ACTION_RISK_CONTROL_BYPASS,
            target_type="approval_proposal",
            target_id=proposal.id,
            metadata={"risk_source": proposal.context.risk_source.value},
            actor_type=_WORKER_ACTOR_TYPE,
            actor_id=_WORKER_ACTOR_ID,
        )
        self._audit_completion(
            correlation=completion,
            event_type="approval_completion",
            execution_id=execution_id,
            action=APPROVAL_ACTION_RISK_CONTROL_BYPASS,
            target_type="approval_proposal",
            target_id=proposal.id,
            outcome="success",
            reason_code="bypass_authorized",
            metadata={"version": consumed.version},
            actor_type=_WORKER_ACTOR_TYPE,
            actor_id=_WORKER_ACTOR_ID,
        )
        return consumed

    def _record_rejected_transition(
        self,
        correlation: str,
        proposal_id: str,
        reason: str,
        metadata: dict,
    ) -> None:
        self._audit_completion(
            correlation=correlation,
            event_type="approval_transition",
            execution_id=f"approval-decision:{proposal_id}",
            action="decide_approval",
            target_type="approval_proposal",
            target_id=proposal_id,
            outcome="rejected",
            reason_code=reason,
            metadata=metadata,
        )

    def _audit_attempt(
        self,
        *,
        actor_type: str = "administrator",
        actor_id: str = LOCAL_ADMIN_OWNER,
        **fields,
    ) -> str:
        correlation = SecurityAuditService.new_correlation_id()
        self._audit.record_attempt(
            actor_type=actor_type,
            actor_id=actor_id,
            correlation_id=correlation,
            **fields,
        )
        return correlation

    def _audit_completion(
        self,
        *,
        correlation: str,
        actor_type: str = "administrator",
        actor_id: str = LOCAL_ADMIN_OWNER,
        **fields,
    ) -> None:
        self._audit.record_completion(
            actor_type=actor_type,
            actor_id=actor_id,
            correlation_id=correlation,
            **fields,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("approval clock must return a timezone-aware datetime")
        return value.astimezone(timezone.utc)
