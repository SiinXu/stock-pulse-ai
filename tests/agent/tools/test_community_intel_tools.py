"""Contract tests for the stock-scoped community-intelligence Phase A tool."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import pytest
from pydantic import ValidationError

from src.agent.runtime.tool_session import BoundToolSession
from src.agent.stock_scope import StockScope
from src.agent.tools.community_intel_tools import (
    COMMUNITY_INTEL_DISCLAIMER,
    COMMUNITY_INTEL_MAX_RESULT_BYTES,
    COMMUNITY_INTEL_SCHEMA_VERSION,
    COMMUNITY_INTEL_TOOL_NAME,
    CommunityIntelCitation,
    CommunityIntelCoverage,
    CommunityIntelObservation,
    build_community_intel_tool,
)
from src.agent.tools.registry import ToolRegistry
from src.agent.tools.search_tools import ALL_SEARCH_TOOLS


class _Provider:
    def __init__(
        self,
        result: Any,
        *,
        configured: bool = True,
        error: BaseException | None = None,
    ) -> None:
        self.is_configured = configured
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def get_brief(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class _SlowProvider:
    is_configured = True

    def __init__(self, result: CommunityIntelObservation) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()

    def get_brief(self, **kwargs: Any) -> CommunityIntelObservation:
        self.calls.append(kwargs)
        self.started.set()
        self.release.wait(timeout=2.0)
        self.finished.set()
        return self.result


def _observation(**overrides: Any) -> CommunityIntelObservation:
    payload: dict[str, Any] = {
        "stock_code": "AAPL",
        "language": "en",
        "as_of": "2026-07-24T12:00:00Z",
        "window_days": 7,
        "window_start": "2026-07-17T12:00:00Z",
        "window_end": "2026-07-24T12:00:00Z",
        "summary": "Discussion was balanced around product demand and valuation risk.",
        "tone": "mixed",
        "confidence": 0.72,
        "confidence_basis": "Two bounded fixture sources agreed on the leading themes.",
        "themes": ("product demand", "valuation risk"),
        "volume_signal": "normal",
        "coverage": (
            CommunityIntelCoverage(
                source_id="fixture_forum",
                status="available",
                as_of="2026-07-24T12:00:00Z",
            ),
            CommunityIntelCoverage(
                source_id="fixture_market",
                status="available",
                as_of="2026-07-24T11:45:00Z",
            ),
        ),
        "citations": (
            CommunityIntelCitation(
                source_id="fixture_forum",
                reference_id="thread-101",
                url="https://example.invalid/community/thread-101",
            ),
        ),
        "gaps": (),
    }
    payload.update(overrides)
    return CommunityIntelObservation(**payload)


def _session(
    provider: Any,
    *,
    expected_stock_code: str = "AAPL",
    call_timeout_seconds: float | None = None,
) -> BoundToolSession:
    registry = ToolRegistry()
    registry.register(build_community_intel_tool(provider))
    return BoundToolSession(
        registry,
        execution_id="community-intel-contract-test",
        allowed_tools=[COMMUNITY_INTEL_TOOL_NAME],
        granted_permissions=["community_intel:read"],
        stock_scope=StockScope(
            expected_stock_code=expected_stock_code,
            allowed_stock_codes={expected_stock_code},
        ),
        backend="test",
        call_timeout_seconds=call_timeout_seconds,
        max_result_bytes=COMMUNITY_INTEL_MAX_RESULT_BYTES,
    )


def _execute(
    provider: Any,
    arguments: dict[str, Any] | None = None,
    **session_kwargs: Any,
) -> tuple[BoundToolSession, dict[str, Any]]:
    session = _session(provider, **session_kwargs)
    result = session.execute(
        COMMUNITY_INTEL_TOOL_NAME,
        arguments or {"stock_code": "AAPL"},
    )
    return session, result


def test_happy_path_uses_real_bound_tool_session_and_materializes_defaults() -> None:
    provider = _Provider(_observation())

    session, result = _execute(provider)

    assert result["ok"] is True
    assert result["result"]["schema_version"] == COMMUNITY_INTEL_SCHEMA_VERSION
    assert result["result"]["status"] == "available"
    assert result["result"]["degraded"] is False
    assert result["result"]["stock_code"] == "AAPL"
    assert result["result"]["window"] == {
        "days": 7,
        "start": "2026-07-17T12:00:00Z",
        "end": "2026-07-24T12:00:00Z",
    }
    assert result["result"]["disclaimer"] == COMMUNITY_INTEL_DISCLAIMER
    assert provider.calls == [
        {"stock_code": "AAPL", "window_days": 7, "language_hint": "en"}
    ]
    assert len(session.audit_trail) == 1
    assert session.audit_trail[0]["tool_name"] == COMMUNITY_INTEL_TOOL_NAME


def test_scope_deny_occurs_before_provider_dispatch() -> None:
    provider = _Provider(_observation(stock_code="MSFT"))
    session = _session(provider, expected_stock_code="AAPL")

    result = session.execute(
        COMMUNITY_INTEL_TOOL_NAME,
        {"stock_code": "MSFT", "window_days": 7, "language_hint": "en"},
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "stock_scope_violation"
    assert result["error"]["retriable"] is False
    assert provider.calls == []
    assert len(session.audit_trail) == 1


def test_tool_surface_timeout_is_typed_and_late_result_is_not_published() -> None:
    provider = _SlowProvider(_observation())
    session = _session(provider, call_timeout_seconds=0.01)

    try:
        result = session.execute(COMMUNITY_INTEL_TOOL_NAME, {"stock_code": "AAPL"})
        assert provider.started.wait(timeout=1.0)
        assert result["ok"] is False
        assert result["error"]["code"] == "timeout"
        assert result["result"] is None
        assert result["diagnostics"]["redacted"] is True
    finally:
        provider.release.set()
        assert provider.finished.wait(timeout=1.0)


def test_no_key_returns_explicit_unavailable_without_provider_call() -> None:
    provider = _Provider(_observation(), configured=False)

    _, result = _execute(provider)

    assert result["ok"] is True
    assert result["result"]["status"] == "unavailable"
    assert result["result"]["reason_code"] == "provider_not_configured"
    assert result["result"]["confidence"] is None
    assert result["result"]["citations"] == []
    assert provider.calls == []


def test_absent_provider_uses_same_no_key_contract() -> None:
    _, result = _execute(None)

    assert result["ok"] is True
    assert result["result"]["status"] == "unavailable"
    assert result["result"]["reason_code"] == "provider_not_configured"


def test_empty_result_returns_explicit_unavailable() -> None:
    provider = _Provider(None)

    _, result = _execute(provider)

    assert result["ok"] is True
    assert result["result"]["status"] == "unavailable"
    assert result["result"]["reason_code"] == "no_data"
    assert result["result"]["gaps"] == ["no_data"]


def test_provider_timeout_exception_returns_safe_degraded_result() -> None:
    provider = _Provider(None, error=TimeoutError("upstream token=secret-value"))

    _, result = _execute(provider)

    assert result["ok"] is True
    assert result["result"]["status"] == "degraded"
    assert result["result"]["reason_code"] == "provider_timeout"
    assert "secret-value" not in result["result_text"]


def test_provider_error_is_safe_logged_and_does_not_leak_details(caplog) -> None:
    secret = "sk_live_abcdefghijklmnop"
    provider = _Provider(None, error=RuntimeError(f"provider failed api_key={secret}"))
    caplog.set_level(logging.WARNING, logger="src.agent.tools.community_intel_tools")

    _, result = _execute(provider)

    assert result["ok"] is True
    assert result["result"]["reason_code"] == "provider_error"
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in rendered
    assert secret not in result["result_text"]
    assert "community_intel_provider_failed" in rendered


@pytest.mark.parametrize(
    "invalid_result",
    [
        {"summary": "raw mapping bypass"},
        ["unbounded", "posts"],
        "free-form prompt text",
    ],
)
def test_invalid_provider_output_returns_typed_degradation(invalid_result: Any) -> None:
    provider = _Provider(invalid_result)

    _, result = _execute(provider)

    assert result["ok"] is True
    assert result["result"]["status"] == "degraded"
    assert result["result"]["reason_code"] == "invalid_provider_output"
    assert result["result"]["confidence"] is None


def test_provider_cannot_change_stock_window_or_language_scope() -> None:
    provider = _Provider(_observation(stock_code="MSFT"))

    _, result = _execute(provider)

    assert result["ok"] is True
    assert result["result"]["reason_code"] == "invalid_provider_output"


def test_provider_model_rejects_extra_raw_post_payload() -> None:
    payload = _observation().model_dump(mode="python")
    payload["raw_posts"] = [{"body": "unbounded"}]

    with pytest.raises(ValidationError, match="raw_posts"):
        CommunityIntelObservation.model_validate(payload)


def test_provider_model_rejects_evidence_outside_declared_window() -> None:
    with pytest.raises(ValidationError, match="evidence window exceeds"):
        _observation(window_start="2026-07-01T12:00:00Z")


def test_result_redacts_secrets_from_text_and_citation_url() -> None:
    secret = "sk_live_abcdefghijklmnop"
    provider = _Provider(
        _observation(
            summary=f"Neutral discussion api_key={secret}",
            confidence_basis=f"Credential {secret} was accidentally included.",
            themes=(f"token={secret}",),
            citations=(
                CommunityIntelCitation(
                    source_id="fixture_forum",
                    reference_id=f"post-{secret}",
                    url=f"https://example.invalid/post?api_key={secret}",
                ),
            ),
        )
    )

    _, result = _execute(provider)

    assert result["ok"] is True
    assert secret not in result["result_text"]
    assert "[REDACTED]" in result["result_text"]
    assert result["result"]["citations"] == [
        {
            "source_id": "fixture_forum",
            "reference_id": "post-[REDACTED]",
            "url": None,
        }
    ]
    assert result["result"]["gaps"] == ["citation_url_redacted"]
    assert result["result"]["status"] == "degraded"
    assert result["result"]["reason_code"] == "partial_coverage"


def test_oversized_but_schema_valid_observation_fails_closed_to_bounded_result() -> None:
    wide = "\u754c"
    citations = tuple(
        CommunityIntelCitation(
            source_id="fixture_forum",
            reference_id=(chr(97 + index) + wide * 159),
            url="https://example.invalid/" + (chr(97 + index) * 470),
        )
        for index in range(6)
    )
    provider = _Provider(
        _observation(
            summary=wide * 1200,
            confidence_basis=wide * 240,
            themes=tuple(chr(97 + index) + wide * 79 for index in range(8)),
            citations=citations,
            gaps=tuple(chr(97 + index) + wide * 119 for index in range(8)),
        )
    )

    _, result = _execute(provider)

    assert result["ok"] is True
    assert result["result"]["reason_code"] == "output_too_large"
    assert len(result["result_text"].encode("utf-8")) <= COMMUNITY_INTEL_MAX_RESULT_BYTES


def test_argument_bounds_reject_before_provider_dispatch() -> None:
    provider = _Provider(_observation())
    session = _session(provider)

    result = session.execute(
        COMMUNITY_INTEL_TOOL_NAME,
        {"stock_code": "AAPL", "window_days": 31, "language_hint": "en"},
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_arguments"
    assert provider.calls == []


def test_tool_declares_strict_stock_scope_and_is_not_in_default_catalog() -> None:
    tool = build_community_intel_tool(_Provider(_observation()))

    assert tool.enforce_contract is True
    assert tool.policy.policy_status == "declared"
    assert tool.policy.read_only is True
    assert tool.policy.scope_dimensions == ["stock"]
    assert tool.policy.permissions == ["community_intel:read"]
    assert COMMUNITY_INTEL_TOOL_NAME not in {item.name for item in ALL_SEARCH_TOOLS}


def test_result_is_strict_json_without_raw_provider_objects() -> None:
    _, result = _execute(_Provider(_observation()))

    decoded = json.loads(result["result_text"])
    assert decoded == result["result"]
    assert set(decoded) == {
        "schema_version",
        "status",
        "degraded",
        "reason_code",
        "stock_code",
        "language",
        "as_of",
        "window",
        "summary",
        "tone",
        "confidence",
        "confidence_basis",
        "themes",
        "volume_signal",
        "coverage",
        "citations",
        "gaps",
        "disclaimer",
    }
