# -*- coding: utf-8 -*-
"""Information quality grading and forced-conclusion constraints (Issue #123).

Grades consume existing AnalysisContextPack ``data_quality`` output and
``data_quality_evidence.v1`` validation findings. They do not re-run provider
validators or invent a parallel quality score.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Literal, Optional, TYPE_CHECKING

from src.report_language import localize_confidence_level, normalize_report_language
from src.schemas.decision_action import (
    DecisionAction,
    localize_action_label,
    normalize_decision_action,
)
from src.services.decision_signal_data_quality import normalize_decision_signal_data_quality

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
_TIMELINESS_WEAK = frozenset({"stale", "partial"})
_CONSISTENCY_CODES = frozenset(
    {
        "dv_cross_source_divergence",
        "dv_daily_date_out_of_order",
        "dv_daily_date_duplicate",
    }
)


def grade_info_quality(
    data_quality: Optional[Mapping[str, Any]],
    *,
    blocks: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build an A/B/C grade from validation-backed data_quality artifacts."""

    quality = dict(data_quality) if isinstance(data_quality, Mapping) else {}
    metadata = quality.get("metadata") if isinstance(quality.get("metadata"), Mapping) else {}
    evidence = _validation_evidence(quality, metadata)
    limitations = _list_strings(quality.get("limitations"))
    block_statuses = _block_statuses(blocks, limitations)

    source_reliability = _grade_source_reliability(
        quality=quality,
        evidence=evidence,
        block_statuses=block_statuses,
    )
    timeliness = _grade_timeliness(evidence=evidence, block_statuses=block_statuses)
    consistency = _grade_consistency(evidence=evidence)

    level = str(quality.get("level") or "").strip().lower()
    level_grade = _LEVEL_TO_GRADE.get(level)
    if level_grade is None:
        score = quality.get("overall_score")
        if isinstance(score, int) and not isinstance(score, bool):
            if score >= 85:
                level_grade = "A"
            elif score >= 70:
                level_grade = "B"
            else:
                level_grade = "C"
        else:
            level_grade = "C" if evidence or block_statuses else "B"

    grade = _worst_grade(level_grade, source_reliability, timeliness, consistency)
    reasons = _grade_reasons(
        grade=grade,
        level=level or None,
        source_reliability=source_reliability,
        timeliness=timeliness,
        consistency=consistency,
        evidence=evidence,
        block_statuses=block_statuses,
    )
    evidence_backed = _is_evidence_backed(block_statuses, evidence)
    overall_score = quality.get("overall_score")
    if not (isinstance(overall_score, int) and not isinstance(overall_score, bool)):
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
        "validation_issue_count": _validation_issue_count(evidence),
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
) -> Dict[str, Any]:
    """Build a forced conclusion payload constrained by information quality."""

    lang = normalize_report_language(language)
    grade = _safe_grade(info_quality.get("grade")) or "C"
    evidence_backed = info_quality.get("evidence_backed") is True
    raw_action = normalize_decision_action(action)
    raw_stance = map_action_to_forced_stance(raw_action)
    final_stance = raw_stance
    uncertainty = False
    constraint_reasons: List[str] = []

    if not evidence_backed and raw_stance == "Pass":
        final_stance = "Watch"
        uncertainty = True
        constraint_reasons.append("no_evidence_pass_blocked")
    if grade == "C" and raw_stance == "Pass":
        final_stance = "Watch"
        uncertainty = True
        constraint_reasons.append("grade_c_pass_downgraded")
    if grade == "C" and raw_stance != "Pass":
        uncertainty = True
        if "grade_c_uncertainty" not in constraint_reasons:
            constraint_reasons.append("grade_c_uncertainty")
    if grade == "B" and raw_stance == "Pass":
        uncertainty = True
        constraint_reasons.append("grade_b_pass_uncertain")

    action_for_stance = _stance_to_action(final_stance, raw_action)
    upgrade, downgrade = _default_conditions(lang=lang, grade=grade, stance=final_stance)
    risks = _list_strings(risk_summary, limit=3)
    watches = _list_strings(watch_conditions, limit=3)
    if not risks and grade == "C":
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
        "confidence_level": str(confidence_level or "").strip() or None,
        "uncertainty": uncertainty,
        "evidence_backed": evidence_backed,
        "info_quality_grade": grade,
        "constraint_reasons": constraint_reasons,
        "upgrade_conditions": upgrade,
        "downgrade_conditions": downgrade,
        "main_risks": risks,
        "watch_conditions": watches,
        "summary": reason
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

    if result is None:
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
    blocks = overview.get("blocks") if isinstance(overview.get("blocks"), Mapping) else None

    dashboard = getattr(result, "dashboard", None)
    if not isinstance(dashboard, dict):
        dashboard = {}
        result.dashboard = dashboard

    adjustments: List[str] = []
    if grading_enabled:
        info_quality = grade_info_quality(data_quality, blocks=blocks)
        dashboard["info_quality"] = info_quality
        adjustments.append(f"info_quality_grade_{info_quality['grade'].lower()}")
    else:
        existing = dashboard.get("info_quality")
        info_quality = (
            dict(existing)
            if isinstance(existing, Mapping)
            else {
                "schema_version": INFO_QUALITY_SCHEMA_VERSION,
                "grade": "B",
                "dimensions": {
                    "source_reliability": "B",
                    "timeliness": "B",
                    "consistency": "B",
                },
                "evidence_backed": True,
                "reasons": ["grading_disabled"],
            }
        )

    if not forced_conclusion_enabled:
        return adjustments

    action = normalize_decision_action(getattr(result, "action", None))
    if action is None:
        action = normalize_decision_action(getattr(result, "operation_advice", None))
    if action is None:
        decision_type = str(getattr(result, "decision_type", "") or "").strip().lower()
        action = normalize_decision_action(decision_type) or "watch"

    intel = dashboard.get("intelligence") if isinstance(dashboard.get("intelligence"), Mapping) else {}
    phase_decision = (
        dashboard.get("phase_decision")
        if isinstance(dashboard.get("phase_decision"), Mapping)
        else {}
    )
    forced = build_forced_conclusion(
        action=action,
        info_quality=info_quality,
        language=language,
        risk_summary=getattr(result, "risk_warning", None) or intel.get("risk_alerts"),
        watch_conditions=phase_decision.get("watch_conditions"),
        confidence_level=getattr(result, "confidence_level", None),
        reason=str(getattr(result, "analysis_summary", None) or "").strip() or None,
    )

    if enforce_action_downgrade and forced.get("constraint_reasons"):
        target_action = forced.get("action")
        if target_action and target_action != action and action in _PASS_ACTIONS:
            _downgrade_result_to_watch(
                result,
                language=language,
                grade=str(info_quality.get("grade") or "C"),
                reason_codes=list(forced.get("constraint_reasons") or []),
            )
            forced = build_forced_conclusion(
                action=getattr(result, "action", "watch"),
                info_quality=info_quality,
                language=language,
                risk_summary=getattr(result, "risk_warning", None),
                watch_conditions=phase_decision.get("watch_conditions"),
                confidence_level=getattr(result, "confidence_level", None),
                reason=str(getattr(result, "analysis_summary", None) or "").strip() or None,
            )
            adjustments.extend(str(code) for code in forced.get("constraint_reasons") or [])
            adjustments.append("forced_conclusion_pass_blocked")

    dashboard["forced_conclusion"] = forced
    dashboard["info_quality"] = info_quality
    adjustments.append(f"forced_conclusion_{str(forced.get('stance') or 'Watch').lower()}")
    return adjustments


def info_quality_grade_from_any(value: Any) -> Optional[InfoQualityGrade]:
    """Extract A/B/C from grade payloads or legacy quality levels."""

    if isinstance(value, Mapping):
        direct = _safe_grade(value.get("grade") or value.get("info_quality_grade"))
        if direct:
            return direct
        nested = value.get("info_quality")
        if isinstance(nested, Mapping):
            nested_grade = _safe_grade(nested.get("grade"))
            if nested_grade:
                return nested_grade
        level = normalize_decision_signal_data_quality(value)
        return _LEVEL_TO_GRADE.get(level)
    text = str(value or "").strip().upper()
    if text in {"A", "B", "C"}:
        return text  # type: ignore[return-value]
    level = normalize_decision_signal_data_quality(value)
    return _LEVEL_TO_GRADE.get(level)


def _validation_evidence(
    quality: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    candidates: List[Any] = []
    if isinstance(quality.get("validation_evidence"), list):
        candidates.extend(quality.get("validation_evidence") or [])
    if isinstance(metadata.get("validation_evidence"), list):
        candidates.extend(metadata.get("validation_evidence") or [])
    evidence: List[Dict[str, Any]] = []
    for item in candidates[-24:]:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("schema_version") or "") != "data_quality_evidence.v1":
            continue
        evidence.append(dict(item))
    return evidence


def _block_statuses(
    blocks: Optional[Mapping[str, Any]],
    limitations: Sequence[str],
) -> Dict[str, str]:
    statuses: Dict[str, str] = {}
    if isinstance(blocks, Mapping):
        for key, block in blocks.items():
            if not isinstance(block, Mapping):
                continue
            status = str(block.get("status") or "").strip().lower()
            if status:
                statuses[str(key)] = status
    for item in limitations:
        key, separator, status = str(item).partition(":")
        if not separator:
            continue
        normalized_key = key.strip()
        normalized_status = status.strip().lower()
        if normalized_key and normalized_status and normalized_key not in statuses:
            statuses[normalized_key] = normalized_status
    return statuses


def _grade_source_reliability(
    *,
    quality: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    block_statuses: Mapping[str, str],
) -> DimensionGrade:
    if any(item.get("severity") == "reject" or item.get("rejected") is True for item in evidence):
        return "C"
    core_statuses = [block_statuses.get(key, "missing") for key in _CORE_BLOCKS]
    if any(status in {"fetch_failed", "missing"} for status in core_statuses):
        return "C"
    if any(status in {"fallback", "estimated"} for status in core_statuses):
        return "B"
    level = str(quality.get("level") or "").strip().lower()
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
    core_statuses = [block_statuses.get(key, "available") for key in _CORE_BLOCKS]
    if any(status == "stale" for status in core_statuses):
        return "C"
    if any(status in _TIMELINESS_WEAK for status in core_statuses):
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
        if item.get("severity") == "warn":
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
    for code in item.get("reason_codes") or []:
        text = str(code or "").strip()
        if text:
            codes.add(text)
    return codes


def _validation_issue_count(evidence: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for item in evidence:
        issues = item.get("issues")
        if isinstance(issues, list):
            total += len(issues)
        elif item.get("severity") in {"warn", "reject"}:
            total += 1
    return total


def _is_evidence_backed(
    block_statuses: Mapping[str, str],
    evidence: Sequence[Mapping[str, Any]],
) -> bool:
    core = [block_statuses.get(key) for key in _CORE_BLOCKS]
    if not any(core):
        return not any(
            item.get("severity") == "reject" or item.get("rejected") is True
            for item in evidence
        )
    availableish = {"available", "partial", "fallback", "estimated", "stale"}
    return any(status in availableish for status in core if status)


def _grade_reasons(
    *,
    grade: InfoQualityGrade,
    level: Optional[str],
    source_reliability: DimensionGrade,
    timeliness: DimensionGrade,
    consistency: DimensionGrade,
    evidence: Sequence[Mapping[str, Any]],
    block_statuses: Mapping[str, str],
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
        reasons.append(f"validation_records:{min(len(evidence), 24)}")
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


def _stance_summary(*, lang: str, stance: ForcedStance, grade: str, uncertainty: bool) -> str:
    if lang == "en":
        base = {"Pass": "Forced conclusion: Pass", "Fail": "Forced conclusion: Fail", "Watch": "Forced conclusion: Watch"}[stance]
        suffix = f" (info quality {grade}"
        if uncertainty:
            suffix += ", uncertain"
        return base + suffix + ")."
    if lang == "ko":
        base = {"Pass": "강제 결론: Pass", "Fail": "강제 결론: Fail", "Watch": "강제 결론: Watch"}[stance]
        suffix = f" (정보 품질 {grade}"
        if uncertainty:
            suffix += ", 불확실"
        return base + suffix + ")."
    base = {"Pass": "强制结论：Pass", "Fail": "强制结论：Fail", "Watch": "强制结论：Watch"}[stance]
    suffix = f"（信息质量 {grade}"
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
    result.guardrail_reason = ",".join(reason_codes) if reason_codes else "info_quality_grade_c"

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

    try:
        score = int(getattr(result, "sentiment_score", 50))
    except (TypeError, ValueError):
        score = 50
    result.sentiment_score = min(59, max(40, score))


def _list_strings(value: Any, limit: int = 6) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Mapping):
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        out: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in out:
                out.append(text)
            if len(out) >= limit:
                break
        return out
    text = str(value).strip()
    return [text] if text else []


def _text(lang: str, *, en: str, zh: str, ko: str) -> str:
    if lang == "en":
        return en
    if lang == "ko":
        return ko
    return zh
