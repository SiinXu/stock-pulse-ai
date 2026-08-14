# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
from src.core.config_registry import get_field_definition, get_registered_field_keys

def test_research_pack_export_keys_are_registered():
    keys = get_registered_field_keys()
    assert "RESEARCH_PACK_EXPORT_ENABLED" in keys
    assert "RESEARCH_PACK_MAX_ZIP_BYTES" in keys
    enabled = get_field_definition("RESEARCH_PACK_EXPORT_ENABLED")
    assert enabled["category"] == "agent"
    assert enabled["data_type"] == "boolean"
    assert enabled["default_value"] == "false"
    assert enabled["help_key"] == "settings.agent.research_pack_export"
    budget = get_field_definition("RESEARCH_PACK_MAX_ZIP_BYTES")
    assert budget["validation"]["min"] == 1048576
    assert budget["validation"]["max"] == 67108864
