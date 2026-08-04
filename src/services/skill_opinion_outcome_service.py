# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Evaluate persisted skill opinions against locally stored daily bars."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.market.context import detect_market
from src.repositories.skill_opinion_outcome_repo import (
    SkillOpinionOutcomeRepository,
)
from src.schemas.skill_opinion_outcome import (
    SUPPORTED_SKILL_OUTCOME_HORIZONS,
    AnalysisHistoryProjection,
    SkillOpinionOutcome,
    SkillOpinionOutcomeCandidate,
    SkillOpinionOutcomeEvaluation,
    SkillOpinionOutcomeEvaluator,
)
from src.services.skill_opinion_sample_service import (
    SkillOpinionSampleService,
)
from src.services.stock_code_utils import normalize_code
from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

SKILL_OPINION_OUTCOME_ENGINE_VERSION = "skill-opinion-outcome-v1"


class SkillOpinionOutcomeService:
    """Materialize samples and evaluate bounded missing or pending keys."""

    def __init__(
        self,
        *,
        repo: Optional[SkillOpinionOutcomeRepository] = None,
        sample_service: Optional[SkillOpinionSampleService] = None,
        db_manager: Optional[DatabaseManager] = None,
    ) -> None:
        self.repo = repo or SkillOpinionOutcomeRepository(db_manager)
        self.sample_service = sample_service or SkillOpinionSampleService(
            db_manager
        )

    def run_outcomes(
        self,
        *,
        sample_id: Optional[int] = None,
        analysis_history_id: Optional[int] = None,
        skill_id: Optional[str] = None,
        stock_code: Optional[str] = None,
        horizons: Optional[Sequence[str]] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Process at most ``limit`` sample-by-horizon outcome keys."""
        sample_id_norm = self._optional_positive_int(sample_id, "sample_id")
        history_id_norm = self._optional_positive_int(
            analysis_history_id,
            "analysis_history_id",
        )
        skill_id_norm = self._optional_text(skill_id, "skill_id")
        stock_code_norm = self._optional_text(stock_code, "stock_code")
        horizons_norm = self._normalize_horizons(horizons)
        limit_norm = self._bounded_positive_int(
            limit,
            "limit",
            maximum=500,
        )

        materialized = {
            "histories_scanned": 0,
            "samples_created": 0,
        }
        if history_id_norm is not None:
            created = self.sample_service.materialize_history(history_id_norm)
            materialized = {
                "histories_scanned": 1,
                "samples_created": created,
            }
        elif sample_id_norm is None:
            materialized = self.sample_service.materialize_pending(
                limit=limit_norm,
                stock_code=stock_code_norm,
            )

        candidates = self.repo.list_candidate_keys(
            horizons=horizons_norm,
            engine_version=SKILL_OPINION_OUTCOME_ENGINE_VERSION,
            limit=limit_norm,
            sample_id=sample_id_norm,
            analysis_history_id=history_id_norm,
            skill_id=skill_id_norm,
            stock_code=stock_code_norm,
        )

        items: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        counts = {"created": 0, "updated": 0, "skipped": 0}
        for candidate in candidates:
            try:
                evaluation = self._evaluate_candidate(candidate)
                _, persist_status = self.repo.persist_outcome(
                    sample_id=candidate.sample.id,
                    horizon=candidate.horizon,
                    engine_version=SKILL_OPINION_OUTCOME_ENGINE_VERSION,
                    evaluation=evaluation,
                )
                if persist_status == "missing_sample":
                    counts["skipped"] += 1
                    continue
                counts[persist_status] += 1
                row = self.repo.get_outcome(
                    sample_id=candidate.sample.id,
                    horizon=candidate.horizon,
                    engine_version=SKILL_OPINION_OUTCOME_ENGINE_VERSION,
                )
                if row is not None:
                    items.append(self._serialize_outcome(row, candidate))
            except Exception as exc:  # broad-exception: fallback_recorded - A single corrupt candidate is isolated and rotated for a later retry.
                error = {
                    "sample_id": candidate.sample.id,
                    "horizon": candidate.horizon,
                    "error_type": type(exc).__name__,
                }
                errors.append(error)
                try:
                    self._record_retry_attempt(candidate)
                except Exception as retry_exc:  # broad-exception: fallback_recorded - A retry-marker failure is logged without masking the original candidate failure.
                    log_safe_exception(
                        logger,
                        "Skill opinion outcome retry marker failed",
                        retry_exc,
                        error_code="skill_opinion_outcome_retry_marker_failed",
                        level=logging.WARNING,
                        context=error,
                    )
                log_safe_exception(
                    logger,
                    "Skill opinion outcome evaluation deferred",
                    exc,
                    error_code="skill_opinion_outcome_evaluation_deferred",
                    level=logging.WARNING,
                    context=error,
                )

        return {
            "items": items,
            "processed_keys": len(candidates),
            "created": counts["created"],
            "updated": counts["updated"],
            "skipped": counts["skipped"],
            "failed": len(errors),
            "errors": errors,
            "histories_scanned": materialized["histories_scanned"],
            "samples_created": materialized["samples_created"],
            "limit_unit": "outcome_key",
            "engine_version": SKILL_OPINION_OUTCOME_ENGINE_VERSION,
        }

    def _record_retry_attempt(
        self,
        candidate: SkillOpinionOutcomeCandidate,
    ) -> None:
        self.repo.persist_outcome(
            sample_id=candidate.sample.id,
            horizon=candidate.horizon,
            engine_version=SKILL_OPINION_OUTCOME_ENGINE_VERSION,
            evaluation=SkillOpinionOutcomeEvaluation(
                eval_status="pending",
                unable_reason="evaluation_error",
            ),
        )

    def _evaluate_candidate(
        self,
        candidate: SkillOpinionOutcomeCandidate,
    ) -> SkillOpinionOutcomeEvaluation:
        analysis_date, analysis_date_failure = self._resolve_analysis_date(
            candidate.history
        )
        if not self._codes_equivalent(
            candidate.sample.stock_code,
            candidate.history.stock_code,
        ):
            return SkillOpinionOutcomeEvaluation(
                eval_status="unable",
                unable_reason="stock_code_mismatch",
                analysis_date=analysis_date,
            )
        if analysis_date_failure is not None:
            return SkillOpinionOutcomeEvaluation(
                eval_status="unable",
                unable_reason=analysis_date_failure,
                analysis_date=analysis_date,
            )
        expected_start_date, failure_reason = self._resolve_expected_start_date(
            stock_code=candidate.sample.stock_code,
            context_snapshot=candidate.history.context_snapshot,
            analysis_date=analysis_date,
        )
        if failure_reason is not None:
            return SkillOpinionOutcomeEvaluation(
                eval_status="unable",
                unable_reason=failure_reason,
                analysis_date=analysis_date,
            )
        if expected_start_date is None:
            return SkillOpinionOutcomeEvaluation(
                eval_status="unable",
                unable_reason="unresolvable_expected_start_date",
                analysis_date=analysis_date,
            )

        code_candidates = self._code_candidates(candidate.sample.stock_code)
        if not code_candidates:
            return SkillOpinionOutcomeEvaluation(
                eval_status="unable",
                unable_reason="invalid_stock_code",
                analysis_date=analysis_date,
            )
        window = self.repo.resolve_daily_window(
            code_candidates=code_candidates,
            expected_start_date=expected_start_date,
            eval_window_days=SUPPORTED_SKILL_OUTCOME_HORIZONS[
                candidate.horizon
            ],
        )
        return SkillOpinionOutcomeEvaluator.evaluate(
            signal=candidate.sample.signal,
            horizon=candidate.horizon,
            analysis_date=analysis_date,
            start_bar=window.start_bar if window is not None else None,
            forward_bars=(
                window.forward_bars if window is not None else ()
            ),
        )

    @classmethod
    def _resolve_expected_start_date(
        cls,
        *,
        stock_code: str,
        context_snapshot: Any,
        analysis_date: Optional[date],
    ) -> Tuple[Optional[date], Optional[str]]:
        if analysis_date is None:
            return None, "missing_analysis_date"
        snapshot = cls._mapping(context_snapshot)
        summary = (
            snapshot.get("market_phase_summary")
            if snapshot is not None
            else None
        )
        if not isinstance(summary, Mapping):
            return None, "missing_market_phase_context"

        normalized_code = normalize_code(str(stock_code or ""))
        if normalized_code is None:
            return None, "invalid_stock_code"
        persisted_market = str(summary.get("market") or "").strip().lower()
        detected_market = detect_market(normalized_code)
        if not persisted_market or persisted_market != detected_market:
            return None, "invalid_market_phase_context"

        effective_value = summary.get("effective_daily_bar_date")
        if effective_value in (None, ""):
            return None, "missing_effective_daily_bar_date"
        effective_date = cls._parse_date(effective_value)
        if effective_date is None:
            return None, "invalid_effective_daily_bar_date"
        if effective_date > analysis_date:
            return None, "future_effective_daily_bar_date"
        return effective_date, None

    @classmethod
    def _resolve_analysis_date(
        cls,
        history: AnalysisHistoryProjection,
    ) -> Tuple[Optional[date], Optional[str]]:
        snapshot = cls._mapping(history.context_snapshot)
        enhanced = (
            snapshot.get("enhanced_context")
            if snapshot is not None
            else None
        )
        if isinstance(enhanced, Mapping):
            raw_date = enhanced.get("date")
            if raw_date not in (None, ""):
                parsed = cls._parse_date(raw_date)
                if parsed is None:
                    return None, "invalid_analysis_date"
                return parsed, None
        if isinstance(history.created_at, datetime):
            return history.created_at.date(), None
        return None, "missing_analysis_date"

    @staticmethod
    def _code_candidates(stock_code: Any) -> List[str]:
        raw = str(stock_code or "").strip()
        if not raw:
            return []
        normalized = normalize_code(raw)
        if normalized is None:
            return []
        if normalized.endswith(".US"):
            normalized = normalized[:-3]
        return list(dict.fromkeys((raw, raw.upper(), normalized)))

    @classmethod
    def _codes_equivalent(cls, left: Any, right: Any) -> bool:
        left_candidates = set(cls._code_candidates(left))
        right_candidates = set(cls._code_candidates(right))
        return bool(left_candidates and left_candidates & right_candidates)

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
    def _parse_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None

    @staticmethod
    def _normalize_horizons(
        values: Optional[Sequence[str]],
    ) -> List[str]:
        if values is None:
            return list(SUPPORTED_SKILL_OUTCOME_HORIZONS)
        if isinstance(values, (str, bytes)) or not values:
            raise ValueError("horizons must not be empty")
        normalized: List[str] = []
        for value in values:
            horizon = str(value or "").strip()
            if horizon not in SUPPORTED_SKILL_OUTCOME_HORIZONS:
                raise ValueError(
                    "horizon must be one of "
                    + ", ".join(SUPPORTED_SKILL_OUTCOME_HORIZONS)
                )
            if horizon not in normalized:
                normalized.append(horizon)
        return normalized

    @staticmethod
    def _optional_positive_int(
        value: Any,
        field_name: str,
    ) -> Optional[int]:
        if value is None:
            return None
        return SkillOpinionOutcomeService._bounded_positive_int(
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

    @staticmethod
    def _optional_text(value: Any, field_name: str) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            raise ValueError(f"{field_name} must not be blank")
        return text

    @staticmethod
    def _serialize_outcome(
        row: SkillOpinionOutcome,
        candidate: SkillOpinionOutcomeCandidate,
    ) -> Dict[str, Any]:
        return {
            "id": row.id,
            "skill_opinion_sample_id": row.skill_opinion_sample_id,
            "analysis_history_id": candidate.sample.analysis_history_id,
            "stock_code": candidate.sample.stock_code,
            "skill_id": candidate.sample.skill_id,
            "signal": candidate.sample.signal,
            "horizon": row.horizon,
            "engine_version": row.engine_version,
            "eval_status": row.eval_status,
            "outcome": row.outcome,
            "direction_correct": row.direction_correct,
            "unable_reason": row.unable_reason,
            "analysis_date": (
                row.analysis_date.isoformat() if row.analysis_date else None
            ),
            "start_trade_date": (
                row.start_trade_date.isoformat()
                if row.start_trade_date
                else None
            ),
            "end_trade_date": (
                row.end_trade_date.isoformat()
                if row.end_trade_date
                else None
            ),
            "start_price": row.start_price,
            "end_close": row.end_close,
            "stock_return_pct": row.stock_return_pct,
            "directional_return_pct": row.directional_return_pct,
            "created_at": (
                row.created_at.isoformat() if row.created_at else None
            ),
            "updated_at": (
                row.updated_at.isoformat() if row.updated_at else None
            ),
        }
