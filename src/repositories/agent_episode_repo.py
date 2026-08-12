# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Append and query access for agent evolution episode logs (Issue #1090)."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any, Callable, List, Optional, Sequence

from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.exc import IntegrityError

from src.repositories.agent_episode_tables import agent_episodes_table
from src.repositories.base import BaseRepository, RepositoryError
from src.schemas.agent_episode import (
    AGENT_EPISODE_MAX_PAGE_SIZE,
    AGENT_EPISODE_SCHEMA_VERSION,
    AgentEpisode,
    AgentEpisodeCreate,
    AgentEpisodePage,
    EpisodeLesson,
    EpisodeOutcomeLabels,
    TrajectoryStepSummary,
)
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_dumps(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
    )


def _as_utc_aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class AgentEpisodeRepository(BaseRepository):
    """The only persistence boundary for the append-oriented episode table."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        clock: Callable[[], datetime] = _utc_naive_now,
    ) -> None:
        super().__init__(db_manager)
        self._clock = clock

    @staticmethod
    def _row_to_episode(row: Any) -> AgentEpisode:
        trajectory_raw = json.loads(row.trajectory_summary_json or "[]")
        lessons_raw = json.loads(row.lessons_json or "[]")
        outcome_raw = json.loads(row.outcome_labels_json) if row.outcome_labels_json else None
        trajectory = [
            TrajectoryStepSummary.model_validate(item)
            for item in trajectory_raw
            if isinstance(item, dict)
        ]
        lessons = [
            EpisodeLesson.model_validate(item)
            for item in lessons_raw
            if isinstance(item, dict)
        ]
        outcome = (
            EpisodeOutcomeLabels.model_validate(outcome_raw)
            if isinstance(outcome_raw, dict)
            else None
        )
        return AgentEpisode.model_validate(
            {
                "id": int(row.id),
                "schema_version": str(row.schema_version),
                "episode_id": str(row.episode_id),
                "run_id": str(row.run_id),
                "mode": str(row.mode),
                "symbol": row.symbol,
                "market": row.market,
                "started_at": _as_utc_aware(row.started_at),
                "completed_at": _as_utc_aware(row.completed_at),
                "success": row.success,
                "soul_version": row.soul_version,
                "soul_hash": row.soul_hash,
                "trajectory_summary": trajectory,
                "lessons": lessons,
                "outcome_labels": outcome,
                "created_at": _as_utc_aware(row.created_at) or datetime.now(timezone.utc),
            }
        )

    def append(self, episode: AgentEpisodeCreate) -> AgentEpisode:
        now = self._clock()
        values = {
            "schema_version": episode.schema_version or AGENT_EPISODE_SCHEMA_VERSION,
            "episode_id": episode.episode_id,
            "run_id": episode.run_id,
            "mode": episode.mode,
            "symbol": episode.symbol,
            "market": episode.market,
            "started_at": _as_utc_naive(episode.started_at),
            "completed_at": _as_utc_naive(episode.completed_at),
            "success": episode.success,
            "soul_version": episode.soul_version,
            "soul_hash": episode.soul_hash,
            "trajectory_summary_json": _json_dumps(
                [step.model_dump(mode="python") for step in episode.trajectory_summary]
            ),
            "lessons_json": _json_dumps(
                [lesson.model_dump(mode="python") for lesson in episode.lessons]
            ),
            "outcome_labels_json": (
                _json_dumps(episode.outcome_labels.model_dump(mode="python"))
                if episode.outcome_labels is not None
                else None
            ),
            "created_at": now,
        }
        try:
            with self.db.get_session() as session:
                result = session.execute(agent_episodes_table.insert().values(**values))
                session.flush()
                row_id = int(result.inserted_primary_key[0])
                session.commit()
            stored = self.get_by_episode_id(episode.episode_id)
            if stored is None:
                raise RepositoryError(
                    "agent episode insert committed but row is missing",
                    error_code="agent_episode_insert_missing",
                    context={"episode_id": episode.episode_id, "row_id": row_id},
                )
            return stored
        except IntegrityError as exc:
            existing = self.get_by_episode_id(episode.episode_id)
            if existing is not None:
                return existing
            self._log_and_raise(
                logger,
                "agent_episode_append_conflict",
                exc,
                error_code="agent_episode_append_conflict",
                context={"episode_id": episode.episode_id},
            )

    def get_by_episode_id(self, episode_id: str) -> Optional[AgentEpisode]:
        key = str(episode_id or "").strip()
        if not key:
            return None
        with self.db.get_session() as session:
            row = session.execute(
                select(agent_episodes_table)
                .where(agent_episodes_table.c.episode_id == key)
                .limit(1)
            ).first()
            return self._row_to_episode(row) if row is not None else None

    def get_by_run_id(self, run_id: str) -> List[AgentEpisode]:
        key = str(run_id or "").strip()
        if not key:
            return []
        with self.db.get_session() as session:
            rows = session.execute(
                select(agent_episodes_table)
                .where(agent_episodes_table.c.run_id == key)
                .order_by(desc(agent_episodes_table.c.created_at), desc(agent_episodes_table.c.id))
            ).all()
            return [self._row_to_episode(row) for row in rows]

    def query(
        self,
        *,
        run_id: Optional[str] = None,
        symbol: Optional[str] = None,
        mode: Optional[str] = None,
        created_from: Optional[datetime] = None,
        created_to: Optional[datetime] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> AgentEpisodePage:
        safe_limit = max(1, min(int(limit), AGENT_EPISODE_MAX_PAGE_SIZE))
        safe_offset = max(0, int(offset))
        conditions = []
        if run_id:
            conditions.append(agent_episodes_table.c.run_id == str(run_id).strip())
        if symbol:
            conditions.append(agent_episodes_table.c.symbol == str(symbol).strip())
        if mode:
            conditions.append(agent_episodes_table.c.mode == str(mode).strip().lower())
        if created_from is not None:
            conditions.append(agent_episodes_table.c.created_at >= _as_utc_naive(created_from))
        if created_to is not None:
            conditions.append(agent_episodes_table.c.created_at <= _as_utc_naive(created_to))
        where_clause = and_(*conditions) if conditions else True
        with self.db.get_session() as session:
            total = int(
                session.execute(
                    select(func.count()).select_from(agent_episodes_table).where(where_clause)
                ).scalar()
                or 0
            )
            rows = session.execute(
                select(agent_episodes_table)
                .where(where_clause)
                .order_by(desc(agent_episodes_table.c.created_at), desc(agent_episodes_table.c.id))
                .offset(safe_offset)
                .limit(safe_limit)
            ).all()
            items = [self._row_to_episode(row) for row in rows]
        return AgentEpisodePage(items=items, total=total, offset=safe_offset, limit=safe_limit)

    def apply_retention(self, *, cutoff: datetime) -> int:
        cutoff_naive = _as_utc_naive(cutoff)
        with self.db.get_session() as session:
            result = session.execute(
                delete(agent_episodes_table).where(
                    agent_episodes_table.c.created_at < cutoff_naive
                )
            )
            session.commit()
            return int(result.rowcount or 0)

    def apply_capacity(self, *, max_rows: int) -> int:
        bound = int(max_rows)
        if bound < 1:
            raise ValueError("agent episode capacity must be at least one row")
        with self.db.get_session() as session:
            total = int(
                session.execute(select(func.count()).select_from(agent_episodes_table)).scalar()
                or 0
            )
            excess = total - bound
            if excess <= 0:
                return 0
            oldest_ids = list(
                session.execute(
                    select(agent_episodes_table.c.id)
                    .order_by(
                        agent_episodes_table.c.created_at.asc(),
                        agent_episodes_table.c.id.asc(),
                    )
                    .limit(excess)
                ).scalars()
            )
            if not oldest_ids:
                return 0
            result = session.execute(
                delete(agent_episodes_table).where(agent_episodes_table.c.id.in_(list(oldest_ids)))
            )
            session.commit()
            return int(result.rowcount or 0)

    def list_for_replay(self, episode_ids: Sequence[str]) -> List[AgentEpisode]:
        keys = [str(item).strip() for item in episode_ids if str(item).strip()]
        if not keys:
            return []
        with self.db.get_session() as session:
            rows = session.execute(
                select(agent_episodes_table).where(agent_episodes_table.c.episode_id.in_(keys))
            ).all()
        by_id = {}
        for row in rows:
            episode = self._row_to_episode(row)
            by_id[episode.episode_id] = episode
        return [by_id[key] for key in keys if key in by_id]
