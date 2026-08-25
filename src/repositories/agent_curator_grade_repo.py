# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""SQLite sidecar store for eval-fixture curator grades.

Issue #1096 remaining ingest slice: latest-row upsert keyed by canonical
``episode_id``. This repository never ``UPDATE``s append-only
``agent_episodes``. Missing grades stay absent; unknown tokens are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select, update

from src.repositories.agent_curator_grade_tables import (
    agent_episode_curator_grades_table,
)
from src.repositories.base import BaseRepository
from src.schemas.curator_grade import (
    CURATOR_GRADE_ALLOWLIST,
    normalize_curator_grade,
)
from src.schemas.memory_provenance import (
    PROVENANCE_SOURCE_OPERATOR,
    apply_server_provenance,
    reject_client_provenance_keys,
)
from src.storage import DatabaseManager, utc_naive_now


def validate_curator_grade(grade: Optional[str]) -> str:
    """Reject unknown / blank curator grades. Research-only; not trading advice."""
    canonical = normalize_curator_grade(grade)
    if canonical is None:
        raise ValueError("manual_grade is required")
    if canonical not in CURATOR_GRADE_ALLOWLIST:
        raise ValueError(f"unsupported manual_grade: {grade!r}")
    return canonical


@dataclass(frozen=True)
class AgentCuratorGradeRecord:
    """Detached latest-row curator-grade sidecar."""

    episode_id: str
    run_id: str
    manual_grade: str
    provenance_source: Optional[str]
    actor_id: Optional[str]
    created_at: datetime
    updated_at: datetime


def _row_to_record(row: Any) -> AgentCuratorGradeRecord:
    return AgentCuratorGradeRecord(
        episode_id=str(row.episode_id),
        run_id=str(row.run_id),
        manual_grade=str(row.manual_grade),
        provenance_source=row.provenance_source,
        actor_id=row.actor_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AgentCuratorGradeRepository(BaseRepository):
    """Persist optional curator grades without mutating episodes."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        super().__init__(db_manager)

    def get_by_episode_id(self, episode_id: str) -> Optional[AgentCuratorGradeRecord]:
        key = str(episode_id or "").strip()
        if not key:
            return None
        with self.db.get_session() as session:
            row = session.execute(
                select(agent_episode_curator_grades_table)
                .where(agent_episode_curator_grades_table.c.episode_id == key)
                .limit(1)
            ).one_or_none()
        return _row_to_record(row) if row is not None else None

    def list_by_run_id(self, run_id: str) -> List[AgentCuratorGradeRecord]:
        key = str(run_id or "").strip()
        if not key:
            return []
        with self.db.get_session() as session:
            rows = session.execute(
                select(agent_episode_curator_grades_table)
                .where(agent_episode_curator_grades_table.c.run_id == key)
                .order_by(agent_episode_curator_grades_table.c.episode_id)
            ).all()
        return [_row_to_record(row) for row in rows]

    def upsert(
        self,
        *,
        episode_id: str,
        run_id: str,
        manual_grade: str,
    ) -> AgentCuratorGradeRecord:
        canonical_episode = str(episode_id or "").strip()
        canonical_run = str(run_id or "").strip()
        if not canonical_episode:
            raise ValueError("episode_id is required")
        if not canonical_run:
            raise ValueError("run_id is required")
        canonical_grade = validate_curator_grade(manual_grade)
        reject_client_provenance_keys({"manual_grade": canonical_grade})
        stamped = apply_server_provenance(
            {"manual_grade": canonical_grade},
            provenance_source=PROVENANCE_SOURCE_OPERATOR,
            actor_id=None,
        )
        now = utc_naive_now()
        persist = {
            "episode_id": canonical_episode,
            "run_id": canonical_run,
            "manual_grade": stamped["manual_grade"],
            "provenance_source": stamped["provenance_source"],
            "actor_id": stamped["actor_id"],
        }
        table = agent_episode_curator_grades_table
        with self.db.get_session() as session:
            existing = session.execute(
                select(table)
                .where(table.c.episode_id == canonical_episode)
                .limit(1)
            ).one_or_none()
            if existing is None:
                persist["created_at"] = now
                persist["updated_at"] = now
                session.execute(table.insert().values(**persist))
            else:
                session.execute(
                    update(table)
                    .where(table.c.episode_id == canonical_episode)
                    .values(
                        run_id=canonical_run,
                        manual_grade=persist["manual_grade"],
                        provenance_source=persist["provenance_source"],
                        actor_id=persist["actor_id"],
                        updated_at=now,
                    )
                )
            session.commit()
        record = self.get_by_episode_id(canonical_episode)
        if record is None:
            raise RuntimeError(
                "curator-grade upsert committed but row is missing for "
                f"episode_id={canonical_episode}"
            )
        return record
