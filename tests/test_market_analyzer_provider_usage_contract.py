# -*- coding: utf-8 -*-
"""Analyzer provider response normalization and usage contracts."""

from tests.market_analyzer_generate_text_support import (
    SimpleNamespace,
    _AnalyzerFactoryMixin,
    _OPENAI_COMPATIBILITY_PAYLOAD_FIXTURES,
    _assert_no_provider_usage_hmac_only,
    _assert_usage_contains,
    _llm_usage_hmac_env,
    json,
    patch,
    pytest,
)


class TestAnalyzerGenerateText(_AnalyzerFactoryMixin):
    @pytest.mark.parametrize(
        "provider_model,response_payload,expected_text",
        _OPENAI_COMPATIBILITY_PAYLOAD_FIXTURES,
        ids=["issue1279-message-content-null", "issue1279-message-content-list"],
    )
    def test_call_litellm_extracts_external_provider_text_shapes(self, provider_model, response_payload, expected_text):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model=provider_model,
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response_payload):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == expected_text
        assert model_used == provider_model
        _assert_usage_contains(usage, response_payload["usage"])

    def test_call_litellm_falls_back_to_message_content_when_blocks_empty(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/deepseek-chat",
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    content_blocks=[],
                    message=SimpleNamespace(content="message response"),
                )
            ],
            usage=None,
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "message response"
        assert model_used == "openai/deepseek-chat"
        _assert_no_provider_usage_hmac_only(usage)
        assert "message_count" not in usage
        assert "known_dynamic_marker_positions" not in usage

    def test_call_litellm_normalizes_kimi_k26_temperature(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/kimi-k2.6",
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response) as mock_dispatch:
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "openai/kimi-k2.6"
        _assert_usage_contains(usage, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
        call_kwargs = mock_dispatch.call_args.args[1]
        assert call_kwargs["temperature"] == 1.0

    def test_call_litellm_non_stream_records_legacy_message_audit_for_actual_messages(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        prompt = (
            "# 决策仪表盘分析请求\n"
            "| 股票代码 | **600519** |\n"
            "| 股票名称 | **贵州茅台** |\n"
            "| 分析日期 | 2026-06-19 |\n\n"
            "## ✅ 分析任务\n"
            "请输出 JSON。"
        )
        fixed_rules_offset = prompt.index("## ✅ 分析任务")
        audit_context = {
            "language": "zh",
            "market_group": "cn",
            "analysis_mode": "stock_analysis",
            "dynamic_markers": [
                {"marker_name": "stock_code", "message_role": "user", "text": "600519"},
                {"marker_name": "stock_name", "message_role": "user", "text": "贵州茅台"},
                {"marker_name": "analysis_date", "message_role": "user", "text": "2026-06-19"},
            ],
        }
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=1, total_tokens=11),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response):
            text, model_used, usage = analyzer._call_litellm(
                prompt,
                {"max_tokens": 128, "temperature": 0.2},
                system_prompt="system prompt",
                audit_context=audit_context,
            )

        assert text == "ok"
        assert model_used == "openai/gpt-4o-mini"
        _assert_usage_contains(usage, {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11})
        assert usage["provider"] == "openai"
        assert usage["message_count"] == 2
        markers = {
            marker["marker_name"]: marker
            for marker in json.loads(usage["known_dynamic_marker_positions"])
        }
        for marker_name in ("stock_code", "stock_name", "analysis_date"):
            assert markers[marker_name]["message_role"] == "user"
            assert markers[marker_name]["char_offset"] < fixed_rules_offset
        assert "600519" not in usage["known_dynamic_marker_positions"]
        assert "贵州茅台" not in usage["known_dynamic_marker_positions"]
        assert "2026-06-19" not in usage["known_dynamic_marker_positions"]

    def test_call_litellm_system_hmac_distinguishes_language_and_market_prompt(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=1, total_tokens=11),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response):
            _, _, zh_usage = analyzer._call_litellm(
                "same user prompt 600519",
                {"max_tokens": 128, "temperature": 0.2},
                system_prompt="system prompt zh cn",
                audit_context={
                    "language": "zh",
                    "market_group": "cn",
                    "analysis_mode": "stock_analysis",
                    "dynamic_markers": [
                        {"marker_name": "stock_code", "message_role": "user", "text": "600519"},
                    ],
                },
            )
            _, _, en_usage = analyzer._call_litellm(
                "same user prompt 600519",
                {"max_tokens": 128, "temperature": 0.2},
                system_prompt="system prompt en us",
                audit_context={
                    "language": "en",
                    "market_group": "us",
                    "analysis_mode": "stock_analysis",
                    "dynamic_markers": [
                        {"marker_name": "stock_code", "message_role": "user", "text": "600519"},
                    ],
                },
            )

        assert zh_usage["system_message_hmac"] != en_usage["system_message_hmac"]
        assert zh_usage["messages_hmac"] != en_usage["messages_hmac"]
        assert zh_usage["user_message_hmac"] == en_usage["user_message_hmac"]
        assert zh_usage["market_group"] == "cn"
        assert en_usage["market_group"] == "us"

    def test_call_litellm_normalizes_kimi_k26_temperature_for_yaml_alias(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="kimi_router",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "kimi_router",
                    "litellm_params": {"model": "openai/kimi-k2.6"},
                }
            ],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response) as mock_dispatch:
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "kimi_router"
        _assert_usage_contains(usage, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
        call_kwargs = mock_dispatch.call_args.args[1]
        assert call_kwargs["temperature"] == 1.0

    def test_call_litellm_normalizes_kimi_k26_temperature_for_non_thinking_yaml_alias(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="kimi_router",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "kimi_router",
                    "litellm_params": {
                        "model": "openai/kimi-k2.6",
                        "extra_body": {"thinking": {"type": "disabled"}},
                    },
                }
            ],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response) as mock_dispatch:
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "kimi_router"
        _assert_usage_contains(usage, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
        call_kwargs = mock_dispatch.call_args.args[1]
        assert call_kwargs["temperature"] == 0.6

    def test_call_litellm_resolves_anthropic_alias_for_usage_normalization(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="claude-router",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "claude-router",
                    "litellm_params": {"model": "anthropic/claude-sonnet-test"},
                }
            ],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=30,
                cache_read_input_tokens=10,
                cache_creation_input_tokens=20,
            ),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "claude-router"
        assert usage["prompt_tokens"] == 130
        assert usage["completion_tokens"] == 30
        assert usage["total_tokens"] == 160
        assert usage["normalized_cache_read_tokens"] == 10
        assert usage["normalized_cache_write_tokens"] == 20
        assert usage["cache_observation"] == "read_and_write"

    def test_call_litellm_uses_openai_wire_model_for_alias_usage_threshold(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="fast",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "fast",
                    "litellm_params": {"model": "openai/gpt-4o"},
                }
            ],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(
                prompt_tokens=500,
                completion_tokens=20,
                total_tokens=520,
                prompt_tokens_details={"cached_tokens": 0},
            ),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "fast"
        assert usage["provider_min_cache_tokens"] == 1024
        assert usage["cache_capability"] == "supported"
        assert usage["cache_eligibility"] == "below_threshold"
        assert usage["cache_observation"] == "unknown"
        assert usage["normalized_cache_read_tokens"] == 0
        assert usage["normalized_cache_eligible_input_tokens"] is None
        assert usage["normalized_cache_hit_ratio"] is None

    def test_call_litellm_preserves_anthropic_litellm_prompt_tokens_without_input_tokens(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="claude-router",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "claude-router",
                    "litellm_params": {"model": "anthropic/claude-sonnet-test"},
                }
            ],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "claude-router"
        assert usage["prompt_tokens"] == 100
        assert usage["completion_tokens"] == 20
        assert usage["total_tokens"] == 120
        assert usage["normalized_prompt_tokens"] == 100
        assert usage["normalized_uncached_input_tokens"] == 100
        assert usage["cache_observation"] == "zero_hit"
        assert usage["messages_hmac"] and len(usage["messages_hmac"]) == 64

    def test_call_litellm_stream_resolves_glm_alias_for_usage_normalization(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="glm-router",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "glm-router",
                    "litellm_params": {"model": "zhipu/glm-4.5"},
                }
            ],
        )

        def stream_response():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(
                    prompt_tokens=1200,
                    completion_tokens=80,
                    total_tokens=1280,
                    prompt_tokens_details={"cached_tokens": 1200},
                ),
            )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=stream_response()):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
                stream=True,
            )

        assert text == "ok"
        assert model_used == "glm-router"
        assert usage["normalized_cache_read_tokens"] == 1200
        assert usage["cache_capability"] == "supported"
        assert usage["cache_observation"] == "full_hit"

    def test_call_litellm_stream_uses_openai_wire_model_for_alias_usage_threshold(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="fast",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "fast",
                    "litellm_params": {"model": "openai/gpt-4o"},
                }
            ],
        )

        def stream_response():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(
                    prompt_tokens=500,
                    completion_tokens=20,
                    total_tokens=520,
                    prompt_tokens_details={"cached_tokens": 0},
                ),
            )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=stream_response()):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
                stream=True,
            )

        assert text == "ok"
        assert model_used == "fast"
        assert usage["provider_min_cache_tokens"] == 1024
        assert usage["cache_capability"] == "supported"
        assert usage["cache_eligibility"] == "below_threshold"
        assert usage["cache_observation"] == "unknown"
        assert usage["normalized_cache_read_tokens"] == 0
        assert usage["normalized_cache_eligible_input_tokens"] is None
        assert usage["normalized_cache_hit_ratio"] is None

    def test_call_litellm_omits_temperature_for_gpt5_family(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/gpt5.5-ferr",
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=response) as mock_dispatch:
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "openai/gpt5.5-ferr"
        _assert_usage_contains(usage, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
        call_kwargs = mock_dispatch.call_args.args[1]
        assert "temperature" not in call_kwargs

    def test_call_litellm_recovers_from_temperature_default_error(self):
        from src.llm.generation_params import clear_litellm_generation_param_recovery_cache

        clear_litellm_generation_param_recovery_cache()
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/custom-default-temp",
            litellm_fallback_models=[],
            llm_model_list=[],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        calls = []

        def _dispatch(model, call_kwargs, **_kwargs):
            calls.append(dict(call_kwargs))
            if len(calls) == 1:
                raise RuntimeError(
                    "temperature=0.2 is unsupported. Only the default (1.0) value is supported."
                )
            return response

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=_dispatch):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "ok"
        assert model_used == "openai/custom-default-temp"
        _assert_usage_contains(usage, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
        assert calls[0]["temperature"] == 0.2
        assert calls[1]["temperature"] == 1.0

    def test_call_litellm_keeps_user_temperature_for_non_kimi_fallback(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/kimi-k2.6",
            litellm_fallback_models=["openai/gpt-4o-mini"],
            llm_model_list=[],
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="fallback ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        temperatures = []

        def fake_dispatch(model, call_kwargs, **kwargs):
            temperatures.append((model, call_kwargs["temperature"]))
            if model == "openai/kimi-k2.6":
                raise RuntimeError("primary failed")
            return response

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert text == "fallback ok"
        assert model_used == "openai/gpt-4o-mini"
        _assert_usage_contains(usage, {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
        assert temperatures == [
            ("openai/kimi-k2.6", 1.0),
            ("openai/gpt-4o-mini", 0.2),
        ]

    def test_call_litellm_stream_falls_back_to_non_stream_after_partial_and_falls_back_model(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="provider/bad-model",
            litellm_fallback_models=["provider/good-model"],
            llm_model_list=[],
        )

        def partial_then_broken_stream():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="abc"))],
                usage=None,
            )
            raise RuntimeError("stream disconnected")

        def good_stream():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="fallback"))],
                usage=SimpleNamespace(prompt_tokens=4, completion_tokens=5, total_tokens=9),
            )

        fallback_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="fallback full"))],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=8, total_tokens=15),
        )

        dispatch_calls = []

        def fake_dispatch(model, call_kwargs, **kwargs):
            dispatch_calls.append((model, bool(call_kwargs.get("stream"))))
            if model == "provider/bad-model":
                if call_kwargs.get("stream"):
                    return partial_then_broken_stream()
                raise RuntimeError("non-stream model broken")
            if call_kwargs.get("stream"):
                return good_stream()
            return fallback_response

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch):
            text, model_used, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
                stream=True,
            )

        assert text == "fallback"
        assert model_used == "provider/good-model"
        _assert_usage_contains(usage, {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9})
        assert dispatch_calls == [
            ("provider/bad-model", True),
            ("provider/bad-model", False),
            ("provider/good-model", True),
        ]

    def test_analyze_integrity_retry_keeps_progress_monotonic(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            gemini_request_delay=0,
            report_language="zh",
            litellm_model="gemini/gemini-2.0-flash",
            llm_temperature=0.2,
            report_integrity_enabled=True,
            report_integrity_retry=1,
        )

        from src.analyzer import AnalysisResult

        progress_updates = []
        first_result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=80,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="首轮结果",
        )
        second_result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=82,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="补全后结果",
        )

        with patch.object(analyzer, "is_available", return_value=True), \
             patch.object(analyzer, "_get_analysis_system_prompt", return_value="system"), \
             patch.object(analyzer, "_format_prompt", return_value="prompt"), \
             patch.object(
                 analyzer,
                 "_call_litellm",
                 side_effect=[
                     ("first response", "model-a", {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}),
                     ("second response", "model-a", {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}),
                 ],
             ), \
             patch.object(analyzer, "_parse_response", side_effect=[first_result, second_result]), \
             patch.object(analyzer, "_build_market_snapshot", return_value={}), \
             patch.object(
                 analyzer,
                 "_check_content_integrity",
                 side_effect=[(False, ["analysis_summary"]), (True, [])],
             ), \
             patch.object(analyzer, "_build_integrity_retry_prompt", return_value="retry prompt"), \
             patch("src.analyzer.persist_llm_usage"):
            result = analyzer.analyze(
                {"code": "600519", "stock_name": "贵州茅台"},
                progress_callback=lambda progress, message: progress_updates.append((progress, message)),
            )

        assert result.analysis_summary == "补全后结果"
        assert [progress for progress, _ in progress_updates] == [68, 93, 94, 95]
        assert "补全重试" in progress_updates[2][1]
        assert "解析 JSON" in progress_updates[3][1]

    def test_analyze_persists_provider_usage_from_private_stream_hidden_usage_best_effort(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            gemini_request_delay=0,
            report_language="zh",
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.2,
            report_integrity_enabled=False,
            report_integrity_retry=0,
        )

        from src.analyzer import AnalysisResult

        parsed_result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=80,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="分析结果",
        )

        def stream_response():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content='{"sentiment_score":80}'))],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=""))],
                usage=None,
                _hidden_params={
                    "usage": SimpleNamespace(prompt_tokens=11, completion_tokens=2, total_tokens=13)
                },
            )

        with patch.object(analyzer, "is_available", return_value=True), \
             patch.object(analyzer, "_get_analysis_system_prompt", return_value="system"), \
             patch.object(analyzer, "_get_skill_prompt_sections", return_value=("RSI skill raw", "Default skill policy", False)), \
             patch.object(analyzer, "_format_prompt", return_value="prompt"), \
             patch.object(analyzer, "_validate_json_response"), \
             patch.object(analyzer, "_dispatch_litellm_completion", return_value=stream_response()), \
             patch.object(analyzer, "_parse_response", return_value=parsed_result), \
             patch.object(analyzer, "_build_market_snapshot", return_value={}), \
             patch("src.analyzer.persist_llm_usage") as mock_usage:
            result = analyzer.analyze({"code": "600519", "stock_name": "贵州茅台"})

        assert result.analysis_summary == "分析结果"
        mock_usage.assert_called_once()
        usage_arg, model_arg = mock_usage.call_args[0]
        assert model_arg == "openai/gpt-4o-mini"
        _assert_usage_contains(usage_arg, {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13})
        assert usage_arg["language"] == "zh"
        assert usage_arg["market_group"] == "cn"
        assert usage_arg["analysis_mode"] == "stock_analysis"
        assert usage_arg["legacy_prompt_mode"] == "skill_aware"
        assert usage_arg["skill_config_hmac"] and len(usage_arg["skill_config_hmac"]) == 64
        assert usage_arg["provider"] == "openai"
        assert usage_arg["transport"] == "litellm"
        assert usage_arg["message_count"] == 2
        assert json.loads(usage_arg["known_dynamic_marker_positions"]) == []
        assert mock_usage.call_args.kwargs == {"call_type": "analysis", "stock_code": "600519"}

    def test_analyze_records_marker_positions_from_real_prompt_format(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            gemini_request_delay=0,
            report_language="zh",
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.2,
            report_integrity_enabled=False,
            report_integrity_retry=0,
            news_max_age_days=3,
            news_strategy_profile="short",
        )

        from src.analyzer import AnalysisResult

        parsed_result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=80,
            trend_prediction="看多",
            operation_advice="持有",
            analysis_summary="分析结果",
        )

        def stream_response():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content='{"sentiment_score":80}'))],
                usage=SimpleNamespace(prompt_tokens=42, completion_tokens=3, total_tokens=45),
            )

        context = {
            "code": "600519",
            "stock_name": "贵州茅台",
            "date": "2026-06-19",
            "today": {
                "close": 1500,
                "open": 1490,
                "high": 1510,
                "low": 1480,
                "pct_chg": 1.2,
                "volume": 100000,
                "amount": 150000000,
            },
            "market_phase_context": {
                "phase": "intraday",
                "is_partial_bar": False,
            },
            "daily_market_context": {
                "summary": "市场偏谨慎，等待量能确认。",
                "region": "cn",
                "trade_date": "2026-06-19",
            },
        }

        with patch.object(analyzer, "is_available", return_value=True), \
             patch.object(analyzer, "_get_analysis_system_prompt", return_value="system"), \
             patch.object(analyzer, "_get_skill_prompt_sections", return_value=("RSI skill raw", "Default skill policy", False)), \
             patch.object(analyzer, "_validate_json_response"), \
             patch.object(analyzer, "_dispatch_litellm_completion", return_value=stream_response()), \
             patch.object(analyzer, "_parse_response", return_value=parsed_result), \
             patch.object(analyzer, "_build_market_snapshot", return_value={}), \
             patch("src.analyzer.persist_llm_usage") as mock_usage:
            result = analyzer.analyze(
                context,
                news_context="2026-06-18 贵州茅台发布经营公告。",
                analysis_context_pack_summary="## 分析上下文包\n- 估值处于中性区间。",
            )

        assert result.analysis_summary == "分析结果"
        mock_usage.assert_called_once()
        usage_arg, _ = mock_usage.call_args[0]
        markers = {
            marker["marker_name"]: marker
            for marker in json.loads(usage_arg["known_dynamic_marker_positions"])
        }
        for marker_name in (
            "stock_code",
            "stock_name",
            "analysis_date",
            "market_phase",
            "daily_market_context",
            "analysis_context_pack",
            "quote",
            "news_context",
        ):
            assert marker_name in markers
            assert markers[marker_name]["message_role"] == "user"
            assert isinstance(markers[marker_name]["char_offset"], int)
            assert markers[marker_name]["char_offset"] >= 0
        assert usage_arg["legacy_prompt_mode"] == "skill_aware"
        assert usage_arg["skill_config_hmac"] and len(usage_arg["skill_config_hmac"]) == 64
        assert "600519" not in usage_arg["known_dynamic_marker_positions"]
        assert "贵州茅台" not in usage_arg["known_dynamic_marker_positions"]
        assert "2026-06-19" not in usage_arg["known_dynamic_marker_positions"]
