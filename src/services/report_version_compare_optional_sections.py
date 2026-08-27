# -*- coding: utf-8 -*-
"""Optional-section honesty for report version compare (issue #188 / T18).

T17 list diffs treat a missing optional section as an empty list, so two runs
that never produced catalysts/risk/multi-agent content look identical. T18
surfaces presence independently and must not invent that parity.

This module does not replace ``compare_analyses``; it only classifies whether
optional sections were produced on each selected run.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Sequence, Tuple

SECTION_CATALYSTS = "catalysts"
SECTION_STRUCTURED_RISK = "structured_risk"
SECTION_MULTI_AGENT = "multi_agent"
OPTIONAL_SECTION_IDS: Tuple[str, ...] = (
    SECTION_CATALYSTS,
    SECTION_STRUCTURED_RISK,
    SECTION_MULTI_AGENT,
)

STATUS_BOTH_MISSING = "both_missing"
STATUS_BASE_MISSING = "base_missing"
STATUS_TARGET_MISSING = "target_missing"
STATUS_PRESENT_IDENTICAL = "present_identical"
STATUS_PRESENT_DIFFERENT = "present_different"

MAX_OPTIONAL_SECTION_PREVIEW_ITEMS = 8
MAX_OPTIONAL_SECTION_ITEM_LENGTH = 512

# Additive optional product surfaces only. Orchestrator analysis always writes
# dashboard.risk_manager on the mandatory risk-gate path, so that key must not
# mark multi_agent as produced.
_MULTI_AGENT_KEYS: Tuple[str, ...] = (
    "bull_bear_debate",
    "committee_deliberation",
    "red_team",
)


def build_optional_sections(
    base_raw: Any,
    target_raw: Any,
) -> List[Dict[str, Any]]:
    """Return a stable, always-complete honesty projection for optional sections."""
    base_map = _as_mapping(base_raw)
    target_map = _as_mapping(target_raw)
    return [
        _compare_section(SECTION_CATALYSTS, base_map, target_map),
        _compare_section(SECTION_STRUCTURED_RISK, base_map, target_map),
        _compare_section(SECTION_MULTI_AGENT, base_map, target_map),
    ]


def _compare_section(
    section: str,
    base_raw: Mapping[str, Any],
    target_raw: Mapping[str, Any],
) -> Dict[str, Any]:
    base_present, base_items, base_fingerprint = _inspect_section(section, base_raw)
    target_present, target_items, target_fingerprint = _inspect_section(section, target_raw)
    status = _comparison_status(
        base_present=base_present,
        target_present=target_present,
        base_fingerprint=base_fingerprint,
        target_fingerprint=target_fingerprint,
    )
    return {
        "section": section,
        "base_present": base_present,
        "target_present": target_present,
        "comparison_status": status,
        "base_item_count": len(base_items),
        "target_item_count": len(target_items),
        "base_preview": base_items[:MAX_OPTIONAL_SECTION_PREVIEW_ITEMS],
        "target_preview": target_items[:MAX_OPTIONAL_SECTION_PREVIEW_ITEMS],
    }


def _comparison_status(
    *,
    base_present: bool,
    target_present: bool,
    base_fingerprint: str,
    target_fingerprint: str,
) -> str:
    if not base_present and not target_present:
        return STATUS_BOTH_MISSING
    if not base_present:
        return STATUS_BASE_MISSING
    if not target_present:
        return STATUS_TARGET_MISSING
    if base_fingerprint == target_fingerprint:
        return STATUS_PRESENT_IDENTICAL
    return STATUS_PRESENT_DIFFERENT


def _inspect_section(
    section: str,
    raw: Mapping[str, Any],
) -> Tuple[bool, List[str], str]:
    if section == SECTION_CATALYSTS:
        return _inspect_catalysts(raw)
    if section == SECTION_STRUCTURED_RISK:
        return _inspect_structured_risk(raw)
    return _inspect_multi_agent(raw)


def _inspect_catalysts(raw: Mapping[str, Any]) -> Tuple[bool, List[str], str]:
    dashboard = _dashboard(raw)
    intelligence = _intelligence(raw, dashboard)
    present, value = _first_present(
        (intelligence, "positive_catalysts"),
        (raw, "positive_catalysts"),
        (dashboard, "positive_catalysts"),
    )
    items = _text_items(value) if present else []
    return present, items, _items_fingerprint(items) if present else ""


def _inspect_structured_risk(raw: Mapping[str, Any]) -> Tuple[bool, List[str], str]:
    dashboard = _dashboard(raw)
    intelligence = _intelligence(raw, dashboard)
    strata = _report_strata(raw, dashboard)
    sources = (
        (intelligence, "risk_alerts"),
        (strata, "risks_counter_evidence"),
        (raw, "risk_alerts"),
        (dashboard, "risk_alerts"),
    )
    present = False
    items: List[str] = []
    seen: set[str] = set()
    for container, key in sources:
        if not _has_key(container, key):
            continue
        present = True
        for item in _text_items(container.get(key)):
            if item in seen:
                continue
            seen.add(item)
            items.append(item)
    return present, items, _items_fingerprint(items) if present else ""


def _inspect_multi_agent(raw: Mapping[str, Any]) -> Tuple[bool, List[str], str]:
    dashboard = _dashboard(raw)
    payload: Dict[str, Any] = {}
    labels: List[str] = []
    for key in _MULTI_AGENT_KEYS:
        if not _has_key(dashboard, key):
            continue
        payload[key] = _json_safe_value(dashboard.get(key))
        labels.append(key)
    if not payload:
        return False, [], ""
    return True, labels, _payload_fingerprint(payload)


def _dashboard(raw: Mapping[str, Any]) -> Dict[str, Any]:
    return _as_mapping(raw.get("dashboard"))


def _intelligence(raw: Mapping[str, Any], dashboard: Mapping[str, Any]) -> Dict[str, Any]:
    intelligence = dashboard.get("intelligence")
    if not isinstance(intelligence, Mapping):
        intelligence = raw.get("intelligence")
    return _as_mapping(intelligence)


def _report_strata(raw: Mapping[str, Any], dashboard: Mapping[str, Any]) -> Dict[str, Any]:
    strata = dashboard.get("report_strata")
    if not isinstance(strata, Mapping):
        strata = raw.get("report_strata")
    return _as_mapping(strata)


def _first_present(*sources: Tuple[Mapping[str, Any], str]) -> Tuple[bool, Any]:
    for container, key in sources:
        if _has_key(container, key):
            return True, container.get(key)
    return False, None


def _has_key(container: Mapping[str, Any], key: str) -> bool:
    return isinstance(container, Mapping) and key in container


def _as_mapping(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _text_items(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = _bounded_text(value)
        return [cleaned] if cleaned else []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        out: List[str] = []
        seen: set[str] = set()
        for item in value:
            text = _item_text(item)
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
        return out
    text = _item_text(value)
    return [text] if text else []


def _item_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        statement = (
            value.get("statement")
            or value.get("text")
            or value.get("fact")
            or value.get("summary")
            or value.get("title")
        )
        return _bounded_text(statement)
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return _bounded_text(value)


def _bounded_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if len(text) <= MAX_OPTIONAL_SECTION_ITEM_LENGTH:
        return text
    return text[:MAX_OPTIONAL_SECTION_ITEM_LENGTH]


def _items_fingerprint(items: Sequence[str]) -> str:
    return _payload_fingerprint(sorted(items))


def _payload_fingerprint(value: Any) -> str:
    canonical = json.dumps(
        _json_safe_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe_value(item) for item in value]
    return str(value)
