# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Write-side capability registry, resolution, and task routing tests."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.v1.endpoints import capabilities as capabilities_endpoint
from src.capability_registry.resolution import resolve_capability_dependencies, resolve_many
from src.capability_registry.task_routing import resolve_task_model_route
from src.capability_registry.write_audit import CapabilityWriteAuditor
from src.capability_registry.write_models import WriteCapabilityEntry, WriteRegistrySnapshot
from src.capability_registry.write_service import CapabilityWriteError, CapabilityWriteService
from src.capability_registry.write_store import CapabilityWriteStore, WriteRegistryStoreError
from tests.security_audit_test_utils import SecurityAuditRecorderStub

FIXED_NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def _service(tmp_path: Path):
    store = CapabilityWriteStore(tmp_path / "capability_write_registry.json", clock=lambda: FIXED_NOW)
    recorder = SecurityAuditRecorderStub()
    auditor = CapabilityWriteAuditor(recorder=recorder)
    return CapabilityWriteService(store=store, auditor=auditor, clock=lambda: FIXED_NOW), recorder


def _llm_payload(**overrides):
    payload = {
        "capability_id": "llm:deepseek-pro",
        "domain": "llm",
        "capability_type": "llm_model",
        "version": "1",
        "provider": "deepseek",
        "display_name": "DeepSeek Pro",
        "model_route": "deepseek/deepseek-v4-pro",
        "tags": ["reasoning", "quality:high"],
        "cost_tier": "high",
        "latency_class": "standard",
    }
    payload.update(overrides)
    return payload


def test_register_update_retire_with_audit(tmp_path: Path) -> None:
    service, recorder = _service(tmp_path)
    entry = service.register(_llm_payload())
    assert entry.status == "active"
    assert entry.generation == 1
    assert recorder.attempts[0]["event_type"] == "capability.write"
    assert recorder.completions[0]["outcome"] == "success"
    updated = service.update(entry.capability_id, {"tags": ["reasoning", "coding"], "cost_tier": "medium"})
    assert updated.generation == 2
    assert "coding" in updated.tags
    retired = service.retire(entry.capability_id)
    assert retired.status == "retired"
    again = service.retire(entry.capability_id)
    assert again.status == "retired"


def test_register_duplicate_and_validation_fail_closed(tmp_path: Path) -> None:
    service, recorder = _service(tmp_path)
    service.register(_llm_payload())
    with pytest.raises(CapabilityWriteError) as dup:
        service.register(_llm_payload())
    assert dup.value.error_code == "capability_already_exists"
    with pytest.raises(CapabilityWriteError) as missing_route:
        service.register(_llm_payload(capability_id="llm:broken", model_route=""))
    assert missing_route.value.error_code == "capability_validation_failed"
    assert any(item.get("outcome") == "failure" for item in recorder.completions)
    assert len(service.list_entries().entries) == 1


def test_audit_unavailable_blocks_write(tmp_path: Path) -> None:
    store = CapabilityWriteStore(tmp_path / "registry.json", clock=lambda: FIXED_NOW)

    class BoomRecorder:
        def record_attempt(self, **fields):
            raise RuntimeError("audit down")

        def record_completion(self, **fields):
            raise RuntimeError("audit down")

    service = CapabilityWriteService(
        store=store,
        auditor=CapabilityWriteAuditor(recorder=BoomRecorder()),
        clock=lambda: FIXED_NOW,
    )
    from src.services.security_audit_service import SecurityAuditUnavailable

    with pytest.raises(SecurityAuditUnavailable):
        service.register(_llm_payload())
    assert store.load().entries == ()


def test_corrupt_store_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "capability_write_registry.json"
    path.write_text("{not-json", encoding="utf-8")
    store = CapabilityWriteStore(path)
    with pytest.raises(WriteRegistryStoreError) as exc:
        store.load()
    assert exc.value.error_code == "write_registry_corrupt"


def test_dependency_resolution(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    service.register({
        "capability_id": "tool:quote", "domain": "tool", "capability_type": "agent_tool",
        "version": "2.0.0", "provider": "quote", "display_name": "quote",
    })
    skill = service.register({
        "capability_id": "skill:demo", "domain": "skill", "capability_type": "analysis_skill",
        "version": "1", "provider": "demo",
        "dependencies": ["tool:quote>=1.5.0", "tool:missing"],
    })
    snapshot = service.list_entries()
    ready = resolve_capability_dependencies(
        WriteCapabilityEntry(
            capability_id="skill:ok", domain="skill", capability_type="analysis_skill",
            version="1", status="active", provider="ok", dependencies=("tool:quote~=2.0",),
            registered_at=FIXED_NOW.isoformat(), updated_at=FIXED_NOW.isoformat(),
        ),
        write_snapshot=snapshot,
    )
    assert ready.ready is True
    blocked = resolve_capability_dependencies(skill, write_snapshot=snapshot)
    assert blocked.ready is False
    assert blocked.reason_code == "dependency_missing"

    @dataclass(frozen=True)
    class Inv:
        capability_id: str
        version: str
        registered: bool = True
        executable: bool | None = True

    inventory_ready = resolve_capability_dependencies(
        WriteCapabilityEntry(
            capability_id="skill:from-inventory", domain="skill", capability_type="analysis_skill",
            version="1", status="active", provider="x", dependencies=("tool:live@1",),
            registered_at=FIXED_NOW.isoformat(), updated_at=FIXED_NOW.isoformat(),
        ),
        write_snapshot=WriteRegistrySnapshot(generation=0, as_of=FIXED_NOW.isoformat()),
        inventory_items=(Inv(capability_id="tool:live", version="1"),),
    )
    assert inventory_ready.ready is True


def test_version_incompatible_dependency(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    service.register({
        "capability_id": "tool:quote", "domain": "tool", "capability_type": "agent_tool",
        "version": "1.0.0", "provider": "quote",
    })
    entry = service.register({
        "capability_id": "skill:needs-newer", "domain": "skill", "capability_type": "analysis_skill",
        "version": "1", "provider": "x", "dependencies": ["tool:quote>=2.0.0"],
    })
    result = resolve_capability_dependencies(entry, write_snapshot=service.list_entries())
    assert result.ready is False
    assert result.reason_code == "version_incompatible"


def _empty_pins(**kwargs):
    base = dict(
        task_routing_enabled=False, task_routing_policy="quality",
        litellm_model="", agent_litellm_model="", vision_model="",
        task_routing_pin_report="", task_routing_pin_agent="", task_routing_pin_vision="",
        task_routing_pin_market_review="", task_routing_pin_cheap_scan="",
        task_routing_pin_deep_reasoning="", task_routing_pin_coding="",
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_task_routing_manual_pin_wins() -> None:
    decision = resolve_task_model_route(
        "report",
        config=_empty_pins(task_routing_enabled=True, litellm_model="openai/gpt-pinned"),
        write_snapshot=WriteRegistrySnapshot(as_of=FIXED_NOW.isoformat()),
        clock=lambda: FIXED_NOW,
    )
    assert decision.reason_code == "manual_pin"
    assert decision.selected_model == "openai/gpt-pinned"
    assert decision.pin_source == "LITELLM_MODEL"


def test_task_routing_policy_match(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    service.register(_llm_payload(
        capability_id="llm:cheap", model_route="ollama/qwen3:8b",
        tags=["cost:low", "latency:fast", "local"], cost_tier="low", latency_class="fast",
    ))
    service.register(_llm_payload(
        capability_id="llm:quality", model_route="deepseek/deepseek-v4-pro",
        tags=["reasoning", "quality:high"], cost_tier="high",
    ))
    snapshot = service.list_entries(include_retired=False)
    cheap = resolve_task_model_route(
        "cheap_scan", config=_empty_pins(task_routing_enabled=True, task_routing_policy="cost"),
        write_snapshot=snapshot, clock=lambda: FIXED_NOW,
    )
    assert cheap.reason_code == "policy_match"
    assert cheap.selected_model == "ollama/qwen3:8b"
    deep = resolve_task_model_route(
        "deep_reasoning",
        config=_empty_pins(task_routing_enabled=True, task_routing_policy="quality"),
        write_snapshot=snapshot, clock=lambda: FIXED_NOW,
    )
    assert deep.selected_model == "deepseek/deepseek-v4-pro"


def test_task_routing_disabled_without_pin() -> None:
    decision = resolve_task_model_route("report", config=_empty_pins(), clock=lambda: FIXED_NOW)
    assert decision.reason_code == "routing_disabled"
    assert decision.selected_model == ""


def test_api_write_resolve_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, recorder = _service(tmp_path)
    monkeypatch.setattr(capabilities_endpoint, "get_capability_write_service", lambda: service)

    from src.capability_registry.task_routing import (
        resolve_task_model_route as _real_route,
    )

    def _routed(task_class, **kwargs):
        kwargs["config"] = _empty_pins(
            task_routing_enabled=True, task_routing_policy="quality"
        )
        return _real_route(task_class, **kwargs)

    monkeypatch.setattr(capabilities_endpoint, "resolve_task_model_route", _routed)
    app = FastAPI()
    app.include_router(capabilities_endpoint.router, prefix="/api/v1/capabilities")
    client = TestClient(app)

    created = client.post("/api/v1/capabilities/registry", json=_llm_payload())
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "active"
    assert recorder.attempts

    listed = client.get("/api/v1/capabilities/registry")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    resolved = client.post(
        "/api/v1/capabilities/resolve",
        json={"capability_ids": ["llm:deepseek-pro"], "include_inventory": False},
    )
    assert resolved.status_code == 200
    assert resolved.json()["ready_count"] == 1

    routed = client.post(
        "/api/v1/capabilities/route",
        json={"task_class": "deep_reasoning", "policy": "quality"},
    )
    assert routed.status_code == 200
    body = routed.json()
    assert body["schema_version"] == "task-route-decision/v1"
    assert body["reason_code"] == "policy_match"
    assert body["selected_model"] == "deepseek/deepseek-v4-pro"

    retired = client.post("/api/v1/capabilities/registry/llm:deepseek-pro/retire")
    assert retired.status_code == 200
    assert retired.json()["status"] == "retired"

    missing = client.post(
        "/api/v1/capabilities/registry",
        json=_llm_payload(capability_id="llm:no-route", model_route=""),
    )
    assert missing.status_code == 400
    assert missing.json()["detail"]["error"] == "capability_validation_failed"


def test_resolve_many_missing_id(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    results = resolve_many(["does-not-exist"], write_snapshot=service.list_entries())
    assert results[0].reason_code == "capability_not_found"
    assert results[0].ready is False


def test_resolve_many_retired_id_is_reported_once(tmp_path: Path) -> None:
    """A requested retired id resolves to capability_retired only, never a duplicate."""

    service, _ = _service(tmp_path)
    service.register(_llm_payload(capability_id="llm:old"))
    service.retire("llm:old")

    results = resolve_many(
        ["llm:old", "llm:missing"],
        write_snapshot=service.list_entries(include_retired=True),
        active_only=True,
    )

    assert [item.capability_id for item in results] == ["llm:missing", "llm:old"]
    by_id = {item.capability_id: item for item in results}
    assert by_id["llm:old"].reason_code == "capability_retired"
    assert by_id["llm:old"].ready is False
    assert by_id["llm:missing"].reason_code == "capability_not_found"


def test_audit_completion_failure_after_write_is_distinct(tmp_path: Path) -> None:
    store = CapabilityWriteStore(tmp_path / "registry.json", clock=lambda: FIXED_NOW)

    class FlakyRecorder:
        def __init__(self) -> None:
            self.attempts = 0

        def record_attempt(self, **fields):
            self.attempts += 1
            return None

        def record_completion(self, **fields):
            raise RuntimeError("completion down")

    from src.capability_registry.write_service import (
        CapabilityWriteAuditCompletionUnavailable,
    )

    service = CapabilityWriteService(
        store=store,
        auditor=CapabilityWriteAuditor(recorder=FlakyRecorder()),
        clock=lambda: FIXED_NOW,
    )
    with pytest.raises(CapabilityWriteAuditCompletionUnavailable):
        service.register(_llm_payload(capability_id="llm:written"))
    # Mutation must have persisted even though completion audit failed.
    assert store.get("llm:written") is not None


def test_update_and_retire_audit_completion_failure_after_write_is_distinct(
    tmp_path: Path,
) -> None:
    service, _ = _service(tmp_path)
    service.register(_llm_payload(capability_id="llm:written"))

    class BoomRecorder:
        def record_attempt(self, **fields):
            return None

        def record_completion(self, **fields):
            raise RuntimeError("completion down")

    from src.capability_registry.write_service import (
        CapabilityWriteAuditCompletionUnavailable,
    )

    service._auditor = CapabilityWriteAuditor(recorder=BoomRecorder())
    with pytest.raises(CapabilityWriteAuditCompletionUnavailable):
        service.update("llm:written", {"cost_tier": "low"})
    updated = service.store.get("llm:written")
    assert updated is not None
    assert updated.cost_tier == "low"

    with pytest.raises(CapabilityWriteAuditCompletionUnavailable):
        service.retire("llm:written")
    retired = service.store.get("llm:written")
    assert retired is not None
    assert retired.status == "retired"


def test_failure_audit_does_not_mask_domain_error(tmp_path: Path) -> None:
    store = CapabilityWriteStore(tmp_path / "registry.json", clock=lambda: FIXED_NOW)

    class BoomRecorder:
        def record_attempt(self, **fields):
            return None

        def record_completion(self, **fields):
            raise RuntimeError("completion down")

    from src.capability_registry.write_service import (
        CapabilityWriteAuditCompletionUnavailable,
    )

    service = CapabilityWriteService(
        store=store,
        auditor=CapabilityWriteAuditor(recorder=BoomRecorder()),
        clock=lambda: FIXED_NOW,
    )
    with pytest.raises(CapabilityWriteAuditCompletionUnavailable):
        service.register(_llm_payload(capability_id="llm:written"))
    with pytest.raises(CapabilityWriteError) as missing:
        service.update("llm:missing", {"display_name": "gone"})
    assert missing.value.error_code == "capability_not_found"
    with pytest.raises(CapabilityWriteError) as duplicate:
        service.register(_llm_payload(capability_id="llm:written"))
    assert duplicate.value.error_code == "capability_already_exists"


def test_store_mutate_serializes_concurrent_writers(tmp_path: Path) -> None:
    store = CapabilityWriteStore(tmp_path / "registry.json", clock=lambda: FIXED_NOW)
    now = FIXED_NOW.isoformat()
    started = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def _entry(capability_id: str) -> WriteCapabilityEntry:
        return WriteCapabilityEntry(
            capability_id=capability_id,
            domain="llm",
            capability_type="llm_model",
            version="1",
            status="active",
            provider=capability_id,
            display_name=capability_id,
            model_route="openai/gpt",
            registered_at=now,
            updated_at=now,
            generation=1,
        )

    def writer_a() -> None:
        try:
            def add_a(snapshot: WriteRegistrySnapshot):
                started.set()
                assert release.wait(timeout=2)
                return snapshot.entries + (_entry("llm:a"),)

            store.mutate(add_a)
        except BaseException as exc:
            errors.append(exc)

    def writer_b() -> None:
        try:
            assert started.wait(timeout=2)

            def add_b(snapshot: WriteRegistrySnapshot):
                return snapshot.entries + (_entry("llm:b"),)

            store.mutate(add_b)
        except BaseException as exc:
            errors.append(exc)

    thread_a = threading.Thread(target=writer_a)
    thread_b = threading.Thread(target=writer_b)
    thread_a.start()
    assert started.wait(timeout=2)
    thread_b.start()
    time.sleep(0.05)
    release.set()
    thread_a.join(timeout=2)
    thread_b.join(timeout=2)
    assert errors == []
    ids = {item.capability_id for item in store.load().entries}
    assert ids == {"llm:a", "llm:b"}


def test_replace_entries_rejects_stale_generation(tmp_path: Path) -> None:
    store = CapabilityWriteStore(tmp_path / "registry.json", clock=lambda: FIXED_NOW)
    store.replace_entries((), generation=1)
    with pytest.raises(WriteRegistryStoreError) as exc:
        store.replace_entries((), generation=1)
    assert exc.value.error_code == "write_registry_generation_conflict"


def test_api_route_uses_live_config_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = _service(tmp_path)
    monkeypatch.setattr(capabilities_endpoint, "get_capability_write_service", lambda: service)

    from src.config import Config

    pins = _empty_pins(
        task_routing_enabled=True, litellm_model="openai/gpt-pinned",
    )
    monkeypatch.setattr(Config, "get_instance", classmethod(lambda cls: pins))

    app = FastAPI()
    app.include_router(capabilities_endpoint.router, prefix="/api/v1/capabilities")
    client = TestClient(app)

    routed = client.post(
        "/api/v1/capabilities/route",
        json={"task_class": "report"},
    )
    assert routed.status_code == 200, routed.text
    body = routed.json()
    assert body["reason_code"] == "manual_pin"
    assert body["selected_model"] == "openai/gpt-pinned"
    assert body["pin_source"] == "LITELLM_MODEL"
    assert body["routing_enabled"] is True
