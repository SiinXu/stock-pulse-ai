# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Optional run and prediction user-feedback writes (Issue #1105).

Opinion lives in sidecar tables. Resolver actuals, prediction status, and
append-only episodes are never rewritten. Missing feedback does not block
automatic resolve or evolution. Parent identity keys stay in the URL path.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from src.repositories.agent_feedback_repo import (
    AgentFeedbackRecord,
    AgentFeedbackRepository,
)
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.repositories.analysis_repo import AnalysisRepository
from src.schemas.agent_prediction import STATUS_RESOLVED
from src.schemas.memory_provenance import (
    FEEDBACK_ACTOR_ID,
    PROVENANCE_SOURCE_USER_FEEDBACK,
)
from src.schemas.memory_write_guard import (
    FEEDBACK_NOTE_MAX_LENGTH,
    reject_memory_write_text,
)
from src.schemas.memory_write_policy import require_opinion_write
from src.storage import DatabaseManager


RUN_FEEDBACK_VALUES = frozenset({"useful", "partial", "wrong", "harmful"})
PREDICTION_FEEDBACK_VALUES = frozenset(
    {"agree_hit", "agree_miss", "disagree_score", "context_note"}
)
FEEDBACK_SOURCES = frozenset({"web", "api"})
_ID_MAX_LENGTH = 128


class AgentFeedbackError(Exception):
    """Base error for optional agent feedback writes."""


class AgentFeedbackNotFoundError(AgentFeedbackError):
    """Raised when the requested run or prediction identity does not exist."""


class AgentFeedbackUnresolvedError(AgentFeedbackError):
    """Raised when prediction feedback is written before the row is resolved."""


class AgentFeedbackService:
    """Validate opinion payloads and upsert sidecar rows."""

    def __init__(
        self,
        *,
        repo: Optional[AgentFeedbackRepository] = None,
        prediction_repo: Optional[AgentPredictionRepository] = None,
        analysis_repo: Optional[AnalysisRepository] = None,
        db_manager: Optional[DatabaseManager] = None,
    ) -> None:
        self.repo = repo or AgentFeedbackRepository(db_manager)
        self.prediction_repo = prediction_repo or AgentPredictionRepository(db_manager)
        self.analysis_repo = analysis_repo or AnalysisRepository(db_manager)

    def get_run_feedback(self, run_id: str) -> Dict[str, Any]:
        canonical = self._canonical_id(run_id, field_name="run_id")
        self._require_run_parent(canonical)
        row = self.repo.get_run_feedback(canonical)
        return self._serialize(row, subject_field="run_id", subject_id=canonical)

    def get_prediction_feedback(self, prediction_id: str) -> Dict[str, Any]:
        canonical = self._canonical_id(prediction_id, field_name="prediction_id")
        self._require_prediction_parent(canonical)
        row = self.repo.get_prediction_feedback(canonical)
        return self._serialize(
            row, subject_field="prediction_id", subject_id=canonical
        )

    def put_run_feedback(
        self,
        run_id: str,
        *,
        feedback_value: str,
        note: Optional[str] = None,
        source: str = "api",
    ) -> Dict[str, Any]:
        canonical = self._canonical_id(run_id, field_name="run_id")
        self._require_run_parent(canonical)
        fields = self._opinion_fields(
            feedback_value=feedback_value,
            allowed=RUN_FEEDBACK_VALUES,
            note=note,
            source=source,
        )
        row = self.repo.upsert_run_feedback(canonical, fields)
        return self._serialize(row, subject_field="run_id", subject_id=canonical)

    def put_prediction_feedback(
        self,
        prediction_id: str,
        *,
        feedback_value: str,
        note: Optional[str] = None,
        source: str = "api",
    ) -> Dict[str, Any]:
        canonical = self._canonical_id(prediction_id, field_name="prediction_id")
        parent = self._require_prediction_parent(canonical)
        if parent.status != STATUS_RESOLVED:
            raise AgentFeedbackUnresolvedError(
                f"Prediction is not resolved: {canonical}"
            )
        fields = self._opinion_fields(
            feedback_value=feedback_value,
            allowed=PREDICTION_FEEDBACK_VALUES,
            note=note,
            source=source,
        )
        row = self.repo.upsert_prediction_feedback(
            canonical,
            fields,
            run_id=parent.run_id,
        )
        return self._serialize(
            row, subject_field="prediction_id", subject_id=canonical
        )

    def _require_run_parent(self, run_id: str) -> None:
        if self.prediction_repo.list_by_run_id(run_id, limit=1):
            return
        if self.analysis_repo.get_by_query_id(run_id) is not None:
            return
        raise AgentFeedbackNotFoundError(f"Run not found: {run_id}")

    def _require_prediction_parent(self, prediction_id: str):
        parent = self.prediction_repo.get(prediction_id)
        if parent is None:
            raise AgentFeedbackNotFoundError(f"Prediction not found: {prediction_id}")
        return parent

    @staticmethod
    def _canonical_id(value: Any, *, field_name: str) -> str:
        token = str(value or "").strip()
        if not token:
            raise ValueError(f"{field_name} is required")
        if any(char.isspace() for char in token):
            raise ValueError(f"{field_name} must not contain whitespace")
        if len(token) > _ID_MAX_LENGTH:
            raise ValueError(f"{field_name} must be at most {_ID_MAX_LENGTH} characters")
        return token

    @staticmethod
    def _normalize_enum(value: Any, allowed: Iterable[str], field_name: str) -> str:
        text = str(value or "").strip()
        allowed_set = set(allowed)
        if text not in allowed_set:
            allowed_text = ", ".join(sorted(allowed_set))
            raise ValueError(f"{field_name} must be one of {allowed_text}")
        return text

    def _opinion_fields(
        self,
        *,
        feedback_value: str,
        allowed: Iterable[str],
        note: Optional[str],
        source: str,
    ) -> Dict[str, Any]:
        reject_memory_write_text(
            note,
            field_name="note",
            max_length=FEEDBACK_NOTE_MAX_LENGTH,
        )
        normalized_note: Optional[str]
        if note in (None, ""):
            normalized_note = None
        else:
            normalized_note = str(note)
        fields: Dict[str, Any] = {
            "feedback_value": self._normalize_enum(
                feedback_value, allowed, "feedback_value"
            ),
            "note": normalized_note,
            "source": self._normalize_enum(source or "api", FEEDBACK_SOURCES, "source"),
        }
        require_opinion_write(
            fields,
            provenance_source=PROVENANCE_SOURCE_USER_FEEDBACK,
            actor_id=FEEDBACK_ACTOR_ID,
        )
        return fields

    @staticmethod
    def _serialize(
        row: Optional[AgentFeedbackRecord],
        *,
        subject_field: str,
        subject_id: str,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            subject_field: subject_id,
            "feedback_value": None,
            "note": None,
            "source": None,
            "provenance_source": None,
            "actor_id": None,
            "created_at": None,
            "updated_at": None,
        }
        if row is None:
            return payload
        payload.update(
            {
                "feedback_value": row.feedback_value,
                "note": row.note,
                "source": row.source,
                "provenance_source": row.provenance_source,
                "actor_id": row.actor_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        )
        return payload
