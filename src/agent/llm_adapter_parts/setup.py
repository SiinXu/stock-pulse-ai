# -*- coding: utf-8 -*-
"""LiteLLM backend and route initialization methods."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List

import litellm
from litellm import Router

from src.agent.litellm_route_resolution import resolve_agent_litellm_route
from src.config import (
    extra_litellm_params,
    get_api_keys_for_model,
    get_effective_agent_primary_model,
)
from src.llm.backend_registry import (
    AUTO_AGENT_BACKEND_ID,
    GENERATION_ONLY_BACKEND_IDS,
    LITELLM_BACKEND_ID,
    resolve_agent_generation_backend_id,
)
from src.llm.generation_backend import GenerationError, GenerationErrorCode
from src.utils.sanitize import log_safe_exception

if TYPE_CHECKING:
    from src.agent.llm_adapter import _CUSTOM_MODEL_PRICING

logger = logging.getLogger("src.agent.llm_adapter")


class _SetupMethods:
    """Source container rebound onto ``LLMToolAdapter`` by the facade."""

    @staticmethod
    def _register_custom_model_pricing() -> None:
        """Register custom model pricing for models not in LiteLLM's built-in price list.

        This prevents cost calculation errors for MiniMax-M2.7 and similar models.
        """
        for model_name, pricing in _CUSTOM_MODEL_PRICING.items():
            try:
                litellm.register_model(
                    {
                        model_name: pricing
                    }
                )
                logger.debug(f"Registered custom pricing for {model_name}")
            except Exception as exc:  # broad-exception: optional_metadata - Optional pricing registration is safely logged.
                log_safe_exception(
                    logger,
                    "Custom model pricing registration skipped",
                    exc,
                    error_code="agent_model_pricing_registration_failed",
                    level=logging.DEBUG,
                    context={"model": model_name},
                )

    def _has_channel_config(self) -> bool:
        """Check if multi-channel config (channels / YAML) is active."""
        return bool(self._config.llm_model_list) and not all(
            e.get('model_name', '').startswith('__legacy_') for e in self._config.llm_model_list
        )

    def _init_litellm(self) -> None:
        """Initialize litellm Router from channels / YAML / legacy keys."""
        config = self._config
        self._legacy_router_model_list = []
        try:
            self._generation_backend_id = resolve_agent_generation_backend_id(config)
        except GenerationError as exc:
            self._backend_error = exc
            log_safe_exception(
                logger,
                "Agent LLM backend configuration error",
                exc,
                error_code="agent_backend_configuration_error",
            )
            return
        if self._generation_backend_id != LITELLM_BACKEND_ID:
            self._backend_error = GenerationError(
                error_code=GenerationErrorCode.UNSUPPORTED_TOOL_CALLING,
                stage="generation",
                retryable=False,
                fallbackable=False,
                backend=self._generation_backend_id,
                provider=self._generation_backend_id,
                details={
                    "field": "AGENT_GENERATION_BACKEND",
                    "requested_backend": self._generation_backend_id,
                    "supported_tool_backend": LITELLM_BACKEND_ID,
                },
            )
            logger.error(
                "Agent LLM backend %s does not support tool calling",
                self._generation_backend_id,
            )
            return

        self._route_resolution = resolve_agent_litellm_route(config)
        litellm_model = self._route_resolution.primary_model or get_effective_agent_primary_model(config)
        if not self._route_resolution.available and litellm_model:
            self._backend_error = GenerationError(
                error_code=GenerationErrorCode.UNSUPPORTED_TOOL_CALLING,
                stage="generation",
                retryable=False,
                fallbackable=False,
                backend=LITELLM_BACKEND_ID,
                provider="agent",
                details={
                    "field": "AGENT_LITELLM_MODEL",
                    "reason": self._route_resolution.reason,
                    "primary_model": litellm_model,
                },
            )
            logger.error("Agent LLM unavailable: %s", self._route_resolution.reason)
            return
        if not litellm_model:
            generation_backend = str(
                getattr(config, "generation_backend", LITELLM_BACKEND_ID) or LITELLM_BACKEND_ID
            ).strip().lower()
            agent_backend = str(
                getattr(config, "agent_generation_backend", AUTO_AGENT_BACKEND_ID)
                or AUTO_AGENT_BACKEND_ID
            ).strip().lower()
            if generation_backend in GENERATION_ONLY_BACKEND_IDS and agent_backend == AUTO_AGENT_BACKEND_ID:
                self._backend_error = GenerationError(
                    error_code=GenerationErrorCode.UNSUPPORTED_TOOL_CALLING,
                    stage="generation",
                    retryable=False,
                    fallbackable=False,
                    backend=generation_backend,
                    provider=generation_backend,
                    details={
                        "field": "AGENT_GENERATION_BACKEND",
                        "requested_backend": AUTO_AGENT_BACKEND_ID,
                        "generation_backend": generation_backend,
                        "supported_tool_backend": LITELLM_BACKEND_ID,
                        "reason": "litellm_agent_backend_unavailable",
                    },
                )
                logger.error(
                    "Agent auto backend cannot inherit %s because it does not support tool calling",
                    generation_backend,
                )
                return
            logger.warning("Agent LLM: no effective primary model configured")
            return

        # --- Channel / YAML path ---
        if self._has_channel_config():
            model_list = self._route_resolution.model_list
            if not model_list:
                self._backend_error = GenerationError(
                    error_code=GenerationErrorCode.UNSUPPORTED_TOOL_CALLING,
                    stage="generation",
                    retryable=False,
                    fallbackable=False,
                    backend=LITELLM_BACKEND_ID,
                    provider="agent",
                    details={
                        "field": "AGENT_LITELLM_MODEL",
                        "reason": self._route_resolution.reason or "no_safe_agent_models",
                        "primary_model": litellm_model,
                    },
                )
                logger.warning("Agent LLM: no Agent-safe channel deployments after Hermes filtering")
                return
            self._router = Router(
                model_list=model_list,
                routing_strategy="simple-shuffle",
                num_retries=2,
            )
            unique_models = list(dict.fromkeys(
                e['litellm_params']['model'] for e in model_list
            ))
            logger.info(
                f"Agent LLM: Router initialized from channels/YAML — "
                f"{len(model_list)} deployment(s), models: {unique_models}"
            )
            return

        # --- Legacy path ---
        keys = get_api_keys_for_model(litellm_model, config)
        if not keys:
            logger.info(
                f"Agent LLM: litellm initialized (model={litellm_model}, "
                f"API key from environment)"
            )
            self._litellm_available = True
            return

        if len(keys) > 1:
            ep = extra_litellm_params(litellm_model, config)
            legacy_model_list = [
                {
                    "model_name": litellm_model,
                    "litellm_params": {
                        "model": litellm_model,
                        "api_key": k,
                        **ep,
                    },
                }
                for k in keys
            ]
            self._legacy_router_model_list = legacy_model_list
            self._router = Router(
                model_list=legacy_model_list,
                routing_strategy="simple-shuffle",
                num_retries=2,
            )
            logger.info(
                f"Agent LLM: Legacy Router initialized with {len(keys)} keys "
                f"for {litellm_model}"
            )
        else:
            logger.info(f"Agent LLM: litellm initialized (model={litellm_model})")
        self._litellm_available = True

    @property
    def is_available(self) -> bool:
        """True if litellm is configured and at least one API key is present."""
        if self._backend_error is not None:
            return False
        return self._router is not None or self._litellm_available

    @property
    def primary_provider(self) -> str:
        """Provider name extracted from litellm_model prefix."""
        model = get_effective_agent_primary_model(self._config)
        if "/" in model:
            return model.split("/")[0]
        return model or "none"
