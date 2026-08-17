# -*- coding: utf-8 -*-
"""Known-answer tests for the portfolio constraint engine (issue #1132).

Numeric feasibility is decided by the deterministic rules engine. Tests call
the real research proposal/scenario wiring layer and do not mock it.
"""

from __future__ import annotations

import unittest

from src.services.portfolio.constraint_scenarios import (
    NOT_BROKER_COMPLIANCE_DISCLAIMER,
    PASSTHROUGH_DISCLAIMER,
    apply_constraints_to_research_assessment,
    evaluate_research_scenario,
    research_proposal_from_assessment,
)
from src.services.portfolio.constraints import (
    LABEL_CONSTRAINT_FEASIBLE,
    LABEL_RESEARCH_ONLY,
    PASSTHROUGH_REASON_NO_CONSTRAINTS,
    ConstraintConfig,
    PortfolioView,
    ProposedAction,
    ResearchProposal,
    check_proposal,
    load_constraint_config,
)


def _allow_fixture() -> dict:
    return {
        "portfolio": {
            "weights_pct": {"AAA": 10.0, "BBB": 15.0},
            "sectors": {"AAA": "Tech", "BBB": "Health"},
            "risk_flags": {},
            "weights_known": True,
        },
        "proposal": {
            "label": "research_add_aaa",
            "actions": [
                {
                    "symbol": "AAA",
                    "action": "buy",
                    "target_weight_pct": 20.0,
                    "sector": "Tech",
                }
            ],
        },
        "config": {
            "max_single_name_weight_pct": 30.0,
            "max_sector_weight_pct": 50.0,
            "blacklist": ["ZZZ"],
            "blocking_risk_flags": ["halt"],
        },
    }


class ConstraintEngineTests(unittest.TestCase):
    def test_unconfigured_is_explicit_passthrough(self) -> None:
        verdict = check_proposal(
            PortfolioView(weights_pct={"AAA": 80.0}),
            ResearchProposal(
                actions=(ProposedAction(symbol="AAA", action="buy", target_weight_pct=90.0),)
            ),
            ConstraintConfig(),
        )
        self.assertTrue(verdict.passthrough)
        self.assertEqual(verdict.passthrough_reason, PASSTHROUGH_REASON_NO_CONSTRAINTS)
        self.assertEqual(verdict.status, "allow")
        self.assertEqual(verdict.label, LABEL_CONSTRAINT_FEASIBLE)

    def test_load_constraint_config_rejects_malformed_values(self) -> None:
        with self.assertRaises(Exception):
            load_constraint_config({"max_single_name_weight_pct": "not-a-number"})

    def test_oversized_symbol_is_input_error(self) -> None:
        with self.assertRaises(Exception):
            ProposedAction(symbol="A" * 33, action="buy", target_weight_pct=10.0).normalized()


class ResearchScenarioWiringTests(unittest.TestCase):
    """Real production entry — evaluate_research_scenario is not mocked."""

    def test_allow_path_is_constraint_feasible_but_not_broker_executable(self) -> None:
        fixture = _allow_fixture()
        result = evaluate_research_scenario(**fixture)
        self.assertEqual(result["status"], "allow")
        self.assertEqual(result["label"], LABEL_CONSTRAINT_FEASIBLE)
        self.assertEqual(result["scenario_label"], LABEL_CONSTRAINT_FEASIBLE)
        self.assertFalse(result["executable"])
        self.assertFalse(result["is_executable_scenario"])
        self.assertFalse(result["auto_execute"])
        self.assertTrue(result["not_broker_compliance"])
        self.assertIn("not broker", result["disclaimer"].lower())
        self.assertEqual(result["findings"], [])

    def test_per_name_cap_rejects_oversized_target(self) -> None:
        fixture = _allow_fixture()
        fixture["proposal"]["actions"][0]["target_weight_pct"] = 40.0
        result = evaluate_research_scenario(**fixture)
        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["label"], LABEL_RESEARCH_ONLY)
        self.assertFalse(result["executable"])
        codes = [item["constraint"] for item in result["findings"]]
        self.assertIn("per_name_cap", codes)

    def test_sector_cap_rejects_projected_overweight(self) -> None:
        result = evaluate_research_scenario(
            portfolio={
                "weights_pct": {"AAA": 20.0, "BBB": 20.0},
                "sectors": {"AAA": "Tech", "BBB": "Tech"},
                "weights_known": True,
            },
            proposal={
                "actions": [
                    {
                        "symbol": "CCC",
                        "action": "add",
                        "target_weight_pct": 15.0,
                        "sector": "Tech",
                    }
                ]
            },
            config={"max_sector_weight_pct": 40.0},
        )
        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["label"], LABEL_RESEARCH_ONLY)
        self.assertEqual(result["findings"][0]["constraint"], "sector_cap")
        self.assertGreater(result["findings"][0]["observed_pct"], 40.0)

    def test_sector_cap_uses_combined_projected_weights(self) -> None:
        result = evaluate_research_scenario(
            portfolio={
                "weights_pct": {"AAA": 10.0, "BBB": 10.0},
                "sectors": {"AAA": "Tech", "BBB": "Tech"},
                "weights_known": True,
            },
            proposal={
                "actions": [
                    {"symbol": "AAA", "action": "add", "target_weight_pct": 20.0, "sector": "Tech"},
                    {"symbol": "BBB", "action": "add", "target_weight_pct": 20.0, "sector": "Tech"},
                ]
            },
            config={"max_sector_weight_pct": 30.0},
        )
        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["findings"][0]["constraint"], "sector_cap")
        self.assertAlmostEqual(result["findings"][0]["observed_pct"], 40.0)

    def test_blacklist_rejects_increasing_action(self) -> None:
        result = evaluate_research_scenario(
            portfolio={"weights_pct": {"AAA": 10.0}, "weights_known": True},
            proposal={"actions": [{"symbol": "BBB", "action": "buy", "target_weight_pct": 5.0}]},
            config={"blacklist": ["BBB"]},
        )
        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["findings"][0]["constraint"], "blacklist")
        self.assertEqual(result["label"], LABEL_RESEARCH_ONLY)

    def test_simple_risk_flag_rejects_increasing_action(self) -> None:
        result = evaluate_research_scenario(
            portfolio={
                "weights_pct": {"AAA": 8.0},
                "risk_flags": {"AAA": ["halt", "watch"]},
                "weights_known": True,
            },
            proposal={"actions": [{"symbol": "AAA", "action": "add", "target_weight_pct": 12.0}]},
            config={"blocking_risk_flags": ["halt"]},
        )
        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["findings"][0]["constraint"], "risk_flag")
        self.assertIn("halt", result["findings"][0]["reason"])

    def test_assessment_signal_positions_are_checked(self) -> None:
        result = evaluate_research_scenario(
            assessment={
                "positions": [
                    {"code": "AAA", "signal": "buy", "suggested_weight": 0.4}
                ]
            },
            portfolio={"weights_pct": {"AAA": 10.0}, "weights_known": True},
            config={"max_single_name_weight_pct": 25.0},
        )
        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["label"], LABEL_RESEARCH_ONLY)
        self.assertEqual(result["findings"][0]["constraint"], "per_name_cap")

    def test_unknown_weights_sized_sector_target_is_hint_not_silent_pass(self) -> None:
        result = evaluate_research_scenario(
            portfolio={"weights_pct": {}, "sectors": {}, "weights_known": False},
            proposal={
                "actions": [
                    {
                        "symbol": "AAA",
                        "action": "buy",
                        "target_weight_pct": 15.0,
                        "sector": "Tech",
                    }
                ]
            },
            config={"max_sector_weight_pct": 40.0},
        )
        self.assertEqual(result["status"], "hints")
        self.assertEqual(result["label"], LABEL_CONSTRAINT_FEASIBLE)
        self.assertEqual(result["findings"][0]["constraint"], "sector_cap")
        self.assertEqual(result["findings"][0]["severity"], "hint")
        self.assertIn("unavailable", result["findings"][0]["reason"])

    def test_unknown_weights_still_reject_when_proposal_alone_exceeds_sector_cap(
        self,
    ) -> None:
        result = evaluate_research_scenario(
            portfolio={"weights_known": False},
            proposal={
                "actions": [
                    {
                        "symbol": "AAA",
                        "action": "buy",
                        "target_weight_pct": 50.0,
                        "sector": "Tech",
                    }
                ]
            },
            config={"max_sector_weight_pct": 40.0},
        )
        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["label"], LABEL_RESEARCH_ONLY)
        self.assertEqual(result["findings"][0]["constraint"], "sector_cap")

    def test_empty_proposal_is_not_an_executable_scenario(self) -> None:
        result = evaluate_research_scenario(
            portfolio={"weights_pct": {"AAA": 10.0}, "weights_known": True},
            proposal={"actions": []},
            config={"max_single_name_weight_pct": 25.0},
        )
        self.assertEqual(result["status"], "allow")
        self.assertFalse(result["executable"])
        self.assertEqual(result["passthrough_reason"], "no_proposed_actions")

    def test_malformed_config_fail_closes_as_research_only(self) -> None:
        result = evaluate_research_scenario(
            portfolio={"weights_pct": {"AAA": 10.0}},
            proposal={"actions": [{"symbol": "AAA", "action": "buy", "target_weight_pct": 12.0}]},
            config={"max_single_name_weight_pct": "nope"},
        )
        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["label"], LABEL_RESEARCH_ONLY)
        self.assertEqual(result["findings"][0]["constraint"], "engine_error")

    def test_oversized_symbol_fail_closes_as_research_only(self) -> None:
        result = evaluate_research_scenario(
            portfolio={"weights_pct": {"AAA": 10.0}},
            proposal={
                "actions": [
                    {"symbol": "S" * 33, "action": "buy", "target_weight_pct": 5.0}
                ]
            },
            config={"max_single_name_weight_pct": 25.0},
        )
        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["label"], LABEL_RESEARCH_ONLY)

    def test_trim_alias_maps_to_reduce_and_does_not_trip_blacklist(self) -> None:
        result = evaluate_research_scenario(
            portfolio={"weights_pct": {"BBB": 20.0}, "weights_known": True},
            proposal={"actions": [{"symbol": "BBB", "action": "trim", "to_weight_pct": 10.0}]},
            config={"blacklist": ["BBB"]},
        )
        self.assertEqual(result["status"], "hints")
        self.assertEqual(result["label"], LABEL_CONSTRAINT_FEASIBLE)
        self.assertEqual(result["findings"][0]["constraint"], "blacklist")

    def test_assessment_attachment_marks_rejected_suggestions(self) -> None:
        assessment = {
            "summary": "add more AAA",
            "rebalance_suggestions": ["Buy AAA to 40%"],
            "disclaimer": "Research aid only — not investment advice.",
        }
        apply_constraints_to_research_assessment(
            assessment,
            portfolio={"weights_pct": {"AAA": 10.0}, "weights_known": True},
            proposal={
                "actions": [{"symbol": "AAA", "action": "buy", "target_weight_pct": 40.0}]
            },
            config={"max_single_name_weight_pct": 25.0},
        )
        self.assertFalse(assessment["is_executable_scenario"])
        self.assertFalse(assessment["constraint_feasible"])
        self.assertEqual(assessment["scenario_label"], LABEL_RESEARCH_ONLY)
        self.assertTrue(assessment["rebalance_suggestions"][0].startswith("[research_only]"))
        self.assertIn(NOT_BROKER_COMPLIANCE_DISCLAIMER, assessment["disclaimer"])
        self.assertIs(
            assessment["constraint_check"],
            assessment["constraint_check"],
        )
        self.assertEqual(
            assessment["constraint_check"]["engine_version"],
            "portfolio-constraints-v1",
        )

    def test_unconfigured_assessment_exposes_explicit_passthrough(self) -> None:
        assessment = {
            "summary": "no policy injected",
            "disclaimer": "Research aid only — not investment advice.",
        }
        apply_constraints_to_research_assessment(
            assessment,
            portfolio={"weights_pct": {"AAA": 10.0}, "weights_known": True},
            proposal={
                "actions": [{"symbol": "AAA", "action": "buy", "target_weight_pct": 40.0}]
            },
        )
        self.assertTrue(assessment["constraint_passthrough"])
        self.assertEqual(
            assessment["constraint_passthrough_reason"],
            PASSTHROUGH_REASON_NO_CONSTRAINTS,
        )
        self.assertTrue(assessment["constraint_feasible"])
        self.assertIn(PASSTHROUGH_DISCLAIMER, assessment["disclaimer"])
        self.assertFalse(assessment["is_executable_scenario"])

    def test_research_proposal_prefers_suggestions_over_bands(self) -> None:
        proposal = research_proposal_from_assessment(
            {},
            rebalancing_base={
                "status": "ok",
                "suggestions": [
                    {"symbol": "AAA", "action": "add", "to_weight_pct": 40.0}
                ],
                "position_bands": [
                    {"symbol": "AAA", "action": "add", "target_weight_pct_mid": 20.0}
                ],
            },
        )
        self.assertEqual(len(proposal.actions), 1)
        self.assertEqual(proposal.actions[0].symbol, "AAA")
        self.assertEqual(proposal.actions[0].target_weight_pct, 40.0)

    def test_conflicting_suggestion_target_is_checked_not_band_mid(self) -> None:
        result = evaluate_research_scenario(
            portfolio={"weights_pct": {"AAA": 10.0}, "weights_known": True},
            rebalancing_base={
                "status": "ok",
                "suggestions": [
                    {"symbol": "AAA", "action": "add", "to_weight_pct": 40.0}
                ],
                "position_bands": [
                    {"symbol": "AAA", "action": "add", "target_weight_pct_mid": 20.0}
                ],
                "current": {"weights": [{"symbol": "AAA", "weight_pct": 10.0}]},
            },
            config={"max_single_name_weight_pct": 30.0},
        )
        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["findings"][0]["constraint"], "per_name_cap")
        self.assertAlmostEqual(result["findings"][0]["observed_pct"], 40.0)

    def test_unparseable_candidate_rows_fail_closed(self) -> None:
        result = evaluate_research_scenario(
            portfolio={"weights_pct": {"AAA": 10.0}, "weights_known": True},
            proposal={"actions": [{"symbol": "AAA", "suggested_weight": 0.4}]},
            config={"max_single_name_weight_pct": 25.0},
        )
        self.assertEqual(result["status"], "reject")
        self.assertEqual(result["label"], LABEL_RESEARCH_ONLY)
        self.assertEqual(result["findings"][0]["constraint"], "unparseable_proposal")

    def test_partial_sector_map_is_hint_not_silent_pass(self) -> None:
        result = evaluate_research_scenario(
            portfolio={
                "weights_pct": {"AAA": 20.0, "BBB": 25.0},
                "sectors": {"AAA": "Tech"},
                "weights_known": True,
            },
            proposal={
                "actions": [
                    {
                        "symbol": "AAA",
                        "action": "add",
                        "target_weight_pct": 22.0,
                        "sector": "Tech",
                    }
                ]
            },
            config={"max_sector_weight_pct": 40.0},
        )
        self.assertEqual(result["status"], "hints")
        self.assertEqual(result["findings"][0]["constraint"], "sector_cap")
        self.assertEqual(result["findings"][0]["severity"], "hint")
        self.assertIn("no sector tag", result["findings"][0]["reason"])

    def test_rebalancing_base_without_sectors_hints_sector_cap(self) -> None:
        result = evaluate_research_scenario(
            rebalancing_base={
                "status": "ok",
                "suggestions": [
                    {"symbol": "AAA", "action": "add", "to_weight_pct": 20.0}
                ],
                "current": {"weights": [{"symbol": "AAA", "weight_pct": 10.0}]},
            },
            config={"max_sector_weight_pct": 40.0},
        )
        self.assertEqual(result["status"], "hints")
        self.assertEqual(result["findings"][0]["constraint"], "sector_cap")
        self.assertIn("no sector is known", result["findings"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
