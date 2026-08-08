"""Analyzer degradation messaging for zero-config first success."""

from __future__ import annotations

from unittest.mock import patch

from src.analyzer import GeminiAnalyzer
from src.config import Config


def test_unavailable_model_guides_to_dry_run_and_local_path() -> None:
    config = Config()
    config.report_language = "en"
    config.gemini_request_delay = 0
    config.generation_backend = "litellm"
    config.litellm_model = ""
    config.litellm_fallback_models = []
    config.llm_model_list = []

    analyzer = GeminiAnalyzer(config=config)
    with patch.object(analyzer, "get_generation_backend_config_error", return_value=None), \
         patch.object(analyzer, "is_available", return_value=False):
        result = analyzer.analyze({"code": "600519", "stock_name": "Kweichow Moutai"})

    assert result.success is False
    assert result.error_code == "llm_not_configured"
    assert "dry-run" in (result.analysis_summary or "")
    assert "Ollama" in (result.analysis_summary or "")
    assert "LLM API key is not configured" in (result.error_message or "")
