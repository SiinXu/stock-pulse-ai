# -*- coding: utf-8 -*-
"""LiteLLM model transport methods."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import litellm

from src.agent.litellm_route_resolution import resolve_agent_litellm_route
from src.config import (
    extra_litellm_params,
    get_api_keys_for_model,
    get_configured_llm_models,
    get_effective_agent_primary_model,
)
from src.llm.errors import call_litellm_with_param_recovery
from src.llm.generation_params import apply_litellm_generation_params
from src.llm.provider_cache import (
    build_provider_cache_route_context,
    normalize_prompt_cache_diagnostics_level,
    resolve_provider_cache_caps,
)

if TYPE_CHECKING:
    from src.agent.llm_adapter import (
        LLMResponse,
        get_thinking_extra_body,
        register_fallback_model_pricing,
        resolve_fallback_litellm_wire_models,
    )

logger = logging.getLogger("src.agent.llm_adapter")


class _TransportMethods:
    """Source container rebound onto ``LLMToolAdapter`` by the facade."""

    @staticmethod
    def _get_model_provider(model: str) -> str:
        """Return LiteLLM provider namespace for model fallback grouping."""
        if "/" in model:
            return model.split("/", 1)[0]
        return "openai"

    def _call_litellm_model(
        self,
        messages: List[Dict[str, Any]],
        tools: List[dict],
        model: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        """Call a specific litellm model with OpenAI-format messages and tools."""
        openai_messages = self._convert_messages(messages, target_model=model)

        # Use short model name (without provider prefix) for thinking model lookup
        model_short = model.split("/")[-1] if "/" in model else model
        extra = get_thinking_extra_body(model_short)

        call_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
        }
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        if timeout is not None:
            call_kwargs["timeout"] = timeout

        if extra:
            call_kwargs["extra_body"] = extra

        if tools:
            call_kwargs["tools"] = tools

        # Use Router for primary model (multi-key), direct litellm for others
        use_channel_router = self._has_channel_config()
        resolution = getattr(self, "_route_resolution", None) or resolve_agent_litellm_route(self._config)
        _router_model_names = set(get_configured_llm_models(resolution.model_list))
        agent_primary_model = resolution.primary_model or get_effective_agent_primary_model(self._config)
        uses_router = (
            bool(use_channel_router and self._router and model in _router_model_names)
            or bool(self._router and model == agent_primary_model and not use_channel_router)
        )
        recovery_model_list = resolution.model_list or self._config.llm_model_list
        if self._router and model == agent_primary_model and not use_channel_router:
            recovery_model_list = self._legacy_router_model_list or self._config.llm_model_list
        if not uses_router:
            keys = get_api_keys_for_model(model, self._config)
            if keys:
                call_kwargs["api_key"] = keys[0]
            call_kwargs.update(extra_litellm_params(model, self._config))
        call_kwargs = apply_litellm_generation_params(
            call_kwargs,
            model,
            self._get_temperature() if temperature is None else temperature,
            model_list=recovery_model_list,
        )
        diagnostics_level = normalize_prompt_cache_diagnostics_level(
            getattr(self._config, "llm_prompt_cache_diagnostics_level", "off")
        )
        if diagnostics_level != "off":
            route_context = build_provider_cache_route_context(
                model=model,
                call_kwargs=call_kwargs,
                model_list=recovery_model_list,
                call_type="agent",
            )
            caps = resolve_provider_cache_caps(route_context)
            logger.debug(
                "[PromptCache] agent diagnostics provider=%s api_surface=%s verification=%s activation=%s",
                caps.provider,
                caps.api_surface,
                caps.verification_status,
                caps.cache_activation,
            )
        register_fallback_model_pricing(
            resolve_fallback_litellm_wire_models(model, recovery_model_list)
        )
        if use_channel_router and self._router and model in _router_model_names:
            # Channel / YAML path: Router manages all models in its model_list
            response = call_litellm_with_param_recovery(
                lambda kwargs: self._router.completion(**kwargs),
                model=model,
                call_kwargs=call_kwargs,
                model_list=recovery_model_list,
                logger=logger,
            )
        elif self._router and model == agent_primary_model and not use_channel_router:
            # Legacy path: Router for primary model multi-key
            response = call_litellm_with_param_recovery(
                lambda kwargs: self._router.completion(**kwargs),
                model=model,
                call_kwargs=call_kwargs,
                model_list=recovery_model_list,
                logger=logger,
            )
        else:
            # Legacy/direct-env path: direct call (also handles direct-env
            # providers like groq/ or bedrock/ that are not in the Router
            # model_list even when channel mode is active)
            response = call_litellm_with_param_recovery(
                lambda kwargs: litellm.completion(**kwargs),
                model=model,
                call_kwargs=call_kwargs,
                model_list=recovery_model_list,
                logger=logger,
            )

        return self._parse_litellm_response(
            response,
            model,
            openai_messages,
            model_list=recovery_model_list,
        )

    def _get_temperature(self) -> float:
        """Return the raw configured temperature before per-model normalization."""
        return float(self._config.llm_temperature)
