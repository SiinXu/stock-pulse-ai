# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Config registry ownership for reasoning-trace export settings (Issue #135)."""

from src.core.config_registry import get_field_definition, get_registered_field_keys


def test_reasoning_trace_export_keys_are_registered():
    keys = get_registered_field_keys()
    assert "REASONING_TRACE_EXPORT_ENABLED" in keys
    assert "REASONING_TRACE_EXPORT_MAX_CHARS" in keys

    enabled = get_field_definition("REASONING_TRACE_EXPORT_ENABLED")
    assert enabled["category"] == "agent"
    assert enabled["data_type"] == "boolean"
    assert enabled["ui_control"] == "switch"
    assert enabled["default_value"] == "false"
    assert enabled["help_key"] == "settings.agent.reasoning_trace_export"

    budget = get_field_definition("REASONING_TRACE_EXPORT_MAX_CHARS")
    assert budget["category"] == "agent"
    assert budget["data_type"] == "integer"
    assert budget["ui_control"] == "number"
    assert budget["default_value"] == "500000"
    assert budget["validation"]["min"] == 10000
    assert budget["validation"]["max"] == 2000000
    assert budget["help_key"] == "settings.agent.reasoning_trace_export"
