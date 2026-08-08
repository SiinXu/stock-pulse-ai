# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only LOCAL_ONLY_MODE and outbound-activity API contracts."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.security.outbound_policy import (
    LOCAL_ONLY_MODE_ENV,
    OutboundPolicyError,
    clear_outbound_activity_for_tests,
    validate_outbound_url,
)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "false")
    monkeypatch.delenv(LOCAL_ONLY_MODE_ENV, raising=False)
    clear_outbound_activity_for_tests()
    from api.app import create_app
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    clear_outbound_activity_for_tests()


def test_local_only_status_default_off(client: TestClient) -> None:
    response = client.get("/api/v1/security/local-only")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["env_key"] == "LOCAL_ONLY_MODE"
    assert body["blocked_error_reason"] == "local_only_mode_blocked"
    assert body["allowed_destination_classes"] == ["loopback"]


def test_outbound_activity_lists_redacted_decisions(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    clear_outbound_activity_for_tests()
    with pytest.raises(OutboundPolicyError):
        validate_outbound_url("https://cloud.example/v1", resolve_dns=False)
    response = client.get("/api/v1/security/outbound-activity", params={"limit": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["local_only_mode"] is True
    assert body["returned"] >= 1
    item = body["items"][0]
    assert item["decision"] == "blocked"
    assert item["reason"] == "local_only_mode_blocked"
    assert item["destination_class"] == "public_hostname"
    assert "cloud.example" not in response.text
