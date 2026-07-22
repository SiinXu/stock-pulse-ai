# -*- coding: utf-8 -*-
"""AlphaSift screening and runtime API contracts."""

from __future__ import annotations

from tests.alphasift_api_test_support import (
    sys,
    ModuleType,
    SimpleNamespace,
    Any,
    Dict,
    ANY,
    MagicMock,
    patch,
    threading,
    HTTPException,
    Config,
    OutboundPolicyError,
    alphasift_service,
    DEFAULT_ALPHASIFT_TEST_SPEC,
    PUBLIC_DIAGNOSTIC_SECRET,
    _make_adapter_module,
    _missing_alphasift_module_diagnostics,
    _AlphaSiftApiTestCaseBase,
)


class AlphaSiftOpportunitiesApiTestCase(_AlphaSiftApiTestCaseBase):
    def test_screen_calls_dsa_adapter_and_normalizes_llm_fields(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "run_id": "run123",
                    "strategy": "dual_low",
                    "market": "cn",
                    "snapshot_count": 100,
                    "snapshot_source": "em_datacenter",
                    "after_filter_count": 5,
                    "llm_ranked": True,
                    "llm_coverage": 1.0,
                    "warnings": "fallback",
                    "source_errors": "sina timeout",
                    "llm_parse_errors": "retry parsed partial JSON",
                    "deep_analysis_requested": False,
                    "post_analyzers": ["scorecard"],
                    "daily_enriched": True,
                    "daily_enrich_count": 12,
                    "risk_enabled": True,
                    "portfolio_diversity_enabled": True,
                    "portfolio_concentration_notes": ["sector concentration adjusted"],
                    "candidates": [
                        {
                            "code": "600519",
                            "name": "Kweichow Moutai",
                            "score": 88.5,
                            "llm_score": 90.0,
                            "llm_thesis": "LLM likes the setup",
                            "risk_level": "medium",
                            "risk_flags": ["valuation"],
                            "price": 1688.0,
                            "industry": "Baijiu",
                            "factor_scores": {"value": 88.0},
                        }
                    ],
                }
            ),
        )

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        fake_module.screen.assert_called_once_with(
            "dual_low",
            market="cn",
            max_results=5,
            use_llm=True,
            context=ANY,
        )
        self.assertEqual(fake_module.screen.call_args.kwargs["context"]["llm"]["model"], "")
        self.assertEqual(payload["run_id"], "run123")
        self.assertEqual(payload["snapshot_count"], 100)
        self.assertEqual(payload["snapshot_source"], "em_datacenter")
        self.assertEqual(payload["after_filter_count"], 5)
        self.assertEqual(payload["llm_ranked"], True)
        self.assertEqual(payload["llm_coverage"], 1.0)
        self.assertEqual(payload["warnings"], ["alphasift_warning"])
        self.assertEqual(payload["source_errors"], ["alphasift_source_error"])
        self.assertEqual(payload["llm_parse_errors"], ["alphasift_llm_parse_error"])
        self.assertEqual(payload["candidate_count"], 1)
        self.assertEqual(payload["post_analyzers"], ["scorecard"])
        self.assertEqual(payload["daily_enriched"], True)
        self.assertEqual(payload["daily_enrich_count"], 12)
        self.assertEqual(payload["portfolio_concentration_notes"], ["sector concentration adjusted"])
        self.assertEqual(payload["candidates"][0]["code"], "600519")
        self.assertEqual(payload["candidates"][0]["llm_score"], 90.0)
        self.assertEqual(payload["candidates"][0]["llm_thesis"], "LLM likes the setup")
        self.assertEqual(payload["candidates"][0]["risk_level"], "medium")
        self.assertEqual(payload["candidates"][0]["price"], 1688.0)
        self.assertEqual(payload["candidates"][0]["industry"], "Baijiu")

    def test_screen_success_hides_raw_adapter_diagnostics_recursively(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(return_value={
                "warnings": [PUBLIC_DIAGNOSTIC_SECRET],
                "source_errors": [PUBLIC_DIAGNOSTIC_SECRET],
                "llm_parse_errors": [PUBLIC_DIAGNOSTIC_SECRET],
                "candidates": [{
                    "code": "600519",
                    "warnings": [PUBLIC_DIAGNOSTIC_SECRET],
                    "source_errors": [PUBLIC_DIAGNOSTIC_SECRET],
                    "exception": PUBLIC_DIAGNOSTIC_SECRET,
                    "error": PUBLIC_DIAGNOSTIC_SECRET,
                    "error_message": PUBLIC_DIAGNOSTIC_SECRET,
                    "errorMessage": PUBLIC_DIAGNOSTIC_SECRET,
                    "error_msg": PUBLIC_DIAGNOSTIC_SECRET,
                    "errorMsg": PUBLIC_DIAGNOSTIC_SECRET,
                    "error_code": PUBLIC_DIAGNOSTIC_SECRET,
                    "errorReason": PUBLIC_DIAGNOSTIC_SECRET,
                    "last_error": PUBLIC_DIAGNOSTIC_SECRET,
                    "lastError": PUBLIC_DIAGNOSTIC_SECRET,
                    "last_error_message": PUBLIC_DIAGNOSTIC_SECRET,
                    "last_error_code": "stock_news_failed",
                    "diagnostic_error": PUBLIC_DIAGNOSTIC_SECRET,
                    "response_error": PUBLIC_DIAGNOSTIC_SECRET,
                    "raw_error": PUBLIC_DIAGNOSTIC_SECRET,
                    "errors": [PUBLIC_DIAGNOSTIC_SECRET],
                    "error_messages": [PUBLIC_DIAGNOSTIC_SECRET],
                    "responseErrors": [PUBLIC_DIAGNOSTIC_SECRET],
                    "nested": {
                        "error": "stock_news_unavailable",
                        "errors": ["stock_news_failed", PUBLIC_DIAGNOSTIC_SECRET],
                    },
                    "diagnostics": {
                        "endpoint": PUBLIC_DIAGNOSTIC_SECRET,
                        "note": "provider returned a partial business payload",
                        "public_url": "https://docs.example.invalid/alphasift",
                        PUBLIC_DIAGNOSTIC_SECRET: "failed",
                    },
                    "debug_message": PUBLIC_DIAGNOSTIC_SECRET,
                }],
            }),
        )

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=1)

        self.assertEqual(payload["warnings"], ["alphasift_warning"])
        self.assertEqual(payload["source_errors"], ["alphasift_source_error"])
        self.assertEqual(payload["llm_parse_errors"], ["alphasift_llm_parse_error"])
        raw = payload["candidates"][0]["raw"]
        self.assertEqual(raw["exception"], "alphasift_internal_error")
        for key in (
            "error",
            "error_message",
            "errorMessage",
            "error_msg",
            "errorMsg",
            "error_code",
            "errorReason",
            "last_error",
            "lastError",
            "last_error_message",
            "diagnostic_error",
            "response_error",
            "raw_error",
        ):
            self.assertEqual(raw[key], "alphasift_error")
            self.assertIsInstance(raw[key], str)
        self.assertEqual(raw["errors"], ["alphasift_error"])
        self.assertEqual(raw["error_messages"], ["alphasift_error"])
        self.assertEqual(raw["responseErrors"], ["alphasift_error"])
        self.assertEqual(raw["last_error_code"], "stock_news_failed")
        self.assertEqual(raw["nested"]["error"], "stock_news_unavailable")
        self.assertEqual(raw["nested"]["errors"], ["stock_news_failed", "alphasift_error"])
        self.assertNotIn(PUBLIC_DIAGNOSTIC_SECRET, raw["diagnostics"]["endpoint"])
        self.assertIn("[REDACTED]", raw["diagnostics"]["endpoint"])
        self.assertIn("[REDACTED_URL]", raw["diagnostics"]["endpoint"])
        self.assertEqual(
            raw["diagnostics"]["note"],
            "provider returned a partial business payload",
        )
        self.assertEqual(
            raw["diagnostics"]["public_url"],
            "https://docs.example.invalid/alphasift",
        )
        diagnostic_keys = list(raw["diagnostics"])
        self.assertIn("Authorization: [REDACTED] [REDACTED_URL]", diagnostic_keys)
        self.assertNotIn(PUBLIC_DIAGNOSTIC_SECRET, diagnostic_keys)
        self.assertNotIn(PUBLIC_DIAGNOSTIC_SECRET, raw["debug_message"])
        self.assertIn("[REDACTED]", raw["debug_message"])
        self.assertIn("[REDACTED_URL]", raw["debug_message"])
        self.assert_public_payload_is_private(payload)

    def test_screen_news_enrichment_exception_hides_raw_error_field(self) -> None:
        config = self._config(enabled=True)
        fake_manager = SimpleNamespace(get_stock_name=MagicMock(return_value="贵州茅台"))
        fake_module = _make_adapter_module(
            screen=MagicMock(return_value={
                "candidates": [{"code": "600519", "score": 88.5}],
            }),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch("src.services.alphasift_service._get_dsa_fetcher_manager", return_value=fake_manager),
            patch("src.services.alphasift_service.get_dsa_realtime_quote", return_value={}),
            patch("src.services.alphasift_service.get_dsa_fundamental_context", return_value={}),
            patch(
                "src.services.alphasift_service.search_dsa_stock_news",
                side_effect=RuntimeError(PUBLIC_DIAGNOSTIC_SECRET),
            ),
        ):
            payload = self._screen(
                config,
                market="cn",
                strategy="dual_low",
                max_results=1,
                mock_enrichment=False,
            )

        news = payload["candidates"][0]["dsa_context"]["news"]
        self.assertEqual(news["error"], "stock_news_failed")
        self.assertIsInstance(news["error"], str)
        self.assertEqual(
            payload["dsa_enrichment"]["warnings"],
            ["dsa_realtime_quote_missing", "stock_news_failed"],
        )
        self.assert_public_payload_is_private(payload)

    def test_screen_prefers_dsa_daily_history_for_alphasift_enrichment(self) -> None:
        config = self._config(enabled=True)
        parent_module = ModuleType("alphasift")
        daily_module = ModuleType("alphasift.daily")
        original_daily_fetch = MagicMock(side_effect=AssertionError("AlphaSift daily fetch should not run first"))
        daily_module.fetch_daily_history = original_daily_fetch
        parent_module.daily = daily_module
        captured: Dict[str, Any] = {}

        def screen_with_daily_fetch(strategy: str, **kwargs: Any) -> Dict[str, Any]:
            daily_df = daily_module.fetch_daily_history(
                "600519",
                lookback_days=20,
                source="akshare",
                retries=1,
            )
            captured["daily_df"] = daily_df
            captured["context"] = kwargs.get("context")
            return {
                "strategy": strategy,
                "candidates": [{"code": "600519", "score": 88.0}],
            }

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_with_daily_fetch))

        with (
            patch.dict(sys.modules, {"alphasift": parent_module, "alphasift.daily": daily_module}),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch(
                "src.services.alphasift_service.get_dsa_daily_history",
                return_value=(
                    [
                        {
                            "trade_date": "20260603",
                            "close": "10.5",
                            "vol": "123400",
                        }
                    ],
                    "EfinanceFetcher",
                ),
            ) as dsa_history_mock,
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        daily_df = captured["daily_df"]
        self.assertEqual(daily_df.attrs["source"], "dsa:EfinanceFetcher")
        self.assertEqual(daily_df.loc[0, "date"], "2026-06-03")
        self.assertEqual(daily_df.loc[0, "volume"], 123400)
        self.assertEqual(daily_df.loc[0, "open"], 10.5)
        self.assertEqual(payload["candidate_count"], 1)
        self.assertIn("daily_history", captured["context"]["dsa"]["capabilities"])
        self.assertIs(captured["context"]["dsa"]["get_daily_history"], dsa_history_mock)
        dsa_history_mock.assert_called_once_with("600519", lookback_days=20)
        original_daily_fetch.assert_not_called()
        self.assertIs(daily_module.fetch_daily_history, original_daily_fetch)

    def test_screen_enriches_top_candidates_with_dsa_context(self) -> None:
        config = self._config(enabled=True)
        fake_manager = SimpleNamespace(get_stock_name=MagicMock(return_value="贵州茅台"))
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "candidates": [
                        {
                            "code": "600519",
                            "score": 88.5,
                            "reason": "AlphaSift pick",
                        }
                    ]
                }
            ),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch("src.services.alphasift_service._get_dsa_fetcher_manager", return_value=fake_manager),
            patch(
                "src.services.alphasift_service.get_dsa_realtime_quote",
                return_value={"price": 1688.0, "change_pct": 1.2, "amount": 100000000.0},
            ),
            patch(
                "src.services.alphasift_service.get_dsa_fundamental_context",
                return_value={"market": "cn", "coverage": {"valuation": "available"}},
            ),
            patch(
                "src.services.alphasift_service.search_dsa_stock_news",
                return_value={
                    "success": True,
                    "provider": "test",
                    "results": [{"title": "贵州茅台最新公告", "source": "测试源"}],
                },
            ),
        ):
            payload = self._screen(
                config,
                market="cn",
                strategy="dual_low",
                max_results=5,
                mock_enrichment=False,
            )

        candidate = payload["candidates"][0]
        self.assertEqual(candidate["name"], "贵州茅台")
        self.assertEqual(candidate["price"], 1688.0)
        self.assertTrue(candidate["dsa_context"]["enriched"])
        self.assertEqual(candidate["dsa_news"][0]["title"], "贵州茅台最新公告")
        self.assertIn("StockPulse 行情", candidate["dsa_analysis_summary"])
        self.assertNotIn("DSA行情", candidate["dsa_analysis_summary"])
        self.assertEqual(payload["dsa_enrichment"]["enriched_count"], 1)

    def test_screen_reuses_alphasift_dsa_context_without_refetch(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "candidates": [
                        {
                            "code": "600519",
                            "name": "贵州茅台",
                            "score": 88.5,
                            "dsa_context": {
                                "enriched": True,
                                "quote": {"price": 1688.0, "change_pct": 1.2},
                                "warnings": ["from_alphasift_provider"],
                            },
                            "dsa_news": [{"title": "贵州茅台最新公告", "source": "测试源"}],
                            "dsa_analysis_summary": "DSA新闻: 贵州茅台最新公告",
                        }
                    ]
                }
            ),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch("src.services.alphasift_service.get_dsa_realtime_quote") as quote_mock,
            patch("src.services.alphasift_service.get_dsa_fundamental_context") as fundamentals_mock,
            patch("src.services.alphasift_service.search_dsa_stock_news") as news_mock,
        ):
            payload = self._screen(
                config,
                market="cn",
                strategy="dual_low",
                max_results=5,
                mock_enrichment=False,
            )

        candidate = payload["candidates"][0]
        self.assertTrue(candidate["dsa_context"]["enriched"])
        self.assertEqual(candidate["dsa_news"][0]["title"], "贵州茅台最新公告")
        self.assertEqual(candidate["dsa_analysis_summary"], "DSA新闻: 贵州茅台最新公告")
        self.assertEqual(payload["dsa_enrichment"]["enriched_count"], 1)
        self.assertEqual(payload["dsa_enrichment"]["warnings"], ["alphasift_warning"])
        quote_mock.assert_not_called()
        fundamentals_mock.assert_not_called()
        news_mock.assert_not_called()

    def test_screen_reuses_context_news_results_without_refetch(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "candidates": [
                        {
                            "code": "600519",
                            "name": "贵州茅台",
                            "score": 88.5,
                            "dsa_context": {
                                "enriched": True,
                                "quote": {"price": 1688.0, "change_pct": 1.2},
                                "news": {
                                    "success": True,
                                    "summary": "DSA新闻：贵州茅台最新公告",
                                    "results": [{"title": "贵州茅台最新公告", "source": "测试源"}],
                                },
                                "warnings": ["from_alphasift_provider"],
                            },
                            "dsa_news": [],
                        }
                    ]
                }
            ),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch("src.services.alphasift_service.get_dsa_realtime_quote") as quote_mock,
            patch("src.services.alphasift_service.get_dsa_fundamental_context") as fundamentals_mock,
            patch("src.services.alphasift_service.search_dsa_stock_news") as news_mock,
        ):
            payload = self._screen(
                config,
                market="cn",
                strategy="dual_low",
                max_results=5,
                mock_enrichment=False,
            )

        candidate = payload["candidates"][0]
        self.assertEqual(candidate["dsa_news"][0]["title"], "贵州茅台最新公告")
        self.assertEqual(candidate["dsa_analysis_summary"], "DSA新闻：贵州茅台最新公告")
        self.assertEqual(payload["dsa_enrichment"]["enriched_count"], 1)
        self.assertEqual(payload["dsa_enrichment"]["warnings"], ["alphasift_warning"])
        quote_mock.assert_not_called()
        fundamentals_mock.assert_not_called()
        news_mock.assert_not_called()

    def test_screen_completes_light_alphasift_context_with_news_only(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "candidates": [
                        {
                            "code": "600519",
                            "name": "贵州茅台",
                            "score": 88.5,
                            "dsa_context": {
                                "enriched": True,
                                "profile": "pre_rank_light",
                                "news_included": False,
                                "quote": {"price": 1688.0, "change_pct": 1.2},
                                "fundamentals": {"coverage": {"valuation": "available"}},
                                "news": {
                                    "success": False,
                                    "skipped": True,
                                    "reason": "pre_rank_light_context",
                                    "results": [],
                                },
                            },
                            "dsa_news": [],
                            "dsa_analysis_summary": "DSA行情: 现价 1688.0",
                        }
                    ]
                }
            ),
        )
        fake_manager = SimpleNamespace(get_stock_name=MagicMock(return_value="贵州茅台"))

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch("src.services.alphasift_service._get_dsa_fetcher_manager", return_value=fake_manager),
            patch("src.services.alphasift_service.get_dsa_realtime_quote") as quote_mock,
            patch("src.services.alphasift_service.get_dsa_fundamental_context") as fundamentals_mock,
            patch(
                "src.services.alphasift_service.search_dsa_stock_news",
                return_value={
                    "success": True,
                    "provider": "test",
                    "results": [{"title": "贵州茅台最新公告", "source": "测试源"}],
                },
            ) as news_mock,
        ):
            payload = self._screen(
                config,
                market="cn",
                strategy="dual_low",
                max_results=5,
                mock_enrichment=False,
            )

        candidate = payload["candidates"][0]
        self.assertEqual(candidate["dsa_context"]["profile"], "post_rank_full")
        self.assertTrue(candidate["dsa_context"]["news_included"])
        self.assertEqual(candidate["dsa_context"]["quote"]["price"], 1688.0)
        self.assertEqual(candidate["dsa_context"]["fundamentals"]["coverage"]["valuation"], "available")
        self.assertEqual(candidate["dsa_news"][0]["title"], "贵州茅台最新公告")
        quote_mock.assert_not_called()
        fundamentals_mock.assert_not_called()
        news_mock.assert_called_once()

    def test_dsa_pre_rank_candidate_context_omits_news(self) -> None:
        fake_manager = SimpleNamespace(get_stock_name=MagicMock(return_value="贵州茅台"))

        with (
            patch("src.services.alphasift_service._get_dsa_fetcher_manager", return_value=fake_manager),
            patch(
                "src.services.alphasift_service.get_dsa_realtime_quote",
                return_value={"price": 1688.0, "change_pct": 1.2, "amount": 100000000.0},
            ),
            patch(
                "src.services.alphasift_service.get_dsa_fundamental_context",
                return_value={"market": "cn", "coverage": {"valuation": "available"}},
            ),
            patch("src.services.alphasift_service.search_dsa_stock_news") as news_mock,
        ):
            context = alphasift_service.get_dsa_candidate_context("600519", "贵州茅台")

        self.assertEqual(context["profile"], "pre_rank_light")
        self.assertFalse(context["news_included"])
        self.assertTrue(context["news"]["skipped"])
        self.assertEqual(context["quote"]["price"], 1688.0)
        self.assertEqual(context["fundamentals"]["coverage"]["valuation"], "available")
        news_mock.assert_not_called()

    def test_screen_injects_dsa_channel_headers_into_alphasift_litellm_calls(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="gemini/gemini-2.5-flash",
            llm_channels=[
                {
                    "name": "gemini",
                    "protocol": "gemini",
                    "enabled": True,
                    "api_keys": ["dsa-gemini-key"],
                    "models": ["gemini/gemini-2.5-flash"],
                    "extra_headers": {"x-tenant": "dsa"},
                }
            ],
        )
        completion_calls: list[dict[str, object]] = []

        def completion_impl(**kwargs):
            completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        def screen_impl(_strategy: str, **_kwargs):
            fake_litellm.completion(
                model="gemini/gemini-2.5-flash",
                api_key="dsa-gemini-key",
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
        self.assertIsNot(fake_litellm.completion, completion_impl)
        self.assertTrue(
            getattr(fake_litellm.completion, "_alphasift_litellm_completion_bridge", False),
        )

    def test_screen_rejects_private_legacy_openai_base_before_litellm_call(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="openai/gpt-4o-mini",
            openai_api_keys=["dsa-openai-key"],
            openai_base_url="http://127.0.0.1:8080/v1",
        )
        completion_calls: list[Dict[str, Any]] = []

        def completion_impl(**kwargs: Any) -> Any:
            completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        def screen_impl(_strategy: str, **_kwargs):
            fake_litellm.completion(
                model="openai/gpt-4o-mini",
                api_key="dsa-openai-key",
                messages=[{"role": "user", "content": "rank"}],
            )
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))
        with (
            patch.dict(sys.modules, {"litellm": fake_litellm}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            self.assertRaises(HTTPException) as caught,
        ):
            self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertIsInstance(caught.exception.__cause__, OutboundPolicyError)
        self.assertEqual(completion_calls, [])

    def test_screen_bridges_openai_channel_base_url_and_headers(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=["openai/gpt-4.1"],
            llm_channels=[
                {
                    "name": "openai",
                    "protocol": "openai",
                    "enabled": True,
                    "base_url": "https://primary-openai.example/v1",
                    "api_keys": ["dsa-openai-primary"],
                    "models": ["openai/gpt-4o-mini", "openai/gpt-4.1"],
                    "extra_headers": {"x-route": "primary", "x-tenant": "dsa"},
                }
            ],
        )
        completion_calls: list[Dict[str, object]] = []

        def completion_impl(**kwargs: Any) -> Any:
            completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **kwargs: Dict[str, Any]) -> dict[str, object]:
            captured["env"] = {
                "OPENAI_BASE_URL": alphasift_service.os.environ.get("OPENAI_BASE_URL"),
                "OPENAI_API_KEY": alphasift_service.os.environ.get("OPENAI_API_KEY"),
                "OPENAI_API_KEYS": alphasift_service.os.environ.get("OPENAI_API_KEYS"),
                "LLM_CHANNELS": alphasift_service.os.environ.get("LLM_CHANNELS"),
                "LLM_OPENAI_BASE_URL": alphasift_service.os.environ.get("LLM_OPENAI_BASE_URL"),
                "LLM_OPENAI_API_KEYS": alphasift_service.os.environ.get("LLM_OPENAI_API_KEYS"),
            }
            captured["context"] = kwargs.get("context")
            fake_litellm.completion(
                model="openai/gpt-4o-mini",
                api_key="dsa-openai-primary",
                api_base="https://primary-openai.example/v1",
                messages=[{"role": "user", "content": "primary"}],
            )
            fake_litellm.completion(
                model="openai/gpt-4.1",
                api_key="dsa-openai-primary",
                api_base="https://primary-openai.example/v1",
                messages=[{"role": "user", "content": "fallback"}],
            )
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(sys.modules, {"litellm": fake_litellm}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(payload["candidate_count"], 0)
        self.assertEqual(len(completion_calls), 2)
        self.assertEqual(captured["env"]["OPENAI_BASE_URL"], "https://primary-openai.example/v1")
        self.assertEqual(captured["env"]["OPENAI_API_KEYS"], "dsa-openai-primary")
        self.assertEqual(captured["env"]["OPENAI_API_KEY"], "dsa-openai-primary")
        self.assertEqual(captured["env"]["LLM_CHANNELS"], "openai")
        self.assertEqual(captured["env"]["LLM_OPENAI_BASE_URL"], "https://primary-openai.example/v1")
        self.assertEqual(captured["env"]["LLM_OPENAI_API_KEYS"], "dsa-openai-primary")
        self.assertEqual(completion_calls[0]["extra_headers"], {"x-route": "primary", "x-tenant": "dsa"})
        self.assertEqual(completion_calls[1]["extra_headers"], {"x-route": "primary", "x-tenant": "dsa"})
        context = captured["context"]
        self.assertIsInstance(context, dict)
        self.assertEqual(context["llm"]["channels"][0]["base_url"], "https://primary-openai.example/v1")
        self.assertEqual(context["llm"]["channels"][0]["extra_headers"], {"x-route": "primary", "x-tenant": "dsa"})
        self.assertEqual(context["llm"]["model_list"][0]["litellm_params"]["api_base"], "https://primary-openai.example/v1")
        self.assertEqual(context["llm"]["fallback_models"], ["openai/gpt-4.1"])
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_injects_openai_compatible_fallback_headers_for_multiple_models(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=["openai/gpt-4.1"],
            llm_model_list=[
                {
                    "model_name": "openai/gpt-4o-mini",
                    "litellm_params": {
                        "model": "openai/gpt-4o-mini",
                        "api_key": "dsa-openai-primary",
                        "api_base": "https://primary.openai.example/v1",
                        "extra_headers": {"x-route": "primary", "x-tenant": "dsa"},
                    },
                },
                {
                    "model_name": "openai/gpt-4.1",
                    "litellm_params": {
                        "model": "openai/gpt-4.1",
                        "api_key": "dsa-openai-fallback",
                        "api_base": "https://fallback.openai.example/v1",
                        "extra_headers": {"x-route": "fallback", "x-tenant": "dsa"},
                    },
                },
            ],
        )
        completion_calls: list[Dict[str, object]] = []

        def completion_impl(**kwargs: Any) -> Any:
            completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        def screen_impl(_strategy: str, **_kwargs) -> dict[str, object]:
            fake_litellm.completion(
                model="openai/gpt-4o-mini",
                api_key="dsa-openai-primary",
                api_base="https://primary.openai.example/v1",
                messages=[{"role": "user", "content": "rank-1"}],
            )
            fake_litellm.completion(
                model="openai/gpt-4.1",
                api_key="dsa-openai-fallback",
                api_base="https://fallback.openai.example/v1",
                messages=[{"role": "user", "content": "rank-2"}],
            )
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(sys.modules, {"litellm": fake_litellm}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(payload["candidate_count"], 0)
        primary_call = next(
            call for call in completion_calls if call["model"] == "openai/gpt-4o-mini"
        )
        fallback_call = next(
            call for call in completion_calls if call["model"] == "openai/gpt-4.1"
        )
        self.assertEqual(primary_call["extra_headers"], {"x-route": "primary", "x-tenant": "dsa"})
        self.assertEqual(
            fallback_call["extra_headers"],
            {"x-route": "fallback", "x-tenant": "dsa"},
        )
        self.assertEqual(primary_call["api_base"], "https://primary.openai.example/v1")
        self.assertEqual(fallback_call["api_base"], "https://fallback.openai.example/v1")
        self.assertTrue(getattr(fake_litellm.completion, "_alphasift_litellm_completion_bridge", False))

    def test_screen_handles_concurrent_requests_without_litellm_header_cross_pollution(self) -> None:
        config_a = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="gemini/gemini-2.5-flash",
            llm_channels=[
                {
                    "name": "gemini",
                    "protocol": "gemini",
                    "enabled": True,
                    "api_keys": ["dsa-gemini-key-a"],
                    "models": ["gemini/gemini-2.5-flash"],
                    "extra_headers": {"x-tenant": "tenant-a"},
                }
            ],
        )
        config_b = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="gemini/gemini-2.5-flash",
            llm_channels=[
                {
                    "name": "gemini",
                    "protocol": "gemini",
                    "enabled": True,
                    "api_keys": ["dsa-gemini-key-b"],
                    "models": ["gemini/gemini-2.5-flash"],
                    "extra_headers": {"x-tenant": "tenant-b"},
                }
            ],
        )

        completion_calls: list[Dict[str, Any]] = []
        thread_b_ready = threading.Event()
        completion_lock = threading.Lock()

        def completion_impl(**kwargs: Any) -> Any:
            with completion_lock:
                completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        def screen_impl(_strategy: str, **kwargs: Any) -> Dict[str, Any]:
            context = kwargs.get("context") or {}
            llm = context.get("llm", {})
            channels = llm.get("channels") or []
            headers = (channels[0] if channels else {}).get("extra_headers", {})
            tenant = headers.get("x-tenant")
            if tenant == "tenant-a":
                thread_b_ready.wait(timeout=2)
            else:
                thread_b_ready.set()
            fake_litellm.completion(
                model="gemini/gemini-2.5-flash",
                api_key=(channels[0].get("api_keys") or [""])[0],
                messages=[{"role": "user", "content": "rank"}],
            )
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        def _run_screen(config: Config) -> None:
            self._screen(config, market="cn", strategy="dual_low", max_results=5, mock_enrichment=False)

        with (
            patch.dict(sys.modules, {"litellm": fake_litellm}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            thread_a = threading.Thread(target=_run_screen, args=(config_a,))
            thread_b = threading.Thread(target=_run_screen, args=(config_b,))
            thread_a.start()
            thread_b.start()
            thread_a.join()
            thread_b.join()

        self.assertEqual(len(completion_calls), 2)
        self.assertCountEqual(
            [call.get("extra_headers", {}).get("x-tenant") for call in completion_calls],
            ["tenant-a", "tenant-b"],
        )
        self.assertTrue(
            thread_a.is_alive() is False and thread_b.is_alive() is False,
        )

    def test_screen_preserves_explicit_alphasift_snapshot_source_priority(self) -> None:
        config = self._config(enabled=True)
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **_kwargs):
            captured["snapshot_priority"] = alphasift_service.os.environ.get("SNAPSHOT_SOURCE_PRIORITY")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(alphasift_service.os.environ, {"SNAPSHOT_SOURCE_PRIORITY": "tushare,em_datacenter"}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(captured["snapshot_priority"], "tushare,em_datacenter")
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_preserves_explicit_daily_source(self) -> None:
        config = self._config(enabled=True)
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **_kwargs):
            captured["daily_source"] = alphasift_service.os.environ.get("DAILY_SOURCE")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(alphasift_service.os.environ, {"DAILY_SOURCE": "akshare"}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(captured["daily_source"], "akshare")
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_preserves_explicit_openai_base_url_without_openai_channel(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="deepseek/deepseek-chat",
            llm_channels=[
                {
                    "name": "deepseek",
                    "protocol": "deepseek",
                    "enabled": True,
                    "base_url": "https://api.deepseek.example/v1",
                    "api_keys": ["runtime-deepseek-key"],
                    "models": ["deepseek/deepseek-chat"],
                }
            ],
        )
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **_kwargs):
            captured["openai_base_url"] = alphasift_service.os.environ.get("OPENAI_BASE_URL")
            captured["llm_openai_base_url"] = alphasift_service.os.environ.get("LLM_OPENAI_BASE_URL")
            captured["openai_api_key"] = alphasift_service.os.environ.get("OPENAI_API_KEY")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(
                alphasift_service.os.environ,
                {
                    "OPENAI_BASE_URL": "https://outer-openai.example/v1",
                    "LLM_OPENAI_BASE_URL": "https://outer-openai-channel.example/v1",
                    "OPENAI_API_KEY": "outer-openai-key",
                },
                clear=False,
            ),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(captured["openai_base_url"], "https://outer-openai.example/v1")
        self.assertEqual(captured["llm_openai_base_url"], "https://outer-openai-channel.example/v1")
        self.assertEqual(captured["openai_api_key"], "outer-openai-key")
        self.assertEqual(payload["candidate_count"], 0)

    def test_alphasift_runtime_priority_puts_tushare_before_sina_when_token_exists(self) -> None:
        config = self._config(enabled=True)
        config.tushare_token = "token-1"

        with patch.dict(alphasift_service.os.environ, {"SNAPSHOT_SOURCE_PRIORITY": ""}, clear=False):
            env = alphasift_service._build_alphasift_runtime_env(config)

        self.assertEqual(env["SNAPSHOT_SOURCE_PRIORITY"], "tushare,sina,efinance,akshare_em,em_datacenter")

    def test_screen_preserves_explicit_candidate_context_provider_override(self) -> None:
        config = self._config(enabled=True)
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **_kwargs):
            captured["providers"] = alphasift_service.os.environ.get("LLM_CANDIDATE_CONTEXT_PROVIDERS")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(alphasift_service.os.environ, {"LLM_CANDIDATE_CONTEXT_PROVIDERS": "news,announcement"}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(captured["providers"], "news,announcement")
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_retries_without_context_for_older_adapter_kwargs_wrappers(self) -> None:
        config = self._config(enabled=True)

        def screen_impl(_strategy: str, **kwargs):
            if "context" in kwargs:
                raise TypeError("unexpected keyword argument 'context'")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(fake_module.screen.call_count, 2)
        first_kwargs = fake_module.screen.call_args_list[0].kwargs
        second_kwargs = fake_module.screen.call_args_list[1].kwargs
        self.assertIn("context", first_kwargs)
        self.assertNotIn("context", second_kwargs)
        self.assertEqual(second_kwargs["market"], "cn")
        self.assertEqual(second_kwargs["max_results"], 5)
        self.assertEqual(second_kwargs["use_llm"], True)
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_does_not_install_when_enabled_but_adapter_missing(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(screen=MagicMock(return_value={"candidates": []}))

        with (
            patch(
                "src.services.alphasift_service._get_alphasift_status_snapshot",
                return_value=({}, False, _missing_alphasift_module_diagnostics()),
            ),
            patch("src.services.alphasift_service._install_alphasift") as install_mock,
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail.get("diagnostics", {}).get("reason"), "missing_module")
        install_mock.assert_not_called()
        fake_module.screen.assert_not_called()

    def test_screen_normalizes_non_finite_values(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "picks": [
                        {
                            "code": "600519",
                            "name": "Kweichow Moutai",
                            "score": float("nan"),
                            "ranking_reason": "AlphaSift pick",
                            "nested": {"pe": float("inf"), "pb": float("-inf"), "eps": 20.5},
                        },
                    ],
                }
            ),
        )

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertIsNone(payload["candidates"][0]["score"])
        self.assertIsNone(payload["candidates"][0]["raw"]["score"])
        self.assertIsNone(payload["candidates"][0]["raw"]["nested"]["pe"])
        self.assertIsNone(payload["candidates"][0]["raw"]["nested"]["pb"])

    def test_screen_allows_non_listed_strategy_as_custom(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            list_strategies=lambda: [{"id": "dual_low", "name": "双低选股"}],
            screen=MagicMock(return_value={"candidates": []}),
        )

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="custom_alpha", max_results=5)

        fake_module.screen.assert_called_once_with(
            "custom_alpha",
            market="cn",
            max_results=5,
            use_llm=True,
            context=ANY,
        )
        self.assertEqual(payload["candidates"], [])
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_rejects_unsupported_market(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            get_status=lambda: {"supported_markets": ["hk", "us"]},
            screen=MagicMock(return_value=[]),
        )

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.detail["error"], "alphasift_invalid_market")

    def test_screen_maps_adapter_value_error_to_bad_request(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(side_effect=ValueError(PUBLIC_DIAGNOSTIC_SECRET)),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            self.assertLogs("src.services.alphasift_service", level="WARNING") as captured,
        ):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail["error"], "alphasift_screen_rejected")
        rendered_logs = "\n".join(captured.output)
        self.assertNotIn("sk-alphasift-secret-marker", rendered_logs)
        self.assertNotIn("user:password", rendered_logs)
        self.assertIn("error_code=alphasift_screen_rejected", rendered_logs)
        self.assertIn("exception_type=ValueError", rendered_logs)
        self.assertTrue(all(record.exc_info is None for record in captured.records))

    def test_screen_runtime_exception_hides_raw_diagnostic(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(side_effect=RuntimeError(PUBLIC_DIAGNOSTIC_SECRET)),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            self.assertLogs("src.services.alphasift_service", level="WARNING") as captured,
        ):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_screen_failed")
        self.assertEqual(caught.exception.detail["message"], "AlphaSift 选股运行失败，请稍后重试。")
        self.assert_public_payload_is_private(caught.exception.detail)
        rendered_logs = "\n".join(captured.output)
        self.assertNotIn("sk-alphasift-secret-marker", rendered_logs)
        self.assertNotIn("user:password", rendered_logs)
        self.assertIn("error_code=alphasift_screen_failed", rendered_logs)
        self.assertIn("exception_type=RuntimeError", rendered_logs)
        self.assertTrue(all(record.exc_info is None for record in captured.records))
