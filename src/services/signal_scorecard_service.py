# -*- coding: utf-8 -*-
"""Public signal scorecard aggregation (Issue #379).

Turns the existing decision-signal outcomes into a transparency surface: hit rate
by signal type and horizon, return distribution, and recent notable misses. Hit
and outcome semantics are the authoritative values already computed by
``DecisionSignalOutcomeService`` — this service only aggregates and never
redefines what counts as a hit.

The payload is intentionally aggregate and non-sensitive (no per-stock identity)
so it is safe to expose on an opt-in public route.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Return-distribution buckets in percent (lower-inclusive, upper-exclusive), with
# open ends. Chosen as coarse, interpretable bands rather than raw values.
_RETURN_BANDS: Tuple[Tuple[Optional[float], Optional[float], str], ...] = (
    (None, -10.0, "<= -10%"),
    (-10.0, -5.0, "-10% ~ -5%"),
    (-5.0, -2.0, "-5% ~ -2%"),
    (-2.0, 2.0, "-2% ~ +2%"),
    (2.0, 5.0, "+2% ~ +5%"),
    (5.0, 10.0, "+5% ~ +10%"),
    (10.0, None, ">= +10%"),
)


class SignalScorecardService:
    """Aggregate signal outcomes into a public, non-sensitive scorecard."""

    def __init__(self, *, outcome_service: Any = None, outcome_repo: Any = None):
        self._outcome_service = outcome_service
        self._outcome_repo = outcome_repo

    @property
    def outcome_service(self) -> Any:
        if self._outcome_service is None:
            from src.services.decision_signal_outcome_service import (
                DecisionSignalOutcomeService,
            )

            self._outcome_service = DecisionSignalOutcomeService()
        return self._outcome_service

    @property
    def outcome_repo(self) -> Any:
        if self._outcome_repo is None:
            self._outcome_repo = self.outcome_service.repo
        return self._outcome_repo

    def build_scorecard(
        self,
        *,
        min_samples: int,
        recent_miss_limit: int = 10,
    ) -> Dict[str, Any]:
        """Return the aggregated scorecard payload.

        Buckets whose decided (hit+miss) sample is below ``min_samples`` render as
        ``insufficient_data`` instead of a percentage, to avoid misleading
        small-sample statistics.
        """

        from src.services.decision_signal_outcome_service import (
            DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
        )

        threshold = max(1, int(min_samples))
        rows = self.outcome_repo.list_stats_rows(
            engine_version=DECISION_SIGNAL_OUTCOME_ENGINE_VERSION,
            horizons=None,
            statuses=None,
        )
        completed = [
            row
            for row in rows
            if getattr(row, "eval_status", None) == "completed"
            and getattr(row, "outcome", None) in {"hit", "miss", "neutral"}
        ]

        overall = self._bucket_stats(completed, threshold)
        overall.pop("action", None)
        overall.pop("horizon", None)

        by_type_horizon = self._breakdown_by_action_horizon(completed, threshold)
        return_distribution = self._return_distribution(completed)
        recent_misses = self._recent_misses(completed, limit=recent_miss_limit)

        return {
            "min_samples": threshold,
            "overall": overall,
            "by_signal_type_horizon": by_type_horizon,
            "return_distribution": return_distribution,
            "recent_misses": recent_misses,
        }

    # ---- helpers ----

    def _bucket_stats(self, rows: Sequence[Any], threshold: int) -> Dict[str, Any]:
        agg = self.outcome_service.aggregate_outcome_rows(list(rows))
        decided = int(agg.get("hit", 0)) + int(agg.get("miss", 0))
        stat: Dict[str, Any] = {
            "sample_size": decided,
            "completed": int(agg.get("completed", 0)),
        }
        if decided < threshold:
            stat.update(
                {
                    "status": "insufficient_data",
                    "hit_rate_pct": None,
                    "avg_return_pct": None,
                }
            )
        else:
            stat.update(
                {
                    "status": "ok",
                    "hit_rate_pct": agg.get("hit_rate_pct"),
                    "avg_return_pct": agg.get("avg_stock_return_pct"),
                }
            )
        return stat

    def _breakdown_by_action_horizon(
        self,
        rows: Sequence[Any],
        threshold: int,
    ) -> List[Dict[str, Any]]:
        grouped: Dict[Tuple[str, str], List[Any]] = defaultdict(list)
        for row in rows:
            action = str(getattr(row, "action", None) or "unknown")
            horizon = str(getattr(row, "horizon", None) or "unknown")
            grouped[(action, horizon)].append(row)

        buckets: List[Dict[str, Any]] = []
        for (action, horizon), group in grouped.items():
            stat = self._bucket_stats(group, threshold)
            stat["signal_type"] = action
            stat["horizon"] = horizon
            buckets.append(stat)
        buckets.sort(
            key=lambda item: (-int(item["sample_size"]), str(item["signal_type"]), str(item["horizon"]))
        )
        return buckets

    @staticmethod
    def _return_distribution(rows: Sequence[Any]) -> List[Dict[str, Any]]:
        counts = {band[2]: 0 for band in _RETURN_BANDS}
        total = 0
        for row in rows:
            value = getattr(row, "stock_return_pct", None)
            if value is None:
                continue
            value = float(value)
            total += 1
            for lower, upper, label in _RETURN_BANDS:
                if (lower is None or value >= lower) and (upper is None or value < upper):
                    counts[label] += 1
                    break
        return [
            {
                "band": band[2],
                "count": counts[band[2]],
                "share_pct": round(counts[band[2]] / total * 100, 2) if total else None,
            }
            for band in _RETURN_BANDS
        ]

    @staticmethod
    def _row_anchor_iso(row: Any) -> Optional[str]:
        anchor = getattr(row, "anchor_date", None)
        if isinstance(anchor, datetime):
            return anchor.date().isoformat()
        if isinstance(anchor, date):
            return anchor.isoformat()
        return None

    def _recent_misses(self, rows: Sequence[Any], *, limit: int) -> List[Dict[str, Any]]:
        misses = [row for row in rows if getattr(row, "outcome", None) == "miss"]

        def _sort_key(row: Any):
            anchor = getattr(row, "anchor_date", None)
            if isinstance(anchor, datetime):
                return anchor.date()
            if isinstance(anchor, date):
                return anchor
            return date.min

        misses.sort(key=_sort_key, reverse=True)
        safe_limit = max(0, int(limit))
        # Non-sensitive: signal type, horizon, realized return, and date only —
        # no stock identity is exposed on the public surface.
        return [
            {
                "signal_type": str(getattr(row, "action", None) or "unknown"),
                "horizon": str(getattr(row, "horizon", None) or "unknown"),
                "return_pct": (
                    round(float(row.stock_return_pct), 2)
                    if getattr(row, "stock_return_pct", None) is not None
                    else None
                ),
                "anchor_date": self._row_anchor_iso(row),
            }
            for row in misses[:safe_limit]
        ]
