# -*- coding: utf-8 -*-
"""Backtest methodology contract (pure, DB-agnostic).

Centralizes:
- explicit cost / slippage model parameters
- look-ahead and survivorship bias disclosures
- in-sample / out-of-sample sample split labeling
- finite numeric guards and currency-return policy notes

These statements are research-honesty metadata. Keep disclosures explicit when the engine surface grows. They must never be phrased as
return promises or live-fill guarantees.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
from typing import Any, Dict, List, Optional, Sequence


SAMPLE_SPLIT_FULL = "full"
SAMPLE_SPLIT_IN_SAMPLE = "in_sample"
SAMPLE_SPLIT_OUT_OF_SAMPLE = "out_of_sample"
VALID_SAMPLE_SPLITS = frozenset(
    {
        SAMPLE_SPLIT_FULL,
        SAMPLE_SPLIT_IN_SAMPLE,
        SAMPLE_SPLIT_OUT_OF_SAMPLE,
    }
)

# Shared disclaimer codes used by API/report surfaces.
DISCLAIMER_NOT_RETURN_PROMISE = "not_return_promise"
DISCLAIMER_HISTORICAL_SIMULATION = "historical_simulation_only"
DISCLAIMER_LOOKAHEAD_FORWARD_ONLY = "look_ahead_forward_only"
DISCLAIMER_SURVIVORSHIP_ANALYZED_UNIVERSE = "survivorship_analyzed_universe"
DISCLAIMER_COST_MODEL_EXPLICIT = "cost_model_explicit"
DISCLAIMER_PERCENT_RETURNS_CURRENCY_AGNOSTIC = "percent_returns_currency_agnostic"
DISCLAIMER_LLM_NONDETERMINISM = "llm_nondeterminism"

# Matches BacktestResult.engine_version VARCHAR(16).
ENGINE_VERSION_MAX_LEN = 16
_COST_FINGERPRINT_LEN = 6


@dataclass(frozen=True)
class CostModelConfig:
    """Round-trip cost model expressed in basis points per side."""

    commission_bps: float = 0.0
    slippage_bps: float = 0.0
    model: str = "explicit_bps_per_side"

    def __post_init__(self) -> None:
        commission = _require_non_negative_finite(
            self.commission_bps,
            field_name="commission_bps",
        )
        slippage = _require_non_negative_finite(
            self.slippage_bps,
            field_name="slippage_bps",
        )
        object.__setattr__(self, "commission_bps", commission)
        object.__setattr__(self, "slippage_bps", slippage)

    @property
    def round_trip_cost_pct(self) -> float:
        """Total percentage drag for a long entry+exit (two sides)."""
        per_side_pct = (self.commission_bps + self.slippage_bps) / 100.0
        return round(per_side_pct * 2.0, 6)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["round_trip_cost_pct"] = self.round_trip_cost_pct
        return payload

    def is_zero_friction(self) -> bool:
        return self.commission_bps == 0.0 and self.slippage_bps == 0.0

    def fingerprint(self) -> str:
        """Stable short digest of the bps pair used in stored engine identity."""
        raw = f"{self.commission_bps:.6f}:{self.slippage_bps:.6f}".encode("ascii")
        return hashlib.sha1(raw).hexdigest()[:_COST_FINGERPRINT_LEN]


@dataclass(frozen=True)
class SampleSplitConfig:
    """Label / filter historical rows into research (IS) vs hold-out (OOS)."""

    mode: str = SAMPLE_SPLIT_FULL
    split_date: Optional[date] = None

    def __post_init__(self) -> None:
        mode = str(self.mode or SAMPLE_SPLIT_FULL).strip().lower()
        if mode not in VALID_SAMPLE_SPLITS:
            raise ValueError(
                "sample_split must be one of: "
                + ", ".join(sorted(VALID_SAMPLE_SPLITS))
            )
        if mode != SAMPLE_SPLIT_FULL and self.split_date is None:
            raise ValueError(
                "split_date is required when sample_split is "
                f"{SAMPLE_SPLIT_IN_SAMPLE} or {SAMPLE_SPLIT_OUT_OF_SAMPLE}"
            )
        object.__setattr__(self, "mode", mode)

    def includes(self, analysis_date: Optional[date]) -> bool:
        """Return whether *analysis_date* belongs to this split."""
        if self.mode == SAMPLE_SPLIT_FULL:
            return True
        if analysis_date is None or self.split_date is None:
            return False
        if self.mode == SAMPLE_SPLIT_IN_SAMPLE:
            return analysis_date < self.split_date
        return analysis_date >= self.split_date

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "split_date": (
                self.split_date.isoformat() if self.split_date is not None else None
            ),
        }


def engine_version_for_cost_model(
    base: str,
    cost_model: Optional[CostModelConfig] = None,
) -> str:
    """Bind stored/query engine identity to the cost model that produced net returns.

    Zero-friction (the default) keeps the configured label so existing ``v1``
    rows remain visible. Non-zero commission/slippage appends a short
    fingerprint so changing bps cannot mix previously stored net returns
    into a new methodology disclosure under the same BACKTEST_ENGINE_VERSION.
    """
    label = str(base or "v1").strip() or "v1"
    cost = cost_model or CostModelConfig()
    if cost.is_zero_friction():
        return label[:ENGINE_VERSION_MAX_LEN]
    fingerprint = cost.fingerprint()
    prefix_budget = ENGINE_VERSION_MAX_LEN - 1 - len(fingerprint)
    prefix = label[: max(prefix_budget, 1)]
    return f"{prefix}-{fingerprint}"[:ENGINE_VERSION_MAX_LEN]


def apply_round_trip_cost(
    *,
    gross_return_pct: Optional[float],
    cost_model: CostModelConfig,
    position: str,
) -> Optional[float]:
    """Apply explicit round-trip costs to a long simulated return.

    Cash positions stay at 0. Non-finite gross values are rejected (``None``).
    """
    if position != "long":
        return 0.0 if position == "cash" else None
    if gross_return_pct is None:
        return None
    try:
        gross = float(gross_return_pct)
    except (TypeError, ValueError):
        return None
    if not _is_finite(gross):
        return None
    net = gross - float(cost_model.round_trip_cost_pct)
    if not _is_finite(net):
        return None
    return round(net, 6)


def build_methodology_statement(
    *,
    cost_model: Optional[CostModelConfig] = None,
    sample_split: Optional[SampleSplitConfig] = None,
    engine_version: str = "v1",
    eval_window_days: Optional[int] = None,
    metric_source: str = "analysis_advice",
    extra_limitations: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Build the public methodology block attached to reports and summaries."""
    cost = cost_model or CostModelConfig()
    split = sample_split or SampleSplitConfig()
    limitations: List[str] = [
        (
            "Historical simulation only. Metrics are not a promise of future "
            "returns and are not live broker fills."
        ),
        (
            "Look-ahead protection: evaluation uses only forward bars after the "
            "resolved analysis/start session; start prices are not taken from "
            "future closes."
        ),
        (
            "Survivorship bias: the universe is limited to symbols that already "
            "have analysis history in this installation; delisted or never-"
            "analyzed names are absent."
        ),
        (
            "Cost model is explicit basis-points-per-side "
            f"(commission_bps={cost.commission_bps}, "
            f"slippage_bps={cost.slippage_bps}, "
            f"round_trip_cost_pct={cost.round_trip_cost_pct}). "
            "Defaults of zero mean zero friction, not zero market impact."
        ),
        (
            "Return units are relative percentages and are currency-agnostic. "
            "Absolute prices from different quote currencies are never summed "
            "without FX normalization; this engine aggregates percent returns only."
        ),
        (
            f"Sample split mode={split.mode}"
            + (
                f", split_date={split.split_date.isoformat()}"
                if split.split_date is not None
                else ""
            )
            + ". Full mode mixes research and hold-out unless a split is applied."
        ),
    ]
    if metric_source == "skill_opinion_outcomes":
        limitations.append(
            "Skill metrics come from attributable YAML skill-opinion outcomes "
            "and share the same public percentage fields as analysis-advice "
            "backtests; LLM skill text is non-deterministic across re-runs."
        )
    if extra_limitations:
        for item in extra_limitations:
            text = str(item or "").strip()
            if text:
                limitations.append(text)

    return {
        "version": "v1",
        "engine_version": str(engine_version or "v1"),
        "metric_source": metric_source,
        "eval_window_days": (
            int(eval_window_days) if eval_window_days is not None else None
        ),
        "is_return_promise": False,
        "disclaimer": (
            "Backtest and skill validation metrics are historical simulations "
            "for research only. They are not investment advice and must not be "
            "presented as guaranteed or expected future returns."
        ),
        "disclaimer_codes": [
            DISCLAIMER_NOT_RETURN_PROMISE,
            DISCLAIMER_HISTORICAL_SIMULATION,
            DISCLAIMER_LOOKAHEAD_FORWARD_ONLY,
            DISCLAIMER_SURVIVORSHIP_ANALYZED_UNIVERSE,
            DISCLAIMER_COST_MODEL_EXPLICIT,
            DISCLAIMER_PERCENT_RETURNS_CURRENCY_AGNOSTIC,
            DISCLAIMER_LLM_NONDETERMINISM,
        ],
        "look_ahead_policy": "forward_only_after_resolved_start_session",
        "survivorship_policy": "analyzed_universe_only",
        "cost_model": cost.to_dict(),
        "sample_split": split.to_dict(),
        "return_units": "percent_relative",
        "currency_policy": (
            "percent_returns_currency_agnostic;"
            "absolute_prices_not_aggregated_across_currencies"
        ),
        "limitations": limitations,
    }


def normalize_sample_split(
    mode: Optional[str],
    split_date: Optional[date],
) -> SampleSplitConfig:
    """Validate and normalize sample-split request parameters."""
    return SampleSplitConfig(
        mode=str(mode or SAMPLE_SPLIT_FULL),
        split_date=split_date,
    )


def _is_finite(value: float) -> bool:
    import math

    return math.isfinite(value)


def _require_non_negative_finite(value: Any, *, field_name: str) -> float:
    import math

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite (rejected NaN/±Inf)")
    if number < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return number
