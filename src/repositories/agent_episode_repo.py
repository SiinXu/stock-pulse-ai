# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Append and query access for agent evolution episode logs (Issue #1090)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Callable, List, Optional, Sequence

from sqlalchemy import and_, delete, desc, func, select, text
from sqlalchemy.exc import IntegrityError

from src.repositories.agent_episode_tables import agent_episodes_table
from src.repositories.agent_evolution_event_repo import insert_evolution_event_on_session
from src.repositories.base import BaseRepository, RepositoryError
from src.schemas.evolution_event import EvolutionEventCreate
from src.schemas.memory_forget_policy import (
    EPISODE_FORGET_EVENT_TYPE,
    ERROR_FORGET_INVALID_POLICY,
    ERROR_FORGET_UNSCOPED,
    EpisodeForgetDecision,
    EpisodeForgetResult,
    MemoryForgetError,
    require_episode_forget_policy,
)
from src.schemas.memory_write_policy import require_episodic_write
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


def _json_loads(raw: Optional[str], *, field: str, expected_type: type) -> Any:
    if raw is None or raw == "":
        raise RepositoryError(
            f"agent episode {field} JSON is missing",
            error_code="agent_episode_corrupt_json",
            context={"field": field},
        )
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RepositoryError(
            f"agent episode {field} JSON is invalid",
            error_code="agent_episode_corrupt_json",
            context={"field": field},
        ) from exc
    if not isinstance(parsed, expected_type):
        raise RepositoryError(
            f"agent episode {field} JSON has the wrong shape",
            error_code="agent_episode_corrupt_json",
            context={"field": field},
        )
    return parsed


def _as_utc_aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError("timestamp must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError("timestamp must be a datetime")
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _bounded_int(name: str, value: Any, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


SQLITE_DEFAULT_MAX_VARIABLE_NUMBER = 999
FORGET_DELETE_EXTRA_BINDS = 1


def sqlite_max_variable_number(session: Any) -> int:
    """Return SQLite ``MAX_VARIABLE_NUMBER``, or the historical default of 999."""
    try:
        rows = session.execute(text("PRAGMA compile_options")).fetchall()
    except Exception:  # broad-exception: fallback_recorded - unknown compile_options still chunk at the historical SQLite bind default
        return SQLITE_DEFAULT_MAX_VARIABLE_NUMBER
    for row in rows:
        option = str(row[0] if row is not None else "")
        if option.upper().startswith("MAX_VARIABLE_NUMBER="):
            try:
                value = int(option.split("=", 1)[1])
            except (IndexError, ValueError):
                break
            if value >= 2:
                return value
            break
    return SQLITE_DEFAULT_MAX_VARIABLE_NUMBER


def forget_id_in_chunk_size(
    session: Any,
    *,
    configured: Optional[int] = None,
) -> int:
    """Max ids per ``DELETE ... id IN (...)`` while reserving one bind for symbol.

    Never exceeds the live SQLite variable ceiling. A configured test bound may
    only shrink the chunk; it cannot raise the SQLite limit.
    """
    detected = sqlite_max_variable_number(session) - FORGET_DELETE_EXTRA_BINDS
    if detected < 1:
        detected = 1
    if configured is None:
        return detected
    if type(configured) is not int or configured < 1:
        raise ValueError("forget_id_chunk_size must be a positive integer")
    return configured if configured <= detected else detected


class AgentEpisodeRepository(BaseRepository):
    """The only persistence boundary for the append-oriented episode table."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        clock: Callable[[], datetime] = _utc_naive_now,
        forget_id_chunk_size: Optional[int] = None,
    ) -> None:
        super().__init__(db_manager)
        self._clock = clock
        if forget_id_chunk_size is not None:
            if type(forget_id_chunk_size) is not int or forget_id_chunk_size < 1:
                raise ValueError("forget_id_chunk_size must be a positive integer")
        self._forget_id_chunk_size = forget_id_chunk_size

    @staticmethod
    def _row_to_episode(row: Any) -> AgentEpisode:
        trajectory_raw = _json_loads(
            row.trajectory_summary_json,
            field="trajectory_summary",
            expected_type=list,
        )
        lessons_raw = _json_loads(
            row.lessons_json,
            field="lessons",
            expected_type=list,
        )
        outcome_raw = (
            _json_loads(
                row.outcome_labels_json,
                field="outcome_labels",
                expected_type=dict,
            )
            if row.outcome_labels_json
            else None
        )
        if any(not isinstance(item, dict) for item in trajectory_raw):
            raise RepositoryError(
                "agent episode trajectory_summary JSON contains a non-object",
                error_code="agent_episode_corrupt_json",
                context={"field": "trajectory_summary"},
            )
        if any(not isinstance(item, dict) for item in lessons_raw):
            raise RepositoryError(
                "agent episode lessons JSON contains a non-object",
                error_code="agent_episode_corrupt_json",
                context={"field": "lessons"},
            )
        trajectory = [
            TrajectoryStepSummary.model_validate(item)
            for item in trajectory_raw
        ]
        lessons = [
            EpisodeLesson.model_validate(item)
            for item in lessons_raw
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
                "provenance_source": row.provenance_source,
                "actor_id": row.actor_id,
            }
        )

    def append(self, episode: AgentEpisodeCreate) -> AgentEpisode:
        stamp = require_episodic_write(episode).stamp_mapping()
        now = _as_utc_naive(self._clock())
        if now is None:
            raise ValueError("agent episode clock must return a datetime")
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
            "provenance_source": stamp["provenance_source"],
            "actor_id": stamp["actor_id"],
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
            if existing is not None and existing.model_dump(
                mode="json",
                exclude={"id", "created_at", "provenance_source", "actor_id"},
            ) == episode.model_dump(mode="json"):
                return existing
            if existing is not None:
                raise RepositoryError(
                    "agent episode id is already bound to a different payload",
                    error_code="agent_episode_id_collision",
                    context={"episode_id": episode.episode_id},
                ) from exc
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

    def get_by_run_id(
        self,
        run_id: str,
        *,
        limit: int = AGENT_EPISODE_MAX_PAGE_SIZE,
    ) -> List[AgentEpisode]:
        key = str(run_id or "").strip()
        if not key:
            return []
        bound = _bounded_int(
            "limit",
            limit,
            minimum=1,
            maximum=AGENT_EPISODE_MAX_PAGE_SIZE,
        )
        with self.db.get_session() as session:
            rows = session.execute(
                select(agent_episodes_table)
                .where(agent_episodes_table.c.run_id == key)
                .order_by(desc(agent_episodes_table.c.created_at), desc(agent_episodes_table.c.id))
                .limit(bound)
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
        safe_limit = _bounded_int(
            "limit",
            limit,
            minimum=1,
            maximum=AGENT_EPISODE_MAX_PAGE_SIZE,
        )
        safe_offset = _bounded_int(
            "offset",
            offset,
            minimum=0,
            maximum=1_000_000_000,
        )
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

    @staticmethod
    def _count_remaining(session: Any, symbol: Optional[str]) -> int:
        stmt = select(func.count()).select_from(agent_episodes_table)
        if symbol:
            stmt = stmt.where(agent_episodes_table.c.symbol == symbol)
        return int(session.execute(stmt).scalar() or 0)

    def _collect_forget_ids(
        self,
        session: Any,
        *,
        symbol: str,
        cutoff_naive: Optional[datetime],
        max_rows: Optional[int],
    ) -> tuple[list[int], list[int]]:
        scoped = agent_episodes_table.c.symbol == symbol
        id_rows = list(
            session.execute(
                select(
                    agent_episodes_table.c.id,
                    agent_episodes_table.c.created_at,
                )
                .where(scoped)
                .order_by(
                    agent_episodes_table.c.created_at.asc(),
                    agent_episodes_table.c.id.asc(),
                )
            )
        )
        delete_ids: list[int] = []
        kept_ids: list[int] = []
        for row in id_rows:
            created = row.created_at
            if cutoff_naive is not None:
                try:
                    created_naive = _as_utc_naive(created)
                except ValueError:
                    kept_ids.append(int(row.id))
                    continue
                if created_naive is not None and created_naive < cutoff_naive:
                    delete_ids.append(int(row.id))
                    continue
            kept_ids.append(int(row.id))
        if max_rows is not None and len(kept_ids) > max_rows:
            overflow = len(kept_ids) - max_rows
            delete_ids.extend(kept_ids[:overflow])
            kept_ids = kept_ids[overflow:]
        return delete_ids, kept_ids

    def _audit_forget_on_session(
        self,
        session: Any,
        *,
        symbol: str,
        before_count: int,
        after_count: int,
        deleted_ids: list[int],
        cutoff: Optional[datetime],
        max_rows: Optional[int],
    ) -> str:
        fingerprint = hashlib.sha256(
            ",".join(str(item) for item in sorted(deleted_ids)).encode("utf-8")
        ).hexdigest()
        after: dict[str, Any] = {
            "count": after_count,
            "deleted_count": len(deleted_ids),
            "deleted_id_sha256": fingerprint,
            "symbol": symbol,
        }
        if cutoff is not None:
            after["cutoff"] = cutoff.replace(tzinfo=timezone.utc).isoformat()
        if max_rows is not None:
            after["max_rows"] = max_rows
        occurred = self._clock()
        if occurred.tzinfo is None or occurred.utcoffset() is None:
            occurred_at = occurred.replace(tzinfo=timezone.utc)
            created_at = occurred
        else:
            occurred_at = occurred.astimezone(timezone.utc)
            created_at = occurred_at.replace(tzinfo=None)
        event = EvolutionEventCreate.model_validate(
            {
                "event_type": EPISODE_FORGET_EVENT_TYPE,
                "actor": "system",
                "occurred_at": occurred_at,
                "before": {"count": before_count, "symbol": symbol},
                "after": after,
            }
        )
        return insert_evolution_event_on_session(session, event, created_at=created_at)

    def _delete_symbol_ids(
        self,
        session: Any,
        *,
        symbol: str,
        delete_ids: list[int],
    ) -> int:
        if not delete_ids:
            return 0
        chunk_size = forget_id_in_chunk_size(
            session, configured=self._forget_id_chunk_size
        )
        deleted = 0
        scoped = agent_episodes_table.c.symbol == symbol
        for offset in range(0, len(delete_ids), chunk_size):
            chunk = delete_ids[offset : offset + chunk_size]
            result = session.execute(
                delete(agent_episodes_table).where(
                    and_(
                        scoped,
                        agent_episodes_table.c.id.in_(list(chunk)),
                    )
                )
            )
            deleted += int(result.rowcount or 0)
        return deleted

    def apply_forget(self, decision: EpisodeForgetDecision) -> EpisodeForgetResult:
        """Delete in-scope episode rows for one symbol in a single transaction.

        Age uses a strict ``created_at < cutoff`` boundary (equality is kept).
        Capacity keeps the newest ``max_rows`` rows of that symbol after TTL.
        No-policy decisions delete nothing and still return a live remaining
        COUNT. Invalid or unscoped decisions raise and do not write. Dry-run
        counts without deleting and does not write an EvolutionEvent. Real
        deletes insert one metadata-only EvolutionEvent in the same
        ``session_scope`` before DELETE. Id lists are chunked so each
        ``DELETE ... id IN (...)`` stays within SQLite's bind limit (one extra
        bind is reserved for ``symbol``). Chunks do not commit separately;
        audit or chunk failure rolls back the whole pass. SQLite serializes
        writers; this pass does not use SELECT FOR UPDATE.
        """
        if not isinstance(decision, EpisodeForgetDecision):
            raise MemoryForgetError(
                "episode forget requires a resolved policy decision",
                error_code=ERROR_FORGET_INVALID_POLICY,
            )
        if decision.error_code:
            raise MemoryForgetError(
                decision.reason or "invalid episode forget policy",
                error_code=decision.error_code,
            )
        symbol = str(decision.symbol or "").strip() or None
        if decision.apply and not symbol:
            raise MemoryForgetError(
                "forgetting requires an explicit symbol scope",
                error_code=ERROR_FORGET_UNSCOPED,
            )
        cutoff_naive = (
            _as_utc_naive(decision.cutoff) if decision.cutoff is not None else None
        )
        try:
            if not decision.apply:
                with self.db.get_session() as session:
                    remaining = self._count_remaining(session, symbol)
                return EpisodeForgetResult(
                    applied=False,
                    symbol=symbol,
                    deleted_count=0,
                    remaining_count=remaining,
                    cutoff=decision.cutoff,
                    max_rows=decision.max_rows,
                    dry_run=bool(decision.dry_run),
                )
            assert symbol is not None
            if decision.dry_run:
                with self.db.get_session() as session:
                    delete_ids, kept_ids = self._collect_forget_ids(
                        session,
                        symbol=symbol,
                        cutoff_naive=cutoff_naive,
                        max_rows=decision.max_rows,
                    )
                return EpisodeForgetResult(
                    applied=True,
                    symbol=symbol,
                    deleted_count=len(delete_ids),
                    remaining_count=len(kept_ids),
                    cutoff=cutoff_naive,
                    max_rows=decision.max_rows,
                    dry_run=True,
                )
            with self.db.session_scope() as session:
                delete_ids, kept_ids = self._collect_forget_ids(
                    session,
                    symbol=symbol,
                    cutoff_naive=cutoff_naive,
                    max_rows=decision.max_rows,
                )
                before_count = len(delete_ids) + len(kept_ids)
                audit_event_id = None
                deleted_count = 0
                if delete_ids:
                    audit_event_id = self._audit_forget_on_session(
                        session,
                        symbol=symbol,
                        before_count=before_count,
                        after_count=len(kept_ids),
                        deleted_ids=delete_ids,
                        cutoff=cutoff_naive,
                        max_rows=decision.max_rows,
                    )
                    deleted_count = self._delete_symbol_ids(
                        session, symbol=symbol, delete_ids=delete_ids
                    )
                    if deleted_count != len(delete_ids):
                        raise RepositoryError(
                            "episode forget deleted a different row set than selected",
                            error_code="agent_episode_forget_conflict",
                            context={
                                "symbol": symbol,
                                "selected": len(delete_ids),
                                "deleted": deleted_count,
                            },
                        )
                remaining = self._count_remaining(session, symbol)
                return EpisodeForgetResult(
                    applied=True,
                    symbol=symbol,
                    deleted_count=deleted_count,
                    remaining_count=remaining,
                    cutoff=cutoff_naive,
                    max_rows=decision.max_rows,
                    dry_run=False,
                    audit_event_id=audit_event_id,
                )
        except MemoryForgetError:
            raise
        except Exception as exc:
            self._log_and_raise(
                logger,
                "agent_episode_forget_failed",
                exc,
                error_code="agent_episode_forget_failed",
                context={"symbol": symbol, "dry_run": bool(decision.dry_run)},
            )

    def apply_retention(self, *, cutoff: datetime, symbol: Optional[str] = None) -> int:
        """Compatibility wrapper. Unscoped calls fail closed; never a global purge."""
        return self.apply_forget(
            require_episode_forget_policy(symbol=symbol, cutoff=cutoff)
        ).deleted_count

    def apply_capacity(self, *, max_rows: int, symbol: Optional[str] = None) -> int:
        """Compatibility wrapper. Unscoped calls fail closed; never a global purge."""
        return self.apply_forget(
            require_episode_forget_policy(symbol=symbol, max_rows=max_rows)
        ).deleted_count

    def list_for_replay(self, episode_ids: Sequence[str]) -> List[AgentEpisode]:
        if isinstance(episode_ids, (str, bytes, bytearray)):
            raise ValueError("episode_ids must be a sequence of ids")
        raw_ids = list(episode_ids)
        if len(raw_ids) > AGENT_EPISODE_MAX_PAGE_SIZE:
            raise ValueError(
                f"episode_ids must contain at most {AGENT_EPISODE_MAX_PAGE_SIZE} ids"
            )
        keys = [str(item).strip() for item in raw_ids if str(item).strip()]
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
