"""Backtest summary projection and skill-metric helpers."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

from src.core.backtest_methodology import (
    CostModelConfig,
    SampleSplitConfig,
    build_methodology_statement,
)
from src.schemas.skill_opinion_outcome import SUPPORTED_SKILL_OUTCOME_HORIZONS
from src.services.skill_opinion_outcome_service import (
    SKILL_OPINION_OUTCOME_ENGINE_VERSION,
)
from src.services.skill_opinion_performance_service import (
    SkillOpinionPerformanceService,
)


class _BacktestSummaryMethods:
    """Summary normalization and attributable skill/strategy projections."""

    def get_global_summary(
        self,
        *,
        eval_window_days: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return overall backtest metrics normalized for Agent memory consumers."""
        return self._normalize_learning_summary(
            self.get_summary(
                scope="overall",
                code=None,
                eval_window_days=eval_window_days,
            )
        )

    def get_stock_summary(
        self,
        code: str,
        *,
        eval_window_days: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return per-stock backtest metrics normalized for Agent memory consumers."""
        return self._normalize_learning_summary(
            self.get_summary(
                scope="stock",
                code=code,
                eval_window_days=eval_window_days,
            )
        )

    def get_skill_summary(
        self,
        skill_id: str,
        *,
        eval_window_days: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return skill metrics isomorphic to analysis-advice summaries."""
        skill_key = str(skill_id or "").strip()
        if not skill_key:
            return None

        # Skill-opinion outcomes are scored offline without backtest costs.
        cost_model = CostModelConfig()
        horizon, window_days = self._resolve_skill_horizon(eval_window_days)
        try:
            stats = SkillOpinionPerformanceService(db_manager=self.db).get_stats(
                skill_id=skill_key,
                horizons=[horizon],
                engine_version=SKILL_OPINION_OUTCOME_ENGINE_VERSION,
            )
        except ValueError:
            return None

        buckets = stats.get("buckets") if isinstance(stats, dict) else None
        if not isinstance(buckets, list) or not buckets:
            return None

        bucket = next(
            (
                item
                for item in buckets
                if isinstance(item, dict)
                and str(item.get("skill_id") or "") == skill_key
            ),
            buckets[0] if isinstance(buckets[0], dict) else None,
        )
        if not isinstance(bucket, dict):
            return None

        evaluated = int(bucket.get("evaluated") or 0)
        observational = int(bucket.get("observational") or 0)
        unable = int(bucket.get("unable") or 0)
        pending = int(bucket.get("pending") or 0)
        hit = int(bucket.get("hit") or 0)
        miss = int(bucket.get("miss") or 0)
        hit_rate = bucket.get("hit_rate_pct")
        avg_dir = bucket.get("avg_directional_return_pct")
        sample_sufficient = bucket.get("sample_sufficient") is True

        summary: Dict[str, Any] = {
            "scope": "skill",
            "skill_id": skill_key,
            "code": None,
            "eval_window_days": window_days,
            "engine_version": str(
                bucket.get("engine_version")
                or SKILL_OPINION_OUTCOME_ENGINE_VERSION
            ),
            "computed_at": None,
            "total_evaluations": evaluated,
            "completed_count": evaluated,
            "insufficient_count": pending + unable,
            "long_count": 0,
            "cash_count": 0,
            "win_count": hit,
            "loss_count": miss,
            "neutral_count": observational,
            "direction_accuracy_pct": hit_rate,
            "win_rate_pct": hit_rate,
            "neutral_rate_pct": (
                round(observational / evaluated * 100, 2)
                if evaluated > 0 and sample_sufficient
                else None
            ),
            "avg_stock_return_pct": avg_dir,
            "avg_simulated_return_pct": avg_dir,
            "stop_loss_trigger_rate": None,
            "take_profit_trigger_rate": None,
            "ambiguous_rate": None,
            "avg_days_to_first_hit": None,
            "advice_breakdown": {},
            "diagnostics": {
                "metric_source": "skill_opinion_outcomes",
                "horizon": horizon,
                "sample_status": bucket.get("sample_status"),
                "sample_sufficient": sample_sufficient,
                "pending_count": pending,
                "unable_count": unable,
                "observational_count": observational,
            },
        }
        with_methodology = self._attach_methodology(
            summary,
            cost_model=cost_model,
            sample_split=SampleSplitConfig(),
            engine_version=str(summary["engine_version"]),
            eval_window_days=window_days,
            metric_source="skill_opinion_outcomes",
            extra_limitations=(
                "Skill-opinion outcome returns are gross directional percentages "
                "from the offline skill evaluator; backtest commission/slippage "
                "bps are not re-applied on this skill rollup path.",
            ),
        )
        if not sample_sufficient:
            return with_methodology
        return self._normalize_learning_summary(with_methodology)

    def get_strategy_summary(
        self,
        strategy_id: str,
        *,
        eval_window_days: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Compatibility wrapper for legacy strategy-based callers."""
        summary = self.get_skill_summary(
            strategy_id,
            eval_window_days=eval_window_days,
        )
        if summary is None:
            return None
        normalized = dict(summary)
        normalized["strategy_id"] = strategy_id
        return normalized

    @classmethod
    def _normalize_learning_summary(
        cls,
        summary: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Normalize percentage metrics for Agent memory consumers."""
        if summary is None:
            return None

        normalized = dict(summary)
        normalized["win_rate"] = cls._pct_to_ratio(
            summary.get("win_rate_pct"),
            default=0.5,
        )
        normalized["direction_accuracy"] = cls._pct_to_ratio(
            summary.get("direction_accuracy_pct"),
            default=0.5,
        )

        avg_return_pct = summary.get("avg_simulated_return_pct")
        if avg_return_pct is None:
            avg_return_pct = summary.get("avg_stock_return_pct")
        normalized["avg_return"] = cls._pct_to_ratio(
            avg_return_pct,
            default=0.0,
        )
        return normalized

    @staticmethod
    def _pct_to_ratio(value: Optional[float], default: float = 0.0) -> float:
        try:
            number = float(value) / 100.0
        except (TypeError, ValueError):
            return default
        if number != number or number in (float("inf"), float("-inf")):
            return default
        return number

    @staticmethod
    def _resolve_skill_horizon(
        eval_window_days: Optional[int],
    ) -> Tuple[str, int]:
        """Map a requested window onto skill-opinion horizon labels."""
        if eval_window_days is None:
            return "10d", 10
        try:
            days = int(eval_window_days)
        except (TypeError, ValueError):
            return "10d", 10
        supported = {
            int(label[:-1]): label
            for label in SUPPORTED_SKILL_OUTCOME_HORIZONS
        }
        if days in supported:
            return supported[days], days
        nearest = min(
            supported,
            key=lambda candidate: (abs(candidate - days), candidate),
        )
        return supported[nearest], nearest

    @staticmethod
    def _attach_methodology(
        summary: Optional[Dict[str, Any]],
        *,
        cost_model: CostModelConfig,
        sample_split: SampleSplitConfig,
        engine_version: str,
        eval_window_days: Optional[int],
        metric_source: str = "analysis_advice",
        extra_limitations: Optional[Sequence[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if summary is None:
            return None
        payload = dict(summary)
        methodology = build_methodology_statement(
            cost_model=cost_model,
            sample_split=sample_split,
            engine_version=engine_version,
            eval_window_days=(
                int(eval_window_days)
                if eval_window_days is not None
                else payload.get("eval_window_days")
            ),
            metric_source=metric_source,
            extra_limitations=extra_limitations,
        )
        payload["methodology"] = methodology
        diagnostics = payload.get("diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = {}
        else:
            diagnostics = dict(diagnostics)
        diagnostics["methodology"] = methodology
        diagnostics["cost_model"] = cost_model.to_dict()
        diagnostics["sample_split"] = sample_split.to_dict()
        payload["diagnostics"] = diagnostics
        return payload

    @staticmethod
    def _actual_movement_from_return(value: Optional[float]) -> Optional[str]:
        if value is None:
            return None
        try:
            actual_return = float(value)
        except (TypeError, ValueError):
            return None
        if actual_return > 0:
            return "up"
        if actual_return < 0:
            return "down"
        return "flat"
