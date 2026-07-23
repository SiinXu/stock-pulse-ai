# -*- coding: utf-8 -*-
"""Analyzer response parsing and fallback contracts."""

from tests.market_analyzer_generate_text_support import (
    SimpleNamespace,
    _AnalyzerFactoryMixin,
    _llm_usage_hmac_env,
    json,
    patch,
    pytest,
)


class TestAnalyzerGenerateText(_AnalyzerFactoryMixin):
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
