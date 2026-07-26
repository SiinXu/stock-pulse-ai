# -*- coding: utf-8 -*-
"""Registry contract for public signal scorecard settings (Lane 6 / G06)."""

import unittest

from src.core.config_registry import build_schema_response, get_field_definition


class TestSignalScorecardRegistry(unittest.TestCase):
    def test_public_enabled_defaults_off(self) -> None:
        field = get_field_definition("SIGNAL_SCORECARD_PUBLIC_ENABLED")
        self.assertEqual(field["category"], "system")
        self.assertEqual(field["data_type"], "boolean")
        self.assertEqual(field["ui_control"], "switch")
        self.assertEqual(field["default_value"], "false")
        self.assertTrue(field["is_editable"])
        self.assertFalse(field["is_sensitive"])
        self.assertEqual(field["help_key"], "settings.system.scorecard")

    def test_min_samples_defaults_and_validation(self) -> None:
        field = get_field_definition("SIGNAL_SCORECARD_MIN_SAMPLES")
        self.assertEqual(field["category"], "system")
        self.assertEqual(field["data_type"], "integer")
        self.assertEqual(field["ui_control"], "number")
        self.assertEqual(field["default_value"], "10")
        self.assertEqual(field["validation"].get("min"), 1)
        self.assertEqual(field["help_key"], "settings.system.scorecard")

    def test_schema_response_includes_scorecard_keys(self) -> None:
        schema = build_schema_response()
        system_cat = next(
            (category for category in schema["categories"] if category["category"] == "system"),
            None,
        )
        self.assertIsNotNone(system_cat, "system category missing")
        field_keys = {field["key"] for field in system_cat["fields"]}
        self.assertIn("SIGNAL_SCORECARD_PUBLIC_ENABLED", field_keys)
        self.assertIn("SIGNAL_SCORECARD_MIN_SAMPLES", field_keys)
