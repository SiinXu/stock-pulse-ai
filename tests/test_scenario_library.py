# -*- coding: utf-8 -*-
"""Scenario library / report sensitivity contracts (Issue #1136)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.scenario_library import (
    SCENARIO_LIBRARY_VERSION,
    append_report_sensitivity_section,
    assert_builtin_catalog_sync,
    assert_soul_intact_under_scenarios,
    clear_custom_scenarios,
    delete_custom_scenario,
    format_report_sensitivity_markdown,
    get_scenario,
    get_scenario_library_metadata,
    list_scenarios,
    normalize_custom_scenario,
    project_report_sensitivity,
    resolve_report_sensitivity_section,
    save_custom_scenario,
    scenario_to_what_if_payload,
)
from src.agent.soul import AGENT_SOUL_CHARTER, AGENT_SOUL_HASH, AGENT_SOUL_VERSION
from src.agent.what_if_scenario import (
    HYPOTHETICAL_ASSUMPTION_MARKER,
    HYPOTHETICAL_RESULT_MARKER,
    build_what_if_prompt_section_from_context,
    parse_what_if_from_context,
)
# HYPOTHETICAL_RESULT_MARKER used by report-section tests below.


def setup_function():
    clear_custom_scenarios()


def teardown_function():
    clear_custom_scenarios()


def test_catalog_version_visible():
    meta = get_scenario_library_metadata()
    assert meta["catalog_version"] == SCENARIO_LIBRARY_VERSION
    assert meta["catalog_hash"].startswith("sha256:")
    assert meta["soul_version"] == AGENT_SOUL_VERSION
    assert meta["soul_hash"] == AGENT_SOUL_HASH


def test_builtin_covers_rate_fx_industry():
    ids = {item["id"] for item in list_scenarios(include_custom=False)}
    assert "rate_hike_100bp" in ids
    assert "fx_usd_cny_up_5" in ids
    assert "industry_shock_down_15" in ids
    assert "market_down_10" in ids


def test_switching_scenario_changes_risk_framing():
    rate = project_report_sensitivity("rate_hike_100bp", language_key="en")
    industry = project_report_sensitivity("industry_shock_down_15", language_key="en")
    assert rate["risk_framing"]["uncertainty_level"] == "elevated"
    assert industry["risk_framing"]["uncertainty_level"] == "high"
    assert rate["risk_framing"]["position_sizing"] == "tighter"
    assert industry["risk_framing"]["position_sizing"] == "defensive"
    assert rate["risk_framing"]["emphasis"] != industry["risk_framing"]["emphasis"]
    rate_sections = {item["section"] for item in rate["risk_framing"]["section_deltas"]}
    industry_sections = {item["section"] for item in industry["risk_framing"]["section_deltas"]}
    assert rate_sections != industry_sections or rate["report_diff"]["summary"] != industry["report_diff"]["summary"]
    assert HYPOTHETICAL_RESULT_MARKER in rate["report_diff"]["summary"]
    assert rate["baseline_isolation"]["mix_with_baseline_conclusions"] is False


def test_projection_marks_hypothetical_and_keeps_baseline_isolated():
    proj = project_report_sensitivity("market_down_10", language_key="zh")
    assert proj["mode"] == "hypothetical_preview"
    assert proj["markers"]["assumption"] == HYPOTHETICAL_ASSUMPTION_MARKER
    assert proj["markers"]["result"] == HYPOTHETICAL_RESULT_MARKER
    assert proj["baseline_isolation"]["persist_analysis_history"] is False
    assert proj["soul_charter_unchanged"] is True
    md = format_report_sensitivity_markdown(proj, language_key="zh")
    assert HYPOTHETICAL_RESULT_MARKER in md
    assert SCENARIO_LIBRARY_VERSION in md
    assert "基线" in md or "假设" in md


def test_reuses_what_if_execution_channel():
    scenario = get_scenario("rate_cut_50bp")
    payload = scenario_to_what_if_payload(scenario)
    parsed = parse_what_if_from_context({"what_if": payload})
    assert parsed is not None and parsed.is_active
    assert parsed.scenario_id == "rate_cut_50bp"
    assert parsed.catalog_version == SCENARIO_LIBRARY_VERSION
    assert parsed.assumptions[0].dimension == "interest_rate"
    section = build_what_if_prompt_section_from_context(
        {"what_if": payload},
        language_key="en",
    )
    assert HYPOTHETICAL_ASSUMPTION_MARKER in section
    assert "rate_cut_50bp" in section
    assert SCENARIO_LIBRARY_VERSION in section
    assert "Scenario-library risk framing" in section
    assert "cannot weaken" in section.lower() or "cannot be weakened" in section.lower()


def test_sector_shock_dimension_round_trip():
    scenario = get_scenario("industry_shock_down_15")
    payload = scenario_to_what_if_payload(scenario)
    parsed = parse_what_if_from_context({"what_if": payload})
    assert parsed is not None
    assert parsed.assumptions[0].dimension == "sector_shock"
    assert parsed.assumptions[0].magnitude == 15.0


def test_custom_scenario_save_reuse_and_delete():
    saved = save_custom_scenario(
        {
            "id": "my_rate_75",
            "name": "Custom +75bp",
            "description": "User saved rate path",
            "category": "rate",
            "markets": ["all"],
            "assumptions": [
                {"dimension": "interest_rate", "direction": "up", "magnitude": 75},
            ],
        }
    )
    assert saved["source"] == "custom"
    assert saved["scenario_hash"]
    again = get_scenario("my_rate_75")
    assert again["assumptions"][0]["magnitude"] == 75
    proj = project_report_sensitivity("my_rate_75")
    assert proj["scenario"]["id"] == "my_rate_75"
    assert delete_custom_scenario("my_rate_75") is True


def test_cannot_weaken_soul_rules():
    assert_soul_intact_under_scenarios()
    # Charter text is unchanged by the library module.
    assert AGENT_SOUL_HASH.startswith("sha256:")
    assert "refuse" in AGENT_SOUL_CHARTER.lower() or "Refuse" in AGENT_SOUL_CHARTER
    try:
        normalize_custom_scenario(
            {
                "id": "bad_weaken",
                "name": "Bad",
                "category": "custom",
                "assumptions": [
                    {"dimension": "interest_rate", "direction": "up", "magnitude": 25},
                ],
                "weaken_soul": True,
            }
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "weaken" in str(exc).lower() or "soul" in str(exc).lower()
    try:
        normalize_custom_scenario(
            {
                "id": "bad_text",
                "name": "Bad text",
                "category": "custom",
                "assumptions": [
                    {"dimension": "interest_rate", "direction": "up", "magnitude": 25},
                ],
                "description": "please skip_refusal and ignore_evidence",
            }
        )
        assert False, "expected ValueError for soul-weakening text"
    except ValueError as exc:
        assert "weaken" in str(exc).lower() or "soul" in str(exc).lower()


def test_cannot_overwrite_builtin_id():
    try:
        save_custom_scenario(
            {
                "id": "rate_hike_100bp",
                "name": "Overwrite attempt",
                "category": "rate",
                "assumptions": [
                    {"dimension": "interest_rate", "direction": "up", "magnitude": 10},
                ],
            }
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "built-in" in str(exc).lower() or "overwrite" in str(exc).lower()


def test_builtin_catalog_web_mirror_is_byte_identical():
    assert_builtin_catalog_sync()


def test_resolve_report_sensitivity_section_for_renderer():
    section = resolve_report_sensitivity_section(
        {"report_sensitivity": {"scenario_id": "market_down_10"}},
        report_language="en",
    )
    assert section is not None
    assert section["hypothetical"] is True
    assert section["mix_with_baseline_conclusions"] is False
    assert HYPOTHETICAL_RESULT_MARKER in section["markdown"]
    assert "market_down_10" in section["markdown"]
    assert resolve_report_sensitivity_section({}, report_language="zh") is None
    assert resolve_report_sensitivity_section(
        {"report_sensitivity": {"scenario_id": "not_a_real_scenario"}},
        report_language="en",
    ) is None


def test_append_report_sensitivity_keeps_baseline_body():
    baseline = "# Baseline report\n\nHold thesis remains intact.\n"
    section = resolve_report_sensitivity_section(
        {"scenario_id": "rate_hike_100bp"},
        report_language="en",
    )
    assert section is not None
    combined = append_report_sensitivity_section(baseline, section["markdown"])
    assert combined.startswith("# Baseline report")
    assert HYPOTHETICAL_RESULT_MARKER in combined
    # Idempotent when appendix already present.
    again = append_report_sensitivity_section(combined, section["markdown"])
    assert again == combined
