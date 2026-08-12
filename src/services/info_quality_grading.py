# -*- coding: utf-8 -*-
"""Information quality grading and forced-conclusion constraints (Issue #123).

Grades consume existing AnalysisContextPack ``data_quality`` output and
``data_quality_evidence.v1`` validation findings. They do not re-run provider
validators or invent a parallel quality score.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from inspect import getattr_static
from math import isfinite
from typing import Any, Dict, List, Literal, Optional, TYPE_CHECKING

from src.report_language import localize_confidence_level, normalize_report_language
from src.schemas.decision_action import (
    DecisionAction,
    localize_action_label,
    normalize_decision_action,
)

if TYPE_CHECKING:
    from src.analyzer import AnalysisResult


INFO_QUALITY_SCHEMA_VERSION: Literal["info-quality-v1"] = "info-quality-v1"
FORCED_CONCLUSION_SCHEMA_VERSION: Literal["forced-conclusion-v1"] = "forced-conclusion-v1"

InfoQualityGrade = Literal["A", "B", "C"]
ForcedStance = Literal["Pass", "Fail", "Watch"]
DimensionGrade = Literal["A", "B", "C"]

_GRADE_RANK: Dict[str, int] = {"A": 0, "B": 1, "C": 2}
_LEVEL_TO_GRADE: Dict[str, InfoQualityGrade] = {
    "good": "A",
    "high": "A",
    "usable": "B",
    "medium": "B",
    "limited": "C",
    "low": "C",
    "poor": "C",
    "unknown": "C",
}
_PASS_ACTIONS = frozenset({"buy", "add"})
_FAIL_ACTIONS = frozenset({"sell", "reduce", "avoid"})
_WATCH_ACTIONS = frozenset({"hold", "watch", "alert"})
_CORE_BLOCKS = ("quote", "daily_bars", "technical")
_KNOWN_BLOCK_STATUSES = frozenset(
    {
        "available",
        "missing",
        "not_supported",
        "fallback",
        "stale",
        "estimated",
        "partial",
        "fetch_failed",
    }
)
_VALIDATION_SEVERITIES = frozenset({"pass", "warn", "reject"})
_VALIDATION_SEVERITY_RANK = {"pass": 0, "warn": 1, "reject": 2}
_MAX_EVIDENCE_RECORDS = 24
_MAX_EVIDENCE_ISSUES = 24
_MAX_TEXT = 320
_TIMELINESS_WEAK = frozenset({"stale", "partial"})
_CONSISTENCY_CODES = frozenset(
    {
        "dv_cross_source_divergence",
        "dv_daily_date_out_of_order",
        "dv_daily_date_duplicate",
    }
)


def read_info_quality_feature_flag(
    config: Any,
    name: Literal["info_quality_grading_enabled", "forced_conclusion_enabled"],
) -> bool:
    """Read a config flag without treating dynamic mock attributes as configured.

    Older/custom config objects that genuinely omit a new flag retain the public
    default of enabled. An explicitly provided value must still be an exact bool.
    """

    if config is None:
        return True
    try:
        getattr_static(config, name)
    except AttributeError:
        return True
    value = getattr(config, name)
    if type(value) is not bool:
        raise TypeError(f"{name} must be bool")
    return value


def grade_info_quality(
    data_quality: Optional[Mapping[str, Any]],
    *,
    blocks: Any = None,
) -> Dict[str, Any]:
    """Build an A/B/C grade from validation-backed data_quality artifacts.

    ``blocks`` accepts either the pack-shaped mapping ``{key: {status: ...}}``
    or the public overview list ``[{key, status}, ...]``.
    """

    quality = dict(data_quality) if isinstance(data_quality, Mapping) else {}
    metadata = quality.get("metadata") if isinstance(quality.get("metadata"), Mapping) else {}
    evidence, invalid_evidence_count = _validation_evidence(quality, metadata)
    limitations = _list_strings(quality.get("limitations"))
    block_statuses = _block_statuses(blocks, limitations)

    source_reliability = _grade_source_reliability(
        quality=quality,
        evidence=evidence,
        block_statuses=block_statuses,
        invalid_evidence_count=invalid_evidence_count,
    )
    timeliness = _grade_timeliness(evidence=evidence, block_statuses=block_statuses)
    consistency = _grade_consistency(evidence=evidence)

    raw_level = quality.get("level")
    level = raw_level.strip().lower() if isinstance(raw_level, str) else ""
    level_grade = _LEVEL_TO_GRADE.get(level)
    if level_grade is None:
        score = quality.get("overall_score")
        if (
            isinstance(score, int)
            and not isinstance(score, bool)
            and 0 <= score <= 100
        ):
            if score >= 85:
                level_grade = "A"
            elif score >= 70:
                level_grade = "B"
            else:
                level_grade = "C"
        else:
            level_grade = "C"

    grade = _worst_grade(level_grade, source_reliability, timeliness, consistency)
    reasons = _grade_reasons(
        grade=grade,
        level=level or None,
        source_reliability=source_reliability,
        timeliness=timeliness,
        consistency=consistency,
        evidence=evidence,
        block_statuses=block_statuses,
        invalid_evidence_count=invalid_evidence_count,
    )
    evidence_backed = _is_evidence_backed(
        block_statuses,
        invalid_evidence_count=invalid_evidence_count,
    )
    overall_score = quality.get("overall_score")
    if not (
        isinstance(overall_score, int)
        and not isinstance(overall_score, bool)
        and 0 <= overall_score <= 100
    ):
        overall_score = None
    return {
        "schema_version": INFO_QUALITY_SCHEMA_VERSION,
        "grade": grade,
        "dimensions": {
            "source_reliability": source_reliability,
            "timeliness": timeliness,
            "consistency": consistency,
        },
        "level": level or None,
        "overall_score": overall_score,
        "evidence_backed": evidence_backed,
        "reasons": reasons,
        "source": "data_quality_evidence.v1+analysis_context_pack",
        "validation_issue_count": min(
            _validation_issue_count(evidence) + invalid_evidence_count,
            _MAX_EVIDENCE_RECORDS * _MAX_EVIDENCE_ISSUES,
        ),
    }


def map_action_to_forced_stance(action: Any) -> ForcedStance:
    """Map eight-state DecisionAction onto Pass / Fail / Watch."""

    normalized = normalize_decision_action(action)
    if normalized in _PASS_ACTIONS:
        return "Pass"
    if normalized in _FAIL_ACTIONS:
        return "Fail"
    return "Watch"


def build_forced_conclusion(
    *,
    action: Any,
    info_quality: Mapping[str, Any],
    language: str = "zh",
    risk_summary: Any = None,
    watch_conditions: Any = None,
    confidence_level: Any = None,
    reason: Optional[str] = None,
    quality_constraints_enabled: bool = True,
) -> Dict[str, Any]:
    """Build a forced conclusion payload constrained by information quality."""

    lang = normalize_report_language(language)
    if type(quality_constraints_enabled) is not bool:
        raise TypeError("quality_constraints_enabled must be bool")
    quality = info_quality if isinstance(info_quality, Mapping) else {}
    grade = _safe_grade(quality.get("grade"))
    if quality_constraints_enabled and grade is None:
        grade = "C"
    evidence_backed = quality.get("evidence_backed") is True
    raw_action = normalize_decision_action(action)
    raw_stance = map_action_to_forced_stance(raw_action)
    final_stance = raw_stance
    uncertainty = False
    constraint_reasons: List[str] = []

    if raw_action is None:
        uncertainty = True
        constraint_reasons.append("missing_action_defaulted_to_watch")
    if quality_constraints_enabled and not evidence_backed and raw_stance == "Pass":
        final_stance = "Watch"
        uncertainty = True
        constraint_reasons.append("no_evidence_pass_blocked")
    if quality_constraints_enabled and grade == "C" and raw_stance == "Pass":
        final_stance = "Watch"
        uncertainty = True
        constraint_reasons.append("grade_c_pass_downgraded")
    if quality_constraints_enabled and grade == "C" and raw_stance != "Pass":
        uncertainty = True
        if "grade_c_uncertainty" not in constraint_reasons:
            constraint_reasons.append("grade_c_uncertainty")
    if quality_constraints_enabled and grade == "B" and raw_stance == "Pass":
        uncertainty = True
        constraint_reasons.append("grade_b_pass_uncertain")

    action_for_stance = _stance_to_action(final_stance, raw_action)
    upgrade, downgrade = _default_conditions(
        lang=lang,
        grade=grade or "unknown",
        stance=final_stance,
    )
    risks = _list_strings(risk_summary, limit=3)
    watches = _list_strings(watch_conditions, limit=3)
    if not risks and quality_constraints_enabled and grade == "C":
        risks = [
            _text(
                lang,
                en="Low information quality; treat directional claims as provisional.",
                zh="信息质量偏低，方向性结论仅供观察，不可当作已证实事实。",
                ko="정보 품질이 낮아 방향성 결론은 잠정적으로만 취급하세요.",
            )
        ]

    return {
        "schema_version": FORCED_CONCLUSION_SCHEMA_VERSION,
        "stance": final_stance,
        "raw_stance": raw_stance,
        "action": action_for_stance,
        "action_label": localize_action_label(action_for_stance, lang),
        "confidence_level": _bounded_text(confidence_level) or None,
        "uncertainty": uncertainty,
        "evidence_backed": evidence_backed if quality_constraints_enabled else None,
        "info_quality_grade": grade,
        "constraint_reasons": constraint_reasons,
        "upgrade_conditions": upgrade,
        "downgrade_conditions": downgrade,
        "main_risks": risks,
        "watch_conditions": watches,
        "summary": _bounded_text(reason)
        or _stance_summary(lang=lang, stance=final_stance, grade=grade, uncertainty=uncertainty),
    }


def apply_info_quality_constraints(
    result: "AnalysisResult",
    *,
    analysis_context_pack_overview: Optional[Mapping[str, Any]] = None,
    grading_enabled: bool = True,
    forced_conclusion_enabled: bool = True,
    enforce_action_downgrade: bool = True,
    report_language: Optional[str] = None,
) -> List[str]:
    """Attach grade/conclusion to the result and optionally force Watch on weak Pass."""

    if result is None or getattr(result, "success", True) is not True:
        return []
    if type(grading_enabled) is not bool or type(forced_conclusion_enabled) is not bool:
        raise TypeError("information-quality feature flags must be bool")
    if type(enforce_action_downgrade) is not bool:
        raise TypeError("enforce_action_downgrade must be bool")
    if not grading_enabled and not forced_conclusion_enabled:
        existing_dashboard = getattr(result, "dashboard", None)
        if isinstance(existing_dashboard, dict):
            existing_dashboard.pop("info_quality", None)
            existing_dashboard.pop("forced_conclusion", None)
        return []

    language = normalize_report_language(
        report_language or getattr(result, "report_language", "zh")
    )
    overview = (
        analysis_context_pack_overview
        if isinstance(analysis_context_pack_overview, Mapping)
        else getattr(result, "analysis_context_pack_overview", None)
    )
    if not isinstance(overview, Mapping):
        overview = {}

    data_quality = overview.get("data_quality")
    if not isinstance(data_quality, Mapping):
        data_quality = {}
    # Overview emits list-shaped blocks; pack emit mapping-shaped blocks.
    blocks = overview.get("blocks")

    dashboard = getattr(result, "dashboard", None)
    if not isinstance(dashboard, dict):
        dashboard = {}
        result.dashboard = dashboard

    adjustments: List[str] = []
    if grading_enabled:
        info_quality = resolve_info_quality(data_quality, blocks=blocks)
        dashboard["info_quality"] = info_quality
        adjustments.append(f"info_quality_grade_{info_quality['grade'].lower()}")
    else:
        dashboard.pop("info_quality", None)
        info_quality = {}

    if not forced_conclusion_enabled:
        dashboard.pop("forced_conclusion", None)
        return adjustments

    action = normalize_decision_action(getattr(result, "action", None))
    if action is None:
        action = normalize_decision_action(getattr(result, "operation_advice", None))
    if action is None:
        decision_type = str(getattr(result, "decision_type", "") or "").strip().lower()
        action = normalize_decision_action(decision_type)

    intel = dashboard.get("intelligence") if isinstance(dashboard.get("intelligence"), Mapping) else {}
    phase_decision = (
        dashboard.get("phase_decision")
        if isinstance(dashboard.get("phase_decision"), Mapping)
        else {}
    )
    previous_forced = (
        dashboard.get("forced_conclusion")
        if isinstance(dashboard.get("forced_conclusion"), Mapping)
        else None
    )
    forced = build_forced_conclusion(
        action=action,
        info_quality=info_quality,
        language=language,
        risk_summary=getattr(result, "risk_warning", None) or intel.get("risk_alerts"),
        watch_conditions=phase_decision.get("watch_conditions"),
        confidence_level=getattr(result, "confidence_level", None),
        quality_constraints_enabled=grading_enabled,
    )
    if (
        isinstance(previous_forced, Mapping)
        and previous_forced.get("schema_version") == FORCED_CONCLUSION_SCHEMA_VERSION
        and previous_forced.get("raw_stance") == "Pass"
        and previous_forced.get("stance") == "Watch"
        and forced.get("stance") == "Watch"
        and previous_forced.get("info_quality_grade") == forced.get("info_quality_grade")
    ):
        forced["raw_stance"] = "Pass"
        prior_reasons = _list_strings(
            previous_forced.get("constraint_reasons"),
            limit=12,
        )
        current_reasons = _list_strings(
            forced.get("constraint_reasons"),
            limit=12,
        )
        forced["constraint_reasons"] = list(
            dict.fromkeys([*prior_reasons, *current_reasons])
        )[:12]
        forced["uncertainty"] = True

    if enforce_action_downgrade and forced.get("constraint_reasons"):
        target_action = forced.get("action")
        if target_action and target_action != action and action in _PASS_ACTIONS:
            _downgrade_result_to_watch(
                result,
                language=language,
                grade=str(info_quality.get("grade") or "C"),
                reason_codes=list(forced.get("constraint_reasons") or []),
            )
            forced["confidence_level"] = _bounded_text(
                getattr(result, "confidence_level", None)
            ) or None
            adjustments.extend(
                str(code) for code in forced.get("constraint_reasons") or []
            )
            adjustments.append("forced_conclusion_pass_blocked")

    dashboard["forced_conclusion"] = forced
    if grading_enabled:
        dashboard["info_quality"] = info_quality
    adjustments.append(f"forced_conclusion_{str(forced.get('stance') or 'Watch').lower()}")
    return adjustments


def resolve_info_quality(
    data_quality: Optional[Mapping[str, Any]],
    *,
    blocks: Any = None,
) -> Dict[str, Any]:
    """Resolve grade using complete inputs; prefer precomputed when re-grade lacks status."""

    quality = data_quality if isinstance(data_quality, Mapping) else {}
    precomputed = _precomputed_info_quality(quality)
    normalized_blocks = _normalize_blocks_input(blocks)
    limitations = _list_strings(quality.get("limitations"))
    has_status_signal = bool(normalized_blocks) or any(
        ":" in item for item in limitations
    )
    if precomputed is not None and not has_status_signal:
        return precomputed
    graded = grade_info_quality(
        quality,
        blocks=normalized_blocks if normalized_blocks else None,
    )
    if precomputed is not None and not _has_core_status_signal(
        _block_statuses(normalized_blocks, limitations)
    ):
        # Re-grade had no core statuses; keep builder/overview grade.
        return precomputed
    if precomputed is not None:
        return _merge_info_quality(precomputed, graded)
    return graded


def _merge_info_quality(
    precomputed: Mapping[str, Any],
    graded: Mapping[str, Any],
) -> Dict[str, Any]:
    """Merge two valid grades without allowing a later projection to improve risk."""

    pre_grade = _safe_grade(precomputed.get("grade")) or "C"
    next_grade = _safe_grade(graded.get("grade")) or "C"
    dimensions: Dict[str, InfoQualityGrade] = {}
    for key in ("source_reliability", "timeliness", "consistency"):
        dimensions[key] = _worst_grade(
            _safe_grade(_nested_mapping_value(precomputed, "dimensions", key)) or "C",
            _safe_grade(_nested_mapping_value(graded, "dimensions", key)) or "C",
        )
    scores = [
        value
        for value in (
            precomputed.get("overall_score"),
            graded.get("overall_score"),
        )
        if isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= 100
    ]
    issue_counts = [
        value
        for value in (
            precomputed.get("validation_issue_count"),
            graded.get("validation_issue_count"),
        )
        if isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= _MAX_EVIDENCE_RECORDS * _MAX_EVIDENCE_ISSUES
    ]
    reasons = list(
        dict.fromkeys(
            [
                *_list_strings(precomputed.get("reasons"), limit=12),
                *_list_strings(graded.get("reasons"), limit=12),
            ]
        )
    )[:12]
    return {
        "schema_version": INFO_QUALITY_SCHEMA_VERSION,
        "grade": _worst_grade(pre_grade, next_grade),
        "dimensions": dimensions,
        "level": _bounded_text(
            graded.get("level") or precomputed.get("level"),
            limit=32,
        ) or None,
        "overall_score": min(scores) if scores else None,
        "evidence_backed": (
            precomputed.get("evidence_backed") is True
            and graded.get("evidence_backed") is True
        ),
        "reasons": reasons,
        "source": "data_quality_evidence.v1+analysis_context_pack",
        "validation_issue_count": max(issue_counts) if issue_counts else None,
    }


def _nested_mapping_value(value: Mapping[str, Any], key: str, nested_key: str) -> Any:
    nested = value.get(key)
    return nested.get(nested_key) if isinstance(nested, Mapping) else None


def _validation_evidence(
    quality: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> tuple[List[Dict[str, Any]], int]:
    candidates: List[Any] = []
    if isinstance(quality.get("validation_evidence"), list):
        candidates.extend(quality.get("validation_evidence") or [])
    if isinstance(metadata.get("validation_evidence"), list):
        candidates.extend(metadata.get("validation_evidence") or [])
    evidence: List[Dict[str, Any]] = []
    invalid_count = max(0, len(candidates) - (_MAX_EVIDENCE_RECORDS * 2))
    signatures = set()
    for item in candidates[-(_MAX_EVIDENCE_RECORDS * 2):]:
        if not isinstance(item, Mapping):
            invalid_count += 1
            continue
        if str(item.get("schema_version") or "") != "data_quality_evidence.v1":
            invalid_count += 1
            continue
        severity = item.get("severity")
        if not isinstance(severity, str) or severity not in _VALIDATION_SEVERITIES:
            invalid_count += 1
            continue
        rejected = item.get("rejected", False)
        if type(rejected) is not bool:
            invalid_count += 1
            continue
        issues_raw = item.get("issues", [])
        if not isinstance(issues_raw, list):
            invalid_count += 1
            continue
        issues: List[Dict[str, Any]] = []
        item_invalid = False
        for issue in issues_raw[:_MAX_EVIDENCE_ISSUES]:
            if not isinstance(issue, Mapping):
                item_invalid = True
                continue
            issue_severity = issue.get("severity", severity)
            if (
                not isinstance(issue_severity, str)
                or issue_severity not in _VALIDATION_SEVERITIES
            ):
                item_invalid = True
                continue
            code = _bounded_text(issue.get("code"), limit=96)
            if not code:
                item_invalid = True
                continue
            issues.append({"code": code, "severity": issue_severity})
        if len(issues_raw) > _MAX_EVIDENCE_ISSUES:
            item_invalid = True
        reason_codes_raw = item.get("reason_codes", [])
        reason_codes: List[str] = []
        if not isinstance(reason_codes_raw, list):
            item_invalid = True
        else:
            for reason_code in reason_codes_raw[:_MAX_EVIDENCE_ISSUES]:
                code = _bounded_text(reason_code, limit=96)
                if not code:
                    item_invalid = True
                    continue
                if code not in reason_codes:
                    reason_codes.append(code)
            if len(reason_codes_raw) > _MAX_EVIDENCE_ISSUES:
                item_invalid = True
        provenance_raw = item.get("provenance")
        provenance: Dict[str, bool] = {}
        if provenance_raw is not None:
            if not isinstance(provenance_raw, Mapping):
                item_invalid = True
            else:
                for key in ("stale", "cache_stale", "fallback"):
                    value = provenance_raw.get(key)
                    if value is None:
                        continue
                    if type(value) is not bool:
                        item_invalid = True
                    else:
                        provenance[key] = value
        data_type = _bounded_text(item.get("data_type"), limit=64)
        if not data_type:
            item_invalid = True
        effective_severity = max(
            [severity, *(issue["severity"] for issue in issues)],
            key=_VALIDATION_SEVERITY_RANK.__getitem__,
        )
        normalized = {
            "schema_version": "data_quality_evidence.v1",
            "data_type": data_type,
            "severity": effective_severity,
            "rejected": rejected,
            "issues": issues,
            "reason_codes": reason_codes,
            "provenance": provenance,
        }
        signature = (
            normalized["data_type"],
            effective_severity,
            rejected,
            tuple((issue["code"], issue["severity"]) for issue in issues),
            tuple(reason_codes),
            tuple(sorted(provenance.items())),
        )
        if signature not in signatures and len(evidence) < _MAX_EVIDENCE_RECORDS:
            signatures.add(signature)
            evidence.append(normalized)
        if item_invalid:
            invalid_count += 1
    return evidence, min(invalid_count, _MAX_EVIDENCE_RECORDS)


def _normalize_blocks_input(blocks: Any) -> Dict[str, Dict[str, Any]]:
    """Normalize pack mapping or overview list into ``{key: block_dict}``."""

    if isinstance(blocks, Mapping):
        out: Dict[str, Dict[str, Any]] = {}
        for key, value in blocks.items():
            text_key = _bounded_text(key, limit=64)
            if not text_key:
                continue
            if isinstance(value, Mapping):
                out[text_key] = dict(value)
            elif isinstance(value, str) and value.strip():
                out[text_key] = {"status": value.strip()}
            else:
                out[text_key] = {"status": "invalid"}
        return out
    if isinstance(blocks, Sequence) and not isinstance(blocks, (str, bytes)):
        out = {}
        for item in blocks:
            if not isinstance(item, Mapping):
                continue
            key = _bounded_text(item.get("key"), limit=64)
            if not key:
                continue
            if key in out:
                out[key] = {"status": "invalid"}
            else:
                out[key] = dict(item)
        return out
    return {}


def _block_statuses(
    blocks: Any,
    limitations: Sequence[str],
) -> Dict[str, str]:
    statuses: Dict[str, str] = {}
    normalized = _normalize_blocks_input(blocks)
    for key, block in normalized.items():
        raw_status = block.get("status")
        status = (
            raw_status.strip().lower()
            if isinstance(raw_status, str)
            else ""
        )
        if status:
            statuses[key] = status if status in _KNOWN_BLOCK_STATUSES else "invalid"
    for item in limitations:
        key, separator, status = str(item).partition(":")
        if not separator:
            continue
        normalized_key = key.strip()
        normalized_status = status.strip().lower()
        if normalized_key and normalized_status and normalized_key not in statuses:
            statuses[normalized_key] = (
                normalized_status
                if normalized_status in _KNOWN_BLOCK_STATUSES
                else "invalid"
            )
    return statuses


def _has_core_status_signal(block_statuses: Mapping[str, str]) -> bool:
    return any(key in block_statuses for key in _CORE_BLOCKS)


def _precomputed_info_quality(quality: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    candidates: List[Any] = [quality.get("info_quality")]
    metadata = quality.get("metadata")
    if isinstance(metadata, Mapping):
        candidates.append(metadata.get("info_quality"))
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        if candidate.get("schema_version") != INFO_QUALITY_SCHEMA_VERSION:
            continue
        grade = _safe_grade(candidate.get("grade") or candidate.get("info_quality_grade"))
        if grade is None:
            continue
        dimensions_raw = candidate.get("dimensions")
        dimensions: Dict[str, str] = {}
        if isinstance(dimensions_raw, Mapping):
            for key in ("source_reliability", "timeliness", "consistency"):
                dim = _safe_grade(dimensions_raw.get(key))
                if dim:
                    dimensions[key] = dim
        if set(dimensions) != {"source_reliability", "timeliness", "consistency"}:
            continue
        if type(candidate.get("evidence_backed")) is not bool:
            continue
        score = candidate.get("overall_score", quality.get("overall_score"))
        if not (
            isinstance(score, int)
            and not isinstance(score, bool)
            and 0 <= score <= 100
        ):
            score = None
        issue_count = candidate.get("validation_issue_count")
        if not (
            isinstance(issue_count, int)
            and not isinstance(issue_count, bool)
            and 0 <= issue_count <= _MAX_EVIDENCE_RECORDS * _MAX_EVIDENCE_ISSUES
        ):
            issue_count = None
        return {
            "schema_version": INFO_QUALITY_SCHEMA_VERSION,
            "grade": grade,
            "dimensions": dimensions,
            "level": _bounded_text(
                candidate.get("level")
                if candidate.get("level") is not None
                else quality.get("level"),
                limit=32,
            ) or None,
            "overall_score": score,
            "evidence_backed": candidate.get("evidence_backed") is True,
            "reasons": _list_strings(candidate.get("reasons") or ["precomputed_info_quality"], limit=12),
            "source": _bounded_text(
                candidate.get("source")
                or "data_quality_evidence.v1+analysis_context_pack",
                limit=96,
            ),
            "validation_issue_count": issue_count,
        }
    return None


def _grade_source_reliability(
    *,
    quality: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    block_statuses: Mapping[str, str],
    invalid_evidence_count: int,
) -> DimensionGrade:
    if invalid_evidence_count:
        return "C"
    if any(item.get("severity") == "reject" or item.get("rejected") is True for item in evidence):
        return "C"
    # A complete core-status snapshot is required; omissions fail closed.
    if not all(key in block_statuses for key in _CORE_BLOCKS):
        return "C"
    known = [
        block_statuses[key]
        for key in _CORE_BLOCKS
        if key in block_statuses and block_statuses[key]
    ]
    if known:
        if any(
            status in {"fetch_failed", "missing", "not_supported", "invalid"}
            for status in known
        ):
            return "C"
        if any(status in {"fallback", "estimated"} for status in known):
            return "B"
    if any(item.get("severity") == "warn" for item in evidence):
        return "B"
    raw_level = quality.get("level")
    level = raw_level.strip().lower() if isinstance(raw_level, str) else ""
    if level in {"poor", "limited"}:
        return "C"
    if level == "usable":
        return "B"
    return "A"


def _grade_timeliness(
    *,
    evidence: Sequence[Mapping[str, Any]],
    block_statuses: Mapping[str, str],
) -> DimensionGrade:
    known = [
        block_statuses[key]
        for key in _CORE_BLOCKS
        if key in block_statuses and block_statuses[key]
    ]
    if known:
        if any(status == "stale" for status in known):
            return "C"
        if any(status in _TIMELINESS_WEAK for status in known):
            return "B"
    for item in evidence:
        provenance = item.get("provenance")
        if isinstance(provenance, Mapping):
            if provenance.get("stale") is True or provenance.get("cache_stale") is True:
                return "C"
            if provenance.get("fallback") is True:
                return "B"
    return "A"


def _grade_consistency(evidence: Sequence[Mapping[str, Any]]) -> DimensionGrade:
    if not evidence:
        return "A"
    saw_warn = False
    for item in evidence:
        if item.get("severity") == "reject" or item.get("rejected") is True:
            codes = _issue_codes(item)
            if codes & _CONSISTENCY_CODES or any("cross_source" in code for code in codes):
                return "C"
        codes = _issue_codes(item)
        if codes & _CONSISTENCY_CODES or any("cross_source" in code for code in codes):
            saw_warn = True
    return "B" if saw_warn else "A"


def _issue_codes(item: Mapping[str, Any]) -> set:
    codes = set()
    issues = item.get("issues")
    if isinstance(issues, list):
        for issue in issues:
            if not isinstance(issue, Mapping):
                continue
            code = str(issue.get("code") or "").strip()
            if code:
                codes.add(code)
    reason_codes = item.get("reason_codes")
    if isinstance(reason_codes, Sequence) and not isinstance(
        reason_codes,
        (str, bytes),
    ):
        for code in reason_codes[:_MAX_EVIDENCE_ISSUES]:
            text = _bounded_text(code, limit=96)
            if text:
                codes.add(text)
    return codes


def _validation_issue_count(evidence: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for item in evidence:
        issues = item.get("issues")
        if isinstance(issues, list):
            total += min(len(issues), _MAX_EVIDENCE_ISSUES)
        elif item.get("severity") in {"warn", "reject"}:
            total += 1
    return total


def _is_evidence_backed(
    block_statuses: Mapping[str, str],
    *,
    invalid_evidence_count: int,
) -> bool:
    if invalid_evidence_count:
        return False
    core = [block_statuses.get(key) for key in _CORE_BLOCKS]
    availableish = {"available", "partial", "fallback", "estimated", "stale"}
    return len(core) == len(_CORE_BLOCKS) and all(
        status in availableish for status in core
    )


def _grade_reasons(
    *,
    grade: InfoQualityGrade,
    level: Optional[str],
    source_reliability: DimensionGrade,
    timeliness: DimensionGrade,
    consistency: DimensionGrade,
    evidence: Sequence[Mapping[str, Any]],
    block_statuses: Mapping[str, str],
    invalid_evidence_count: int,
) -> List[str]:
    reasons: List[str] = []
    if level:
        reasons.append(f"level:{level}")
    for name, value in (
        ("source_reliability", source_reliability),
        ("timeliness", timeliness),
        ("consistency", consistency),
    ):
        if value != "A":
            reasons.append(f"{name}:{value}")
    for key in _CORE_BLOCKS:
        status = block_statuses.get(key)
        if status and status != "available":
            reasons.append(f"{key}:{status}")
    if evidence:
        reasons.append(f"validation_records:{min(len(evidence), _MAX_EVIDENCE_RECORDS)}")
    if invalid_evidence_count:
        reasons.append(f"invalid_validation_records:{invalid_evidence_count}")
    if grade == "A" and not reasons:
        reasons.append("validation_and_blocks_clean")
    return reasons[:12]


def _worst_grade(*grades: str) -> InfoQualityGrade:
    worst = "A"
    for grade in grades:
        safe = _safe_grade(grade)
        if safe is None:
            continue
        if _GRADE_RANK[safe] > _GRADE_RANK[worst]:
            worst = safe
    return worst  # type: ignore[return-value]


def _safe_grade(value: Any) -> Optional[InfoQualityGrade]:
    text = str(value or "").strip().upper()
    if text in {"A", "B", "C"}:
        return text  # type: ignore[return-value]
    return None


def _stance_to_action(stance: ForcedStance, raw_action: Optional[DecisionAction]) -> DecisionAction:
    if stance == "Pass":
        return raw_action if raw_action in _PASS_ACTIONS else "buy"
    if stance == "Fail":
        return raw_action if raw_action in _FAIL_ACTIONS else "avoid"
    if raw_action in _WATCH_ACTIONS:
        return raw_action
    return "watch"


def _default_conditions(*, lang: str, grade: str, stance: ForcedStance):
    if lang == "en":
        upgrade = [
            "Core quote, daily bars, and technical data remain available without reject findings.",
            "Cross-source consistency warnings clear and freshness improves.",
        ]
        downgrade = [
            "Validation reject findings appear on price or indicator inputs.",
            "Core data becomes stale, fallback-only, or fetch-failed.",
        ]
        if stance == "Pass":
            downgrade.append("Information quality grade falls to C.")
        if grade == "C":
            upgrade.insert(0, "Information quality grade recovers to A or B with evidence-backed facts.")
        return upgrade[:3], downgrade[:3]
    if lang == "ko":
        upgrade = [
            "시세·일봉·기술 데이터가 거부 없이 유지됩니다.",
            "교차 출처 불일치 경고가 해소되고 신선도가 개선됩니다.",
        ]
        downgrade = [
            "가격 또는 지표 입력에 검증 거부 소견이 나타납니다.",
            "핵심 데이터가 만료·폴백 전용·수집 실패 상태가 됩니다.",
        ]
        if stance == "Pass":
            downgrade.append("정보 품질 등급이 C로 하락합니다.")
        if grade == "C":
            upgrade.insert(0, "정보 품질 등급이 근거 있는 A/B로 회복됩니다.")
        return upgrade[:3], downgrade[:3]
    upgrade = [
        "核心行情、日线与技术数据保持可用且无 reject 校验问题。",
        "跨源一致性告警消除且数据时效改善。",
    ]
    downgrade = [
        "价格或指标输入出现校验 reject。",
        "核心数据变为过期、仅降级来源或抓取失败。",
    ]
    if stance == "Pass":
        downgrade.append("信息质量等级降至 C。")
    if grade == "C":
        upgrade.insert(0, "信息质量等级恢复到有证据支撑的 A/B。")
    return upgrade[:3], downgrade[:3]


def _stance_summary(*, lang: str, stance: ForcedStance, grade: Optional[str], uncertainty: bool) -> str:
    grade_text = grade or "unknown"
    if lang == "en":
        base = {"Pass": "Forced conclusion: Pass", "Fail": "Forced conclusion: Fail", "Watch": "Forced conclusion: Watch"}[stance]
        suffix = f" (info quality {grade_text}"
        if uncertainty:
            suffix += ", uncertain"
        return base + suffix + ")."
    if lang == "ko":
        base = {"Pass": "강제 결론: Pass", "Fail": "강제 결론: Fail", "Watch": "강제 결론: Watch"}[stance]
        suffix = f" (정보 품질 {grade_text}"
        if uncertainty:
            suffix += ", 불확실"
        return base + suffix + ")."
    base = {"Pass": "强制结论：Pass", "Fail": "强制结论：Fail", "Watch": "强制结论：Watch"}[stance]
    suffix = f"（信息质量 {grade_text}"
    if uncertainty:
        suffix += "，不确定"
    return base + suffix + "）。"


def _downgrade_result_to_watch(result, *, language: str, grade: str, reason_codes: Sequence[str]) -> None:
    lang = normalize_report_language(language)
    if lang == "en":
        advice = "Hold and watch"
        reason = (
            f"Information quality grade {grade} blocks an evidence-backed Pass; "
            "treat the stance as Watch with explicit uncertainty."
        )
        signal_type = "🟡 Hold / Watch"
        confidence = "Low"
    elif lang == "ko":
        advice = "보유 관찰"
        reason = (
            f"정보 품질 등급 {grade} 때문에 근거 있는 Pass를 확정할 수 없어 "
            "Watch(불확실)로 처리합니다."
        )
        signal_type = "🟡 보유/관망"
        confidence = "낮음"
    else:
        advice = "持有观察"
        reason = (
            f"信息质量等级为 {grade}，禁止无充分证据的 Pass 结论冒充事实，"
            "已降级为 Watch 并标注不确定。"
        )
        signal_type = "🟡持有观望"
        confidence = "低"

    result.decision_type = "hold"
    result.operation_advice = advice
    result.action = "watch"
    result.action_label = localize_action_label("watch", lang)
    result.confidence_level = localize_confidence_level(confidence, lang)
    combined_reasons = []
    existing_guardrail = _bounded_text(getattr(result, "guardrail_reason", None), limit=512)
    for code in [*existing_guardrail.split(","), *reason_codes]:
        text = _bounded_text(code, limit=96)
        if text and text not in combined_reasons:
            combined_reasons.append(text)
    result.guardrail_reason = ",".join(combined_reasons[:12]) or "info_quality_grade_c"

    dashboard = result.dashboard if isinstance(result.dashboard, dict) else {}
    result.dashboard = dashboard
    core = dashboard.get("core_conclusion")
    if not isinstance(core, dict):
        core = {}
        dashboard["core_conclusion"] = core
    core["signal_type"] = signal_type
    existing = str(core.get("one_sentence") or "").strip()
    core["one_sentence"] = f"{advice}: {reason}" if lang == "en" else f"{advice}：{reason}"
    if existing and existing not in core["one_sentence"]:
        core["one_sentence"] = f"{core['one_sentence']} ({existing[:80]})"

    warning = str(getattr(result, "risk_warning", "") or "").strip()
    if reason not in warning:
        sep = "; " if lang == "en" else "；"
        result.risk_warning = f"{warning}{sep}{reason}" if warning else reason

    raw_score = getattr(result, "sentiment_score", 50)
    try:
        score_value = float(raw_score) if not isinstance(raw_score, bool) else 50.0
    except (TypeError, ValueError, OverflowError):
        score_value = 50.0
    if not isfinite(score_value):
        score_value = 50.0
    result.sentiment_score = min(59, max(0, int(score_value)))


def _list_strings(value: Any, limit: int = 6) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = _bounded_text(value)
        return [text] if text else []
    if isinstance(value, Mapping):
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        out: List[str] = []
        for item in value:
            if isinstance(item, Mapping):
                continue
            text = _bounded_text(item)
            if text and text not in out:
                out.append(text)
            if len(out) >= limit:
                break
        return out
    text = _bounded_text(value)
    return [text] if text else []


def _bounded_text(value: Any, *, limit: int = _MAX_TEXT) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text[:limit]


def _text(lang: str, *, en: str, zh: str, ko: str) -> str:
    if lang == "en":
        return en
    if lang == "ko":
        return ko
    return zh
