# -*- coding: utf-8 -*-
"""Analyzer generation backend and response contracts."""

from tests.market_analyzer_generate_text_support import (
    MagicMock,
    SimpleNamespace,
    _OPENAI_COMPATIBILITY_PAYLOAD_FIXTURES,
    _assert_no_provider_usage_hmac_only,
    _assert_usage_contains,
    _llm_usage_hmac_env,
    contextmanager,
    json,
    patch,
    pytest,
)


# Analyzer.generate_text()

class TestAnalyzerGenerateText:
    def _make_analyzer(self):
        """Return a minimally configured GeminiAnalyzer with _call_litellm mocked."""
        with patch("src.analyzer.get_config") as mock_cfg:
            cfg = MagicMock()
            cfg.litellm_model = "gemini/gemini-2.0-flash"
            cfg.litellm_fallback_models = []
            cfg.gemini_api_keys = ["sk-gemini-testkey-1234"]
            cfg.anthropic_api_keys = []
            cfg.openai_api_keys = []
            cfg.deepseek_api_keys = []
            cfg.llm_model_list = []
            cfg.openai_base_url = None
            cfg.generation_backend = "litellm"
            cfg.generation_fallback_backend = "litellm"
            mock_cfg.return_value = cfg
            from src.analyzer import GeminiAnalyzer
            analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
            analyzer._router = None
            analyzer._litellm_available = True
            analyzer._config_override = cfg
            return analyzer

    def test_legacy_market_group_normalizes_supported_markets(self):
        from src.analyzer import _legacy_market_group

        assert _legacy_market_group("") == "unknown"
        assert _legacy_market_group("unknown") == "unknown"
        assert _legacy_market_group("600519") == "cn"
        assert _legacy_market_group("hk00700") == "hk"
        assert _legacy_market_group("AAPL") == "us"

    def test_legacy_audit_marker_specs_use_language_and_optional_context(self):
        from src.analyzer import _legacy_audit_marker_specs

        zh_markers = _legacy_audit_marker_specs(
            {"date": "2026-06-19"},
            code="600519",
            stock_name="贵州茅台",
            report_language="zh",
            news_context="news",
            analysis_context_pack_summary="pack summary",
        )
        zh_by_name = {marker["marker_name"]: marker for marker in zh_markers}

        assert zh_by_name["stock_code"]["text"] == "600519"
        assert zh_by_name["stock_name"]["text"] == "贵州茅台"
        assert zh_by_name["analysis_date"]["text"] == "2026-06-19"
        assert zh_by_name["market_phase"]["text"] == "## 市场阶段上下文"
        assert zh_by_name["daily_market_context"]["text"] == "## 大盘环境摘要"
        assert zh_by_name["analysis_context_pack"]["text"] == "pack summary"
        assert zh_by_name["quote"]["text"] == "## 📈 技术面数据"
        assert zh_by_name["news_context"]["text"] == "## 📰 舆情情报"
        assert {marker["message_role"] for marker in zh_markers} == {"user"}

        en_markers = _legacy_audit_marker_specs(
            {"date": ""},
            code="AAPL",
            stock_name="Apple",
            report_language="en",
            news_context=None,
            analysis_context_pack_summary=None,
        )
        en_by_name = {marker["marker_name"]: marker for marker in en_markers}

        assert en_by_name["market_phase"]["text"] == "## Market Phase Context"
        assert en_by_name["daily_market_context"]["text"] == "## Daily Market Context"
        assert "analysis_date" not in en_by_name
        assert "analysis_context_pack" not in en_by_name
        assert "news_context" not in en_by_name

    def test_generate_text_returns_llm_response(self):
        analyzer = self._make_analyzer()
        with patch.object(analyzer, "_call_litellm", return_value="市场分析报告") as mock_call:
            result = analyzer.generate_text("写一份复盘", max_tokens=1024, temperature=0.5)
            assert result == "市场分析报告"
            mock_call.assert_called_once_with(
                "写一份复盘",
                generation_config={"max_tokens": 1024, "temperature": 0.5},
            )

    def test_generate_text_does_not_persist_unavailable_usage(self):
        analyzer = self._make_analyzer()
        usage = {
            "usage_available": False,
            "usage_source": "unavailable",
            "backend": "codex_cli",
        }
        with patch.object(analyzer, "_call_litellm", return_value=("复盘", "codex_cli", usage)), \
             patch("src.analyzer.persist_llm_usage") as mock_persist:
            result = analyzer.generate_text("写一份复盘")

        assert result == "复盘"
        mock_persist.assert_not_called()

    @pytest.mark.parametrize(
        ("generation_backend", "executable_name"),
        [
            ("codex_cli", "codex"),
            ("claude_code_cli", "claude"),
            ("opencode_cli", "opencode"),
        ],
    )
    def test_local_cli_is_available_without_litellm_api_keys(self, generation_backend, executable_name):
        analyzer = self._make_analyzer()
        analyzer._litellm_available = False
        analyzer._router = None
        analyzer._config_override = SimpleNamespace(
            generation_backend=generation_backend,
            generation_fallback_backend="",
            generation_backend_timeout_seconds=300,
            generation_backend_max_output_bytes=1048576,
            generation_backend_max_concurrency=1,
            local_cli_backend_max_concurrency=1,
        )

        with patch("src.llm.local_cli_backend.shutil.which", return_value=f"/usr/bin/{executable_name}"), \
             patch("src.llm.local_cli_backend.os.access", return_value=True):
            assert analyzer.get_generation_backend_config_error() is None
            assert analyzer.is_available() is True

    def test_analyze_uses_litellm_fallback_when_codex_cli_config_error_is_fallbackable(self):
        from src.llm.generation_backend import GenerationBackend, GenerationError, GenerationErrorCode
        from src.llm.local_cli_backend import LocalCliGenerationBackend

        analyzer = self._make_analyzer()
        analyzer._litellm_available = True
        analyzer._config_override = SimpleNamespace(
            generation_backend="codex_cli",
            generation_fallback_backend="litellm",
            litellm_model="gemini/gemini-2.0-flash",
            litellm_fallback_models=[],
            llm_model_list=[],
            report_language="zh",
            gemini_request_delay=0,
            llm_temperature=0.7,
            report_integrity_enabled=False,
            report_integrity_retry=0,
        )
        codex_error = GenerationError(
            error_code=GenerationErrorCode.COMMAND_NOT_FOUND,
            stage="configuration",
            retryable=False,
            fallbackable=True,
            backend="codex_cli",
            provider="codex_cli",
            details={"reason": "executable_not_found"},
        )
        primary_backend = MagicMock(spec=LocalCliGenerationBackend)
        primary_backend.get_config_error.return_value = codex_error
        primary_backend.generate.side_effect = codex_error
        fallback_backend = MagicMock(spec=GenerationBackend)
        fallback_backend.generate.return_value = SimpleNamespace(
            text=json.dumps({
                "sentiment_score": 70,
                "trend_prediction": "看多",
                "operation_advice": "持有",
                "analysis_summary": "fallback ok",
            }),
            model="gemini/gemini-2.0-flash",
            usage={
                "usage_available": False,
                "usage_source": "unavailable",
                "backend": "litellm",
            },
        )

        def _backend_for(backend_id=None):
            return primary_backend if backend_id == "codex_cli" else fallback_backend

        with patch.object(analyzer, "_get_generation_backend", side_effect=_backend_for), \
             patch.object(analyzer, "_get_analysis_system_prompt", return_value="system"), \
             patch.object(analyzer, "_get_skill_prompt_sections", return_value=(None, None, True)), \
             patch.object(analyzer, "_format_prompt", return_value="prompt"), \
             patch.object(analyzer, "_build_market_snapshot", return_value={}):
            assert analyzer.is_available() is True
            result = analyzer.analyze({"code": "600519", "stock_name": "贵州茅台"})

        assert result.success is True
        assert result.analysis_summary == "fallback ok"
        primary_backend.generate.assert_called()
        fallback_backend.generate.assert_called()

    def test_analyze_preserves_litellm_text_fallback_after_codex_cli_primary_failure(self):
        from src.analyzer import AnalysisResult, _AllModelsFailedError
        from src.llm.generation_backend import GenerationBackend, GenerationError, GenerationErrorCode

        analyzer = self._make_analyzer()
        analyzer._litellm_available = True
        analyzer._config_override = SimpleNamespace(
            generation_backend="codex_cli",
            generation_fallback_backend="litellm",
            litellm_model="provider/primary-model",
            litellm_fallback_models=["provider/fallback-model"],
            llm_model_list=[],
            report_language="zh",
            gemini_request_delay=0,
            llm_temperature=0.7,
            report_integrity_enabled=False,
            report_integrity_retry=0,
        )
        primary_error = GenerationError(
            error_code=GenerationErrorCode.COMMAND_NOT_FOUND,
            stage="configuration",
            retryable=False,
            fallbackable=True,
            backend="codex_cli",
            provider="codex_cli",
            details={"reason": "executable_not_found"},
        )
        all_models_error = _AllModelsFailedError(
            "all fallback models returned invalid JSON",
            last_response_text="这不是 JSON，而是 fallback 模型返回的纯文本分析",
            last_model="provider/fallback-model",
            last_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
        text_fallback_result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=50,
            trend_prediction="震荡",
            operation_advice="持有",
            analysis_summary="纯文本兜底摘要",
            success=False,
            error_message="LLM response is not valid JSON; analysis result will not be persisted",
        )
        primary_backend = MagicMock(spec=GenerationBackend)
        primary_backend.generate.side_effect = primary_error
        fallback_backend = MagicMock(spec=GenerationBackend)
        fallback_backend.generate.side_effect = all_models_error

        def _backend_for(backend_id):
            return primary_backend if backend_id == "codex_cli" else fallback_backend

        with patch.object(analyzer, "get_generation_backend_config_error", return_value=None), \
             patch.object(analyzer, "is_available", return_value=True), \
             patch.object(analyzer, "_get_generation_backend", side_effect=_backend_for), \
             patch.object(analyzer, "_get_analysis_system_prompt", return_value="system"), \
             patch.object(analyzer, "_get_skill_prompt_sections", return_value=(None, None, True)), \
             patch.object(analyzer, "_format_prompt", return_value="prompt"), \
             patch.object(analyzer, "_parse_response", return_value=text_fallback_result) as mock_parse, \
             patch.object(analyzer, "_build_market_snapshot", return_value={}), \
             patch("src.analyzer.persist_llm_usage") as mock_persist:
            result = analyzer.analyze({"code": "600519", "stock_name": "贵州茅台"})

        assert result.analysis_summary == "纯文本兜底摘要"
        assert result.raw_response == "这不是 JSON，而是 fallback 模型返回的纯文本分析"
        assert result.model_used == "provider/fallback-model"
        mock_parse.assert_called_once_with(
            "这不是 JSON，而是 fallback 模型返回的纯文本分析",
            "600519",
            "贵州茅台",
        )
        mock_persist.assert_called_once_with(
            {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            "provider/fallback-model",
            call_type="analysis",
            stock_code="600519",
        )
        primary_backend.generate.assert_called_once()
        fallback_backend.generate.assert_called_once()

    def test_analyze_does_not_persist_unavailable_usage(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            generation_backend="codex_cli",
            generation_fallback_backend="",
            generation_backend_timeout_seconds=300,
            generation_backend_max_output_bytes=1048576,
            generation_backend_max_concurrency=1,
            local_cli_backend_max_concurrency=1,
            litellm_model="",
            gemini_request_delay=0,
            report_language="zh",
            llm_temperature=0.7,
            report_integrity_enabled=False,
            report_integrity_retry=0,
        )
        response_text = json.dumps({
            "sentiment_score": 70,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "analysis_summary": "测试",
        })
        usage = {
            "usage_available": False,
            "usage_source": "unavailable",
            "backend": "codex_cli",
        }

        with patch.object(analyzer, "get_generation_backend_config_error", return_value=None), \
             patch.object(analyzer, "is_available", return_value=True), \
             patch.object(analyzer, "_get_analysis_system_prompt", return_value="system"), \
             patch.object(analyzer, "_get_skill_prompt_sections", return_value=(None, None, True)), \
             patch.object(analyzer, "_format_prompt", return_value="prompt"), \
             patch.object(analyzer, "_call_litellm", return_value=(response_text, "codex_cli", usage)), \
             patch.object(analyzer, "_build_market_snapshot", return_value={}), \
             patch("src.analyzer.persist_llm_usage") as mock_persist:
            result = analyzer.analyze({"code": "600519", "stock_name": "贵州茅台"})

        assert result.success is True
        mock_persist.assert_not_called()

    def test_generate_text_returns_none_on_failure(self):
        analyzer = self._make_analyzer()
        with patch.object(analyzer, "_call_litellm", side_effect=Exception("LLM error")):
            result = analyzer.generate_text("prompt")
            assert result is None  # must not raise

    def test_generate_text_raises_generation_error_for_unsupported_backend(self):
        from src.llm.generation_backend import GenerationError

        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            generation_backend="codex",
            generation_fallback_backend="litellm",
        )

        with pytest.raises(GenerationError) as exc_info:
            analyzer.generate_text("prompt")

        assert exc_info.value.details["field"] == "GENERATION_BACKEND"
        assert exc_info.value.details["requested_backend"] == "codex"

    def test_generate_text_default_params(self):
        analyzer = self._make_analyzer()
        with patch.object(analyzer, "_call_litellm", return_value="ok") as mock_call:
            analyzer.generate_text("hello")
            _, kwargs = mock_call.call_args
            gen_cfg = kwargs["generation_config"]
            assert gen_cfg["max_tokens"] == 2048
            assert gen_cfg["temperature"] == 0.7

    def test_call_litellm_wrapper_uses_generation_backend_tuple_contract(self):
        from src.llm.generation_backend import GenerationBackend

        analyzer = self._make_analyzer()
        backend = MagicMock(spec=GenerationBackend)
        backend.generate.return_value = SimpleNamespace(
            text="backend response",
            model="gemini/gemini-3.1-pro-preview",
            usage={"provider": "gemini", "total_tokens": 9},
        )

        with patch.object(analyzer, "_get_generation_backend", return_value=backend):
            result = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
                system_prompt="system",
                stream=True,
                stream_progress_callback=lambda _chars: None,
                response_validator=lambda _text: None,
                audit_context={"call_type": "analysis"},
            )

        assert result == (
            "backend response",
            "gemini/gemini-3.1-pro-preview",
            {"provider": "gemini", "total_tokens": 9},
        )
        backend.generate.assert_called_once()
        _, generation_config = backend.generate.call_args.args
        assert generation_config == {"max_tokens": 128, "temperature": 0.2}
        assert backend.generate.call_args.kwargs["system_prompt"] == "system"
        assert backend.generate.call_args.kwargs["stream"] is True
        assert callable(backend.generate.call_args.kwargs["stream_progress_callback"])
        assert callable(backend.generate.call_args.kwargs["response_validator"])
        assert backend.generate.call_args.kwargs["audit_context"] == {"call_type": "analysis"}

    def test_call_litellm_wraps_fallback_generation_error_with_primary_context(self):
        from src.llm.generation_backend import GenerationBackend, GenerationError, GenerationErrorCode

        analyzer = self._make_analyzer()
        analyzer._config_override.generation_backend = "codex_cli"
        analyzer._config_override.generation_fallback_backend = "litellm"
        primary_error = GenerationError(
            error_code=GenerationErrorCode.COMMAND_NOT_FOUND,
            stage="configuration",
            retryable=False,
            fallbackable=True,
            backend="codex_cli",
            provider="codex_cli",
            details={"reason": "executable_not_found"},
        )
        fallback_error = GenerationError(
            error_code=GenerationErrorCode.INVALID_JSON,
            stage="validation",
            retryable=True,
            fallbackable=True,
            backend="litellm",
            provider="gemini",
            details={"reason": "invalid_json"},
        )
        primary_backend = MagicMock(spec=GenerationBackend)
        primary_backend.generate.side_effect = primary_error
        fallback_backend = MagicMock(spec=GenerationBackend)
        fallback_backend.generate.side_effect = fallback_error

        def _backend_for(backend_id):
            return primary_backend if backend_id == "codex_cli" else fallback_backend

        with patch.object(analyzer, "_get_generation_backend", side_effect=_backend_for):
            with pytest.raises(GenerationError) as exc_info:
                analyzer._call_litellm("prompt", {"max_tokens": 128})

        error = exc_info.value
        assert error.stage == "fallback"
        assert error.error_code is GenerationErrorCode.INVALID_JSON
        assert error.details["reason"] == "fallback_backend_failed"
        assert error.details["primary_error"]["error_code"] == "command_not_found"
        assert error.details["primary_error"]["details"]["reason"] == "executable_not_found"
        assert error.details["fallback_error"]["error_code"] == "invalid_json"
        assert error.details["fallback_error"]["details"]["reason"] == "invalid_json"

    def test_call_litellm_rejects_unknown_generation_backend_without_litellm_fallback(self):
        from src.llm.generation_backend import GenerationError

        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            generation_backend="codex",
            generation_fallback_backend="litellm",
        )

        with pytest.raises(GenerationError) as exc_info:
            analyzer._call_litellm("prompt", {"max_tokens": 128})

        assert exc_info.value.details["requested_backend"] == "codex"

    def test_call_litellm_rejects_unknown_generation_fallback_backend(self):
        from src.llm.generation_backend import GenerationError

        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            generation_backend="litellm",
            generation_fallback_backend="codex",
        )

        with pytest.raises(GenerationError) as exc_info:
            analyzer._call_litellm("prompt", {"max_tokens": 128})

        assert exc_info.value.details["field"] == "GENERATION_FALLBACK_BACKEND"
        assert exc_info.value.details["requested_backend"] == "codex"

    def test_analyze_reports_generation_backend_config_error_instead_of_api_key_missing(self):
        analyzer = self._make_analyzer()
        analyzer._litellm_available = True
        analyzer._config_override = SimpleNamespace(
            generation_backend="codex",
            generation_fallback_backend="litellm",
            report_language="zh",
            gemini_request_delay=0,
        )

        with patch.object(analyzer, "_get_analysis_system_prompt", return_value="system"), \
             patch.object(analyzer, "_get_skill_prompt_sections", return_value=(None, None, True)):
            result = analyzer.analyze({"code": "AAPL", "stock_name": "Apple"})

        assert result.success is False
        assert "backend_not_configured" in result.error_message
        assert "GENERATION_BACKEND" in result.error_message
        assert "codex" in result.error_message
        assert "API Key" not in result.error_message
        assert "API Key" not in result.analysis_summary

    def test_call_litellm_stream_aggregates_chunks_and_reports_progress(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="gemini/gemini-2.0-flash",
            litellm_fallback_models=[],
            llm_model_list=[],
        )

        def stream_response():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="abc"))],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="def"))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            )

        progress_updates = []

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=stream_response()):
            text, model, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
                stream=True,
                stream_progress_callback=progress_updates.append,
            )

        assert text == "abcdef"
        assert model == "gemini/gemini-2.0-flash"
        _assert_usage_contains(usage, {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3})
        assert progress_updates == [3, 6]

    def test_call_litellm_stream_reads_private_hidden_usage_best_effort(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=[],
            llm_model_list=[],
        )

        def stream_response():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="abc"))],
                usage=None,
            )
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=""))],
                usage=None,
                _hidden_params={
                    "usage": SimpleNamespace(prompt_tokens=11, completion_tokens=2, total_tokens=13)
                },
            )

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=stream_response()):
            text, model, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
                stream=True,
            )

        assert text == "abc"
        assert model == "openai/gpt-4o-mini"
        _assert_usage_contains(usage, {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13})

    def test_call_litellm_stream_records_legacy_message_audit_for_actual_messages(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="gemini/gemini-2.0-flash",
            litellm_fallback_models=[],
            llm_model_list=[],
        )

        def stream_response():
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=8, completion_tokens=1, total_tokens=9),
            )

        audit_context = {
            "language": "zh",
            "market_group": "cn",
            "analysis_mode": "stock_analysis",
            "dynamic_markers": [
                {"marker_name": "stock_code", "message_role": "user", "text": "600519"},
                {"marker_name": "quote", "message_role": "user", "text": "## 📈 技术面数据"},
            ],
        }

        with patch.object(analyzer, "_dispatch_litellm_completion", return_value=stream_response()):
            text, model, usage = analyzer._call_litellm(
                "## 📊 股票基础信息\n| 股票代码 | **600519** |\n\n## 📈 技术面数据\n",
                {"max_tokens": 128, "temperature": 0.2},
                system_prompt="system prompt",
                stream=True,
                audit_context=audit_context,
            )

        assert text == "ok"
        assert model == "gemini/gemini-2.0-flash"
        _assert_usage_contains(usage, {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9})
        assert usage["language"] == "zh"
        assert usage["market_group"] == "cn"
        assert usage["analysis_mode"] == "stock_analysis"
        assert usage["provider"] == "gemini"
        assert usage["transport"] == "litellm"
        assert usage["message_count"] == 2
        markers = json.loads(usage["known_dynamic_marker_positions"])
        assert [marker["marker_name"] for marker in markers] == ["stock_code", "quote"]
        assert "600519" not in usage["known_dynamic_marker_positions"]

    def test_call_litellm_legacy_path_uses_legacy_model_list_for_param_recovery(self):
        with patch("src.analyzer.get_config") as mock_cfg:
            cfg = MagicMock()
            cfg.litellm_model = "openai/gpt-4o-mini"
            cfg.litellm_fallback_models = []
            cfg.gemini_api_keys = []
            cfg.anthropic_api_keys = []
            cfg.deepseek_api_keys = []
            cfg.openai_api_keys = ["sk-openai-legacy-a", "sk-openai-legacy-b"]
            cfg.openai_base_url = None
            cfg.llm_model_list = [
                {
                    "model_name": "__legacy_openai__",
                    "litellm_params": {
                        "model": "__legacy_openai__",
                        "api_key": "sk-openai-legacy-a",
                        "api_base": "https://legacy-a.example/v1",
                        "extra_headers": {"x-tenant": "legacy-a"},
                    },
                },
                {
                    "model_name": "__legacy_openai__",
                    "litellm_params": {
                        "model": "__legacy_openai__",
                        "api_key": "sk-openai-legacy-b",
                        "api_base": "https://legacy-b.example/v1",
                        "extra_headers": {"x-tenant": "legacy-b"},
                    },
                },
            ]
            cfg.llm_temperature = 0.7
            mock_cfg.return_value = cfg

            from src.analyzer import GeminiAnalyzer

            analyzer = GeminiAnalyzer()
            analyzer._config_override = cfg

        captured = {}

        def _fake_call_litellm_with_param_recovery(call, **kwargs):
            captured["model_list"] = kwargs.get("model_list")
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=None,
            )

        with patch("src.analyzer.call_litellm_with_param_recovery", side_effect=_fake_call_litellm_with_param_recovery):
            text, _, _ = analyzer._call_litellm("回归用例", {"max_tokens": 128, "temperature": 0.7})

        assert text == "ok"
        passed_model_list = captured.get("model_list")
        assert passed_model_list is not None
        assert len(passed_model_list) == 2
        assert all(item["litellm_params"].get("model") == "openai/gpt-4o-mini" for item in passed_model_list)
        assert [item["litellm_params"]["api_base"] for item in passed_model_list] == [
            "https://legacy-a.example/v1",
            "https://legacy-b.example/v1",
        ]
        assert [item["litellm_params"]["extra_headers"] for item in passed_model_list] == [
            {"x-tenant": "legacy-a"},
            {"x-tenant": "legacy-b"},
        ]

    @patch("src.analyzer.Router")
    def test_analyzer_legacy_router_recovery_cache_is_scoped_by_api_base(self, mock_router):
        """Analyzer legacy recovery should not leak across same model different api_base."""
        from src.analyzer import call_litellm_with_param_recovery as real_call
        from src.llm.generation_params import clear_litellm_generation_param_recovery_cache

        clear_litellm_generation_param_recovery_cache()
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="analyzer ok"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )
        strict_router = MagicMock()
        flex_router = MagicMock()
        strict_router.completion.side_effect = [
            RuntimeError("Unsupported parameter: temperature is not supported"),
            response,
        ]
        flex_router.completion.return_value = response
        mock_router.side_effect = [strict_router, flex_router]

        strict_cfg = SimpleNamespace(
            litellm_model="openai/shared-model",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.2,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=["sk-strict-key-1", "sk-strict-key-2"],
            deepseek_api_keys=[],
            openai_base_url="https://strict.example/v1",
        )
        flex_cfg = SimpleNamespace(
            litellm_model="openai/shared-model",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.2,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=["sk-flex-key-1", "sk-flex-key-2"],
            deepseek_api_keys=[],
            openai_base_url="https://flex.example/v1",
        )

        captured_model_lists = []

        def _fake_recovery(call, **kwargs):
            captured_model_lists.append(kwargs.get("model_list"))
            return real_call(call, **kwargs)

        import src.analyzer as analyzer_module
        from src.analyzer import GeminiAnalyzer

        with patch.object(analyzer_module, "call_litellm_with_param_recovery", side_effect=_fake_recovery):
            GeminiAnalyzer(config=strict_cfg)._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )
            GeminiAnalyzer(config=flex_cfg)._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
            )

        assert len(captured_model_lists) == 2
        strict_model_list = captured_model_lists[0]
        flex_model_list = captured_model_lists[1]
        assert strict_model_list is not None
        assert flex_model_list is not None
        assert all(
            item.get("litellm_params", {}).get("api_base") == "https://strict.example/v1"
            for item in strict_model_list
        )
        assert all(
            item.get("litellm_params", {}).get("api_base") == "https://flex.example/v1"
            for item in flex_model_list
        )
        assert strict_router.completion.call_args_list[0].kwargs["temperature"] == 0.2
        assert "temperature" not in strict_router.completion.call_args_list[1].kwargs
        assert flex_router.completion.call_args.kwargs["temperature"] == 0.2

    def test_prompt_cache_hints_disabled_does_not_change_analyzer_request_shape(self):
        from src.analyzer import GeminiAnalyzer

        cfg = SimpleNamespace(
            litellm_model="openai/gpt-4o",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.7,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=["sk-openai-test"],
            deepseek_api_keys=[],
            openai_base_url=None,
            llm_prompt_cache_telemetry_enabled=True,
            llm_prompt_cache_hints_enabled=False,
            llm_prompt_cache_diagnostics_level="off",
        )
        analyzer = GeminiAnalyzer(config=cfg)
        captured = {}

        def _fake_recovery(call, **kwargs):
            captured["call_kwargs"] = kwargs["call_kwargs"]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage={"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
            )

        with patch("src.analyzer.call_litellm_with_param_recovery", side_effect=_fake_recovery):
            text, _, _ = analyzer._call_litellm("dynamic prompt", {"max_tokens": 128, "temperature": 0.7})

        assert text == "ok"
        call_kwargs = captured["call_kwargs"]
        assert "prompt_cache_key" not in call_kwargs
        assert call_kwargs["messages"] == [
            {"role": "system", "content": analyzer.TEXT_SYSTEM_PROMPT},
            {"role": "user", "content": "dynamic prompt"},
        ]

    def test_prompt_cache_telemetry_disabled_filters_cache_fields_from_analyzer_usage(self):
        from src.analyzer import GeminiAnalyzer

        cfg = SimpleNamespace(
            litellm_model="openai/gpt-4o",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.7,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=["sk-openai-test"],
            deepseek_api_keys=[],
            openai_base_url=None,
            llm_prompt_cache_telemetry_enabled=False,
            llm_prompt_cache_hints_enabled=False,
            llm_prompt_cache_diagnostics_level="off",
        )
        analyzer = GeminiAnalyzer(config=cfg)

        def _fake_recovery(call, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage={
                    "prompt_tokens": 1200,
                    "completion_tokens": 1,
                    "total_tokens": 1201,
                    "prompt_tokens_details": {"cached_tokens": 1000},
                },
            )

        with patch("src.analyzer.call_litellm_with_param_recovery", side_effect=_fake_recovery):
            _, _, usage = analyzer._call_litellm("dynamic prompt", {"max_tokens": 128, "temperature": 0.7})

        assert usage["prompt_tokens"] == 1200
        assert usage["completion_tokens"] == 1
        assert usage["total_tokens"] == 1201
        assert "provider_usage_json" not in usage
        assert "normalized_cache_read_tokens" not in usage
        assert "cache_capability" not in usage
        assert usage["messages_hmac"]

    def test_prompt_cache_telemetry_disabled_marks_no_usage_response_for_storage(self):
        from src.analyzer import GeminiAnalyzer

        cfg = SimpleNamespace(
            litellm_model="openai/gpt-4o",
            litellm_fallback_models=[],
            llm_model_list=[],
            llm_temperature=0.7,
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=["sk-openai-test"],
            deepseek_api_keys=[],
            openai_base_url=None,
            llm_prompt_cache_telemetry_enabled=False,
            llm_prompt_cache_hints_enabled=False,
            llm_prompt_cache_diagnostics_level="off",
        )
        analyzer = GeminiAnalyzer(config=cfg)

        def _fake_recovery(call, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=None,
            )

        with patch("src.analyzer.call_litellm_with_param_recovery", side_effect=_fake_recovery):
            text, _, usage = analyzer._call_litellm("dynamic prompt", {"max_tokens": 128, "temperature": 0.7})

        assert text == "ok"
        assert getattr(usage, "prompt_cache_telemetry_disabled", False)
        assert "cache_capability" not in usage
        assert "cache_eligibility" not in usage
        assert "cache_observation" not in usage
        assert usage["messages_hmac"]

    def test_call_litellm_stream_falls_back_to_non_stream_before_first_chunk(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="gemini/gemini-2.0-flash",
            litellm_fallback_models=[],
            llm_model_list=[],
        )

        def broken_stream():
            raise RuntimeError("stream unsupported")
            yield  # pragma: no cover

        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="full response"))],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=5, total_tokens=9),
        )

        dispatch_calls = []

        def fake_dispatch(model, call_kwargs, **kwargs):
            dispatch_calls.append(call_kwargs.copy())
            if call_kwargs.get("stream"):
                return broken_stream()
            return response

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch):
            text, model, usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
                stream=True,
            )

        assert text == "full response"
        assert model == "gemini/gemini-2.0-flash"
        _assert_usage_contains(usage, {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9})
        assert len(dispatch_calls) == 2
        assert dispatch_calls[0]["stream"] is True
        assert "stream" not in dispatch_calls[1]

    def test_call_litellm_hermes_route_forces_non_stream_direct_client(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/hermes-agent",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "openai/hermes-agent",
                    "litellm_params": {
                        "model": "openai/hermes-agent",
                        "api_key": "sk-hermes-test-value",
                        "api_base": "http://127.0.0.1:8642/v1",
                    },
                    "model_info": {"dsa_channel": "hermes"},
                }
            ],
            llm_temperature=0.0,
            generation_backend="litellm",
            generation_fallback_backend="litellm",
            llm_channel_config_issues=[],
            llm_blocks_legacy_fallback=False,
        )
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
        seen_kwargs = {}

        @contextmanager
        def fake_no_proxy_client(**_kwargs):
            yield object()

        def fake_completion(**kwargs):
            seen_kwargs.update(kwargs)
            return response

        with patch("src.analyzer.open_hermes_no_proxy_client", side_effect=fake_no_proxy_client), \
             patch("src.analyzer.litellm.completion", side_effect=fake_completion):
            text, model, _usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.0},
                stream=True,
            )

        assert text == "OK"
        assert model == "openai/hermes-agent"
        assert seen_kwargs["model"] == "openai/hermes-agent"
        assert seen_kwargs["stream"] is False
        assert "api_key" not in seen_kwargs
        assert "api_base" not in seen_kwargs
        assert "client" in seen_kwargs

    def test_call_litellm_hermes_failure_redacts_secret_from_logs_and_error(self, caplog):
        from src.analyzer import _AllModelsFailedError

        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/hermes-agent",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "openai/hermes-agent",
                    "litellm_params": {
                        "model": "openai/hermes-agent",
                        "api_key": "saved-secret-token",
                        "api_base": "http://127.0.0.1:8642/v1",
                    },
                    "model_info": {"dsa_channel": "hermes"},
                }
            ],
            llm_temperature=0.0,
            generation_backend="litellm",
            generation_fallback_backend="",
            llm_channel_config_issues=[],
            llm_blocks_legacy_fallback=False,
        )

        @contextmanager
        def fake_no_proxy_client(**_kwargs):
            yield object()

        caplog.set_level("WARNING", logger="src.analyzer")
        with patch("src.analyzer.open_hermes_no_proxy_client", side_effect=fake_no_proxy_client), \
             patch("src.analyzer.litellm.completion", side_effect=RuntimeError("upstream saw saved-secret-token")):
            with pytest.raises(_AllModelsFailedError) as exc_info:
                analyzer._call_litellm("prompt", {"max_tokens": 4})

        assert "saved-secret-token" not in str(exc_info.value)
        assert "saved-secret-token" not in caplog.text
        assert "[REDACTED]" in str(exc_info.value)

    def test_analyze_redacts_hermes_secret_from_final_error_result(self, caplog):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/hermes-agent",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "openai/hermes-agent",
                    "litellm_params": {
                        "model": "openai/hermes-agent",
                        "api_key": "saved-secret-token",
                        "api_base": "http://127.0.0.1:8642/v1",
                    },
                    "model_info": {"dsa_channel": "hermes"},
                }
            ],
            generation_backend="litellm",
            generation_fallback_backend="",
            llm_channel_config_issues=[],
            llm_blocks_legacy_fallback=False,
            llm_temperature=0.0,
            report_integrity_enabled=False,
            report_integrity_retry=0,
            report_language="zh",
            gemini_request_delay=0,
        )
        context = {"code": "600519", "stock_name": "贵州茅台"}

        caplog.set_level("ERROR", logger="src.analyzer")
        with patch.object(analyzer, "get_generation_backend_config_error", return_value=None), \
             patch.object(analyzer, "is_available", return_value=True), \
             patch.object(analyzer, "_get_analysis_system_prompt", return_value="system"), \
             patch.object(analyzer, "_get_skill_prompt_sections", return_value=("", "", False)), \
             patch.object(analyzer, "_format_prompt", return_value="prompt"), \
             patch.object(analyzer, "_call_litellm", side_effect=RuntimeError("upstream saw saved-secret-token")):
            result = analyzer.analyze(context)

        assert result.success is False
        assert "saved-secret-token" not in result.error_message
        assert "saved-secret-token" not in result.analysis_summary
        assert "saved-secret-token" not in result.risk_warning
        assert "saved-secret-token" not in caplog.text
        assert "[REDACTED]" in result.error_message

    def test_generation_diagnostic_redacts_legacy_provider_api_key(self):
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/test-model",
            litellm_fallback_models=[],
            llm_model_list=[],
            gemini_api_keys=[],
            anthropic_api_keys=[],
            openai_api_keys=["saved-legacy-secret-token"],
            deepseek_api_keys=[],
        )

        diagnostic = analyzer.sanitize_generation_diagnostic(
            RuntimeError("upstream saw saved-legacy-secret-token")
        )

        assert "saved-legacy-secret-token" not in diagnostic
        assert "[REDACTED]" in diagnostic

    def test_generation_diagnostic_fails_closed_when_secret_lookup_raises(self):
        analyzer = self._make_analyzer()
        opaque_secret = "opaque configured value 4zQ9"

        with patch.object(
            analyzer,
            "_litellm_redaction_values_for_model",
            side_effect=RuntimeError("redaction lookup unavailable"),
        ):
            diagnostic = analyzer.sanitize_generation_diagnostic(
                RuntimeError(f"upstream echoed {opaque_secret}")
            )

        assert opaque_secret not in diagnostic
        assert "[REDACTED]" in diagnostic

    def test_generate_text_log_fails_closed_when_secret_lookup_raises(self, caplog):
        analyzer = self._make_analyzer()
        opaque_secret = "opaque configured value 7mR2"

        caplog.set_level("ERROR", logger="src.analyzer")
        with patch.object(
            analyzer,
            "_call_litellm",
            side_effect=RuntimeError(f"upstream echoed {opaque_secret}"),
        ), patch.object(
            analyzer,
            "_get_runtime_config",
            side_effect=RuntimeError("redaction config unavailable"),
        ):
            result = analyzer.generate_text("prompt")

        assert result is None
        assert opaque_secret not in caplog.text
        assert "[REDACTED]" in caplog.text

    def test_generation_config_error_rejects_mixed_hermes_route(self):
        from src.llm.generation_backend import GenerationErrorCode

        analyzer = self._make_analyzer()
        analyzer._router = None
        analyzer._litellm_available = False
        analyzer._config_override = SimpleNamespace(
            litellm_model="shared-route",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "shared-route",
                    "litellm_params": {
                        "model": "hermes-agent",
                        "api_key": "sk-hermes-test-value",
                        "api_base": "http://127.0.0.1:8642/v1",
                    },
                    "model_info": {"dsa_channel": "hermes"},
                },
                {
                    "model_name": "shared-route",
                    "litellm_params": {
                        "model": "openai/gpt-4o-mini",
                        "api_key": "sk-openai-test-value",
                    },
                },
            ],
            generation_backend="litellm",
            generation_fallback_backend="",
            llm_channel_config_issues=[],
            llm_blocks_legacy_fallback=False,
        )

        error = analyzer.get_generation_backend_config_error()

        assert error is not None
        assert error.error_code is GenerationErrorCode.UNSAFE_CONFIG
        assert error.details["code"] == "mixed_hermes_route_unsupported"

    def test_generation_config_error_rejects_bare_mixed_hermes_route(self):
        from src.llm.generation_backend import GenerationErrorCode

        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="shared-route",
            litellm_fallback_models=[],
            llm_model_list=[
                {
                    "model_name": "openai/shared-route",
                    "litellm_params": {
                        "model": "openai/hermes-agent",
                        "api_key": "sk-hermes-test-value",
                        "api_base": "http://127.0.0.1:8642/v1",
                    },
                    "model_info": {"dsa_channel": "hermes"},
                },
                {
                    "model_name": "openai/shared-route",
                    "litellm_params": {
                        "model": "openai/gpt-4o-mini",
                        "api_key": "sk-openai-test-value",
                    },
                },
            ],
            generation_backend="litellm",
            generation_fallback_backend="",
            llm_channel_config_issues=[],
            llm_blocks_legacy_fallback=False,
        )

        error = analyzer.get_generation_backend_config_error()

        assert error is not None
        assert error.error_code is GenerationErrorCode.UNSAFE_CONFIG
        assert error.details["code"] == "mixed_hermes_route_unsupported"

    def test_generation_config_error_rejects_mixed_hermes_fallback_route(self):
        from src.llm.generation_backend import GenerationErrorCode

        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=["shared-route"],
            llm_model_list=[
                {
                    "model_name": "shared-route",
                    "litellm_params": {
                        "model": "openai/hermes-agent",
                        "api_key": "sk-hermes-test-value",
                        "api_base": "http://127.0.0.1:8642/v1",
                    },
                    "model_info": {"dsa_channel": "hermes"},
                },
                {
                    "model_name": "shared-route",
                    "litellm_params": {
                        "model": "openai/gpt-4o-mini",
                        "api_key": "sk-openai-test-value",
                    },
                },
            ],
            generation_backend="litellm",
            generation_fallback_backend="",
            llm_channel_config_issues=[],
            llm_blocks_legacy_fallback=False,
        )

        error = analyzer.get_generation_backend_config_error()

        assert error is not None
        assert error.error_code is GenerationErrorCode.UNSAFE_CONFIG
        assert error.details["code"] == "mixed_hermes_route_unsupported"
        assert error.details["route_name"] == "shared-route"

    def test_generation_config_error_rejects_bare_mixed_hermes_fallback_route(self):
        from src.llm.generation_backend import GenerationErrorCode

        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=["shared-route"],
            llm_model_list=[
                {
                    "model_name": "openai/shared-route",
                    "litellm_params": {
                        "model": "openai/hermes-agent",
                        "api_key": "sk-hermes-test-value",
                        "api_base": "http://127.0.0.1:8642/v1",
                    },
                    "model_info": {"dsa_channel": "hermes"},
                },
                {
                    "model_name": "openai/shared-route",
                    "litellm_params": {
                        "model": "openai/gpt-4o-mini",
                        "api_key": "sk-openai-test-value",
                    },
                },
            ],
            generation_backend="litellm",
            generation_fallback_backend="",
            llm_channel_config_issues=[],
            llm_blocks_legacy_fallback=False,
        )

        error = analyzer.get_generation_backend_config_error()

        assert error is not None
        assert error.error_code is GenerationErrorCode.UNSAFE_CONFIG
        assert error.details["code"] == "mixed_hermes_route_unsupported"

    def test_invalid_hermes_with_valid_sibling_keeps_analyzer_available(self):
        from src.config import Config
        from src.analyzer import GeminiAnalyzer

        env = {
            "LLM_CHANNELS": "hermes,primary",
            "LLM_PRIMARY_PROTOCOL": "openai",
            "LLM_PRIMARY_BASE_URL": "https://example.invalid/v1",
            "LLM_PRIMARY_API_KEY": "sk-primary-test-value",
            "LLM_PRIMARY_MODELS": "gpt-sibling",
            "OPENAI_API_KEY": "sk-openai-test-value",
        }

        with patch("src.config.setup_env"), \
             patch.object(Config, "_parse_litellm_yaml", return_value=[]), \
             patch.dict("os.environ", env, clear=True):
            config = Config._load_from_env()
            analyzer = GeminiAnalyzer(config=config)

        assert config.litellm_model == "openai/gpt-sibling"
        assert "hermes-agent" in config.llm_blocked_hermes_routes
        assert "openai/hermes-agent" in config.llm_blocked_hermes_routes
        assert analyzer.is_available() is True
        assert analyzer.get_generation_backend_config_error() is None

    def test_explicit_invalid_hermes_primary_with_valid_sibling_is_blocked_before_completion(self):
        from src.config import Config
        from src.analyzer import GeminiAnalyzer
        from src.llm.generation_backend import GenerationError, GenerationErrorCode

        env = {
            "LLM_CHANNELS": "hermes,primary",
            "LLM_HERMES_API_KEY": "hermes-key",
            "LLM_HERMES_MODELS": "bad model",
            "LLM_PRIMARY_PROTOCOL": "openai",
            "LLM_PRIMARY_BASE_URL": "https://example.invalid/v1",
            "LLM_PRIMARY_API_KEY": "sibling-key",
            "LLM_PRIMARY_MODELS": "gpt-sibling",
            "OPENAI_API_KEY": "legacy-key",
            "LITELLM_MODEL": "bad model",
        }

        with patch("src.config.setup_env"), \
             patch.object(Config, "_parse_litellm_yaml", return_value=[]), \
             patch.dict("os.environ", env, clear=True):
            config = Config._load_from_env()
            analyzer = GeminiAnalyzer(config=config)

        assert "bad model" in config.llm_blocked_hermes_routes
        assert "openai/bad model" in config.llm_blocked_hermes_routes
        error = analyzer.get_generation_backend_config_error()
        assert error is not None
        assert error.error_code is GenerationErrorCode.UNSAFE_CONFIG
        assert error.details["code"] == "explicit_hermes_route_invalid"
        assert error.details["reason"] == "explicit_hermes_route_invalid"
        assert error.details["field"] == "LITELLM_MODEL"
        assert analyzer.is_available() is False

        with patch("src.analyzer.litellm.completion") as completion:
            with pytest.raises(GenerationError):
                analyzer._call_litellm("prompt", {"max_tokens": 4})
        completion.assert_not_called()

    def test_explicit_invalid_hermes_fallback_with_valid_sibling_is_blocked_before_loop(self):
        from src.config import Config
        from src.analyzer import GeminiAnalyzer
        from src.llm.generation_backend import GenerationError, GenerationErrorCode

        env = {
            "LLM_CHANNELS": "hermes,primary",
            "LLM_HERMES_API_KEY": "hermes-key",
            "LLM_HERMES_MODELS": "bad model",
            "LLM_PRIMARY_PROTOCOL": "openai",
            "LLM_PRIMARY_BASE_URL": "https://example.invalid/v1",
            "LLM_PRIMARY_API_KEY": "sibling-key",
            "LLM_PRIMARY_MODELS": "gpt-sibling",
            "OPENAI_API_KEY": "legacy-key",
            "LITELLM_MODEL": "openai/gpt-sibling",
            "LITELLM_FALLBACK_MODELS": "bad model",
        }

        with patch("src.config.setup_env"), \
             patch.object(Config, "_parse_litellm_yaml", return_value=[]), \
             patch.dict("os.environ", env, clear=True):
            config = Config._load_from_env()
            analyzer = GeminiAnalyzer(config=config)

        error = analyzer.get_generation_backend_config_error()
        assert error is not None
        assert error.error_code is GenerationErrorCode.UNSAFE_CONFIG
        assert error.details["code"] == "explicit_hermes_route_invalid"
        assert error.details["field"] == "LITELLM_FALLBACK_MODELS"
        assert analyzer.is_available() is False

        with patch("src.analyzer.litellm.completion") as completion:
            with pytest.raises(GenerationError):
                analyzer._call_litellm("prompt", {"max_tokens": 4})
        completion.assert_not_called()

    @pytest.mark.parametrize("selected_model", ["anthropic/foo bad", "openai/anthropic/foo bad"])
    def test_provider_looking_malformed_hermes_model_is_not_reinterpreted_as_direct_provider(self, selected_model):
        from src.config import Config
        from src.analyzer import GeminiAnalyzer
        from src.llm.generation_backend import GenerationError

        env = {
            "LLM_CHANNELS": "hermes,primary",
            "LLM_HERMES_API_KEY": "hermes-key",
            "LLM_HERMES_MODELS": "anthropic/foo bad",
            "LLM_PRIMARY_PROTOCOL": "openai",
            "LLM_PRIMARY_BASE_URL": "https://example.invalid/v1",
            "LLM_PRIMARY_API_KEY": "sibling-key",
            "LLM_PRIMARY_MODELS": "gpt-sibling",
            "ANTHROPIC_API_KEY": "anthropic-legacy-key",
            "LITELLM_MODEL": selected_model,
        }

        with patch("src.config.setup_env"), \
             patch.object(Config, "_parse_litellm_yaml", return_value=[]), \
             patch.dict("os.environ", env, clear=True):
            config = Config._load_from_env()
            analyzer = GeminiAnalyzer(config=config)

        error = analyzer.get_generation_backend_config_error()
        assert error is not None
        assert error.details["code"] == "explicit_hermes_route_invalid"
        assert error.details["field"] == "LITELLM_MODEL"

        with patch("src.analyzer.litellm.completion") as completion:
            with pytest.raises(GenerationError):
                analyzer._call_litellm("prompt", {"max_tokens": 4})
        completion.assert_not_called()

    def test_invalid_hermes_config_error_handles_canonicalize_value_error(self):
        from src.llm.generation_backend import GenerationErrorCode

        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="bad hermes route",
            litellm_fallback_models=[],
            llm_model_list=[],
            generation_backend="litellm",
            generation_fallback_backend="",
            llm_channel_config_issues=[
                {
                    "field": "LLM_HERMES_MODELS",
                    "code": "invalid_model",
                    "message": "Hermes model IDs must be valid",
                }
            ],
            llm_blocks_legacy_fallback=True,
            llm_blocked_hermes_routes=["openai/hermes-agent"],
        )

        with patch("src.analyzer.canonicalize_hermes_model_ref", side_effect=ValueError("bad model")), \
             patch("src.analyzer.litellm.completion") as completion:
            error = analyzer.get_generation_backend_config_error()

        assert error is not None
        assert error.error_code is GenerationErrorCode.UNSAFE_CONFIG
        assert error.details["code"] == "invalid_model"
        completion.assert_not_called()

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

    def test_parse_response_non_json_returns_failure(self):
        """_parse_response must return success=False when LLM output is not valid JSON."""
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(report_language="zh")

        from src.analyzer import GeminiAnalyzer

        result = GeminiAnalyzer._parse_response(analyzer, "这是一段纯文本分析，没有 JSON。", "600519", "贵州茅台")
        assert result.success is False
        assert result.error_message is not None
        assert result.code == "600519"

    def test_parse_response_malformed_json_returns_failure(self):
        """_parse_response must return success=False when JSON extraction fails."""
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(report_language="zh")

        from src.analyzer import GeminiAnalyzer

        malformed = "Here is the analysis: {broken json content without closing"
        result = GeminiAnalyzer._parse_response(analyzer, malformed, "AAPL", "Apple")
        assert result.success is False
        assert result.error_message is not None

    def test_parse_response_valid_json_returns_success(self):
        """_parse_response must return success=True when LLM output contains valid JSON."""
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(report_language="zh")

        from src.analyzer import GeminiAnalyzer
        import json

        valid_response = json.dumps({
            "sentiment_score": 75,
            "trend_prediction": "看多",
            "operation_advice": "持有",
            "analysis_summary": "测试分析",
        })
        result = GeminiAnalyzer._parse_response(analyzer, valid_response, "600519", "贵州茅台")
        assert result.success is True
        assert result.error_message is None

    def test_json_parse_failure_triggers_fallback_model(self):
        """When the primary model returns non-JSON, _call_litellm must try the fallback model."""
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="provider/primary-model",
            litellm_fallback_models=["provider/fallback-model"],
            llm_model_list=[],
        )

        import json as _json
        valid_json = _json.dumps({"sentiment_score": 70, "trend_prediction": "看多"})
        dispatch_calls = []

        def fake_dispatch(model, call_kwargs, **kwargs):
            dispatch_calls.append(model)
            if "primary" in model:
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="这不是 JSON 格式的响应"))],
                    usage=None,
                )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=valid_json))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            )

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch):
            text, model_used, usage = analyzer._call_litellm(
                "test prompt",
                {"max_tokens": 128, "temperature": 0.7},
                response_validator=analyzer._validate_json_response,
            )

        assert "primary" in dispatch_calls[0], "primary model should be tried first"
        assert len(dispatch_calls) == 2, "fallback model should be tried after primary JSON failure"
        assert "fallback" in model_used
        assert valid_json == text

    def test_all_models_invalid_json_raises_all_models_failed_error(self):
        """When all models return non-JSON, _AllModelsFailedError is raised with last_response_text."""
        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            litellm_model="provider/primary-model",
            litellm_fallback_models=["provider/fallback-model"],
            llm_model_list=[],
        )

        from src.analyzer import _AllModelsFailedError

        def fake_dispatch(model, call_kwargs, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="这不是 JSON 格式的响应"))],
                usage=None,
            )

        with patch.object(analyzer, "_dispatch_litellm_completion", side_effect=fake_dispatch):
            with pytest.raises(_AllModelsFailedError) as exc_info:
                analyzer._call_litellm(
                    "test prompt",
                    {"max_tokens": 128, "temperature": 0.7},
                    response_validator=analyzer._validate_json_response,
                )

        assert exc_info.value.last_response_text == "这不是 JSON 格式的响应"

    def test_analyze_all_models_invalid_json_goes_through_post_processing(self):
        """When all models return non-JSON, analyze() must still run integrity
        checks, placeholder fill, and persist_llm_usage — no early return.

        With report_integrity_retry=1, the retry loop runs once (re-prompting
        with complement instructions); when that also yields invalid JSON the
        exhausted-retries path fires placeholder fill.
        """
        from src.analyzer import AnalysisResult, _AllModelsFailedError

        analyzer = self._make_analyzer()
        analyzer._config_override = SimpleNamespace(
            gemini_request_delay=0,
            report_language="zh",
            litellm_model="provider/primary-model",
            litellm_fallback_models=["provider/fallback-model"],
            llm_temperature=0.7,
            llm_model_list=[],
            report_integrity_enabled=True,
            report_integrity_retry=1,
        )

        # _parse_response on non-JSON text produces a text fallback result
        text_fallback_result = AnalysisResult(
            code="600519",
            name="贵州茅台",
            sentiment_score=50,
            trend_prediction="震荡",
            operation_advice="持有",
            analysis_summary="部分文本摘要",
            success=False,
            error_message="LLM response is not valid JSON; analysis result will not be persisted",
        )

        all_models_error = _AllModelsFailedError(
            "all failed",
            last_response_text="这不是 JSON，而是纯文本分析结果",
            last_model="provider/fallback-model",
            last_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )

        with patch.object(analyzer, "is_available", return_value=True), \
             patch.object(analyzer, "_get_analysis_system_prompt", return_value="system"), \
             patch.object(analyzer, "_format_prompt", return_value="prompt"), \
             patch.object(
                 analyzer,
                 "_call_litellm",
                 side_effect=all_models_error,
             ) as mock_call, \
             patch.object(analyzer, "_parse_response", return_value=text_fallback_result) as mock_parse, \
             patch.object(analyzer, "_build_market_snapshot", return_value={}), \
             patch.object(analyzer, "_check_content_integrity", return_value=(False, ["dashboard.core_conclusion.one_sentence"])), \
             patch.object(analyzer, "_build_integrity_retry_prompt", return_value="retry prompt"), \
             patch.object(analyzer, "_apply_placeholder_fill") as mock_fill, \
             patch("src.analyzer.persist_llm_usage") as mock_usage:

            result = analyzer.analyze(
                {"code": "600519", "stock_name": "贵州茅台"},
                news_context="some news",
            )

        # _call_litellm called twice: initial + 1 retry
        assert mock_call.call_count == 2

        # _parse_response called twice (initial + retry)
        assert mock_parse.call_count == 2
        mock_parse.assert_called_with("这不是 JSON，而是纯文本分析结果", "600519", "贵州茅台")

        # Placeholder fill was applied after retry exhaustion
        mock_fill.assert_called_once()
        assert "dashboard.core_conclusion.one_sentence" in mock_fill.call_args[0][1]

        # persist_llm_usage was called with the last model and usage
        mock_usage.assert_called_once()
        usage_args = mock_usage.call_args
        assert usage_args[0][0] == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        assert usage_args[0][1] == "provider/fallback-model"
        assert usage_args[1]["call_type"] == "analysis"
        assert usage_args[1]["stock_code"] == "600519"

        # Result is success=False (text fallback), but all fields exist
        assert result.success is False
        assert result.code == "600519"
        assert result.search_performed is True
