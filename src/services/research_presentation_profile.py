# -*- coding: utf-8 -*-
"""Research presentation profiles: conservative / balanced / aggressive (#205).

Presentation-layer only. Profiles reorder emphasis of the *same* analysis
evidence for research framing. They must never:

- change underlying facts, scores, actions, or decision outputs
- reduce risk disclosure completeness relative to another profile
  (list/character limits remain owned solely by ``REPORT_MODE``)
- alter ``RISK_GATE_PROFILE`` / ``decision_profile`` analysis semantics

Orthogonal axes:

- ``REPORT_MODE`` (brief / standard / research): section inclusion + hard limits
- ``RESEARCH_PRESENTATION_PROFILE`` (this module): emphasis / ordering only
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

PROFILE_CONSERVATIVE = "conservative"
PROFILE_BALANCED = "balanced"
PROFILE_AGGRESSIVE = "aggressive"

VALID_RESEARCH_PRESENTATION_PROFILES = frozenset(
    {PROFILE_CONSERVATIVE, PROFILE_BALANCED, PROFILE_AGGRESSIVE}
)

# Intelligence body fields that may be reordered for emphasis.
INTEL_BLOCK_KEYS: Tuple[str, ...] = (
    "sentiment_summary",
    "earnings_outlook",
    "risk_alerts",
    "positive_catalysts",
    "latest_news",
)

# Full evidence-strata block keys (framework alignment always last for disclaimer
# adjacency). Risk block is never dropped by a profile.
STRATA_BLOCK_KEYS: Tuple[str, ...] = (
    "verified_facts",
    "missing_or_conflicts",
    "model_inference",
    "risks_counter_evidence",
    "framework_alignment",
)

_PROFILE_PLANS: Dict[str, Dict[str, Any]] = {
    PROFILE_CONSERVATIVE: {
        # Risk and gaps first; catalysts still fully present later.
        "intelligence_block_order": [
            "risk_alerts",
            "earnings_outlook",
            "sentiment_summary",
            "positive_catalysts",
            "latest_news",
        ],
        "strata_block_order": [
            "risks_counter_evidence",
            "missing_or_conflicts",
            "verified_facts",
            "model_inference",
            "framework_alignment",
        ],
        "wechat_emphasis_order": ["risk_alerts", "positive_catalysts"],
        "emphasis": "risk_first",
    },
    PROFILE_BALANCED: {
        # Historical default order used by templates before #205.
        "intelligence_block_order": list(INTEL_BLOCK_KEYS),
        "strata_block_order": list(STRATA_BLOCK_KEYS),
        "wechat_emphasis_order": ["risk_alerts", "positive_catalysts"],
        "emphasis": "balanced",
    },
    PROFILE_AGGRESSIVE: {
        # Opportunity emphasis first; risk blocks remain complete, just later.
        "intelligence_block_order": [
            "positive_catalysts",
            "sentiment_summary",
            "earnings_outlook",
            "latest_news",
            "risk_alerts",
        ],
        "strata_block_order": [
            "verified_facts",
            "model_inference",
            "risks_counter_evidence",
            "missing_or_conflicts",
            "framework_alignment",
        ],
        "wechat_emphasis_order": ["positive_catalysts", "risk_alerts"],
        "emphasis": "opportunity_first",
    },
}


def normalize_research_presentation_profile(
    value: Optional[str],
    *,
    default: str = PROFILE_BALANCED,
) -> str:
    """Normalize a free-form profile string; invalid values fall back to *default*."""
    raw = (value or "").strip().lower()
    if not raw:
        return (
            default
            if default in VALID_RESEARCH_PRESENTATION_PROFILES
            else PROFILE_BALANCED
        )
    aliases = {
        "risk_averse": PROFILE_CONSERVATIVE,
        "defensive": PROFILE_CONSERVATIVE,
        "cautious": PROFILE_CONSERVATIVE,
        "neutral": PROFILE_BALANCED,
        "default": PROFILE_BALANCED,
        "growth": PROFILE_AGGRESSIVE,
        "offensive": PROFILE_AGGRESSIVE,
        "opportunity": PROFILE_AGGRESSIVE,
    }
    if raw in aliases:
        return aliases[raw]
    if raw in VALID_RESEARCH_PRESENTATION_PROFILES:
        return raw
    return (
        default
        if default in VALID_RESEARCH_PRESENTATION_PROFILES
        else PROFILE_BALANCED
    )


def resolve_research_presentation_profile(
    *,
    explicit: Optional[str] = None,
    config_profile: Optional[str] = None,
) -> str:
    """Resolve effective research presentation profile.

    Precedence:
    1. explicit per-request ``research_presentation_profile``
    2. Config ``RESEARCH_PRESENTATION_PROFILE`` (default balanced)
    3. balanced
    """
    if explicit is not None and str(explicit).strip():
        return normalize_research_presentation_profile(
            str(explicit), default=PROFILE_BALANCED
        )
    if config_profile is not None and str(config_profile).strip():
        return normalize_research_presentation_profile(
            str(config_profile), default=PROFILE_BALANCED
        )
    return PROFILE_BALANCED


def get_presentation_plan(profile: str) -> Dict[str, Any]:
    """Return a shallow copy of the presentation plan for *profile*."""
    normalized = normalize_research_presentation_profile(profile)
    plan = dict(_PROFILE_PLANS[normalized])
    plan["profile"] = normalized
    # Defensive copies so callers cannot mutate module constants.
    plan["intelligence_block_order"] = list(plan["intelligence_block_order"])
    plan["strata_block_order"] = list(plan["strata_block_order"])
    plan["wechat_emphasis_order"] = list(plan["wechat_emphasis_order"])
    return plan


def should_emit_framing_notice(
    *,
    report_mode: Optional[str] = None,
    platform: Optional[str] = None,
) -> bool:
    """Return False on push-budget brief surfaces (#861/#874).

    Brief mode / platform have almost no profile reordering surface (Decision Card
    stays risk-leading) and must not spend characters on a long framing banner.
    """
    from src.services.report_mode import REPORT_MODE_BRIEF, normalize_report_mode

    mode = normalize_report_mode(report_mode) if report_mode is not None else None
    plat = (platform or "").strip().lower()
    if mode == REPORT_MODE_BRIEF or plat == "brief":
        return False
    return True


def profile_framing_notice(
    profile: str,
    report_language: str = "zh",
    *,
    style: str = "full",
) -> str:
    """Explicit research-framing banner.

    ``style``:
    - ``full``: long research-framing line for markdown / wechat detail
    - ``none``: empty (brief push budget path)
    """
    if (style or "full").strip().lower() == "none":
        return ""
    normalized = normalize_research_presentation_profile(profile)
    # Prefer report labels so zh/en/ko stay single-sourced with templates.
    from src.report_language import get_report_labels

    labels = get_report_labels(report_language)
    name = {
        PROFILE_CONSERVATIVE: labels.get(
            "presentation_profile_conservative", PROFILE_CONSERVATIVE
        ),
        PROFILE_BALANCED: labels.get(
            "presentation_profile_balanced", PROFILE_BALANCED
        ),
        PROFILE_AGGRESSIVE: labels.get(
            "presentation_profile_aggressive", PROFILE_AGGRESSIVE
        ),
    }[normalized]
    heading = labels.get(
        "presentation_profile_heading", "Research presentation profile"
    )
    detail = labels.get(
        "presentation_profile_framing_detail",
        "emphasis/ordering only; same evidence and full risk disclosure; "
        "research framing aid, not personalized advice",
    )
    return f"_{heading}: **{name}** ({detail})_"


def risk_content_fingerprint(
    dashboard: Optional[Mapping[str, Any]],
    *,
    risk_warning: Any = None,
) -> Tuple[str, ...]:
    """Stable fingerprint of risk disclosure content for parity tests.

    Includes intelligence risk alerts, strata counter-evidence, and optional
    result-level ``risk_warning``. Order is sorted so presentation reordering
    does not change the fingerprint.
    """
    items: List[str] = []
    if isinstance(dashboard, Mapping):
        intel = dashboard.get("intelligence")
        if isinstance(intel, Mapping):
            alerts = intel.get("risk_alerts")
            if isinstance(alerts, Sequence) and not isinstance(alerts, (str, bytes)):
                for alert in alerts:
                    text = str(alert).strip()
                    if text:
                        items.append(f"alert:{text}")
        strata = dashboard.get("report_strata")
        if isinstance(strata, Mapping):
            risks = strata.get("risks_counter_evidence")
            if isinstance(risks, Sequence) and not isinstance(risks, (str, bytes)):
                for risk in risks:
                    text = str(risk).strip()
                    if text:
                        items.append(f"strata:{text}")
    warning = "" if risk_warning is None else str(risk_warning).strip()
    if warning:
        items.append(f"warning:{warning}")
    return tuple(sorted(items))


def assert_profile_does_not_change_limits(
    mode_limits: Mapping[str, Any],
    profile: str,
) -> Mapping[str, Any]:
    """Return *mode_limits* unchanged; documents the risk-parity contract.

    Presentation profiles must never mutate report-mode hard limits. Callers may
    use this as a guardrail before applying list limits.
    """
    # Touch profile only to normalize/validate; never branch on it for limits.
    normalize_research_presentation_profile(profile)
    return mode_limits


__all__ = [
    "PROFILE_CONSERVATIVE",
    "PROFILE_BALANCED",
    "PROFILE_AGGRESSIVE",
    "VALID_RESEARCH_PRESENTATION_PROFILES",
    "INTEL_BLOCK_KEYS",
    "STRATA_BLOCK_KEYS",
    "normalize_research_presentation_profile",
    "resolve_research_presentation_profile",
    "get_presentation_plan",
    "should_emit_framing_notice",
    "profile_framing_notice",
    "risk_content_fingerprint",
    "assert_profile_does_not_change_limits",
]
