# -*- coding: utf-8 -*-
"""Single authority for reading model routes from an effective config map.

The setup checks, connection tests, model discovery and assignment validation all
need to answer the same questions from a raw ``.env`` mapping: which channels are
enabled, which model routes they expose, what transport a connection resolves to,
and whether a legacy provider key can still back a model. Keeping those pure
readers here means ``SystemConfigService`` and
``ModelAssignmentValidator`` share one authority instead of re-deriving routes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from src.config import (
    ANSPIRE_LLM_BASE_URL_DEFAULT,
    ANSPIRE_LLM_MODEL_DEFAULT,
    Config,
    _get_litellm_provider,
    _uses_direct_env_provider,
    canonicalize_llm_channel_protocol,
    get_configured_llm_models,
    normalize_llm_channel_model,
    parse_env_bool,
    resolve_llm_channel_protocol,
)
from src.llm.hermes import (
    HERMES_DEFAULT_BASE_URL,
    HERMES_DEFAULT_MODEL,
    HERMES_DEFAULT_PROTOCOL,
    is_reserved_hermes_name,
    parse_hermes_channel,
    route_identity_candidates,
)


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def resolve_connection_provider(
    effective_map: Dict[str, str],
    connection_name: str,
) -> Tuple[Optional[Dict[str, Any]], str, bool]:
    """Resolve explicit Provider identity, with exact-name legacy fallback."""
    from src.llm.provider_catalog import get_provider

    prefix = f"LLM_{connection_name.upper()}"
    explicit_id = (effective_map.get(f"{prefix}_PROVIDER") or "").strip().lower()
    if explicit_id:
        return get_provider(explicit_id), explicit_id, True

    inferred_id = connection_name.strip().lower()
    inferred = get_provider(inferred_id)
    if inferred is not None and inferred_id != "custom":
        return inferred, inferred_id, False
    custom = get_provider("custom")
    return custom, "custom", False


def resolve_connection_transport(
    effective_map: Dict[str, str],
    connection_name: str,
) -> Tuple[str, str]:
    """Resolve a Connection's protocol and endpoint from explicit Provider identity."""
    prefix = f"LLM_{connection_name.upper()}"
    protocol = (effective_map.get(f"{prefix}_PROTOCOL") or "").strip()
    base_url = (effective_map.get(f"{prefix}_BASE_URL") or "").strip()
    provider, _provider_id, provider_is_explicit = resolve_connection_provider(
        effective_map,
        connection_name,
    )
    if (
        provider_is_explicit
        and provider is not None
        and not provider["is_custom"]
    ):
        protocol = str(provider["protocol"])
        if not base_url:
            base_url = str(provider["default_base_url"])
    if connection_name.lower() == "anspire":
        protocol = protocol or "openai"
        base_url = base_url or str(
            effective_map.get("ANSPIRE_LLM_BASE_URL")
            or ANSPIRE_LLM_BASE_URL_DEFAULT
        ).strip()
    return protocol, base_url


def anspire_legacy_llm_enabled(effective_map: Dict[str, str]) -> bool:
    if not parse_env_bool(effective_map.get("ANSPIRE_LLM_ENABLED"), default=True):
        return False
    for name in _split_csv(effective_map.get("LLM_CHANNELS") or ""):
        if name.strip().lower() != "anspire":
            continue
        enabled_raw = effective_map.get("LLM_ANSPIRE_ENABLED")
        if not (enabled_raw or "").strip():
            enabled_raw = effective_map.get("ANSPIRE_LLM_ENABLED")
        return parse_env_bool(enabled_raw, default=True)
    return True


def collect_llm_channel_models_from_map(effective_map: Dict[str, str]) -> List[str]:
    """Collect normalized model names from channel-style env values."""
    raw_channels = (effective_map.get("LLM_CHANNELS") or "").strip()
    if not raw_channels:
        return []

    models: List[str] = []
    seen: Set[str] = set()
    for raw_name in raw_channels.split(","):
        name = raw_name.strip()
        if not name:
            continue

        prefix = f"LLM_{name.upper()}"
        enabled_raw = effective_map.get(f"{prefix}_ENABLED")
        if name.lower() == "anspire" and not (enabled_raw or "").strip():
            enabled_raw = effective_map.get("ANSPIRE_LLM_ENABLED")
        enabled = parse_env_bool(enabled_raw, default=True)
        if not enabled:
            continue

        protocol_value, base_url_value = resolve_connection_transport(
            effective_map,
            name,
        )
        raw_models = [
            model.strip()
            for model in (effective_map.get(f"{prefix}_MODELS") or "").split(",")
            if model.strip()
        ]
        if name.lower() == "anspire" and not raw_models:
            raw_models = [
                (
                    effective_map.get("ANSPIRE_LLM_MODEL")
                    or ANSPIRE_LLM_MODEL_DEFAULT
                ).strip()
            ]
        if is_reserved_hermes_name(name):
            result = parse_hermes_channel(
                enabled=True,
                protocol=protocol_value or HERMES_DEFAULT_PROTOCOL,
                base_url=base_url_value or HERMES_DEFAULT_BASE_URL,
                api_key=(effective_map.get(f"{prefix}_API_KEY") or "").strip(),
                api_keys_raw=(effective_map.get(f"{prefix}_API_KEYS") or "").strip(),
                extra_headers_raw=(effective_map.get(f"{prefix}_EXTRA_HEADERS") or "").strip(),
                models=raw_models or [HERMES_DEFAULT_MODEL],
            )
            channel = result.channel or {}
            for model in channel.get("models") or []:
                if model and model not in seen:
                    seen.add(model)
                    models.append(model)
            continue
        resolved_protocol = resolve_llm_channel_protocol(protocol_value, base_url=base_url_value, models=raw_models, channel_name=name)
        for model in raw_models:
            normalized_model = normalize_llm_channel_model(model, resolved_protocol, base_url_value)
            if not normalized_model or normalized_model in seen:
                continue
            seen.add(normalized_model)
            models.append(normalized_model)

    return models


def collect_hermes_channel_models_from_map(effective_map: Dict[str, str]) -> List[str]:
    """Collect valid reserved Hermes route aliases from channel-style env values."""
    raw_channels = (effective_map.get("LLM_CHANNELS") or "").strip()
    if not raw_channels:
        return []

    models: List[str] = []
    seen: Set[str] = set()
    for raw_name in raw_channels.split(","):
        name = raw_name.strip()
        if not is_reserved_hermes_name(name):
            continue

        prefix = f"LLM_{name.upper()}"
        enabled = parse_env_bool(effective_map.get(f"{prefix}_ENABLED"), default=True)
        if not enabled:
            continue

        raw_models = _split_csv(effective_map.get(f"{prefix}_MODELS") or "")
        result = parse_hermes_channel(
            enabled=True,
            protocol=(effective_map.get(f"{prefix}_PROTOCOL") or HERMES_DEFAULT_PROTOCOL).strip(),
            base_url=(effective_map.get(f"{prefix}_BASE_URL") or HERMES_DEFAULT_BASE_URL).strip(),
            api_key=(effective_map.get(f"{prefix}_API_KEY") or "").strip(),
            api_keys_raw=(effective_map.get(f"{prefix}_API_KEYS") or "").strip(),
            extra_headers_raw=(effective_map.get(f"{prefix}_EXTRA_HEADERS") or "").strip(),
            models=raw_models or [HERMES_DEFAULT_MODEL],
        )
        channel = result.channel or {}
        for model in channel.get("models") or []:
            if model and model not in seen:
                seen.add(model)
                models.append(model)
    return models


def collect_non_hermes_channel_models_from_map(effective_map: Dict[str, str]) -> List[str]:
    """Collect enabled non-Hermes channel route aliases from channel-style env values."""
    raw_channels = (effective_map.get("LLM_CHANNELS") or "").strip()
    if not raw_channels:
        return []
    models: List[str] = []
    seen: Set[str] = set()
    for raw_name in raw_channels.split(","):
        name = raw_name.strip()
        if not name or is_reserved_hermes_name(name):
            continue
        prefix = f"LLM_{name.upper()}"
        enabled_raw = effective_map.get(f"{prefix}_ENABLED")
        if name.lower() == "anspire" and not (enabled_raw or "").strip():
            enabled_raw = effective_map.get("ANSPIRE_LLM_ENABLED")
        if not parse_env_bool(enabled_raw, default=True):
            continue
        protocol_value, base_url_value = resolve_connection_transport(
            effective_map,
            name,
        )
        raw_models = _split_csv(effective_map.get(f"{prefix}_MODELS") or "")
        if name.lower() == "anspire" and not raw_models:
            raw_models = [
                (
                    effective_map.get("ANSPIRE_LLM_MODEL")
                    or ANSPIRE_LLM_MODEL_DEFAULT
                ).strip()
            ]
        resolved_protocol = resolve_llm_channel_protocol(
            protocol_value,
            base_url=base_url_value,
            models=raw_models,
            channel_name=name,
        )
        for raw_model in raw_models:
            model = normalize_llm_channel_model(raw_model, resolved_protocol, base_url_value)
            if model and model not in seen:
                seen.add(model)
                models.append(model)
    return models


def collect_mixed_hermes_routes_from_map(effective_map: Dict[str, str]) -> Set[str]:
    hermes_routes = set(collect_hermes_channel_models_from_map(effective_map))
    non_hermes_routes = set(collect_non_hermes_channel_models_from_map(effective_map))
    return hermes_routes & non_hermes_routes


def matches_route_set(model: str, routes: Set[str]) -> bool:
    """Loose safety match for Hermes/provenance checks, not normal route availability."""
    return bool(route_identity_candidates(model) & set(routes or set()))


def matches_exact_route(model: str, routes: Set[str]) -> bool:
    """Match the Router's top-level model_name exactly for normal availability checks."""
    normalized_model = str(model or "").strip()
    return bool(normalized_model) and normalized_model in set(routes or set())


def uses_litellm_yaml(effective_map: Dict[str, str]) -> bool:
    """Return True when a valid LiteLLM YAML config takes precedence over channels."""
    config_path = (effective_map.get("LITELLM_CONFIG") or "").strip()
    if not config_path:
        return False
    return bool(Config._parse_litellm_yaml(config_path))


def collect_yaml_models_from_map(effective_map: Dict[str, str]) -> List[str]:
    """Collect declared router model names from LiteLLM YAML config."""
    config_path = (effective_map.get("LITELLM_CONFIG") or "").strip()
    if not config_path:
        return []
    return get_configured_llm_models(Config._parse_litellm_yaml(config_path))


def has_legacy_key_for_provider(provider: str, effective_map: Dict[str, str]) -> bool:
    """Return True when legacy env config can still back the provider."""
    normalized_provider = canonicalize_llm_channel_protocol(provider)
    if normalized_provider in {"gemini", "vertex_ai"}:
        return bool(
            (effective_map.get("GEMINI_API_KEYS") or "").strip()
            or (effective_map.get("GEMINI_API_KEY") or "").strip()
        )
    if normalized_provider == "anthropic":
        return bool(
            (effective_map.get("ANTHROPIC_API_KEYS") or "").strip()
            or (effective_map.get("ANTHROPIC_API_KEY") or "").strip()
        )
    if normalized_provider == "deepseek":
        return bool(
            (effective_map.get("DEEPSEEK_API_KEYS") or "").strip()
            or (effective_map.get("DEEPSEEK_API_KEY") or "").strip()
        )
    if normalized_provider == "openai":
        return bool(
            (effective_map.get("OPENAI_API_KEYS") or "").strip()
            or (effective_map.get("AIHUBMIX_KEY") or "").strip()
            or (effective_map.get("OPENAI_API_KEY") or "").strip()
            or (
                anspire_legacy_llm_enabled(effective_map)
                and (effective_map.get("ANSPIRE_API_KEYS") or "").strip()
            )
        )
    return False


def has_runtime_source_for_model(model: str, effective_map: Dict[str, str]) -> bool:
    """Whether the selected model still has a backing runtime source."""
    if not model or _uses_direct_env_provider(model):
        return True
    provider = _get_litellm_provider(model)
    return has_legacy_key_for_provider(provider, effective_map)
