# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Repository for attributable skill-opinion forward outcomes."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, case, func, insert, or_, select, update

from src.repositories.skill_opinion_tables import (
    analysis_history_table,
    skill_opinion_outcome_table,
    skill_opinion_sample_table,
    stock_daily_table,
)
from src.schemas.skill_opinion_outcome import (
    AnalysisHistoryProjection,
    LocalDailyWindow,
    SkillOpinionOutcome,
    SkillOpinionOutcomeCandidate,
    SkillOpinionOutcomeEvaluation,
    SkillOpinionPerformanceBucket,
    SkillOpinionSample,
    StockDailyBar,
    TERMINAL_SKILL_OUTCOME_STATUSES,
)
from src.storage import DatabaseManager


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_SAMPLE_COLUMNS = tuple(
    column.label(f"sample_{column.name}")
    for column in skill_opinion_sample_table.c
)
_HISTORY_COLUMNS = (
    analysis_history_table.c.id.label("history_id"),
    analysis_history_table.c.code.label("history_code"),
    analysis_history_table.c.raw_result.label("history_raw_result"),
    analysis_history_table.c.context_snapshot.label("history_context_snapshot"),
    analysis_history_table.c.created_at.label("history_created_at"),
)
_OUTCOME_COLUMNS = tuple(
    column.label(f"outcome_{column.name}")
    for column in skill_opinion_outcome_table.c
)


class SkillOpinionOutcomeRepository:
    """Select bounded candidates and persist missing or retryable outcomes."""

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        *,
        clock: Callable[[], datetime] = _utc_naive_now,
    ) -> None:
        self.db = db_manager or DatabaseManager.get_instance()
        self._clock = clock

    def list_candidate_keys(
        self,
        *,
        horizons: Sequence[str],
        engine_version: str,
        limit: int,
        sample_id: Optional[int] = None,
        analysis_history_id: Optional[int] = None,
        skill_id: Optional[str] = None,
        stock_code: Optional[str] = None,
    ) -> List[SkillOpinionOutcomeCandidate]:
        """Return at most ``limit`` missing or pending outcome keys."""
        candidates: List[SkillOpinionOutcomeCandidate] = []
        with self.db.get_session() as session:
            for horizon in horizons:
                join_condition = and_(
                    skill_opinion_outcome_table.c.skill_opinion_sample_id
                    == skill_opinion_sample_table.c.id,
                    skill_opinion_outcome_table.c.horizon == horizon,
                    skill_opinion_outcome_table.c.engine_version
                    == engine_version,
                )
                conditions = [
                    or_(
                        skill_opinion_outcome_table.c.id.is_(None),
                        skill_opinion_outcome_table.c.eval_status == "pending",
                    )
                ]
                if sample_id is not None:
                    conditions.append(
                        skill_opinion_sample_table.c.id == sample_id
                    )
                if analysis_history_id is not None:
                    conditions.append(
                        skill_opinion_sample_table.c.analysis_history_id
                        == analysis_history_id
                    )
                if skill_id is not None:
                    conditions.append(
                        skill_opinion_sample_table.c.skill_id == skill_id
                    )
                if stock_code is not None:
                    conditions.append(
                        skill_opinion_sample_table.c.stock_code == stock_code
                    )

                rows = session.execute(
                    select(
                        *_SAMPLE_COLUMNS,
                        *_HISTORY_COLUMNS,
                        *_OUTCOME_COLUMNS,
                    )
                    .select_from(
                        skill_opinion_sample_table.join(
                            analysis_history_table,
                            analysis_history_table.c.id
                            == skill_opinion_sample_table.c.analysis_history_id,
                        ).outerjoin(
                            skill_opinion_outcome_table,
                            join_condition,
                        )
                    )
                    .where(and_(*conditions))
                    .order_by(
                        func.coalesce(
                            skill_opinion_outcome_table.c.updated_at,
                            skill_opinion_sample_table.c.created_at,
                        ),
                        skill_opinion_sample_table.c.id,
                    )
                    .limit(limit)
                ).all()
                candidates.extend(
                    self._candidate(row, horizon) for row in rows
                )

        horizon_rank = {
            horizon: index for index, horizon in enumerate(horizons)
        }
        candidates.sort(
            key=lambda item: (
                self._candidate_time(item),
                item.sample.id,
                horizon_rank[item.horizon],
                item.existing_outcome is not None,
            )
        )
        return candidates[:limit]

    def persist_outcome(
        self,
        *,
        sample_id: int,
        horizon: str,
        engine_version: str,
        evaluation: SkillOpinionOutcomeEvaluation,
    ) -> Tuple[Optional[int], str]:
        """Insert a missing key or update pending; never overwrite terminal rows."""

        def _write(session) -> Tuple[Optional[int], str]:
            sample_exists = session.execute(
                select(skill_opinion_sample_table.c.id)
                .where(skill_opinion_sample_table.c.id == sample_id)
                .limit(1)
            ).scalar_one_or_none()
            if sample_exists is None:
                return None, "missing_sample"

            existing_row = session.execute(
                select(skill_opinion_outcome_table)
                .where(
                    skill_opinion_outcome_table.c.skill_opinion_sample_id
                    == sample_id,
                    skill_opinion_outcome_table.c.horizon == horizon,
                    skill_opinion_outcome_table.c.engine_version
                    == engine_version,
                )
                .limit(1)
            ).one_or_none()
            existing = (
                self._outcome(existing_row)
                if existing_row is not None
                else None
            )
            if (
                existing is not None
                and existing.eval_status in TERMINAL_SKILL_OUTCOME_STATUSES
            ):
                return existing.id, "skipped"

            now = self._clock()
            mutable_fields: Dict[str, Any] = {
                **evaluation.to_fields(),
                "updated_at": now,
            }
            if existing is None:
                result = session.execute(
                    insert(skill_opinion_outcome_table).values(
                        skill_opinion_sample_id=sample_id,
                        horizon=horizon,
                        engine_version=engine_version,
                        created_at=now,
                        **mutable_fields,
                    )
                )
                inserted_id = result.inserted_primary_key[0]
                return int(inserted_id), "created"

            session.execute(
                update(skill_opinion_outcome_table)
                .where(skill_opinion_outcome_table.c.id == existing.id)
                .values(**mutable_fields)
            )
            return existing.id, "updated"

        return self.db._run_write_transaction(
            "persist skill opinion outcome",
            _write,
        )

    def get_outcome(
        self,
        *,
        sample_id: int,
        horizon: str,
        engine_version: str,
    ) -> Optional[SkillOpinionOutcome]:
        with self.db.get_session() as session:
            row = session.execute(
                select(skill_opinion_outcome_table)
                .where(
                    skill_opinion_outcome_table.c.skill_opinion_sample_id
                    == sample_id,
                    skill_opinion_outcome_table.c.horizon == horizon,
                    skill_opinion_outcome_table.c.engine_version
                    == engine_version,
                )
                .limit(1)
            ).one_or_none()
        return self._outcome(row) if row is not None else None

    def resolve_daily_window(
        self,
        *,
        code_candidates: Sequence[str],
        expected_start_date: date,
        eval_window_days: int,
    ) -> Optional[LocalDailyWindow]:
        """Resolve an exact-start window without combining stored code shapes."""
        normalized_codes = list(
            dict.fromkeys(
                str(code or "").strip()
                for code in code_candidates
                if str(code or "").strip()
            )
        )
        best: Optional[Tuple[Tuple[int, int, int], LocalDailyWindow]] = None
        with self.db.get_session() as session:
            for index, code in enumerate(normalized_codes):
                rows = session.execute(
                    select(
                        stock_daily_table.c.code,
                        stock_daily_table.c.date,
                        stock_daily_table.c.close,
                    )
                    .where(
                        stock_daily_table.c.code == code,
                        stock_daily_table.c.date >= expected_start_date,
                    )
                    .order_by(stock_daily_table.c.date)
                    .limit(eval_window_days + 1)
                ).all()
                if not rows or rows[0]._mapping["date"] != expected_start_date:
                    continue
                bars = [
                    StockDailyBar(
                        code=str(row._mapping["code"]),
                        date=row._mapping["date"],
                        close=row._mapping["close"],
                    )
                    for row in rows
                ]
                window = LocalDailyWindow(
                    start_bar=bars[0],
                    forward_bars=tuple(bars[1:]),
                )
                score = (
                    int(len(bars) >= eval_window_days + 1),
                    len(bars),
                    -index,
                )
                if best is None or score > best[0]:
                    best = score, window
        return best[1] if best is not None else None

    def list_performance_buckets(
        self,
        *,
        engine_version: str,
        skill_id: Optional[str] = None,
        skill_ids: Optional[Sequence[str]] = None,
        horizons: Optional[Sequence[str]] = None,
    ) -> List[SkillOpinionPerformanceBucket]:
        """Aggregate persisted outcome facts without applying sample policy."""
        status = skill_opinion_outcome_table.c.eval_status
        outcome = skill_opinion_outcome_table.c.outcome
        conditions = [
            skill_opinion_outcome_table.c.engine_version == engine_version
        ]
        if skill_id is not None:
            conditions.append(skill_opinion_sample_table.c.skill_id == skill_id)
        if skill_ids is not None:
            conditions.append(
                skill_opinion_sample_table.c.skill_id.in_(list(skill_ids))
            )
        if horizons is not None:
            conditions.append(
                skill_opinion_outcome_table.c.horizon.in_(list(horizons))
            )
        with self.db.get_session() as session:
            rows = session.execute(
                select(
                    skill_opinion_sample_table.c.skill_id,
                    skill_opinion_outcome_table.c.horizon,
                    skill_opinion_outcome_table.c.engine_version,
                    func.count(skill_opinion_outcome_table.c.id),
                    func.sum(case((status == "pending", 1), else_=0)),
                    func.sum(case((status == "evaluated", 1), else_=0)),
                    func.sum(
                        case((status == "observational", 1), else_=0)
                    ),
                    func.sum(case((status == "unable", 1), else_=0)),
                    func.sum(case((outcome == "hit", 1), else_=0)),
                    func.sum(case((outcome == "miss", 1), else_=0)),
                    func.avg(
                        case(
                            (
                                status == "evaluated",
                                skill_opinion_outcome_table.c.directional_return_pct,
                            ),
                            else_=None,
                        )
                    ),
                )
                .select_from(
                    skill_opinion_outcome_table.join(
                        skill_opinion_sample_table,
                        skill_opinion_sample_table.c.id
                        == skill_opinion_outcome_table.c.skill_opinion_sample_id,
                    )
                )
                .where(and_(*conditions))
                .group_by(
                    skill_opinion_sample_table.c.skill_id,
                    skill_opinion_outcome_table.c.horizon,
                    skill_opinion_outcome_table.c.engine_version,
                )
            ).all()
        return [
            SkillOpinionPerformanceBucket(
                skill_id=str(row[0]),
                horizon=str(row[1]),
                engine_version=str(row[2]),
                total=int(row[3] or 0),
                pending=int(row[4] or 0),
                evaluated=int(row[5] or 0),
                observational=int(row[6] or 0),
                unable=int(row[7] or 0),
                hit=int(row[8] or 0),
                miss=int(row[9] or 0),
                avg_directional_return_pct=(
                    float(row[10]) if row[10] is not None else None
                ),
            )
            for row in rows
        ]

    @classmethod
    def _candidate(
        cls,
        row: Any,
        horizon: str,
    ) -> SkillOpinionOutcomeCandidate:
        mapping = row._mapping
        sample = SkillOpinionSample(
            id=int(mapping["sample_id"]),
            analysis_history_id=int(mapping["sample_analysis_history_id"]),
            stock_code=str(mapping["sample_stock_code"]),
            skill_id=str(mapping["sample_skill_id"]),
            skill_version=mapping["sample_skill_version"],
            signal=str(mapping["sample_signal"]),
            confidence=float(mapping["sample_confidence"]),
            horizon=mapping["sample_horizon"],
            data_quality_level=mapping["sample_data_quality_level"],
            opinion_created_at=mapping["sample_opinion_created_at"],
            sample_schema_version=str(
                mapping["sample_sample_schema_version"]
            ),
            created_at=mapping["sample_created_at"],
        )
        history = AnalysisHistoryProjection(
            id=int(mapping["history_id"]),
            stock_code=str(mapping["history_code"]),
            raw_result=mapping["history_raw_result"],
            context_snapshot=mapping["history_context_snapshot"],
            created_at=mapping["history_created_at"],
        )
        existing = (
            cls._prefixed_outcome(mapping)
            if mapping["outcome_id"] is not None
            else None
        )
        return SkillOpinionOutcomeCandidate(
            sample=sample,
            history=history,
            horizon=horizon,
            existing_outcome=existing,
        )

    @staticmethod
    def _prefixed_outcome(mapping: Any) -> SkillOpinionOutcome:
        return SkillOpinionOutcome(
            id=int(mapping["outcome_id"]),
            skill_opinion_sample_id=int(
                mapping["outcome_skill_opinion_sample_id"]
            ),
            horizon=str(mapping["outcome_horizon"]),
            engine_version=str(mapping["outcome_engine_version"]),
            eval_status=str(mapping["outcome_eval_status"]),
            outcome=mapping["outcome_outcome"],
            direction_correct=mapping["outcome_direction_correct"],
            unable_reason=mapping["outcome_unable_reason"],
            analysis_date=mapping["outcome_analysis_date"],
            start_trade_date=mapping["outcome_start_trade_date"],
            end_trade_date=mapping["outcome_end_trade_date"],
            start_price=mapping["outcome_start_price"],
            end_close=mapping["outcome_end_close"],
            stock_return_pct=mapping["outcome_stock_return_pct"],
            directional_return_pct=mapping[
                "outcome_directional_return_pct"
            ],
            created_at=mapping["outcome_created_at"],
            updated_at=mapping["outcome_updated_at"],
        )

    @staticmethod
    def _outcome(row: Any) -> SkillOpinionOutcome:
        mapping = row._mapping
        return SkillOpinionOutcome(
            id=int(mapping["id"]),
            skill_opinion_sample_id=int(
                mapping["skill_opinion_sample_id"]
            ),
            horizon=str(mapping["horizon"]),
            engine_version=str(mapping["engine_version"]),
            eval_status=str(mapping["eval_status"]),
            outcome=mapping["outcome"],
            direction_correct=mapping["direction_correct"],
            unable_reason=mapping["unable_reason"],
            analysis_date=mapping["analysis_date"],
            start_trade_date=mapping["start_trade_date"],
            end_trade_date=mapping["end_trade_date"],
            start_price=mapping["start_price"],
            end_close=mapping["end_close"],
            stock_return_pct=mapping["stock_return_pct"],
            directional_return_pct=mapping["directional_return_pct"],
            created_at=mapping["created_at"],
            updated_at=mapping["updated_at"],
        )

    @staticmethod
    def _candidate_time(candidate: SkillOpinionOutcomeCandidate) -> datetime:
        existing_time = (
            candidate.existing_outcome.updated_at
            if candidate.existing_outcome is not None
            else None
        )
        return existing_time or candidate.sample.created_at or datetime.min
