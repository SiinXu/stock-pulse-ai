# -*- coding: utf-8 -*-
"""Authoritative catalog of LLM model-service providers.

This is the single backend source of truth for provider metadata (labels,
default endpoints, discovery support, capabilities, credential requirements)
shared by the backend and the Web UI. The Web must not maintain a second
business list; it fetches this catalog and derives everything else from it.

Credential/base-URL requirements are *derived* from the existing backend
contract (``channel_allows_empty_api_key``) rather than re-declared here, so
there is a single authority for "does this provider need a key".
"""
from __future__ import annotations

from typing import Any, Dict, List

# Static provider metadata. ``default_base_url == ""`` means the provider either
# uses its SDK default endpoint (official Gemini / Anthropic) or must have a
# user-supplied endpoint (custom). ``is_custom`` distinguishes those two cases.
_PROVIDERS: List[Dict[str, Any]] = [
    {
        "id": "aihubmix", "label": "AIHubmix（聚合平台）", "protocol": "openai",
        "default_base_url": "https://aihubmix.com/v1",
        "placeholder_models": "gpt-5.5,claude-sonnet-4-6,gemini-3.1-pro-preview",
        "capabilities": ["openai-compatible", "aggregator"], "is_local": False, "is_custom": False,
    },
    {
        "id": "anspire", "label": "Anspire Open（一站式模型+搜索）", "protocol": "openai",
        "default_base_url": "https://open-gateway.anspire.cn/v6",
        "placeholder_models": "Doubao-Seed-2.0-lite,Doubao-Seed-2.0-pro,qwen3.5-flash,MiniMax-M2.7",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "deepseek", "label": "DeepSeek 官方", "protocol": "deepseek",
        "default_base_url": "https://api.deepseek.com",
        "placeholder_models": "deepseek-v4-flash,deepseek-v4-pro",
        "capabilities": ["official-api", "openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "dashscope", "label": "通义千问（Dashscope）", "protocol": "openai",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "placeholder_models": "qwen3.6-plus,qwen3.6-flash",
        "capabilities": ["openai-compatible", "model-discovery"], "is_local": False, "is_custom": False,
    },
    {
        "id": "zhipu", "label": "智谱 GLM", "protocol": "openai",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "placeholder_models": "glm-5.1,glm-4.7-flash",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "moonshot", "label": "Moonshot（月之暗面）", "protocol": "openai",
        "default_base_url": "https://api.moonshot.cn/v1",
        "placeholder_models": "kimi-k2.6,kimi-k2.5",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "minimax", "label": "MiniMax 官方", "protocol": "openai",
        "default_base_url": "https://api.minimax.io/v1",
        "placeholder_models": "MiniMax-M3,MiniMax-M2.7,MiniMax-M2.7-highspeed",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "volcengine", "label": "火山方舟（豆包）", "protocol": "openai",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "placeholder_models": "doubao-seed-1-6-251015,doubao-seed-1-6-thinking-251015",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "siliconflow", "label": "硅基流动（SiliconFlow）", "protocol": "openai",
        "default_base_url": "https://api.siliconflow.cn/v1",
        "placeholder_models": "deepseek-ai/DeepSeek-V3.2,Qwen/Qwen3-235B-A22B-Thinking-2507",
        "capabilities": ["openai-compatible", "model-discovery"], "is_local": False, "is_custom": False,
    },
    {
        "id": "openrouter", "label": "OpenRouter", "protocol": "openai",
        "default_base_url": "https://openrouter.ai/api/v1",
        "placeholder_models": "~anthropic/claude-sonnet-latest,~openai/gpt-latest",
        "capabilities": ["openai-compatible", "aggregator", "model-discovery"], "is_local": False, "is_custom": False,
    },
    {
        "id": "gemini", "label": "Gemini 官方", "protocol": "gemini",
        "default_base_url": "",
        "placeholder_models": "gemini-3.1-pro-preview,gemini-3-flash-preview",
        "capabilities": ["official-api", "vision"], "is_local": False, "is_custom": False,
    },
    {
        "id": "anthropic", "label": "Anthropic 官方", "protocol": "anthropic",
        "default_base_url": "",
        "placeholder_models": "claude-sonnet-4-6,claude-opus-4-7",
        "capabilities": ["official-api"], "is_local": False, "is_custom": False,
    },
    {
        "id": "openai", "label": "OpenAI 官方", "protocol": "openai",
        "default_base_url": "https://api.openai.com/v1",
        "placeholder_models": "gpt-5.5,gpt-5.4-mini",
        "capabilities": ["official-api", "openai-compatible", "model-discovery"], "is_local": False, "is_custom": False,
    },
    {
        "id": "ollama", "label": "Ollama（本地）", "protocol": "ollama",
        "default_base_url": "http://127.0.0.1:11434",
        "placeholder_models": "llama3.2,qwen2.5",
        "capabilities": ["local-runtime"], "is_local": True, "is_custom": False,
    },
    {
        "id": "custom", "label": "自定义兼容服务", "protocol": "openai",
        "default_base_url": "",
        "placeholder_models": "model-name-1,model-name-2",
        "capabilities": [], "is_local": False, "is_custom": True,
    },
]

_DISCOVERY_PROTOCOLS = {"openai", "deepseek", "ollama"}


def get_provider_catalog() -> List[Dict[str, Any]]:
    """Return provider metadata enriched with derived requirement flags."""
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
        supports_discovery = (
            "model-discovery" in provider["capabilities"] or protocol in _DISCOVERY_PROTOCOLS
        )
        catalog.append({
            "id": provider["id"],
            "label": provider["label"],
            "protocol": protocol,
            "default_base_url": default_base_url,
            "placeholder_models": provider["placeholder_models"],
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


def get_provider_ids() -> List[str]:
    return [provider["id"] for provider in _PROVIDERS]
