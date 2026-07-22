# -*- coding: utf-8 -*-
"""AlphaSift documented LLM bridge API contracts."""

from __future__ import annotations

from tests.alphasift_api_test_support import (
    sys,
    SimpleNamespace,
    MagicMock,
    patch,
    HTTPException,
    Config,
    alphasift_service,
    DEFAULT_ALPHASIFT_TEST_SPEC,
    _make_adapter_module,
    _AlphaSiftApiTestCaseBase,
)


class AlphaSiftOpportunitiesApiTestCase(_AlphaSiftApiTestCaseBase):
    def test_screen_bridges_dsa_llm_config_into_alphasift_runtime(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="gemini/gemini-2.5-flash",
            litellm_fallback_models=["deepseek/deepseek-chat"],
            llm_channels=[
                {
                    "name": "gemini",
                    "protocol": "gemini",
                    "enabled": True,
                    "base_url": "",
                    "api_keys": ["dsa-gemini-key"],
                    "models": ["gemini/gemini-2.5-flash"],
                    "extra_headers": {"x-tenant": "dsa"},
                }
            ],
        )
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **kwargs):
            captured["env"] = {
                "LITELLM_MODEL": alphasift_service.os.environ.get("LITELLM_MODEL"),
                "LITELLM_FALLBACK_MODELS": alphasift_service.os.environ.get("LITELLM_FALLBACK_MODELS"),
                "LLM_CHANNELS": alphasift_service.os.environ.get("LLM_CHANNELS"),
                "LLM_GEMINI_PROTOCOL": alphasift_service.os.environ.get("LLM_GEMINI_PROTOCOL"),
                "LLM_GEMINI_API_KEYS": alphasift_service.os.environ.get("LLM_GEMINI_API_KEYS"),
                "LLM_GEMINI_EXTRA_HEADERS": alphasift_service.os.environ.get("LLM_GEMINI_EXTRA_HEADERS"),
                "GEMINI_API_KEY": alphasift_service.os.environ.get("GEMINI_API_KEY"),
                "LLM_CANDIDATE_CONTEXT_ENABLED": alphasift_service.os.environ.get("LLM_CANDIDATE_CONTEXT_ENABLED"),
                "LLM_CANDIDATE_CONTEXT_PROVIDERS": alphasift_service.os.environ.get("LLM_CANDIDATE_CONTEXT_PROVIDERS"),
                "LLM_CANDIDATE_MULTIPLIER": alphasift_service.os.environ.get("LLM_CANDIDATE_MULTIPLIER"),
                "LLM_MAX_CANDIDATES": alphasift_service.os.environ.get("LLM_MAX_CANDIDATES"),
                "DAILY_SOURCE": alphasift_service.os.environ.get("DAILY_SOURCE"),
                "DAILY_FETCH_RETRIES": alphasift_service.os.environ.get("DAILY_FETCH_RETRIES"),
                "DAILY_FETCH_MAX_WORKERS": alphasift_service.os.environ.get("DAILY_FETCH_MAX_WORKERS"),
                "SNAPSHOT_SOURCE_PRIORITY": alphasift_service.os.environ.get("SNAPSHOT_SOURCE_PRIORITY"),
                "ALPHASIFT_DATA_DIR": alphasift_service.os.environ.get("ALPHASIFT_DATA_DIR"),
                "ALPHASIFT_FALLBACK_SNAPSHOT_PATH": alphasift_service.os.environ.get("ALPHASIFT_FALLBACK_SNAPSHOT_PATH"),
                "ALPHASIFT_DAILY_HISTORY_CACHE_DIR": alphasift_service.os.environ.get("ALPHASIFT_DAILY_HISTORY_CACHE_DIR"),
                "ALPHASIFT_INDUSTRY_PROVIDER_CACHE_DIR": alphasift_service.os.environ.get("ALPHASIFT_INDUSTRY_PROVIDER_CACHE_DIR"),
            }
            captured["context"] = kwargs.get("context")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(
                alphasift_service.os.environ,
                {
                    "GEMINI_API_KEY": "outer-key",
                    "SNAPSHOT_SOURCE_PRIORITY": "",
                    "LLM_CANDIDATE_CONTEXT_ENABLED": "true",
                    "LLM_CANDIDATE_MULTIPLIER": "",
                    "LLM_MAX_CANDIDATES": "",
                    "DAILY_FETCH_RETRIES": "",
                    "DAILY_FETCH_MAX_WORKERS": "",
                },
                clear=False,
            ),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)
            self.assertEqual(alphasift_service.os.environ.get("GEMINI_API_KEY"), "outer-key")

        runtime_env = captured["env"]
        self.assertIsInstance(runtime_env, dict)
        self.assertEqual(runtime_env["LITELLM_MODEL"], "gemini/gemini-2.5-flash")
        self.assertEqual(runtime_env["LITELLM_FALLBACK_MODELS"], "deepseek/deepseek-chat")
        self.assertEqual(runtime_env["LLM_CHANNELS"], "gemini")
        self.assertEqual(runtime_env["LLM_GEMINI_PROTOCOL"], "gemini")
        self.assertEqual(runtime_env["LLM_GEMINI_API_KEYS"], "dsa-gemini-key")
        self.assertEqual(runtime_env["LLM_GEMINI_EXTRA_HEADERS"], '{"x-tenant": "dsa"}')
        self.assertEqual(runtime_env["GEMINI_API_KEY"], "dsa-gemini-key")
        self.assertEqual(runtime_env["LLM_CANDIDATE_CONTEXT_ENABLED"], "false")
        self.assertEqual(runtime_env["LLM_CANDIDATE_CONTEXT_PROVIDERS"], "news,fund_flow,announcement,quote")
        self.assertEqual(runtime_env["LLM_CANDIDATE_MULTIPLIER"], "2")
        self.assertEqual(runtime_env["LLM_MAX_CANDIDATES"], "10")
        self.assertEqual(runtime_env["DAILY_SOURCE"], "auto")
        self.assertEqual(runtime_env["DAILY_FETCH_RETRIES"], "3")
        self.assertEqual(runtime_env["DAILY_FETCH_MAX_WORKERS"], "1")
        self.assertEqual(runtime_env["SNAPSHOT_SOURCE_PRIORITY"], "sina,efinance,akshare_em,em_datacenter")
        self.assertEqual(runtime_env["ALPHASIFT_DATA_DIR"], str(alphasift_service.DSA_ALPHASIFT_DATA_DIR))
        self.assertEqual(
            runtime_env["ALPHASIFT_FALLBACK_SNAPSHOT_PATH"],
            str(alphasift_service.DSA_ALPHASIFT_DATA_DIR / "snapshot.last_good.json"),
        )
        self.assertEqual(
            runtime_env["ALPHASIFT_DAILY_HISTORY_CACHE_DIR"],
            str(alphasift_service.DSA_ALPHASIFT_DATA_DIR / "daily_history"),
        )
        self.assertEqual(
            runtime_env["ALPHASIFT_INDUSTRY_PROVIDER_CACHE_DIR"],
            str(alphasift_service.DSA_ALPHASIFT_DATA_DIR / "industry_provider_cache"),
        )
        context = captured["context"]
        self.assertIsInstance(context, dict)
        self.assertEqual(context["llm"]["model"], "gemini/gemini-2.5-flash")
        self.assertFalse(context["llm"]["candidate_context_enabled"])
        self.assertEqual(context["llm"]["candidate_multiplier"], 2)
        self.assertEqual(context["llm"]["max_candidates"], 10)
        self.assertEqual(context["llm"]["channels"][0]["api_keys"], ["dsa-gemini-key"])
        self.assertEqual(context["llm"]["channels"][0]["extra_headers"], {"x-tenant": "dsa"})
        self.assertEqual(context["llm"]["model_list"][0]["litellm_params"]["extra_headers"], {"x-tenant": "dsa"})
        self.assertIn("get_candidate_context", context["dsa"])
        self.assertEqual(context["dsa"]["mode"], "pre_rank_light")
        self.assertEqual(context["dsa"]["max_candidates"], 3)
        self.assertFalse(context["dsa"]["include_news"])
        self.assertNotIn("search_stock_news", context["dsa"])
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_bridges_legacy_openai_fields_into_alphasift_runtime_env(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="openai/gpt-4o-mini",
            openai_api_keys=["dsa-openai-key"],
            openai_base_url="https://openai-compatible.example/v1",
        )
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **kwargs):
            captured["env"] = {
                "OPENAI_API_KEY": alphasift_service.os.environ.get("OPENAI_API_KEY"),
                "OPENAI_API_KEYS": alphasift_service.os.environ.get("OPENAI_API_KEYS"),
                "OPENAI_BASE_URL": alphasift_service.os.environ.get("OPENAI_BASE_URL"),
                "LITELLM_MODEL": alphasift_service.os.environ.get("LITELLM_MODEL"),
            }
            captured["context"] = kwargs.get("context")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(
                alphasift_service.os.environ,
                {
                    "OPENAI_API_KEY": "outer-openai-key",
                    "OPENAI_BASE_URL": "https://outer-openai.example/v1",
                },
                clear=False,
            ),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)
            self.assertEqual(alphasift_service.os.environ.get("OPENAI_API_KEY"), "outer-openai-key")
            self.assertEqual(alphasift_service.os.environ.get("OPENAI_BASE_URL"), "https://outer-openai.example/v1")

        runtime_env = captured["env"]
        self.assertIsInstance(runtime_env, dict)
        self.assertEqual(runtime_env["OPENAI_API_KEY"], "dsa-openai-key")
        self.assertEqual(runtime_env["OPENAI_API_KEYS"], "dsa-openai-key")
        self.assertEqual(runtime_env["OPENAI_BASE_URL"], "https://openai-compatible.example/v1")
        self.assertEqual(runtime_env["LITELLM_MODEL"], "openai/gpt-4o-mini")

        context = captured["context"]
        self.assertIsInstance(context, dict)
        self.assertEqual(context["llm"]["channels"], [])
        self.assertEqual(context["llm"]["model_list"], [])
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_injects_openai_compatible_model_headers_into_alphasift_litellm_calls(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=["openai/gpt-4o-mini"],
            llm_model_list=[
                {
                    "model_name": "openai/gpt-4o-mini",
                    "litellm_params": {
                        "model": "openai/gpt-4o-mini",
                        "api_key": "dsa-openai-key",
                        "api_base": "https://openai-compatible.example/v1",
                        "extra_headers": {"x-tenant": "dsa"},
                    },
                },
            ],
        )
        completion_calls: list[dict[str, object]] = []

        def completion_impl(**kwargs):
            completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        def screen_impl(_strategy: str, **_kwargs):
            fake_litellm.completion(
                model="openai/gpt-4o-mini",
                api_key="dsa-openai-key",
                api_base="https://openai-compatible.example/v1",
                messages=[{"role": "user", "content": "rank"}],
            )
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(sys.modules, {"litellm": fake_litellm}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(payload["candidate_count"], 0)
        self.assertEqual(completion_calls[0]["extra_headers"], {"x-tenant": "dsa"})
        self.assertEqual(
            completion_calls[0]["api_base"],
            "https://openai-compatible.example/v1",
        )
        self.assertIsNot(fake_litellm.completion, completion_impl)
        self.assertTrue(
            getattr(fake_litellm.completion, "_alphasift_litellm_completion_bridge", False),
        )

    def test_screen_disabled_preserves_existing_llm_env_state(self) -> None:
        config = self._config(enabled=False)
        baseline_env = {
            "OPENAI_API_KEY": "legacy-openai-key",
            "OPENAI_BASE_URL": "https://outer.example.com/v1",
            "LITELLM_MODEL": "openai/gpt-4o-mini",
        }
        original_env = {key: alphasift_service.os.environ.get(key) for key in baseline_env}

        with (
            patch.dict(alphasift_service.os.environ, baseline_env, clear=False),
            patch("src.services.alphasift_service._build_alphasift_runtime_env") as runtime_env_mock,
            self.assertRaises(HTTPException) as caught,
        ):
            self._screen(config, market="cn", strategy="dual_low", max_results=5)
            for key, value in baseline_env.items():
                self.assertEqual(alphasift_service.os.environ.get(key), value)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail["error"], "alphasift_disabled")
        runtime_env_mock.assert_not_called()
        for key, value in baseline_env.items():
            self.assertEqual(alphasift_service.os.environ.get(key), original_env[key])

    def test_screen_filters_undeclared_managed_fallbacks_for_dsa_routes(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="gemini/gemini-3-flash-preview",
            litellm_fallback_models=["gemini/gemini-2.5-flash"],
            llm_channels=[
                {
                    "name": "gemini",
                    "protocol": "gemini",
                    "enabled": True,
                    "base_url": "",
                    "api_keys": ["dsa-gemini-key"],
                    "models": ["gemini/gemini-3-flash-preview"],
                },
                {
                    "name": "deepseek",
                    "protocol": "deepseek",
                    "enabled": True,
                    "base_url": "https://api.deepseek.com",
                    "api_keys": ["dsa-deepseek-key"],
                    "models": ["deepseek/deepseek-chat"],
                },
            ],
            llm_model_list=[
                {
                    "model_name": "gemini/gemini-3-flash-preview",
                    "litellm_params": {
                        "model": "gemini/gemini-3-flash-preview",
                        "api_key": "dsa-gemini-key",
                    },
                },
                {
                    "model_name": "deepseek/deepseek-chat",
                    "litellm_params": {
                        "model": "deepseek/deepseek-chat",
                        "api_key": "dsa-deepseek-key",
                        "api_base": "https://api.deepseek.com",
                    },
                },
            ],
        )
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **kwargs):
            captured["env"] = {
                "LITELLM_MODEL": alphasift_service.os.environ.get("LITELLM_MODEL"),
                "LITELLM_FALLBACK_MODELS": alphasift_service.os.environ.get("LITELLM_FALLBACK_MODELS"),
                "LLM_CHANNELS": alphasift_service.os.environ.get("LLM_CHANNELS"),
            }
            captured["context"] = kwargs.get("context")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        runtime_env = captured["env"]
        self.assertIsInstance(runtime_env, dict)
        self.assertEqual(runtime_env["LITELLM_MODEL"], "gemini/gemini-3-flash-preview")
        self.assertEqual(runtime_env["LITELLM_FALLBACK_MODELS"], "deepseek/deepseek-chat")
        self.assertEqual(runtime_env["LLM_CHANNELS"], "gemini,deepseek")
        context = captured["context"]
        self.assertIsInstance(context, dict)
        self.assertEqual(context["llm"]["fallback_models"], ["deepseek/deepseek-chat"])
        self.assertEqual(payload["candidate_count"], 0)
