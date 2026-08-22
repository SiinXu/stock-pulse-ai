# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed SystemConfigService.update security-audit coverage."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api import deps as api_deps
from src.api.v1.endpoints import config_profiles as config_profiles_endpoint
from src.api.v1.endpoints import onboarding as onboarding_endpoint
from src.api.v1.endpoints import system_config as system_config_endpoint
from src.api.v1.errors import normalize_error_body
from src.api.v1.schemas.system_config import (
    ImportSystemConfigRequest,
    UpdateSystemConfigRequest,
)
from src.config import Config
from src.core.config_manager import ConfigManager
from src.repositories.security_audit_repo import SecurityAuditRepository
from src.schemas.security_audit import SecurityAuditEvent, SecurityAuditEventCreate
from src.services.config_presets import PROFILE_API_VERSION, PROFILE_KIND
from src.services.config_profile_service import ConfigProfileService
from src.services.onboarding_plan_service import OnboardingPlanService
from src.services.security_audit_service import (
    SecurityAuditService,
    SecurityAuditUnavailable,
)
from src.services.system_config_service import (
    ConfigValidationError,
    SystemConfigService,
    SystemConfigWriteAuditCompletionUnavailable,
)
from src.services.system_config_service_parts.write_audit import (
    SYSTEM_CONFIG_WRITE_EVENT_TYPE,
    _persist_already_ran,
)
from src.storage import DatabaseManager
from tests.security.test_security_audit_integrations import (
    _RecordingAudit,
    _SchemaValidatingAuditRepository,
)

CANARY = "write-audit-canary-secret"
CANARY_URL = "https://llm-canary.example/v1"
CANARY_MODEL = "canary-model-name"


def _visible(audit: _RecordingAudit) -> str:
    return json.dumps(
        {"attempts": audit.attempts, "completions": audit.completions},
        ensure_ascii=False,
        default=str,
    )


def _write_events(audit: _RecordingAudit, *, phase: str) -> list[dict]:
    source = audit.attempts if phase == "attempt" else audit.completions
    return [
        event
        for event in source
        if event.get("event_type") == SYSTEM_CONFIG_WRITE_EVENT_TYPE
    ]


def _config_service(tmp_path, monkeypatch, *lines: str):
    env_path = tmp_path / ".env"
    body = "\n".join(lines or ("LOG_LEVEL=INFO",)) + "\n"
    env_path.write_text(body, encoding="utf-8")
    monkeypatch.setenv("ENV_FILE", str(env_path))
    monkeypatch.setenv("OUTBOUND_HTTP_ALLOWLIST", "localhost,127.0.0.1")
    monkeypatch.delenv("DSA_DESKTOP_MODE", raising=False)
    Config.reset_instance()
    manager = ConfigManager(env_path=env_path)
    return SystemConfigService(manager=manager), manager, env_path


def _put_app(config_service, audit) -> FastAPI:
    app = FastAPI()
    app.include_router(system_config_endpoint.router, prefix="/api/v1/system")
    app.dependency_overrides[api_deps.get_system_config_service] = lambda: config_service
    app.dependency_overrides[api_deps.require_security_audit_service] = lambda: audit
    app.dependency_overrides[api_deps.get_security_audit_service] = lambda: audit
    return app


def _request():
    return SimpleNamespace(cookies={system_config_endpoint.COOKIE_NAME: "valid-session"})


@pytest.fixture
def write_database(tmp_path):
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'system-config-write-audit.sqlite'}")
    try:
        yield manager
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def test_http_put_records_one_attempt_and_success_without_secrets(
    tmp_path, monkeypatch
) -> None:
    service, manager, _env_path = _config_service(
        tmp_path, monkeypatch, "GEMINI_API_KEY=old-secret"
    )
    audit = _RecordingAudit()
    request = UpdateSystemConfigRequest(
        config_version=manager.get_config_version(),
        reload_now=False,
        items=[{"key": "GEMINI_API_KEY", "value": CANARY}],
    )

    response = system_config_endpoint.update_system_config(
        request=request,
        service=service,
        security_audit=audit,
    )

    assert response.success is True
    attempts = _write_events(audit, phase="attempt")
    completions = _write_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert attempts[0]["event_type"] == SYSTEM_CONFIG_WRITE_EVENT_TYPE
    assert attempts[0]["action"] == SYSTEM_CONFIG_WRITE_EVENT_TYPE
    assert attempts[0]["actor_type"] == "administrator"
    assert attempts[0]["actor_id"] in {
        "local_operator",
        "authenticated_admin",
        "desktop_operator",
    }
    assert attempts[0]["metadata"]["source"] == "http_put"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]
    assert completions[0]["outcome"] == "success"
    assert completions[0]["reason_code"] == "config_updated"
    visible = _visible(audit)
    assert CANARY not in visible
    assert CANARY_URL not in visible
    assert CANARY_MODEL not in visible


def test_attempt_failure_does_not_persist(tmp_path, monkeypatch) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    audit = _RecordingAudit(fail_attempt=True)

    with pytest.raises(SecurityAuditUnavailable):
        service.update(
            config_version=manager.get_config_version(),
            items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
            reload_now=False,
            security_audit=audit,
        )

    assert manager.read_config_map()["LOG_LEVEL"] == "INFO"
    assert _write_events(audit, phase="attempt") == []
    assert _write_events(audit, phase="completion") == []


def test_http_attempt_failure_is_503_operation_not_completed(
    tmp_path, monkeypatch
) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    audit = _RecordingAudit(fail_attempt=True)
    app = _put_app(service, audit)
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/system/config",
            json={
                "config_version": manager.get_config_version(),
                "reload_now": False,
                "items": [{"key": "LOG_LEVEL", "value": "DEBUG"}],
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "security_audit_unavailable"
    assert response.json()["detail"]["operation_completed"] is False
    assert manager.read_config_map()["LOG_LEVEL"] == "INFO"


def test_success_completion_failure_keeps_persisted_write(
    tmp_path, monkeypatch
) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    audit = _RecordingAudit(fail_completion=True)

    with pytest.raises(SystemConfigWriteAuditCompletionUnavailable) as exc_info:
        service.update(
            config_version=manager.get_config_version(),
            items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
            reload_now=False,
            security_audit=audit,
        )

    assert manager.read_config_map()["LOG_LEVEL"] == "DEBUG"
    assert exc_info.value.item["applied_count"] == 1
    assert len(_write_events(audit, phase="attempt")) == 1
    completions = _write_events(audit, phase="completion")
    assert completions == []
    assert all(event.get("reason_code") != "config_update_failed" for event in audit.completions)


def test_http_completion_failure_is_503_operation_completed(
    tmp_path, monkeypatch
) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    audit = _RecordingAudit(fail_completion=True)
    app = _put_app(service, audit)
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/system/config",
            json={
                "config_version": manager.get_config_version(),
                "reload_now": False,
                "items": [{"key": "LOG_LEVEL", "value": "DEBUG"}],
            },
        )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "security_audit_unavailable"
    assert detail["operation_completed"] is True
    assert detail["applied_count"] == 1
    assert manager.read_config_map()["LOG_LEVEL"] == "DEBUG"
    assert all(
        event.get("reason_code") != "config_update_failed"
        for event in _write_events(audit, phase="completion")
    )


def test_production_envelope_keeps_operation_completed_in_params() -> None:
    body = normalize_error_body(
        {
            "error": "security_audit_unavailable",
            "message": (
                "Configuration was persisted, but audit completion could not be persisted"
            ),
            "operation_completed": True,
            "config_version": "v2",
            "applied_count": 1,
        },
        default_error="http_error",
        default_message="Request failed",
    )
    assert body["error"] == "security_audit_unavailable"
    assert body["params"]["operation_completed"] is True
    assert body["params"]["applied_count"] == 1
    assert "operation_completed" not in body


def test_domain_400_preserved_when_reject_completion_fails(
    tmp_path, monkeypatch
) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    audit = _RecordingAudit(fail_completion=True)

    with pytest.raises(HTTPException) as exc_info:
        system_config_endpoint.update_system_config(
            request=UpdateSystemConfigRequest(
                config_version=manager.get_config_version(),
                reload_now=False,
                items=[{"key": "not valid", "value": CANARY}],
            ),
            service=service,
            security_audit=audit,
        )

    assert exc_info.value.status_code == 400
    assert manager.read_config_map()["LOG_LEVEL"] == "INFO"


def test_domain_409_preserved_when_reject_completion_fails(
    tmp_path, monkeypatch
) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    audit = _RecordingAudit(fail_completion=True)

    with pytest.raises(HTTPException) as exc_info:
        system_config_endpoint.update_system_config(
            request=UpdateSystemConfigRequest(
                config_version="stale-version",
                reload_now=False,
                items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
            ),
            service=service,
            security_audit=audit,
        )

    assert exc_info.value.status_code == 409
    assert manager.read_config_map()["LOG_LEVEL"] == "INFO"


def test_persist_already_ran_excludes_rolled_back_activation() -> None:
    rolled_back = ConfigValidationError(
        issues=[{"code": "runtime_activation_failed"}]
    )
    unrestored = RuntimeError("Configuration activation and restoration failed")

    assert _persist_already_ran(rolled_back) is False
    assert _persist_already_ran(unrestored) is True


def test_runtime_activation_failed_preserves_400_when_reject_completion_fails(
    tmp_path, monkeypatch
) -> None:
    service, manager, _env_path = _config_service(
        tmp_path, monkeypatch, "LOG_LEVEL=INFO"
    )
    audit = _RecordingAudit(fail_completion=True)
    rolled_back = ConfigValidationError(
        issues=[
            {
                "key": "RUNTIME_CONFIG",
                "code": "runtime_activation_failed",
                "severity": "error",
                "message": (
                    "The candidate configuration could not be activated; "
                    "the previous runtime configuration was restored."
                ),
            }
        ]
    )

    with patch.object(service, "_update_validated", side_effect=rolled_back):
        with pytest.raises(HTTPException) as exc_info:
            system_config_endpoint.update_system_config(
                request=UpdateSystemConfigRequest(
                    config_version=manager.get_config_version(),
                    reload_now=True,
                    items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
                ),
                service=service,
                security_audit=audit,
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "validation_failed"
    assert exc_info.value.detail["issues"][0]["code"] == "runtime_activation_failed"
    assert manager.read_config_map()["LOG_LEVEL"] == "INFO"


def test_profile_apply_emits_write_with_preset_source(tmp_path, monkeypatch) -> None:
    service, manager, _env_path = _config_service(
        tmp_path,
        monkeypatch,
        "LOG_LEVEL=INFO",
        "LLM_OLLAMA_MODELS=llama3.2:1b",
    )
    audit = _RecordingAudit()
    profiles = ConfigProfileService(
        system_config_service=service,
        ollama_probe=lambda: False,
        which_executable=lambda _name: None,
    )

    result = profiles.apply_preset(
        "local-first",
        config_version=manager.get_config_version(),
        reload_now=False,
        security_audit=audit,
    )

    assert result["applied"] is True
    attempts = _write_events(audit, phase="attempt")
    completions = _write_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert attempts[0]["metadata"]["source"] == "config_profile_preset"
    assert CANARY not in _visible(audit)


def test_profile_empty_noop_does_not_emit(tmp_path, monkeypatch) -> None:
    service, manager, _env_path = _config_service(
        tmp_path,
        monkeypatch,
        "GENERATION_BACKEND=litellm",
        "GENERATION_FALLBACK_BACKEND=litellm",
        "LLM_CONFIG_MODE=channels",
        "LLM_OLLAMA_PROVIDER=ollama",
        "LLM_OLLAMA_PROTOCOL=ollama",
        "LLM_OLLAMA_ENABLED=true",
        "LLM_OLLAMA_DISPLAY_NAME=Ollama (local)",
        "AGENT_GENERATION_BACKEND=auto",
        "AGENT_SKILLS=bull_trend",
        "LLM_CHANNELS=ollama",
        "LLM_OLLAMA_MODELS=llama3.2:1b",
    )
    audit = _RecordingAudit()
    profiles = ConfigProfileService(
        system_config_service=service,
        ollama_probe=lambda: False,
        which_executable=lambda _name: None,
    )

    result = profiles.apply_preset(
        "local-first",
        config_version=manager.get_config_version(),
        reload_now=False,
        security_audit=audit,
    )

    assert result["applied"] is False
    assert _write_events(audit, phase="attempt") == []
    assert _write_events(audit, phase="completion") == []


def test_profile_secret_rejected_before_update(tmp_path, monkeypatch) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    audit = _RecordingAudit()
    profiles = ConfigProfileService(
        system_config_service=service,
        ollama_probe=lambda: False,
        which_executable=lambda _name: None,
    )
    evil = yaml.safe_dump(
        {
            "apiVersion": PROFILE_API_VERSION,
            "kind": PROFILE_KIND,
            "metadata": {"name": "evil"},
            "spec": {
                "llm": {"config": {"OPENAI_API_KEY": CANARY}},
                "strategies": {"enabled": []},
                "features": {},
            },
        }
    )

    with pytest.raises(Exception):
        profiles.apply_import(
            content=evil,
            config_version=manager.get_config_version(),
            reload_now=False,
            security_audit=audit,
        )

    assert _write_events(audit, phase="attempt") == []
    assert manager.read_config_map().get("OPENAI_API_KEY") is None


def test_onboarding_apply_emits_write(tmp_path, monkeypatch) -> None:
    service, manager, env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    audit = _RecordingAudit()
    onboarding = OnboardingPlanService(
        system_config_service=service,
        state_path=tmp_path / "onboarding_state.json",
    )
    result = onboarding.apply_plan(
        {
            "schema_version": 1,
            "experience_stage": "beginner",
            "markets": ["cn"],
            "goals": ["pre_post_market"],
            "holdings": "none",
            "interaction": "web",
            "risk_tone": "balanced",
            "infrastructure": "cloud_key",
            "report_language": "en",
        },
        config_version=manager.get_config_version(),
        confirm=True,
        security_audit=audit,
    )

    assert result["success"] is True
    attempts = _write_events(audit, phase="attempt")
    assert len(attempts) == 1
    assert attempts[0]["metadata"]["source"] == "onboarding_apply"


def test_onboarding_confirm_false_does_not_emit(tmp_path, monkeypatch) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    audit = _RecordingAudit()
    onboarding = OnboardingPlanService(
        system_config_service=service,
        state_path=tmp_path / "onboarding_state.json",
    )
    with pytest.raises(Exception):
        onboarding.apply_plan(
            {
                "schema_version": 1,
                "experience_stage": "beginner",
                "markets": ["cn"],
                "goals": ["pre_post_market"],
                "holdings": "none",
                "interaction": "web",
                "risk_tone": "balanced",
                "infrastructure": "cloud_key",
                "report_language": "en",
            },
            config_version=manager.get_config_version(),
            confirm=False,
            security_audit=audit,
        )
    assert _write_events(audit, phase="attempt") == []


def test_local_model_persist_emits_write_and_attempt_fail_is_closed(
    tmp_path, monkeypatch
) -> None:
    service, manager, _env_path = _config_service(
        tmp_path, monkeypatch, "LLM_OLLAMA_MODELS="
    )
    audit = _RecordingAudit()
    service.update(
        config_version=manager.get_config_version(),
        items=[{"key": "LLM_OLLAMA_MODELS", "value": "llama3.2:1b"}],
        reload_now=False,
        actor="local_model_center",
        security_audit=audit,
    )
    attempts = _write_events(audit, phase="attempt")
    assert attempts[0]["metadata"]["source"] == "local_model"
    assert manager.read_config_map()["LLM_OLLAMA_MODELS"] == "llama3.2:1b"

    blocked = _RecordingAudit(fail_attempt=True)
    current = manager.get_config_version()
    with pytest.raises(SecurityAuditUnavailable):
        service.update(
            config_version=current,
            items=[{"key": "LLM_OLLAMA_MODELS", "value": "should-not-write"}],
            reload_now=False,
            actor="local_model_registration_restore",
            security_audit=blocked,
        )
    assert manager.read_config_map()["LLM_OLLAMA_MODELS"] == "llama3.2:1b"


def test_legacy_migration_emits_write_and_http_maps_503(
    tmp_path, monkeypatch
) -> None:
    service, manager, _env_path = _config_service(
        tmp_path,
        monkeypatch,
        "GEMINI_API_KEY=legacy-key",
        "GEMINI_MODEL=gemini-2.5-flash",
    )
    audit = _RecordingAudit()
    result = service.apply_legacy_channels_migration(
        config_version=manager.get_config_version(),
        security_audit=audit,
    )
    assert result["success"] is True
    attempts = _write_events(audit, phase="attempt")
    assert attempts[0]["metadata"]["source"] == "legacy_migration"

    blocked = _RecordingAudit(fail_attempt=True)
    with pytest.raises(HTTPException) as exc_info:
        system_config_endpoint.apply_legacy_channels_migration(
            payload=UpdateSystemConfigRequest(
                config_version=manager.get_config_version(),
                reload_now=False,
                items=[{"key": "LOG_LEVEL", "value": "INFO"}],
            ),
            service=service,
            security_audit=blocked,
        )
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["operation_completed"] is False


def test_http_put_does_not_double_emit(tmp_path, monkeypatch) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    repository = _SchemaValidatingAuditRepository()
    audit_service = SecurityAuditService(repository)
    app = _put_app(service, audit_service)
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/system/config",
            json={
                "config_version": manager.get_config_version(),
                "reload_now": False,
                "items": [{"key": "LOG_LEVEL", "value": "DEBUG"}],
            },
        )
    assert response.status_code == 200, response.text
    assert [event.phase for event in repository.events] == ["attempt", "completion"]
    assert {event.event_type for event in repository.events} == {
        SYSTEM_CONFIG_WRITE_EVENT_TYPE
    }


def test_import_nested_skip_emits_import_only(tmp_path, monkeypatch) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    monkeypatch.setenv("DSA_DESKTOP_MODE", "true")
    repository = _SchemaValidatingAuditRepository()
    audit_service = SecurityAuditService(repository)
    system_config_endpoint.import_system_config(
        request=ImportSystemConfigRequest(
            config_version=manager.get_config_version(),
            content="LOG_LEVEL=DEBUG\n",
            reload_now=False,
        ),
        request_obj=_request(),
        service=service,
        security_audit=audit_service,
    )
    types = [event.event_type for event in repository.events]
    assert SYSTEM_CONFIG_WRITE_EVENT_TYPE not in types
    assert types.count("system_config.import") == 2
    assert [event.phase for event in repository.events] == ["attempt", "completion"]


def test_durable_query_and_completion_failure_has_no_failed_row(
    tmp_path, monkeypatch, write_database
) -> None:
    del write_database
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")

    class _FailingCompletionStore:
        def __init__(self, inner: SecurityAuditRepository) -> None:
            self._inner = inner

        def append(self, event: SecurityAuditEventCreate) -> SecurityAuditEvent:
            if event.phase == "completion":
                raise RuntimeError("audit store down")
            return self._inner.append(event)

        def apply_retention(self, **kwargs):
            return self._inner.apply_retention(**kwargs)

        def apply_capacity(self, **kwargs):
            return self._inner.apply_capacity(**kwargs)

        def list_events(self, **kwargs):
            return self._inner.list_events(**kwargs)

    inner = SecurityAuditRepository()
    failing = SecurityAuditService(_FailingCompletionStore(inner))
    with pytest.raises(SystemConfigWriteAuditCompletionUnavailable):
        service.update(
            config_version=manager.get_config_version(),
            items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
            reload_now=False,
            security_audit=failing,
        )
    assert manager.read_config_map()["LOG_LEVEL"] == "DEBUG"
    page = SecurityAuditService(inner).list_events(
        event_type=SYSTEM_CONFIG_WRITE_EVENT_TYPE,
        page_size=20,
    )
    phases = [item.phase for item in page.items]
    assert "attempt" in phases
    assert "completion" not in phases
    assert all(item.reason_code != "config_update_failed" for item in page.items)


def test_validate_preview_and_simple_updates_do_not_emit(
    tmp_path, monkeypatch
) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    audit = _RecordingAudit()
    monkeypatch.setattr(
        "src.services.security_audit_service.get_security_audit_service",
        lambda: audit,
    )
    service.validate(
        items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
    )
    profiles = ConfigProfileService(
        system_config_service=service,
        ollama_probe=lambda: False,
        which_executable=lambda _name: None,
    )
    profiles.preview_preset_apply(
        "local-first",
        config_version=manager.get_config_version(),
    )
    service.apply_simple_updates([("CUSTOM_NOTE", "not-audited")])
    onboarding = OnboardingPlanService(
        system_config_service=service,
        state_path=tmp_path / "onboarding_state.json",
    )
    onboarding.get_first_run_readiness()
    assert _write_events(audit, phase="attempt") == []


def test_http_profile_apply_maps_attempt_503(tmp_path, monkeypatch) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    profiles = ConfigProfileService(
        system_config_service=service,
        ollama_probe=lambda: False,
        which_executable=lambda _name: None,
    )
    audit = _RecordingAudit(fail_attempt=True)
    app = FastAPI()
    app.include_router(config_profiles_endpoint.router, prefix="/api/v1/config-profiles")
    app.state.config_profile_service = profiles
    app.dependency_overrides[api_deps.require_security_audit_service] = lambda: audit
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/config-profiles/presets/local-first/apply",
            json={
                "config_version": manager.get_config_version(),
                "reload_now": False,
            },
        )
    assert response.status_code == 503
    assert response.json()["detail"]["operation_completed"] is False
    assert manager.read_config_map().get("LLM_OLLAMA_ENABLED") is None


def test_http_onboarding_apply_maps_attempt_503(tmp_path, monkeypatch) -> None:
    service, manager, _env_path = _config_service(tmp_path, monkeypatch, "LOG_LEVEL=INFO")
    audit = _RecordingAudit(fail_attempt=True)
    app = FastAPI()
    app.include_router(onboarding_endpoint.router, prefix="/api/v1/onboarding")
    app.dependency_overrides[api_deps.get_system_config_service] = lambda: service
    app.dependency_overrides[api_deps.require_security_audit_service] = lambda: audit
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/onboarding/apply",
            json={
                "profile": {
                    "schema_version": 1,
                    "experience_stage": "beginner",
                    "markets": ["cn"],
                    "goals": ["pre_post_market"],
                    "holdings": "none",
                    "interaction": "web",
                    "risk_tone": "balanced",
                    "infrastructure": "cloud_key",
                    "report_language": "en",
                },
                "config_version": manager.get_config_version(),
                "confirm": True,
            },
        )
    assert response.status_code == 503
    assert response.json()["detail"]["operation_completed"] is False
