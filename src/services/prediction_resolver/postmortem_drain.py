# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Map resolver postmortem jobs into typed lessons after a tick.

Production scheduler/CLI inject the existing ``InMemoryPostmortemQueue`` when
``AGENT_POSTMORTEM_ENABLED`` is on, then drain after a non-overlap tick. The
handler only maps already-stored outcome/score/actuals; it does not re-fetch
market data, invent direction, or roll back resolved rows.
"""

from __future__ import annotations

import logging
import math
import threading
from typing import Any, Callable, Dict, List, Mapping, Optional

from pydantic import ValidationError

from src.agent.evolution.budget import (
    DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET,
    LlmCallBudget,
    budget_from_config,
)
from src.agent.evolution.episode_lessons import (
    EpisodeLessonSink,
    InMemoryEpisodeLessonSink,
    record_reflection_lessons,
)
from src.agent.evolution.postmortem import (
    ResolvedClaimOutcome,
    ResolvedForecastInput,
    is_postmortem_enabled,
    reflect_resolved_forecast,
)
from src.services.prediction_resolver.postmortem_queue import (
    InMemoryPostmortemQueue,
    PostmortemJob,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

POSTMORTEM_LESSON_LAYER = "postmortem"
_SCORE_LABELS = frozenset({"hit", "partial", "miss", "data_unavailable"})
_DEFAULT_DRAIN_WORKERS = 2
LlmCompleteFn = Callable[[str, str], str]


class ThreadSafeEpisodeLessonSink:
    """Process-local sidecar sink used when episode append is unavailable."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inner = InMemoryEpisodeLessonSink()

    def append_lessons(
        self,
        *,
        run_id: str,
        episode_id: Optional[str],
        lessons: Any,
        layer: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            self._inner.append_lessons(
                run_id=run_id,
                episode_id=episode_id,
                lessons=lessons,
                layer=layer,
                meta=meta,
            )

    @property
    def records(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._inner.records)

    def clear(self) -> None:
        with self._lock:
            self._inner.records.clear()


_DEFAULT_LESSON_SINK = ThreadSafeEpisodeLessonSink()


def default_postmortem_lesson_sink() -> ThreadSafeEpisodeLessonSink:
    return _DEFAULT_LESSON_SINK


def maybe_build_postmortem_queue(config: Any) -> Optional[InMemoryPostmortemQueue]:
    """Inject the in-memory queue only when the existing postmortem flag is on."""
    if not is_postmortem_enabled(config):
        return None
    return InMemoryPostmortemQueue()


def map_postmortem_job_to_input(
    job: PostmortemJob,
    *,
    episode_id: Optional[str] = None,
) -> Optional[ResolvedForecastInput]:
    """Build ``ResolvedForecastInput`` from stored job payload only.

    Direction is copied from stored claims or scored actuals when present. It
    is never inferred from prices.
    """
    if job is None:
        return None
    prediction_id = str(job.prediction_id or "").strip()
    if not prediction_id:
        return None
    outcome = job.outcome if isinstance(job.outcome, Mapping) else {}
    run_id = _optional_id(outcome.get("run_id"))
    resolved_episode = _optional_id(episode_id) or run_id or prediction_id
    claims = _claims_from_outcome(outcome)
    if not claims:
        logger.info(
            "Skipping postmortem job without stored claim scores prediction_id=%s",
            prediction_id,
        )
        return None
    try:
        return ResolvedForecastInput(
            episode_id=resolved_episode[:128],
            prediction_id=prediction_id[:128],
            run_id=run_id,
            symbol=_optional_text(outcome.get("symbol"), maximum=32),
            market=_optional_text(outcome.get("market"), maximum=16),
            claims=claims,
            evidence_refs=_string_list(outcome.get("evidence_refs")),
            flags=_string_list(outcome.get("flags")),
        )
    except (ValidationError, TypeError, ValueError) as exc:
        log_safe_exception(
            logger,
            "Postmortem job mapping failed",
            exc,
            error_code="prediction_resolver_postmortem_map_failed",
            context={"prediction_id": prediction_id},
            level=logging.WARNING,
        )
        return None


def handle_postmortem_job(
    job: PostmortemJob,
    *,
    config: Any = None,
    sink: Optional[EpisodeLessonSink] = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    budget: Optional[LlmCallBudget] = None,
) -> None:
    """Reflect one drained job and project typed lessons. Fail-soft."""
    outcome = job.outcome if isinstance(job.outcome, Mapping) else {}
    run_id = _optional_id(outcome.get("run_id"))
    episode_id = _lookup_episode_id(run_id, config)
    item = map_postmortem_job_to_input(job, episode_id=episode_id)
    if item is None:
        return
    result = reflect_resolved_forecast(
        item,
        config=config,
        llm_complete=llm_complete,
        budget=budget,
        allow_deterministic_lessons=True,
    )
    record_reflection_lessons(
        sink if sink is not None else _DEFAULT_LESSON_SINK,
        result,
        layer=POSTMORTEM_LESSON_LAYER,
        run_id=run_id or result.run_id,
        episode_id=item.episode_id,
        meta={
            "layer": POSTMORTEM_LESSON_LAYER,
            "prediction_id": item.prediction_id,
            "label": outcome.get("label"),
        },
    )


def drain_postmortem_queue(
    queue: Any,
    *,
    skipped_overlap: bool,
    max_items: int,
    config: Any = None,
    sink: Optional[EpisodeLessonSink] = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    max_workers: Optional[int] = None,
) -> int:
    """Drain at most ``max_items`` jobs after a non-overlap tick.

    Drain/LLM/episode errors are logged and requeued by the queue. Resolved
    prediction rows are never written here.
    """
    if skipped_overlap or queue is None:
        return 0
    drain = getattr(queue, "drain", None)
    if not callable(drain):
        return 0
    if isinstance(max_items, bool) or not isinstance(max_items, int):
        logger.warning(
            "Invalid postmortem drain max_items=%r; skipping drain",
            max_items,
        )
        return 0
    if max_items <= 0:
        return 0
    workers = (
        _DEFAULT_DRAIN_WORKERS if max_workers is None else int(max_workers)
    )
    if llm_complete is not None:
        workers = 1
    workers = max(1, min(workers, max_items, 16))
    call_budget = budget_from_config(
        config,
        default=DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET,
        attr="agent_postmortem_llm_budget",
    )
    lesson_sink = sink if sink is not None else _DEFAULT_LESSON_SINK

    def _handler(job: PostmortemJob) -> None:
        handle_postmortem_job(
            job,
            config=config,
            sink=lesson_sink,
            llm_complete=llm_complete,
            budget=call_budget,
        )

    try:
        return int(
            drain(
                handler=_handler,
                max_items=max_items,
                max_workers=workers,
            )
        )
    except Exception as exc:  # broad-exception: fallback_recorded - fail-soft drain
        log_safe_exception(
            logger,
            "Prediction postmortem drain failed; resolved rows were not rolled back",
            exc,
            error_code="prediction_resolver_postmortem_drain_failed",
            level=logging.WARNING,
        )
        return 0


def _lookup_episode_id(run_id: Optional[str], config: Any) -> Optional[str]:
    if not run_id:
        return None
    if getattr(config, "agent_episode_log_enabled", None) is not True:
        return None
    try:
        from src.services.agent_episode_service import AgentEpisodeService

        episodes = AgentEpisodeService(config=config).get_by_run_id(run_id)
    except Exception as exc:  # broad-exception: fallback_recorded - missing episode is not fatal
        log_safe_exception(
            logger,
            "Postmortem episode lookup failed",
            exc,
            error_code="prediction_resolver_postmortem_episode_lookup_failed",
            context={"run_id": run_id},
            level=logging.WARNING,
        )
        return None
    if not episodes:
        return None
    episode_id = getattr(episodes[0], "episode_id", None)
    return _optional_id(episode_id)


def _claims_from_outcome(outcome: Mapping[str, Any]) -> List[ResolvedClaimOutcome]:
    score = outcome.get("score")
    score_payload = score if isinstance(score, Mapping) else {}
    raw_results = score_payload.get("claim_results")
    if not isinstance(raw_results, list):
        return []
    original_by_id = _original_claims_by_id(outcome.get("claims"))
    actuals = outcome.get("actuals") if isinstance(outcome.get("actuals"), Mapping) else {}
    claims: List[ResolvedClaimOutcome] = []
    for raw in raw_results:
        if not isinstance(raw, Mapping):
            continue
        claim_id = str(raw.get("claim_id") or "").strip()
        if not claim_id:
            continue
        label = raw.get("outcome")
        if label not in _SCORE_LABELS:
            continue
        original = original_by_id.get(claim_id) or {}
        try:
            claims.append(
                ResolvedClaimOutcome(
                    claim_id=claim_id[:128],
                    claim_type=_claim_type(raw, original),
                    score=label,
                    confidence=_optional_confidence(
                        raw.get("confidence", original.get("confidence"))
                    ),
                    predicted=_predicted_from_stored(original),
                    actual=_actual_from_stored(raw, actuals),
                    signals=_signals_from_stored(raw, outcome),
                )
            )
        except (ValidationError, TypeError, ValueError) as exc:
            log_safe_exception(
                logger,
                "Skipping unmappable stored claim for postmortem",
                exc,
                error_code="prediction_resolver_postmortem_claim_map_failed",
                context={"claim_id": claim_id},
                level=logging.INFO,
            )
            continue
        if len(claims) >= 16:
            break
    return claims


def _original_claims_by_id(raw_claims: Any) -> Dict[str, Mapping[str, Any]]:
    indexed: Dict[str, Mapping[str, Any]] = {}
    if not isinstance(raw_claims, list):
        return indexed
    for item in raw_claims:
        if not isinstance(item, Mapping):
            continue
        claim_id = str(item.get("claim_id") or "").strip()
        if claim_id and claim_id not in indexed:
            indexed[claim_id] = item
    return indexed


def _claim_type(raw: Mapping[str, Any], original: Mapping[str, Any]) -> str:
    for candidate in (
        raw.get("claim_type"),
        original.get("claim_type"),
        original.get("type"),
    ):
        text = _optional_text(candidate, maximum=64)
        if text:
            return text
    return "custom"


def _predicted_from_stored(original: Mapping[str, Any]) -> Dict[str, Any]:
    predicted: Dict[str, Any] = {}
    direction = original.get("direction")
    payload = original.get("payload")
    if isinstance(payload, Mapping) and not isinstance(direction, str):
        direction = payload.get("direction")
    if isinstance(direction, str) and direction.strip():
        predicted["direction"] = direction.strip()
    return predicted


def _actual_from_stored(
    raw: Mapping[str, Any],
    actuals: Mapping[str, Any],
) -> Dict[str, Any]:
    actual: Dict[str, Any] = {}
    actual_direction = raw.get("actual_direction")
    if isinstance(actual_direction, str) and actual_direction.strip():
        actual["direction"] = actual_direction.strip()
    for key in ("start_price", "end_price", "return_pct", "high_price", "low_price"):
        if key in actuals and actuals[key] is not None:
            actual[key] = actuals[key]
    realized = raw.get("realized_return_pct")
    if realized is not None and "return_pct" not in actual:
        actual["return_pct"] = realized
    return actual


def _signals_from_stored(raw: Mapping[str, Any], outcome: Mapping[str, Any]) -> List[str]:
    details = raw.get("details")
    signals: List[str] = []
    if isinstance(details, Mapping) and isinstance(details.get("signals"), list):
        signals.extend(
            item.strip().lower()
            for item in details["signals"]
            if isinstance(item, str) and item.strip()
        )
    flags = outcome.get("flags")
    if isinstance(flags, list):
        signals.extend(
            item.strip().lower()
            for item in flags
            if isinstance(item, str) and item.strip()
        )
    ordered: List[str] = []
    for item in signals:
        if item not in ordered:
            ordered.append(item)
    return ordered[:16]


def _optional_id(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:128] if text else None


def _optional_text(value: Any, *, maximum: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:maximum] if text else None


def _optional_confidence(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        return None
    return number


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        if len(out) >= 16:
            break
    return out


__all__ = [
    "POSTMORTEM_LESSON_LAYER",
    "ThreadSafeEpisodeLessonSink",
    "default_postmortem_lesson_sink",
    "drain_postmortem_queue",
    "handle_postmortem_job",
    "map_postmortem_job_to_input",
    "maybe_build_postmortem_queue",
]
