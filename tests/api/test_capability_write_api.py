# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""API tests for capability write registry and task routing."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middlewares.auth import add_auth_middleware
from api.v1.endpoints import capabilities as capabilities_endpoint
from src.capability_registry.write_audit import CapabilityWriteAuditor
from src.capability_registry.write_service import (
    CapabilityWriteService,
    get_capability_write_service,
)
from src.capability_registry.write_store import CapabilityWriteStore
from src.capability_registry import collect_capability_records
from tests.security_audit_test_utils import SecurityAuditRecorderStub


def _app(tmp_path: Path) -> tuple[TestClient, SecurityAuditRecorderStub]:
    audit = SecurityAuditRecorderStub()
    store = CapabilityWriteStore(tmp_path / "capability_write_registry.json")
    service = CapabilityWriteService(
        store=store,
        auditor=CapabilityWriteAuditor(recorder=audit),
    )
    get_capability_write_service(path=tmp_path / "capability_write_registry.json", reset=True)
    # Replace process singleton with audited test service.
    import src.capability_registry.write_service as write_service_mod

    write_service_mod._SERVICE = service

    app = FastAPI()
    app.include_router(capabilities_endpoint.router, prefix="/api/v1/capabilities")
    add_auth_middleware(app)
    return TestClient(app), audit


def _llm_body(capability_id: str = "llm:primary", **overrides):
    body = {
        "capability_id": capability_id,
        "domain": "llm",
        "capability_type": "llm_model",
        "version": "1.0.0",
        "provider": capability_id,
        "model_route": "openai/gpt-test",
        "tags": ["reasoning", "quality:high"],
        "cost_tier": "high",
    }
    body.update(overrides)
    return body


def test_register_list_retire_route_flow(tmp_path: Path, monkeypatch) -> None:
    client, audit = _app(tmp_path)
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "false")

    created = client.post("/api/v1/capabilities/registry", json=_llm_body())
    assert created.status_code == 200, created.text
    assert created.json()["capability_id"] == "llm:primary"
    assert any(item["outcome"] == "success" for item in audit.completions)

    listed = client.get("/api/v1/capabilities/registry")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["schema_version"] == "capability-write-registry/v1"

    # Read inventory remains independent and does not invent write entries.
    inventory = client.get("/api/v1/capabilities")
    assert inventory.status_code == 200
    assert inventory.json()["schema_version"] == "capability-inventory/v1"

    resolved = client.post(
        "/api/v1/capabilities/registry/resolve",
        json={"capability_ids": ["llm:primary"]},
    )
    assert resolved.status_code == 200
    assert resolved.json()["results"][0]["ready"] is True

    routed = client.post(
        "/api/v1/capabilities/route",
        json={"task_class": "deep_reasoning", "policy": "quality"},
    )
    assert routed.status_code == 200
    body = routed.json()
    assert body["schema_version"] == "task-route-decision/v1"
    # With routing default-off, expect configured fallback or disabled reason.
    assert "reason_code" in body
    assert "explain" in body

    retired = client.post("/api/v1/capabilities/registry/llm:primary/retire")
    assert retired.status_code == 200
    assert retired.json()["status"] == "retired"


def test_unauthorized_write_is_denied_and_audited(tmp_path: Path, monkeypatch) -> None:
    import src.auth as auth

    client, audit = _app(tmp_path)
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "true")
    auth._auth_enabled = None
    try:
        # No session cookie.
        response = client.post(
            "/api/v1/capabilities/registry", json=_llm_body("llm:blocked")
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "unauthorized"
        assert any(item.get("outcome") == "denied" for item in audit.completions)
        service = get_capability_write_service()
        assert service.list_entries().entries == ()
    finally:
        monkeypatch.delenv("ADMIN_AUTH_ENABLED", raising=False)
        auth._auth_enabled = None


def test_failed_register_does_not_pollute_inventory(tmp_path: Path, monkeypatch) -> None:
    client, audit = _app(tmp_path)
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "false")
    bad = client.post(
        "/api/v1/capabilities/registry",
        json={
            "capability_id": "llm:bad",
            "domain": "llm",
            "capability_type": "llm_model",
            "version": "1",
            # missing model_route
        },
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["error"] == "capability_validation_failed"
    assert any(item.get("outcome") == "failure" for item in audit.completions)

    inventory = collect_capability_records(domains=["tool"])
    assert all(item.capability_id != "llm:bad" for item in inventory.items)
    assert get_capability_write_service().list_entries().entries == ()


def test_completed_write_with_failed_audit_is_reported_truthfully(
    tmp_path: Path, monkeypatch
) -> None:
    class CompletionFailureRecorder:
        def record_attempt(self, **fields):
            return None

        def record_completion(self, **fields):
            raise RuntimeError("completion unavailable")

    store = CapabilityWriteStore(tmp_path / "capability_write_registry.json")
    service = CapabilityWriteService(
        store=store,
        auditor=CapabilityWriteAuditor(recorder=CompletionFailureRecorder()),
    )
    import src.capability_registry.write_service as write_service_mod

    write_service_mod._SERVICE = service
    app = FastAPI()
    app.include_router(capabilities_endpoint.router, prefix="/api/v1/capabilities")
    client = TestClient(app)
    monkeypatch.setenv("ADMIN_AUTH_ENABLED", "false")

    response = client.post(
        "/api/v1/capabilities/registry",
        json=_llm_body("llm:persisted"),
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["operation_completed"] is True
    assert detail["capability_id"] == "llm:persisted"
    assert store.get("llm:persisted") is not None
