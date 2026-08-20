# -*- coding: utf-8 -*-
"""Honesty contract for optional report-compare sections (issue #188 / T18)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.services.report_version_compare_optional_sections import (
    SECTION_CATALYSTS,
    SECTION_MULTI_AGENT,
    SECTION_STRUCTURED_RISK,
    STATUS_BASE_MISSING,
    STATUS_BOTH_MISSING,
    STATUS_PRESENT_DIFFERENT,
    STATUS_PRESENT_IDENTICAL,
    STATUS_TARGET_MISSING,
    build_optional_sections,
)


def _payload(
    *,
    catalysts: Optional[Any] = None,
    include_catalysts: bool = False,
    risk_alerts: Optional[Any] = None,
    include_risk_alerts: bool = False,
    risks_counter_evidence: Optional[Any] = None,
    include_risks: bool = False,
    debate: Optional[Any] = None,
    include_debate: bool = False,
    committee: Optional[Any] = None,
    include_committee: bool = False,
) -> Dict[str, Any]:
    intelligence: Dict[str, Any] = {}
    if include_catalysts:
        intelligence["positive_catalysts"] = catalysts
    if include_risk_alerts:
        intelligence["risk_alerts"] = risk_alerts
    strata: Dict[str, Any] = {}
    if include_risks:
        strata["risks_counter_evidence"] = risks_counter_evidence
    dashboard: Dict[str, Any] = {}
    if intelligence:
        dashboard["intelligence"] = intelligence
    if strata:
        dashboard["report_strata"] = strata
    if include_debate:
        dashboard["bull_bear_debate"] = debate
    if include_committee:
        dashboard["committee_deliberation"] = committee
    return {"dashboard": dashboard} if dashboard else {}


OPTIONAL_SECTIONS_UNDER_TEST = (
    SECTION_CATALYSTS,
    SECTION_STRUCTURED_RISK,
    SECTION_MULTI_AGENT,
)


def _by_section(rows):
    mapped = {row["section"]: row for row in rows}
    assert set(mapped) == set(OPTIONAL_SECTIONS_UNDER_TEST)
    return mapped


def test_both_missing_is_not_identical_empty_parity() -> None:
    rows = _by_section(build_optional_sections({}, {"action": "buy"}))
    for section in OPTIONAL_SECTIONS_UNDER_TEST:
        row = rows[section]
        assert row["comparison_status"] == STATUS_BOTH_MISSING
        assert row["base_present"] is False
        assert row["target_present"] is False
        assert row["base_preview"] == []
        assert row["target_preview"] == []


def test_left_missing_catalysts_does_not_collapse_into_added_items() -> None:
    rows = _by_section(
        build_optional_sections(
            {},
            _payload(include_catalysts=True, catalysts=["Export recovery"]),
        )
    )
    row = rows[SECTION_CATALYSTS]
    assert row["comparison_status"] == STATUS_BASE_MISSING
    assert row["base_present"] is False
    assert row["target_present"] is True
    assert row["target_item_count"] == 1
    assert row["target_preview"] == ["Export recovery"]
    assert rows[SECTION_STRUCTURED_RISK]["comparison_status"] == STATUS_BOTH_MISSING


def test_right_missing_structured_risk_is_explicit() -> None:
    rows = _by_section(
        build_optional_sections(
            _payload(
                include_risk_alerts=True,
                risk_alerts=["Valuation elevated"],
                include_risks=True,
                risks_counter_evidence=["Elevated PE"],
            ),
            {"dashboard": {}},
        )
    )
    row = rows[SECTION_STRUCTURED_RISK]
    assert row["comparison_status"] == STATUS_TARGET_MISSING
    assert row["base_present"] is True
    assert row["target_present"] is False
    assert "Valuation elevated" in row["base_preview"]
    assert "Elevated PE" in row["base_preview"]
    assert row["target_preview"] == []


def test_present_empty_list_is_not_missing() -> None:
    rows = _by_section(
        build_optional_sections(
            _payload(include_catalysts=True, catalysts=[]),
            {},
        )
    )
    row = rows[SECTION_CATALYSTS]
    assert row["base_present"] is True
    assert row["target_present"] is False
    assert row["comparison_status"] == STATUS_TARGET_MISSING
    assert row["base_item_count"] == 0


def test_present_but_different_catalysts_and_risks() -> None:
    rows = _by_section(
        build_optional_sections(
            _payload(
                include_catalysts=True,
                catalysts=["Quarterly update clean"],
                include_risk_alerts=True,
                risk_alerts=["Valuation elevated"],
            ),
            _payload(
                include_catalysts=True,
                catalysts=["Quarterly update clean", "Export recovery"],
                include_risk_alerts=True,
                risk_alerts=["Liquidity risk"],
            ),
        )
    )
    catalysts = rows[SECTION_CATALYSTS]
    assert catalysts["comparison_status"] == STATUS_PRESENT_DIFFERENT
    assert catalysts["base_present"] is True
    assert catalysts["target_present"] is True
    assert catalysts["base_preview"] == ["Quarterly update clean"]
    assert "Export recovery" in catalysts["target_preview"]

    risk = rows[SECTION_STRUCTURED_RISK]
    assert risk["comparison_status"] == STATUS_PRESENT_DIFFERENT
    assert risk["base_preview"] == ["Valuation elevated"]
    assert risk["target_preview"] == ["Liquidity risk"]


def test_present_identical_does_not_hide_the_section() -> None:
    payload = _payload(
        include_catalysts=True,
        catalysts=["Quarterly update clean"],
        include_risks=True,
        risks_counter_evidence=["Elevated PE"],
        include_debate=True,
        debate={"status": "complete", "winner": "bull"},
    )
    rows = _by_section(build_optional_sections(payload, payload))
    assert rows[SECTION_CATALYSTS]["comparison_status"] == STATUS_PRESENT_IDENTICAL
    assert rows[SECTION_STRUCTURED_RISK]["comparison_status"] == STATUS_PRESENT_IDENTICAL
    assert rows[SECTION_MULTI_AGENT]["comparison_status"] == STATUS_PRESENT_IDENTICAL
    assert rows[SECTION_MULTI_AGENT]["base_preview"] == ["bull_bear_debate"]


def test_multi_agent_left_missing_and_present_different() -> None:
    missing = _by_section(
        build_optional_sections(
            {},
            _payload(include_debate=True, debate={"status": "complete"}),
        )
    )
    assert missing[SECTION_MULTI_AGENT]["comparison_status"] == STATUS_BASE_MISSING
    assert missing[SECTION_MULTI_AGENT]["target_preview"] == ["bull_bear_debate"]

    different = _by_section(
        build_optional_sections(
            _payload(include_debate=True, debate={"status": "complete", "winner": "bull"}),
            _payload(
                include_debate=True,
                debate={"status": "complete", "winner": "bear"},
                include_committee=True,
                committee={"status": "resolved"},
            ),
        )
    )
    row = different[SECTION_MULTI_AGENT]
    assert row["comparison_status"] == STATUS_PRESENT_DIFFERENT
    assert row["base_preview"] == ["bull_bear_debate"]
    assert row["target_preview"] == ["bull_bear_debate", "committee_deliberation"]


def test_mandatory_risk_manager_gate_does_not_mark_multi_agent_present() -> None:
    """Ordinary orchestrator runs persist dashboard.risk_manager without debate."""
    base = {
        "dashboard": {
            "risk_manager": {
                "schema_version": "risk-manager-result/v1",
                "final_action": "hold",
                "evaluation_id": "a" * 32,
            }
        }
    }
    target = {
        "dashboard": {
            "risk_manager": {
                "schema_version": "risk-manager-result/v1",
                "final_action": "buy",
                "evaluation_id": "b" * 32,
            }
        }
    }
    rows = _by_section(build_optional_sections(base, target))
    row = rows[SECTION_MULTI_AGENT]
    assert row["comparison_status"] == STATUS_BOTH_MISSING
    assert row["base_present"] is False
    assert row["target_present"] is False
    assert row["base_preview"] == []
    assert row["target_preview"] == []


def test_risk_manager_trace_does_not_change_multi_agent_fingerprint() -> None:
    debate = {"status": "complete", "winner": "bull"}
    rows = _by_section(
        build_optional_sections(
            {
                "dashboard": {
                    "bull_bear_debate": debate,
                    "risk_manager": {"final_action": "hold"},
                }
            },
            {
                "dashboard": {
                    "bull_bear_debate": debate,
                    "risk_manager": {"final_action": "buy"},
                }
            },
        )
    )
    row = rows[SECTION_MULTI_AGENT]
    assert row["comparison_status"] == STATUS_PRESENT_IDENTICAL
    assert row["base_preview"] == ["bull_bear_debate"]
    assert row["target_preview"] == ["bull_bear_debate"]


def test_key_presence_none_is_still_produced() -> None:
    rows = _by_section(
        build_optional_sections(
            _payload(include_catalysts=True, catalysts=None),
            _payload(include_risk_alerts=True, risk_alerts=None),
        )
    )
    assert rows[SECTION_CATALYSTS]["base_present"] is True
    assert rows[SECTION_CATALYSTS]["comparison_status"] == STATUS_TARGET_MISSING
    assert rows[SECTION_STRUCTURED_RISK]["target_present"] is True
    assert rows[SECTION_STRUCTURED_RISK]["comparison_status"] == STATUS_BASE_MISSING
