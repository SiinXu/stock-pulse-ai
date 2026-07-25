# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Atomic persistence operations for Human-in-the-Loop approvals."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from src.schemas.approvals import (
    APPROVAL_ACTION_RISK_CONTROL_BYPASS,
    ApprovalContext,
    ApprovalProposal,
    ApprovalRiskSource,
    ApprovalRule,
    ApprovalStatus,
    DEFAULT_APPROVAL_EXPIRES_IN_SECONDS,
)
from src.storage import (
    ApprovalProposalRecord,
    ApprovalRuleRecord,
    DatabaseManager,
)


class ApprovalRepositoryError(RuntimeError):
    """Base persistence-contract error."""


class ApprovalNotFoundError(ApprovalRepositoryError):
    """The requested owner-scoped proposal does not exist."""


class ApprovalVersionConflictError(ApprovalRepositoryError):
    """A CAS mutation used a stale or otherwise invalid version."""

    def __init__(self, current_version: int):
        self.current_version = current_version
        super().__init__("Approval version conflict")


class ApprovalInvalidTransitionError(ApprovalRepositoryError):
    """A terminal or consumed proposal cannot perform the requested transition."""


class ApprovalExpiredError(ApprovalInvalidTransitionError):
    """A decision lost the race against the proposal expiry boundary."""


class ApprovalStorageCorruptionError(ApprovalRepositoryError):
    """Persisted approval state violates the strict contract."""


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("approval timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class ApprovalRepository:
    """Owner-scoped rule and one-shot proposal repository."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    def get_rule(
        self,
        *,
        owner: str,
        action: str = APPROVAL_ACTION_RISK_CONTROL_BYPASS,
    ) -> ApprovalRule:
        with self.db.get_session() as session:
            row = session.execute(
                select(ApprovalRuleRecord).where(
                    ApprovalRuleRecord.owner_id == owner,
                    ApprovalRuleRecord.action == action,
                )
            ).scalar_one_or_none()
            if row is None:
                return ApprovalRule(
                    owner=owner,
                    action=action,
                    enabled=False,
                    risk_sources=[
                        ApprovalRiskSource.RISK_VETO,
                        ApprovalRiskSource.RISK_DOWNGRADE,
                    ],
                    expires_in_seconds=DEFAULT_APPROVAL_EXPIRES_IN_SECONDS,
                    version=0,
                    updated_at=None,
                )
            return self._rule(row)

    def put_rule(
        self,
        *,
        owner: str,
        enabled: bool,
        risk_sources: list[ApprovalRiskSource],
        expires_in_seconds: int,
        expected_version: int,
        now: datetime,
        action: str = APPROVAL_ACTION_RISK_CONTROL_BYPASS,
    ) -> ApprovalRule:
        now_naive = _utc_naive(now)
        encoded_sources = json.dumps(
            [source.value for source in risk_sources],
            separators=(",", ":"),
        )
        with self.db.get_session() as session:
            row = session.execute(
                select(ApprovalRuleRecord).where(
                    ApprovalRuleRecord.owner_id == owner,
                    ApprovalRuleRecord.action == action,
                )
            ).scalar_one_or_none()
            current_version = 0 if row is None else int(row.version)
            if current_version != expected_version:
                raise ApprovalVersionConflictError(current_version)
            if row is None:
                row = ApprovalRuleRecord(
                    owner_id=owner,
                    action=action,
                    enabled=enabled,
                    risk_sources_json=encoded_sources,
                    expires_in_seconds=expires_in_seconds,
                    version=1,
                    created_at=now_naive,
                    updated_at=now_naive,
                )
                session.add(row)
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    current = session.execute(
                        select(ApprovalRuleRecord).where(
                            ApprovalRuleRecord.owner_id == owner,
                            ApprovalRuleRecord.action == action,
                        )
                    ).scalar_one()
                    raise ApprovalVersionConflictError(int(current.version)) from None
            else:
                result = session.execute(
                    update(ApprovalRuleRecord)
                    .where(
                        ApprovalRuleRecord.id == row.id,
                        ApprovalRuleRecord.version == expected_version,
                    )
                    .values(
                        enabled=enabled,
                        risk_sources_json=encoded_sources,
                        expires_in_seconds=expires_in_seconds,
                        version=expected_version + 1,
                        updated_at=now_naive,
                    )
                )
                if int(result.rowcount or 0) != 1:
                    session.rollback()
                    current = session.execute(
                        select(ApprovalRuleRecord).where(
                            ApprovalRuleRecord.owner_id == owner,
                            ApprovalRuleRecord.action == action,
                        )
                    ).scalar_one()
                    raise ApprovalVersionConflictError(int(current.version))
                session.commit()
            refreshed = session.execute(
                select(ApprovalRuleRecord).where(
                    ApprovalRuleRecord.owner_id == owner,
                    ApprovalRuleRecord.action == action,
                )
            ).scalar_one()
            return self._rule(refreshed)

    def create_or_get_proposal(
        self,
        *,
        proposal_id: str,
        owner: str,
        risk_source: ApprovalRiskSource,
        idempotency_key: str,
        execution_id: str,
        context: ApprovalContext,
        expires_at: datetime,
        now: datetime,
        action: str = APPROVAL_ACTION_RISK_CONTROL_BYPASS,
    ) -> tuple[ApprovalProposal, bool]:
        context_json = context.model_dump_json()
        now_naive = _utc_naive(now)
        with self.db.get_session() as session:
            row = ApprovalProposalRecord(
                id=proposal_id,
                owner_id=owner,
                action=action,
                risk_source=risk_source.value,
                status=ApprovalStatus.PENDING.value,
                version=1,
                idempotency_key=idempotency_key,
                execution_id=execution_id,
                context_json=context_json,
                expires_at=_utc_naive(expires_at),
                created_at=now_naive,
                updated_at=now_naive,
            )
            session.add(row)
            try:
                session.commit()
                session.refresh(row)
                return self._proposal(row), True
            except IntegrityError:
                session.rollback()
                existing = session.execute(
                    select(ApprovalProposalRecord).where(
                        ApprovalProposalRecord.idempotency_key == idempotency_key
                    )
                ).scalar_one_or_none()
                if existing is None:
                    raise
                if (
                    existing.owner_id != owner
                    or existing.action != action
                    or existing.execution_id != execution_id
                    or existing.risk_source != risk_source.value
                    or existing.context_json != context_json
                ):
                    raise ApprovalStorageCorruptionError(
                        "approval idempotency key maps to different immutable input"
                    )
                return self._proposal(existing), False

    def get_proposal(self, *, owner: str, proposal_id: str) -> ApprovalProposal:
        with self.db.get_session() as session:
            row = session.execute(
                select(ApprovalProposalRecord).where(
                    ApprovalProposalRecord.id == proposal_id,
                    ApprovalProposalRecord.owner_id == owner,
                )
            ).scalar_one_or_none()
            if row is None:
                raise ApprovalNotFoundError("Approval proposal not found")
            return self._proposal(row)

    def list_proposals(
        self,
        *,
        owner: str,
        page: int,
        page_size: int,
        status: ApprovalStatus | None,
    ) -> tuple[list[ApprovalProposal], int]:
        conditions = [ApprovalProposalRecord.owner_id == owner]
        if status is not None:
            conditions.append(ApprovalProposalRecord.status == status.value)
        with self.db.get_session() as session:
            total = int(
                session.execute(
                    select(func.count(ApprovalProposalRecord.id)).where(*conditions)
                ).scalar()
                or 0
            )
            rows = session.execute(
                select(ApprovalProposalRecord)
                .where(*conditions)
                .order_by(
                    ApprovalProposalRecord.created_at.desc(),
                    ApprovalProposalRecord.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars().all()
            return [self._proposal(row) for row in rows], total

    def list_due_pending(
        self,
        *,
        owner: str,
        due_at: datetime,
        limit: int = 100,
    ) -> list[ApprovalProposal]:
        """Return one bounded batch of pending proposals due for expiry."""
        due_at_naive = _utc_naive(due_at)
        with self.db.get_session() as session:
            rows = session.execute(
                select(ApprovalProposalRecord)
                .where(
                    ApprovalProposalRecord.owner_id == owner,
                    ApprovalProposalRecord.status == ApprovalStatus.PENDING.value,
                    ApprovalProposalRecord.expires_at <= due_at_naive,
                )
                .order_by(
                    ApprovalProposalRecord.expires_at.asc(),
                    ApprovalProposalRecord.id.asc(),
                )
                .limit(max(1, min(int(limit), 100)))
            ).scalars().all()
            return [self._proposal(row) for row in rows]

    def transition(
        self,
        *,
        owner: str,
        proposal_id: str,
        expected_version: int,
        target_status: ApprovalStatus,
        now: datetime,
    ) -> ApprovalProposal:
        if target_status not in {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.CANCELLED,
            ApprovalStatus.EXPIRED,
        }:
            raise ApprovalInvalidTransitionError("Approval target state is invalid")
        now_naive = _utc_naive(now)
        with self.db.get_session() as session:
            row = session.execute(
                select(ApprovalProposalRecord).where(
                    ApprovalProposalRecord.id == proposal_id,
                    ApprovalProposalRecord.owner_id == owner,
                )
            ).scalar_one_or_none()
            if row is None:
                raise ApprovalNotFoundError("Approval proposal not found")
            current_status = ApprovalStatus(row.status)
            if current_status == target_status:
                return self._proposal(row)
            if current_status is not ApprovalStatus.PENDING:
                raise ApprovalInvalidTransitionError("Approval proposal is terminal")
            is_due = row.expires_at <= now_naive
            if target_status is ApprovalStatus.EXPIRED:
                if not is_due:
                    raise ApprovalInvalidTransitionError(
                        "Approval proposal has not expired"
                    )
            elif is_due:
                raise ApprovalExpiredError("Approval proposal has expired")
            if int(row.version) != expected_version:
                raise ApprovalVersionConflictError(int(row.version))
            expiry_predicate = (
                ApprovalProposalRecord.expires_at <= now_naive
                if target_status is ApprovalStatus.EXPIRED
                else ApprovalProposalRecord.expires_at > now_naive
            )
            result = session.execute(
                update(ApprovalProposalRecord)
                .where(
                    ApprovalProposalRecord.id == proposal_id,
                    ApprovalProposalRecord.owner_id == owner,
                    ApprovalProposalRecord.status == ApprovalStatus.PENDING.value,
                    ApprovalProposalRecord.version == expected_version,
                    expiry_predicate,
                )
                .values(
                    status=target_status.value,
                    version=expected_version + 1,
                    decided_at=now_naive,
                    updated_at=now_naive,
                )
            )
            if int(result.rowcount or 0) != 1:
                session.rollback()
                current = session.execute(
                    select(ApprovalProposalRecord).where(
                        ApprovalProposalRecord.id == proposal_id,
                        ApprovalProposalRecord.owner_id == owner,
                    )
                ).scalar_one()
                if (
                    current.status == ApprovalStatus.PENDING.value
                    and int(current.version) == expected_version
                    and current.expires_at <= now_naive
                    and target_status is not ApprovalStatus.EXPIRED
                ):
                    raise ApprovalExpiredError(
                        "Approval proposal has expired"
                    )
                raise ApprovalVersionConflictError(int(current.version))
            session.commit()
            refreshed = session.execute(
                select(ApprovalProposalRecord).where(
                    ApprovalProposalRecord.id == proposal_id
                )
            ).scalar_one()
            return self._proposal(refreshed)

    def consume(
        self,
        *,
        owner: str,
        proposal_id: str,
        expected_version: int,
        now: datetime,
    ) -> ApprovalProposal:
        now_naive = _utc_naive(now)
        with self.db.get_session() as session:
            row = session.execute(
                select(ApprovalProposalRecord).where(
                    ApprovalProposalRecord.id == proposal_id,
                    ApprovalProposalRecord.owner_id == owner,
                )
            ).scalar_one_or_none()
            if row is None:
                raise ApprovalNotFoundError("Approval proposal not found")
            if (
                row.status != ApprovalStatus.APPROVED.value
                or row.consumed_at is not None
                or row.expires_at <= now_naive
            ):
                raise ApprovalInvalidTransitionError(
                    "Approval proposal cannot be consumed"
                )
            if int(row.version) != expected_version:
                raise ApprovalVersionConflictError(int(row.version))
            result = session.execute(
                update(ApprovalProposalRecord)
                .where(
                    ApprovalProposalRecord.id == proposal_id,
                    ApprovalProposalRecord.owner_id == owner,
                    ApprovalProposalRecord.status == ApprovalStatus.APPROVED.value,
                    ApprovalProposalRecord.version == expected_version,
                    ApprovalProposalRecord.consumed_at.is_(None),
                    ApprovalProposalRecord.expires_at > now_naive,
                )
                .values(
                    consumed_at=now_naive,
                    version=expected_version + 1,
                    updated_at=now_naive,
                )
            )
            if int(result.rowcount or 0) != 1:
                session.rollback()
                current = session.execute(
                    select(ApprovalProposalRecord).where(
                        ApprovalProposalRecord.id == proposal_id,
                        ApprovalProposalRecord.owner_id == owner,
                    )
                ).scalar_one()
                raise ApprovalVersionConflictError(int(current.version))
            session.commit()
            refreshed = session.execute(
                select(ApprovalProposalRecord).where(
                    ApprovalProposalRecord.id == proposal_id
                )
            ).scalar_one()
            return self._proposal(refreshed)

    @staticmethod
    def _rule(row: ApprovalRuleRecord) -> ApprovalRule:
        try:
            sources = [
                ApprovalRiskSource(value)
                for value in json.loads(row.risk_sources_json)
            ]
            return ApprovalRule(
                owner=row.owner_id,
                action=row.action,
                enabled=bool(row.enabled),
                risk_sources=sources,
                expires_in_seconds=int(row.expires_in_seconds),
                version=int(row.version),
                updated_at=_utc_aware(row.updated_at),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ApprovalStorageCorruptionError(
                "Persisted approval rule is invalid"
            ) from exc

    @staticmethod
    def _proposal(row: ApprovalProposalRecord) -> ApprovalProposal:
        try:
            return ApprovalProposal(
                id=row.id,
                owner=row.owner_id,
                status=ApprovalStatus(row.status),
                version=int(row.version),
                expires_at=_utc_aware(row.expires_at),
                consumed_at=(
                    _utc_aware(row.consumed_at)
                    if row.consumed_at is not None
                    else None
                ),
                context=ApprovalContext.model_validate_json(row.context_json),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ApprovalStorageCorruptionError(
                "Persisted approval proposal is invalid"
            ) from exc
