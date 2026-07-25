# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persistence boundary for the local personal investment framework."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import List, Optional, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from src.schemas.investment_framework import InvestmentFrameworkContent
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


@dataclass(frozen=True)
class _ValidatedInvestmentFrameworkState:
    aggregate: InvestmentFrameworkRecord
    versions: Tuple[InvestmentFrameworkVersionRecord, ...]
    latest: InvestmentFrameworkVersionRecord
    active: Optional[InvestmentFrameworkVersionRecord]


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
            state = self._load_validated_state_in_session(
                session,
                scope_key=scope_key,
            )
            if state is None:
                return None
            return self._stored(state.aggregate, state.latest)

    def get_active(
        self,
        *,
        scope_key: str = LOCAL_INVESTMENT_FRAMEWORK_SCOPE,
    ) -> Optional[StoredInvestmentFramework]:
        with self.db.get_session() as session:
            state = self._load_validated_state_in_session(
                session,
                scope_key=scope_key,
            )
            if state is None or state.active is None:
                return None
            return self._stored(state.aggregate, state.active)

    def list_history(
        self,
        *,
        scope_key: str = LOCAL_INVESTMENT_FRAMEWORK_SCOPE,
    ) -> Tuple[StoredInvestmentFramework, List[StoredInvestmentFrameworkVersion]]:
        with self.db.get_session() as session:
            state = self._require_validated_state_in_session(
                session,
                scope_key=scope_key,
            )
            current = self._stored(state.aggregate, state.latest)
            return current, [
                self._stored_version(row)
                for row in reversed(state.versions)
            ]

    def create(
        self,
        *,
        content_json: str,
        change_summary: Optional[str],
        scope_key: str = LOCAL_INVESTMENT_FRAMEWORK_SCOPE,
    ) -> StoredInvestmentFramework:
        now = utc_naive_now()

        def write(session):
            existing = self._load_validated_state_in_session(
                session,
                scope_key=scope_key,
            )
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
            framework_id = int(aggregate.id)
            version_id = int(version.id)
            session.expire_all()
            state = self._require_validated_state_in_session(
                session,
                scope_key=scope_key,
            )
            self._assert_exact_transition(
                state,
                expected_aggregate=(
                    framework_id,
                    scope_key,
                    1,
                    1,
                    1,
                    now,
                    now,
                ),
                expected_versions=(
                    (
                        version_id,
                        framework_id,
                        1,
                        content_json,
                        change_summary,
                        now,
                    ),
                ),
            )
            return self._stored(state.aggregate, state.latest)

        try:
            return self.db._run_write_transaction(
                "investment_framework_create",
                write,
            )
        except IntegrityError as exc:
            current = self.get_current(scope_key=scope_key)
            if current is not None:
                raise InvestmentFrameworkAlreadyExistsError(
                    "Investment framework already exists"
                ) from exc
            raise InvestmentFrameworkRepositoryError(
                "Investment framework storage violates creation constraints"
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
            state = self._require_validated_state_in_session(
                session,
                scope_key=scope_key,
            )
            aggregate = state.aggregate
            self._guard_revision(aggregate, expected_revision)
            prior_versions = tuple(
                self._version_fingerprint(version)
                for version in state.versions
            )
            framework_id = int(aggregate.id)
            aggregate_created_at = aggregate.created_at
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
                session.expire_all()
                raise InvestmentFrameworkRevisionConflictError(
                    self._current_revision_in_session(session, scope_key=scope_key)
                )
            new_version = InvestmentFrameworkVersionRecord(
                framework_id=aggregate.id,
                version=next_version,
                content_json=content_json,
                change_summary=change_summary,
                created_at=now,
            )
            session.add(new_version)
            session.flush()
            version_id = int(new_version.id)
            session.expire_all()
            updated_state = self._require_validated_state_in_session(
                session,
                scope_key=scope_key,
            )
            self._assert_exact_transition(
                updated_state,
                expected_aggregate=(
                    framework_id,
                    scope_key,
                    next_version,
                    next_version,
                    expected_revision + 1,
                    aggregate_created_at,
                    now,
                ),
                expected_versions=prior_versions
                + (
                    (
                        version_id,
                        framework_id,
                        next_version,
                        content_json,
                        change_summary,
                        now,
                    ),
                ),
            )
            return self._stored(updated_state.aggregate, updated_state.latest)

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
            if current.revision != expected_revision:
                raise InvestmentFrameworkRevisionConflictError(
                    current.revision
                ) from exc
            raise InvestmentFrameworkRepositoryError(
                "Investment framework version history violates storage constraints"
            ) from exc

    def deactivate(
        self,
        *,
        expected_revision: int,
        scope_key: str = LOCAL_INVESTMENT_FRAMEWORK_SCOPE,
    ) -> StoredInvestmentFramework:
        now = utc_naive_now()

        def write(session):
            state = self._require_validated_state_in_session(
                session,
                scope_key=scope_key,
            )
            aggregate = state.aggregate
            self._guard_revision(aggregate, expected_revision)
            if aggregate.active_version is None:
                return self._stored(state.aggregate, state.latest)
            prior_versions = tuple(
                self._version_fingerprint(version)
                for version in state.versions
            )
            framework_id = int(aggregate.id)
            latest_version = int(aggregate.latest_version)
            aggregate_created_at = aggregate.created_at
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
                session.expire_all()
                raise InvestmentFrameworkRevisionConflictError(
                    self._current_revision_in_session(session, scope_key=scope_key)
                )
            session.flush()
            session.expire_all()
            inactive_state = self._require_validated_state_in_session(
                session,
                scope_key=scope_key,
            )
            self._assert_exact_transition(
                inactive_state,
                expected_aggregate=(
                    framework_id,
                    scope_key,
                    latest_version,
                    None,
                    expected_revision + 1,
                    aggregate_created_at,
                    now,
                ),
                expected_versions=prior_versions,
            )
            return self._stored(inactive_state.aggregate, inactive_state.latest)

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
            state = self._require_validated_state_in_session(
                session,
                scope_key=scope_key,
            )
            aggregate = state.aggregate
            self._guard_revision(aggregate, expected_revision)
            deleted = DeletedInvestmentFramework(
                framework_id=int(aggregate.id),
                latest_version=int(aggregate.latest_version),
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
                session.expire_all()
                raise InvestmentFrameworkRevisionConflictError(
                    self._current_revision_in_session(session, scope_key=scope_key)
                )
            session.execute(
                delete(InvestmentFrameworkVersionRecord).where(
                    InvestmentFrameworkVersionRecord.framework_id == aggregate.id
                )
            )
            session.flush()
            if self._load_validated_state_in_session(
                session,
                scope_key=scope_key,
            ) is not None:
                raise InvestmentFrameworkRepositoryError(
                    "Deleted investment framework remains present"
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
    def _aggregate_fingerprint(
        aggregate: InvestmentFrameworkRecord,
    ) -> tuple:
        return (
            int(aggregate.id),
            str(aggregate.scope_key),
            int(aggregate.latest_version),
            (
                int(aggregate.active_version)
                if aggregate.active_version is not None
                else None
            ),
            int(aggregate.revision),
            aggregate.created_at,
            aggregate.updated_at,
        )

    @staticmethod
    def _version_fingerprint(
        version: InvestmentFrameworkVersionRecord,
    ) -> tuple:
        return (
            int(version.id),
            int(version.framework_id),
            int(version.version),
            str(version.content_json),
            version.change_summary,
            version.created_at,
        )

    @classmethod
    def _assert_exact_transition(
        cls,
        state: _ValidatedInvestmentFrameworkState,
        *,
        expected_aggregate: tuple,
        expected_versions: tuple,
    ) -> None:
        if cls._aggregate_fingerprint(state.aggregate) != expected_aggregate:
            raise InvestmentFrameworkRepositoryError(
                "Investment framework aggregate transition was altered"
            )
        observed_versions = tuple(
            cls._version_fingerprint(version)
            for version in state.versions
        )
        if observed_versions != expected_versions:
            raise InvestmentFrameworkRepositoryError(
                "Investment framework version transition was altered"
            )

    @staticmethod
    def _guard_revision(
        aggregate: InvestmentFrameworkRecord,
        expected_revision: int,
    ) -> None:
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("expected_revision must be a positive integer")
        if int(aggregate.revision) != expected_revision:
            raise InvestmentFrameworkRevisionConflictError(int(aggregate.revision))

    @classmethod
    def _require_validated_state_in_session(
        cls,
        session,
        *,
        scope_key: str,
    ) -> _ValidatedInvestmentFrameworkState:
        state = cls._load_validated_state_in_session(
            session,
            scope_key=scope_key,
        )
        if state is None:
            raise InvestmentFrameworkNotFoundError(
                "Investment framework does not exist"
            )
        return state

    @classmethod
    def _current_revision_in_session(cls, session, *, scope_key: str) -> int:
        state = cls._require_validated_state_in_session(
            session,
            scope_key=scope_key,
        )
        return cls._positive_integer(
            state.aggregate.revision,
            field_name="revision",
        )

    @staticmethod
    def _positive_integer(value: object, *, field_name: str) -> int:
        if type(value) is not int or value < 1:
            raise InvestmentFrameworkRepositoryError(
                f"Investment framework {field_name} is invalid"
            )
        return value

    @classmethod
    def _load_validated_state_in_session(
        cls,
        session,
        *,
        scope_key: str,
    ) -> Optional[_ValidatedInvestmentFrameworkState]:
        if type(scope_key) is not str or scope_key != LOCAL_INVESTMENT_FRAMEWORK_SCOPE:
            raise InvestmentFrameworkRepositoryError(
                "Investment framework scope is invalid"
            )
        try:
            aggregates = tuple(
                session.execute(
                    select(InvestmentFrameworkRecord).order_by(
                        InvestmentFrameworkRecord.id
                    )
                ).scalars().all()
            )
            versions = tuple(
                session.execute(
                    select(InvestmentFrameworkVersionRecord).order_by(
                        InvestmentFrameworkVersionRecord.framework_id,
                        InvestmentFrameworkVersionRecord.version,
                        InvestmentFrameworkVersionRecord.id,
                    )
                ).scalars().all()
            )
        except (TypeError, ValueError) as exc:
            raise InvestmentFrameworkRepositoryError(
                "Investment framework rows could not be materialized"
            ) from exc
        if not aggregates:
            if versions:
                raise InvestmentFrameworkRepositoryError(
                    "Investment framework history is orphaned"
                )
            return None
        if len(aggregates) != 1:
            raise InvestmentFrameworkRepositoryError(
                "Investment framework aggregate cardinality is invalid"
            )

        aggregate = aggregates[0]
        framework_id = cls._positive_integer(
            aggregate.id,
            field_name="ID",
        )
        if (
            type(aggregate.scope_key) is not str
            or aggregate.scope_key != LOCAL_INVESTMENT_FRAMEWORK_SCOPE
        ):
            raise InvestmentFrameworkRepositoryError(
                "Investment framework aggregate scope is invalid"
            )
        latest_version = cls._positive_integer(
            aggregate.latest_version,
            field_name="latest version",
        )
        revision = cls._positive_integer(
            aggregate.revision,
            field_name="revision",
        )
        active_version = aggregate.active_version
        if active_version is not None:
            active_version = cls._positive_integer(
                active_version,
                field_name="active version",
            )
            if active_version != latest_version:
                raise InvestmentFrameworkRepositoryError(
                    "Investment framework active version is not the latest version"
                )

        if len(versions) != latest_version:
            raise InvestmentFrameworkRepositoryError(
                "Investment framework version history length is invalid"
            )
        for expected_version, version in enumerate(versions, start=1):
            cls._positive_integer(version.id, field_name="history row ID")
            owner_id = cls._positive_integer(
                version.framework_id,
                field_name="history owner ID",
            )
            if owner_id != framework_id:
                raise InvestmentFrameworkRepositoryError(
                    "Investment framework history has a foreign owner"
                )
            version_number = cls._positive_integer(
                version.version,
                field_name="history version",
            )
            if version_number != expected_version:
                raise InvestmentFrameworkRepositoryError(
                    "Investment framework version history is not contiguous"
                )
            if type(version.content_json) is not str:
                raise InvestmentFrameworkRepositoryError(
                    "Investment framework history content is invalid"
                )
            try:
                InvestmentFrameworkContent.model_validate(
                    json.loads(version.content_json)
                )
            except (TypeError, ValueError, RecursionError) as exc:
                raise InvestmentFrameworkRepositoryError(
                    "Investment framework history content is invalid"
                ) from exc
            if (
                version.change_summary is not None
                and (
                    type(version.change_summary) is not str
                    or not version.change_summary
                    or len(version.change_summary) > 500
                )
            ):
                raise InvestmentFrameworkRepositoryError(
                    "Investment framework change summary is invalid"
                )

        if active_version is None:
            minimum_revision = latest_version + 1
            maximum_revision = latest_version * 2
        else:
            minimum_revision = latest_version
            maximum_revision = latest_version * 2 - 1
        if not minimum_revision <= revision <= maximum_revision:
            raise InvestmentFrameworkRepositoryError(
                "Investment framework revision is outside its legal state bounds"
            )
        latest = versions[-1]
        active = latest if active_version is not None else None
        return _ValidatedInvestmentFrameworkState(
            aggregate=aggregate,
            versions=versions,
            latest=latest,
            active=active,
        )
