# -*- coding: utf-8 -*-
"""Versioned scenario library for report sensitivity (Issue #1136).

Reusable scenarios (rate / FX / industry / market) map onto the existing Chat
what-if execution channel. Risk framing projection is deterministic so tests
can assert that switching scenarios changes expected risk emphasis without
touching the Agent Soul charter.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.agent.soul import AGENT_SOUL_CHARTER, AGENT_SOUL_HASH, AGENT_SOUL_VERSION
from src.agent.what_if_scenario import (
    DEFAULT_WHAT_IF_MAX_TURNS,
    HYPOTHETICAL_ASSUMPTION_MARKER,
    HYPOTHETICAL_RESULT_MARKER,
    PREVIEW_DISCLAIMER_EN,
    PREVIEW_DISCLAIMER_ZH,
    WHAT_IF_CONTEXT_KEY,
    WhatIfAssumption,
    WhatIfScenario,
)

SCENARIO_LIBRARY_VERSION = "1.0.0"
SCENARIO_LIBRARY_SCHEMA_VERSION = 1
REPORT_SENSITIVITY_CONTEXT_KEY = "report_sensitivity"

CATEGORIES = frozenset({"rate", "fx", "industry", "market", "custom"})
MARKETS = frozenset({"cn", "hk", "us", "all"})
UNCERTAINTY_LEVELS = ("baseline", "elevated", "high")
POSITION_SIZING = ("unchanged", "tighter", "defensive")
RISK_SECTION_KEYS = frozenset(
    {
        "risks_counter_evidence",
        "risk_warning",
        "risk_control",
        "invalidation",
        "time_sensitivity",
    }
)
# Fields that would attempt to weaken Soul evidence / refusal / risk rules.
_SOUL_WEAKEN_KEYS = frozenset(
    {
        "weaken_soul",
        "skip_refusal",
        "ignore_evidence",
        "bypass_soul",
        "disable_refusal",
        "fabricate_evidence",
        "guarantee_returns",
        "override_soul",
        "soul_override",
    }
)
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_MAX_CUSTOM = 32
_MAX_NAME = 120
_MAX_DESC = 500
_MAX_ASSUMPTIONS = 8
_MAX_TIGHTENING = 12
_MAX_EMPHASIS = 12

_custom_lock = threading.RLock()
_custom_scenarios: Dict[str, Dict[str, Any]] = {}


@dataclass(frozen=True)
class RiskFraming:
    """Deterministic risk-emphasis projection for report sensitivity."""

    uncertainty_level: str
    position_sizing: str
    emphasis: Tuple[str, ...]
    tighter_constraints: Tuple[str, ...]
    section_deltas: Tuple[Dict[str, str], ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uncertainty_level": self.uncertainty_level,
            "position_sizing": self.position_sizing,
            "emphasis": list(self.emphasis),
            "tighter_constraints": list(self.tighter_constraints),
            "section_deltas": [dict(item) for item in self.section_deltas],
        }


@dataclass(frozen=True)
class LibraryScenario:
    id: str
    name: str
    description: str
    category: str
    markets: Tuple[str, ...]
    assumptions: Tuple[WhatIfAssumption, ...]
    risk_framing: RiskFraming
    source: str = "built_in"
    version: int = 1

    @property
    def scenario_hash(self) -> str:
        payload = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "markets": list(self.markets),
            "assumptions": [_assumption_dict(a) for a in self.assumptions],
            "risk_framing": self.risk_framing.to_dict(),
            "source": self.source,
            "version": self.version,
        }
        canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "markets": list(self.markets),
            "assumptions": [_assumption_dict(a) for a in self.assumptions],
            "risk_framing": self.risk_framing.to_dict(),
            "source": self.source,
            "version": self.version,
            "scenario_hash": self.scenario_hash,
        }


def _assumption_dict(a: WhatIfAssumption) -> Dict[str, Any]:
    out: Dict[str, Any] = {"dimension": a.dimension}
    if a.direction is not None:
        out["direction"] = a.direction
    if a.magnitude is not None:
        out["magnitude"] = a.magnitude
    if a.currency_pair is not None:
        out["currency_pair"] = a.currency_pair
    if a.label is not None:
        out["label"] = a.label
    return out


def _rf(
    *,
    uncertainty: str,
    sizing: str,
    emphasis: Sequence[str],
    tighter: Sequence[str],
    sections: Sequence[Tuple[str, str, str]],
) -> RiskFraming:
    if uncertainty not in UNCERTAINTY_LEVELS:
        raise ValueError(f"invalid uncertainty_level '{uncertainty}'")
    if sizing not in POSITION_SIZING:
        raise ValueError(f"invalid position_sizing '{sizing}'")
    deltas = tuple(
        {"section": section, "direction": direction, "note": note}
        for section, direction, note in sections
    )
    for item in deltas:
        if item["section"] not in RISK_SECTION_KEYS:
            raise ValueError(f"unsupported risk section '{item['section']}'")
        if item["direction"] not in {"elevated", "tightened", "accelerated"}:
            raise ValueError(f"invalid section delta direction '{item['direction']}'")
    return RiskFraming(
        uncertainty_level=uncertainty,
        position_sizing=sizing,
        emphasis=tuple(emphasis),
        tighter_constraints=tuple(tighter),
        section_deltas=deltas,
    )


_BUILTIN: Tuple[LibraryScenario, ...] = (
    LibraryScenario(
        id="rate_hike_100bp",
        name="Policy rates +100bp",
        description="Parallel policy-rate hike of 100 basis points.",
        category="rate",
        markets=("all",),
        assumptions=(WhatIfAssumption(dimension="interest_rate", direction="up", magnitude=100.0),),
        risk_framing=_rf(
            uncertainty="elevated",
            sizing="tighter",
            emphasis=(
                "discount_rate_pressure",
                "duration_and_leverage_sensitivity",
                "funding_cost_upside",
            ),
            tighter=(
                "Require explicit funding-cost and multiple-compression checks before any bullish sizing.",
                "Do not soften invalidation levels solely because the baseline thesis remains intact.",
            ),
            sections=(
                ("risks_counter_evidence", "elevated", "Surface rate-driven downside and valuation compression."),
                ("risk_control", "tightened", "Prefer smaller size and stricter invalidation under higher rates."),
                ("invalidation", "elevated", "Call out rate-path breaks that invalidate the baseline case."),
            ),
        ),
    ),
    LibraryScenario(
        id="rate_cut_50bp",
        name="Policy rates -50bp",
        description="Parallel policy-rate cut of 50 basis points.",
        category="rate",
        markets=("all",),
        assumptions=(WhatIfAssumption(dimension="interest_rate", direction="down", magnitude=50.0),),
        risk_framing=_rf(
            uncertainty="elevated",
            sizing="unchanged",
            emphasis=(
                "easing_is_not_risk_free",
                "growth_reacceleration_vs_policy_lag",
                "still_separate_hypothesis_from_observation",
            ),
            tighter=(
                "Do not present rate cuts as guaranteed upside; keep downside and lag risks explicit.",
            ),
            sections=(
                ("risks_counter_evidence", "elevated", "Keep lag, transmission, and false-break risks visible."),
                ("risk_warning", "elevated", "Mark easing benefits as hypothetical, not observed facts."),
            ),
        ),
    ),
    LibraryScenario(
        id="fx_usd_cny_up_5",
        name="USD/CNY +5%",
        description="USD strengthens 5% versus CNY (USD/CNY up).",
        category="fx",
        markets=("cn", "hk", "us"),
        assumptions=(
            WhatIfAssumption(
                dimension="fx_rate",
                direction="up",
                magnitude=5.0,
                currency_pair="USD/CNY",
            ),
        ),
        risk_framing=_rf(
            uncertainty="elevated",
            sizing="tighter",
            emphasis=(
                "import_cost_and_margin_pressure",
                "fx_translation_on_offshore_earnings",
                "capital_flow_sensitivity",
            ),
            tighter=(
                "Call out FX exposure and margin translation before upgrading confidence.",
            ),
            sections=(
                ("risks_counter_evidence", "elevated", "Emphasize FX drag on importers and CNY earners."),
                ("risk_control", "tightened", "Reduce size when FX exposure is material and unhedged."),
            ),
        ),
    ),
    LibraryScenario(
        id="fx_usd_cny_down_5",
        name="USD/CNY -5%",
        description="USD weakens 5% versus CNY (USD/CNY down).",
        category="fx",
        markets=("cn", "hk", "us"),
        assumptions=(
            WhatIfAssumption(
                dimension="fx_rate",
                direction="down",
                magnitude=5.0,
                currency_pair="USD/CNY",
            ),
        ),
        risk_framing=_rf(
            uncertainty="elevated",
            sizing="unchanged",
            emphasis=(
                "export_competitiveness_shift",
                "fx_is_hypothetical_not_print",
                "hedge_and_pass_through_uncertainty",
            ),
            tighter=(
                "Do not treat a weaker USD as confirmed bullish evidence for all exporters.",
            ),
            sections=(
                ("risks_counter_evidence", "elevated", "Keep demand elasticity and lag effects in view."),
                ("risk_warning", "elevated", "Label FX path as scenario-only."),
            ),
        ),
    ),
    LibraryScenario(
        id="industry_shock_down_15",
        name="Industry shock -15%",
        description="Sector / industry factor shock of -15% (parameterized label).",
        category="industry",
        markets=("all",),
        assumptions=(
            WhatIfAssumption(
                dimension="sector_shock",
                direction="down",
                magnitude=15.0,
                label="Target industry / sector instantaneous -15%",
            ),
        ),
        risk_framing=_rf(
            uncertainty="high",
            sizing="defensive",
            emphasis=(
                "sector_beta_and_peer_contagion",
                "crowding_and_liquidity_gap",
                "thesis_invalidation_speed",
            ),
            tighter=(
                "Treat industry shock as elevating peer and liquidity risk; prefer defensive sizing.",
                "Do not drop refusal or evidence rules to keep a bullish narrative alive.",
            ),
            sections=(
                ("risks_counter_evidence", "elevated", "Lead with sector contagion and peer drawdown."),
                ("risk_control", "tightened", "Defensive size and faster invalidation under sector stress."),
                ("time_sensitivity", "accelerated", "Shorten reaction window while the shock path is open."),
                ("invalidation", "elevated", "Make sector-level breaks first-class invalidation inputs."),
            ),
        ),
    ),
    LibraryScenario(
        id="market_down_10",
        name="Broad market -10%",
        description="Broad equity index instantaneous move of -10%.",
        category="market",
        markets=("all",),
        assumptions=(WhatIfAssumption(dimension="index_move", direction="down", magnitude=10.0),),
        risk_framing=_rf(
            uncertainty="high",
            sizing="defensive",
            emphasis=(
                "beta_and_correlation_spike",
                "liquidity_and_gap_risk",
                "preserve_downside_first_framing",
            ),
            tighter=(
                "Under a market-down path, keep downside and liquidity risk ahead of opportunity framing.",
            ),
            sections=(
                ("risks_counter_evidence", "elevated", "Prioritize market-beta and gap risk."),
                ("risk_control", "tightened", "Defensive posture until the hypothetical path is closed."),
                ("time_sensitivity", "accelerated", "Faster review cadence while the drawdown path is active."),
            ),
        ),
    ),
)


def get_scenario_library_metadata() -> Dict[str, str]:
    """Return catalog version identity (visible to clients and reports)."""
    digest = hashlib.sha256()
    for item in _BUILTIN:
        digest.update(item.scenario_hash.encode("utf-8"))
    digest.update(SCENARIO_LIBRARY_VERSION.encode("utf-8"))
    return {
        "catalog_version": SCENARIO_LIBRARY_VERSION,
        "schema_version": str(SCENARIO_LIBRARY_SCHEMA_VERSION),
        "catalog_hash": "sha256:" + digest.hexdigest(),
        "soul_version": AGENT_SOUL_VERSION,
        "soul_hash": AGENT_SOUL_HASH,
    }


def list_builtin_scenarios() -> List[Dict[str, Any]]:
    return [item.to_dict() for item in _BUILTIN]


def list_custom_scenarios() -> List[Dict[str, Any]]:
    with _custom_lock:
        return [deepcopy(item) for item in sorted(_custom_scenarios.values(), key=lambda x: x["id"])]


def list_scenarios(*, include_custom: bool = True) -> List[Dict[str, Any]]:
    items = list_builtin_scenarios()
    if include_custom:
        items.extend(list_custom_scenarios())
    return items


def get_scenario(scenario_id: str) -> Dict[str, Any]:
    target = str(scenario_id or "").strip()
    if not target:
        raise ValueError("scenario_id is required")
    for item in _BUILTIN:
        if item.id == target:
            return item.to_dict()
    with _custom_lock:
        if target in _custom_scenarios:
            return deepcopy(_custom_scenarios[target])
    raise ValueError(f"Unknown scenario_id '{target}'")


def _parse_assumption(raw: Mapping[str, Any]) -> WhatIfAssumption:
    # Reuse the what-if parser by wrapping a one-item payload (no private imports).
    from src.agent.what_if_scenario import parse_what_if_from_context

    parsed = parse_what_if_from_context(
        {
            WHAT_IF_CONTEXT_KEY: {
                "enabled": True,
                "assumptions": [raw],
            }
        }
    )
    if parsed is None or not parsed.assumptions:
        raise ValueError("invalid scenario assumption")
    return parsed.assumptions[0]


def _normalize_risk_framing(raw: Any, *, category: str) -> RiskFraming:
    if raw is None:
        # Custom scenarios without framing inherit a conservative default by category.
        defaults = {
            "rate": ("elevated", "tighter"),
            "fx": ("elevated", "tighter"),
            "industry": ("high", "defensive"),
            "market": ("high", "defensive"),
            "custom": ("elevated", "tighter"),
        }
        uncertainty, sizing = defaults.get(category, ("elevated", "tighter"))
        return _rf(
            uncertainty=uncertainty,
            sizing=sizing,
            emphasis=("hypothetical_path_only", "keep_baseline_separate"),
            tighter=(
                "Scenario output is hypothetical; do not merge into baseline conclusions.",
            ),
            sections=(
                ("risk_warning", "elevated", "Label results as hypothetical scenario analysis."),
            ),
        )
    if not isinstance(raw, Mapping):
        raise ValueError("risk_framing must be an object")
    extras = set(raw) - {
        "uncertainty_level",
        "position_sizing",
        "emphasis",
        "tighter_constraints",
        "section_deltas",
    }
    if extras:
        raise ValueError(f"risk_framing contains unsupported fields: {sorted(extras)}")
    uncertainty = str(raw.get("uncertainty_level") or "elevated").strip().lower()
    sizing = str(raw.get("position_sizing") or "tighter").strip().lower()
    emphasis_raw = raw.get("emphasis") or []
    tighter_raw = raw.get("tighter_constraints") or []
    sections_raw = raw.get("section_deltas") or []
    if not isinstance(emphasis_raw, list) or len(emphasis_raw) > _MAX_EMPHASIS:
        raise ValueError("emphasis must be a short list")
    if not isinstance(tighter_raw, list) or len(tighter_raw) > _MAX_TIGHTENING:
        raise ValueError("tighter_constraints must be a short list")
    if not isinstance(sections_raw, list) or len(sections_raw) > _MAX_TIGHTENING:
        raise ValueError("section_deltas must be a short list")
    emphasis = [str(x).strip() for x in emphasis_raw if str(x).strip()]
    tighter = [str(x).strip() for x in tighter_raw if str(x).strip()]
    sections: List[Tuple[str, str, str]] = []
    for item in sections_raw:
        if not isinstance(item, Mapping):
            raise ValueError("each section delta must be an object")
        sections.append(
            (
                str(item.get("section") or "").strip(),
                str(item.get("direction") or "").strip(),
                str(item.get("note") or "").strip()[:200],
            )
        )
    return _rf(
        uncertainty=uncertainty,
        sizing=sizing,
        emphasis=emphasis,
        tighter=tighter,
        sections=sections,
    )


def _assert_no_soul_weakening(payload: Mapping[str, Any]) -> None:
    """Reject payloads that attempt to weaken Soul refusal/evidence rules."""
    lowered_keys = {str(k).strip().lower() for k in payload.keys()}
    bad = lowered_keys & _SOUL_WEAKEN_KEYS
    if bad:
        raise ValueError(f"scenario cannot weaken Soul rules: {sorted(bad)}")
    # Nested text blobs are scanned for explicit weaken directives.
    blob = json.dumps(payload, ensure_ascii=True).lower()
    for key in _SOUL_WEAKEN_KEYS:
        if key.replace("_", " ") in blob or key in blob:
            raise ValueError(f"scenario text attempts to weaken Soul rule '{key}'")
    # Uncertainty/sizing may only stay or tighten relative to baseline.
    framing = payload.get("risk_framing")
    if isinstance(framing, Mapping):
        level = str(framing.get("uncertainty_level") or "elevated").lower()
        if level not in UNCERTAINTY_LEVELS:
            raise ValueError("invalid uncertainty_level")
        # "none" or inventing a looser level is rejected by UNCERTAINTY_LEVELS.
        sizing = str(framing.get("position_sizing") or "tighter").lower()
        if sizing not in POSITION_SIZING:
            raise ValueError("invalid position_sizing")
        # Explicit "looser" / "aggressive_size" aliases are not accepted.
        for banned in ("looser", "aggressive", "ignore_risk", "no_risk"):
            if banned in json.dumps(framing, ensure_ascii=True).lower():
                raise ValueError("scenario risk_framing cannot loosen risk posture")


def normalize_custom_scenario(raw: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("scenario must be an object")
    _assert_no_soul_weakening(raw)
    allowed = {
        "id",
        "name",
        "description",
        "category",
        "markets",
        "assumptions",
        "risk_framing",
    }
    extras = set(raw) - allowed
    if extras:
        raise ValueError(f"scenario contains unsupported fields: {sorted(extras)}")
    scenario_id = str(raw.get("id") or "").strip().lower()
    if not _ID_RE.match(scenario_id):
        raise ValueError("scenario id must match ^[a-z][a-z0-9_]{1,63}$")
    if any(item.id == scenario_id for item in _BUILTIN):
        raise ValueError("cannot overwrite a built-in scenario id")
    name = str(raw.get("name") or scenario_id).strip()
    if not name or len(name) > _MAX_NAME:
        raise ValueError("scenario name is invalid")
    description = str(raw.get("description") or "").strip()
    if len(description) > _MAX_DESC:
        raise ValueError("scenario description is too long")
    category = str(raw.get("category") or "custom").strip().lower()
    if category not in CATEGORIES:
        raise ValueError("scenario category is invalid")
    markets_raw = raw.get("markets") or ["all"]
    if not isinstance(markets_raw, list) or not markets_raw:
        raise ValueError("markets must be a non-empty list")
    markets = tuple(str(m).strip().lower() for m in markets_raw)
    if any(m not in MARKETS for m in markets):
        raise ValueError("markets contains an unsupported code")
    assumptions_raw = raw.get("assumptions")
    if not isinstance(assumptions_raw, list) or not 1 <= len(assumptions_raw) <= _MAX_ASSUMPTIONS:
        raise ValueError(f"assumptions must contain 1-{_MAX_ASSUMPTIONS} items")
    assumptions = tuple(_parse_assumption(item) for item in assumptions_raw)
    framing = _normalize_risk_framing(raw.get("risk_framing"), category=category)
    scenario = LibraryScenario(
        id=scenario_id,
        name=name,
        description=description,
        category=category,
        markets=markets,
        assumptions=assumptions,
        risk_framing=framing,
        source="custom",
        version=1,
    )
    return scenario.to_dict()


def save_custom_scenario(raw: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = normalize_custom_scenario(raw)
    with _custom_lock:
        if normalized["id"] not in _custom_scenarios and len(_custom_scenarios) >= _MAX_CUSTOM:
            raise ValueError(f"custom scenario limit ({_MAX_CUSTOM}) reached")
        _custom_scenarios[normalized["id"]] = deepcopy(normalized)
        return deepcopy(normalized)


def delete_custom_scenario(scenario_id: str) -> bool:
    target = str(scenario_id or "").strip()
    with _custom_lock:
        return _custom_scenarios.pop(target, None) is not None


def clear_custom_scenarios() -> None:
    with _custom_lock:
        _custom_scenarios.clear()


def scenario_to_what_if_payload(
    scenario: Mapping[str, Any],
    *,
    turn_index: int = 1,
    max_turns: int = DEFAULT_WHAT_IF_MAX_TURNS,
) -> Dict[str, Any]:
    """Project a library scenario onto the existing what-if context channel."""
    assumptions = scenario.get("assumptions")
    if not isinstance(assumptions, list) or not assumptions:
        raise ValueError("scenario has no assumptions")
    meta = get_scenario_library_metadata()
    return {
        "enabled": True,
        "turn_index": max(1, int(turn_index)),
        "max_turns": max(1, int(max_turns)),
        "assumptions": assumptions,
        "scenario_id": scenario.get("id"),
        "scenario_hash": scenario.get("scenario_hash"),
        "catalog_version": meta["catalog_version"],
        "catalog_hash": meta["catalog_hash"],
    }


def library_scenario_to_what_if(scenario: Mapping[str, Any]) -> WhatIfScenario:
    payload = scenario_to_what_if_payload(scenario)
    from src.agent.what_if_scenario import parse_what_if_from_context

    parsed = parse_what_if_from_context({WHAT_IF_CONTEXT_KEY: payload})
    if parsed is None:
        raise ValueError("scenario could not be projected onto what-if channel")
    return parsed


def project_report_sensitivity(
    scenario_id: Optional[str] = None,
    *,
    scenario: Optional[Mapping[str, Any]] = None,
    language_key: str = "en",
) -> Dict[str, Any]:
    """Deterministic report-sensitivity projection for a library scenario.

    Results are always marked as hypothetical and never replace baseline
    conclusions. Risk framing changes with the selected scenario so tests can
    assert expected emphasis without invoking an LLM.
    """
    if scenario is None:
        if not scenario_id:
            raise ValueError("scenario_id or scenario is required")
        scenario = get_scenario(scenario_id)
    else:
        # Allow one-shot custom payloads without persisting.
        if "scenario_hash" not in scenario:
            scenario = normalize_custom_scenario(scenario)
        _assert_no_soul_weakening(scenario)

    meta = get_scenario_library_metadata()
    framing = scenario["risk_framing"]
    what_if = scenario_to_what_if_payload(scenario)
    disclaimer = PREVIEW_DISCLAIMER_EN if language_key == "en" else PREVIEW_DISCLAIMER_ZH
    return {
        "schema_version": SCENARIO_LIBRARY_SCHEMA_VERSION,
        "mode": "hypothetical_preview",
        "markers": {
            "assumption": HYPOTHETICAL_ASSUMPTION_MARKER,
            "result": HYPOTHETICAL_RESULT_MARKER,
        },
        "disclaimer": disclaimer,
        "catalog_version": meta["catalog_version"],
        "catalog_hash": meta["catalog_hash"],
        "soul_version": meta["soul_version"],
        "soul_hash": meta["soul_hash"],
        "soul_charter_unchanged": True,
        "scenario": {
            "id": scenario["id"],
            "name": scenario["name"],
            "description": scenario.get("description") or "",
            "category": scenario["category"],
            "markets": scenario.get("markets") or [],
            "source": scenario.get("source") or "built_in",
            "version": scenario.get("version") or 1,
            "scenario_hash": scenario.get("scenario_hash"),
        },
        "assumptions": scenario["assumptions"],
        "what_if": what_if,
        "risk_framing": framing,
        "baseline_isolation": {
            "mix_with_baseline_conclusions": False,
            "persist_analysis_history": False,
            "persist_decision_signal": False,
            "persist_agent_memory": False,
        },
        "report_diff": {
            "sections": list(framing.get("section_deltas") or []),
            "summary": _diff_summary(scenario, framing, language_key=language_key),
        },
    }


def _diff_summary(
    scenario: Mapping[str, Any],
    framing: Mapping[str, Any],
    *,
    language_key: str,
) -> str:
    name = scenario.get("name") or scenario.get("id")
    uncertainty = framing.get("uncertainty_level")
    sizing = framing.get("position_sizing")
    if language_key == "zh":
        return (
            f"{HYPOTHETICAL_RESULT_MARKER} 情景「{name}」下的风险表述："
            f"不确定性={uncertainty}，仓位口径={sizing}。"
            f"仅为假设推演，不得与基线结论混写。"
        )
    return (
        f"{HYPOTHETICAL_RESULT_MARKER} Under scenario '{name}', risk framing is "
        f"uncertainty={uncertainty}, position_sizing={sizing}. "
        f"Hypothetical only; do not mix with baseline conclusions."
    )


def format_report_sensitivity_markdown(projection: Mapping[str, Any], *, language_key: str = "en") -> str:
    """Render a report appendix section for scenario sensitivity (hypothetical)."""
    scenario = projection.get("scenario") or {}
    framing = projection.get("risk_framing") or {}
    marker = HYPOTHETICAL_RESULT_MARKER
    catalog_version = projection.get("catalog_version")
    if language_key == "zh":
        lines = [
            f"## {marker} 报告敏感性情景",
            "",
            f"> {projection.get('disclaimer')}",
            "",
            f"- 情景目录版本：`{catalog_version}`",
            f"- 情景：`{scenario.get('id')}` — {scenario.get('name')}",
            f"- 情景哈希：`{scenario.get('scenario_hash')}`",
            f"- 不确定性：{framing.get('uncertainty_level')}",
            f"- 仓位口径：{framing.get('position_sizing')}",
            "",
            "### 风险表述变化（相对基线）",
        ]
    else:
        lines = [
            f"## {marker} Report sensitivity scenario",
            "",
            f"> {projection.get('disclaimer')}",
            "",
            f"- Catalog version: `{catalog_version}`",
            f"- Scenario: `{scenario.get('id')}` — {scenario.get('name')}",
            f"- Scenario hash: `{scenario.get('scenario_hash')}`",
            f"- Uncertainty: {framing.get('uncertainty_level')}",
            f"- Position sizing: {framing.get('position_sizing')}",
            "",
            "### Risk framing deltas vs baseline",
        ]
    for item in framing.get("section_deltas") or []:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"- **{item.get('section')}** ({item.get('direction')}): {item.get('note')}"
        )
    tighter = framing.get("tighter_constraints") or []
    if tighter:
        lines.append("")
        lines.append("### Tighter constraints" if language_key != "zh" else "### 收紧约束")
        for rule in tighter:
            lines.append(f"- {rule}")
    lines.append("")
    lines.append(str(projection.get("report_diff", {}).get("summary") or ""))
    lines.append("")
    lines.append(
        "Soul refusal/evidence rules remain authoritative and cannot be weakened by this scenario."
        if language_key != "zh"
        else "Soul 拒绝/证据规则仍然优先，情景不得削弱这些规则。"
    )
    return "\n".join(lines)


def assert_soul_intact_under_scenarios() -> None:
    """Hard guard used by tests: scenarios never mutate the Soul charter."""
    # Identity must remain the live Soul module values.
    meta = get_scenario_library_metadata()
    assert meta["soul_version"] == AGENT_SOUL_VERSION
    assert meta["soul_hash"] == AGENT_SOUL_HASH
    assert "Never fabricate" in AGENT_SOUL_CHARTER or "fabricate" in AGENT_SOUL_CHARTER.lower()
    for item in list_scenarios(include_custom=False):
        _assert_no_soul_weakening(item)
        # Framing may only use allowed tighten-oriented sizing values.
        sizing = item["risk_framing"]["position_sizing"]
        assert sizing in POSITION_SIZING
        assert item["risk_framing"]["uncertainty_level"] in UNCERTAINTY_LEVELS


def build_what_if_enrichment_from_library(
    context: Optional[Mapping[str, Any]],
    *,
    language_key: str = "en",
) -> str:
    """Optional prompt appendix when what_if carries a library scenario_id."""
    if not isinstance(context, Mapping):
        return ""
    raw = context.get(WHAT_IF_CONTEXT_KEY)
    if not isinstance(raw, Mapping):
        return ""
    scenario_id = raw.get("scenario_id")
    if not scenario_id:
        return ""
    try:
        projection = project_report_sensitivity(str(scenario_id), language_key=language_key)
    except ValueError:
        return ""
    framing = projection["risk_framing"]
    meta = get_scenario_library_metadata()
    if language_key == "zh":
        lines = [
            "### 情景库风险表述（假设）",
            f"- 目录版本：{meta['catalog_version']}（{meta['catalog_hash'][:18]}…）",
            f"- 情景：{projection['scenario']['id']} / hash={projection['scenario']['scenario_hash'][:12]}…",
            f"- 不确定性：{framing['uncertainty_level']}；仓位口径：{framing['position_sizing']}",
            "- 以下强调仅用于假设推演，不得写入基线结论：",
        ]
    else:
        lines = [
            "### Scenario-library risk framing (hypothetical)",
            f"- Catalog version: {meta['catalog_version']} ({meta['catalog_hash'][:18]}…)",
            f"- Scenario: {projection['scenario']['id']} / hash={projection['scenario']['scenario_hash'][:12]}…",
            f"- Uncertainty: {framing['uncertainty_level']}; position sizing: {framing['position_sizing']}",
            "- Emphasis below is for the hypothetical branch only; never write it as baseline:",
        ]
    for key in framing.get("emphasis") or []:
        lines.append(f"  - {key}")
    for rule in framing.get("tighter_constraints") or []:
        lines.append(f"  - constraint: {rule}")
    lines.append(
        "- Soul evidence/refusal rules stay in force; this scenario cannot weaken them."
        if language_key != "zh"
        else "- Soul 证据/拒绝规则持续生效；本情景不得削弱它们。"
    )
    return "\n".join(lines)


__all__ = [
    "REPORT_SENSITIVITY_CONTEXT_KEY",
    "SCENARIO_LIBRARY_SCHEMA_VERSION",
    "SCENARIO_LIBRARY_VERSION",
    "assert_soul_intact_under_scenarios",
    "build_what_if_enrichment_from_library",
    "clear_custom_scenarios",
    "delete_custom_scenario",
    "format_report_sensitivity_markdown",
    "get_scenario",
    "get_scenario_library_metadata",
    "library_scenario_to_what_if",
    "list_builtin_scenarios",
    "list_custom_scenarios",
    "list_scenarios",
    "normalize_custom_scenario",
    "project_report_sensitivity",
    "save_custom_scenario",
    "scenario_to_what_if_payload",
]
