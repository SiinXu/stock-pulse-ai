# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Materialize immutable skill-opinion samples from persisted reports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
import json
import math
from typing import Any, Dict, List, Optional

from src.repositories.skill_opinion_sample_repo import (
    SkillOpinionSampleRepository,
)
from src.schemas.skill_opinion_outcome import (
    AnalysisHistoryProjection,
    CANONICAL_SKILL_SIGNALS,
    SkillOpinionInput,
)
from src.storage import DatabaseManager


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
