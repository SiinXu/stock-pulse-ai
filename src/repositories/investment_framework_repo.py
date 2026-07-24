# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persistence boundary for the local personal investment framework."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import delete, desc, select, update
from sqlalchemy.exc import IntegrityError

from src.storage import (
    DatabaseManager,
    InvestmentFrameworkRecord,
    InvestmentFrameworkVersionRecord,
    utc_naive_now,
)


LOCAL_INVESTMENT_FRAMEWORK_SCOPE = "local"


class InvestmentFrameworkRepositoryError(RuntimeError):
    """Base persistence-contract error."""


class InvestmentFrameworkNotFoundError(InvestmentFrameworkRepositoryError):
    """Raised when the local framework aggregate does not exist."""


class InvestmentFrameworkAlreadyExistsError(InvestmentFrameworkRepositoryError):
    """Raised when create would replace an existing local framework."""


class InvestmentFrameworkRevisionConflictError(InvestmentFrameworkRepositoryError):
    """Raised when a mutation uses a stale aggregate revision."""

    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__("Investment framework revision conflict")


@dataclass(frozen=True)
class StoredInvestmentFramework:
    framework_id: int
    scope_key: str
    latest_version: int
    active_version: Optional[int]
    revision: int
    created_at: datetime
    updated_at: datetime
    version: int
    content_json: str
    change_summary: Optional[str]
    version_created_at: datetime


@dataclass(frozen=True)
class StoredInvestmentFrameworkVersion:
    framework_id: int
    version: int
    content_json: str
    change_summary: Optional[str]
    created_at: datetime


@dataclass(frozen=True)
class DeletedInvestmentFramework:
    framework_id: int
    latest_version: int


class InvestmentFrameworkRepository:
    """Atomic version/history operations for the single local account scope."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def get_current(
        self,
        *,
        scope_key: str = LOCAL_INVESTMENT_FRAMEWORK_SCOPE,
    ) -> Optional[StoredInvestmentFramework]:
        with self.db.get_session() as session:
            return self._load_current_in_session(session, scope_key=scope_key)

    def get_active(
        self,
        *,
        scope_key: str = LOCAL_INVESTMENT_FRAMEWORK_SCOPE,
    ) -> Optional[StoredInvestmentFramework]:
        with self.db.get_session() as session:
            aggregate = session.execute(
                select(InvestmentFrameworkRecord)
                .where(
                    InvestmentFrameworkRecord.scope_key == scope_key,
                    InvestmentFrameworkRecord.active_version.is_not(None),
                )
                .limit(1)
            ).scalar_one_or_none()
            if aggregate is None:
                return None
            version = session.execute(
                select(InvestmentFrameworkVersionRecord)
                .where(
                    InvestmentFrameworkVersionRecord.framework_id == aggregate.id,
                    InvestmentFrameworkVersionRecord.version == aggregate.active_version,
                )
                .limit(1)
            ).scalar_one_or_none()
            if version is None:
                raise InvestmentFrameworkRepositoryError(
                    "Active investment framework version is missing"
                )
            return self._stored(aggregate, version)

    def list_history(
        self,
        *,
        scope_key: str = LOCAL_INVESTMENT_FRAMEWORK_SCOPE,
    ) -> Tuple[StoredInvestmentFramework, List[StoredInvestmentFrameworkVersion]]:
        with self.db.get_session() as session:
            current = self._load_current_in_session(session, scope_key=scope_key)
            if current is None:
                raise InvestmentFrameworkNotFoundError(
                    "Investment framework does not exist"
                )
            rows = session.execute(
                select(InvestmentFrameworkVersionRecord)
                .where(
                    InvestmentFrameworkVersionRecord.framework_id
                    == current.framework_id
                )
                .order_by(desc(InvestmentFrameworkVersionRecord.version))
            ).scalars().all()
            return current, [self._stored_version(row) for row in rows]

    def create(
        self,
        *,
        content_json: str,
        change_summary: Optional[str],
        scope_key: str = LOCAL_INVESTMENT_FRAMEWORK_SCOPE,
    ) -> StoredInvestmentFramework:
        now = utc_naive_now()

        def write(session):
            existing = session.execute(
                select(InvestmentFrameworkRecord.id)
                .where(InvestmentFrameworkRecord.scope_key == scope_key)
                .limit(1)
            ).scalar_one_or_none()
            if existing is not None:
                raise InvestmentFrameworkAlreadyExistsError(
                    "Investment framework already exists"
                )
            aggregate = InvestmentFrameworkRecord(
                scope_key=scope_key,
                latest_version=1,
                active_version=1,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            session.add(aggregate)
            session.flush()
            version = InvestmentFrameworkVersionRecord(
                framework_id=aggregate.id,
                version=1,
                content_json=content_json,
                change_summary=change_summary,
                created_at=now,
            )
            session.add(version)
            session.flush()
            return self._stored(aggregate, version)

        try:
            return self.db._run_write_transaction(
                "investment_framework_create",
                write,
            )
        except IntegrityError as exc:
            raise InvestmentFrameworkAlreadyExistsError(
                "Investment framework already exists"
            ) from exc

    def update(
        self,
        *,
        expected_revision: int,
        content_json: str,
        change_summary: Optional[str],
        scope_key: str = LOCAL_INVESTMENT_FRAMEWORK_SCOPE,
    ) -> StoredInvestmentFramework:
        now = utc_naive_now()

        def write(session):
            aggregate = self._require_aggregate_in_session(
                session,
                scope_key=scope_key,
            )
            self._guard_revision(aggregate, expected_revision)
            next_version = int(aggregate.latest_version) + 1
            result = session.execute(
                update(InvestmentFrameworkRecord)
                .where(
                    InvestmentFrameworkRecord.id == aggregate.id,
                    InvestmentFrameworkRecord.revision == expected_revision,
                )
                .values(
                    latest_version=next_version,
                    active_version=next_version,
                    revision=expected_revision + 1,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if int(result.rowcount or 0) != 1:
                raise InvestmentFrameworkRevisionConflictError(
                    self._current_revision_in_session(session, scope_key=scope_key)
                )
            session.add(
                InvestmentFrameworkVersionRecord(
                    framework_id=aggregate.id,
                    version=next_version,
                    content_json=content_json,
                    change_summary=change_summary,
                    created_at=now,
                )
            )
            session.flush()
            session.expire_all()
            stored = self._load_current_in_session(session, scope_key=scope_key)
            if stored is None:
                raise InvestmentFrameworkRepositoryError(
                    "Updated investment framework could not be reloaded"
                )
            return stored

        try:
            return self.db._run_write_transaction(
                "investment_framework_update",
                write,
            )
        except IntegrityError as exc:
            current = self.get_current(scope_key=scope_key)
            if current is None:
                raise InvestmentFrameworkNotFoundError(
                    "Investment framework does not exist"
                ) from exc
            raise InvestmentFrameworkRevisionConflictError(
                current.revision
            ) from exc

    def deactivate(
        self,
        *,
        expected_revision: int,
        scope_key: str = LOCAL_INVESTMENT_FRAMEWORK_SCOPE,
    ) -> StoredInvestmentFramework:
        now = utc_naive_now()

        def write(session):
            aggregate = self._require_aggregate_in_session(
                session,
                scope_key=scope_key,
            )
            self._guard_revision(aggregate, expected_revision)
            if aggregate.active_version is None:
                current = self._load_current_in_session(session, scope_key=scope_key)
                if current is None:
                    raise InvestmentFrameworkRepositoryError(
                        "Inactive investment framework could not be reloaded"
                    )
                return current
            result = session.execute(
                update(InvestmentFrameworkRecord)
                .where(
                    InvestmentFrameworkRecord.id == aggregate.id,
                    InvestmentFrameworkRecord.revision == expected_revision,
                )
                .values(
                    active_version=None,
                    revision=expected_revision + 1,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if int(result.rowcount or 0) != 1:
                raise InvestmentFrameworkRevisionConflictError(
                    self._current_revision_in_session(session, scope_key=scope_key)
                )
            session.flush()
            session.expire_all()
            current = self._load_current_in_session(session, scope_key=scope_key)
            if current is None:
                raise InvestmentFrameworkRepositoryError(
                    "Deactivated investment framework could not be reloaded"
                )
            return current

        return self.db._run_write_transaction(
            "investment_framework_deactivate",
            write,
        )

    def delete(
        self,
        *,
        expected_revision: int,
        scope_key: str = LOCAL_INVESTMENT_FRAMEWORK_SCOPE,
    ) -> DeletedInvestmentFramework:
        def write(session):
            aggregate = self._require_aggregate_in_session(
                session,
                scope_key=scope_key,
            )
            self._guard_revision(aggregate, expected_revision)
            deleted = DeletedInvestmentFramework(
                framework_id=int(aggregate.id),
                latest_version=int(aggregate.latest_version),
            )
            session.execute(
                delete(InvestmentFrameworkVersionRecord).where(
                    InvestmentFrameworkVersionRecord.framework_id == aggregate.id
                )
            )
            result = session.execute(
                delete(InvestmentFrameworkRecord)
                .where(
                    InvestmentFrameworkRecord.id == aggregate.id,
                    InvestmentFrameworkRecord.revision == expected_revision,
                )
                .execution_options(synchronize_session=False)
            )
            if int(result.rowcount or 0) != 1:
                raise InvestmentFrameworkRevisionConflictError(
                    self._current_revision_in_session(session, scope_key=scope_key)
                )
            return deleted

        return self.db._run_write_transaction(
            "investment_framework_delete",
            write,
        )

    @staticmethod
    def _stored(
        aggregate: InvestmentFrameworkRecord,
        version: InvestmentFrameworkVersionRecord,
    ) -> StoredInvestmentFramework:
        return StoredInvestmentFramework(
            framework_id=int(aggregate.id),
            scope_key=str(aggregate.scope_key),
            latest_version=int(aggregate.latest_version),
            active_version=(
                int(aggregate.active_version)
                if aggregate.active_version is not None
                else None
            ),
            revision=int(aggregate.revision),
            created_at=aggregate.created_at,
            updated_at=aggregate.updated_at,
            version=int(version.version),
            content_json=str(version.content_json),
            change_summary=version.change_summary,
            version_created_at=version.created_at,
        )

    @staticmethod
    def _stored_version(
        version: InvestmentFrameworkVersionRecord,
    ) -> StoredInvestmentFrameworkVersion:
        return StoredInvestmentFrameworkVersion(
            framework_id=int(version.framework_id),
            version=int(version.version),
            content_json=str(version.content_json),
            change_summary=version.change_summary,
            created_at=version.created_at,
        )

    @staticmethod
    def _guard_revision(
        aggregate: InvestmentFrameworkRecord,
        expected_revision: int,
    ) -> None:
        if int(aggregate.revision) != expected_revision:
            raise InvestmentFrameworkRevisionConflictError(int(aggregate.revision))

    @staticmethod
    def _require_aggregate_in_session(
        session,
        *,
        scope_key: str,
    ) -> InvestmentFrameworkRecord:
        aggregate = session.execute(
            select(InvestmentFrameworkRecord)
            .where(InvestmentFrameworkRecord.scope_key == scope_key)
            .limit(1)
        ).scalar_one_or_none()
        if aggregate is None:
            raise InvestmentFrameworkNotFoundError(
                "Investment framework does not exist"
            )
        return aggregate

    @staticmethod
    def _current_revision_in_session(session, *, scope_key: str) -> int:
        current_revision = session.execute(
            select(InvestmentFrameworkRecord.revision)
            .where(InvestmentFrameworkRecord.scope_key == scope_key)
            .limit(1)
        ).scalar_one_or_none()
        if current_revision is None:
            raise InvestmentFrameworkNotFoundError(
                "Investment framework does not exist"
            )
        return int(current_revision)

    @staticmethod
    def _load_current_in_session(
        session,
        *,
        scope_key: str,
    ) -> Optional[StoredInvestmentFramework]:
        aggregate = session.execute(
            select(InvestmentFrameworkRecord)
            .where(InvestmentFrameworkRecord.scope_key == scope_key)
            .limit(1)
        ).scalar_one_or_none()
        if aggregate is None:
            return None
        version = session.execute(
            select(InvestmentFrameworkVersionRecord)
            .where(
                InvestmentFrameworkVersionRecord.framework_id == aggregate.id,
                InvestmentFrameworkVersionRecord.version == aggregate.latest_version,
            )
            .limit(1)
        ).scalar_one_or_none()
        if version is None:
            raise InvestmentFrameworkRepositoryError(
                "Latest investment framework version is missing"
            )
        return InvestmentFrameworkRepository._stored(aggregate, version)
