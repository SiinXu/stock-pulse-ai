"""Domain-schema tests for personal investment framework content."""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

import api.v1.schemas as api_schema_exports
from api.v1.schemas.investment_framework import (
    InvestmentFrameworkCreateRequest,
    InvestmentFrameworkDeactivateRequest,
    InvestmentFrameworkDeleteResponse,
    InvestmentFrameworkHistoryItem,
    InvestmentFrameworkHistoryResponse,
    InvestmentFrameworkResponse,
    InvestmentFrameworkUpdateRequest,
)
from src.schemas.investment_framework import (
    INVESTMENT_FRAMEWORK_CASEFOLD_UNICODE_VERSION,
    InvestmentFrameworkAnalysisContext,
    InvestmentFrameworkContent,
    InvestmentFrameworkDecisionBranch,
    InvestmentFrameworkDecisionNode,
    InvestmentFrameworkEvaluationDimension,
    casefold_investment_framework_dimension_name,
)


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


def _frontend_casefold_contract() -> tuple[str, dict[int, str]]:
    editor_model = (
        Path(__file__).resolve().parents[2]
        / "apps"
        / "dsa-web"
        / "src"
        / "components"
        / "settings"
        / "investmentFrameworkEditorModel.ts"
    ).read_text(encoding="utf-8")
    match = re.search(
        r"INVESTMENT_FRAMEWORK_CASEFOLD_UNICODE_VERSION = '([^']+)';"
        r".*?const UNICODE_15_FULL_CASEFOLD_DATA = `\n(.*?)\n`;",
        editor_model,
        re.DOTALL,
    )
    assert match is not None

    mappings: dict[int, str] = {}
    for raw_record in match.group(2).split(";"):
        record = raw_record.strip()
        if not record:
            continue
        source, targets = record.split(":")
        mappings[int(source, 16)] = "".join(
            chr(int(target, 16))
            for target in targets.split(",")
        )
    return match.group(1), mappings


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

    coerced_title = _structured_content()
    coerced_title["title"] = 123
    with pytest.raises(ValidationError):
        InvestmentFrameworkContent.model_validate(coerced_title)

    coerced_weight = _structured_content()
    coerced_weight["evaluation_dimensions"][0]["weight"] = "40"
    with pytest.raises(ValidationError):
        InvestmentFrameworkContent.model_validate(coerced_weight)

    coerced_rule = _structured_content()
    coerced_rule["risk_rules"] = [123]
    with pytest.raises(ValidationError):
        InvestmentFrameworkContent.model_validate(coerced_rule)


def test_all_framework_dtos_use_strict_validation_including_responses() -> None:
    api_models = (
        InvestmentFrameworkCreateRequest,
        InvestmentFrameworkUpdateRequest,
        InvestmentFrameworkDeactivateRequest,
        InvestmentFrameworkResponse,
        InvestmentFrameworkHistoryItem,
        InvestmentFrameworkHistoryResponse,
        InvestmentFrameworkDeleteResponse,
    )
    domain_models = (
        InvestmentFrameworkDecisionBranch,
        InvestmentFrameworkDecisionNode,
        InvestmentFrameworkEvaluationDimension,
        InvestmentFrameworkContent,
        InvestmentFrameworkAnalysisContext,
    )
    assert all(
        model.model_config["strict"] is True
        and model.model_config["extra"] == "forbid"
        and model.model_config["revalidate_instances"] == "always"
        for model in api_models
    )
    assert all(
        model.model_config["strict"] is True
        and model.model_config["extra"] == "forbid"
        and model.model_config["revalidate_instances"] == "always"
        for model in domain_models
    )
    for model in api_models:
        assert getattr(api_schema_exports, model.__name__) is model
        assert model.__name__ in api_schema_exports.__all__

    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    response = {
        "framework_id": 1,
        "scope": "local",
        "version": 1,
        "active_version": 1,
        "revision": 1,
        "is_active": True,
        "content": _structured_content(),
        "change_summary": None,
        "created_at": now,
        "updated_at": now,
        "version_created_at": now,
    }
    assert InvestmentFrameworkResponse.model_validate(response).framework_id == 1
    for field in ("framework_id", "revision"):
        with pytest.raises(ValidationError):
            InvestmentFrameworkResponse.model_validate(
                {**response, field: "1"}
            )

    coerced_content = _structured_content()
    coerced_content["evaluation_dimensions"][0]["weight"] = "40"
    with pytest.raises(ValidationError):
        InvestmentFrameworkResponse.model_validate(
            {**response, "content": coerced_content}
        )

    mutated_content = InvestmentFrameworkContent.model_validate(
        _structured_content()
    )
    mutated_content.evaluation_dimensions[0].weight = "40"
    with pytest.raises(ValidationError):
        InvestmentFrameworkResponse.model_validate(
            {**response, "content": mutated_content}
        )

    mutated_response = InvestmentFrameworkResponse.model_validate(response)
    mutated_response.revision = "1"
    with pytest.raises(ValidationError):
        InvestmentFrameworkResponse.model_validate(mutated_response)


def test_framework_response_dtos_reject_nonpositive_identity_and_version_fields() -> None:
    now = datetime(2026, 7, 25, tzinfo=timezone.utc)
    content = _structured_content()
    response = {
        "framework_id": 1,
        "scope": "local",
        "version": 1,
        "active_version": 1,
        "revision": 1,
        "is_active": True,
        "content": content,
        "change_summary": None,
        "created_at": now,
        "updated_at": now,
        "version_created_at": now,
    }
    for field in ("framework_id", "version", "active_version", "revision"):
        with pytest.raises(ValidationError):
            InvestmentFrameworkResponse.model_validate({**response, field: 0})

    history_item = {
        "version": 1,
        "is_active": True,
        "content": content,
        "change_summary": None,
        "created_at": now,
    }
    with pytest.raises(ValidationError):
        InvestmentFrameworkHistoryItem.model_validate(
            {**history_item, "version": 0}
        )

    history = {
        "framework_id": 1,
        "latest_version": 1,
        "active_version": 1,
        "revision": 1,
        "items": [history_item],
        "total": 1,
    }
    for field in (
        "framework_id",
        "latest_version",
        "active_version",
        "revision",
    ):
        with pytest.raises(ValidationError):
            InvestmentFrameworkHistoryResponse.model_validate(
                {**history, field: 0}
            )

    deleted = {
        "deleted": True,
        "framework_id": 1,
        "deleted_through_version": 1,
    }
    for field in ("framework_id", "deleted_through_version"):
        with pytest.raises(ValidationError):
            InvestmentFrameworkDeleteResponse.model_validate(
                {**deleted, field: 0}
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


def test_pinned_frontend_casefold_table_matches_backend_contract() -> None:
    version, frontend_mappings = _frontend_casefold_contract()
    for code_point in range(0x110000):
        character = chr(code_point)
        assert casefold_investment_framework_dimension_name(
            character
        ) == frontend_mappings.get(code_point, character)

    assert version == INVESTMENT_FRAMEWORK_CASEFOLD_UNICODE_VERSION == "15.0.0"
    assert len(frontend_mappings) == 1530


def test_dimension_casefold_contract_rejects_duplicates_and_allows_newer_additions() -> None:
    duplicate = _structured_content()
    duplicate["evaluation_dimensions"][0]["name"] = "Straße"
    duplicate["evaluation_dimensions"][1]["name"] = "STRASSE"
    with pytest.raises(ValidationError, match="must be unique"):
        InvestmentFrameworkContent.model_validate(duplicate)

    unicode_14_duplicate = _structured_content()
    unicode_14_duplicate["evaluation_dimensions"][0]["name"] = "\u2C2F"
    unicode_14_duplicate["evaluation_dimensions"][1]["name"] = "\u2C5F"
    with pytest.raises(ValidationError, match="must be unique"):
        InvestmentFrameworkContent.model_validate(unicode_14_duplicate)

    backend_allowed = _structured_content()
    backend_allowed["evaluation_dimensions"][0]["name"] = "\uA7CB"
    backend_allowed["evaluation_dimensions"][1]["name"] = "\u0264"
    validated = InvestmentFrameworkContent.model_validate(backend_allowed)

    assert [item.name for item in validated.evaluation_dimensions] == [
        "\uA7CB",
        "\u0264",
    ]


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
