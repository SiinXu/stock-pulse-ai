# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Static LLM provider catalog data and its dependency-free accessors.

Leaf module: it holds the raw provider metadata plus the accessors that need no
runtime configuration, so ``src.config`` and ``src.llm.provider_catalog`` can
both read provider metadata without importing each other. The credential/base
URL *enrichment* (which derives requirement flags from the backend config
contract) stays in ``provider_catalog`` because it depends on ``src.config``.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

# Static provider metadata. ``default_base_url == ""`` means the provider either
# uses its SDK default endpoint (official Gemini / Anthropic) or must have a
# user-supplied endpoint (custom). ``is_custom`` distinguishes those two cases.
_PROVIDERS: List[Dict[str, Any]] = [
    {
        "id": "aihubmix", "label_zh": "AIHubmix（聚合平台）", "label_en": "AIHubmix (Aggregator)", "protocol": "openai",
        "default_base_url": "https://aihubmix.com/v1",
        "credential_url": "https://aihubmix.com/", "console_url": "https://aihubmix.com/",
        "models_url": None, "docs_url": None,
        "capabilities": ["openai-compatible", "aggregator"], "is_local": False, "is_custom": False,
    },
    {
        "id": "anspire", "label_zh": "Anspire Open（一站式模型+搜索）", "label_en": "Anspire Open (Models + Search)", "protocol": "openai",
        "default_base_url": "https://open-gateway.anspire.cn/v6",
        "credential_url": "https://open.anspire.cn/",
        "console_url": "https://open.anspire.cn/",
        "models_url": None,
        "docs_url": "https://docs.litellm.ai/docs/providers/openai_compatible",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "deepseek", "label_zh": "DeepSeek 官方", "label_en": "DeepSeek Official", "protocol": "deepseek",
        "default_base_url": "https://api.deepseek.com",
        "credential_url": "https://platform.deepseek.com/api_keys",
        "console_url": "https://platform.deepseek.com/",
        "models_url": "https://api-docs.deepseek.com/quick_start/pricing",
        "docs_url": "https://api-docs.deepseek.com/",
        "capabilities": ["official-api", "openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "dashscope", "label_zh": "通义千问（DashScope）", "label_en": "Qwen (DashScope)", "protocol": "openai",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "credential_url": "https://bailian.console.aliyun.com/?apiKey=1#/api-key",
        "console_url": "https://bailian.console.aliyun.com/",
        "models_url": "https://help.aliyun.com/zh/model-studio/text-generation-model/",
        "docs_url": "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope",
        "capabilities": ["openai-compatible", "model-discovery"], "is_local": False, "is_custom": False,
    },
    {
        "id": "zhipu", "label_zh": "智谱 GLM", "label_en": "Zhipu GLM", "protocol": "openai",
        "default_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "credential_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "console_url": "https://open.bigmodel.cn/usercenter/overview",
        "models_url": "https://docs.bigmodel.cn/cn/guide/start/model-overview",
        "docs_url": "https://docs.bigmodel.cn/cn/guide/start/introduction",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "moonshot", "label_zh": "Moonshot（月之暗面）", "label_en": "Moonshot AI", "protocol": "openai",
        "default_base_url": "https://api.moonshot.cn/v1",
        "credential_url": "https://platform.moonshot.cn/console/api-keys",
        "console_url": "https://platform.moonshot.cn/console",
        "models_url": "https://platform.kimi.com/docs/models",
        "docs_url": "https://platform.kimi.com/docs/",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "minimax", "label_zh": "MiniMax 官方", "label_en": "MiniMax Official", "protocol": "openai",
        "default_base_url": "https://api.minimax.io/v1",
        "credential_url": "https://platform.minimax.io/user-center/basic-information/interface-key",
        "console_url": "https://platform.minimax.io/",
        "models_url": "https://platform.minimax.io/docs/api-reference/models/openai/list-models",
        "docs_url": "https://platform.minimax.io/docs/api-reference/text-chat",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "volcengine", "label_zh": "火山方舟（豆包）", "label_en": "Volcano Engine Ark (Doubao)", "protocol": "openai",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "credential_url": "https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey",
        "console_url": "https://console.volcengine.com/ark/",
        "models_url": "https://www.volcengine.com/docs/82379/1949118",
        "docs_url": "https://www.volcengine.com/docs/82379/2121998",
        "capabilities": ["openai-compatible"], "is_local": False, "is_custom": False,
    },
    {
        "id": "siliconflow", "label_zh": "硅基流动（SiliconFlow）", "label_en": "SiliconFlow", "protocol": "openai",
        "default_base_url": "https://api.siliconflow.cn/v1",
        "credential_url": "https://cloud.siliconflow.cn/account/ak",
        "console_url": "https://cloud.siliconflow.cn/",
        "models_url": "https://docs.siliconflow.cn/quickstart/models",
        "docs_url": "https://docs.siliconflow.cn/",
        "capabilities": ["openai-compatible", "model-discovery"], "is_local": False, "is_custom": False,
    },
    {
        "id": "openrouter", "label_zh": "OpenRouter", "label_en": "OpenRouter", "protocol": "openai",
        "default_base_url": "https://openrouter.ai/api/v1",
        "credential_url": "https://openrouter.ai/settings/keys",
        "console_url": "https://openrouter.ai/settings/keys",
        "models_url": "https://openrouter.ai/models",
        "docs_url": "https://openrouter.ai/docs/api/api-reference/models/get-models",
        "capabilities": ["openai-compatible", "aggregator", "model-discovery"], "is_local": False, "is_custom": False,
    },
    {
        "id": "gemini", "label_zh": "Gemini 官方", "label_en": "Gemini Official", "protocol": "gemini",
        "default_base_url": "",
        "credential_url": "https://aistudio.google.com/app/apikey",
        "console_url": "https://aistudio.google.com/",
        "models_url": "https://ai.google.dev/gemini-api/docs/models",
        "docs_url": "https://ai.google.dev/gemini-api/docs",
        "capabilities": ["official-api", "vision"], "is_local": False, "is_custom": False,
    },
    {
        "id": "anthropic", "label_zh": "Anthropic 官方", "label_en": "Anthropic Official", "protocol": "anthropic",
        "default_base_url": "",
        "credential_url": "https://console.anthropic.com/settings/keys",
        "console_url": "https://console.anthropic.com/",
        "models_url": "https://docs.anthropic.com/en/docs/about-claude/models/all-models",
        "docs_url": "https://docs.anthropic.com/en/api/getting-started",
        "capabilities": ["official-api"], "is_local": False, "is_custom": False,
    },
    {
        "id": "openai", "label_zh": "OpenAI 官方", "label_en": "OpenAI Official", "protocol": "openai",
        "default_base_url": "https://api.openai.com/v1",
        "credential_url": "https://platform.openai.com/api-keys",
        "console_url": "https://platform.openai.com/",
        "models_url": "https://platform.openai.com/docs/models",
        "docs_url": "https://platform.openai.com/docs/overview",
        "capabilities": ["official-api", "openai-compatible", "model-discovery"], "is_local": False, "is_custom": False,
    },
    {
        "id": "ollama", "label_zh": "Ollama（本地）", "label_en": "Ollama (Local)", "protocol": "ollama",
        "default_base_url": "http://127.0.0.1:11434",
        "credential_url": None, "console_url": None,
        "models_url": "https://ollama.com/library",
        "docs_url": "https://github.com/ollama/ollama/blob/main/docs/api.md",
        "capabilities": ["local-runtime"], "is_local": True, "is_custom": False,
    },
    {
        "id": "custom", "label_zh": "自定义兼容服务", "label_en": "Custom compatible service", "protocol": "openai",
        "default_base_url": "",
        "credential_url": None, "console_url": None, "models_url": None, "docs_url": None,
        "capabilities": [], "is_local": False, "is_custom": True,
    },
]


def get_provider_ids() -> List[str]:
    """Return every canonical Provider ID in catalog order."""
    return [provider["id"] for provider in _PROVIDERS]


def get_static_provider(provider_id: str) -> Optional[Dict[str, Any]]:
    """Return a caller-immune copy of one provider's static catalog metadata.

    Unlike ``provider_catalog.get_provider`` this exposes only the raw static
    fields (no config-derived requirement flags), so callers that need the
    stable ``protocol`` / ``default_base_url`` / ``is_custom`` metadata can read
    it without depending on ``src.config``.
    """
    normalized = str(provider_id or "").strip().lower()
    if not normalized:
        return None
    return next(
        (deepcopy(provider) for provider in _PROVIDERS if provider["id"] == normalized),
        None,
    )
