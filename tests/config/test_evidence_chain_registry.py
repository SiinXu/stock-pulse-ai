# -*- coding: utf-8 -*-
from src.core.config_registry import get_field_definition, get_registered_field_keys

def test_evidence_chain_and_audit_export_keys_are_registered():
    keys = get_registered_field_keys()
    assert "EVIDENCE_CHAIN_ENABLED" in keys
    assert "AUDIT_EXPORT_ENABLED" in keys
    assert "AUDIT_INCLUDE_RAW_ARTIFACTS" in keys
    chain = get_field_definition("EVIDENCE_CHAIN_ENABLED")
    assert chain["default_value"] == "true"
    assert chain["help_key"] == "settings.agent.evidence_chain_export"
    audit = get_field_definition("AUDIT_EXPORT_ENABLED")
    assert audit["default_value"] == "false"
