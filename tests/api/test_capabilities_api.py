# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API tests for GET /api/v1/capabilities."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.auth as auth
from api.app import create_app
from api.v1.endpoints import capabilities as capabilities_endpoint
from src.capability_registry import CapabilityRecord, CapabilitySnapshot, SourceStatus
from src.config import Config

NOW = datetime(2026, 8, 9, tzinfo=timezone.utc).isoformat()


def _router_app() -> FastAPI:
    app = FastAPI()
    app.include_router(capabilities_endpoint.router, prefix="/api/v1/capabilities")
    return app


def _sample_snapshot() -> CapabilitySnapshot:
    return CapabilitySnapshot(
        sources=(SourceStatus("tool", "ok", "9", NOW),),
        items=(
            CapabilityRecord(
                "tool:quote", "tool", "agent_tool", "agent.tool_registry",
                "quote", "9", "9", NOW, registered=True, executable=None,
                scopes=("market_data:read",), display_name="quote",
            ),
            CapabilityRecord(
                "extension.plugin:demo", "extension", "plugin_lifecycle",
                "plugin.manager", "demo", "1", "3", NOW, registered=True,
                executable=False, reason_code="lifecycle_not_capability",
                display_name="Demo",
            ),
        ),
    )


def test_list_capabilities_returns_typed_versioned_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(
        capabilities_endpoint, "collect_capability_records", lambda **_kwargs: _sample_snapshot()
    )
    response = TestClient(_router_app()).get("/api/v1/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "capability-inventory/v1"
    assert body["partial"] is False
    assert body["total"] == 2
    assert body["executable_count"] == 0
    assert body["non_executable_count"] == 1
    assert body["unknown_executable_count"] == 1
    assert body["items"][0]["scopes"] == ["market_data:read"]
    assert "details" not in body["items"][0]


def test_partial_source_status_is_exposed(monkeypatch) -> None:
    snapshot = CapabilitySnapshot(
        sources=(SourceStatus("tool", "error", "unknown", NOW, "tool_source_unavailable"),)
    )
    monkeypatch.setattr(
        capabilities_endpoint, "collect_capability_records", lambda **_kwargs: snapshot
    )
    body = TestClient(_router_app()).get("/api/v1/capabilities").json()

    assert body["partial"] is True
    assert body["sources"][0]["state"] == "error"
    assert body["sources"][0]["error_code"] == "tool_source_unavailable"


def test_domain_filter_and_invalid_error_contract(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _collect(**kwargs):
        captured.update(kwargs)
        return _sample_snapshot()

    monkeypatch.setattr(capabilities_endpoint, "collect_capability_records", _collect)
    client = TestClient(_router_app())
    response = client.get("/api/v1/capabilities", params=[("domain", "tool")])
    assert response.status_code == 200
    assert captured["domains"] == ["tool"]

    monkeypatch.setattr(
        capabilities_endpoint,
        "collect_capability_records",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("unsupported capability domains")),
    )
    invalid = client.get("/api/v1/capabilities", params=[("domain", "nope")])
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["error"] == "invalid_capability_domain"


def _reset_auth() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


def test_real_app_auth_rejects_missing_invalid_and_accepts_signed_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    env_path.write_text("ADMIN_AUTH_ENABLED=true\n", encoding="utf-8")
    monkeypatch.setenv("ENV_FILE", str(env_path))
    # Loading the temporary .env writes its keys into os.environ, so the whole
    # process environment is restored below. Otherwise ADMIN_AUTH_ENABLED stays
    # set and later suites resolve a different administrator identity.
    original_environ = dict(os.environ)
    Config.reset_instance()
    _reset_auth()
    monkeypatch.setattr(
        capabilities_endpoint, "collect_capability_records", lambda **_kwargs: _sample_snapshot()
    )

    try:
        client = TestClient(create_app(static_dir=static_dir))
        missing = client.get("/api/v1/capabilities")
        invalid = client.get(
            "/api/v1/capabilities", cookies={auth.COOKIE_NAME: "not-a-signed-session"}
        )
        session = auth.create_session()
        valid = client.get(
            "/api/v1/capabilities", cookies={auth.COOKIE_NAME: session}
        )

        assert missing.status_code == 401
        assert missing.json()["error"] == "unauthorized"
        assert invalid.status_code == 401
        assert invalid.json()["error"] == "unauthorized"
        assert valid.status_code == 200
        assert valid.json()["schema_version"] == "capability-inventory/v1"

        monkeypatch.setattr(
            capabilities_endpoint,
            "collect_capability_records",
            lambda **_kwargs: (_ for _ in ()).throw(ValueError("unsupported domain")),
        )
        invalid_domain = client.get(
            "/api/v1/capabilities?domain=nope",
            cookies={auth.COOKIE_NAME: session},
        )
        assert invalid_domain.status_code == 400
        assert invalid_domain.json()["error"] == "invalid_capability_domain"
        assert invalid_domain.json()["message"] == "unsupported domain"
        assert invalid_domain.json()["trace_id"]
    finally:
        os.environ.clear()
        os.environ.update(original_environ)
        Config.reset_instance()
        _reset_auth()
