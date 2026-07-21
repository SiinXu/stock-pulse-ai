"""Compatibility guards for the public config-registry facade."""

import hashlib
import importlib
import json

import src.core.config_registry as registry


EXPECTED_PUBLIC_EXPORTS = {
    "AGENT_CONTEXT_COMPRESSION_PROFILES",
    "AGENT_MAX_STEPS_DEFAULT",
    "Any",
    "DEFAULT_ALPHASIFT_INSTALL_SPEC",
    "Dict",
    "LLM_CHANNEL_FIELD_KEY_RE",
    "List",
    "NOTIFICATION_SEVERITIES",
    "Optional",
    "ROUTABLE_NOTIFICATION_CHANNELS",
    "SCHEMA_VERSION",
    "WEB_SETTINGS_HIDDEN_FROM_UI",
    "annotations",
    "build_schema_response",
    "deepcopy",
    "derive_ui_placement",
    "evaluate_config_conditions",
    "get_category_definitions",
    "get_contract_field_definitions",
    "get_field_definition",
    "get_registered_field_keys",
    "re",
}
EXPECTED_REGISTERED_KEYS_SHA256 = (
    "751d590d2bd2a75f322ad4e14888118371a4d66931235779f1e71ad0d963a24d"
)
EXPECTED_SCHEMA_SHA256 = (
    "c64ce34d12e21a6d7561dafa70d941092dd390e27a8aabbbb6060009a14f7c09"
)


def _json_sha256(value, *, sort_keys: bool = False) -> str:
    payload = json.dumps(
        value,
        sort_keys=sort_keys,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def test_config_registry_public_export_surface_is_stable():
    public_exports = {name for name in dir(registry) if not name.startswith("_")}

    assert public_exports == EXPECTED_PUBLIC_EXPORTS


def test_config_registry_contract_snapshot_is_stable():
    assert (
        _json_sha256(registry.get_registered_field_keys())
        == EXPECTED_REGISTERED_KEYS_SHA256
    )
    assert (
        _json_sha256(registry.build_schema_response(), sort_keys=True)
        == EXPECTED_SCHEMA_SHA256
    )


def test_config_registry_reload_rebuilds_nested_definitions():
    old_get_field_definition = registry.get_field_definition
    old_field_definitions = registry._FIELD_DEFINITIONS
    registry._FIELD_DEFINITIONS["STOCK_LIST"]["title"] = "mutated"

    reloaded = importlib.reload(registry)

    assert reloaded.get_field_definition is not old_get_field_definition
    assert reloaded._FIELD_DEFINITIONS is not old_field_definitions
    assert reloaded.get_field_definition("STOCK_LIST")["title"] == "Stock List"
