# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Registry contract for read-only research API settings (Issue #1143)."""

import unittest

from src.core.config_registry import build_schema_response, get_field_definition


class TestResearchApiRegistry(unittest.TestCase):
    def test_enabled_defaults_off(self) -> None:
        field = get_field_definition("RESEARCH_API_ENABLED")
        self.assertEqual(field["category"], "system")
        self.assertEqual(field["data_type"], "boolean")
        self.assertEqual(field["ui_control"], "switch")
        self.assertEqual(field["default_value"], "false")
        self.assertTrue(field["is_editable"])
        self.assertFalse(field["is_sensitive"])
        self.assertEqual(field["help_key"], "settings.system.research_api")

    def test_rate_limit_defaults_and_validation(self) -> None:
        field = get_field_definition("RESEARCH_API_RATE_LIMIT_PER_MINUTE")
        self.assertEqual(field["category"], "system")
        self.assertEqual(field["data_type"], "integer")
        self.assertEqual(field["ui_control"], "number")
        self.assertEqual(field["default_value"], "60")
        self.assertEqual(field["validation"].get("min"), 1)
        self.assertEqual(field["help_key"], "settings.system.research_api")

    def test_schema_response_includes_research_api_keys(self) -> None:
        schema = build_schema_response()
        system_cat = next(
            (category for category in schema["categories"] if category["category"] == "system"),
            None,
        )
        self.assertIsNotNone(system_cat, "system category missing")
        field_keys = {field["key"] for field in system_cat["fields"]}
        self.assertIn("RESEARCH_API_ENABLED", field_keys)
        self.assertIn("RESEARCH_API_RATE_LIMIT_PER_MINUTE", field_keys)
