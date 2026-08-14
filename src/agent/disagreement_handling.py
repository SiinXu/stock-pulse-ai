# -*- coding: utf-8 -*-
"""
Structured disagreement detection, cross-validation, and escalation.

Product honesty rules:
- Unresolved disagreement is a legitimate reported outcome.
- Escalation must not invent artificial consensus via majority vote.
- High disagreement must be visible on the final product (not silently smoothed).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Optional

from src.agent.protocols import strategy_signal_score

DISAGREEMENT_HANDLING_SCHEMA_VERSION = "disagreement-handling-v1"

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

_DEFAULT_HIGH_CONFIDENCE = 0.7
_DEFAULT_MEDIUM_CONFIDENCE = 0.55
_SPLIT_CONFIDENCE_CAP = 0.35
_SPLIT_CONFIDENCE_FACTOR = 0.5
_CROSS_VALIDATE_CONFIDENCE_FACTOR = 0.9

_ROLE_MIXED_TYPES = frozenset({"mixed_directional_signals"})
_STRATEGY_HIGH_TYPES = frozenset(
    {
        "directional_opposition",
        "wide_score_dispersion",
        "high_confidence_dissent",
        "adjustment_contradiction",
    }
)


def build_disagreement_handling_record(
    *,
    role_summary: Optional[Mapping[str, Any]] = None,
    strategy_synthesis: Optional[Mapping[str, Any]] = None,
    strategy_conflicts: Optional[Sequence[Any]] = None,
    high_confidence_threshold: float = _DEFAULT_HIGH_CONFIDENCE,
    medium_confidence_threshold: float = _DEFAULT_MEDIUM_CONFIDENCE,
) -> Dict[str, Any]:
    """Build a low-sensitivity structured disagreement handling record."""
    high_threshold = _clamp_unit(high_confidence_threshold, _DEFAULT_HIGH_CONFIDENCE)
    medium_threshold = _clamp_unit(medium_confidence_threshold, _DEFAULT_MEDIUM_CONFIDENCE)
    if medium_threshold > high_threshold:
        medium_threshold = high_threshold

    points = _collect_points(
        role_summary=role_summary,
        strategy_synthesis=strategy_synthesis,
        strategy_conflicts=strategy_conflicts,
        high_threshold=high_threshold,
    )
    role_conflict = _role_layer_conflict(role_summary)
    strategy_conflict = _strategy_layer_conflict(
        strategy_synthesis=strategy_synthesis,
        strategy_conflicts=strategy_conflicts,
        points=points,
    )
    disagreement_score = _score_disagreement(
        points=points,
        role_conflict=role_conflict,
        strategy_conflict=strategy_conflict,
        high_threshold=high_threshold,
    )
    initial_escalation = _initial_escalation(
        points=points,
        role_summary=role_summary,
        strategy_synthesis=strategy_synthesis,
        high_threshold=high_threshold,
        medium_threshold=medium_threshold,
        disagreement_score=disagreement_score,
        role_conflict=role_conflict,
        strategy_conflict=strategy_conflict,
    )
    cross_validation = _run_cross_validation(
        requested=initial_escalation in {ESCALATION_CROSS_VALIDATE, ESCALATION_SPLIT},
        role_conflict=role_conflict,
        strategy_conflict=strategy_conflict,
        points=points,
        high_threshold=high_threshold,
        disagreement_score=disagreement_score,
    )
    escalation = _finalize_escalation(initial_escalation, cross_validation)
    high_disagreement = escalation == ESCALATION_SPLIT or (
        disagreement_score >= high_threshold and _has_opposing_sides(points)
    )
    if high_disagreement:
        escalation = ESCALATION_SPLIT

    pre_signal = _pre_escalation_signal(strategy_synthesis)
    if escalation == ESCALATION_SPLIT:
        verdict_mode = VERDICT_SPLIT
        resolution_status = RESOLUTION_UNRESOLVED
        final_signal = "hold"
        explanation_key = "disagreement.high_split_verdict"
    elif _is_insufficient(role_summary, strategy_synthesis, points):
        verdict_mode = VERDICT_INSUFFICIENT
        resolution_status = RESOLUTION_UNRESOLVED
        final_signal = pre_signal or "hold"
        explanation_key = "disagreement.insufficient_evidence"
    elif escalation in {ESCALATION_NONE, ESCALATION_RECORD} and not points:
        verdict_mode = VERDICT_CONSENSUS
        resolution_status = RESOLUTION_RESOLVED
        final_signal = pre_signal or "hold"
        explanation_key = "disagreement.aligned"
    else:
        verdict_mode = VERDICT_CONSENSUS
        resolution_status = RESOLUTION_PARTIAL if points else RESOLUTION_RESOLVED
        final_signal = pre_signal or "hold"
        explanation_key = (
            "disagreement.recorded_with_cross_validation"
            if escalation == ESCALATION_CROSS_VALIDATE
            else "disagreement.recorded"
        )

    confidence_cap = _SPLIT_CONFIDENCE_CAP if escalation == ESCALATION_SPLIT else None
    return {
        "schema_version": DISAGREEMENT_HANDLING_SCHEMA_VERSION,
        "enabled": True,
        "high_disagreement": bool(high_disagreement),
        "verdict_mode": verdict_mode,
        "escalation": escalation,
        "resolution_status": resolution_status,
        "disagreement_score": round(disagreement_score, 4),
        "points": points,
        "cross_validation": cross_validation,
        "policy": {
            "method": "threshold_escalation",
            "majority_vote_used": False,
            "high_confidence_threshold": high_threshold,
            "medium_confidence_threshold": medium_threshold,
            "conservative_final_signal": "hold" if escalation == ESCALATION_SPLIT else None,
            "pre_escalation_final_signal": pre_signal,
            "applied_final_signal": final_signal,
            "confidence_cap": confidence_cap,
        },
        "explanation_key": explanation_key,
    }


def apply_disagreement_handling_to_synthesis(
    synthesis: Mapping[str, Any],
    *,
    role_summary: Optional[Mapping[str, Any]] = None,
    high_confidence_threshold: float = _DEFAULT_HIGH_CONFIDENCE,
    medium_confidence_threshold: float = _DEFAULT_MEDIUM_CONFIDENCE,
) -> Dict[str, Any]:
    """Return a synthesis copy with structured disagreement handling applied."""
    if not isinstance(synthesis, Mapping) or not synthesis:
        return {}

    payload = dict(synthesis)
    conflicts = payload.get("conflicts")
    record = build_disagreement_handling_record(
        role_summary=role_summary,
        strategy_synthesis=payload,
        strategy_conflicts=conflicts if isinstance(conflicts, list) else [],
        high_confidence_threshold=high_confidence_threshold,
        medium_confidence_threshold=medium_confidence_threshold,
    )
    payload["disagreement_handling"] = record
    escalation = record.get("escalation")

    if escalation == ESCALATION_SPLIT:
        pre_signal = str(payload.get("final_signal") or "hold")
        payload["final_signal"] = "hold"
        payload["consensus_level"] = "low"
        original = payload.get("original_confidence")
        if not isinstance(original, (int, float)) or isinstance(original, bool):
            original = payload.get("confidence")
        try:
            base_confidence = float(original if original is not None else 0.0)
        except (TypeError, ValueError):
            base_confidence = 0.0
        base_confidence = max(0.0, min(1.0, base_confidence))
        capped = min(base_confidence * _SPLIT_CONFIDENCE_FACTOR, _SPLIT_CONFIDENCE_CAP)
        payload["confidence"] = round(max(0.0, capped), 4)
        if "original_confidence" not in payload:
            payload["original_confidence"] = round(base_confidence, 4)
        summary_params = payload.get("summary_params")
        if isinstance(summary_params, dict):
            summary_params = dict(summary_params)
            summary_params["final_signal"] = "hold"
            summary_params["consensus_level"] = "low"
            summary_params["high_disagreement"] = True
            summary_params["verdict_mode"] = VERDICT_SPLIT
            payload["summary_params"] = summary_params
        policy = dict(record.get("policy") or {})
        policy["pre_escalation_final_signal"] = pre_signal
        policy["applied_final_signal"] = "hold"
        record = dict(record)
        record["policy"] = policy
        payload["disagreement_handling"] = record
        payload = _regroup_for_hold(payload)
    elif escalation == ESCALATION_CROSS_VALIDATE:
        original = payload.get("original_confidence")
        if not isinstance(original, (int, float)) or isinstance(original, bool):
            original = payload.get("confidence")
        try:
            confidence = float(original if original is not None else 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if not math.isfinite(confidence):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        if "original_confidence" not in payload:
            payload["original_confidence"] = round(confidence, 4)
        payload["confidence"] = round(
            max(0.0, min(1.0, confidence * _CROSS_VALIDATE_CONFIDENCE_FACTOR)),
            4,
        )
        summary_params = payload.get("summary_params")
        if isinstance(summary_params, dict):
            summary_params = dict(summary_params)
            summary_params["cross_validation_requested"] = True
            payload["summary_params"] = summary_params
    return payload


def merge_role_disagreement_into_handling(
    existing: Optional[Mapping[str, Any]],
    role_summary: Optional[Mapping[str, Any]],
    *,
    high_confidence_threshold: float = _DEFAULT_HIGH_CONFIDENCE,
    medium_confidence_threshold: float = _DEFAULT_MEDIUM_CONFIDENCE,
) -> Dict[str, Any]:
    """Merge or build a handling record from a role-layer disagreement summary."""
    if isinstance(existing, Mapping) and existing.get("enabled"):
        synthesis_stub = {
            "final_signal": (existing.get("policy") or {}).get("pre_escalation_final_signal")
            or (existing.get("policy") or {}).get("applied_final_signal")
            or "hold",
            "conflict_severity": _severity_from_points(existing.get("points") or []),
            "conflicts": [
                {
                    "conflict_type": point.get("kind"),
                    "severity": point.get("severity"),
                    "participants": point.get("participants") or [],
                    "metadata": {
                        "bullish": (point.get("sides") or {}).get("bullish") or [],
                        "bearish": (point.get("sides") or {}).get("bearish") or [],
                    },
                }
                for point in (existing.get("points") or [])
                if isinstance(point, dict) and point.get("source") == "strategy"
            ],
            "consensus_level": "low" if existing.get("high_disagreement") else "medium",
            "confidence": 0.0,
        }
        return build_disagreement_handling_record(
            role_summary=role_summary,
            strategy_synthesis=synthesis_stub,
            strategy_conflicts=synthesis_stub["conflicts"],
            high_confidence_threshold=high_confidence_threshold,
            medium_confidence_threshold=medium_confidence_threshold,
        )
    return build_disagreement_handling_record(
        role_summary=role_summary,
        high_confidence_threshold=high_confidence_threshold,
        medium_confidence_threshold=medium_confidence_threshold,
    )


def is_disagreement_handling_enabled(config: Any) -> bool:
    return bool(getattr(config, "agent_disagreement_handling", False))


def disagreement_handling_thresholds(config: Any) -> tuple[float, float]:
    high = getattr(config, "agent_disagreement_high_confidence_threshold", None)
    medium = getattr(config, "agent_disagreement_medium_confidence_threshold", None)
    high_value = _clamp_unit(high, _DEFAULT_HIGH_CONFIDENCE)
    medium_value = _clamp_unit(medium, _DEFAULT_MEDIUM_CONFIDENCE)
    if medium_value > high_value:
        medium_value = high_value
    return high_value, medium_value


def public_disagreement_handling_payload(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping) or not value:
        return None
    if value.get("schema_version") != DISAGREEMENT_HANDLING_SCHEMA_VERSION:
        return None
    if value.get("enabled") is not True:
        return None
    points: List[Dict[str, Any]] = []
    raw_points = value.get("points")
    if isinstance(raw_points, list):
        for item in raw_points[:12]:
            if not isinstance(item, Mapping):
                continue
            participants = item.get("participants")
            points.append(
                {
                    "source": str(item.get("source") or "unknown"),
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
    cross = value.get("cross_validation")
    cross_payload: Dict[str, Any] = {}
    if isinstance(cross, Mapping):
        cross_payload = {
            "requested": bool(cross.get("requested")),
            "status": str(cross.get("status") or "not_applicable"),
            "role_layer_conflict": bool(cross.get("role_layer_conflict")),
            "strategy_layer_conflict": bool(cross.get("strategy_layer_conflict")),
            "dual_layer_confirmed": bool(cross.get("dual_layer_confirmed")),
            "outcome": str(cross.get("outcome") or ESCALATION_NONE),
        }
    policy = value.get("policy") if isinstance(value.get("policy"), Mapping) else {}
    return {
        "schema_version": DISAGREEMENT_HANDLING_SCHEMA_VERSION,
        "enabled": True,
        "high_disagreement": bool(value.get("high_disagreement")),
        "verdict_mode": str(value.get("verdict_mode") or VERDICT_CONSENSUS),
        "escalation": str(value.get("escalation") or ESCALATION_NONE),
        "resolution_status": str(value.get("resolution_status") or RESOLUTION_UNRESOLVED),
        "disagreement_score": _safe_float(value.get("disagreement_score"), 0.0),
        "points": points,
        "cross_validation": cross_payload,
        "policy": {
            "method": str(policy.get("method") or "threshold_escalation"),
            "majority_vote_used": False,
            "pre_escalation_final_signal": policy.get("pre_escalation_final_signal"),
            "applied_final_signal": policy.get("applied_final_signal"),
            "confidence_cap": _optional_unit_float(policy.get("confidence_cap")),
        },
        "explanation_key": str(value.get("explanation_key") or ""),
    }


def _collect_points(
    *, role_summary, strategy_synthesis, strategy_conflicts, high_threshold
):
    points: List[Dict[str, Any]] = []
    if isinstance(role_summary, Mapping):
        conflict_type = str(role_summary.get("conflict_type") or "").strip()
        if conflict_type and conflict_type not in {
            "aligned_bullish", "aligned_bearish", "aligned_neutral",
            "bullish_with_neutral", "bearish_with_neutral", "insufficient_opinions",
        }:
            bullish = _agent_names(role_summary.get("bullish_agents"))
            bearish = _agent_names(role_summary.get("bearish_agents"))
            neutral = _agent_names(role_summary.get("neutral_agents"))
            severity = "medium"
            if conflict_type in _ROLE_MIXED_TYPES:
                max_bull = _max_confidence(role_summary.get("bullish_agents"))
                max_bear = _max_confidence(role_summary.get("bearish_agents"))
                if max_bull >= high_threshold and max_bear >= high_threshold:
                    severity = "high"
            points.append({
                "source": "role",
                "kind": conflict_type,
                "severity": severity,
                "participants": _unique([*bullish, *bearish, *neutral]),
                "sides": {"bullish": bullish, "bearish": bearish, "neutral": neutral},
                "summary_key": f"disagreement.point.role.{conflict_type}",
            })
    raw_conflicts: List[Any] = []
    if isinstance(strategy_conflicts, Sequence) and not isinstance(strategy_conflicts, (str, bytes)):
        raw_conflicts.extend(list(strategy_conflicts))
    if isinstance(strategy_synthesis, Mapping):
        nested = strategy_synthesis.get("conflicts")
        if isinstance(nested, list):
            raw_conflicts.extend(nested)
    seen = set()
    for conflict in raw_conflicts:
        parsed = _conflict_to_point(conflict)
        if parsed is None:
            continue
        key = (parsed["kind"], tuple(parsed["participants"]), parsed["severity"])
        if key in seen:
            continue
        seen.add(key)
        points.append(parsed)
    return points


def _conflict_to_point(conflict):
    if hasattr(conflict, "conflict_type"):
        kind = str(getattr(conflict, "conflict_type", "") or "").strip()
        severity = str(getattr(conflict, "severity", "medium") or "medium").strip()
        participants = list(getattr(conflict, "participants", None) or [])
        metadata = getattr(conflict, "metadata", None) or {}
    elif isinstance(conflict, Mapping):
        kind = str(conflict.get("conflict_type") or "").strip()
        severity = str(conflict.get("severity") or "medium").strip()
        participants = list(conflict.get("participants") or [])
        metadata = conflict.get("metadata") if isinstance(conflict.get("metadata"), Mapping) else {}
    else:
        return None
    if not kind:
        return None
    if severity not in {"low", "medium", "high"}:
        severity = "medium"
    clean_participants = _unique(str(p).strip() for p in participants if str(p).strip())
    sides: Dict[str, Any] = {}
    if isinstance(metadata, Mapping):
        for side_key in ("bullish", "bearish"):
            side = metadata.get(side_key)
            if isinstance(side, list):
                sides[side_key] = _unique(str(x).strip() for x in side if str(x).strip())
    return {
        "source": "strategy",
        "kind": kind,
        "severity": severity,
        "participants": clean_participants,
        "sides": sides,
        "summary_key": f"disagreement.point.strategy.{kind}",
    }


def _role_layer_conflict(role_summary):
    if not isinstance(role_summary, Mapping):
        return False
    conflict_type = str(role_summary.get("conflict_type") or "")
    if conflict_type in _ROLE_MIXED_TYPES:
        return True
    return bool(role_summary.get("bullish_agents")) and bool(role_summary.get("bearish_agents"))


def _strategy_layer_conflict(*, strategy_synthesis, strategy_conflicts, points):
    if any(p.get("source") == "strategy" for p in points):
        return True
    if isinstance(strategy_synthesis, Mapping):
        severity = str(strategy_synthesis.get("conflict_severity") or "none")
        if severity in {"medium", "high"}:
            return True
        count = strategy_synthesis.get("conflict_count")
        if isinstance(count, int) and count > 0:
            return True
    if strategy_conflicts:
        return len(list(strategy_conflicts)) > 0
    return False


def _score_disagreement(*, points, role_conflict, strategy_conflict, high_threshold):
    if not points and not role_conflict and not strategy_conflict:
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
        if point.get("kind") in _ROLE_MIXED_TYPES or point.get("kind") == "directional_opposition":
            score = max(score, 0.8)
    if role_conflict and strategy_conflict:
        score = max(score, high_threshold)
        score = min(1.0, score + 0.1)
    elif role_conflict or strategy_conflict:
        score = max(score, 0.55)
    return round(min(1.0, score), 4)


def _initial_escalation(*, points, role_summary, strategy_synthesis, high_threshold,
                        medium_threshold, disagreement_score, role_conflict, strategy_conflict):
    if not points and not role_conflict and not strategy_conflict:
        return ESCALATION_NONE
    high_points = [p for p in points if str(p.get("severity") or "") == "high"]
    if high_points and _has_opposing_sides(points):
        return ESCALATION_SPLIT
    if role_conflict:
        max_bull = _max_confidence(role_summary.get("bullish_agents") if isinstance(role_summary, Mapping) else None)
        max_bear = _max_confidence(role_summary.get("bearish_agents") if isinstance(role_summary, Mapping) else None)
        if max_bull >= high_threshold and max_bear >= high_threshold:
            return ESCALATION_SPLIT
    strategy_severity = "none"
    if isinstance(strategy_synthesis, Mapping):
        strategy_severity = str(strategy_synthesis.get("conflict_severity") or "none")
    if strategy_severity == "high":
        return ESCALATION_SPLIT
    if disagreement_score >= high_threshold and (role_conflict or strategy_conflict):
        return ESCALATION_CROSS_VALIDATE
    if disagreement_score >= medium_threshold or points:
        return ESCALATION_CROSS_VALIDATE if (role_conflict or strategy_conflict) else ESCALATION_RECORD
    return ESCALATION_RECORD


def _run_cross_validation(*, requested, role_conflict, strategy_conflict, points,
                          high_threshold, disagreement_score):
    if not requested:
        return {
            "requested": False, "status": "not_applicable",
            "role_layer_conflict": role_conflict, "strategy_layer_conflict": strategy_conflict,
            "dual_layer_confirmed": False, "outcome": ESCALATION_NONE,
        }
    dual = role_conflict and strategy_conflict
    opposing = _has_opposing_sides(points)
    if dual and opposing:
        outcome = ESCALATION_SPLIT
    elif dual or (disagreement_score >= high_threshold and opposing):
        outcome = ESCALATION_SPLIT
    elif role_conflict or strategy_conflict:
        outcome = ESCALATION_RECORD
    else:
        outcome = ESCALATION_NONE
    return {
        "requested": True, "status": "completed",
        "role_layer_conflict": role_conflict, "strategy_layer_conflict": strategy_conflict,
        "dual_layer_confirmed": dual, "outcome": outcome,
    }


def _finalize_escalation(initial, cross_validation):
    if not cross_validation.get("requested"):
        return initial
    outcome = str(cross_validation.get("outcome") or ESCALATION_NONE)
    rank = {ESCALATION_NONE: 0, ESCALATION_RECORD: 1, ESCALATION_CROSS_VALIDATE: 2, ESCALATION_SPLIT: 3}
    if rank.get(outcome, 0) >= rank.get(initial, 0):
        return outcome if outcome != ESCALATION_NONE else initial
    return initial


def _has_opposing_sides(points):
    bullish, bearish = [], []
    for point in points:
        sides = point.get("sides") if isinstance(point.get("sides"), Mapping) else {}
        bullish.extend(sides.get("bullish") or [])
        bearish.extend(sides.get("bearish") or [])
        kind = str(point.get("kind") or "")
        if kind in {"directional_opposition", "mixed_directional_signals"}:
            return True
        if kind in _STRATEGY_HIGH_TYPES and str(point.get("severity")) == "high":
            return True
    return bool(bullish) and bool(bearish)


def _is_insufficient(role_summary, strategy_synthesis, points):
    if isinstance(strategy_synthesis, Mapping):
        if str(strategy_synthesis.get("consensus_level") or "") == "insufficient":
            return True
    if isinstance(role_summary, Mapping):
        if str(role_summary.get("conflict_type") or "") == "insufficient_opinions":
            return not points
    return False


def _pre_escalation_signal(strategy_synthesis):
    if isinstance(strategy_synthesis, Mapping):
        signal = strategy_synthesis.get("final_signal")
        if signal:
            return str(signal)
    return None


def _regroup_for_hold(payload):
    supporting = payload.get("supporting_skills")
    opposing = payload.get("opposing_skills")
    if not isinstance(supporting, list) or not isinstance(opposing, list):
        return payload
    new_supporting, new_opposing = [], list(opposing)
    for item in supporting:
        if not isinstance(item, dict):
            new_opposing.append(item)
            continue
        signal = str(item.get("signal") or "").strip().lower()
        score = strategy_signal_score(signal) if signal else 3.0
        if score == 3.0:
            new_supporting.append(item)
        else:
            new_opposing.append(item)
    payload["supporting_skills"] = new_supporting
    payload["opposing_skills"] = new_opposing
    return payload


def _agent_names(items):
    if not isinstance(items, list):
        return []
    names = []
    for item in items:
        if isinstance(item, Mapping):
            name = str(item.get("agent_name") or item.get("agent") or "").strip()
            if name:
                names.append(name)
        elif isinstance(item, str) and item.strip():
            names.append(item.strip())
    return _unique(names)


def _max_confidence(items):
    if not isinstance(items, list):
        return 0.0
    best = 0.0
    for item in items:
        if not isinstance(item, Mapping):
            continue
        try:
            value = float(item.get("confidence") or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        best = max(best, max(0.0, min(1.0, value)))
    return best


def _severity_from_points(points):
    order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    best = "none"
    for point in points:
        if not isinstance(point, Mapping):
            continue
        severity = str(point.get("severity") or "none")
        if order.get(severity, 0) > order.get(best, 0):
            best = severity
    return best


def _unique(values):
    seen, result = set(), []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _clamp_unit(value, default):
    try:
        if value is None or isinstance(value, bool):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return max(0.0, min(1.0, number))


def _safe_float(value, default=0.0):
    try:
        if value is None or isinstance(value, bool):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return round(max(0.0, min(1.0, number)), 4)


def _optional_unit_float(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(max(0.0, min(1.0, number)), 4)


__all__ = [
    "DISAGREEMENT_HANDLING_SCHEMA_VERSION",
    "ESCALATION_NONE", "ESCALATION_RECORD", "ESCALATION_CROSS_VALIDATE", "ESCALATION_SPLIT",
    "VERDICT_CONSENSUS", "VERDICT_SPLIT", "VERDICT_INSUFFICIENT",
    "apply_disagreement_handling_to_synthesis", "build_disagreement_handling_record",
    "disagreement_handling_thresholds", "is_disagreement_handling_enabled",
    "merge_role_disagreement_into_handling", "public_disagreement_handling_payload",
]
