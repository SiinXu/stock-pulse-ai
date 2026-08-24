# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""SQLite sidecar store for research-only episode forward-return buckets.

Issue #1096 first slice: latest-row upsert keyed by canonical ``episode_id``
plus allowlisted horizon. This repository never ``UPDATE``s append-only
``agent_episodes`` and never writes ``prediction_outcome``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select, update

from src.repositories.agent_forward_return_tables import (
    agent_episode_forward_returns_table,
)
from src.repositories.base import BaseRepository
from src.schemas.memory_provenance import (
    PROVENANCE_SOURCE_SYSTEM_RESOLVE,
    apply_server_provenance,
    reject_client_provenance_keys,
)
from src.storage import DatabaseManager, utc_naive_now


FORWARD_RETURN_HORIZONS = frozenset({"1d", "5d"})
FORWARD_RETURN_BUCKETS = frozenset(
    {
        "1d_up",
        "1d_down",
        "1d_flat",
        "5d_up",
        "5d_down",
        "5d_flat",
    }
)


@dataclass(frozen=True)
class AgentForwardReturnRecord:
    """Detached latest-row forward-return sidecar."""

    episode_id: str
    run_id: str
    horizon: str
    forward_return_bucket: str
    provenance_source: Optional[str]
    actor_id: Optional[str]
    created_at: datetime
    updated_at: datetime


def validate_forward_return_bucket(bucket: str, *, horizon: Optional[str] = None) -> str:
    """Reject unknown bucket strings. Research-only; not trading advice."""
    canonical = str(bucket or "").strip().lower()
    if canonical not in FORWARD_RETURN_BUCKETS:
        raise ValueError(f"unsupported forward_return_bucket: {bucket!r}")
    derived_horizon = canonical.split("_", 1)[0]
    if horizon is not None:
        expected = str(horizon or "").strip().lower()
        if expected not in FORWARD_RETURN_HORIZONS:
            raise ValueError(f"unsupported forward-return horizon: {horizon!r}")
        if derived_horizon != expected:
            raise ValueError(
                "forward_return_bucket does not match horizon: "
                f"{canonical} vs {expected}"
            )
    return canonical


def validate_forward_return_horizon(horizon: str) -> str:
    canonical = str(horizon or "").strip().lower()
    if canonical not in FORWARD_RETURN_HORIZONS:
        raise ValueError(f"unsupported forward-return horizon: {horizon!r}")
    return canonical


def _row_to_record(row: Any) -> AgentForwardReturnRecord:
    return AgentForwardReturnRecord(
        episode_id=str(row.episode_id),
        run_id=str(row.run_id),
        horizon=str(row.horizon),
        forward_return_bucket=str(row.forward_return_bucket),
        provenance_source=row.provenance_source,
        actor_id=row.actor_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AgentForwardReturnRepository(BaseRepository):
    """Persist optional forward-return buckets without mutating episodes."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        super().__init__(db_manager)

    def get_by_episode_horizon(
        self,
        episode_id: str,
        horizon: str,
    ) -> Optional[AgentForwardReturnRecord]:
        key = str(episode_id or "").strip()
        if not key:
            return None
        canonical_horizon = validate_forward_return_horizon(horizon)
        with self.db.get_session() as session:
            row = session.execute(
                select(agent_episode_forward_returns_table)
                .where(agent_episode_forward_returns_table.c.episode_id == key)
                .where(agent_episode_forward_returns_table.c.horizon == canonical_horizon)
                .limit(1)
            ).one_or_none()
        return _row_to_record(row) if row is not None else None

    def list_by_run_id(self, run_id: str) -> List[AgentForwardReturnRecord]:
        key = str(run_id or "").strip()
        if not key:
            return []
        with self.db.get_session() as session:
            rows = session.execute(
                select(agent_episode_forward_returns_table)
                .where(agent_episode_forward_returns_table.c.run_id == key)
                .order_by(
                    agent_episode_forward_returns_table.c.episode_id,
                    agent_episode_forward_returns_table.c.horizon,
                )
            ).all()
        return [_row_to_record(row) for row in rows]

    def upsert(
        self,
        *,
        episode_id: str,
        run_id: str,
        horizon: str,
        forward_return_bucket: str,
    ) -> AgentForwardReturnRecord:
        canonical_episode = str(episode_id or "").strip()
        canonical_run = str(run_id or "").strip()
        if not canonical_episode:
            raise ValueError("episode_id is required")
        if not canonical_run:
            raise ValueError("run_id is required")
        canonical_horizon = validate_forward_return_horizon(horizon)
        canonical_bucket = validate_forward_return_bucket(
            forward_return_bucket,
            horizon=canonical_horizon,
        )
        reject_client_provenance_keys(
            {
                "forward_return_bucket": canonical_bucket,
            }
        )
        stamped = apply_server_provenance(
            {"forward_return_bucket": canonical_bucket},
            provenance_source=PROVENANCE_SOURCE_SYSTEM_RESOLVE,
            actor_id=None,
        )
        now = utc_naive_now()
        persist = {
            "episode_id": canonical_episode,
            "run_id": canonical_run,
            "horizon": canonical_horizon,
            "forward_return_bucket": stamped["forward_return_bucket"],
            "provenance_source": stamped["provenance_source"],
            "actor_id": stamped["actor_id"],
        }
        table = agent_episode_forward_returns_table
        with self.db.get_session() as session:
            existing = session.execute(
                select(table)
                .where(table.c.episode_id == canonical_episode)
                .where(table.c.horizon == canonical_horizon)
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
                    .where(table.c.horizon == canonical_horizon)
                    .values(
                        run_id=canonical_run,
                        forward_return_bucket=persist["forward_return_bucket"],
                        provenance_source=persist["provenance_source"],
                        actor_id=persist["actor_id"],
                        updated_at=now,
                    )
                )
            session.commit()
        record = self.get_by_episode_horizon(canonical_episode, canonical_horizon)
        if record is None:
            raise RuntimeError(
                "forward-return upsert committed but row is missing for "
                f"episode_id={canonical_episode} horizon={canonical_horizon}"
            )
        return record
