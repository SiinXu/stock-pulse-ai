# -*- coding: utf-8 -*-
"""Pull overlay: resolved forecast outcomes into gated confidence adapters.

Default-off. Reads scored ``agent_predictions`` through the existing
``list_by_symbol_market`` index (limit <= 500) and passes forecast stats into
``calibrate_confidence``. Does not copy AgentMemory arithmetic, does not blend
backtest stats, and does not mutate BaseAgent, Soul, ToolSurface, episodes,
or the prediction store.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.agent.evolution.adapters import (
    DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES,
    calibrate_confidence,
    is_online_adapters_enabled,
    record_adapter_influence,
)
from src.agent.memory import AgentMemory
from src.agent.protocols import AgentContext
from src.market.context import detect_market
from src.schemas.agent_prediction import STATUS_RESOLVED
from src.schemas.prediction_claim_scoring import OUTCOME_NUMERIC_SCORE
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

FORECAST_OUTCOME_LIST_LIMIT = 500
REASON_MISSING_SCOPE = "missing_scope"
REASON_NO_SCORED_OUTCOMES = "no_scored_outcomes"

_SCORED_LABELS = frozenset(OUTCOME_NUMERIC_SCORE.keys())


def _identity(*, samples: int = 0, reason: str) -> Dict[str, Any]:
    return {
        "applied": False,
        "factor": 1.0,
        "samples": int(samples),
        "reason": reason,
    }


def _coerce_min_samples(value: Any) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES


def _usable_confidence(value: Any) -> Optional[float]:
    """Finite confidence in [0, 1]. Preserve 0.0; do not treat it as missing."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        return None
    return number


def _outcome_mapping(record: Any) -> Optional[Mapping[str, Any]]:
    outcome = getattr(record, "outcome", None)
    return outcome if isinstance(outcome, Mapping) else None


def _outcome_label(record: Any) -> Optional[str]:
    outcome = _outcome_mapping(record)
    if outcome is None:
        return None
    label = outcome.get("label")
    return label if isinstance(label, str) and label else None


def _claim_confidence(claim: Any) -> Optional[float]:
    if isinstance(claim, Mapping):
        return _usable_confidence(claim.get("confidence"))
    return _usable_confidence(getattr(claim, "confidence", None))


def row_confidence(record: Any) -> Optional[float]:
    """Usable confidence for one scored row.

    Prefer ``outcome.score.aggregate.mean_confidence`` when finite in
    ``[0, 1]``. Otherwise mean claim confidences that are finite in ``[0, 1]``.
    Never reads ``model_meta``. Never invents AgentMemory's 0.6 fallback.
    """
    outcome = _outcome_mapping(record)
    if outcome is not None:
        score = outcome.get("score")
        if isinstance(score, Mapping):
            aggregate = score.get("aggregate")
            if isinstance(aggregate, Mapping):
                nested = _usable_confidence(aggregate.get("mean_confidence"))
                if nested is not None:
                    return nested
    claims = getattr(record, "claims", None) or []
    if not isinstance(claims, Sequence) or isinstance(claims, (str, bytes)):
        return None
    values = [
        confidence
        for claim in claims
        for confidence in (_claim_confidence(claim),)
        if confidence is not None
    ]
    if not values:
        return None
    return sum(values) / float(len(values))


def load_scored_forecast_rows(
    repo: Any,
    *,
    symbol: str,
    market: str,
    limit: int = FORECAST_OUTCOME_LIST_LIMIT,
) -> List[Any]:
    """``list_by_symbol_market`` then keep resolved scored labels. Never ``list_due``."""
    code = str(symbol or "").strip()
    mkt = str(market or "").strip().lower()
    if not code or not mkt or repo is None:
        return []
    try:
        bound = int(limit)
    except (TypeError, ValueError):
        bound = FORECAST_OUTCOME_LIST_LIMIT
    bound = max(1, min(bound, FORECAST_OUTCOME_LIST_LIMIT))
    rows = repo.list_by_symbol_market(symbol=code, market=mkt, limit=bound)
    if not rows:
        return []
    scored: List[Any] = []
    for record in rows:
        if str(getattr(record, "status", "") or "") != STATUS_RESOLVED:
            continue
        label = _outcome_label(record)
        if label not in _SCORED_LABELS:
            continue
        scored.append(record)
    return scored


def forecast_calibration_stats(
    rows: Sequence[Any],
    *,
    min_samples: int,
) -> Dict[str, Any]:
    """``{total, accuracy, avg_confidence, used}`` from filtered scored rows."""
    threshold = _coerce_min_samples(min_samples)
    scores: List[float] = []
    confidences: List[float] = []
    for record in rows or ():
        label = _outcome_label(record)
        numeric = OUTCOME_NUMERIC_SCORE.get(label or "")
        if numeric is None:
            continue
        confidence = row_confidence(record)
        if confidence is None:
            continue
        scores.append(float(numeric))
        confidences.append(confidence)
    total = len(scores)
    if total == 0:
        return {
            "total": 0,
            "accuracy": 0.0,
            "avg_confidence": 0.0,
            "used": False,
        }
    accuracy = sum(scores) / float(total)
    avg_confidence = sum(confidences) / float(total)
    return {
        "total": total,
        "accuracy": accuracy,
        "avg_confidence": avg_confidence,
        "used": total >= threshold,
    }


class ForecastOutcomeMemory(AgentMemory):
    """AgentMemory subclass that serves forecast stats, not backtests.

    ``get_calibration`` stays on AgentMemory so adapter clamp arithmetic is
    not copied here. Accuracy and avg_confidence of 0.0 are stored as real
    zeros, never as missing.
    """

    def __init__(
        self,
        *,
        total: int,
        accuracy: float,
        avg_confidence: float,
        min_samples: int,
    ) -> None:
        super().__init__(enabled=True, min_samples=min_samples)
        self._forecast_total = int(total)
        self._forecast_accuracy = float(accuracy)
        self._forecast_avg_confidence = float(avg_confidence)

    def _get_accuracy_stats(
        self,
        agent_name: str,
        stock_code: Optional[str],
        skill_id: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "total": self._forecast_total,
            "accuracy": self._forecast_accuracy,
            "direction_accuracy": self._forecast_accuracy,
            "avg_confidence": self._forecast_avg_confidence,
        }


def _record_influence(
    ctx: Optional[AgentContext],
    meta: Dict[str, Any],
    *,
    config: Any,
) -> None:
    if ctx is None:
        return
    record_adapter_influence(ctx, {"confidence": meta}, config=config)


def apply_forecast_outcome_calibration(
    raw: float,
    *,
    ctx: Optional[AgentContext],
    config: Any,
    repo: Any,
    agent_name: str,
    stock_code: Optional[str],
) -> Tuple[float, Dict[str, Any]]:
    """Flag-off identity; else pull rows, call calibrate_confidence, record meta.

    When adapters are off or ``stock_code`` is missing, the prediction store is
    not queried. Forecast ``N >= min_samples`` uses forecast stats only — never
    AgentMemory / backtest rows. Store failures log and return identity.
    """
    if not is_online_adapters_enabled(config):
        return float(raw), _identity(reason="adapters_disabled")

    min_samples = _coerce_min_samples(
        getattr(config, "agent_online_adapters_min_samples", DEFAULT_ONLINE_ADAPTERS_MIN_SAMPLES)
    )
    code = str(stock_code or "").strip()
    if not code:
        meta = _identity(reason=REASON_MISSING_SCOPE)
        _record_influence(ctx, meta, config=config)
        return float(raw), meta

    market = detect_market(code)
    try:
        rows = load_scored_forecast_rows(
            repo,
            symbol=code,
            market=market,
            limit=FORECAST_OUTCOME_LIST_LIMIT,
        )
    except Exception as exc:
        log_safe_exception(
            logger,
            "Forecast outcome overlay store lookup failed",
            exc,
            error_code="forecast_outcome_overlay_store_failed",
            level=logging.DEBUG,
            context={"stock_code": code, "agent_name": agent_name},
        )
        meta = _identity(reason=REASON_NO_SCORED_OUTCOMES)
        _record_influence(ctx, meta, config=config)
        return float(raw), meta

    stats = forecast_calibration_stats(rows, min_samples=min_samples)
    total = int(stats["total"])
    if total == 0:
        meta = _identity(reason=REASON_NO_SCORED_OUTCOMES)
        _record_influence(ctx, meta, config=config)
        return float(raw), meta

    forecast_memory = ForecastOutcomeMemory(
        total=total,
        accuracy=float(stats["accuracy"]),
        avg_confidence=float(stats["avg_confidence"]),
        min_samples=min_samples,
    )
    adjusted, meta = calibrate_confidence(
        raw,
        memory=forecast_memory,
        agent_name=agent_name,
        stock_code=code,
        min_samples=min_samples,
        config=config,
    )
    _record_influence(ctx, meta, config=config)
    return adjusted, meta
