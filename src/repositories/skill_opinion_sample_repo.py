# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Persistence for immutable, low-sensitivity skill-opinion samples."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from sqlalchemy import and_, exists, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.repositories.skill_opinion_tables import (
    analysis_history_table,
    skill_opinion_sample_table,
)
from src.schemas.skill_opinion_outcome import (
    AnalysisHistoryProjection,
    SkillOpinionSample,
)
from src.storage import DatabaseManager


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SkillOpinionSampleRepository:
    """Read history projections and insert missing immutable samples."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        clock: Callable[[], datetime] = _utc_naive_now,
    ) -> None:
        self.db = db_manager or DatabaseManager.get_instance()
        self._clock = clock

    def get_history(
        self,
        analysis_history_id: int,
    ) -> Optional[AnalysisHistoryProjection]:
        with self.db.get_session() as session:
            row = session.execute(
                select(
                    analysis_history_table.c.id,
                    analysis_history_table.c.code,
                    analysis_history_table.c.raw_result,
                    analysis_history_table.c.context_snapshot,
                    analysis_history_table.c.created_at,
                )
                .where(analysis_history_table.c.id == analysis_history_id)
                .limit(1)
            ).one_or_none()
        return self._history(row) if row is not None else None

    def list_unmaterialized_histories(
        self,
        *,
        sample_schema_version: str,
        limit: int,
        stock_code: Optional[str] = None,
    ) -> List[AnalysisHistoryProjection]:
        """Return bounded reports with synthesis data and no current samples."""
        sample_exists = exists(
            select(skill_opinion_sample_table.c.id).where(
                and_(
                    skill_opinion_sample_table.c.analysis_history_id
                    == analysis_history_table.c.id,
                    skill_opinion_sample_table.c.sample_schema_version
                    == sample_schema_version,
                )
            )
        )
        conditions = [
            analysis_history_table.c.raw_result.is_not(None),
            analysis_history_table.c.raw_result.like('%"strategy_synthesis"%'),
            ~sample_exists,
        ]
        if stock_code is not None:
            conditions.append(analysis_history_table.c.code == stock_code)
        with self.db.get_session() as session:
            rows = session.execute(
                select(
                    analysis_history_table.c.id,
                    analysis_history_table.c.code,
                    analysis_history_table.c.raw_result,
                    analysis_history_table.c.context_snapshot,
                    analysis_history_table.c.created_at,
                )
                .where(and_(*conditions))
                .order_by(
                    analysis_history_table.c.created_at,
                    analysis_history_table.c.id,
                )
                .limit(limit)
            ).all()
        return [self._history(row) for row in rows]

    def insert_missing(self, rows: Iterable[Dict[str, Any]]) -> int:
        """Insert eligible rows atomically and ignore only identity duplicates."""
        values = list(rows)
        if not values:
            return 0

        def _insert(session) -> int:
            history_ids = {
                row.get("analysis_history_id")
                for row in values
                if row.get("analysis_history_id") is not None
            }
            if not history_ids:
                return 0
            existing_history_ids = set(
                session.execute(
                    select(analysis_history_table.c.id).where(
                        analysis_history_table.c.id.in_(history_ids)
                    )
                ).scalars()
            )
            now = self._clock()
            eligible = [
                {**row, "created_at": row.get("created_at") or now}
                for row in values
                if row.get("analysis_history_id") in existing_history_ids
            ]
            if not eligible:
                return 0
            statement = sqlite_insert(skill_opinion_sample_table).values(eligible)
            statement = statement.on_conflict_do_nothing(
                index_elements=[
                    "analysis_history_id",
                    "skill_id",
                    "sample_schema_version",
                ]
            )
            result = session.execute(statement)
            return max(int(result.rowcount or 0), 0)

        return self.db._run_write_transaction(
            "insert skill opinion samples",
            _insert,
        )

    def list_for_history(
        self,
        analysis_history_id: int,
    ) -> List[SkillOpinionSample]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(skill_opinion_sample_table)
                .where(
                    skill_opinion_sample_table.c.analysis_history_id
                    == analysis_history_id
                )
                .order_by(skill_opinion_sample_table.c.id)
            ).all()
        return [self._sample(row) for row in rows]


    def list_recent(
        self,
        *,
        skill_id: Optional[str] = None,
        stock_code: Optional[str] = None,
        analysis_history_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[SkillOpinionSample], int]:
        """Return recent samples newest-first with a total count."""
        from sqlalchemy import func

        conditions = []
        if skill_id is not None:
            conditions.append(
                skill_opinion_sample_table.c.skill_id == skill_id
            )
        if stock_code is not None:
            conditions.append(
                skill_opinion_sample_table.c.stock_code == stock_code
            )
        if analysis_history_id is not None:
            conditions.append(
                skill_opinion_sample_table.c.analysis_history_id
                == analysis_history_id
            )
        with self.db.get_session() as session:
            count_stmt = select(func.count()).select_from(
                skill_opinion_sample_table
            )
            list_stmt = select(skill_opinion_sample_table).order_by(
                skill_opinion_sample_table.c.id.desc()
            )
            if conditions:
                count_stmt = count_stmt.where(and_(*conditions))
                list_stmt = list_stmt.where(and_(*conditions))
            total = int(session.execute(count_stmt).scalar_one() or 0)
            rows = session.execute(
                list_stmt.offset(offset).limit(limit)
            ).all()
        return [self._sample(row) for row in rows], total

    @staticmethod
    def _history(row: Any) -> AnalysisHistoryProjection:
        mapping = row._mapping
        return AnalysisHistoryProjection(
            id=int(mapping["id"]),
            stock_code=str(mapping["code"]),
            raw_result=mapping["raw_result"],
            context_snapshot=mapping["context_snapshot"],
            created_at=mapping["created_at"],
        )

    @staticmethod
    def _sample(row: Any) -> SkillOpinionSample:
        mapping = row._mapping
        return SkillOpinionSample(
            id=int(mapping["id"]),
            analysis_history_id=int(mapping["analysis_history_id"]),
            stock_code=str(mapping["stock_code"]),
            skill_id=str(mapping["skill_id"]),
            skill_version=mapping["skill_version"],
            signal=str(mapping["signal"]),
            confidence=float(mapping["confidence"]),
            horizon=mapping["horizon"],
            data_quality_level=mapping["data_quality_level"],
            opinion_created_at=mapping["opinion_created_at"],
            sample_schema_version=str(mapping["sample_schema_version"]),
            created_at=mapping["created_at"],
        )
