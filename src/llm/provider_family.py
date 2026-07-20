# -*- coding: utf-8 -*-
"""Provider-family inference shared by usage telemetry and prompt-cache routing.

Leaf module: it depends only on the standard library so that both
``src.llm.usage`` and ``src.llm.provider_cache`` can import it without forming
an import cycle. Behavior is identical to the former ``provider_cache`` helpers.
"""

from __future__ import annotations

from typing import Optional, Tuple
from urllib.parse import urlparse

_EXPLICIT_PROVIDER_FAMILY_ALIASES = {
    "anthropic": "anthropic",
    "gemini": "gemini",
    "vertex_ai": "vertex_ai",
    "deepseek": "deepseek",
    "dashscope": "dashscope",
    "qwen": "qwen",
    "moonshot": "moonshot",
    "kimi": "kimi",
    "minimax": "minimax",
    "openrouter": "openrouter",
    "zhipu": "glm",
    "bigmodel": "glm",
    "glm": "glm",
    "stepfun": "stepfun",
    "litellm": "litellm_gateway",
    "litellm_gateway": "litellm_gateway",
}

_API_BASE_HOST_FAMILY_SUFFIXES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("openrouter", ("openrouter.ai",)),
    ("dashscope", ("dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com", "bailian.aliyuncs.com")),
    ("moonshot", ("moonshot.cn",)),
    ("minimax", ("minimax.chat", "minimax.io")),
    ("deepseek", ("deepseek.com",)),
    ("glm", ("bigmodel.cn", "z.ai")),
    ("stepfun", ("stepfun.com", "stepfun.ai")),
)


def infer_provider_family(
    *,
    model: str = "",
    provider: Optional[str] = None,
    api_base: Optional[str] = None,
) -> str:
    normalized_model = (model or "").strip().lower()
    normalized_provider = (provider or "").strip().lower()

    if normalized_provider in _EXPLICIT_PROVIDER_FAMILY_ALIASES:
        return _EXPLICIT_PROVIDER_FAMILY_ALIASES[normalized_provider]

    model_family = _infer_provider_family_from_model(normalized_model)
    if model_family:
        return model_family

    if normalized_provider == "openai":
        return "openai" if _is_native_openai_model(normalized_model) else "openai_compatible"
    api_base_family = _infer_provider_family_from_api_base(api_base)
    if api_base_family:
        return api_base_family
    if normalized_model.startswith("openai/"):
        return "openai" if _is_native_openai_model(normalized_model) else "openai_compatible"
    if normalized_provider == "openai_compatible":
        return "openai_compatible"
    if "/" in normalized_model:
        return normalized_model.split("/", 1)[0]
    return normalized_provider or "unknown"


def _infer_provider_family_from_model(normalized_model: str) -> Optional[str]:
    if not normalized_model:
        return None
    if normalized_model.startswith("openai/~"):
        return "openrouter"
    if normalized_model.startswith("anthropic/"):
        return "anthropic"
    if normalized_model.startswith("gemini/"):
        return "gemini"
    if normalized_model.startswith("vertex_ai/"):
        return "vertex_ai"
    if normalized_model.startswith("step/"):
        return "stepfun"
    if _is_glm_model(normalized_model):
        return "glm"

    model_name = normalized_model.split("/", 1)[1] if normalized_model.startswith("openai/") else normalized_model
    if model_name.startswith(("qwen", "qwq", "qvq")):
        return "qwen"
    if model_name.startswith("kimi"):
        return "kimi"
    if model_name.startswith("moonshot"):
        return "moonshot"
    if model_name.startswith("minimax"):
        return "minimax"
    if model_name.startswith("deepseek"):
        return "deepseek"
    if model_name.startswith("step"):
        return "stepfun"
    return None


def _infer_provider_family_from_api_base(api_base: Optional[str]) -> Optional[str]:
    host = _api_base_host(api_base)
    if not host:
        return None
    for family, suffixes in _API_BASE_HOST_FAMILY_SUFFIXES:
        if any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes):
            return family
    return None


def _api_base_host(api_base: Optional[str]) -> str:
    text = (api_base or "").strip().lower()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return (parsed.hostname or "").strip(".")


def _is_native_openai_model(normalized_model: str) -> bool:
    model_name = normalized_model.split("/", 1)[1] if normalized_model.startswith("openai/") else normalized_model
    return model_name.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-", "gpt4"))


def _is_glm_model(normalized_model: str) -> bool:
    if not normalized_model:
        return False
    model_name = normalized_model.split("/", 1)[-1]
    return model_name.startswith(("glm", "chatglm")) or "z-ai" in normalized_model or "zai-" in normalized_model
