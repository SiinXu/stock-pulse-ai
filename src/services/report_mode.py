# -*- coding: utf-8 -*-
"""Report mode contract: brief / standard / research + hard length limits (#861 Phase 2).

Presentation-layer only. Modes select which sections render and apply deterministic
hard limits (list counts / field character caps). The Decision Card is never
dropped when content is truncated; omitted content is annotated explicitly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

REPORT_MODE_BRIEF = "brief"
REPORT_MODE_STANDARD = "standard"
REPORT_MODE_RESEARCH = "research"

VALID_REPORT_MODES = frozenset(
    {REPORT_MODE_BRIEF, REPORT_MODE_STANDARD, REPORT_MODE_RESEARCH}
)

# Platform defaults when neither extra_context nor a non-default config forces a mode.
_PLATFORM_DEFAULT_MODE = {
    "brief": REPORT_MODE_BRIEF,
    "wechat": REPORT_MODE_BRIEF,
    "markdown": REPORT_MODE_STANDARD,
}

# Hard limits from issue #861. Decision Card itself is never omitted as a block;
# individual card fields still honor character caps so the card stays scannable.
_MODE_LIMITS: Dict[str, Dict[str, Any]] = {
    REPORT_MODE_BRIEF: {
        "one_sentence_max": 50,
        "max_risks": 1,
        "risk_max_chars": 40,
        "max_triggers": 2,
        "trigger_max_chars": 40,
        "max_key_facts": 0,
        "max_catalysts": 0,
        "max_model_inference": 0,
        "max_checklist": 0,
        "max_committee_members": 0,
        "strata_style": "none",  # none | compact | full
        "include_detail_sections": False,
        "include_core_duplicate": False,
        "include_intelligence": False,
        "include_data_perspective": False,
        "include_phase_decision": False,
        "include_signal_attribution": False,
        "include_strategy_synthesis": False,
        "include_committee": False,
        "include_battle_plan": False,
        "include_history": False,
        "include_market_snapshot": False,
    },
    REPORT_MODE_STANDARD: {
        "one_sentence_max": 50,
        "max_risks": 3,
        "risk_max_chars": 40,
        "max_triggers": 2,
        "trigger_max_chars": 40,
        "max_key_facts": 7,
        "max_catalysts": 2,
        "max_model_inference": 3,
        "max_checklist": 8,
        "max_committee_members": 5,
        "strata_style": "compact",
        "include_detail_sections": True,
        "include_core_duplicate": True,
        "include_intelligence": True,
        "include_data_perspective": True,
        "include_phase_decision": True,
        "include_signal_attribution": True,
        "include_strategy_synthesis": True,
        "include_committee": True,
        "include_battle_plan": True,
        "include_history": True,
        "include_market_snapshot": True,
    },
    REPORT_MODE_RESEARCH: {
        "one_sentence_max": 120,
        "max_risks": 20,
        "risk_max_chars": 200,
        "max_triggers": 10,
        "trigger_max_chars": 200,
        "max_key_facts": 50,
        "max_catalysts": 20,
        "max_model_inference": 20,
        "max_checklist": 50,
        "max_committee_members": 20,
        "strata_style": "full",
        "include_detail_sections": True,
        "include_core_duplicate": True,
        "include_intelligence": True,
        "include_data_perspective": True,
        "include_phase_decision": True,
        "include_signal_attribution": True,
        "include_strategy_synthesis": True,
        "include_committee": True,
        "include_battle_plan": True,
        "include_history": True,
        "include_market_snapshot": True,
    },
}


def normalize_report_mode(value: Optional[str], *, default: str = REPORT_MODE_STANDARD) -> str:
    """Normalize a free-form mode string; invalid values fall back to *default*."""
    raw = (value or "").strip().lower()
    if not raw:
        return default if default in VALID_REPORT_MODES else REPORT_MODE_STANDARD
    # Accept issue #861 "minimal" as an alias of brief.
    if raw in {"minimal", "min", "push"}:
        return REPORT_MODE_BRIEF
    if raw in {"full", "deep", "detailed"}:
        return REPORT_MODE_RESEARCH
    if raw in VALID_REPORT_MODES:
        return raw
    return default if default in VALID_REPORT_MODES else REPORT_MODE_STANDARD


def resolve_report_mode(
    platform: str,
    *,
    explicit: Optional[str] = None,
    config_mode: Optional[str] = None,
) -> str:
    """Resolve effective mode.

    Precedence:
    1. explicit per-request ``report_mode``
    2. For push platforms (``brief`` / ``wechat``): brief unless config forces
       ``brief`` or ``research`` (default ``standard`` still maps push → brief so
       unconfigured installs stay push-friendly without dual long reports)
    3. Config ``REPORT_MODE`` (default standard)
    4. standard
    """
    if explicit is not None and str(explicit).strip():
        return normalize_report_mode(str(explicit), default=REPORT_MODE_STANDARD)

    platform_key = (platform or "").strip().lower()
    config_normalized: Optional[str] = None
    if config_mode is not None and str(config_mode).strip():
        config_normalized = normalize_report_mode(
            str(config_mode), default=REPORT_MODE_STANDARD
        )

    if platform_key in ("brief", "wechat"):
        if config_normalized in {REPORT_MODE_BRIEF, REPORT_MODE_RESEARCH}:
            return config_normalized
        # standard (default) or unset → push-oriented brief
        return REPORT_MODE_BRIEF

    if config_normalized is not None:
        return config_normalized
    return _PLATFORM_DEFAULT_MODE.get(platform_key, REPORT_MODE_STANDARD)


def get_mode_limits(mode: str) -> Dict[str, Any]:
    """Return a shallow copy of hard limits for *mode*."""
    normalized = normalize_report_mode(mode)
    return dict(_MODE_LIMITS[normalized])


def _clip_text(value: Any, max_chars: int) -> Tuple[str, bool]:
    text = "" if value is None else str(value).strip()
    if not text:
        return "", False
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip() + "…", True


def _limit_string_list(
    items: Sequence[Any],
    *,
    max_items: int,
    max_chars: int,
) -> Tuple[List[str], int, int]:
    """Return (kept, omitted_item_count, truncated_char_count)."""
    source = [str(item).strip() for item in (items or []) if str(item).strip()]
    if max_items <= 0:
        return [], len(source), 0
    kept: List[str] = []
    char_truncated = 0
    for item in source[:max_items]:
        clipped, was_truncated = _clip_text(item, max_chars)
        if was_truncated:
            char_truncated += 1
        kept.append(clipped)
    omitted = max(0, len(source) - len(kept))
    return kept, omitted, char_truncated


def truncation_notice(omitted_count: int, report_language: str = "zh") -> str:
    """Explicit omission annotation (never silent). Empty when nothing was omitted."""
    if omitted_count <= 0:
        return ""
    lang = (report_language or "zh").lower()
    if lang.startswith("en"):
        return (
            f"_(Omitted {omitted_count} section(s)/item(s); "
            "full report available in research mode.)_"
        )
    if lang.startswith("ko"):
        return (
            f"_({omitted_count}개 항목 생략됨; 전체 보고서는 research 모드에서 확인)_"
        )
    return f"_（已省略 {omitted_count} 段/项，完整报告见 research 模式）_"


def build_decision_card_payload(
    result: Any,
    *,
    signal_text: str,
    signal_emoji: str,
    localized_trend: str,
    limits: Mapping[str, Any],
) -> Dict[str, Any]:
    """Assemble a Decision Card dict from existing result/dashboard fields.

    Missing fields are omitted (None / empty) rather than filled with placeholders.
    List/character hard limits are applied; the card block itself is always returned.
    """
    dashboard = getattr(result, "dashboard", None) or {}
    if not isinstance(dashboard, Mapping):
        dashboard = {}
    core = dashboard.get("core_conclusion") or {}
    if not isinstance(core, Mapping):
        core = {}
    intel = dashboard.get("intelligence") or {}
    if not isinstance(intel, Mapping):
        intel = {}
    battle = dashboard.get("battle_plan") or {}
    if not isinstance(battle, Mapping):
        battle = {}
    phase_decision = dashboard.get("phase_decision") or {}
    if not isinstance(phase_decision, Mapping):
        phase_decision = {}
    sniper = battle.get("sniper_points") or {}
    if not isinstance(sniper, Mapping):
        sniper = {}
    pos_advice = core.get("position_advice") or {}
    if not isinstance(pos_advice, Mapping):
        pos_advice = {}

    one_sentence_raw = core.get("one_sentence") or getattr(result, "analysis_summary", None) or ""
    one_sentence, one_sentence_clipped = _clip_text(
        one_sentence_raw, int(limits.get("one_sentence_max", 50))
    )

    risk_source: List[Any] = []
    if isinstance(intel.get("risk_alerts"), list):
        risk_source = list(intel.get("risk_alerts") or [])
    elif getattr(result, "risk_warning", None):
        risk_source = [getattr(result, "risk_warning")]

    risks, risks_omitted, risks_char_trunc = _limit_string_list(
        risk_source,
        max_items=int(limits.get("max_risks", 3)),
        max_chars=int(limits.get("risk_max_chars", 40)),
    )

    trigger_source: List[Any] = []
    watch = phase_decision.get("watch_conditions")
    if isinstance(watch, list):
        trigger_source = list(watch)
    triggers, triggers_omitted, triggers_char_trunc = _limit_string_list(
        trigger_source,
        max_items=int(limits.get("max_triggers", 2)),
        max_chars=int(limits.get("trigger_max_chars", 40)),
    )

    confidence_level = str(getattr(result, "confidence_level", None) or "").strip()
    confidence_reason = str(phase_decision.get("confidence_reason") or "").strip()
    time_sensitivity = str(core.get("time_sensitivity") or "").strip()
    immediate_action = str(phase_decision.get("immediate_action") or "").strip()
    stop_loss = sniper.get("stop_loss")
    take_profit = sniper.get("take_profit")

    omitted = risks_omitted + triggers_omitted
    truncated_fields = risks_char_trunc + triggers_char_trunc + (1 if one_sentence_clipped else 0)

    return {
        "signal_text": signal_text,
        "signal_emoji": signal_emoji,
        "score": getattr(result, "sentiment_score", None),
        "one_sentence": one_sentence or None,
        "trend": (localized_trend or "").strip() or None,
        "confidence_level": confidence_level or None,
        "confidence_reason": confidence_reason or None,
        "immediate_action": immediate_action or None,
        "time_sensitivity": time_sensitivity or None,
        "position_no": str(pos_advice.get("no_position") or "").strip() or None,
        "position_has": str(pos_advice.get("has_position") or "").strip() or None,
        "risks": risks,
        "triggers": triggers,
        "stop_loss": stop_loss if stop_loss not in (None, "", "N/A") else None,
        "take_profit": take_profit if take_profit not in (None, "", "N/A") else None,
        "omitted_count": omitted,
        "truncated_field_count": truncated_fields,
    }


def apply_list_limits_to_dashboard_view(
    dashboard: Optional[Mapping[str, Any]],
    limits: Mapping[str, Any],
) -> Tuple[Dict[str, Any], int]:
    """Return a shallow-limited dashboard view for template loops + omitted count.

    Does not mutate the original dashboard. Used so standard/research templates
    can share one limit path instead of scattering ``[:N]`` caps.
    """
    if not isinstance(dashboard, Mapping):
        return {}, 0
    view: Dict[str, Any] = dict(dashboard)
    omitted = 0

    intel = dict(view.get("intelligence") or {}) if isinstance(view.get("intelligence"), Mapping) else {}
    if intel:
        risks = intel.get("risk_alerts") if isinstance(intel.get("risk_alerts"), list) else []
        limited_risks, risk_omitted, _ = _limit_string_list(
            risks,
            max_items=int(limits.get("max_risks", 3)),
            max_chars=int(limits.get("risk_max_chars", 40)),
        )
        omitted += risk_omitted
        if risks:
            intel["risk_alerts"] = limited_risks

        cats = intel.get("positive_catalysts") if isinstance(intel.get("positive_catalysts"), list) else []
        limited_cats, cat_omitted, _ = _limit_string_list(
            cats,
            max_items=int(limits.get("max_catalysts", 2)),
            max_chars=int(limits.get("risk_max_chars", 40)),
        )
        omitted += cat_omitted
        if cats:
            intel["positive_catalysts"] = limited_cats
        view["intelligence"] = intel

    phase = dict(view.get("phase_decision") or {}) if isinstance(view.get("phase_decision"), Mapping) else {}
    if phase:
        watch = phase.get("watch_conditions") if isinstance(phase.get("watch_conditions"), list) else []
        limited_watch, watch_omitted, _ = _limit_string_list(
            watch,
            max_items=int(limits.get("max_triggers", 2)),
            max_chars=int(limits.get("trigger_max_chars", 40)),
        )
        omitted += watch_omitted
        if watch:
            phase["watch_conditions"] = limited_watch
        view["phase_decision"] = phase

    battle = dict(view.get("battle_plan") or {}) if isinstance(view.get("battle_plan"), Mapping) else {}
    if battle:
        checklist = battle.get("action_checklist") if isinstance(battle.get("action_checklist"), list) else []
        max_checklist = int(limits.get("max_checklist", 8))
        if checklist and max_checklist >= 0 and len(checklist) > max_checklist:
            omitted += len(checklist) - max_checklist
            battle["action_checklist"] = list(checklist[:max_checklist])
            view["battle_plan"] = battle
        elif checklist:
            view["battle_plan"] = battle

    committee = dict(view.get("committee_deliberation") or {}) if isinstance(
        view.get("committee_deliberation"), Mapping
    ) else {}
    if committee:
        members = committee.get("members") if isinstance(committee.get("members"), list) else []
        max_members = int(limits.get("max_committee_members", 5))
        if members and max_members >= 0 and len(members) > max_members:
            omitted += len(members) - max_members
            committee["members"] = list(members[:max_members])
            view["committee_deliberation"] = committee
        elif members:
            view["committee_deliberation"] = committee

        inference = (
            committee.get("model_inference")
            if isinstance(committee.get("model_inference"), list)
            else []
        )
        max_inf = int(limits.get("max_model_inference", 3))
        if inference and max_inf >= 0 and len(inference) > max_inf:
            omitted += len(inference) - max_inf
            committee["model_inference"] = list(inference[:max_inf])
            view["committee_deliberation"] = committee

    strata = view.get("report_strata")
    if isinstance(strata, Mapping):
        strata_view: MutableMapping[str, Any] = dict(strata)
        facts = strata_view.get("verified_facts")
        if isinstance(facts, list):
            max_facts = int(limits.get("max_key_facts", 7))
            if max_facts >= 0 and len(facts) > max_facts:
                omitted += len(facts) - max_facts
                strata_view["verified_facts"] = list(facts[:max_facts])
        inference = strata_view.get("model_inference")
        if isinstance(inference, list):
            max_inf = int(limits.get("max_model_inference", 3))
            if max_inf >= 0 and len(inference) > max_inf:
                omitted += len(inference) - max_inf
                strata_view["model_inference"] = list(inference[:max_inf])
        risks = strata_view.get("risks_counter_evidence")
        if isinstance(risks, list):
            max_risks = int(limits.get("max_risks", 3))
            if max_risks >= 0 and len(risks) > max_risks:
                omitted += len(risks) - max_risks
                strata_view["risks_counter_evidence"] = list(risks[:max_risks])
        view["report_strata"] = dict(strata_view)

    return view, omitted


__all__ = [
    "REPORT_MODE_BRIEF",
    "REPORT_MODE_STANDARD",
    "REPORT_MODE_RESEARCH",
    "VALID_REPORT_MODES",
    "normalize_report_mode",
    "resolve_report_mode",
    "get_mode_limits",
    "truncation_notice",
    "build_decision_card_payload",
    "apply_list_limits_to_dashboard_view",
]
