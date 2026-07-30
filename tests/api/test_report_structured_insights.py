# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract tests for the optional structured report insight projection."""

from api.v1.schemas.report_structured_insights import (
    REPORT_STRUCTURED_INSIGHTS_SCHEMA_VERSION,
    project_report_structured_insights_for_api,
)


def test_projects_complete_dashboard_payload() -> None:
    projected = project_report_structured_insights_for_api(
        {
            "dashboard": {
                "phase_decision": {
                    "phase_context": {
                        "phase": "intraday",
                        "market": "US",
                        "market_local_time": "2026-07-29T11:30:00-04:00",
                        "is_trading_day": True,
                        "is_market_open_now": True,
                        "minutes_to_close": 270,
                        "warnings": ["partial_bar"],
                    },
                    "action_window": "Next 30 minutes",
                    "immediate_action": "Wait for confirmation",
                    "watch_conditions": ["Price holds above VWAP"],
                    "next_check_time": "12:00 ET",
                    "confidence_reason": "Price and volume confirmation are incomplete",
                    "data_limitations": ["Current daily bar is partial"],
                },
                "signal_attribution": {
                    "technical_indicators": "50%",
                    "news_sentiment": 20,
                    "fundamentals": 20,
                    "market_conditions": 10,
                    "strongest_bullish_signal": "Volume expansion",
                    "strongest_bearish_signal": "Weak breadth",
                },
                "strategy_synthesis": {
                    "final_signal": "buy",
                    "weighted_score": 4.2,
                    "confidence": 0.74,
                    "original_confidence": 0.8,
                    "conflict_count": 1,
                    "conflict_severity": "medium",
                    "consensus_level": "medium",
                    "supporting_skills": [
                        {
                            "skill_id": "volume_breakout",
                            "signal": "buy",
                            "confidence": 0.83,
                            "reasoning": "Breakout confirmed",
                            "conditions_met": ["volume"],
                        }
                    ],
                    "opposing_skills": [
                        {
                            "skill_id": "box_oscillation",
                            "signal": "reduce",
                            "confidence": 0.72,
                        }
                    ],
                    "conflicts": [
                        {
                            "conflict_type": "directional_opposition",
                            "severity": "medium",
                            "description_key": "strategy_conflict.directional_opposition",
                            "participants": ["volume_breakout", "box_oscillation"],
                            "metadata": {"ignored": "not part of the public contract"},
                        }
                    ],
                    "summary_params": {
                        "opinion_count": 2,
                        "total_opinion_count": 3,
                        "invalid_opinion_count": 1,
                    },
                },
            }
        }
    )

    assert projected is not None
    assert projected["schema_version"] == REPORT_STRUCTURED_INSIGHTS_SCHEMA_VERSION
    assert projected["phase_decision"]["phase_context"]["phase"] == "intraday"
    assert projected["signal_attribution"]["technical_indicators"] == 50
    synthesis = projected["strategy_synthesis"]
    assert synthesis["final_signal"] == "buy"
    assert synthesis["opposing_skills"][0]["skill_id"] == "box_oscillation"
    assert synthesis["conflicts"][0] == {
        "conflict_type": "directional_opposition",
        "severity": "medium",
        "description_key": "strategy_conflict.directional_opposition",
        "participants": ["volume_breakout", "box_oscillation"],
    }
    assert synthesis["summary_params"]["invalid_opinion_count"] == 1


def test_projects_partial_payload_without_synthesizing_missing_sections() -> None:
    projected = project_report_structured_insights_for_api(
        {
            "phase_decision": {
                "immediate_action": "Observe",
                "watch_conditions": "Wait for the opening range",
            }
        }
    )

    assert projected == {
        "schema_version": REPORT_STRUCTURED_INSIGHTS_SCHEMA_VERSION,
        "phase_decision": {
            "immediate_action": "Observe",
            "watch_conditions": ["Wait for the opening range"],
        },
    }


def test_returns_none_for_missing_or_empty_sections() -> None:
    assert project_report_structured_insights_for_api(None, {}, {"dashboard": {}}) is None
    assert (
        project_report_structured_insights_for_api(
            {
                "dashboard": {
                    "phase_decision": {},
                    "signal_attribution": {
                        "technical_indicators": 0,
                        "news_sentiment": 0,
                        "fundamentals": 0,
                        "market_conditions": 0,
                    },
                    "strategy_synthesis": {"conflict_count": 0},
                }
            }
        )
        is None
    )


def test_ignores_malformed_fields_and_uses_later_valid_source() -> None:
    projected = project_report_structured_insights_for_api(
        {
            "dashboard": {
                "phase_decision": "bad",
                "signal_attribution": ["bad"],
                "strategy_synthesis": {"supporting_skills": "bad"},
            }
        },
        {
            "structured_insights": {
                "phase_decision": {"confidence_reason": "Fallback source retained"},
            }
        },
    )

    assert projected == {
        "schema_version": REPORT_STRUCTURED_INSIGHTS_SCHEMA_VERSION,
        "phase_decision": {"confidence_reason": "Fallback source retained"},
    }


def test_preserves_conflict_and_opposition_without_unbounded_metadata() -> None:
    projected = project_report_structured_insights_for_api(
        {
            "strategy_synthesis": {
                "final_signal": "hold",
                "opposing_skills": [
                    {"skill_id": "bear_case", "signal": "sell", "raw_data": {"secret": True}},
                    "malformed",
                ],
                "conflicts": [
                    {
                        "conflict_type": "high_confidence_dissent",
                        "severity": "high",
                        "participants": ["bear_case", "", 123],
                        "metadata": {"large": ["ignored"]},
                    },
                    None,
                ],
            }
        }
    )

    assert projected is not None
    synthesis = projected["strategy_synthesis"]
    assert synthesis["opposing_skills"] == [
        {"skill_id": "bear_case", "signal": "sell"},
    ]
    assert synthesis["conflicts"] == [
        {
            "conflict_type": "high_confidence_dissent",
            "severity": "high",
            "participants": ["bear_case"],
        }
    ]
