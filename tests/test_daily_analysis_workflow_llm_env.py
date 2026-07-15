# -*- coding: utf-8 -*-
"""Static checks for LLM provider channel mappings in 00-daily-analysis.yml."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT_DIR / ".github/workflows/00-daily-analysis.yml"
ENV_EXAMPLE_PATH = ROOT_DIR / ".env.example"

EXPECTED_TEMPLATE_CHANNELS = {
    "aihubmix",
    "deepseek",
    "dashscope",
    "zhipu",
    "moonshot",
    "minimax",
    "volcengine",
    "siliconflow",
    "openrouter",
    "gemini",
    "anthropic",
    "openai",
    "ollama",
}


def _extract_provider_templates() -> dict[str, str]:
    # The authoritative provider channel list (ids + default endpoints) is the
    # backend provider catalog; the frontend llmProviderTemplates.ts is now
    # presentation-only and no longer declares channel/baseUrl business data.
    from src.llm.provider_catalog import get_provider_catalog

    templates = {
        str(entry["id"]): str(entry["default_base_url"])
        for entry in get_provider_catalog()
        if str(entry["id"]) != "custom"
    }
    assert templates, "No provider entries were found in the backend provider catalog"
    assert EXPECTED_TEMPLATE_CHANNELS.issubset(templates.keys())
    assert "ark" not in templates
    return templates


def _load_daily_analysis_env() -> dict[str, str]:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["analyze"]["steps"]
    analyze_step = next((step for step in steps if step.get("name") == "执行股票分析"), None)
    available_step_names = [step.get("name", "<unnamed>") for step in steps]
    assert analyze_step is not None, (
        "Expected 00-daily-analysis.yml job analyze to include a step named "
        f"'执行股票分析'; available step names: {available_step_names}"
    )
    return analyze_step["env"]


def test_daily_analysis_maps_all_provider_template_channels() -> None:
    templates = _extract_provider_templates()
    env = _load_daily_analysis_env()

    for channel in templates:
        prefix = f"LLM_{channel.upper()}_"
        for suffix in (
            "PROVIDER",
            "PROTOCOL",
            "BASE_URL",
            "API_KEY",
            "API_KEYS",
            "MODELS",
            "ENABLED",
            "EXTRA_HEADERS",
        ):
            assert f"{prefix}{suffix}" in env

    assert not any(key.startswith("LLM_ARK_") for key in env)


def test_daily_analysis_maps_fixed_named_connections_with_provider_identity() -> None:
    env = _load_daily_analysis_env()

    for connection in ("PRIMARY", "SECONDARY"):
        for suffix in (
            "PROVIDER",
            "PROTOCOL",
            "BASE_URL",
            "API_KEY",
            "API_KEYS",
            "MODELS",
            "ENABLED",
            "EXTRA_HEADERS",
        ):
            assert f"LLM_{connection}_{suffix}" in env

    for suffix in ("PROVIDER", "PROTOCOL", "BASE_URL", "API_KEY", "MODELS", "ENABLED"):
        assert f"LLM_HERMES_{suffix}" in env


def test_daily_analysis_keeps_channel_secrets_in_secrets_context() -> None:
    templates = _extract_provider_templates()
    env = _load_daily_analysis_env()

    for channel in templates:
        upper = channel.upper()
        for suffix in ("API_KEY", "API_KEYS"):
            key = f"LLM_{upper}_{suffix}"
            assert env[key] == f"${{{{ secrets.{key} }}}}"

        for suffix in ("PROVIDER", "PROTOCOL", "BASE_URL", "MODELS", "ENABLED", "EXTRA_HEADERS"):
            key = f"LLM_{upper}_{suffix}"
            assert f"vars.{key}" in env[key]
            assert f"secrets.{key}" in env[key]


def test_daily_analysis_maps_usage_hmac_config_safely() -> None:
    env = _load_daily_analysis_env()

    assert env["LLM_USAGE_HMAC_SECRET"] == "${{ secrets.LLM_USAGE_HMAC_SECRET }}"
    assert "vars.LLM_USAGE_HMAC_SECRET" not in env["LLM_USAGE_HMAC_SECRET"]
    assert "vars.LLM_USAGE_HMAC_KEY_VERSION" in env["LLM_USAGE_HMAC_KEY_VERSION"]
    assert "secrets.LLM_USAGE_HMAC_KEY_VERSION" in env["LLM_USAGE_HMAC_KEY_VERSION"]


def test_daily_analysis_maps_prompt_cache_config() -> None:
    env = _load_daily_analysis_env()

    for key in (
        "LLM_PROMPT_CACHE_TELEMETRY_ENABLED",
        "LLM_PROMPT_CACHE_HINTS_ENABLED",
        "LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL",
    ):
        assert key in env
        assert f"vars.{key}" in env[key]
        assert f"secrets.{key}" in env[key]


def test_daily_analysis_maps_generation_backend_runtime_config() -> None:
    env = _load_daily_analysis_env()

    for key in (
        "GENERATION_BACKEND",
        "GENERATION_FALLBACK_BACKEND",
        "GENERATION_BACKEND_TIMEOUT_SECONDS",
        "GENERATION_BACKEND_MAX_OUTPUT_BYTES",
        "GENERATION_BACKEND_MAX_CONCURRENCY",
        "LOCAL_CLI_BACKEND_MAX_CONCURRENCY",
        "AGENT_GENERATION_BACKEND",
    ):
        assert key in env
        assert f"vars.{key}" in env[key]
        assert f"secrets.{key}" in env[key]


def test_daily_analysis_generation_fallback_defaults_to_litellm() -> None:
    env = _load_daily_analysis_env()
    expression = env["GENERATION_FALLBACK_BACKEND"]

    assert expression == (
        "${{ vars.GENERATION_FALLBACK_BACKEND || "
        "secrets.GENERATION_FALLBACK_BACKEND || 'litellm' }}"
    )


def test_env_example_includes_provider_template_channel_examples() -> None:
    templates = _extract_provider_templates()
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    for channel, base_url in templates.items():
        upper = channel.upper()
        assert f"LLM_CHANNELS={channel}" in env_example
        assert f"LLM_{upper}_PROVIDER={channel}" in env_example
        assert f"LLM_{upper}_MODELS=" in env_example

        if channel != "ollama":
            assert f"LLM_{upper}_API_KEY=" in env_example
        if base_url:
            assert f"LLM_{upper}_BASE_URL=" in env_example
        if channel != "ollama":
            assert f"LLM_{upper}_PROTOCOL=" in env_example

    assert "LLM_CHANNELS=ark" not in env_example
    assert "LLM_ARK_" not in env_example
