# -*- coding: utf-8 -*-
"""Analyzer completion extraction: typed reasoning blocks and MiniMax <think> wrappers."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest


class TestAnalyzerMiniMaxResponse:
    def _make_analyzer(self):
        with patch("src.analyzer.get_config") as mock_cfg:
            cfg = SimpleNamespace(
                litellm_model="openai/MiniMax-M3",
                litellm_fallback_models=[],
                llm_model_list=[],
                generation_backend="litellm",
                generation_fallback_backend="litellm",
            )
            mock_cfg.return_value = cfg
            from src.analyzer import GeminiAnalyzer

            analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
            analyzer._router = None
            analyzer._litellm_available = True
            analyzer._config_override = cfg
            return analyzer

    def test_extract_completion_text_strips_leading_think_wrapper(self):
        analyzer = self._make_analyzer()
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    content_blocks=None,
                    message=SimpleNamespace(
                        content='<think>Internal reasoning</think>\n{"sentiment_score": 72}'
                    ),
                )
            ]
        )
        assert analyzer._extract_completion_text(response) == '{"sentiment_score": 72}'

    def test_extract_completion_text_filters_typed_reasoning_blocks(self):
        analyzer = self._make_analyzer()
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    content_blocks=[
                        SimpleNamespace(type="thinking", text="internal reasoning"),
                        SimpleNamespace(type="text", text='{"sentiment_score": 72}'),
                    ],
                    message=None,
                )
            ]
        )
        assert analyzer._extract_completion_text(response) == '{"sentiment_score": 72}'

    def test_extract_completion_text_preserves_literal_think_inside_json(self):
        analyzer = self._make_analyzer()
        payload = '{"analysis_summary":"literal <think>text</think>"}'
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    content_blocks=None,
                    message=SimpleNamespace(content=payload),
                )
            ]
        )
        assert analyzer._extract_completion_text(response) == payload

    def test_call_litellm_stream_strips_split_think_wrapper(self):
        analyzer = self._make_analyzer()

        def stream_response():
            for content in (
                "<thi",
                "nk>Internal reasoning</think>",
                '{"sentiment_score": ',
                "72}",
            ):
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=content))],
                    usage=None,
                )

        with patch.object(
            analyzer, "_dispatch_litellm_completion", return_value=stream_response()
        ):
            text, model, _usage = analyzer._call_litellm(
                "prompt",
                {"max_tokens": 128, "temperature": 0.2},
                stream=True,
            )

        assert text == '{"sentiment_score": 72}'
        assert model == "openai/MiniMax-M3"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
