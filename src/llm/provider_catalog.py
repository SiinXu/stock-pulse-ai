# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Authoritative catalog of LLM model-service providers.

This is the single backend source of truth for provider metadata (labels,
default endpoints, discovery support, capabilities, credential requirements)
shared by the backend and the Web UI. The Web must not maintain a second
business list; it fetches this catalog and derives everything else from it.

The catalog intentionally does NOT ship concrete model IDs: model names age
quickly and must never be used as a Connection's default models. Models are
obtained per Connection at runtime — via discovery when the provider supports
it, or entered manually — and a Connection with no models stays explicitly
incomplete. Credential/base-URL requirements are *derived* from the existing
backend contract (``channel_allows_empty_api_key``) rather than re-declared
here, so there is a single authority for "does this provider need a key".
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Sequence

from src.llm.provider_catalog_data import _PROVIDERS
from src.llm.provider_catalog_data import get_provider_ids  # noqa: F401  (re-exported for backward compatibility)

_DISCOVERY_PROTOCOLS = {"openai", "deepseek", "ollama"}


# Dynamic Connection fields are a separate schema because their concrete env
# keys depend on the user-selected Connection name. This is the sole business
# definition consumed by the backend validator and serialized to Web clients.
# ``is_required`` remains as a deprecated compatibility projection; ``contract``
# is authoritative, including conditional requirements and visibility.
_CONNECTION_FIELD_SCHEMA: List[Dict[str, Any]] = [
    {
        "key": "connection_name",
        "env_suffix": None,
        "data_type": "string",
        "is_sensitive": False,
        "is_required": True,
        "contract": {"requirement": "required"},
    },
    {
        "key": "display_name",
        "env_suffix": "DISPLAY_NAME",
        "data_type": "string",
        "is_sensitive": False,
        "is_required": True,
        "contract": {"requirement": "required"},
    },
    {
        "key": "provider_id",
        "env_suffix": "PROVIDER",
        "data_type": "string",
        "is_sensitive": False,
        "is_required": True,
        "contract": {"requirement": "required"},
    },
    {
        "key": "protocol",
        "env_suffix": "PROTOCOL",
        "data_type": "string",
        "is_sensitive": False,
        "is_required": False,
        "contract": {
            "requirement": "optional",
            "required_when": [
                {"key": "enabled", "operator": "equals", "value": "true"},
            ],
            "visible_when": [
                {"key": "protocol_visible", "operator": "equals", "value": "true"},
            ],
            "requires_connection_test": True,
        },
    },
    {
        "key": "base_url",
        "env_suffix": "BASE_URL",
        "data_type": "string",
        "is_sensitive": False,
        "is_required": False,
        "contract": {
            "requirement": "optional",
            "required_when": [
                {"key": "enabled", "operator": "equals", "value": "true"},
                {"key": "base_url_required", "operator": "equals", "value": "true"},
            ],
            "visible_when": [
                {"key": "base_url_visible", "operator": "equals", "value": "true"},
            ],
            "requires_connection_test": True,
        },
    },
    {
        "key": "api_key",
        "env_suffix": "API_KEY",
        "data_type": "string",
        "is_sensitive": True,
        "is_required": False,
        "contract": {
            "requirement": "optional",
            "required_when": [
                {"key": "enabled", "operator": "equals", "value": "true"},
                {"key": "api_key_required", "operator": "equals", "value": "true"},
                {"key": "api_keys", "operator": "equals", "value": ""},
            ],
            "visible_when": [
                {"key": "api_key_visible", "operator": "equals", "value": "true"},
            ],
            "requires_connection_test": True,
        },
    },
    {
        "key": "api_keys",
        "env_suffix": "API_KEYS",
        "data_type": "array",
        "is_sensitive": True,
        "is_required": False,
        "contract": {
            "requirement": "optional",
            "visible_when": [
                {"key": "api_key_visible", "operator": "equals", "value": "true"},
            ],
            "requires_connection_test": True,
        },
    },
    {
        "key": "models",
        "env_suffix": "MODELS",
        "data_type": "array",
        "is_sensitive": False,
        "is_required": False,
        "contract": {
            "requirement": "optional",
            "required_when": [
                {"key": "enabled", "operator": "equals", "value": "true"},
            ],
            "requires_connection_test": True,
        },
    },
    {
        "key": "extra_headers",
        "env_suffix": "EXTRA_HEADERS",
        "data_type": "json",
        "is_sensitive": True,
        "is_required": False,
        "contract": {
            "requirement": "optional",
            "visible_when": [
                {"key": "extra_headers_visible", "operator": "equals", "value": "true"},
            ],
            "requires_connection_test": True,
        },
    },
    {
        "key": "enabled",
        "env_suffix": "ENABLED",
        "data_type": "boolean",
        "is_sensitive": False,
        "is_required": True,
        "contract": {"requirement": "required"},
    },
]


def get_connection_field_schema() -> List[Dict[str, Any]]:
    """Return a caller-immune copy of the dynamic Connection field schema."""
    return deepcopy(_CONNECTION_FIELD_SCHEMA)


def evaluate_connection_field_states(
    schema: Sequence[Dict[str, Any]],
    values: Dict[str, str],
) -> Dict[str, Dict[str, Any]]:
    """Evaluate every field contract with the shared AND condition semantics."""
    from src.core.config_registry import evaluate_config_conditions

    normalized_values = {
        str(key).strip().upper(): "" if value is None else str(value)
        for key, value in values.items()
    }
    states: Dict[str, Dict[str, Any]] = {}
    for field in schema:
        key = str(field.get("key") or "").strip()
        if not key:
            continue
        contract = field.get("contract") or {}
        condition_results = [
            evaluate_config_conditions(contract.get(condition_key), normalized_values)
            for condition_key in ("required_when", "visible_when", "enabled_when")
            if contract.get(condition_key) is not None
        ]
        unknown_condition = "unknown" in condition_results
        visible_result = evaluate_config_conditions(
            contract.get("visible_when"), normalized_values
        )
        visible = visible_result != "not_met"
        enabled_result = evaluate_config_conditions(
            contract.get("enabled_when"), normalized_values
        )
        enabled = (
            contract.get("requirement") != "inherited"
            and not unknown_condition
            and enabled_result == "met"
        )
        required = contract.get("requirement") == "required"
        if (
            not required
            and contract.get("required_when") is not None
            and evaluate_config_conditions(
                contract.get("required_when"), normalized_values
            ) == "met"
        ):
            required = True
        states[key] = {
            "visible": visible,
            "enabled": enabled,
            "required": bool(visible and required),
            "unknown_condition": unknown_condition,
            "requires_connection_test": bool(
                contract.get("requires_connection_test", False)
            ),
        }
    return states


def validate_connection_contract_values(
    schema: Sequence[Dict[str, Any]],
    values: Dict[str, str],
    *,
    field_keys: Optional[Sequence[str]] = None,
) -> List[str]:
    """Return required visible fields whose current values are empty."""
    missing, _unknown = _inspect_connection_contract_values(
        schema,
        values,
        field_keys=field_keys,
    )
    return missing


def get_unknown_connection_contract_fields(
    schema: Sequence[Dict[str, Any]],
    values: Dict[str, str],
    *,
    field_keys: Optional[Sequence[str]] = None,
) -> List[str]:
    """Return selected fields containing an unsupported contract condition."""
    _missing, unknown = _inspect_connection_contract_values(
        schema,
        values,
        field_keys=field_keys,
    )
    return unknown


def _inspect_connection_contract_values(
    schema: Sequence[Dict[str, Any]],
    values: Dict[str, str],
    *,
    field_keys: Optional[Sequence[str]] = None,
) -> tuple[List[str], List[str]]:
    """Collect missing fields and unknown-condition fields in schema order."""
    selected_keys = set(field_keys) if field_keys is not None else None
    states = evaluate_connection_field_states(schema, values)
    missing: List[str] = []
    unknown: List[str] = []
    for field in schema:
        key = str(field.get("key") or "")
        if selected_keys is not None and key not in selected_keys:
            continue
        if states.get(key, {}).get("unknown_condition"):
            unknown.append(key)
        if states.get(key, {}).get("required") and not str(values.get(key, "") or "").strip():
            missing.append(key)
    return missing, unknown


def build_connection_contract_values(
    *,
    connection_name: str,
    display_name: str,
    provider_id: str,
    provider: Optional[Dict[str, Any]],
    protocol: str,
    base_url: str,
    api_key: str,
    api_keys: str = "",
    models: Sequence[str] = (),
    extra_headers: str = "",
    enabled: bool,
) -> Dict[str, str]:
    """Build the provider-aware value context consumed by field contracts."""
    from src.config import channel_allows_empty_api_key

    resolved_provider = provider
    if resolved_provider is None:
        resolved_provider = get_provider(provider_id) or get_provider(connection_name) or get_provider("custom")
    resolved_provider_id = str(
        (resolved_provider or {}).get("id") or provider_id or "custom"
    )
    provider_default_url = str((resolved_provider or {}).get("default_base_url") or "")
    provider_is_custom = bool((resolved_provider or {}).get("is_custom", False))
    provider_protocol = str((resolved_provider or {}).get("protocol") or "").strip().lower()
    normalized_url = base_url.strip().rstrip("/")
    normalized_default_url = provider_default_url.strip().rstrip("/")
    key_required = not channel_allows_empty_api_key(protocol, base_url)
    return {
        "connection_name": connection_name.strip(),
        "display_name": display_name.strip(),
        "provider_id": resolved_provider_id,
        "protocol": protocol.strip(),
        "base_url": base_url.strip(),
        "api_key": api_key.strip(),
        "api_keys": api_keys.strip(),
        "models": ",".join(str(model).strip() for model in models if str(model).strip()),
        "extra_headers": extra_headers.strip(),
        "enabled": "true" if enabled else "false",
        "api_key_required": "true" if key_required else "false",
        "api_key_visible": "true" if (
            key_required or provider_is_custom or api_key.strip() or api_keys.strip()
        ) else "false",
        "base_url_required": "true" if provider_is_custom else "false",
        "base_url_visible": "true" if (
            provider_is_custom
            or bool(normalized_url and normalized_url != normalized_default_url)
        ) else "false",
        "extra_headers_visible": "true" if extra_headers.strip() else "false",
        "protocol_visible": "true" if (
            provider_is_custom
            or bool(protocol.strip() and protocol.strip().lower() != provider_protocol)
        ) else "false",
    }


def _provider_supports_model_discovery(provider: Dict[str, Any]) -> bool:
    """Return whether one raw Catalog entry supports model discovery."""
    return (
        "model-discovery" in provider["capabilities"]
        or str(provider["protocol"]).strip().lower() in _DISCOVERY_PROTOCOLS
    )


def supports_model_discovery(
    *,
    provider_id: str = "",
    protocol: str = "",
) -> bool:
    """Return the Catalog's discovery capability for a Provider or protocol."""
    normalized_provider_id = str(provider_id or "").strip().lower()
    if normalized_provider_id:
        provider = next(
            (
                entry
                for entry in _PROVIDERS
                if entry["id"] == normalized_provider_id
            ),
            None,
        )
        return bool(provider and _provider_supports_model_discovery(provider))
    return str(protocol or "").strip().lower() in _DISCOVERY_PROTOCOLS


def get_provider_catalog() -> List[Dict[str, Any]]:
    """Return provider metadata enriched with derived requirement flags.

    Each call returns fresh dicts (with copied ``capabilities`` lists), so a
    caller may freely mutate the result without polluting the shared catalog or
    other callers.
    """
    # Lazy import: src.config imports from src.llm.*, so importing at module
    # load would create a cycle.
    from src.config import channel_allows_empty_api_key

    catalog: List[Dict[str, Any]] = []
    for provider in _PROVIDERS:
        protocol = provider["protocol"]
        default_base_url = provider["default_base_url"]
        # Custom endpoints are dynamic: assume a key is needed by default, but a
        # local base URL still exempts it at validate time.
        requires_api_key = not channel_allows_empty_api_key(protocol, default_base_url)
        supports_discovery = _provider_supports_model_discovery(provider)
        catalog.append({
            "id": provider["id"],
            # `label` preserves the pre-contract Chinese display spelling for
            # older clients. New clients select one of the stable locale fields.
            "label": provider["label_zh"],
            "label_zh": provider["label_zh"],
            "label_en": provider["label_en"],
            "protocol": protocol,
            "default_base_url": default_base_url,
            "credential_url": provider["credential_url"],
            "console_url": provider["console_url"],
            "models_url": provider["models_url"],
            "docs_url": provider["docs_url"],
            "capabilities": list(provider["capabilities"]),
            "requires_api_key": requires_api_key,
            # Only custom needs a user-provided endpoint; officials use their
            # prefilled or SDK default endpoint.
            "requires_base_url": bool(provider["is_custom"]),
            "supports_discovery": supports_discovery,
            "is_local": bool(provider["is_local"]),
            "is_custom": bool(provider["is_custom"]),
        })
    return catalog


def get_provider(provider_id: str) -> Optional[Dict[str, Any]]:
    """Return fresh metadata for one catalog provider id."""
    normalized = str(provider_id or "").strip().lower()
    if not normalized:
        return None
    return next(
        (provider for provider in get_provider_catalog() if provider["id"] == normalized),
        None,
    )


def get_empty_api_key_hosts() -> List[str]:
    """Return the hostnames whose endpoints may run without an API key.

    Mirrors the backend validation contract (``channel_allows_empty_api_key``)
    so the Web can apply the same exemption without hardcoding a host list.
    """
    from src.config import LLM_EMPTY_API_KEY_HOSTNAMES

    return sorted(LLM_EMPTY_API_KEY_HOSTNAMES)
