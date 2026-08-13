# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Write-side capability registry, resolution, and task routing tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.capability_registry.resolution import (
    detect_dependency_cycle,
    resolve_capability_dependencies,
    resolve_many,
)
from src.capability_registry.task_routing import (
    decision_for_diagnostics,
    resolve_task_model_route,
)
from src.capability_registry.write_audit import CapabilityWriteAuditor
from src.capability_registry.write_models import (
    WriteCapabilityEntry,
    WriteRegistrySnapshot,
)
from src.capability_registry.write_service import (
    CapabilityWriteAuditCompletionUnavailable,
    CapabilityWriteError,
    CapabilityWriteService,
)
from src.capability_registry.write_store import CapabilityWriteStore
from src.capability_registry.service import collect_capability_records
from tests.security_audit_test_utils import SecurityAuditRecorderStub


def _svc(tmp_path: Path) -> tuple[CapabilityWriteService, SecurityAuditRecorderStub]:
    audit = SecurityAuditRecorderStub()
    store = CapabilityWriteStore(tmp_path / "capability_write_registry.json")
    service = CapabilityWriteService(
        store=store,
        auditor=CapabilityWriteAuditor(recorder=audit),
    )
    return service, audit


def _llm_payload(capability_id: str, **overrides):
    base = {
        "capability_id": capability_id,
        "domain": "llm",
        "capability_type": "llm_model",
        "version": "1.0.0",
        "provider": capability_id,
        "model_route": f"openai/{capability_id}",
        "tags": ["reasoning"],
        "cost_tier": "medium",
    }
    base.update(overrides)
    return base


def test_register_update_retire_roundtrip(tmp_path: Path) -> None:
    service, audit = _svc(tmp_path)
    entry = service.register(_llm_payload("llm:primary"))
    assert entry.status == "active"
    assert len(audit.attempts) == 1
    assert audit.completions[-1]["outcome"] == "success"

    updated = service.update(
        "llm:primary",
        {"tags": ["reasoning", "quality:high"], "cost_tier": "high"},
    )
    assert "quality:high" in updated.tags
    assert updated.generation == 2

    retired = service.retire("llm:primary")
    assert retired.status == "retired"
    assert retired.retired_at is not None
    # Retired capabilities must not be selected by the router.
    decision = resolve_task_model_route(
        "report",
        config=_Cfg(task_routing_enabled=True, litellm_model=""),
        write_snapshot=service.list_entries(),
    )
    assert decision.selected_capability_id != "llm:primary"
    assert decision.reason_code in {
        "no_llm_capabilities",
        "no_matching_candidate",
        "no_llm_capabilities_configured_fallback",
        "no_matching_candidate_configured_fallback",
    }


def test_duplicate_register_fails_without_polluting_store(tmp_path: Path) -> None:
    service, audit = _svc(tmp_path)
    service.register(_llm_payload("llm:primary"))
    with pytest.raises(CapabilityWriteError) as exc:
        service.register(_llm_payload("llm:primary"))
    assert exc.value.error_code == "capability_already_exists"
    assert audit.completions[-1]["outcome"] == "failure"
    snap = service.list_entries()
    assert len(snap.entries) == 1


def test_validation_failure_does_not_write_store(tmp_path: Path) -> None:
    service, audit = _svc(tmp_path)
    with pytest.raises(CapabilityWriteError) as exc:
        service.register(
            {
                "capability_id": "llm:broken",
                "domain": "llm",
                "capability_type": "llm_model",
                "version": "1",
                # missing model_route for active llm
            }
        )
    assert exc.value.error_code == "capability_validation_failed"
    assert service.list_entries().entries == ()
    assert not (tmp_path / "capability_write_registry.json").exists() or \
        CapabilityWriteStore(tmp_path / "capability_write_registry.json").load().entries == ()


def test_registration_failure_does_not_pollute_read_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hard acceptance: failed write never appears in GET inventory snapshot."""

    service, _audit = _svc(tmp_path)
    monkeypatch.setenv(
        "CAPABILITY_WRITE_REGISTRY_PATH",
        str(tmp_path / "capability_write_registry.json"),
    )
    with pytest.raises(CapabilityWriteError):
        service.register(
            {
                "capability_id": "llm:invalid",
                "domain": "llm",
                "capability_type": "llm_model",
                "version": "1",
            }
        )
    # Inventory remains owner-driven only; failed write is not projected.
    inventory = collect_capability_records(domains=["tool"])
    assert all(
        item.capability_id != "llm:invalid" for item in inventory.items
    )


def test_resolve_many_retired_requested_id_is_not_also_not_found(
    tmp_path: Path,
) -> None:
    """Explicit retired ids emit capability_retired once, never not_found."""

    service, _ = _svc(tmp_path)
    service.register(_llm_payload("llm:old"))
    service.retire("llm:old")
    snap = service.list_entries(include_retired=True)
    results = resolve_many(
        ["llm:old", "llm:missing"],
        write_snapshot=snap,
        active_only=True,
    )
    by_id = {item.capability_id: item for item in results}
    assert len(results) == 2
    assert by_id["llm:old"].reason_code == "capability_retired"
    assert by_id["llm:old"].ready is False
    assert by_id["llm:missing"].reason_code == "capability_not_found"


def test_unauthorized_write_denied_is_audited(tmp_path: Path) -> None:
    """Hard acceptance: unauthorized writes are rejected and leave audit trail."""

    service, audit = _svc(tmp_path)
    correlation = service.auditor.record_denied(
        capability_id="llm:secret",
        operation="register",
        reason_code="capability_write_unauthorized",
        actor_type="anonymous",
        actor_id="unauthenticated",
    )
    assert correlation
    assert len(audit.attempts) == 1
    assert audit.completions[-1]["outcome"] == "denied"
    assert audit.completions[-1]["reason_code"] == "capability_write_unauthorized"
    assert service.list_entries().entries == ()


def test_audit_completion_failure_reports_persisted_mutation(tmp_path: Path) -> None:
    store = CapabilityWriteStore(tmp_path / "capability_write_registry.json")

    class CompletionFailureRecorder:
        def record_attempt(self, **fields):
            return None

        def record_completion(self, **fields):
            raise RuntimeError("completion unavailable")

    service = CapabilityWriteService(
        store=store,
        auditor=CapabilityWriteAuditor(recorder=CompletionFailureRecorder()),
    )

    with pytest.raises(CapabilityWriteAuditCompletionUnavailable) as exc:
        service.register(_llm_payload("llm:persisted"))

    assert exc.value.entry.capability_id == "llm:persisted"
    assert store.get("llm:persisted") is not None


def test_dependency_cycle_and_version_incompatibility(tmp_path: Path) -> None:
    service, _ = _svc(tmp_path)
    service.register(
        {
            "capability_id": "tool:a",
            "domain": "tool",
            "capability_type": "agent_tool",
            "version": "1.0.0",
            "provider": "a",
            "dependencies": ["tool:b"],
        }
    )
    service.register(
        {
            "capability_id": "tool:b",
            "domain": "tool",
            "capability_type": "agent_tool",
            "version": "1.0.0",
            "provider": "b",
            "dependencies": ["tool:a"],
        }
    )
    snap = service.list_entries()
    a = next(item for item in snap.entries if item.capability_id == "tool:a")
    cycle = detect_dependency_cycle(a, write_snapshot=snap)
    assert cycle is not None
    result = resolve_capability_dependencies(a, write_snapshot=snap)
    assert result.ready is False
    assert result.reason_code == "dependency_cycle"

    service.register(
        {
            "capability_id": "tool:c",
            "domain": "tool",
            "capability_type": "agent_tool",
            "version": "2.0.0",
            "provider": "c",
            "dependencies": ["tool:base>=3.0.0"],
        }
    )
    service.register(
        {
            "capability_id": "tool:base",
            "domain": "tool",
            "capability_type": "agent_tool",
            "version": "1.5.0",
            "provider": "base",
        }
    )
    snap = service.list_entries()
    c = next(item for item in snap.entries if item.capability_id == "tool:c")
    incompat = resolve_capability_dependencies(c, write_snapshot=snap)
    assert incompat.ready is False
    assert incompat.reason_code == "version_incompatible"


def test_task_route_decision_explainable_and_diagnostic(tmp_path: Path) -> None:
    """Hard acceptance: routing decisions can be reconstructed from diagnostics."""

    service, _ = _svc(tmp_path)
    service.register(
        _llm_payload(
            "llm:cheap",
            model_route="openai/cheap",
            tags=["cost:low", "latency:fast"],
            cost_tier="low",
            latency_class="fast",
        )
    )
    service.register(
        _llm_payload(
            "llm:reasoner",
            model_route="openai/reasoner",
            tags=["reasoning", "quality:high"],
            cost_tier="high",
        )
    )
    snap = service.list_entries()
    decision = resolve_task_model_route(
        "deep_reasoning",
        config=_Cfg(task_routing_enabled=True, litellm_model="openai/default"),
        write_snapshot=snap,
        policy="quality",
    )
    assert decision.reason_code == "policy_match"
    assert decision.selected_capability_id == "llm:reasoner"
    diag = decision_for_diagnostics(decision)
    assert diag["selected_model"] == "openai/reasoner"
    assert diag["reason_code"] == "policy_match"
    assert any("selected llm:reasoner" in line for line in diag["explain"])
    assert diag["candidates"]

    # Manual pin wins.
    pinned = resolve_task_model_route(
        "report",
        config=_Cfg(
            task_routing_enabled=True,
            task_routing_pin_report="openai/pinned",
            litellm_model="openai/default",
        ),
        write_snapshot=snap,
    )
    assert pinned.reason_code == "manual_pin"
    assert pinned.selected_model == "openai/pinned"


def test_retired_not_routed_and_concurrent_safe(tmp_path: Path) -> None:
    service, _ = _svc(tmp_path)
    service.register(_llm_payload("llm:a", tags=["reasoning"]))
    service.retire("llm:a")
    decision = resolve_task_model_route(
        "report",
        config=_Cfg(task_routing_enabled=True, litellm_model="openai/fallback"),
        write_snapshot=service.list_entries(),
    )
    assert decision.selected_capability_id != "llm:a"
    assert decision.selected_model == "openai/fallback"
    assert decision.fallback_used is True

    # Concurrent-ish sequential writes under the store lock stay consistent.
    service.register(_llm_payload("llm:b", tags=["reasoning"]))
    service.register(_llm_payload("llm:c", tags=["reasoning"]))
    ids = {item.capability_id for item in service.list_entries().entries}
    assert "llm:b" in ids and "llm:c" in ids


@dataclass
class _Cfg:
    task_routing_enabled: bool = False
    task_routing_policy: str = "quality"
    task_routing_pin_report: str = ""
    task_routing_pin_agent: str = ""
    task_routing_pin_vision: str = ""
    task_routing_pin_market_review: str = ""
    task_routing_pin_cheap_scan: str = ""
    task_routing_pin_deep_reasoning: str = ""
    task_routing_pin_coding: str = ""
    litellm_model: str = ""
    agent_litellm_model: str = ""
    vision_model: str = ""
