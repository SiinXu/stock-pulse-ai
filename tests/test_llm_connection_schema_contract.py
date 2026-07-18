# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Shared dynamic Connection field-contract regressions."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.llm.provider_catalog import (
    build_connection_contract_values,
    evaluate_connection_field_states,
    get_connection_field_schema,
    get_unknown_connection_contract_fields,
    get_provider,
    validate_connection_contract_values,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "apps/dsa-web/src/components/settings/__tests__/fixtures/llmConnectionContractCases.json"
)


class LLMConnectionSchemaContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_schema_covers_every_dynamic_connection_field(self) -> None:
        fields = {field["key"]: field for field in get_connection_field_schema()}
        self.assertEqual(
            set(fields),
            {
                "connection_name",
                "display_name",
                "provider_id",
                "protocol",
                "base_url",
                "api_key",
                "api_keys",
                "models",
                "extra_headers",
                "enabled",
            },
        )
        for field in fields.values():
            self.assertIn("contract", field)
            self.assertIn(field["contract"]["requirement"], {"required", "optional", "inherited"})
            self.assertEqual(
                field["is_required"],
                field["contract"]["requirement"] == "required",
            )

    def test_python_evaluator_matches_shared_provider_cases(self) -> None:
        schema = get_connection_field_schema()
        for case in self.fixture["cases"]:
            with self.subTest(case=case["name"], provider=case["providerId"]):
                states = evaluate_connection_field_states(schema, case["values"])
                required = [key for key, state in states.items() if state["required"]]
                visible = [key for key, state in states.items() if state["visible"]]
                missing = validate_connection_contract_values(schema, case["values"])
                self.assertEqual(required, case["required"])
                self.assertEqual(visible, case["visible"])
                self.assertEqual(missing, case["missing"])

    def test_value_builder_preserves_empty_display_name_from_shared_fixture(self) -> None:
        case = next(
            case
            for case in self.fixture["cases"]
            if case["name"] == "enabled_connection_empty_display_name"
        )
        source = case["values"]
        values = build_connection_contract_values(
            connection_name=source["connection_name"],
            display_name=source["display_name"],
            provider_id=case["providerId"],
            provider=get_provider(case["providerId"]),
            protocol=source["protocol"],
            base_url=source["base_url"],
            api_key=source["api_key"],
            api_keys=source["api_keys"],
            models=source["models"].split(","),
            extra_headers=source["extra_headers"],
            enabled=source["enabled"] == "true",
        )

        self.assertEqual(values["display_name"], "")
        self.assertEqual(
            validate_connection_contract_values(get_connection_field_schema(), values),
            case["missing"],
        )

    def test_unknown_operator_is_visible_read_only_and_diagnostic(self) -> None:
        schema = get_connection_field_schema()
        base_url = next(field for field in schema if field["key"] == "base_url")
        base_url["contract"]["visible_when"] = [
            {"key": "provider_id", "operator": "futureOperator", "value": "custom"}
        ]
        states = evaluate_connection_field_states(schema, {"provider_id": "custom"})
        self.assertTrue(states["base_url"]["visible"])
        self.assertFalse(states["base_url"]["enabled"])
        self.assertTrue(states["base_url"]["unknown_condition"])
        self.assertEqual(
            get_unknown_connection_contract_fields(
                schema,
                {"provider_id": "custom"},
            ),
            ["base_url"],
        )

    def test_unmet_condition_does_not_hide_a_later_unknown_operator(self) -> None:
        schema = get_connection_field_schema()
        base_url = next(field for field in schema if field["key"] == "base_url")
        base_url["contract"]["visible_when"] = [
            {"key": "provider_id", "operator": "equals", "value": "other"},
            {"key": "provider_id", "operator": "futureOperator", "value": "openai"},
        ]

        values = {"provider_id": "openai"}
        states = evaluate_connection_field_states(schema, values)

        self.assertTrue(states["base_url"]["visible"])
        self.assertFalse(states["base_url"]["enabled"])
        self.assertTrue(states["base_url"]["unknown_condition"])
        self.assertEqual(
            get_unknown_connection_contract_fields(schema, values),
            ["base_url"],
        )

    def test_contract_context_ignores_legacy_catalog_requirement_flags(self) -> None:
        provider = get_provider("openai")
        assert provider is not None
        provider["requires_api_key"] = False
        provider["requires_base_url"] = True

        values = build_connection_contract_values(
            connection_name="openai",
            display_name="OpenAI",
            provider_id="openai",
            provider=provider,
            protocol="openai",
            base_url="https://api.openai.com/v1",
            api_key="",
            models=["gpt-4o-mini"],
            enabled=True,
        )

        self.assertEqual(values["api_key_required"], "true")
        self.assertEqual(values["base_url_required"], "false")

    def test_custom_local_credentials_remain_visible_when_optional(self) -> None:
        values = build_connection_contract_values(
            connection_name="custom",
            display_name="Custom",
            provider_id="custom",
            provider=get_provider("custom"),
            protocol="openai",
            base_url="http://localhost:9000/v1",
            api_key="",
            models=["local-model"],
            enabled=True,
        )

        self.assertEqual(values["api_key_required"], "false")
        self.assertEqual(values["api_key_visible"], "true")

    def test_falsey_malformed_condition_payloads_are_unknown(self) -> None:
        from src.core.config_registry import evaluate_config_conditions

        self.assertEqual(evaluate_config_conditions({}, {}), "unknown")
        self.assertEqual(evaluate_config_conditions("", {}), "unknown")
        self.assertEqual(evaluate_config_conditions([], {}), "met")
        self.assertEqual(evaluate_config_conditions(None, {}), "met")

    def test_static_openapi_publishes_connection_schema_and_bilingual_labels(self) -> None:
        spec_path = Path(__file__).resolve().parents[1] / "docs/architecture/api_spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        schemas = spec["components"]["schemas"]

        catalog_properties = schemas["LLMProviderCatalogResponse"]["properties"]
        self.assertIn("connection_fields", catalog_properties)
        provider_properties = schemas["LLMProviderCatalogEntry"]["properties"]
        self.assertIn("label_zh", provider_properties)
        self.assertIn("label_en", provider_properties)
        self.assertTrue(provider_properties["label"]["deprecated"])
        field_properties = schemas["LLMConnectionFieldSchema"]["properties"]
        self.assertIn("contract", field_properties)
        self.assertTrue(field_properties["is_required"]["deprecated"])

    def test_legacy_schema_fields_are_explicitly_deprecated(self) -> None:
        from api.v1.schemas.system_config import LLMProviderCatalogResponse

        schema = LLMProviderCatalogResponse.model_json_schema()
        self.assertTrue(
            schema["$defs"]["LLMConnectionFieldSchema"]["properties"]["is_required"]["deprecated"]
        )
        self.assertTrue(
            schema["$defs"]["LLMProviderCatalogEntry"]["properties"]["label"]["deprecated"]
        )


if __name__ == "__main__":
    unittest.main()
