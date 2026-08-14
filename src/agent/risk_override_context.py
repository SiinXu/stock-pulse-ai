# -*- coding: utf-8 -*-
"""Risk-exit context helpers, including info-quality grade C evidence.

Extracted from ``risk_override`` so that module stays under the hot-path
size budget. Public callers continue to import ``build_risk_context_for_exit``
from ``src.agent.risk_override``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Dict, List, Mapping, MutableSequence, Optional, Tuple

from src.agent.protocols import AgentContext

INFO_QUALITY_GRADE_C = "C"
INFO_QUALITY_SCHEMA_V1 = "info-quality-v1"
INFO_QUALITY_GRADE_C_CODE = "info_quality_grade_c"


def is_stale_risk_evidence(value: str, *, maximum_age_hours: int = 24) -> bool:
    """Return whether a valid risk-evidence timestamp is older than the limit."""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - parsed.astimezone(timezone.utc) > timedelta(
        hours=maximum_age_hours
    )


def dashboard_risk_sources(
    dashboard: Optional[Mapping[str, Any]],
) -> Tuple[Mapping[str, Any], ...]:
    if not isinstance(dashboard, Mapping):
        return ()
    sources: List[Mapping[str, Any]] = [dashboard]
    for key in ("risk", "risk_assessment", "risk_manager_input"):
        value = dashboard.get(key)
        if isinstance(value, Mapping):
            sources.append(value)
    nested = dashboard.get("dashboard")
    if isinstance(nested, Mapping):
        sources.append(nested)
        for key in ("risk", "risk_assessment", "risk_manager_input"):
            value = nested.get(key)
            if isinstance(value, Mapping):
                sources.append(value)
    return tuple(sources)


def bounded_confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not isfinite(parsed):
        return 0.0
    return max(0.0, min(1.0, parsed))


def apply_info_quality_risk_evidence(
    ctx: AgentContext,
    dashboard: Optional[Mapping[str, Any]],
    raw: Dict[str, Any],
    *,
    enabled: bool,
) -> Dict[str, Any]:
    """Attach trusted info-quality-v1 grade C as deterministic risk evidence."""
    if type(enabled) is not bool:
        raise TypeError("info_quality_risk_enabled must be bool")
    info_quality = (
        dashboard.get("info_quality") if isinstance(dashboard, Mapping) else None
    )
    grade = ""
    schema_version = ""
    if isinstance(info_quality, Mapping):
        grade = str(info_quality.get("grade") or "").strip().upper()
        schema_version = str(info_quality.get("schema_version") or "").strip()
    if not (
        enabled
        and grade == INFO_QUALITY_GRADE_C
        and schema_version == INFO_QUALITY_SCHEMA_V1
    ):
        return raw
    ctx.set_data("info_quality_grade", INFO_QUALITY_GRADE_C)
    ctx.add_risk_flag(
        "info_quality",
        "information quality grade C",
        severity="high",
    )
    merged = dict(raw)
    if "signal_adjustment" not in merged:
        merged["signal_adjustment"] = "buy_to_hold"
    if "risk_level" not in merged:
        merged["risk_level"] = "high"
    return merged


def append_info_quality_gate_evidence(
    ctx: AgentContext,
    codes: MutableSequence[str],
    reasons: MutableSequence[str],
) -> None:
    """Record grade C as a stable Risk Manager evidence/reason code."""
    if str(ctx.get_data("info_quality_grade") or "").strip().upper() == INFO_QUALITY_GRADE_C:
        codes.append(INFO_QUALITY_GRADE_C_CODE)
        reasons.append(INFO_QUALITY_GRADE_C_CODE)
