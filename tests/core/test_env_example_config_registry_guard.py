# -*- coding: utf-8 -*-
"""Guard the documented environment contract consumed by Web Settings.

Every key in ``.env.example`` must have explicit registry metadata. Inference
remains a compatibility fallback for runtime-only values, never the final UI
contract for a documented setting.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from src.core.config_registry import (
    _infer_data_type,
    _infer_ui_control,
    get_field_definition,
    get_registered_field_keys,
)

_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
_DOCUMENTED_ENV_ASSIGNMENT_RE = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=")


def _documented_env_example_keys() -> set[str]:
    return {
        match.group(1)
        for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        for match in [_DOCUMENTED_ENV_ASSIGNMENT_RE.match(line)]
        if match
    }


class TestEnvExampleConfigRegistryGuard(unittest.TestCase):
    """Fail closed when a documented key skips explicit registration."""

    def test_every_documented_env_example_key_is_registered(self) -> None:
        documented = _documented_env_example_keys()
        registered = set(get_registered_field_keys())

        self.assertEqual(
            sorted(documented - registered),
            [],
            "Every .env.example key needs explicit metadata in "
            "src/core/config_registry_parts/. Do not rely on inferred Settings "
            "controls for documented configuration.",
        )


class TestConfigRegistryTypeInferenceFallback(unittest.TestCase):
    """Inference stays correct for runtime-only compatibility values."""

    def test_boolean_named_keys_infer_boolean_without_value_hint(self) -> None:
        samples = (
            "CRYPTO_PROVIDER_ENABLED",
            "MCP_SERVER_ENABLED",
            "DATA_VALIDATION_ENABLED",
            "DATA_VALIDATION_STRICT",
            "ENABLE_FUNDAMENTAL_PIPELINE",
            "SQLITE_WAL_ENABLED",
            "FAILURE_NOTIFY_ENABLED",
        )
        registered = set(get_registered_field_keys())
        for key in samples:
            with self.subTest(key=key):
                self.assertEqual(_infer_data_type(key, None), "boolean")
                self.assertEqual(_infer_ui_control("boolean", key), "switch")
                field = get_field_definition(key)
                if key not in registered:
                    self.assertEqual(field["data_type"], "boolean")
                    self.assertEqual(field["ui_control"], "switch")

    def test_boolean_value_hint_with_inline_comment(self) -> None:
        self.assertEqual(
            _infer_data_type(
                "DECISION_MEMORY_ENABLED",
                "true # Global toggle; per-request override via use_memory",
            ),
            "boolean",
        )
        self.assertEqual(
            _infer_data_type(
                "PROVIDER_ADAPTIVE_PRIORITY_ENABLED",
                "true # Reorder sufficiently sampled peers",
            ),
            "boolean",
        )
        self.assertEqual(_infer_data_type("SOME_FLAG", "false # off"), "boolean")

    def test_numeric_value_hint_with_inline_comment(self) -> None:
        self.assertEqual(_infer_data_type("SOME_TIMEOUT", "30 # seconds"), "integer")
        self.assertEqual(_infer_data_type("SOME_RATIO", "1.5 # ratio"), "number")

    def test_enum_options_infer_select_control(self) -> None:
        options = [
            {"label": "Brief", "value": "brief"},
            {"label": "Standard", "value": "standard"},
            {"label": "Research", "value": "research"},
        ]
        self.assertEqual(
            _infer_ui_control("string", "REPORT_MODE", options=options),
            "select",
        )
        self.assertEqual(
            _infer_ui_control(
                "string",
                "MCP_SERVER_TRANSPORT",
                options=["stdio", "sse"],
            ),
            "select",
        )
        self.assertEqual(_infer_ui_control("string", "PROVIDER_MARKET_DATA_MODE"), "text")
        self.assertEqual(_infer_data_type("REPORT_MODE", "standard"), "string")

    def test_registered_boolean_fields_unchanged_by_inference_fallback(self) -> None:
        field = get_field_definition("WEBUI_ENABLED")
        self.assertEqual(field["data_type"], "boolean")
        self.assertEqual(field["ui_control"], "switch")
        self.assertNotEqual(field["display_order"], 9000)


if __name__ == "__main__":
    unittest.main()
