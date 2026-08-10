# -*- coding: utf-8 -*-
"""Registry contract for agent runtime / decision-memory / report-mode settings."""

from __future__ import annotations

import unittest

from src.core.config_registry import build_schema_response, get_field_definition
from src.services.report_mode import (
    REPORT_MODE_BRIEF,
    REPORT_MODE_RESEARCH,
    REPORT_MODE_STANDARD,
    VALID_REPORT_MODES,
)


class TestReportModeRegistry(unittest.TestCase):
    def test_report_mode_is_select_with_runtime_contract_options(self) -> None:
        field = get_field_definition("REPORT_MODE")
        self.assertEqual(field["category"], "notification")
        self.assertEqual(field["data_type"], "string")
        self.assertEqual(field["ui_control"], "select")
        self.assertEqual(field["default_value"], REPORT_MODE_STANDARD)
        self.assertEqual(field["help_key"], "settings.report.REPORT_MODE")
        self.assertNotEqual(field["display_order"], 9000)

        option_values = {
            option["value"] if isinstance(option, dict) else option
            for option in field["options"]
        }
        self.assertEqual(option_values, set(VALID_REPORT_MODES))
        self.assertEqual(set(field["validation"]["enum"]), set(VALID_REPORT_MODES))
        self.assertIn(REPORT_MODE_BRIEF, field["validation"]["enum"])
        self.assertIn(REPORT_MODE_RESEARCH, field["validation"]["enum"])

    def test_schema_response_includes_report_mode(self) -> None:
        schema = build_schema_response()
        notification = next(
            category
            for category in schema["categories"]
            if category["category"] == "notification"
        )
        keys = {field["key"] for field in notification["fields"]}
        self.assertIn("REPORT_MODE", keys)


class TestReasoningTraceExportRegistry(unittest.TestCase):
    def test_export_switch_defaults_off(self) -> None:
        field = get_field_definition("REASONING_TRACE_EXPORT_ENABLED")
        self.assertEqual(field["category"], "agent")
        self.assertEqual(field["data_type"], "boolean")
        self.assertEqual(field["ui_control"], "switch")
        self.assertEqual(field["default_value"], "false")
        self.assertEqual(field["help_key"], "settings.agent.reasoning_trace_export")

    def test_export_max_chars_bounds(self) -> None:
        field = get_field_definition("REASONING_TRACE_EXPORT_MAX_CHARS")
        self.assertEqual(field["category"], "agent")
        self.assertEqual(field["data_type"], "integer")
        self.assertEqual(field["ui_control"], "number")
        self.assertEqual(field["default_value"], "500000")
        self.assertEqual(field["validation"]["min"], 10000)
        self.assertEqual(field["validation"]["max"], 2000000)


class TestPluginDataProviderAutoBindRegistry(unittest.TestCase):
    def test_auto_bind_defaults_off_with_restart(self) -> None:
        field = get_field_definition("PLUGIN_DATA_PROVIDER_AUTO_BIND")
        self.assertEqual(field["category"], "system")
        self.assertEqual(field["data_type"], "boolean")
        self.assertEqual(field["ui_control"], "switch")
        self.assertEqual(field["default_value"], "false")
        self.assertEqual(
            field["help_key"], "settings.system.PLUGIN_DATA_PROVIDER_AUTO_BIND"
        )
        self.assertIn("restart_required", field.get("warning_codes", []))


class TestAgentRuntimeGuardRegistry(unittest.TestCase):
    def test_tool_timeout_defaults(self) -> None:
        field = get_field_definition("AGENT_TOOL_TIMEOUT_S")
        self.assertEqual(field["category"], "agent")
        self.assertEqual(field["ui_control"], "number")
        self.assertEqual(field["default_value"], "120")
        self.assertEqual(field["validation"]["min"], 0)
        self.assertEqual(field["help_key"], "settings.agent.runtime_guards")

    def test_identical_call_and_stage_entry_defaults(self) -> None:
        identical = get_field_definition("AGENT_MAX_IDENTICAL_TOOL_CALLS")
        stage_entries = get_field_definition("AGENT_MAX_STAGE_ENTRIES")
        self.assertEqual(identical["default_value"], "3")
        self.assertEqual(stage_entries["default_value"], "1")
        self.assertEqual(identical["validation"]["min"], 0)
        self.assertEqual(stage_entries["validation"]["min"], 0)

    def test_stage_failure_policy_enum(self) -> None:
        field = get_field_definition("AGENT_STAGE_FAILURE_POLICY")
        self.assertEqual(field["ui_control"], "select")
        self.assertEqual(field["default_value"], "isolate")
        self.assertEqual(set(field["validation"]["enum"]), {"isolate", "fail_fast"})


class TestAgentStageTimeoutRegistry(unittest.TestCase):
    _STAGE_TIMEOUT_KEYS = (
        "AGENT_TECHNICAL_AGENT_TIMEOUT_S",
        "AGENT_INTEL_AGENT_TIMEOUT_S",
        "AGENT_RISK_AGENT_TIMEOUT_S",
        "AGENT_DECISION_AGENT_TIMEOUT_S",
        "AGENT_PORTFOLIO_AGENT_TIMEOUT_S",
        "AGENT_SKILL_AGENT_TIMEOUT_S",
    )

    def test_stage_timeouts_default_to_shared_budget(self) -> None:
        for key in self._STAGE_TIMEOUT_KEYS:
            field = get_field_definition(key)
            self.assertEqual(field["category"], "agent", key)
            self.assertEqual(field["ui_control"], "number", key)
            self.assertEqual(field["default_value"], "0", key)
            self.assertEqual(field["validation"]["min"], 0, key)
            self.assertEqual(field["help_key"], "settings.agent.stage_timeouts", key)


class TestDecisionMemoryRegistry(unittest.TestCase):
    def test_decision_memory_defaults(self) -> None:
        enabled = get_field_definition("DECISION_MEMORY_ENABLED")
        lookback = get_field_definition("DECISION_MEMORY_LOOKBACK")
        min_age = get_field_definition("DECISION_MEMORY_MIN_AGE_DAYS")
        min_samples = get_field_definition("DECISION_MEMORY_MIN_SAMPLES")

        self.assertEqual(enabled["ui_control"], "switch")
        self.assertEqual(enabled["default_value"], "true")
        self.assertEqual(lookback["default_value"], "5")
        self.assertEqual(min_age["default_value"], "3")
        self.assertEqual(min_samples["default_value"], "5")
        self.assertEqual(min_samples["validation"]["min"], 1)
        for field in (enabled, lookback, min_age, min_samples):
            self.assertEqual(field["help_key"], "settings.agent.decision_memory")
            self.assertEqual(field["category"], "agent")


if __name__ == "__main__":
    unittest.main()
