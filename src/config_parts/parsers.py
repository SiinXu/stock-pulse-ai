"""Pure value parsers and LLM route helpers for :mod:`src.config`."""

import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from urllib.parse import urlparse

from src.llm import generation_params as llm_generation_params
from src.llm.hermes import is_reserved_hermes_name, route_identity_candidates
from src.config_parts.defaults import (
    AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE,
    AGENT_CONTEXT_COMPRESSION_PROFILES,
    NEWS_STRATEGY_WINDOWS,
    SUPPORTED_LLM_CHANNEL_PROTOCOLS,
    AgentContextCompressionPreset,
    _FALSEY_ENV_VALUES,
    _MANAGED_LITELLM_KEY_PROVIDERS,
    logger,
)

if TYPE_CHECKING:
    from src.config_parts.model import Config

def parse_env_bool(value: Optional[str], default: bool = False) -> bool:
    """Parse common truthy/falsey environment-style values."""
    if value is None:
        return default
    normalized = value.strip().lower()
    if not normalized:
        return default
    return normalized not in _FALSEY_ENV_VALUES


def parse_env_int(
    value: Optional[str],
    default: int,
    *,
    field_name: str,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    """Parse an integer env value with warning + fallback semantics."""
    raw_value = value
    if raw_value is None or not str(raw_value).strip():
        parsed = int(default)
    else:
        try:
            parsed = int(str(raw_value).strip())
        except (TypeError, ValueError):
            logger.warning(
                "%s=%r is not a valid integer; falling back to %s",
                field_name,
                raw_value,
                default,
            )
            parsed = int(default)

    if minimum is not None and parsed < minimum:
        logger.warning(
            "%s=%r is below minimum %s; clamping to %s",
            field_name,
            parsed,
            minimum,
            minimum,
        )
        parsed = minimum
    if maximum is not None and parsed > maximum:
        logger.warning(
            "%s=%r is above maximum %s; clamping to %s",
            field_name,
            parsed,
            maximum,
            maximum,
        )
        parsed = maximum
    return parsed


def parse_env_float(
    value: Optional[str],
    default: float,
    *,
    field_name: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    """Parse a float env value with warning + fallback semantics."""
    raw_value = value
    if raw_value is None or not str(raw_value).strip():
        parsed = float(default)
    else:
        try:
            parsed = float(str(raw_value).strip())
        except (TypeError, ValueError):
            logger.warning(
                "%s=%r is not a valid number; falling back to %s",
                field_name,
                raw_value,
                default,
            )
            parsed = float(default)

    if minimum is not None and parsed < minimum:
        logger.warning(
            "%s=%r is below minimum %s; clamping to %s",
            field_name,
            parsed,
            minimum,
            minimum,
        )
        parsed = minimum
    if maximum is not None and parsed > maximum:
        logger.warning(
            "%s=%r is above maximum %s; clamping to %s",
            field_name,
            parsed,
            maximum,
            maximum,
        )
        parsed = maximum
    return parsed


def normalize_news_strategy_profile(value: Optional[str]) -> str:
    """Normalize news strategy profile to known values."""
    candidate = (value or "short").strip().lower()
    return candidate if candidate in NEWS_STRATEGY_WINDOWS else "short"


def resolve_news_window_days(news_max_age_days: int, news_strategy_profile: Optional[str]) -> int:
    """Resolve effective news window days from profile and global max-age."""
    profile = normalize_news_strategy_profile(news_strategy_profile)
    profile_days = NEWS_STRATEGY_WINDOWS.get(profile, NEWS_STRATEGY_WINDOWS["short"])
    return max(1, min(max(1, int(news_max_age_days)), profile_days))


def normalize_agent_context_compression_profile(value: Optional[str]) -> str:
    """Normalize visible-chat context compression profile values."""
    candidate = (value or AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE).strip().lower()
    if candidate in AGENT_CONTEXT_COMPRESSION_PROFILES:
        return candidate
    logger.warning(
        "Invalid AGENT_CONTEXT_COMPRESSION_PROFILE=%r; falling back to %s",
        value,
        AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE,
    )
    return AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE


def get_agent_context_compression_preset(profile: Optional[str]) -> AgentContextCompressionPreset:
    """Return the preset for a normalized profile, falling back to balanced."""
    normalized = normalize_agent_context_compression_profile(profile)
    return AGENT_CONTEXT_COMPRESSION_PROFILES[normalized]


def parse_agent_context_compression_int(
    value: Optional[str],
    default: int,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int:
    """Parse compression integers; empty/invalid/out-of-range values follow preset defaults."""
    raw_value = value
    if raw_value is None or not str(raw_value).strip():
        return int(default)
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        logger.warning(
            "%s=%r is not a valid integer; falling back to preset default %s",
            field_name,
            raw_value,
            default,
        )
        return int(default)
    if parsed < minimum or parsed > maximum:
        logger.warning(
            "%s=%r is outside supported range [%s, %s]; falling back to preset default %s",
            field_name,
            parsed,
            minimum,
            maximum,
            default,
        )
        return int(default)
    return parsed


def canonicalize_llm_channel_protocol(value: Optional[str]) -> str:
    """Normalize a protocol label into a LiteLLM provider identifier."""
    candidate = (value or "").strip().lower().replace("-", "_")
    aliases = {
        "openai_compatible": "openai",
        "openai_compat": "openai",
        "claude": "anthropic",
        "google": "gemini",
        "vertex": "vertex_ai",
        "vertexai": "vertex_ai",
    }
    return aliases.get(candidate, candidate)


# Local endpoint hostnames that exempt a channel from requiring an API key.
# Exposed via the provider-catalog API so the Web derives the same rule from
# this single authority instead of hardcoding its own host list.
LLM_EMPTY_API_KEY_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "0.0.0.0"})


def resolve_llm_channel_protocol(
    protocol: Optional[str],
    *,
    base_url: Optional[str] = None,
    models: Optional[List[str]] = None,
    channel_name: Optional[str] = None,
) -> str:
    """Resolve the effective protocol for a channel."""
    explicit = canonicalize_llm_channel_protocol(protocol)
    if explicit in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
        return explicit

    for model in models or []:
        if "/" not in model:
            continue
        prefix = canonicalize_llm_channel_protocol(model.split("/", 1)[0])
        if prefix in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
            return prefix

    # Infer from channel name (e.g. "deepseek" -> deepseek, "gemini" -> gemini)
    if channel_name:
        name_protocol = canonicalize_llm_channel_protocol(channel_name)
        if name_protocol in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
            return name_protocol

    if base_url:
        parsed = urlparse(base_url)
        if parsed.hostname in LLM_EMPTY_API_KEY_HOSTNAMES:
            # Default to openai for local servers (vLLM, LM Studio, LocalAI, etc.).
            # Ollama users should set PROTOCOL=ollama explicitly or name the channel "ollama".
            return "openai"
        return "openai"

    return ""


def channel_allows_empty_api_key(protocol: Optional[str], base_url: Optional[str]) -> bool:
    """Return True when a channel can run without an API key."""
    resolved_protocol = resolve_llm_channel_protocol(protocol, base_url=base_url)
    if resolved_protocol == "ollama":
        return True
    parsed = urlparse(base_url or "")
    return parsed.hostname in LLM_EMPTY_API_KEY_HOSTNAMES


def normalize_llm_channel_model(model: str, protocol: Optional[str], base_url: Optional[str] = None) -> str:
    """Attach a provider prefix when the model omits it."""
    normalized_model = model.strip()
    if not normalized_model:
        return normalized_model

    resolved_protocol = resolve_llm_channel_protocol(protocol, base_url=base_url, models=[normalized_model])

    if "/" in normalized_model:
        # The model already has a slash, e.g. 'deepseek-ai/DeepSeek-V3'.
        # Check if the prefix is a known LiteLLM provider; if so, keep it.
        # Otherwise (e.g. HuggingFace-style IDs on SiliconFlow), prepend
        # the resolved protocol so LiteLLM routes via the correct handler.
        raw_prefix, remainder = normalized_model.split("/", 1)
        prefix = raw_prefix.lower()
        canonical_prefix = canonicalize_llm_channel_protocol(prefix)
        known_providers = _MANAGED_LITELLM_KEY_PROVIDERS | set(SUPPORTED_LLM_CHANNEL_PROTOCOLS) | {
            "minimax",
            "cohere", "huggingface", "bedrock", "sagemaker", "azure",
            "replicate", "together_ai", "palm", "text-completion-openai",
            "command-r", "groq", "cerebras", "fireworks_ai", "friendliai",
        }
        if prefix in known_providers:
            return normalized_model
        if canonical_prefix in known_providers:
            return f"{canonical_prefix}/{remainder}"
        # Not a real provider prefix — add one so LiteLLM routes correctly.
        if resolved_protocol:
            return f"{resolved_protocol}/{normalized_model}"
        return normalized_model

    if not resolved_protocol:
        return normalized_model
    return f"{resolved_protocol}/{normalized_model}"


def get_configured_llm_models(model_list: List[Dict[str, Any]]) -> List[str]:
    """Return non-legacy model names declared in Router model_list order.

    Uses the top-level ``model_name`` (the routing alias that users set in
    LITELLM_MODEL) rather than ``litellm_params.model`` (the wire-level
    model identifier).  For channel-built entries both are identical, but
    YAML configs may define a friendly alias that differs from the
    underlying provider/model path.
    """
    models: List[str] = []
    seen: set = set()
    for entry in model_list or []:
        # Prefer top-level model_name (router routing key); fall back to
        # litellm_params.model for entries that omit it.
        name = str(entry.get("model_name") or "").strip()
        if not name:
            params = entry.get("litellm_params", {}) or {}
            name = str(params.get("model") or "").strip()
        if (
            not name
            or name.startswith("__legacy_")
            or name in seen
        ):
            continue
        seen.add(name)
        models.append(name)
    return models


def resolve_litellm_wire_model(
    model: str,
    model_list: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Resolve a router alias to its underlying LiteLLM wire model."""
    return llm_generation_params.resolve_litellm_wire_model(model, model_list)


def resolve_litellm_thinking_enabled(
    model: str,
    model_list: Optional[List[Dict[str, Any]]] = None,
    request_overrides: Optional[Dict[str, Any]] = None,
) -> Optional[bool]:
    """Resolve whether the outgoing LiteLLM request explicitly enables thinking."""
    return llm_generation_params.resolve_litellm_thinking_enabled(
        model,
        model_list=model_list,
        request_overrides=request_overrides,
    )


def get_fixed_litellm_temperature(
    model: str,
    model_list: Optional[List[Dict[str, Any]]] = None,
    request_overrides: Optional[Dict[str, Any]] = None,
) -> Optional[float]:
    """Return a provider-mandated temperature for known strict models."""
    return llm_generation_params.get_fixed_litellm_temperature(
        model,
        model_list=model_list,
        request_overrides=request_overrides,
    )


def normalize_litellm_temperature(
    model: str,
    temperature: Optional[float],
    *,
    default: float = 0.7,
    model_list: Optional[List[Dict[str, Any]]] = None,
    request_overrides: Optional[Dict[str, Any]] = None,
) -> float:
    """Normalize temperature before sending a LiteLLM request."""
    return llm_generation_params.normalize_litellm_temperature(
        model,
        temperature,
        default=default,
        model_list=model_list,
        request_overrides=request_overrides,
    )


def resolve_unified_llm_temperature(model: str) -> float:
    """Resolve the raw unified LLM temperature with backward-compatible fallbacks."""
    llm_temperature_raw = os.getenv("LLM_TEMPERATURE")
    if llm_temperature_raw and llm_temperature_raw.strip():
        try:
            return float(llm_temperature_raw)
        except (ValueError, TypeError):
            pass

    provider_temperature_env = {
        "gemini": "GEMINI_TEMPERATURE",
        "vertex_ai": "GEMINI_TEMPERATURE",
        "anthropic": "ANTHROPIC_TEMPERATURE",
        "openai": "OPENAI_TEMPERATURE",
        "deepseek": "OPENAI_TEMPERATURE",
    }
    preferred_env = provider_temperature_env.get(_get_litellm_provider(model))
    if preferred_env:
        preferred_value = os.getenv(preferred_env)
        if preferred_value and preferred_value.strip():
            try:
                return float(preferred_value)
            except (ValueError, TypeError):
                pass

    for env_name in ("GEMINI_TEMPERATURE", "ANTHROPIC_TEMPERATURE", "OPENAI_TEMPERATURE"):
        env_value = os.getenv(env_name)
        if env_value and env_value.strip():
            try:
                return float(env_value)
            except (ValueError, TypeError):
                continue

    return 0.7


def _get_litellm_provider(model: str) -> str:
    """Extract the LiteLLM provider prefix from a model string."""
    if not model:
        return ""
    from src.llm.model_ref import decode_model_ref

    try:
        decoded = decode_model_ref(model)
    except ValueError:
        return ""
    if decoded is not None:
        model = decoded.runtime_route
    if "/" in model:
        return model.split("/", 1)[0]
    return "openai"


def _uses_direct_env_provider(model: str) -> bool:
    """Whether runtime handles the model via direct litellm env/provider resolution."""
    provider = _get_litellm_provider(model)
    return bool(provider) and provider not in _MANAGED_LITELLM_KEY_PROVIDERS


def _matches_route_set(model: str, routes: set[str]) -> bool:
    """Loose safety match for Hermes/provenance checks, not normal route availability."""
    from src.llm.model_ref import decode_model_ref

    try:
        decoded = decode_model_ref(model)
    except ValueError:
        decoded = None
    if decoded is not None:
        model = decoded.runtime_route
    return bool(route_identity_candidates(model) & set(routes or set()))


def _matches_exact_route(model: str, routes: set[str]) -> bool:
    """Match the Router's top-level model_name exactly for normal availability checks."""
    normalized_model = str(model or "").strip()
    return bool(normalized_model) and normalized_model in set(routes or set())


def normalize_agent_litellm_model(
    model: str,
    configured_models: Optional[set[str]] = None,
) -> str:
    """Normalize AGENT_LITELLM_MODEL while preserving configured router aliases."""
    normalized_model = (model or "").strip()
    if not normalized_model:
        return ""
    from src.llm.model_ref import is_model_ref, normalize_model_ref

    # Preserve the reserved namespace for authoritative version validation.
    # Never reinterpret a ModelRef as a bare OpenAI model.
    if normalized_model.startswith("modelref:"):
        if is_model_ref(normalized_model):
            return normalize_model_ref(normalized_model)
        return normalized_model
    if "/" not in normalized_model:
        if configured_models and normalized_model in configured_models:
            return normalized_model
        return f"openai/{normalized_model}"
    return normalized_model


def get_effective_agent_primary_model(config: "Config") -> str:
    """Return the effective Agent primary model with fallback inheritance."""
    configured_router_models = set(
        get_configured_llm_models(getattr(config, "llm_model_list", []) or [])
    )
    configured_agent_model = normalize_agent_litellm_model(
        getattr(config, "agent_litellm_model", ""),
        configured_models=configured_router_models,
    )
    if configured_agent_model:
        return configured_agent_model
    return (getattr(config, "litellm_model", "") or "").strip()


def get_effective_agent_models_to_try(config: "Config") -> List[str]:
    """Return Agent model try-order: primary + global fallbacks (deduped)."""
    configured_router_models = set(
        get_configured_llm_models(getattr(config, "llm_model_list", []) or [])
    )
    raw_models = [get_effective_agent_primary_model(config)] + (
        getattr(config, "litellm_fallback_models", []) or []
    )
    seen = set()
    ordered_models: List[str] = []
    for model in raw_models:
        normalized_model = (model or "").strip()
        if not normalized_model:
            continue
        dedupe_key = normalize_agent_litellm_model(
            normalized_model,
            configured_models=configured_router_models,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        ordered_models.append(normalized_model)
    return ordered_models

for _compat_name, _compat_value in tuple(globals().items()):
    if getattr(_compat_value, "__module__", None) == __name__:
        _compat_value.__module__ = "src.config"

del _compat_name, _compat_value
