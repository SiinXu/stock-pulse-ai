"""Deterministic tests for loopback-only local runtime detection."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from src.services.local_runtime_detect import (
    DEFAULT_OLLAMA_LOOPBACK_BASE_URL,
    LocalRuntimeDetectResult,
    detect_local_runtime,
    detect_local_runtime_from_config_map,
    parse_local_runtime_auto_detect_enabled,
)


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: Optional[Dict[str, Any]] = None) -> None:
        self.status_code = status_code
        body = json.dumps(payload or {}).encode("utf-8")
        self._chunks = [body]
        self.closed = False

    def iter_content(self, chunk_size: int = 4096):
        for chunk in self._chunks:
            yield chunk

    def close(self) -> None:
        self.closed = True


def test_parse_auto_detect_defaults_on_for_empty() -> None:
    assert parse_local_runtime_auto_detect_enabled(None) is True
    assert parse_local_runtime_auto_detect_enabled("") is True
    assert parse_local_runtime_auto_detect_enabled("true") is True
    assert parse_local_runtime_auto_detect_enabled("false") is False


def test_detect_disabled_skips_probe() -> None:
    calls: List[str] = []

    def requester(method: str, url: str, **kwargs: Any):
        calls.append(url)
        raise AssertionError("probe should not run when disabled")

    result = detect_local_runtime(enabled=False, requester=requester)
    assert result.available is False
    assert result.detect_enabled is False
    assert result.reason == "detect_disabled"
    assert calls == []


def test_detect_on_success_returns_suggested_profile() -> None:
    def requester(method: str, url: str, **kwargs: Any):
        assert method == "GET"
        assert url.endswith("/api/tags")
        assert "127.0.0.1" in url or "localhost" in url
        return _FakeResponse(
            200,
            {"models": [{"name": "qwen3:8b"}, {"name": "llama3.2:3b"}]},
        )

    result = detect_local_runtime(enabled=True, requester=requester)
    assert result.available is True
    assert result.backend == "ollama"
    assert result.models[0] == "qwen3:8b"
    assert result.suggested_profile["LLM_CHANNELS"] == "ollama"
    assert result.suggested_profile["LLM_OLLAMA_PROTOCOL"] == "ollama"
    assert result.suggested_profile["LITELLM_MODEL"] == "ollama/qwen3:8b"
    assert "API_KEY" not in json.dumps(result.suggested_profile)


def test_detect_skips_non_loopback_candidates() -> None:
    seen: List[str] = []

    def requester(method: str, url: str, **kwargs: Any):
        seen.append(url)
        return _FakeResponse(200, {"models": [{"name": "only-loopback"}]})

    result = detect_local_runtime(
        enabled=True,
        effective_map={"LLM_OLLAMA_BASE_URL": "http://192.168.1.50:11434"},
        requester=requester,
    )
    assert result.available is True
    assert all("192.168.1.50" not in url for url in seen)
    assert any("127.0.0.1" in url or "localhost" in url for url in seen)


def test_detect_probe_failure_is_log_only() -> None:
    def requester(method: str, url: str, **kwargs: Any):
        raise ConnectionError("refused")

    result = detect_local_runtime(enabled=True, requester=requester)
    assert result.available is False
    assert result.detect_enabled is True
    assert result.reason == "probe_failed"


def test_detect_from_config_map_respects_off_flag() -> None:
    def requester(method: str, url: str, **kwargs: Any):
        raise AssertionError("should not probe")

    result = detect_local_runtime_from_config_map(
        {"LOCAL_RUNTIME_AUTO_DETECT": "false"},
        requester=requester,
    )
    assert result.available is False
    assert result.reason == "detect_disabled"


def test_public_dict_shape() -> None:
    payload = LocalRuntimeDetectResult(
        available=True,
        backend="ollama",
        base_url=DEFAULT_OLLAMA_LOOPBACK_BASE_URL,
        models=["m"],
        suggested_profile={"LLM_CHANNELS": "ollama"},
        reason="ollama_reachable",
    ).to_public_dict()
    assert payload["available"] is True
    assert payload["backend"] == "ollama"
    assert payload["suggested_profile"]["LLM_CHANNELS"] == "ollama"
