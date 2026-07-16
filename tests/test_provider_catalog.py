# -*- coding: utf-8 -*-
"""Contract tests for the authoritative LLM provider catalog.

These guard three invariants that a prior full-suite flake exposed:

1. The catalog ships NO concrete model IDs (model names age fast and must never
   seed a Connection's default models).
2. ``get_provider_catalog()`` returns caller-immune data — a caller mutating the
   result cannot pollute the shared catalog or a later caller.
3. Exercising the catalog / available-models path does not leave global state
   that breaks a subsequent System Config validation (ordering isolation).
"""
from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path

from tests._llm_env_isolation import restore_ambient_llm_env, strip_ambient_llm_env
from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.config import Config, channel_allows_empty_api_key  # noqa: E402
from src.core.config_manager import ConfigManager  # noqa: E402
from src.llm.provider_catalog import (  # noqa: E402
    get_empty_api_key_hosts,
    get_provider_catalog,
    get_provider_ids,
)
from src.services.system_config_service import SystemConfigService  # noqa: E402

# A concrete model ID is a *versioned* vendor model name (gpt-4o,
# claude-sonnet-4-6, gemini-3-flash, deepseek-v4, qwen3.5, MiniMax-M2, llama3.2,
# glm-5 ...). The pattern requires the version-ish suffix so it does NOT flag
# bare provider ids / labels / protocols (openai, minimax, "MiniMax 官方").
_MODEL_ID_PATTERN = re.compile(
    r"(?i)("
    r"gpt-\w|\bo[1-9]\b|claude-\w|gemini-\d|deepseek-v\d|qwen\d|"
    r"minimax-m|doubao-\w|kimi-k\d|glm-\d|llama\d"
    r")"
)


class ProviderCatalogContractTestCase(unittest.TestCase):
    def test_catalog_ships_no_concrete_model_ids(self) -> None:
        catalog = get_provider_catalog()
        self.assertTrue(catalog)
        for entry in catalog:
            # No placeholder_models field at all.
            self.assertNotIn("placeholder_models", entry)
            # And no other string field smuggles a concrete model name.
            for key, value in entry.items():
                if isinstance(value, str):
                    self.assertIsNone(
                        _MODEL_ID_PATTERN.search(value),
                        f"catalog field {key}={value!r} contains a concrete model ID",
                    )

    def test_catalog_only_declares_the_allowed_metadata_fields(self) -> None:
        allowed = {
            "id", "label", "label_zh", "label_en", "protocol", "default_base_url", "capabilities",
            "requires_api_key", "requires_base_url", "supports_discovery",
            "is_local", "is_custom", "credential_url", "console_url",
            "models_url", "docs_url",
        }
        for entry in get_provider_catalog():
            self.assertEqual(set(entry.keys()), allowed)

    def test_every_builtin_provider_has_bilingual_labels(self) -> None:
        chinese_script = re.compile(r"[\u3400-\u9fff]")
        for entry in get_provider_catalog():
            self.assertTrue(entry["label_zh"].strip(), entry["id"])
            self.assertTrue(entry["label_en"].strip(), entry["id"])
            self.assertIsNone(chinese_script.search(entry["label_en"]), entry["id"])
            # `label` remains the deprecated compatibility spelling.
            self.assertEqual(entry["label"], entry["label_zh"])

    def test_catalog_exposes_optional_provider_owned_quick_links(self) -> None:
        providers = {entry["id"]: entry for entry in get_provider_catalog()}
        for field in ("credential_url", "console_url", "models_url", "docs_url"):
            self.assertTrue(providers["openai"][field].startswith("https://"))
        self.assertIsNone(providers["ollama"]["credential_url"])
        self.assertTrue(providers["ollama"]["models_url"].startswith("https://"))
        self.assertIsNone(providers["custom"]["credential_url"])
        self.assertIsNone(providers["custom"]["docs_url"])

    def test_catalog_return_is_caller_immune(self) -> None:
        first = get_provider_catalog()
        # Mutate the returned data aggressively.
        first[0]["label"] = "MUTATED"
        first[0]["capabilities"].append("mutated-capability")
        first.append({"id": "injected"})

        second = get_provider_catalog()
        self.assertNotEqual(second[0]["label"], "MUTATED")
        self.assertNotIn("mutated-capability", second[0]["capabilities"])
        self.assertNotIn("injected", [entry["id"] for entry in second])
        # get_provider_ids stays authoritative too.
        self.assertNotIn("injected", get_provider_ids())

    def test_empty_api_key_hosts_mirror_backend_exemption_contract(self) -> None:
        # The catalog API exposes the exact host list the backend validator
        # exempts, so the Web can apply the same rule without hardcoding one.
        hosts = get_empty_api_key_hosts()
        self.assertTrue(hosts)
        self.assertEqual(hosts, sorted(hosts))
        for host in hosts:
            self.assertTrue(
                channel_allows_empty_api_key("openai", f"http://{host}:8000/v1"),
                f"{host} advertised as exempt but backend still requires a key",
            )
        # A remote OpenAI-compatible endpoint still requires a key.
        self.assertNotIn("api.example.com", hosts)
        self.assertFalse(channel_allows_empty_api_key("openai", "https://api.example.com/v1"))
        # Ollama stays exempt regardless of endpoint host.
        self.assertTrue(channel_allows_empty_api_key("ollama", "https://ollama.remote.example/v1"))

    def test_catalog_use_does_not_pollute_later_config_validation(self) -> None:
        # Ordering isolation: touch the catalog / available-models path, then a
        # fresh System Config validation of a minimal cloud connection must still
        # pass — no leaked global model state.
        saved_env = strip_ambient_llm_env()
        temp_dir = tempfile.TemporaryDirectory()
        try:
            # Exercise the catalog + a mutation attempt first.
            catalog = get_provider_catalog()
            catalog[0]["capabilities"].append("noise")
            get_provider_ids()

            env_path = Path(temp_dir.name) / ".env"
            env_path.write_text("LOG_LEVEL=INFO\n", encoding="utf-8")
            os.environ["ENV_FILE"] = str(env_path)
            Config.reset_instance()
            service = SystemConfigService(manager=ConfigManager(env_path=env_path))

            items = [
                {"key": "LLM_CONFIG_MODE", "value": "channels"},
                {"key": "LLM_CHANNELS", "value": "openai"},
                {"key": "LLM_OPENAI_PROTOCOL", "value": "openai"},
                {"key": "LLM_OPENAI_BASE_URL", "value": "https://api.openai.com/v1"},
                {"key": "LLM_OPENAI_API_KEY", "value": "sk-test"},
                {"key": "LLM_OPENAI_MODELS", "value": "gpt-4o-mini"},
                {"key": "LLM_OPENAI_ENABLED", "value": "true"},
                {"key": "LITELLM_MODEL", "value": "openai/gpt-4o-mini"},
            ]
            validation = service.validate(items)
            self.assertTrue(validation["valid"], validation["issues"])
        finally:
            Config.reset_instance()
            os.environ.pop("ENV_FILE", None)
            restore_ambient_llm_env(saved_env)
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
