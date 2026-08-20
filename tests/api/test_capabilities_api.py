# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API tests for GET /api/v1/capabilities."""

from __future__ import annotations

import asyncio
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

import src.auth as auth
from src.api.app import create_app
from src.api.middlewares.auth import EXEMPT_PATHS, _bounded_request_body
from src.api.v1.endpoints import capabilities as capabilities_endpoint
from src.capability_registry import CapabilityRecord, CapabilitySnapshot, SourceStatus
from src.capability_registry.write_service import get_capability_write_service
from src.config import Config
from src.repositories.security_audit_repo import SecurityAuditRepository
from src.services.security_audit_service import get_security_audit_service
from src.storage import DatabaseManager

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
        with TestClient(create_app(static_dir=static_dir)) as client:
            missing = client.get("/api/v1/capabilities")
            invalid = client.get(
                "/api/v1/capabilities",
                cookies={auth.COOKIE_NAME: "not-a-signed-session"},
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


_WRITE_PAYLOAD = {
    "capability_id": "llm:deepseek-pro",
    "domain": "llm",
    "capability_type": "llm_model",
    "version": "1",
    "provider": "deepseek",
    "display_name": "DeepSeek Pro",
    "model_route": "deepseek/deepseek-v4-pro",
}

_DENIED_SECRET = "sk_live_must_not_persist_in_audit"


@contextmanager
def _real_app(tmp_path: Path, *, auth_enabled: bool):
    env_path = tmp_path / ".env"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    db_path = tmp_path / "stock_analysis.db"
    registry_path = tmp_path / "capability_write_registry.json"
    flag = "true" if auth_enabled else "false"
    env_path.write_text(
        f"ADMIN_AUTH_ENABLED={flag}\n"
        f"DATABASE_PATH={db_path}\n"
        f"CAPABILITY_WRITE_REGISTRY_PATH={registry_path}\n",
        encoding="utf-8",
    )
    original_environ = dict(os.environ)
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
    os.environ["CAPABILITY_WRITE_REGISTRY_PATH"] = str(registry_path)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    get_capability_write_service(reset=True)
    _reset_auth()
    try:
        with TestClient(create_app(static_dir=static_dir)) as client:
            yield client, registry_path
    finally:
        os.environ.clear()
        os.environ.update(original_environ)
        Config.reset_instance()
        get_capability_write_service(reset=True)
        _reset_auth()


def _capability_write_events():
    return get_security_audit_service().list_events(
        event_type="capability.write",
        page_size=100,
    ).items


def _denied_write_events():
    return [
        event
        for event in _capability_write_events()
        if event.phase == "completion" and event.outcome == "denied"
    ]


def test_capability_write_routes_are_not_auth_exempt() -> None:
    assert all("capabilities" not in path for path in EXEMPT_PATHS)


def test_unauthenticated_register_is_401_and_persists_denied_audit(tmp_path: Path) -> None:
    with _real_app(tmp_path, auth_enabled=True) as (client, registry_path):
        response = client.post("/api/v1/capabilities/registry", json=_WRITE_PAYLOAD)

        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"
        denied = _denied_write_events()
        assert len(denied) == 1
        event = denied[0]
        assert event.event_type == "capability.write"
        assert event.actor.type == "unauthenticated"
        assert event.actor.id == "unauthenticated"
        assert event.target.type == "capability"
        assert event.target.id == "llm:deepseek-pro"
        assert event.reason_code == "unauthorized"
        assert event.action == "capability.register"
        assert not registry_path.exists()


def test_unauthenticated_update_and_retire_audit_target_from_path(tmp_path: Path) -> None:
    with _real_app(tmp_path, auth_enabled=True) as (client, _registry_path):
        updated = client.put(
            "/api/v1/capabilities/registry/llm:deepseek-pro",
            json={"display_name": "ignored"},
        )
        retired = client.post("/api/v1/capabilities/registry/llm:deepseek-pro/retire")

        assert updated.status_code == 401
        assert updated.json()["error"] == "unauthorized"
        assert retired.status_code == 401
        assert retired.json()["error"] == "unauthorized"
        denied = _denied_write_events()
        assert {event.action for event in denied} == {
            "capability.update",
            "capability.retire",
        }
        assert all(event.target.id == "llm:deepseek-pro" for event in denied)
        assert all(event.reason_code == "unauthorized" for event in denied)


def test_invalid_cookie_is_denied_and_never_writes(tmp_path: Path) -> None:
    with _real_app(tmp_path, auth_enabled=True) as (client, registry_path):
        response = client.post(
            "/api/v1/capabilities/registry",
            json=_WRITE_PAYLOAD,
            cookies={auth.COOKIE_NAME: "not-a-signed-session"},
        )

        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"
        assert _denied_write_events()
        assert not registry_path.exists()


def test_unauthenticated_register_does_not_reach_write_endpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with _real_app(tmp_path, auth_enabled=True) as (client, _registry_path):
        monkeypatch.setattr(
            capabilities_endpoint,
            "get_capability_write_service",
            lambda: (_ for _ in ()).throw(AssertionError("write endpoint reached")),
        )
        response = client.post("/api/v1/capabilities/registry", json=_WRITE_PAYLOAD)
        assert response.status_code == 401
        assert response.json()["error"] == "unauthorized"
        assert _denied_write_events()


def test_get_and_unrelated_401_do_not_audit_capability_write(tmp_path: Path) -> None:
    with _real_app(tmp_path, auth_enabled=True) as (client, _registry_path):
        inventory = client.get("/api/v1/capabilities")
        registry = client.get("/api/v1/capabilities/registry")
        resolve = client.post(
            "/api/v1/capabilities/resolve",
            json={"capability_ids": ["llm:deepseek-pro"]},
        )
        unrelated = client.get("/api/v1/history")

        assert inventory.status_code == 401
        assert registry.status_code == 401
        assert resolve.status_code == 401
        assert unrelated.status_code == 401
        assert _capability_write_events() == []


def test_auth_disabled_register_succeeds_without_denied_audit(tmp_path: Path) -> None:
    with _real_app(tmp_path, auth_enabled=False) as (client, _registry_path):
        response = client.post("/api/v1/capabilities/registry", json=_WRITE_PAYLOAD)

        assert response.status_code == 200, response.text
        assert response.json()["capability_id"] == "llm:deepseek-pro"
        events = _capability_write_events()
        assert any(
            event.phase == "completion" and event.outcome == "success"
            for event in events
        )
        assert all(event.outcome != "denied" for event in events)


def test_valid_session_register_keeps_attempt_success_audit(tmp_path: Path) -> None:
    with _real_app(tmp_path, auth_enabled=True) as (client, _registry_path):
        session = auth.create_session()
        response = client.post(
            "/api/v1/capabilities/registry",
            json=_WRITE_PAYLOAD,
            cookies={auth.COOKIE_NAME: session},
        )

        assert response.status_code == 200, response.text
        events = _capability_write_events()
        assert any(event.phase == "attempt" for event in events)
        assert any(
            event.phase == "completion" and event.outcome == "success"
            for event in events
        )
        assert all(event.outcome != "denied" for event in events)


def test_missing_register_target_falls_back_to_unknown_capability(tmp_path: Path) -> None:
    with _real_app(tmp_path, auth_enabled=True) as (client, _registry_path):
        response = client.post("/api/v1/capabilities/registry", json={})

        assert response.status_code == 401
        denied = _denied_write_events()
        assert len(denied) == 1
        assert denied[0].target.id == "unknown-capability"


def test_denied_write_audit_sink_failure_returns_503_without_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with _real_app(tmp_path, auth_enabled=True) as (client, registry_path):
        def _fail_append(self, event):
            raise RuntimeError("audit sink down")

        monkeypatch.setattr(SecurityAuditRepository, "append", _fail_append)
        try:
            response = client.post("/api/v1/capabilities/registry", json=_WRITE_PAYLOAD)
        finally:
            monkeypatch.undo()

        assert response.status_code == 503
        assert response.json()["error"] == "security_audit_unavailable"
        assert not registry_path.exists()


def test_denied_write_audit_does_not_copy_secrets_from_body(tmp_path: Path) -> None:
    with _real_app(tmp_path, auth_enabled=True) as (client, _registry_path):
        payload = {
            **_WRITE_PAYLOAD,
            "display_name": _DENIED_SECRET,
            "api_key": _DENIED_SECRET,
            "token": _DENIED_SECRET,
        }
        response = client.post("/api/v1/capabilities/registry", json=payload)

        assert response.status_code == 401
        denied = _denied_write_events()
        assert denied
        rendered = repr([event.model_dump() for event in _capability_write_events()])
        assert _DENIED_SECRET not in rendered
        assert denied[0].target.id == "llm:deepseek-pro"


def _asgi_request(headers: list[tuple[bytes, bytes]], receive):
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/capabilities/registry",
            "raw_path": b"/api/v1/capabilities/registry",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
        },
        receive,
    )


def test_bounded_request_body_stops_chunked_read_at_cap() -> None:
    pulled: list[int] = []
    messages = iter(
        (
            {"type": "http.request", "body": b"{" + b"x" * 4096, "more_body": True},
            {"type": "http.request", "body": b"y" * 1_000_000, "more_body": False},
        )
    )

    async def receive():
        pulled.append(1)
        return next(messages)

    result = asyncio.run(
        _bounded_request_body(
            _asgi_request([(b"transfer-encoding", b"chunked")], receive),
            4096,
        )
    )

    assert result == b""
    assert pulled == [1]


def test_bounded_request_body_reads_undeclared_body_within_cap() -> None:
    payload = b'{"capability_id":"llm:deepseek-pro"}'

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    result = asyncio.run(
        _bounded_request_body(_asgi_request([], receive), 4096)
    )

    assert result == payload


def test_bounded_request_body_skips_read_when_content_length_exceeds_cap() -> None:
    async def receive():
        raise AssertionError("must not read an oversized declared body")

    result = asyncio.run(
        _bounded_request_body(
            _asgi_request([(b"content-length", b"8192")], receive),
            4096,
        )
    )

    assert result == b""
