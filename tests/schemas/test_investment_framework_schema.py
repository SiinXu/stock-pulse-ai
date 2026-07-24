"""Domain-schema tests for personal investment framework content."""

import pytest
from pydantic import ValidationError

from src.schemas.investment_framework import InvestmentFrameworkContent


def _structured_content() -> dict:
    return {
        "title": "Quality compounders",
        "root_node_id": "quality",
        "decision_tree": [
            {
                "node_id": "quality",
                "question": "Does the company meet the quality threshold?",
                "branches": [
                    {"condition": "Yes", "target_node_id": "valuation"},
                    {"condition": "No", "outcome": "Do not initiate coverage"},
                ],
            },
            {
                "node_id": "valuation",
                "question": "Is the valuation inside the required margin of safety?",
                "branches": [
                    {"condition": "Yes", "outcome": "Eligible for a research position"},
                    {"condition": "No", "outcome": "Track without buying"},
                ],
            },
        ],
        "evaluation_dimensions": [
            {
                "name": "Moat",
                "weight": 40,
                "criteria": ["Pricing power is supported by disclosed evidence"],
            },
            {
                "name": "Capital allocation",
                "weight": 25,
                "criteria": ["Returns on incremental capital remain positive"],
            },
        ],
        "risk_rules": ["Do not exceed the documented position limit"],
        "tracking_criteria": ["Review after material guidance revisions"],
    }


def test_structured_framework_content_is_stable_and_strict() -> None:
    content = InvestmentFrameworkContent.model_validate(_structured_content())

    assert content.root_node_id == "quality"
    assert [item.name for item in content.evaluation_dimensions] == [
        "Moat",
        "Capital allocation",
    ]
    with pytest.raises(ValidationError):
        InvestmentFrameworkContent.model_validate(
            {**_structured_content(), "owner_id": "not-an-api-field"}
        )


def test_decision_tree_rejects_unknown_targets_and_ambiguous_branches() -> None:
    unknown_target = _structured_content()
    unknown_target["decision_tree"][0]["branches"][0]["target_node_id"] = "missing"
    with pytest.raises(ValidationError, match="unknown target"):
        InvestmentFrameworkContent.model_validate(unknown_target)

    ambiguous = _structured_content()
    ambiguous["decision_tree"][0]["branches"][0]["outcome"] = "Ambiguous"
    with pytest.raises(ValidationError, match="exactly one"):
        InvestmentFrameworkContent.model_validate(ambiguous)


def test_framework_rejects_empty_content_and_duplicate_dimensions() -> None:
    with pytest.raises(ValidationError, match="at least one criterion"):
        InvestmentFrameworkContent.model_validate({"title": "Empty"})

    duplicate = _structured_content()
    duplicate["evaluation_dimensions"][1]["name"] = "moat"
    with pytest.raises(ValidationError, match="must be unique"):
        InvestmentFrameworkContent.model_validate(duplicate)


def test_decision_tree_rejects_cycles_and_unreachable_nodes() -> None:
    cyclic = _structured_content()
    cyclic["decision_tree"][1]["branches"][0] = {
        "condition": "Loop",
        "target_node_id": "quality",
    }
    with pytest.raises(ValidationError, match="must not contain cycles"):
        InvestmentFrameworkContent.model_validate(cyclic)

    unreachable = _structured_content()
    unreachable["decision_tree"][0]["branches"][0] = {
        "condition": "Stop",
        "outcome": "Terminal",
    }
    with pytest.raises(ValidationError, match="reachable from the root"):
        InvestmentFrameworkContent.model_validate(unreachable)
