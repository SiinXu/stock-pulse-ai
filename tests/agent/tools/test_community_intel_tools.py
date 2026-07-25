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
    def __init__(self, result: Any, *, configured: bool = True, error: BaseException | None = None) -> None:
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
            CommunityIntelCoverage(source_id="fixture_forum", status="available", as_of="2026-07-24T12:00:00Z"),
            CommunityIntelCoverage(source_id="fixture_market", status="available", as_of="2026-07-24T11:45:00Z"),
        ),
        "citations": (
            CommunityIntelCitation(
                source_id="fixture_forum",
                reference_id="thread-101",
                url="https://community.example.com/thread-101",
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
        stock_scope=StockScope(expected_stock_code=expected_stock_code, allowed_stock_codes={expected_stock_code}),
        backend="test",
        call_timeout_seconds=call_timeout_seconds,
        max_result_bytes=COMMUNITY_INTEL_MAX_RESULT_BYTES,
    )


def _execute(provider: Any, arguments: dict[str, Any] | None = None, **session_kwargs: Any):
    session = _session(provider, **session_kwargs)
    result = session.execute(COMMUNITY_INTEL_TOOL_NAME, arguments or {"stock_code": "AAPL"})
    return session, result


def test_happy_path_uses_real_bound_tool_session_and_materializes_defaults() -> None:
    provider = _Provider(_observation())
    session, result = _execute(provider)
    assert result["ok"] is True
    assert result["result"]["schema_version"] == COMMUNITY_INTEL_SCHEMA_VERSION
    assert result["result"]["status"] == "available"
    assert result["result"]["disclaimer"] == COMMUNITY_INTEL_DISCLAIMER
    assert provider.calls == [{"stock_code": "AAPL", "window_days": 7, "language_hint": "en"}]


def test_scope_deny_occurs_before_provider_dispatch() -> None:
    provider = _Provider(_observation(stock_code="MSFT"))
    session = _session(provider, expected_stock_code="AAPL")
    result = session.execute(COMMUNITY_INTEL_TOOL_NAME, {"stock_code": "MSFT", "window_days": 7, "language_hint": "en"})
    assert result["ok"] is False
    assert result["error"]["code"] == "stock_scope_violation"
    assert provider.calls == []


@pytest.mark.parametrize("stock_code", ["HK00700", "hk700", "00700.HK", "00700"])
def test_hk_aliases_stay_canonical_after_scope_authorization(stock_code: str) -> None:
    provider = _Provider(_observation(stock_code="HK00700"))
    session = _session(provider, expected_stock_code="HK00700")

    result = session.execute(
        COMMUNITY_INTEL_TOOL_NAME,
        {"stock_code": stock_code, "window_days": 7, "language_hint": "en"},
    )

    assert result["ok"] is True
    assert provider.calls == [
        {"stock_code": "HK00700", "window_days": 7, "language_hint": "en"}
    ]
    assert result["result"]["stock_code"] == "HK00700"


def test_tool_surface_timeout_is_typed_and_late_result_is_not_published() -> None:
    provider = _SlowProvider(_observation())
    session = _session(provider, call_timeout_seconds=0.01)
    try:
        result = session.execute(COMMUNITY_INTEL_TOOL_NAME, {"stock_code": "AAPL"})
        assert provider.started.wait(timeout=1.0)
        assert result["ok"] is False
        assert result["error"]["code"] == "timeout"
    finally:
        provider.release.set()
        assert provider.finished.wait(timeout=1.0)


def test_no_key_returns_explicit_unavailable_without_provider_call() -> None:
    provider = _Provider(_observation(), configured=False)
    _, result = _execute(provider)
    assert result["ok"] is True
    assert result["result"]["status"] == "unavailable"
    assert result["result"]["reason_code"] == "provider_not_configured"
    assert provider.calls == []


def test_absent_provider_uses_same_no_key_contract() -> None:
    _, result = _execute(None)
    assert result["result"]["reason_code"] == "provider_not_configured"


def test_empty_result_returns_explicit_unavailable() -> None:
    _, result = _execute(_Provider(None))
    assert result["result"]["reason_code"] == "no_data"


def test_provider_timeout_exception_returns_safe_degraded_result() -> None:
    _, result = _execute(_Provider(None, error=TimeoutError("upstream token=secret-value")))
    assert result["result"]["reason_code"] == "provider_timeout"
    assert "secret-value" not in result["result_text"]


def test_provider_error_is_safe_logged_and_does_not_leak_details(caplog) -> None:
    secret = "sk_live_abcdefghijklmnop"
    caplog.set_level(logging.WARNING, logger="src.agent.tools.community_intel_tools")
    _, result = _execute(_Provider(None, error=RuntimeError(f"provider failed api_key={secret}")))
    assert result["result"]["reason_code"] == "provider_error"
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in rendered


@pytest.mark.parametrize("invalid_result", [{"summary": "raw mapping bypass"}, ["posts"], "free-form"])
def test_invalid_provider_output_returns_typed_degradation(invalid_result: Any) -> None:
    _, result = _execute(_Provider(invalid_result))
    assert result["result"]["reason_code"] == "invalid_provider_output"


def test_constructed_observation_rejects_raw_nested_citation_mapping() -> None:
    observation = _observation().model_copy(
        update={
            "citations": (
                {
                    "source_id": "fixture_forum",
                    "reference_id": "raw-nested-reference",
                    "url": "https://community.example.com/raw-reference",
                },
            )
        }
    )

    _, result = _execute(_Provider(observation))

    assert result["ok"] is True
    assert result["result"]["reason_code"] == "invalid_provider_output"
    assert "raw-reference" not in result["result_text"]


def test_provider_cannot_change_stock_window_or_language_scope() -> None:
    _, result = _execute(_Provider(_observation(stock_code="MSFT")))
    assert result["result"]["reason_code"] == "invalid_provider_output"


def test_provider_model_rejects_extra_raw_post_payload() -> None:
    payload = _observation().model_dump(mode="python")
    payload["raw_posts"] = [{"body": "unbounded"}]
    with pytest.raises(ValidationError, match="raw_posts"):
        CommunityIntelObservation.model_validate(payload)


def test_result_redacts_secrets_from_text_and_citation_url() -> None:
    secret = "sk_live_abcdefghijklmnop"
    _, result = _execute(
        _Provider(
            _observation(
                summary=f"Neutral discussion api_key={secret}",
                confidence_basis=f"Credential {secret} was accidentally included.",
                themes=(f"token={secret}",),
                citations=(
                    CommunityIntelCitation(
                        source_id="fixture_forum",
                        reference_id=f"post-{secret}",
                        url=f"https://community.example.com/post?api_key={secret}",
                    ),
                ),
            )
        )
    )
    assert secret not in result["result_text"]
    assert result["result"]["citations"][0]["url"] is None
    assert result["result"]["reason_code"] == "partial_coverage"


@pytest.mark.parametrize(
    "citation_url",
    [
        "http://127.0.0.1:8000/admin?view=1",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://service.local/private",
        "http://[::1]/admin",
        "http://intranet/admin",
        "http://service.internal/private",
        "http://router.home.arpa/status",
        "https://fixture.invalid/reference",
        "https://fixture.test/reference",
        "https://fixture.example/reference",
        "https://hidden.onion/reference",
        "https://service.alt/reference",
        "https://service.corp/reference",
        "https://router.home/reference",
        "https://gateway.mail/reference",
        "https://resolver.arpa/reference",
        "https://ipv4only.arpa/reference",
        "https://1.10.in-addr.arpa/reference",
        "https://1.168.192.in-addr.arpa/reference",
        "https://d.f.ip6.arpa/reference",
    ],
)
def test_bound_session_rejects_non_public_citation_targets_even_if_allowlisted(
    monkeypatch: pytest.MonkeyPatch,
    citation_url: str,
) -> None:
    monkeypatch.setenv(
        "OUTBOUND_HTTP_ALLOWLIST",
        "127.0.0.1:8000,169.254.169.254,metadata.google.internal,service.local,::1,"
        "intranet,service.internal,router.home.arpa,fixture.invalid,fixture.test,"
        "fixture.example,hidden.onion,service.alt,service.corp,router.home,gateway.mail,"
        "resolver.arpa,ipv4only.arpa,1.10.in-addr.arpa,1.168.192.in-addr.arpa,d.f.ip6.arpa",
    )
    unsafe_citation = CommunityIntelCitation.model_construct(
        source_id="fixture_forum",
        reference_id="internal-reference",
        url=citation_url,
    )
    observation = _observation().model_copy(
        update={"citations": (unsafe_citation,)},
    )

    _, result = _execute(_Provider(observation))

    assert result["ok"] is True
    assert result["result"]["reason_code"] == "invalid_provider_output"
    assert citation_url not in result["result_text"]


def test_redacted_citation_reserves_a_deterministic_capped_gap_slot() -> None:
    provider_gaps = tuple(f"provider_gap_{index}" for index in range(8))
    secret = "sk_live_abcdefghijklmnop"

    _, result = _execute(
        _Provider(
            _observation(
                citations=(
                    CommunityIntelCitation(
                        source_id="fixture_forum",
                        reference_id="thread-101",
                        url=f"https://community.example.com/post?api_key={secret}",
                    ),
                ),
                gaps=provider_gaps,
            )
        )
    )

    assert result["ok"] is True
    assert result["result"]["citations"][0]["url"] is None
    assert result["result"]["gaps"] == [
        *provider_gaps[:7],
        "citation_url_redacted",
    ]


def test_argument_bounds_reject_before_provider_dispatch() -> None:
    provider = _Provider(_observation())
    session = _session(provider)
    result = session.execute(COMMUNITY_INTEL_TOOL_NAME, {"stock_code": "AAPL", "window_days": 31, "language_hint": "en"})
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_arguments"
    assert provider.calls == []


def test_tool_declares_strict_stock_scope_and_is_not_in_default_catalog() -> None:
    tool = build_community_intel_tool(_Provider(_observation()))
    assert tool.enforce_contract is True
    assert tool.policy.scope_dimensions == ["stock"]
    assert COMMUNITY_INTEL_TOOL_NAME not in {item.name for item in ALL_SEARCH_TOOLS}


def test_result_is_strict_json_without_raw_provider_objects() -> None:
    _, result = _execute(_Provider(_observation()))
    decoded = json.loads(result["result_text"])
    assert decoded == result["result"]


def test_maximum_valid_observation_exceeding_eight_kib_degrades() -> None:
    coverage = tuple(
        CommunityIntelCoverage(
            source_id=f"source_{index}",
            status="available",
            as_of="2026-07-24T12:00:00Z",
        )
        for index in range(4)
    )
    citations = tuple(
        CommunityIntelCitation(
            source_id=f"source_{index % 4}",
            reference_id=(f"reference {index} " + "market evidence " * 12)[:160],
            url=(
                f"https://source-{index}.example.com/"
                + "market/discussion/topic/" * 19
                + str(index)
            )[:500],
        )
        for index in range(6)
    )
    observation = _observation(
        summary=("Balanced market discussion with bounded evidence. " * 30)[:1200],
        confidence_basis=("Multiple bounded sources support this assessment. " * 6)[:240],
        themes=tuple(
            (f"theme {index} " + "market discussion " * 5)[:80]
            for index in range(8)
        ),
        coverage=coverage,
        citations=citations,
        gaps=tuple(
            (f"gap {index} " + "source coverage remains incomplete " * 4)[:120]
            for index in range(8)
        ),
    )

    _, result = _execute(_Provider(observation))

    assert result["ok"] is True
    assert result["result"]["reason_code"] == "output_too_large"
