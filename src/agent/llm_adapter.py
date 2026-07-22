# -*- coding: utf-8 -*-
"""
Multi-provider LLM Tool-Calling Adapter.

Normalizes function-calling / tool-use across all providers into a unified
interface consumed by the AgentExecutor, via LiteLLM.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

import litellm
from litellm import Router

from src.config import (
    extra_litellm_params,
    get_api_keys_for_model,
    get_config,
    get_configured_llm_models,
    get_effective_agent_primary_model,
)
from src.agent.facade_binding import bind_facade_methods as _bind_facade_methods
from src.agent.litellm_route_resolution import (
    AgentLiteLLMRouteResolution,
    resolve_agent_litellm_route,
)
from src.agent.llm_adapter_parts.calls import _CallMethods
from src.agent.llm_adapter_parts.messages import _MessageMethods
from src.agent.llm_adapter_parts.setup import _SetupMethods
from src.agent.llm_adapter_parts.transport import _TransportMethods
from src.agent.provider_trace import (
    TRACE_MODEL_KEY,
    TRACE_PROVIDER_KEY,
    resolved_model_provider_identity,
    resolved_provider_namespace,
    trace_model_matches,
)
from src.agent.public_contract import (
    AGENT_LLM_FAILURE_MESSAGE,
    sanitize_agent_diagnostic,
)
from src.llm.errors import call_litellm_with_param_recovery
from src.llm.backend_registry import (
    AUTO_AGENT_BACKEND_ID,
    GENERATION_ONLY_BACKEND_IDS,
    LITELLM_BACKEND_ID,
    resolve_agent_generation_backend_id,
)
from src.llm.generation_backend import GenerationError, GenerationErrorCode
from src.llm.generation_params import apply_litellm_generation_params, resolve_litellm_wire_model
from src.llm.usage import attach_message_hmacs, extract_usage_payload, normalize_litellm_usage
from src.llm.provider_cache import (
    build_provider_cache_route_context,
    filter_prompt_cache_telemetry,
    normalize_prompt_cache_diagnostics_level,
    resolve_provider_cache_caps,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


def _resolve_litellm_exception(name: str) -> type[BaseException]:
    """Return a catchable LiteLLM exception class even in stubbed test environments."""
    exc = getattr(litellm, name, None)
    if isinstance(exc, type) and issubclass(exc, BaseException):
        return exc

    class _FallbackLiteLLMError(Exception):
        pass

    _FallbackLiteLLMError.__name__ = f"Fallback{name}"
    return _FallbackLiteLLMError


# ============================================================
# Unified response types
# ============================================================

@dataclass
class ToolCall:
    """A single tool call requested by the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]
    thought_signature: Optional[str] = None
    provider_specific_fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""
    content: Optional[str] = None          # text response (final answer)
    tool_calls: List[ToolCall] = field(default_factory=list)  # tool calls to execute
    reasoning_content: Optional[str] = None  # Chain-of-thought (CoT) from DeepSeek thinking mode; must be passed back in multi-turn assistant messages; None for other providers
    provider_blocks: List[Dict[str, Any]] = field(default_factory=list)  # Opaque provider content blocks (e.g. Claude thinking/redacted_thinking)
    usage: Dict[str, Any] = field(default_factory=dict)       # token usage info
    provider: str = ""                     # which provider handled this call
    model: str = ""                        # full model name used (e.g. gemini/gemini-2.0-flash), for report meta
    raw: Any = None                        # raw provider response for debugging


# Models that auto-return reasoning_content; do NOT send extra_body (may cause 400).
_AUTO_THINKING_MODELS: List[str] = ["deepseek-reasoner", "deepseek-r1", "qwq"]

# Models that need explicit opt-in via extra_body; payload decoupled from model name.
_OPT_IN_THINKING_MODELS: Dict[str, dict] = {
    "deepseek-chat": {"thinking": {"type": "enabled"}},
}

# Custom model pricing for models not in LiteLLM's built-in price list.
# Official MiniMax pricing: https://platform.minimax.io/docs/guides/pricing-paygo
# - MiniMax-M3: $0.6/M input tokens, $2.4/M output tokens for prompts <=512K input
#   tokens. Officially supports up to 1M input tokens with a separate higher
#   price tier for the >512K bucket; we conservatively register only the
#   <=512K bucket here because the cost tracker carries a single per-token
#   price and the higher-tier price is not modeled. Long prompts will be
#   cost-estimated using the <=512K rate; treat the estimate as a floor in
#   that case.
# - MiniMax-M2.7: $0.3/M input tokens, $1.2/M output tokens.
# - MiniMax-M2.5: kept as legacy so existing user configs continue to report
#   accurate cost. Still listed as a Legacy Model on the official pricing
#   page; remove only after we have user-facing migration guidance.
_CUSTOM_MODEL_PRICING: Dict[str, dict] = {
    "MiniMax-M3": {
        "supports_function_calling": True,
        "supports_vision": True,
        "supports_audio_input": False,
        "supports_audio_output": False,
        # Project-conservative bound for the <=512K input-token price tier.
        # MiniMax-M3 supports up to 1M input tokens officially, but pricing
        # changes above 512K; see comment block above.
        "context_window": 512000,
        "max_tokens": 128000,
        "input_cost_per_token": 0.0000006,   # $0.6 / 1M tokens (<=512K input bucket)
        "output_cost_per_token": 0.0000024,   # $2.4 / 1M tokens (<=512K input bucket)
    },
    "MiniMax-M2.7": {
        "supports_function_calling": True,
        "supports_vision": False,
        "supports_audio_input": False,
        "supports_audio_output": False,
        "context_window": 100000,
        "max_tokens": 10000,
        "input_cost_per_token": 0.0000003,   # $0.3 / 1M tokens
        "output_cost_per_token": 0.0000012,   # $1.2 / 1M tokens
    },
    # Legacy model retained for backward compatibility with existing user
    # configs; values match the previous M2.5 entry to avoid silently
    # zero-costing prior cost estimates.
    "MiniMax-M2.5": {
        "supports_function_calling": True,
        "supports_vision": False,
        "supports_audio_input": False,
        "supports_audio_output": False,
        "context_window": 245760,
        "max_tokens": 8192,
        "input_cost_per_token": 0.0000003,   # $0.3 / 1M tokens (legacy)
        "output_cost_per_token": 0.0000012,   # $1.2 / 1M tokens (legacy)
    },
}

_FALLBACK_MODEL_PRICING: Dict[str, Any] = {
    "supports_function_calling": True,
    "supports_vision": False,
    "supports_audio_input": False,
    "supports_audio_output": False,
    "context_window": 100000,
    "max_tokens": 10000,
    "input_cost_per_token": 0.0,
    "output_cost_per_token": 0.0,
}
_FALLBACK_MODEL_PRICING_REGISTERED: set[str] = set()


def _split_provider_model(model: str) -> Tuple[str, str]:
    normalized = (model or "").strip()
    if not normalized:
        return "", ""
    if "/" in normalized:
        provider, remainder = normalized.split("/", 1)
        return provider.lower(), remainder.strip()
    return "openai", normalized


def _object_to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            dumped = value.dict()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass
    result: Dict[str, Any] = {}
    for key in ("type", "text", "content", "thinking", "signature", "data"):
        if hasattr(value, key):
            result[key] = getattr(value, key)
    return result


def _provider_specific_fields_from(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    data = _object_to_dict(value)
    return data if isinstance(data, dict) else {}


def _extract_provider_blocks(choice: Any) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Return opaque provider blocks and joined text block content, if present."""
    block_sources = []
    message = getattr(choice, "message", None)
    for owner in (message, choice):
        if owner is None:
            continue
        for attr in ("content", "content_blocks", "provider_blocks", "thinking_blocks"):
            value = getattr(owner, attr, None)
            if isinstance(value, list):
                block_sources.append(value)

    blocks: List[Dict[str, Any]] = []
    text_parts: List[str] = []
    for source in block_sources:
        for raw_block in source:
            block = _object_to_dict(raw_block)
            if not block:
                continue
            blocks.append(block)
            block_type = str(block.get("type") or "")
            text = block.get("text") or block.get("content")
            if block_type == "text" and text:
                text_parts.append(str(text))
    return blocks, ("".join(text_parts).strip() or None)


def _message_trace_matches_target(
    message: Dict[str, Any],
    target_model: Optional[str],
    *,
    target_provider: Optional[str] = None,
) -> bool:
    """Whether provider-specific fields in ``message`` can be sent to target."""
    if not target_model:
        return True
    trace_provider = message.get(TRACE_PROVIDER_KEY)
    trace_model = message.get(TRACE_MODEL_KEY)
    if not trace_provider and not trace_model:
        return True
    return trace_model_matches(
        trace_provider,
        trace_model,
        target_model,
        current_provider=target_provider,
    )


def _model_matches(model: str, entries: List[str]) -> bool:
    """Check if model name matches any entry (exact or prefix with version suffix)."""
    if not model:
        return False
    m = model.lower().strip()
    for e in entries:
        if m == e or m.startswith(e + "-"):
            return True
    return False


def _get_opt_in_payload(model: str, opt_in: Dict[str, dict]) -> Optional[dict]:
    """Return extra_body payload for opt-in thinking models, or None."""
    if not model:
        return None
    m = model.lower().strip()
    for key, payload in opt_in.items():
        if m == key or m.startswith(key + "-"):
            return payload
    return None


def get_thinking_extra_body(model: str) -> Optional[dict]:
    """Return extra_body for thinking mode, or None.

    - Auto-thinking models (_AUTO_THINKING_MODELS: deepseek-reasoner, deepseek-r1, qwq):
      These models automatically return reasoning_content in API responses; sending
      extra_body would cause 400 because the API already enables thinking by default.
      Return None to avoid duplicate activation.
    - Opt-in models (_OPT_IN_THINKING_MODELS: deepseek-chat): Return the activation
      payload to explicitly enable thinking mode.
    - All other models: Return None (no thinking mode).
    """
    if _model_matches(model, _AUTO_THINKING_MODELS):
        return None
    return _get_opt_in_payload(model, _OPT_IN_THINKING_MODELS)


def resolve_fallback_litellm_wire_models(
    model: str,
    model_list: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """Resolve all wire models reachable from a configured alias."""
    normalized_model = (model or "").strip()
    if not normalized_model:
        return []

    resolved: List[str] = []
    if model_list:
        for entry in model_list:
            if not isinstance(entry, dict):
                continue
            entry_model_name = str(entry.get("model_name", "") or "").strip()
            if not entry_model_name:
                entry_params = entry.get("litellm_params", {}) or {}
                entry_model_name = str(entry_params.get("model") or "").strip()
            if entry_model_name != normalized_model:
                continue

            entry_params = entry.get("litellm_params", {}) or {}
            wire_model = str(entry_params.get("model") or normalized_model).strip()
            if wire_model and wire_model not in resolved:
                resolved.append(wire_model)

    if not resolved:
        wire_model = resolve_litellm_wire_model(normalized_model, model_list)
        if wire_model and wire_model not in resolved:
            resolved.append(wire_model)
    return resolved


# ============================================================
# LLM Tool Adapter
# ============================================================

class LLMToolAdapter:
    """Unified adapter for tool-calling via LiteLLM.

    Supports all providers (Gemini, Anthropic, OpenAI, DeepSeek, etc.) through
    a single litellm.completion() interface with optional Router for multi-key
    load balancing.
    """

    def __init__(self, config=None):
        config = config or get_config()
        self._config = config
        self._router = None          # litellm Router (multi-key primary model)
        self._legacy_router_model_list: List[Dict[str, Any]] = []
        self._litellm_available = False
        self._backend_error: Optional[GenerationError] = None
        self._generation_backend_id = ""
        self._route_resolution: AgentLiteLLMRouteResolution = AgentLiteLLMRouteResolution(False)
        self._register_custom_model_pricing()
        self._init_litellm()

    def call_completion(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[dict]] = None,
        provider: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        """Shared completion path for both tool and text-only calls."""
        config = self._config
        if self._backend_error is not None:
            error_msg = (
                "Agent generation backend configuration error: "
                f"{self._backend_error.message}"
            )
            logger.error(error_msg)
            return LLMResponse(content=error_msg, provider="error")
        route_resolution = resolve_agent_litellm_route(config)
        models_to_try = route_resolution.models_to_try
        if not models_to_try:
            error_msg = (
                "No LLM configured. Please set LITELLM_MODEL, LLM_CHANNELS, "
                "or provider API keys before using Agent."
            )
            logger.error(error_msg)
            return LLMResponse(content=error_msg, provider="error")
        started_at = time.time()
        providers = [self._get_model_provider(model) for model in models_to_try]

        last_diagnostic = "unknown"
        hit_rate_limit = False
        for idx, model in enumerate(models_to_try):
            remaining_timeout = timeout
            if timeout is not None and timeout > 0:
                remaining_timeout = max(0.0, float(timeout) - (time.time() - started_at))
                if remaining_timeout <= 0:
                    last_diagnostic = sanitize_agent_diagnostic(TimeoutError(
                        f"LLM completion timed out before trying fallback model {model}"
                    ))
                    break
            try:
                return self._call_litellm_model(
                    messages,
                    tools or [],
                    model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=remaining_timeout,
                )
            except Exception as exc:
                diagnostic = sanitize_agent_diagnostic(exc)
                last_diagnostic = diagnostic
                if isinstance(exc, _resolve_litellm_exception("RateLimitError")):
                    log_safe_exception(
                        logger,
                        "Agent LLM rate-limited",
                        exc,
                        error_code="agent_llm_rate_limited",
                        level=logging.WARNING,
                        context={"model": model},
                    )
                    hit_rate_limit = True

                    # Avoid blind backoff across different providers; cross-provider
                    # fallback usually means different accounts/rate-limit buckets.
                    should_backoff = (
                        idx + 1 < len(models_to_try)
                        and providers[idx] == providers[idx + 1]
                    )
                    if should_backoff:
                        backoff_sleep = min(2.0, (time.time() - started_at) * 0.1 + 0.5)
                        if timeout is not None and timeout > 0:
                            remaining_timeout = max(0.0, float(timeout) - (time.time() - started_at))
                            if remaining_timeout > 0:
                                time.sleep(min(backoff_sleep, remaining_timeout))
                        else:
                            time.sleep(backoff_sleep)
                    continue
                if isinstance(exc, _resolve_litellm_exception("ContextWindowExceededError")):
                    log_safe_exception(
                        logger,
                        "Agent LLM context window exceeded",
                        exc,
                        error_code="agent_llm_context_window_exceeded",
                        level=logging.WARNING,
                        context={"model": model},
                    )
                    continue
                log_safe_exception(
                    logger,
                    "Agent LLM call failed",
                    exc,
                    error_code="agent_llm_call_failed",
                    level=logging.WARNING,
                    context={"model": model},
                )
                continue

        public_message = (
            f"{AGENT_LLM_FAILURE_MESSAGE} (rate-limit encountered during fallback)."
            if hit_rate_limit
            else AGENT_LLM_FAILURE_MESSAGE
        )
        logger.error(
            "%s diagnostic=%s",
            public_message,
            last_diagnostic,
        )
        return LLMResponse(content=public_message, provider="error")


def register_fallback_model_pricing(models: Iterable[str]) -> None:
    """Register zero-cost pricing for unknown OpenAI-compatible models."""
    if not models:
        return
    register = getattr(litellm, "register_model", None)
    if not callable(register):
        return
    cost_map = getattr(litellm, "model_cost", {})
    if not isinstance(cost_map, dict):
        cost_map = {}
    for model in models:
        provider, wire_model = _split_provider_model(str(model))
        if provider != "openai":
            continue
        if not wire_model or wire_model.startswith("__legacy_"):
            continue
        custom_pricing = _CUSTOM_MODEL_PRICING.get(wire_model)
        if custom_pricing is not None:
            if wire_model in cost_map:
                continue
            try:
                register({wire_model: dict(custom_pricing)})
                logger.debug("Registered custom pricing for %s", wire_model)
            except Exception as exc:
                log_safe_exception(
                    logger,
                    "Custom pricing registration failed; trying fallback pricing",
                    exc,
                    error_code="agent_model_pricing_registration_failed",
                    level=logging.DEBUG,
                    context={"model": wire_model},
                )
            else:
                continue
        if wire_model in cost_map or wire_model in _FALLBACK_MODEL_PRICING_REGISTERED:
            continue
        try:
            register({wire_model: dict(_FALLBACK_MODEL_PRICING)})
            _FALLBACK_MODEL_PRICING_REGISTERED.add(wire_model)
            logger.debug("Registered fallback pricing for %s", wire_model)
        except Exception as exc:
            log_safe_exception(
                logger,
                "Fallback pricing registration skipped",
                exc,
                error_code="agent_model_pricing_registration_failed",
                level=logging.DEBUG,
                context={"model": wire_model},
            )


# Preserve the legacy module namespace used by descriptors rebound from the
# private source containers. The tuple also makes the complete compatibility
# dependency surface explicit for static analysis and regression guards.
_LLM_ADAPTER_COMPAT_EXPORTS = (
    AGENT_LLM_FAILURE_MESSAGE,
    AUTO_AGENT_BACKEND_ID,
    GENERATION_ONLY_BACKEND_IDS,
    GenerationError,
    GenerationErrorCode,
    LITELLM_BACKEND_ID,
    LLMResponse,
    Router,
    ToolCall,
    _CUSTOM_MODEL_PRICING,
    _extract_provider_blocks,
    _message_trace_matches_target,
    _provider_specific_fields_from,
    _resolve_litellm_exception,
    apply_litellm_generation_params,
    attach_message_hmacs,
    build_provider_cache_route_context,
    call_litellm_with_param_recovery,
    extra_litellm_params,
    extract_usage_payload,
    filter_prompt_cache_telemetry,
    get_api_keys_for_model,
    get_configured_llm_models,
    get_effective_agent_primary_model,
    get_thinking_extra_body,
    json,
    litellm,
    log_safe_exception,
    logger,
    logging,
    normalize_litellm_usage,
    normalize_prompt_cache_diagnostics_level,
    register_fallback_model_pricing,
    resolve_agent_generation_backend_id,
    resolve_agent_litellm_route,
    resolve_fallback_litellm_wire_models,
    resolve_provider_cache_caps,
    resolved_model_provider_identity,
    resolved_provider_namespace,
    sanitize_agent_diagnostic,
    time,
    uuid,
)

_RETAINED_CALL_COMPLETION = LLMToolAdapter.__dict__["call_completion"]
delattr(LLMToolAdapter, "call_completion")

_SETUP_METHOD_NAMES = _bind_facade_methods(
    LLMToolAdapter, _SetupMethods, globals(), evaluate_annotations=True
)
_CALL_METHOD_NAMES = _bind_facade_methods(
    LLMToolAdapter, _CallMethods, globals(), evaluate_annotations=True
)
setattr(LLMToolAdapter, "call_completion", _RETAINED_CALL_COMPLETION)
_TRANSPORT_METHOD_NAMES = _bind_facade_methods(
    LLMToolAdapter, _TransportMethods, globals(), evaluate_annotations=True
)
_MESSAGE_METHOD_NAMES = _bind_facade_methods(
    LLMToolAdapter, _MessageMethods, globals(), evaluate_annotations=True
)
del _RETAINED_CALL_COMPLETION
