# -*- coding: utf-8 -*-
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

from typing import Any, Dict, List, Optional

# Static provider metadata. ``default_base_url == ""`` means the provider either
# uses its SDK default endpoint (official Gemini / Anthropic) or must have a
# user-supplied endpoint (custom). ``is_custom`` distinguishes those two cases.
_PROVIDERS: List[Dict[str, Any]] = [
    {
        "id": "aihubmix", "label": "AIHubmix（聚合平台）", "protocol": "openai",
        "default_base_url": "https://aihubmix.com/v1",
        "capabilities": ["openai-compatible", "aggregator"], "is_local": False, "is_custom": False,
        "credential_url": "https://aihubmix.com/token",
        "console_url": "https://aihubmix.com/",
        "docs_url": "https://doc.aihubmix.com/",
    },
    {
        "id": "anspire", "label": "Anspire Open（一站式模型+搜索）", "protocol": "openai",
        "default_base_url": "https://open-gateway.anspire.cn/v6",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
        "credential_url": "https://open.anspire.cn/",
        "console_url": "https://open.anspire.cn/",
        "docs_url": "https://open.anspire.cn/",
    },
    {
        "id": "deepseek", "label": "DeepSeek 官方", "protocol": "deepseek",
        "default_base_url": "https://api.deepseek.com",
        "capabilities": ["official-api", "openai-compatible"], "is_local": False, "is_custom": False,
        "credential_url": "https://platform.deepseek.com/api_keys",
        "console_url": "https://platform.deepseek.com/",
        "models_url": "https://api-docs.deepseek.com/quick_start/pricing",
        "docs_url": "https://api-docs.deepseek.com/",
    },
    {
        "id": "dashscope", "label": "通义千问（Dashscope）", "protocol": "openai",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "capabilities": ["openai-compatible", "model-discovery"], "is_local": False, "is_custom": False,
        "credential_url": "https://bailian.console.aliyun.com/?apiKey=1#/api-key",
        "console_url": "https://bailian.console.aliyun.com/",
        "models_url": "https://help.aliyun.com/zh/model-studio/text-generation-model/",
        "docs_url": "https://help.aliyun.com/zh/model-studio/developer-reference/use-qwen-by-calling-api",
    },
    {
        "id": "zhipu", "label": "智谱 GLM", "protocol": "openai",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
        "credential_url": "https://bigmodel.cn/usercenter/proj-mgmt/apikeys",
        "console_url": "https://bigmodel.cn/usercenter/",
        "models_url": "https://docs.bigmodel.cn/cn/guide/start/model-overview",
        "docs_url": "https://docs.bigmodel.cn/",
    },
    {
        "id": "moonshot", "label": "Moonshot（月之暗面）", "protocol": "openai",
        "default_base_url": "https://api.moonshot.cn/v1",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
        "credential_url": "https://platform.moonshot.cn/console/api-keys",
        "console_url": "https://platform.moonshot.cn/console/",
        "models_url": "https://platform.kimi.com/docs/models",
        "docs_url": "https://platform.kimi.com/docs/",
    },
    {
        "id": "minimax", "label": "MiniMax 官方", "protocol": "openai",
        "default_base_url": "https://api.minimax.io/v1",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
        "credential_url": "https://platform.minimax.io/user-center/basic-information/interface-key",
        "console_url": "https://platform.minimax.io/",
        "models_url": "https://platform.minimax.io/docs/api-reference/models/openai/list-models",
        "docs_url": "https://platform.minimax.io/docs/api-reference/text-chat",
    },
    {
        "id": "volcengine", "label": "火山方舟（豆包）", "protocol": "openai",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
        "credential_url": "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
        "console_url": "https://console.volcengine.com/ark/",
        "models_url": "https://www.volcengine.com/docs/82379/1949118",
        "docs_url": "https://www.volcengine.com/docs/82379/2121998",
    },
    {
        "id": "siliconflow", "label": "硅基流动（SiliconFlow）", "protocol": "openai",
        "default_base_url": "https://api.siliconflow.cn/v1",
        "capabilities": ["openai-compatible", "model-discovery"], "is_local": False, "is_custom": False,
        "credential_url": "https://cloud.siliconflow.cn/account/ak",
        "console_url": "https://cloud.siliconflow.cn/",
        "models_url": "https://docs.siliconflow.cn/quickstart/models",
        "docs_url": "https://docs.siliconflow.cn/",
    },
    {
        "id": "openrouter", "label": "OpenRouter", "protocol": "openai",
        "default_base_url": "https://openrouter.ai/api/v1",
        "capabilities": ["openai-compatible", "aggregator", "model-discovery"], "is_local": False, "is_custom": False,
        "credential_url": "https://openrouter.ai/settings/keys",
        "console_url": "https://openrouter.ai/settings/keys",
        "models_url": "https://openrouter.ai/models",
        "docs_url": "https://openrouter.ai/docs/",
    },
    {
        "id": "gemini", "label": "Gemini 官方", "protocol": "gemini",
        "default_base_url": "",
        "capabilities": ["official-api", "vision"], "is_local": False, "is_custom": False,
        "credential_url": "https://aistudio.google.com/app/apikey",
        "console_url": "https://aistudio.google.com/",
        "models_url": "https://ai.google.dev/gemini-api/docs/models",
        "docs_url": "https://ai.google.dev/gemini-api/docs",
    },
    {
        "id": "anthropic", "label": "Anthropic 官方", "protocol": "anthropic",
        "default_base_url": "",
        "capabilities": ["official-api"], "is_local": False, "is_custom": False,
        "credential_url": "https://console.anthropic.com/settings/keys",
        "console_url": "https://console.anthropic.com/",
        "models_url": "https://docs.anthropic.com/en/docs/about-claude/models/all-models",
        "docs_url": "https://docs.anthropic.com/",
    },
    {
        "id": "openai", "label": "OpenAI 官方", "protocol": "openai",
        "default_base_url": "https://api.openai.com/v1",
        "capabilities": ["official-api", "openai-compatible", "model-discovery"], "is_local": False, "is_custom": False,
        "credential_url": "https://platform.openai.com/api-keys",
        "console_url": "https://platform.openai.com/",
        "models_url": "https://platform.openai.com/docs/models",
        "docs_url": "https://platform.openai.com/docs/api-reference",
    },
    {
        "id": "ollama", "label": "Ollama（本地）", "protocol": "ollama",
        "default_base_url": "http://127.0.0.1:11434",
        "capabilities": ["local-runtime"], "is_local": True, "is_custom": False,
        "models_url": "https://ollama.com/search",
        "docs_url": "https://github.com/ollama/ollama/blob/main/docs/api.md",
    },
    {
        "id": "custom", "label": "自定义兼容服务", "protocol": "openai",
        "default_base_url": "",
        "capabilities": [], "is_local": False, "is_custom": True,
    },
]

_DISCOVERY_PROTOCOLS = {"openai", "deepseek", "ollama"}


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
            "label": provider["label"],
            "protocol": protocol,
            "default_base_url": default_base_url,
            "capabilities": list(provider["capabilities"]),
            "requires_api_key": requires_api_key,
            # Only custom needs a user-provided endpoint; officials use their
            # prefilled or SDK default endpoint.
            "requires_base_url": bool(provider["is_custom"]),
            "supports_discovery": supports_discovery,
            "is_local": bool(provider["is_local"]),
            "is_custom": bool(provider["is_custom"]),
            "credential_url": provider.get("credential_url"),
            "console_url": provider.get("console_url"),
            "models_url": provider.get("models_url"),
            "docs_url": provider.get("docs_url"),
        })
    return catalog


def get_provider_ids() -> List[str]:
    """Return every canonical Provider ID in catalog order."""
    return [provider["id"] for provider in _PROVIDERS]


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
