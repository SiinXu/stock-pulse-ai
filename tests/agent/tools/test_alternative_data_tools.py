# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract tests for the corporate-events alternative-data ToolSurface tool."""

from __future__ import annotations

from typing import Any

from src.agent.runtime.tool_session import BoundToolSession
from src.agent.stock_scope import StockScope
from src.agent.tools.alternative_data_tools import (
    ALT_DATA_MAX_RESULT_BYTES,
    ALT_DATA_PERMISSION,
    CORPORATE_EVENTS_TOOL_NAME,
    build_corporate_events_tool,
)
from src.agent.tools.data_tools import ALL_DATA_TOOLS
from src.agent.tools.registry import SUPPORTED_AGENT_TOOL_CAPABILITIES, ToolRegistry
from src.schemas.alternative_data import (
    ALT_DATA_DISCLAIMER,
    AlternativeDataCitation,
    AlternativeDataCoverage,
    AlternativeDataObservation,
    CorporateEventItem,
)
from tests.security_audit_test_utils import SecurityAuditRecorderStub


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

    def get_events(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def _observation(**overrides: Any) -> AlternativeDataObservation:
    payload: dict[str, Any] = {
        "category": "corporate_events",
        "stock_code": "AAPL",
        "language": "en",
        "as_of": "2026-08-01T00:00:00Z",
        "summary": "One fixture corporate event in the window.",
        "confidence": 0.6,
        "confidence_basis": "Single fixture source.",
        "events": (
            CorporateEventItem(
                event_id="evt-1",
                event_type="earnings",
                title="Q2 earnings date",
                event_date="2026-08-20",
                impact_hint="unclear",
                source_id="fixture_src",
                confidence=0.6,
            ),
        ),
        "coverage": (
            AlternativeDataCoverage(
                source_id="fixture_src",
                status="available",
                as_of="2026-08-01T00:00:00Z",
            ),
        ),
        "citations": (
            AlternativeDataCitation(
                source_id="fixture_src",
                reference_id="evt-1",
                url=None,
            ),
        ),
        "gaps": (),
        "authority": "non_authoritative",
        "role": "supporting_only",
        "disclaimer": ALT_DATA_DISCLAIMER,
    }
    payload.update(overrides)
    return AlternativeDataObservation(**payload)


def _session(
    provider: Any,
    *,
    expected_stock_code: str = "AAPL",
    granted_permissions: list[str] | None = None,
) -> BoundToolSession:
    registry = ToolRegistry()
    registry.register(build_corporate_events_tool(provider))
    return BoundToolSession(
        registry,
        execution_id="alt-data-contract-test",
        allowed_tools=[CORPORATE_EVENTS_TOOL_NAME],
        granted_permissions=granted_permissions
        if granted_permissions is not None
        else [ALT_DATA_PERMISSION],
        stock_scope=StockScope(
            expected_stock_code=expected_stock_code,
            allowed_stock_codes={expected_stock_code},
        ),
        backend="test",
        max_result_bytes=ALT_DATA_MAX_RESULT_BYTES,
        security_audit=SecurityAuditRecorderStub(),
    )


def test_alt_data_permission_is_catalogued() -> None:
    assert ALT_DATA_PERMISSION in SUPPORTED_AGENT_TOOL_CAPABILITIES


def test_tool_not_in_default_data_catalog() -> None:
    names = {
        getattr(item, "__name__", None) or getattr(item, "name", None)
        for item in ALL_DATA_TOOLS
    }
    assert CORPORATE_EVENTS_TOOL_NAME not in names
    assert "build_corporate_events_tool" not in names


def test_happy_path_via_bound_tool_session() -> None:
    session = _session(_Provider(_observation()))
    result = session.execute(
        CORPORATE_EVENTS_TOOL_NAME,
        {"stock_code": "AAPL"},
    )
    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"] == "available"
    assert payload["authority"] == "non_authoritative"
    assert payload["role"] == "supporting_only"
    assert payload["disclaimer"] == ALT_DATA_DISCLAIMER
    assert len(payload["events"]) == 1
    assert payload["confidence"] == 0.6


def test_unauthorized_call_denied_by_toolsurface() -> None:
    session = _session(_Provider(_observation()), granted_permissions=[])
    result = session.execute(
        CORPORATE_EVENTS_TOOL_NAME,
        {"stock_code": "AAPL"},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "permission_denied"
    assert "alt_data:read" in result["error"]["details"]["missing_capabilities"]


def test_missing_provider_does_not_invent_events() -> None:
    session = _session(_Provider(None, configured=False))
    result = session.execute(
        CORPORATE_EVENTS_TOOL_NAME,
        {"stock_code": "AAPL"},
    )
    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "provider_not_configured"
    assert payload["events"] == []
    assert payload["confidence"] is None
    assert "provider_not_configured" in payload["gaps"]


def test_provider_error_becomes_typed_gap() -> None:
    session = _session(_Provider(None, error=RuntimeError("upstream boom")))
    result = session.execute(
        CORPORATE_EVENTS_TOOL_NAME,
        {"stock_code": "AAPL"},
    )
    assert result["ok"] is True
    payload = result["result"]
    assert payload["status"] == "degraded"
    assert payload["reason_code"] == "provider_error"
    assert payload["events"] == []
    assert payload["confidence"] is None


def test_invalid_observation_rejected() -> None:
    session = _session(_Provider({"not": "a valid observation"}))
    result = session.execute(
        CORPORATE_EVENTS_TOOL_NAME,
        {"stock_code": "AAPL"},
    )
    assert result["ok"] is True
    payload = result["result"]
    assert payload["reason_code"] == "invalid_provider_output"
    assert payload["events"] == []
    assert payload["confidence"] is None


def test_stock_scope_mismatch_rejected() -> None:
    session = _session(_Provider(_observation()), expected_stock_code="AAPL")
    result = session.execute(
        CORPORATE_EVENTS_TOOL_NAME,
        {"stock_code": "MSFT"},
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "stock_scope_violation"
