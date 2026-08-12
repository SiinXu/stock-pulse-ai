# -*- coding: utf-8 -*-
"""
Multi-model consensus and disagreement comparison (#154).

Runs the same analysis task across 2–3 models on a shared data snapshot and
produces a structured consensus / disagreement product. Disagreement points use
the same low-sensitivity point contract as multi-agent disagreement handling
(#1205 / #246 / #193): source, kind, severity, participants, sides, summary_key.

Product honesty rules:
- Disagreement is never averaged into a synthetic middle signal.
- majority_vote_used is always False.
- Single-model failure degrades to the remaining successful model(s) with
  explicit degradation annotation; one success becomes a single-model result.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from src.agent.provider_trace import resolved_model_provider_identity
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "multi-model-consensus-v1"

# Escalation / verdict constants aligned with disagreement_handling (#1205).
ESCALATION_NONE = "none"
ESCALATION_RECORD = "record"
ESCALATION_CROSS_VALIDATE = "cross_validate"
ESCALATION_SPLIT = "escalate_split"

VERDICT_CONSENSUS = "consensus"
VERDICT_SPLIT = "split"
VERDICT_INSUFFICIENT = "insufficient"

RESOLUTION_RESOLVED = "resolved"
RESOLUTION_PARTIAL = "partially_resolved"
RESOLUTION_UNRESOLVED = "unresolved"

PRESET_FAST = "fast"
PRESET_QUALITY = "quality"
_VALID_PRESETS = frozenset({PRESET_FAST, PRESET_QUALITY})

_DEFAULT_MAX_MODELS = 3
_DEFAULT_HIGH_CONFIDENCE = 0.7
_DEFAULT_MEDIUM_CONFIDENCE = 0.55
_SPLIT_CONFIDENCE_CAP = 0.35

_BULLISH = frozenset({"strong_buy", "buy", "add"})
_BEARISH = frozenset({"strong_sell", "sell", "reduce", "avoid"})
_NEUTRAL = frozenset({"hold", "watch", "alert"})

AnalyzeFn = Callable[..., Any]


def is_multi_model_consensus_enabled(config: Any = None) -> bool:
    """Return whether default-off multi-model consensus is enabled."""
    if config is None:
        return False
    return bool(getattr(config, "multi_model_consensus_enabled", False))


def resolve_consensus_models(config: Any) -> List[str]:
    """Resolve the ordered model set for a multi-model comparison run.

    Priority:
    1. Explicit ``multi_model_consensus_models`` list
    2. Preset (``fast`` / ``quality``) over primary + fallbacks
    3. Primary ``litellm_model`` + ``litellm_fallback_models`` (capped)

    Does **not** apply USD budget caps; use :func:`resolve_consensus_models_for_run`.
    """
    max_models = _clamp_int(
        getattr(config, "multi_model_consensus_max_models", None),
        _DEFAULT_MAX_MODELS,
        minimum=2,
        maximum=5,
    )
    explicit = _normalize_model_list(getattr(config, "multi_model_consensus_models", None))
    if explicit:
        return explicit[:max_models]

    primary = str(getattr(config, "litellm_model", "") or "").strip()
    fallbacks = _normalize_model_list(getattr(config, "litellm_fallback_models", None))
    preset = str(getattr(config, "multi_model_consensus_preset", "") or "").strip().lower()

    candidates: List[str] = []
    if primary:
        candidates.append(primary)
    for model in fallbacks:
        if model not in candidates:
            candidates.append(model)

    if preset == PRESET_FAST and candidates:
        # Prefer fewer / first models for a cheap consensus check.
        return candidates[: min(2, max_models)]
    if preset == PRESET_QUALITY and candidates:
        return candidates[:max_models]
    return candidates[:max_models]


# When USD budget is configured without live provider pricing, hard-cap fan-out
# to this many models (conservative). Zero/negative budget closes multi-model.
_BUDGET_MODE_MODEL_CAP = 2


def resolve_consensus_models_for_run(
    config: Any,
) -> Tuple[List[str], Dict[str, Any]]:
    """Resolve models and apply hard budget constraints for one analysis run.

    Budget rules (``MULTI_MODEL_CONSENSUS_MAX_COST_USD``):
    - unset / None: no USD constraint (only ``MAX_MODELS`` applies)
    - <= 0: multi-model fan-out closed (empty model list)
    - > 0 without live pricing: hard-cap to ``_BUDGET_MODE_MODEL_CAP`` models and
      record skipped models under ``skipped_for_budget``
    """
    models = resolve_consensus_models(config)
    max_cost_raw = getattr(config, "multi_model_consensus_max_cost_usd", None)
    budget: Dict[str, Any] = {
        "max_cost_usd": None,
        "budget_enforced": False,
        "budget_reason": None,
        "skipped_for_budget": [],
        "models_before_budget": list(models),
    }
    if max_cost_raw is None or isinstance(max_cost_raw, bool):
        return models, budget
    try:
        max_cost = float(max_cost_raw)
    except (TypeError, ValueError):
        return models, budget
    budget["max_cost_usd"] = max_cost
    if max_cost <= 0:
        budget["budget_enforced"] = True
        budget["budget_reason"] = "budget_closed"
        budget["skipped_for_budget"] = list(models)
        return [], budget
    if len(models) > _BUDGET_MODE_MODEL_CAP:
        budget["budget_enforced"] = True
        budget["budget_reason"] = "max_cost_usd_budget_mode_cap"
        budget["skipped_for_budget"] = list(models[_BUDGET_MODE_MODEL_CAP:])
        models = models[:_BUDGET_MODE_MODEL_CAP]
    return models, budget


def build_model_stance(result: Any, *, requested_model: str) -> Dict[str, Any]:
    """Extract a low-sensitivity stance from an AnalysisResult-like object."""
    success = bool(getattr(result, "success", False)) if result is not None else False
    model_used = str(getattr(result, "model_used", None) or requested_model or "").strip()
    model_list = []
    provider = ""
    if result is not None:
        # Provider identity is best-effort from the model string.
        pass
    wire_model, provider = resolved_model_provider_identity(model_used or requested_model, model_list)

    if not success or result is None:
        return {
            "model_id": requested_model,
            "model_version": wire_model or requested_model,
            "provider": provider or _provider_from_model(requested_model),
            "status": "failed",
            "signal": None,
            "decision_type": None,
            "action": None,
            "operation_advice": None,
            "sentiment_score": None,
            "score_band": None,
            "confidence_level": None,
            "confidence": None,
            "key_risks": [],
            "key_catalysts": [],
            "error_type": str(getattr(result, "error_code", None) or getattr(result, "error_message", None) or "analysis_failed"),
        }

    decision_type = _canonical_signal(
        getattr(result, "decision_type", None)
        or getattr(result, "action", None)
        or getattr(result, "operation_advice", None)
    )
    action = str(getattr(result, "action", None) or "").strip() or None
    score = _safe_int(getattr(result, "sentiment_score", None))
    confidence = _confidence_to_unit(getattr(result, "confidence_level", None))
    risks = _extract_risks(result)
    catalysts = _extract_catalysts(result)

    return {
        "model_id": requested_model,
        "model_version": wire_model or model_used or requested_model,
        "provider": provider or _provider_from_model(model_used or requested_model),
        "status": "success",
        "signal": decision_type,
        "decision_type": decision_type,
        "action": action,
        "operation_advice": str(getattr(result, "operation_advice", None) or "") or None,
        "sentiment_score": score,
        "score_band": _score_band(score),
        "confidence_level": str(getattr(result, "confidence_level", None) or "") or None,
        "confidence": confidence,
        "key_risks": risks,
        "key_catalysts": catalysts,
        "error_type": None,
    }


def build_multi_model_comparison(
    stances: Sequence[Mapping[str, Any]],
    *,
    requested_models: Sequence[str],
    shared_snapshot_fingerprint: str = "",
    budget: Optional[Mapping[str, Any]] = None,
    high_confidence_threshold: float = _DEFAULT_HIGH_CONFIDENCE,
    medium_confidence_threshold: float = _DEFAULT_MEDIUM_CONFIDENCE,
) -> Dict[str, Any]:
    """Build the structured multi-model comparison product payload."""
    high_threshold = _clamp_unit(high_confidence_threshold, _DEFAULT_HIGH_CONFIDENCE)
    medium_threshold = _clamp_unit(medium_confidence_threshold, _DEFAULT_MEDIUM_CONFIDENCE)
    if medium_threshold > high_threshold:
        medium_threshold = high_threshold

    models = [dict(item) for item in stances if isinstance(item, Mapping)]
    successful = [m for m in models if m.get("status") == "success" and m.get("signal")]
    failed = [m for m in models if m.get("status") != "success"]

    points = _collect_model_points(successful)
    disagreement_score = _score_disagreement(points, successful, high_threshold)
    high_disagreement = _is_high_disagreement(points, successful, high_threshold)
    consensus_level = _consensus_level(successful, points, high_disagreement)
    consensus_score = _consensus_score(successful, points)

    if len(successful) == 0:
        status = "insufficient"
        degradation = {
            "reason": "all_models_failed",
            "failed_models": [m.get("model_id") for m in failed],
            "annotation": "no_usable_model_result",
        }
        verdict_mode = VERDICT_INSUFFICIENT
        resolution_status = RESOLUTION_UNRESOLVED
        escalation = ESCALATION_NONE
        explanation_key = "multi_model.insufficient"
        applied_signal = "hold"
        pre_signal = None
    elif len(successful) == 1:
        only = successful[0]
        if failed or len(requested_models) > 1:
            status = "degraded_single"
            degradation = {
                "reason": "single_model_success",
                "failed_models": [m.get("model_id") for m in failed],
                "annotation": "single_model_fallback",
                "successful_model": only.get("model_id"),
            }
        else:
            status = "ok"
            degradation = None
        verdict_mode = VERDICT_INSUFFICIENT if consensus_level == "insufficient" else VERDICT_CONSENSUS
        resolution_status = RESOLUTION_RESOLVED if not failed else RESOLUTION_PARTIAL
        escalation = ESCALATION_RECORD if failed else ESCALATION_NONE
        explanation_key = (
            "multi_model.degraded_single"
            if failed or len(requested_models) > 1
            else "multi_model.single_model"
        )
        pre_signal = only.get("signal")
        applied_signal = pre_signal or "hold"
    else:
        status = "degraded_partial" if failed else "ok"
        degradation = (
            {
                "reason": "partial_model_failure",
                "failed_models": [m.get("model_id") for m in failed],
                "annotation": "partial_success",
            }
            if failed
            else None
        )
        if high_disagreement:
            verdict_mode = VERDICT_SPLIT
            resolution_status = RESOLUTION_UNRESOLVED
            escalation = ESCALATION_SPLIT
            explanation_key = "multi_model.high_split"
            # Honesty: do not invent a majority/averaged signal.
            # applied_final_signal=hold is the *comparison policy* recommendation only;
            # the primary AnalysisResult keeps the primary model direction and is
            # honesty-annotated via confidence dampening + risk note (not blended).
            pre_signal = _primary_signal(successful)
            applied_signal = "hold"
        elif points:
            verdict_mode = VERDICT_CONSENSUS
            resolution_status = RESOLUTION_PARTIAL
            escalation = ESCALATION_CROSS_VALIDATE if disagreement_score >= medium_threshold else ESCALATION_RECORD
            explanation_key = "multi_model.recorded"
            pre_signal = _primary_signal(successful)
            applied_signal = pre_signal or "hold"
        else:
            verdict_mode = VERDICT_CONSENSUS
            resolution_status = RESOLUTION_RESOLVED
            escalation = ESCALATION_NONE
            explanation_key = "multi_model.aligned"
            pre_signal = _primary_signal(successful)
            applied_signal = pre_signal or "hold"

    primary_model = None
    if successful:
        primary_model = successful[0].get("model_id")

    disagreement_handling = {
        "enabled": True,
        "high_disagreement": bool(high_disagreement),
        "verdict_mode": verdict_mode,
        "escalation": escalation,
        "resolution_status": resolution_status,
        "disagreement_score": round(disagreement_score, 4),
        "points": points,
        "cross_validation": {
            "requested": escalation in {ESCALATION_CROSS_VALIDATE, ESCALATION_SPLIT},
            "status": "completed" if escalation in {ESCALATION_CROSS_VALIDATE, ESCALATION_SPLIT} else "not_applicable",
            "role_layer_conflict": False,
            "strategy_layer_conflict": False,
            "model_layer_conflict": bool(points),
            "dual_layer_confirmed": False,
            "outcome": escalation if escalation in {ESCALATION_CROSS_VALIDATE, ESCALATION_SPLIT} else ESCALATION_NONE,
        },
        "policy": {
            "method": "multi_model_comparison",
            "majority_vote_used": False,
            "high_confidence_threshold": high_threshold,
            "medium_confidence_threshold": medium_threshold,
            "conservative_final_signal": "hold" if high_disagreement else None,
            "pre_escalation_final_signal": pre_signal,
            "applied_final_signal": applied_signal,
            "confidence_cap": _SPLIT_CONFIDENCE_CAP if high_disagreement else None,
            "averaging_used": False,
        },
        "explanation_key": explanation_key,
    }

    agreement_table = [
        {
            "model_id": m.get("model_id"),
            "model_version": m.get("model_version"),
            "status": m.get("status"),
            "action": m.get("action") or m.get("signal"),
            "signal": m.get("signal"),
            "score_band": m.get("score_band"),
            "sentiment_score": m.get("sentiment_score"),
            "confidence": m.get("confidence"),
            "confidence_level": m.get("confidence_level"),
            "key_risks": list(m.get("key_risks") or [])[:5],
            "key_catalysts": list(m.get("key_catalysts") or [])[:5],
        }
        for m in models
    ]

    budget_payload = dict(budget or {})
    budget_payload.setdefault("models_requested", list(requested_models))
    budget_payload.setdefault("models_run", [m.get("model_id") for m in models])

    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": True,
        "status": status,
        "degradation": degradation,
        "models": models,
        "agreement_table": agreement_table,
        "consensus_level": consensus_level,
        "consensus_score": round(consensus_score, 4),
        "primary_result_model": primary_model,
        "disagreement_handling": disagreement_handling,
        "shared_snapshot": {
            "context_fingerprint": shared_snapshot_fingerprint or "",
        },
        "budget": budget_payload,
        "trace": {
            "model_identities": [
                {
                    "model_id": m.get("model_id"),
                    "model_version": m.get("model_version"),
                    "provider": m.get("provider"),
                    "status": m.get("status"),
                }
                for m in models
            ],
        },
    }


def public_multi_model_comparison_payload(value: Any) -> Optional[Dict[str, Any]]:
    """Return a low-sensitivity public product slice for dashboards / reports."""
    if not isinstance(value, Mapping) or not value:
        return None
    if value.get("enabled") is not True:
        return None

    points: List[Dict[str, Any]] = []
    handling = value.get("disagreement_handling") if isinstance(value.get("disagreement_handling"), Mapping) else {}
    raw_points = handling.get("points") if isinstance(handling, Mapping) else value.get("points")
    if isinstance(raw_points, list):
        for item in raw_points[:12]:
            if not isinstance(item, Mapping):
                continue
            participants = item.get("participants")
            points.append(
                {
                    "source": str(item.get("source") or "model"),
                    "kind": str(item.get("kind") or "unknown"),
                    "severity": str(item.get("severity") or "medium"),
                    "participants": [
                        str(p).strip()
                        for p in (participants if isinstance(participants, list) else [])
                        if str(p).strip()
                    ][:12],
                    "summary_key": str(item.get("summary_key") or ""),
                }
            )

    policy = handling.get("policy") if isinstance(handling.get("policy"), Mapping) else {}
    public_handling = {
        "enabled": True,
        "high_disagreement": bool(handling.get("high_disagreement")),
        "verdict_mode": str(handling.get("verdict_mode") or VERDICT_CONSENSUS),
        "escalation": str(handling.get("escalation") or ESCALATION_NONE),
        "resolution_status": str(handling.get("resolution_status") or RESOLUTION_UNRESOLVED),
        "disagreement_score": _safe_float(handling.get("disagreement_score"), 0.0),
        "points": points,
        "policy": {
            "method": str(policy.get("method") or "multi_model_comparison"),
            "majority_vote_used": False,
            "averaging_used": False,
            "pre_escalation_final_signal": policy.get("pre_escalation_final_signal"),
            "applied_final_signal": policy.get("applied_final_signal"),
            "confidence_cap": policy.get("confidence_cap"),
        },
        "explanation_key": str(handling.get("explanation_key") or ""),
    }

    agreement_table = []
    raw_table = value.get("agreement_table")
    if isinstance(raw_table, list):
        for row in raw_table[:5]:
            if not isinstance(row, Mapping):
                continue
            agreement_table.append(
                {
                    "model_id": str(row.get("model_id") or ""),
                    "model_version": str(row.get("model_version") or row.get("model_id") or ""),
                    "status": str(row.get("status") or ""),
                    "action": row.get("action"),
                    "signal": row.get("signal"),
                    "score_band": row.get("score_band"),
                    "sentiment_score": row.get("sentiment_score"),
                    "confidence": row.get("confidence"),
                    "key_risks": list(row.get("key_risks") or [])[:3],
                    "key_catalysts": list(row.get("key_catalysts") or [])[:3],
                }
            )

    degradation = value.get("degradation") if isinstance(value.get("degradation"), Mapping) else None
    trace = value.get("trace") if isinstance(value.get("trace"), Mapping) else {}
    return {
        "schema_version": str(value.get("schema_version") or SCHEMA_VERSION),
        "enabled": True,
        "status": str(value.get("status") or "ok"),
        "degradation": degradation,
        "agreement_table": agreement_table,
        "consensus_level": str(value.get("consensus_level") or "insufficient"),
        "consensus_score": _safe_float(value.get("consensus_score"), 0.0),
        "primary_result_model": value.get("primary_result_model"),
        "disagreement_handling": public_handling,
        "shared_snapshot": dict(value.get("shared_snapshot") or {})
        if isinstance(value.get("shared_snapshot"), Mapping)
        else {},
        "budget": dict(value.get("budget") or {}) if isinstance(value.get("budget"), Mapping) else {},
        "trace": {
            "model_identities": list(trace.get("model_identities") or [])[:5],
        },
    }


def fingerprint_shared_snapshot(context: Mapping[str, Any], news_context: Optional[str] = None) -> str:
    """Build a stable fingerprint so multi-model runs share the same inputs."""
    payload = {
        "code": context.get("code"),
        "stock_name": context.get("stock_name"),
        "realtime": _select_keys(context.get("realtime"), ("price", "change_pct", "volume", "time")),
        "trend": _select_keys(context.get("trend"), ("signal", "score", "summary")),
        "news_len": len(news_context or ""),
        "news_hash": hashlib.sha256((news_context or "").encode("utf-8")).hexdigest()[:16]
        if news_context
        else "",
        "context_pack": bool(context.get("analysis_context_pack") or context.get("analysis_context_pack_summary")),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def run_multi_model_consensus_analysis(
    *,
    analyzer: Any,
    config: Any,
    context: Mapping[str, Any],
    news_context: Optional[str] = None,
    analysis_context_pack_summary: Optional[str] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    stream_progress_callback: Optional[Callable[[int], None]] = None,
    parallel: bool = False,
    record_llm_run: Optional[Callable[..., None]] = None,
    record_llm_run_started: Optional[Callable[..., None]] = None,
) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
    """Run multi-model analysis on a shared snapshot and return (primary_result, comparison).

    When fewer than two models are resolvable, returns (None, None) so the caller
    can fall back to the single-model path without product annotation.

    Model runs are **sequential by default**. The shared analyzer instance is not
    assumed thread-safe; ``parallel=True`` is accepted for callers that inject a
    thread-safe facade, but the stock pipeline keeps sequential execution.
    """
    models, budget_meta = resolve_consensus_models_for_run(config)
    if len(models) < 2:
        logger.info(
            "[multi_model_consensus] fewer than 2 models after budget resolution; "
            "skipping multi-model path (budget_enforced=%s reason=%s)",
            budget_meta.get("budget_enforced"),
            budget_meta.get("budget_reason"),
        )
        return None, None

    budget: Dict[str, Any] = {
        "max_models": len(models),
        "models_requested": list(models),
        "max_cost_usd": budget_meta.get("max_cost_usd"),
        "budget_enforced": bool(budget_meta.get("budget_enforced")),
        "budget_reason": budget_meta.get("budget_reason"),
        "skipped_for_budget": list(budget_meta.get("skipped_for_budget") or []),
        "models_before_budget": list(budget_meta.get("models_before_budget") or []),
        "execution": "parallel" if parallel else "sequential",
    }

    fingerprint = fingerprint_shared_snapshot(context, news_context)
    # Freeze a shallow copy so each model sees the same top-level snapshot keys.
    shared_context = dict(context)

    def _run_one(model_id: str) -> Tuple[str, Optional[Any], Optional[BaseException], int]:
        started = time.monotonic()
        if record_llm_run_started is not None:
            try:
                record_llm_run_started(model=model_id, call_type="multi_model_consensus")
            except Exception as exc:  # broad-exception: diagnostics fail-open
                log_safe_exception(
                    logger,
                    "multi-model llm start diagnostic failed",
                    exc,
                    error_code="multi_model_llm_start_diag_failed",
                    level=logging.DEBUG,
                )
        try:
            result = analyzer.analyze(
                shared_context,
                news_context=news_context,
                progress_callback=progress_callback,
                stream_progress_callback=stream_progress_callback,
                analysis_context_pack_summary=analysis_context_pack_summary,
                model_override=model_id,
                disable_model_fallback=True,
            )
            duration_ms = int((time.monotonic() - started) * 1000)
            if record_llm_run is not None:
                try:
                    record_llm_run(
                        success=bool(result and getattr(result, "success", True)),
                        model=getattr(result, "model_used", None) or model_id,
                        call_type="multi_model_consensus",
                        duration_ms=duration_ms,
                        error_type=(
                            None
                            if result and getattr(result, "success", True)
                            else "AnalysisResultError"
                        ),
                        error_message=(
                            getattr(result, "error_message", None)
                            if result and not getattr(result, "success", True)
                            else None
                        ),
                    )
                except Exception as exc:  # broad-exception: diagnostics fail-open
                    log_safe_exception(
                        logger,
                        "multi-model llm diagnostic failed",
                        exc,
                        error_code="multi_model_llm_diag_failed",
                        level=logging.DEBUG,
                    )
            return model_id, result, None, duration_ms
        except BaseException as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            if record_llm_run is not None:
                try:
                    record_llm_run(
                        success=False,
                        model=model_id,
                        call_type="multi_model_consensus",
                        duration_ms=duration_ms,
                        error_type=type(exc).__name__,
                        error_message=exc,
                    )
                except Exception as diag_exc:  # broad-exception: diagnostics fail-open
                    log_safe_exception(
                        logger,
                        "multi-model llm failure diagnostic failed",
                        diag_exc,
                        error_code="multi_model_llm_fail_diag_failed",
                        level=logging.DEBUG,
                    )
            return model_id, None, exc, duration_ms

    outcomes: List[Tuple[str, Optional[Any], Optional[BaseException], int]] = []
    if parallel and len(models) > 1:
        # Optional parallel path: serialize analyzer.analyze via a lock so a
        # shared non-thread-safe analyzer cannot corrupt internal state.
        analyze_lock = threading.Lock()
        original_run_one = _run_one

        def _run_one_locked(model_id: str) -> Tuple[str, Optional[Any], Optional[BaseException], int]:
            with analyze_lock:
                return original_run_one(model_id)

        max_workers = min(len(models), 3)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_run_one_locked, model_id): model_id for model_id in models
            }
            for future in as_completed(futures):
                try:
                    outcomes.append(future.result())
                except Exception as exc:  # broad-exception: isolate worker failure
                    model_id = futures[future]
                    log_safe_exception(
                        logger,
                        "multi-model worker failed",
                        exc,
                        error_code="multi_model_worker_failed",
                        level=logging.WARNING,
                    )
                    outcomes.append((model_id, None, exc, 0))
        # Preserve requested order for stable primary selection.
        order = {model_id: index for index, model_id in enumerate(models)}
        outcomes.sort(key=lambda item: order.get(item[0], 999))
    else:
        for model_id in models:
            outcomes.append(_run_one(model_id))

    stances: List[Dict[str, Any]] = []
    result_by_model: Dict[str, Any] = {}
    for model_id, result, error, _duration in outcomes:
        if error is not None or result is None:
            stances.append(
                {
                    "model_id": model_id,
                    "model_version": model_id,
                    "provider": _provider_from_model(model_id),
                    "status": "failed",
                    "signal": None,
                    "decision_type": None,
                    "action": None,
                    "operation_advice": None,
                    "sentiment_score": None,
                    "score_band": None,
                    "confidence_level": None,
                    "confidence": None,
                    "key_risks": [],
                    "key_catalysts": [],
                    "error_type": type(error).__name__ if error is not None else "empty_result",
                }
            )
            continue
        stance = build_model_stance(result, requested_model=model_id)
        stances.append(stance)
        if stance.get("status") == "success":
            result_by_model[model_id] = result

    comparison = build_multi_model_comparison(
        stances,
        requested_models=models,
        shared_snapshot_fingerprint=fingerprint,
        budget=budget,
    )

    primary_model = comparison.get("primary_result_model")
    primary_result = result_by_model.get(str(primary_model)) if primary_model else None
    if primary_result is None and result_by_model:
        # Fallback: first successful in requested order.
        for model_id in models:
            if model_id in result_by_model:
                primary_result = result_by_model[model_id]
                comparison["primary_result_model"] = model_id
                break

    if primary_result is not None:
        public_payload = public_multi_model_comparison_payload(comparison) or comparison
        dashboard = getattr(primary_result, "dashboard", None)
        if not isinstance(dashboard, dict):
            dashboard = {}
            primary_result.dashboard = dashboard
        else:
            dashboard = dict(dashboard)
            primary_result.dashboard = dashboard
        dashboard["multi_model_comparison"] = public_payload
        _apply_product_honesty_to_primary(primary_result, public_payload)

    return primary_result, comparison


def _apply_product_honesty_to_primary(result: Any, public_payload: Mapping[str, Any]) -> None:
    """Surface multi-model honesty on the primary product without averaging signals.

    - High disagreement: cap displayed confidence and prepend a risk note; do **not**
      rewrite ``decision_type`` / ``operation_advice`` into a synthetic blend.
    - Degradation: keep explicit annotation on the dashboard payload (already set).
    """
    handling = public_payload.get("disagreement_handling")
    if not isinstance(handling, Mapping):
        handling = {}
    dashboard = getattr(result, "dashboard", None)
    if not isinstance(dashboard, dict):
        dashboard = {}
        result.dashboard = dashboard

    if handling.get("high_disagreement"):
        dashboard["multi_model_high_disagreement"] = True
        report_language = str(getattr(result, "report_language", "zh") or "zh").lower()
        result.confidence_level = _low_confidence_label(report_language)
        note = _high_disagreement_risk_note(report_language)
        existing = str(getattr(result, "risk_warning", None) or "").strip()
        if note and note not in existing:
            result.risk_warning = f"{note} {existing}".strip() if existing else note

    degradation = public_payload.get("degradation")
    if isinstance(degradation, Mapping) and degradation.get("annotation"):
        dashboard["multi_model_degradation"] = {
            "annotation": degradation.get("annotation"),
            "reason": degradation.get("reason"),
            "failed_models": list(degradation.get("failed_models") or [])[:5],
        }


def _low_confidence_label(report_language: str) -> str:
    if report_language.startswith("zh"):
        return "低"
    if report_language.startswith("ko"):
        return "낮음"
    return "Low"


def _high_disagreement_risk_note(report_language: str) -> str:
    if report_language.startswith("zh"):
        return "【多模型高分歧】模型方向冲突已结构化记录，未做多数表决或均值抹平；置信度已下调。"
    if report_language.startswith("ko"):
        return "[다중 모델 고이견] 모델 방향 충돌이 구조화 기록되었으며 다수결/평균 없이 신뢰도가 하향 조정되었습니다."
    return (
        "[Multi-model high disagreement] Opposing model directions are recorded "
        "structurally without majority vote or averaging; confidence was reduced."
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_model_points(successful: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    if len(successful) < 2:
        return []

    points: List[Dict[str, Any]] = []
    sides = {"bullish": [], "bearish": [], "neutral": []}
    for item in successful:
        model_id = str(item.get("model_id") or "unknown")
        side = _side_for_signal(item.get("signal"))
        sides[side].append(model_id)

    if sides["bullish"] and sides["bearish"]:
        points.append(
            {
                "source": "model",
                "kind": "directional_opposition",
                "severity": "high",
                "participants": _unique([*sides["bullish"], *sides["bearish"], *sides["neutral"]]),
                "sides": {
                    "bullish": list(sides["bullish"]),
                    "bearish": list(sides["bearish"]),
                    "neutral": list(sides["neutral"]),
                },
                "summary_key": "disagreement.point.model.directional_opposition",
            }
        )
    elif (sides["bullish"] or sides["bearish"]) and sides["neutral"] and (
        len(sides["bullish"]) + len(sides["bearish"]) >= 1 and len(sides["neutral"]) >= 1
    ):
        # Soft disagreement: directional vs hold/watch only.
        points.append(
            {
                "source": "model",
                "kind": "mixed_directional_signals",
                "severity": "medium",
                "participants": _unique([*sides["bullish"], *sides["bearish"], *sides["neutral"]]),
                "sides": {
                    "bullish": list(sides["bullish"]),
                    "bearish": list(sides["bearish"]),
                    "neutral": list(sides["neutral"]),
                },
                "summary_key": "disagreement.point.model.mixed_directional_signals",
            }
        )

    bands = {str(item.get("score_band") or "") for item in successful if item.get("score_band")}
    if len(bands) >= 2:
        scores = [item.get("sentiment_score") for item in successful if isinstance(item.get("sentiment_score"), int)]
        severity = "high" if scores and (max(scores) - min(scores) >= 25) else "medium"
        points.append(
            {
                "source": "model",
                "kind": "score_band_dispersion",
                "severity": severity,
                "participants": _unique(str(item.get("model_id") or "") for item in successful),
                "sides": {},
                "summary_key": "disagreement.point.model.score_band_dispersion",
            }
        )

    confidences = [
        float(item["confidence"])
        for item in successful
        if isinstance(item.get("confidence"), (int, float)) and not isinstance(item.get("confidence"), bool)
    ]
    if len(confidences) >= 2 and (max(confidences) - min(confidences) >= 0.3):
        points.append(
            {
                "source": "model",
                "kind": "confidence_dispersion",
                "severity": "medium",
                "participants": _unique(str(item.get("model_id") or "") for item in successful),
                "sides": {},
                "summary_key": "disagreement.point.model.confidence_dispersion",
            }
        )

    return points


def _score_disagreement(
    points: Sequence[Mapping[str, Any]],
    successful: Sequence[Mapping[str, Any]],
    high_threshold: float,
) -> float:
    if len(successful) < 2:
        return 0.0
    if not points:
        return 0.0
    score = 0.0
    for point in points:
        severity = str(point.get("severity") or "medium")
        if severity == "high":
            score = max(score, 0.85)
        elif severity == "medium":
            score = max(score, 0.6)
        else:
            score = max(score, 0.35)
        if point.get("kind") == "directional_opposition":
            score = max(score, high_threshold)
    return round(min(1.0, score), 4)


def _is_high_disagreement(
    points: Sequence[Mapping[str, Any]],
    successful: Sequence[Mapping[str, Any]],
    high_threshold: float,
) -> bool:
    if any(p.get("kind") == "directional_opposition" for p in points):
        # High-confidence opposition elevates; bare opposition already high severity.
        max_bull = 0.0
        max_bear = 0.0
        for item in successful:
            conf = item.get("confidence")
            try:
                value = float(conf) if conf is not None else 0.0
            except (TypeError, ValueError):
                value = 0.0
            side = _side_for_signal(item.get("signal"))
            if side == "bullish":
                max_bull = max(max_bull, value)
            elif side == "bearish":
                max_bear = max(max_bear, value)
        if max_bull >= high_threshold and max_bear >= high_threshold:
            return True
        return True  # directional opposition is always product-visible high disagreement
    return False


def _consensus_level(
    successful: Sequence[Mapping[str, Any]],
    points: Sequence[Mapping[str, Any]],
    high_disagreement: bool,
) -> str:
    if len(successful) < 2:
        return "insufficient"
    if high_disagreement:
        return "low"
    if not points:
        return "high"
    if any(p.get("kind") == "mixed_directional_signals" for p in points):
        return "medium"
    if any(str(p.get("severity")) == "high" for p in points):
        return "low"
    return "medium"


def _consensus_score(
    successful: Sequence[Mapping[str, Any]],
    points: Sequence[Mapping[str, Any]],
) -> float:
    """Agreement degree in [0, 1]. Not a blended trading signal."""
    if len(successful) < 2:
        return 0.0
    if not points:
        return 1.0
    if any(p.get("kind") == "directional_opposition" for p in points):
        return 0.15
    if any(p.get("kind") == "mixed_directional_signals" for p in points):
        return 0.45
    return 0.6


def _primary_signal(successful: Sequence[Mapping[str, Any]]) -> Optional[str]:
    if not successful:
        return None
    signal = successful[0].get("signal")
    return str(signal) if signal else None


def _canonical_signal(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "强烈看多": "strong_buy",
        "看多": "buy",
        "买入": "buy",
        "加仓": "add",
        "持有": "hold",
        "观望": "watch",
        "减仓": "reduce",
        "卖出": "sell",
        "强烈看空": "strong_sell",
        "看空": "sell",
        "buy": "buy",
        "strong_buy": "strong_buy",
        "add": "add",
        "hold": "hold",
        "watch": "watch",
        "reduce": "reduce",
        "sell": "sell",
        "strong_sell": "strong_sell",
        "avoid": "avoid",
        "alert": "alert",
        "bullish": "buy",
        "bearish": "sell",
        "sideways": "hold",
    }
    if text in aliases:
        return aliases[text]
    # Fuzzy contains for localized free text.
    for needle, mapped in (
        ("strong buy", "strong_buy"),
        ("strong sell", "strong_sell"),
        ("buy", "buy"),
        ("sell", "sell"),
        ("add", "add"),
        ("reduce", "reduce"),
        ("hold", "hold"),
        ("watch", "watch"),
        ("买入", "buy"),
        ("卖出", "sell"),
        ("加仓", "add"),
        ("减仓", "reduce"),
        ("持有", "hold"),
        ("观望", "watch"),
    ):
        if needle in text:
            return mapped
    return "hold"


def _side_for_signal(signal: Any) -> str:
    canonical = _canonical_signal(signal)
    if canonical in _BULLISH:
        return "bullish"
    if canonical in _BEARISH:
        return "bearish"
    return "neutral"


def _score_band(score: Optional[int]) -> Optional[str]:
    if score is None:
        return None
    if score >= 70:
        return "strongly_bullish"
    if score >= 60:
        return "bullish"
    if score >= 40:
        return "range"
    if score >= 30:
        return "bearish"
    return "strongly_bearish"


def _confidence_to_unit(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number > 1.0:
            number = number / 100.0
        return round(max(0.0, min(1.0, number)), 4)
    text = str(value).strip().lower()
    mapping = {
        "高": 0.85,
        "中": 0.55,
        "低": 0.3,
        "high": 0.85,
        "medium": 0.55,
        "mid": 0.55,
        "low": 0.3,
    }
    return mapping.get(text)


def _extract_risks(result: Any) -> List[str]:
    risks: List[str] = []
    warning = str(getattr(result, "risk_warning", None) or "").strip()
    if warning:
        risks.append(warning[:200])
    dashboard = getattr(result, "dashboard", None)
    if isinstance(dashboard, Mapping):
        intel = dashboard.get("intelligence")
        if isinstance(intel, Mapping):
            alerts = intel.get("risk_alerts")
            if isinstance(alerts, list):
                for item in alerts[:5]:
                    if isinstance(item, str) and item.strip():
                        risks.append(item.strip()[:200])
                    elif isinstance(item, Mapping):
                        text = str(item.get("text") or item.get("title") or item.get("summary") or "").strip()
                        if text:
                            risks.append(text[:200])
    return _unique(risks)[:5]


def _extract_catalysts(result: Any) -> List[str]:
    catalysts: List[str] = []
    key_points = str(getattr(result, "key_points", None) or "").strip()
    if key_points:
        for part in key_points.replace("\n", ";").split(";"):
            cleaned = part.strip(" -•\t")
            if cleaned:
                catalysts.append(cleaned[:200])
    buy_reason = str(getattr(result, "buy_reason", None) or "").strip()
    if buy_reason:
        catalysts.append(buy_reason[:200])
    return _unique(catalysts)[:5]


def _provider_from_model(model: str) -> str:
    text = str(model or "").strip()
    if "/" in text:
        return text.split("/", 1)[0]
    return ""


def _normalize_model_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return [part for part in parts if part]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        out: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in out:
                out.append(text)
        return out
    return []


def _select_keys(value: Any, keys: Sequence[str]) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {key: value.get(key) for key in keys if key in value}


def _unique(values: Any) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _clamp_unit(value: Any, default: float) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _clamp_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        if value is None or isinstance(value, bool):
            return default
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return round(max(0.0, min(1.0, float(value))), 4)
    except (TypeError, ValueError):
        return default


__all__ = [
    "SCHEMA_VERSION",
    "build_model_stance",
    "build_multi_model_comparison",
    "fingerprint_shared_snapshot",
    "is_multi_model_consensus_enabled",
    "public_multi_model_comparison_payload",
    "resolve_consensus_models",
    "resolve_consensus_models_for_run",
    "run_multi_model_consensus_analysis",
]
