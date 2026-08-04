# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Pure domain records for attributable strategy-skill outcomes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import math
from typing import Any, Dict, Optional, Sequence


SUPPORTED_SKILL_OUTCOME_HORIZONS: Dict[str, int] = {
    "1d": 1,
    "3d": 3,
    "5d": 5,
    "10d": 10,
}
CANONICAL_SKILL_SIGNALS = frozenset(
    {"strong_buy", "buy", "hold", "sell", "strong_sell"}
)
BULLISH_SKILL_SIGNALS = frozenset({"strong_buy", "buy"})
TERMINAL_SKILL_OUTCOME_STATUSES = frozenset(
    {"evaluated", "observational", "unable"}
)


@dataclass(frozen=True)
class SkillOpinionInput:
    """Low-sensitivity input for one immutable individual skill sample."""

    skill_id: str
    signal: str
    confidence: float
    skill_version: Optional[str] = None
    horizon: Optional[str] = None
    observed_at: Optional[datetime] = None


@dataclass(frozen=True)
class AnalysisHistoryProjection:
    """Persisted history fields required to materialize and evaluate samples."""

    id: int
    stock_code: str
    raw_result: Optional[str]
    context_snapshot: Optional[str]
    created_at: Optional[datetime]


@dataclass(frozen=True)
class SkillOpinionSample:
    """Detached persisted sample record."""

    id: int
    analysis_history_id: int
    stock_code: str
    skill_id: str
    skill_version: Optional[str]
    signal: str
    confidence: float
    horizon: Optional[str]
    data_quality_level: Optional[str]
    opinion_created_at: Optional[datetime]
    sample_schema_version: str
    created_at: Optional[datetime]


@dataclass(frozen=True)
class StockDailyBar:
    """Detached local daily bar used by the pure evaluator."""

    code: str
    date: date
    close: Optional[float]


@dataclass(frozen=True)
class LocalDailyWindow:
    """One exact-start window from a single persisted stock-code shape."""

    start_bar: StockDailyBar
    forward_bars: Sequence[StockDailyBar]


@dataclass(frozen=True)
class SkillOpinionOutcomeEvaluation:
    """One deterministic sample-by-horizon evaluation result."""

    eval_status: str
    outcome: Optional[str] = None
    direction_correct: Optional[bool] = None
    unable_reason: Optional[str] = None
    analysis_date: Optional[date] = None
    start_trade_date: Optional[date] = None
    end_trade_date: Optional[date] = None
    start_price: Optional[float] = None
    end_close: Optional[float] = None
    stock_return_pct: Optional[float] = None
    directional_return_pct: Optional[float] = None

    def to_fields(self) -> Dict[str, Any]:
        """Return persistence fields without coupling the schema to SQLAlchemy."""
        return asdict(self)


@dataclass(frozen=True)
class SkillOpinionOutcome:
    """Detached persisted outcome record."""

    id: int
    skill_opinion_sample_id: int
    horizon: str
    engine_version: str
    eval_status: str
    outcome: Optional[str]
    direction_correct: Optional[bool]
    unable_reason: Optional[str]
    analysis_date: Optional[date]
    start_trade_date: Optional[date]
    end_trade_date: Optional[date]
    start_price: Optional[float]
    end_close: Optional[float]
    stock_return_pct: Optional[float]
    directional_return_pct: Optional[float]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


@dataclass(frozen=True)
class SkillOpinionOutcomeCandidate:
    """One missing or pending sample-by-horizon key."""

    sample: SkillOpinionSample
    history: AnalysisHistoryProjection
    horizon: str
    existing_outcome: Optional[SkillOpinionOutcome]


@dataclass(frozen=True)
class SkillOpinionPerformanceBucket:
    """Raw persisted counts for one skill, horizon, and engine version."""

    skill_id: str
    horizon: str
    engine_version: str
    total: int
    pending: int
    evaluated: int
    observational: int
    unable: int
    hit: int
    miss: int
    avg_directional_return_pct: Optional[float]


class SkillOpinionOutcomeEvaluator:
    """Evaluate one immutable canonical skill signal against local daily bars."""

    @classmethod
    def evaluate(
        cls,
        *,
        signal: Any,
        horizon: str,
        analysis_date: Optional[date],
        start_bar: Optional[StockDailyBar] = None,
        forward_bars: Sequence[StockDailyBar] = (),
    ) -> SkillOpinionOutcomeEvaluation:
        canonical_signal = str(signal or "").strip().lower()
        if canonical_signal not in CANONICAL_SKILL_SIGNALS:
            return cls._unable("invalid_signal", analysis_date=analysis_date)

        eval_days = SUPPORTED_SKILL_OUTCOME_HORIZONS.get(
            str(horizon or "").strip()
        )
        if eval_days is None:
            return cls._unable("unsupported_horizon", analysis_date=analysis_date)
        if analysis_date is None:
            return cls._unable("missing_analysis_date")
        if start_bar is None:
            return cls._pending("missing_start_bar", analysis_date=analysis_date)

        raw_start_price = start_bar.close
        start_price = cls._positive_finite_float(raw_start_price)
        if start_price is None:
            reason = (
                "missing_start_close"
                if raw_start_price is None
                else "invalid_start_price"
            )
            return cls._pending(
                reason,
                analysis_date=analysis_date,
                start_trade_date=start_bar.date,
            )

        bars = list(forward_bars)
        if len(bars) < eval_days:
            return cls._pending(
                "insufficient_future_data",
                analysis_date=analysis_date,
                start_trade_date=start_bar.date,
                start_price=start_price,
            )

        end_bar = bars[eval_days - 1]
        raw_end_close = end_bar.close
        end_close = cls._positive_finite_float(raw_end_close)
        if end_close is None:
            reason = (
                "missing_end_close"
                if raw_end_close is None
                else "invalid_end_close"
            )
            return cls._pending(
                reason,
                analysis_date=analysis_date,
                start_trade_date=start_bar.date,
                end_trade_date=end_bar.date,
                start_price=start_price,
            )

        stock_return_pct = (end_close - start_price) / start_price * 100.0
        if not math.isfinite(stock_return_pct):
            return cls._pending(
                "invalid_return",
                analysis_date=analysis_date,
                start_trade_date=start_bar.date,
                end_trade_date=end_bar.date,
                start_price=start_price,
                end_close=end_close,
            )
        if canonical_signal == "hold":
            return SkillOpinionOutcomeEvaluation(
                eval_status="observational",
                outcome="observational",
                analysis_date=analysis_date,
                start_trade_date=start_bar.date,
                end_trade_date=end_bar.date,
                start_price=start_price,
                end_close=end_close,
                stock_return_pct=stock_return_pct,
            )

        multiplier = 1.0 if canonical_signal in BULLISH_SKILL_SIGNALS else -1.0
        directional_return_pct = stock_return_pct * multiplier
        direction_correct = directional_return_pct > 0.0
        return SkillOpinionOutcomeEvaluation(
            eval_status="evaluated",
            outcome="hit" if direction_correct else "miss",
            direction_correct=direction_correct,
            directional_return_pct=directional_return_pct,
            analysis_date=analysis_date,
            start_trade_date=start_bar.date,
            end_trade_date=end_bar.date,
            start_price=start_price,
            end_close=end_close,
            stock_return_pct=stock_return_pct,
        )

    @staticmethod
    def _pending(
        reason: str,
        **fields: Any,
    ) -> SkillOpinionOutcomeEvaluation:
        return SkillOpinionOutcomeEvaluation(
            eval_status="pending",
            unable_reason=reason,
            **fields,
        )

    @staticmethod
    def _unable(
        reason: str,
        **fields: Any,
    ) -> SkillOpinionOutcomeEvaluation:
        return SkillOpinionOutcomeEvaluation(
            eval_status="unable",
            unable_reason=reason,
            **fields,
        )

    @staticmethod
    def _positive_finite_float(value: Any) -> Optional[float]:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (OverflowError, TypeError, ValueError):
            return None
        return number if math.isfinite(number) and number > 0 else None
