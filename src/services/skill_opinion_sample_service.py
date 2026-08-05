# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Materialize immutable skill-opinion samples from persisted reports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
import json
import logging
import math
from typing import Any, Dict, List, Optional

from src.repositories.skill_opinion_sample_repo import (
    SkillOpinionSampleRepository,
)
from src.schemas.skill_opinion_outcome import (
    AnalysisHistoryProjection,
    CANONICAL_SKILL_SIGNALS,
    SkillOpinionInput,
    SkillOpinionSample,
)
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

SKILL_OPINION_SAMPLE_SCHEMA_VERSION = "skill-opinion-sample-v1"
_QUALITY_LEVELS = frozenset(
    {
        "good",
        "usable",
        "limited",
        "poor",
        "high",
        "medium",
        "low",
        "unknown",
    }
)



def is_skill_opinion_recording_enabled(config: Any = None) -> bool:
    """Return whether config-gated skill-opinion sample recording is on."""
    if config is None:
        from src.config import Config

        config = Config.get_instance()
    return bool(getattr(config, "skill_opinion_recording_enabled", False))


class SkillOpinionSampleService:
    """Validate and persist only low-sensitivity individual skill facts."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        repo: Optional[SkillOpinionSampleRepository] = None,
    ) -> None:
        self.repo = repo or SkillOpinionSampleRepository(db_manager)

    def persist(
        self,
        *,
        analysis_history_id: int,
        stock_code: str,
        opinions: Iterable[SkillOpinionInput],
        data_quality_level: Optional[str] = None,
    ) -> int:
        """Persist one validated immutable row per history and skill."""
        history_id = self._positive_int(
            analysis_history_id,
            "analysis_history_id",
        )
        code = str(stock_code or "").strip()
        if not code:
            raise ValueError("stock_code is required")
        if len(code) > 16:
            raise ValueError("stock_code exceeds 16 characters")

        quality = str(data_quality_level or "").strip().lower()
        if quality not in _QUALITY_LEVELS:
            quality = ""

        rows: List[Dict[str, Any]] = []
        seen_skill_ids = set()
        for opinion in opinions:
            validated = self._validated_opinion(opinion)
            if validated.skill_id in seen_skill_ids:
                raise ValueError(
                    "skill opinions must contain one row per skill_id"
                )
            seen_skill_ids.add(validated.skill_id)
            rows.append(
                {
                    "analysis_history_id": history_id,
                    "stock_code": code,
                    "skill_id": validated.skill_id,
                    "skill_version": validated.skill_version,
                    "signal": validated.signal,
                    "confidence": validated.confidence,
                    "horizon": validated.horizon,
                    "data_quality_level": quality or None,
                    "opinion_created_at": validated.observed_at,
                    "sample_schema_version": (
                        SKILL_OPINION_SAMPLE_SCHEMA_VERSION
                    ),
                }
            )
        return self.repo.insert_missing(rows)


    def record_from_agent_opinions(
        self,
        *,
        analysis_history_id: int,
        stock_code: str,
        opinions: Sequence[Any],
        data_quality_level: Optional[str] = None,
    ) -> int:
        """Map runtime skill opinions and persist low-sensitivity samples.

        Accepts ``AgentOpinion``-like objects or mappings with ``skill_id`` /
        ``signal`` / ``confidence``. Invalid or non-canonical rows are skipped
        rather than failing the analysis pipeline.
        """
        projected = self.project_agent_opinions(opinions)
        if not projected:
            return 0
        return self.persist(
            analysis_history_id=analysis_history_id,
            stock_code=stock_code,
            opinions=projected,
            data_quality_level=data_quality_level,
        )

    def maybe_materialize_after_history_save(
        self,
        analysis_history_id: int,
        *,
        config: Any = None,
    ) -> int:
        """Config-gated materialization after analysis history is saved.

        Failures are logged and never raised so history persistence remains
        isolated from the outcome data plane.
        """
        if not is_skill_opinion_recording_enabled(config):
            return 0
        try:
            return self.materialize_history(analysis_history_id)
        except Exception as exc:  # broad-exception: fallback_recorded - Sample materialization must never fail analysis history persistence.
            log_safe_exception(
                logger,
                "Skill opinion sample materialization after history save failed",
                exc,
                error_code="skill_opinion_sample_materialize_after_history_failed",
                level=logging.WARNING,
                context={"analysis_history_id": analysis_history_id},
            )
            return 0

    def list_recent_samples(
        self,
        *,
        skill_id: Optional[str] = None,
        stock_code: Optional[str] = None,
        analysis_history_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Return a bounded page of recent low-sensitivity samples."""
        limit_norm = self._bounded_positive_int(
            limit,
            "limit",
            maximum=200,
        )
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        history_id = (
            self._positive_int(analysis_history_id, "analysis_history_id")
            if analysis_history_id is not None
            else None
        )
        skill = (
            self._optional_text(skill_id, maximum=128)
            if skill_id is not None
            else None
        )
        code = (
            self._optional_text(stock_code, maximum=16)
            if stock_code is not None
            else None
        )
        if skill_id is not None and skill is None:
            raise ValueError("skill_id must not be blank")
        if stock_code is not None and code is None:
            raise ValueError("stock_code must not be blank")
        rows, total = self.repo.list_recent(
            skill_id=skill,
            stock_code=code,
            analysis_history_id=history_id,
            limit=limit_norm,
            offset=offset,
        )
        return {
            "items": [self._serialize_sample(row) for row in rows],
            "total": total,
            "limit": limit_norm,
            "offset": offset,
        }

    @classmethod
    def project_agent_opinions(
        cls,
        opinions: Sequence[Any],
    ) -> List[SkillOpinionInput]:
        """Project runtime opinions into validated low-sensitivity inputs."""
        projected: Dict[str, SkillOpinionInput] = {}
        for item in opinions or ():
            opinion = cls._project_runtime_opinion(item)
            if opinion is None:
                continue
            existing = projected.get(opinion.skill_id)
            if existing is not None and existing != opinion:
                continue
            projected[opinion.skill_id] = opinion
        return list(projected.values())

    @classmethod
    def _project_runtime_opinion(cls, item: Any) -> Optional[SkillOpinionInput]:
        if item is None:
            return None
        if isinstance(item, SkillOpinionInput):
            try:
                return cls._validated_opinion(item)
            except ValueError:
                return None
        if isinstance(item, Mapping):
            return cls._project_opinion(item)

        raw_data = getattr(item, "raw_data", None)
        raw_map = raw_data if isinstance(raw_data, Mapping) else {}
        skill_id = str(
            raw_map.get("skill_id")
            or getattr(item, "skill_id", "")
            or ""
        ).strip()
        if not skill_id:
            agent_name = str(getattr(item, "agent_name", "") or "").strip()
            if agent_name.startswith("skill_"):
                skill_id = agent_name[len("skill_") :]
            elif agent_name.startswith("strategy_"):
                skill_id = agent_name[len("strategy_") :]
        signal = str(
            getattr(item, "signal", None) or raw_map.get("signal") or ""
        ).strip().lower()
        confidence = getattr(item, "confidence", raw_map.get("confidence"))
        if (
            not skill_id
            or len(skill_id) > 128
            or signal not in CANONICAL_SKILL_SIGNALS
            or raw_map.get("invalid_signal") is True
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
        ):
            return None
        confidence_value = float(confidence)
        if (
            not math.isfinite(confidence_value)
            or not 0.0 <= confidence_value <= 1.0
        ):
            return None
        skill_version = cls._optional_text(
            raw_map.get("skill_version"),
            maximum=64,
        )
        horizon = cls._optional_text(raw_map.get("horizon"), maximum=16)
        return SkillOpinionInput(
            skill_id=skill_id,
            signal=signal,
            confidence=confidence_value,
            skill_version=skill_version,
            horizon=horizon,
        )

    @staticmethod
    def _serialize_sample(row: SkillOpinionSample) -> Dict[str, Any]:
        return {
            "id": row.id,
            "analysis_history_id": row.analysis_history_id,
            "stock_code": row.stock_code,
            "skill_id": row.skill_id,
            "skill_version": row.skill_version,
            "signal": row.signal,
            "confidence": row.confidence,
            "horizon": row.horizon,
            "data_quality_level": row.data_quality_level,
            "opinion_created_at": (
                row.opinion_created_at.isoformat()
                if isinstance(row.opinion_created_at, datetime)
                else None
            ),
            "sample_schema_version": row.sample_schema_version,
            "created_at": (
                row.created_at.isoformat()
                if isinstance(row.created_at, datetime)
                else None
            ),
        }

    def materialize_history(self, analysis_history_id: int) -> int:
        """Project canonical skill facts from one persisted analysis report."""
        history_id = self._positive_int(
            analysis_history_id,
            "analysis_history_id",
        )
        history = self.repo.get_history(history_id)
        if history is None:
            return 0
        return self._materialize(history)

    def materialize_pending(
        self,
        *,
        limit: int = 100,
        stock_code: Optional[str] = None,
    ) -> Dict[str, int]:
        """Materialize a bounded set of saved reports not yet projected."""
        limit_norm = self._bounded_positive_int(
            limit,
            "limit",
            maximum=500,
        )
        code = None
        if stock_code is not None:
            code = str(stock_code).strip()
            if not code:
                raise ValueError("stock_code must not be blank")
        histories = self.repo.list_unmaterialized_histories(
            sample_schema_version=SKILL_OPINION_SAMPLE_SCHEMA_VERSION,
            limit=limit_norm,
            stock_code=code,
        )
        created = sum(self._materialize(history) for history in histories)
        return {
            "histories_scanned": len(histories),
            "samples_created": created,
        }

    def _materialize(self, history: AnalysisHistoryProjection) -> int:
        opinions = self._opinions_from_raw_result(history.raw_result)
        if not opinions:
            return 0
        return self.persist(
            analysis_history_id=history.id,
            stock_code=history.stock_code,
            opinions=opinions,
            data_quality_level=self._data_quality_level(
                history.context_snapshot
            ),
        )

    @classmethod
    def _opinions_from_raw_result(
        cls,
        raw_result: Any,
    ) -> List[SkillOpinionInput]:
        payload = cls._mapping(raw_result)
        synthesis = cls._strategy_synthesis(payload)
        if synthesis is None:
            return []

        opinions: Dict[str, SkillOpinionInput] = {}
        for group_name in ("supporting_skills", "opposing_skills"):
            group = synthesis.get(group_name)
            if not isinstance(group, list):
                continue
            for item in group:
                opinion = cls._project_opinion(item)
                if opinion is None:
                    continue
                existing = opinions.get(opinion.skill_id)
                if existing is not None and existing != opinion:
                    raise ValueError(
                        "persisted strategy synthesis contains conflicting skill facts"
                    )
                opinions[opinion.skill_id] = opinion
        return list(opinions.values())

    @classmethod
    def _strategy_synthesis(
        cls,
        payload: Optional[Mapping[str, Any]],
    ) -> Optional[Mapping[str, Any]]:
        if payload is None:
            return None
        direct = payload.get("strategy_synthesis")
        if isinstance(direct, Mapping):
            return direct
        dashboard = payload.get("dashboard")
        if isinstance(dashboard, Mapping):
            nested = dashboard.get("strategy_synthesis")
            if isinstance(nested, Mapping):
                return nested
        raw_response = cls._mapping(payload.get("raw_response"))
        if raw_response is not None and raw_response is not payload:
            return cls._strategy_synthesis(raw_response)
        return None

    @staticmethod
    def _project_opinion(item: Any) -> Optional[SkillOpinionInput]:
        if not isinstance(item, Mapping):
            return None
        skill_id = str(item.get("skill_id") or "").strip()
        signal = str(item.get("signal") or "").strip().lower()
        confidence = item.get("confidence")
        if (
            not skill_id
            or len(skill_id) > 128
            or signal not in CANONICAL_SKILL_SIGNALS
            or item.get("invalid_signal") is True
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
        ):
            return None
        confidence_value = float(confidence)
        if (
            not math.isfinite(confidence_value)
            or not 0.0 <= confidence_value <= 1.0
        ):
            return None
        return SkillOpinionInput(
            skill_id=skill_id,
            signal=signal,
            confidence=confidence_value,
        )

    @classmethod
    def _data_quality_level(cls, context_snapshot: Any) -> Optional[str]:
        snapshot = cls._mapping(context_snapshot)
        if snapshot is None:
            return None
        overview = snapshot.get("analysis_context_pack_overview")
        if not isinstance(overview, Mapping):
            return None
        quality = overview.get("data_quality")
        if not isinstance(quality, Mapping):
            return None
        level = str(quality.get("level") or "").strip().lower()
        return level if level in _QUALITY_LEVELS else None

    @staticmethod
    def _mapping(value: Any) -> Optional[Mapping[str, Any]]:
        if isinstance(value, Mapping):
            return value
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, Mapping) else None

    @staticmethod
    def _validated_opinion(opinion: SkillOpinionInput) -> SkillOpinionInput:
        if not isinstance(opinion, SkillOpinionInput):
            raise ValueError("opinions must contain SkillOpinionInput values")
        skill_id = str(opinion.skill_id or "").strip()
        signal = str(opinion.signal or "").strip().lower()
        if not skill_id or signal not in CANONICAL_SKILL_SIGNALS:
            raise ValueError(
                "skill opinion requires a valid skill_id and canonical signal"
            )
        if len(skill_id) > 128:
            raise ValueError("skill_id exceeds 128 characters")
        if isinstance(opinion.confidence, bool):
            raise ValueError("skill opinion confidence must be numeric")
        try:
            confidence = float(opinion.confidence)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError(
                "skill opinion confidence must be numeric"
            ) from exc
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError(
                "skill opinion confidence must be between 0 and 1"
            )
        skill_version = SkillOpinionSampleService._optional_text(
            opinion.skill_version,
            maximum=64,
        )
        horizon = SkillOpinionSampleService._optional_text(
            opinion.horizon,
            maximum=16,
        )
        observed_at = opinion.observed_at
        if observed_at is not None:
            if not isinstance(observed_at, datetime):
                raise ValueError("skill opinion observed_at must be a datetime")
            if observed_at.tzinfo is not None and observed_at.utcoffset() is not None:
                observed_at = observed_at.astimezone(timezone.utc).replace(
                    tzinfo=None
                )
        return SkillOpinionInput(
            skill_id=skill_id,
            signal=signal,
            confidence=confidence,
            skill_version=skill_version,
            horizon=horizon,
            observed_at=observed_at,
        )

    @staticmethod
    def _optional_text(value: Any, *, maximum: int) -> Optional[str]:
        text = str(value or "").strip()
        if not text:
            return None
        if len(text) > maximum:
            raise ValueError(f"text exceeds {maximum} characters")
        return text

    @staticmethod
    def _positive_int(value: Any, field_name: str) -> int:
        return SkillOpinionSampleService._bounded_positive_int(
            value,
            field_name,
        )

    @staticmethod
    def _bounded_positive_int(
        value: Any,
        field_name: str,
        *,
        maximum: Optional[int] = None,
    ) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be a positive integer")
        if isinstance(value, int):
            number = value
        elif isinstance(value, str) and value.strip().isdigit():
            number = int(value)
        else:
            raise ValueError(f"{field_name} must be a positive integer")
        if number <= 0 or (maximum is not None and number > maximum):
            suffix = (
                f" no greater than {maximum}"
                if maximum is not None
                else ""
            )
            raise ValueError(
                f"{field_name} must be a positive integer{suffix}"
            )
        return number
