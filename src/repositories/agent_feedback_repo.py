# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""SQLite sidecar store for optional run and prediction user feedback.

Issue #1105: latest-row upsert keyed by canonical ``run_id`` or
``prediction_id``. This repository never writes ``agent_predictions`` status,
outcome, actuals, or ``resolved_at``, and never ``UPDATE``s append-only
``agent_episodes``. Parent identity keys stay off the opinion payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Mapping, Optional

from sqlalchemy import select, update

from src.repositories.agent_feedback_tables import (
    agent_prediction_feedback_table,
    agent_run_feedback_table,
)
from src.repositories.base import BaseRepository
from src.schemas.memory_provenance import (
    FEEDBACK_ACTOR_ID,
    PROVENANCE_SOURCE_USER_FEEDBACK,
)
from src.schemas.memory_write_policy import require_opinion_write
from src.storage import DatabaseManager, utc_naive_now


@dataclass(frozen=True)
class AgentFeedbackRecord:
    """Detached latest-row feedback sidecar."""

    subject_id: str
    feedback_value: str
    note: Optional[str]
    source: str
    provenance_source: Optional[str]
    actor_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    run_id: Optional[str] = None


_OPINION_KEYS = frozenset({"feedback_value", "note", "source"})


def _row_to_record(row: Any, *, subject_field: str) -> AgentFeedbackRecord:
    run_id = getattr(row, "run_id", None) if subject_field == "prediction_id" else None
    return AgentFeedbackRecord(
        subject_id=str(getattr(row, subject_field)),
        feedback_value=str(row.feedback_value),
        note=row.note,
        source=str(row.source),
        provenance_source=row.provenance_source,
        actor_id=row.actor_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        run_id=None if run_id is None else str(run_id),
    )


def _opinion_fields(fields: Mapping[str, Any]) -> Dict[str, Any]:
    decision, stamped = require_opinion_write(
        fields,
        provenance_source=PROVENANCE_SOURCE_USER_FEEDBACK,
        actor_id=FEEDBACK_ACTOR_ID,
    )
    extra = tuple(sorted(str(key) for key in fields if str(key) not in _OPINION_KEYS))
    if extra:
        raise ValueError(
            "feedback persist mapping cannot include identity or extra keys: "
            + ", ".join(extra)
        )
    persist = {str(key): stamped[key] for key in _OPINION_KEYS if key in stamped}
    persist["provenance_source"] = decision.provenance_source
    persist["actor_id"] = decision.actor_id
    return persist


class AgentFeedbackRepository(BaseRepository):
    """Persist optional user opinion without mutating resolver actuals."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        super().__init__(db_manager)

    def get_run_feedback(self, run_id: str) -> Optional[AgentFeedbackRecord]:
        key = str(run_id or "").strip()
        if not key:
            return None
        with self.db.get_session() as session:
            row = session.execute(
                select(agent_run_feedback_table)
                .where(agent_run_feedback_table.c.run_id == key)
                .limit(1)
            ).one_or_none()
        return _row_to_record(row, subject_field="run_id") if row is not None else None

    def get_prediction_feedback(self, prediction_id: str) -> Optional[AgentFeedbackRecord]:
        key = str(prediction_id or "").strip()
        if not key:
            return None
        with self.db.get_session() as session:
            row = session.execute(
                select(agent_prediction_feedback_table)
                .where(agent_prediction_feedback_table.c.prediction_id == key)
                .limit(1)
            ).one_or_none()
        return (
            _row_to_record(row, subject_field="prediction_id")
            if row is not None
            else None
        )

    def upsert_run_feedback(self, run_id: str, fields: Mapping[str, Any]) -> AgentFeedbackRecord:
        return self._upsert(
            table=agent_run_feedback_table,
            key_field="run_id",
            key=run_id,
            fields=fields,
        )

    def upsert_prediction_feedback(
        self,
        prediction_id: str,
        fields: Mapping[str, Any],
        *,
        run_id: str,
    ) -> AgentFeedbackRecord:
        copied_run_id = str(run_id or "").strip()
        if not copied_run_id:
            raise ValueError("run_id is required when persisting prediction feedback")
        return self._upsert(
            table=agent_prediction_feedback_table,
            key_field="prediction_id",
            key=prediction_id,
            fields=fields,
            extra_values={"run_id": copied_run_id},
        )

    def _upsert(
        self,
        *,
        table: Any,
        key_field: str,
        key: str,
        fields: Mapping[str, Any],
        extra_values: Optional[Mapping[str, Any]] = None,
    ) -> AgentFeedbackRecord:
        canonical = str(key or "").strip()
        if not canonical:
            raise ValueError(f"{key_field} is required")
        opinion = _opinion_fields(fields)
        now = utc_naive_now()
        persist: Dict[str, Any] = {
            key_field: canonical,
            "feedback_value": opinion["feedback_value"],
            "note": opinion.get("note"),
            "source": opinion.get("source") or "api",
            "provenance_source": opinion["provenance_source"],
            "actor_id": opinion["actor_id"],
        }
        if extra_values:
            persist.update(dict(extra_values))
        with self.db.get_session() as session:
            existing = session.execute(
                select(table).where(getattr(table.c, key_field) == canonical).limit(1)
            ).one_or_none()
            if existing is None:
                persist["created_at"] = now
                persist["updated_at"] = now
                session.execute(table.insert().values(**persist))
            else:
                values = {
                    "feedback_value": persist["feedback_value"],
                    "note": persist["note"],
                    "source": persist["source"],
                    "provenance_source": persist["provenance_source"],
                    "actor_id": persist["actor_id"],
                    "updated_at": now,
                }
                if extra_values:
                    values.update(dict(extra_values))
                session.execute(
                    update(table)
                    .where(getattr(table.c, key_field) == canonical)
                    .values(**values)
                )
            session.commit()
        record = (
            self.get_run_feedback(canonical)
            if key_field == "run_id"
            else self.get_prediction_feedback(canonical)
        )
        if record is None:
            raise RuntimeError(
                f"agent feedback upsert committed but row is missing for {key_field}"
            )
        return record
