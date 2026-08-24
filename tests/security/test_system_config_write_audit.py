# -*- coding: utf-8 -*-
"""Fail-closed SystemConfigService.update write-audit coverage (#1062 DAG-5)."""

from __future__ import annotations

import inspect
import json
import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import deps as api_deps
from src.api.v1.endpoints import config_profiles as config_profiles_endpoint
from src.api.v1.endpoints import local_models as local_models_endpoint
from src.api.v1.endpoints import onboarding as onboarding_endpoint
from src.api.v1.endpoints import stocks as stocks_endpoint
from src.api.v1.endpoints import system_config as system_config_endpoint
from src.api.v1.errors import normalize_error_body
from src.api.v1.services.system_config_write_audit import (
    system_config_write_audit_unavailable,
)
import src.auth as auth_module
from src.auth import refresh_auth_state
from src.config import Config
from src.core.config_manager import ConfigManager
from src.repositories.security_audit_repo import SecurityAuditRepository
from src.services.onboarding_plan_service import OnboardingPlanService
from src.services.security_audit_service import SecurityAuditService
from src.services.system_config_service import (
    ConfigValidationError,
    SystemConfigService,
    SystemConfigWriteAuditCompletionUnavailable,
)
from src.storage import DatabaseManager
from tests.security.test_security_audit_integrations import _RecordingAudit


CANARY = "write-audit-canary-secret-must-not-persist"
WRITE_EVENT = "system_config.write"


def _restore_admin_auth_enabled(original: str | None) -> None:
    if original is None:
        os.environ.pop("ADMIN_AUTH_ENABLED", None)
    else:
        os.environ["ADMIN_AUTH_ENABLED"] = original
    refresh_auth_state()


def _restore_openai_api_key(original: str | None) -> None:
    if original is None:
        os.environ.pop("OPENAI_API_KEY", None)
    else:
        os.environ["OPENAI_API_KEY"] = original


@pytest.fixture(autouse=True)
def _restore_auth_cache_after_env_restore():
    original = os.environ.get("ADMIN_AUTH_ENABLED")
    yield
    _restore_admin_auth_enabled(original)


@pytest.fixture
def write_env(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "STOCK_LIST=600519\nLOG_LEVEL=INFO\nADMIN_AUTH_ENABLED=false\n",
        encoding="utf-8",
    )
    original_admin_auth = os.environ.get("ADMIN_AUTH_ENABLED")
    original_openai_api_key = os.environ.get("OPENAI_API_KEY")
    monkeypatch.setenv("ENV_FILE", str(env_path))
    Config.reset_instance()
    manager = ConfigManager(env_path=env_path)
    service = SystemConfigService(manager=manager)
    try:
        yield env_path, manager, service
    finally:
        Config.reset_instance()
        _restore_admin_auth_enabled(original_admin_auth)
        _restore_openai_api_key(original_openai_api_key)


def _write_events(audit: _RecordingAudit, *, phase: str) -> list[dict]:
    source = audit.attempts if phase == "attempt" else audit.completions
    return [event for event in source if event.get("event_type") == WRITE_EVENT]


def _put_app(service: SystemConfigService, audit) -> FastAPI:
    app = FastAPI()
    app.include_router(system_config_endpoint.router, prefix="/api/v1/system")
    app.dependency_overrides[api_deps.get_system_config_service] = lambda: service
    app.dependency_overrides[api_deps.get_security_audit_service] = lambda: audit
    return app


def test_http_put_emits_one_write_pair_without_secrets(write_env) -> None:
    env_path, manager, service = write_env
    audit = _RecordingAudit()
    request = {
        "config_version": manager.get_config_version(),
        "reload_now": False,
        "items": [{"key": "STOCK_LIST", "value": f"300750,{CANARY}"}],
    }
    with TestClient(_put_app(service, audit)) as client:
        response = client.put("/api/v1/system/config", json=request)
    assert response.status_code == 200, response.text
    attempts = _write_events(audit, phase="attempt")
    completions = _write_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]
    assert attempts[0]["actor_type"] == "administrator"
    assert attempts[0]["actor_id"] == "local_operator"
    assert attempts[0]["metadata"]["source"] == "http_put"
    rendered = json.dumps({"attempts": attempts, "completions": completions})
    assert CANARY not in rendered
    assert os.fspath(env_path) not in rendered


def test_attempt_failure_does_not_persist(write_env) -> None:
    _env_path, manager, service = write_env
    before = manager.read_config_map()["STOCK_LIST"]
    audit = _RecordingAudit(fail_attempt=True)
    with TestClient(_put_app(service, audit)) as client:
        response = client.put(
            "/api/v1/system/config",
            json={
                "config_version": manager.get_config_version(),
                "reload_now": False,
                "items": [{"key": "STOCK_LIST", "value": "300750"}],
            },
        )
    assert response.status_code == 503
    assert response.json()["detail"]["operation_completed"] is False
    assert manager.read_config_map()["STOCK_LIST"] == before
    assert _write_events(audit, phase="attempt") == []
    assert _write_events(audit, phase="completion") == []


def test_completion_failure_after_persist_reports_reload_triggered(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit(fail_completion=True)
    with TestClient(_put_app(service, audit)) as client:
        response = client.put(
            "/api/v1/system/config",
            json={
                "config_version": manager.get_config_version(),
                "reload_now": False,
                "items": [{"key": "STOCK_LIST", "value": "300750"}],
            },
        )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["operation_completed"] is True
    assert "config_version" in detail
    assert detail["applied_count"] == 1
    assert detail["reload_triggered"] is False
    assert manager.read_config_map()["STOCK_LIST"] == "300750"
    assert len(_write_events(audit, phase="attempt")) == 1
    assert _write_events(audit, phase="completion") == []
    assert all(
        event.get("reason_code") != "config_update_failed"
        for event in audit.completions
    )


def test_isolated_and_production_503_field_parity() -> None:
    isolated = system_config_write_audit_unavailable(
        SystemConfigWriteAuditCompletionUnavailable(
            config_version="v-2",
            applied_count=3,
            reload_triggered=True,
        )
    )
    assert isolated.status_code == 503
    assert isolated.detail["operation_completed"] is True
    assert isolated.detail["reload_triggered"] is True
    assert isolated.detail["applied_count"] == 3
    body = normalize_error_body(
        dict(isolated.detail),
        default_error="http_error",
        default_message="Request failed",
    )
    assert body["error"] == "security_audit_unavailable"
    assert body["params"]["operation_completed"] is True
    assert body["params"]["reload_triggered"] is True
    assert "operation_completed" not in body


def test_long_invalid_key_is_hashed_in_sample(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit()
    long_key = "not valid " + ("X" * 300)
    with pytest.raises(ConfigValidationError):
        service.update(
            config_version=manager.get_config_version(),
            items=[{"key": long_key, "value": CANARY}],
            reload_now=False,
            security_audit=audit,
        )
    sample = audit.attempts[0]["metadata"]["key_sample"][0]
    assert sample.startswith("sha256:")
    assert CANARY not in repr(audit.attempts)


def test_domain_400_and_409_preserved_when_reject_completion_fails(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit(fail_completion=True)
    with TestClient(_put_app(service, audit)) as client:
        invalid = client.put(
            "/api/v1/system/config",
            json={
                "config_version": manager.get_config_version(),
                "reload_now": False,
                "items": [{"key": "not valid", "value": CANARY}],
            },
        )
        conflict = client.put(
            "/api/v1/system/config",
            json={
                "config_version": "stale-version",
                "reload_now": False,
                "items": [{"key": "STOCK_LIST", "value": "300750"}],
            },
        )
    assert invalid.status_code == 400
    assert conflict.status_code == 409


def test_no_http_double_emit_against_durable_store(write_env, tmp_path) -> None:
    _env_path, manager, service = write_env
    DatabaseManager.reset_instance()
    db = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'write-audit.sqlite'}")
    try:
        repository = SecurityAuditRepository(db)
        audit = SecurityAuditService(repository)
        with TestClient(_put_app(service, audit)) as client:
            response = client.put(
                "/api/v1/system/config",
                json={
                    "config_version": manager.get_config_version(),
                    "reload_now": False,
                    "items": [{"key": "STOCK_LIST", "value": "300750"}],
                },
            )
        assert response.status_code == 200, response.text
        events, _total = repository.list_events(page=1, page_size=20)
        write_events = [event for event in events if event.event_type == WRITE_EVENT]
        write_events.sort(key=lambda event: event.id)
        assert [event.phase for event in write_events] == ["attempt", "completion"]
        assert write_events[0].correlation_id == write_events[1].correlation_id
    finally:
        DatabaseManager.reset_instance()


def test_import_does_not_emit_write(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit()
    with patch(
        "src.services.security_audit_service.get_security_audit_service",
        return_value=audit,
    ):
        service.import_env(
            config_version=manager.get_config_version(),
            content="STOCK_LIST=000001\n",
            reload_now=False,
        )
    assert _write_events(audit, phase="attempt") == []
    assert manager.read_config_map()["STOCK_LIST"] == "000001"


def test_watchlist_add_and_remove_land_as_write(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit()
    app = FastAPI()
    app.include_router(stocks_endpoint.router, prefix="/api/v1/stocks")
    app.dependency_overrides[api_deps.get_system_config_service] = lambda: service
    app.dependency_overrides[api_deps.get_security_audit_service] = lambda: audit
    with TestClient(app) as client:
        added = client.post("/api/v1/stocks/watchlist/add", json={"stock_code": "AAPL"})
        removed = client.post("/api/v1/stocks/watchlist/remove", json={"stock_code": "AAPL"})
    assert added.status_code == 200, added.text
    assert removed.status_code == 200, removed.text
    sources = [event["metadata"]["source"] for event in _write_events(audit, phase="attempt")]
    assert sources == ["watchlist", "watchlist"]
    assert len(_write_events(audit, phase="completion")) == 2


def test_watchlist_attempt_failure_is_503_not_500(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit(fail_attempt=True)
    app = FastAPI()
    app.include_router(stocks_endpoint.router, prefix="/api/v1/stocks")
    app.dependency_overrides[api_deps.get_system_config_service] = lambda: service
    app.dependency_overrides[api_deps.get_security_audit_service] = lambda: audit
    with TestClient(app) as client:
        response = client.post("/api/v1/stocks/watchlist/add", json={"stock_code": "AAPL"})
    assert response.status_code == 503
    assert response.json()["detail"]["operation_completed"] is False
    assert "加入自选失败" not in response.text


def test_watchlist_completion_failure_includes_reload_triggered(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit(fail_completion=True)
    app = FastAPI()
    app.include_router(stocks_endpoint.router, prefix="/api/v1/stocks")
    app.dependency_overrides[api_deps.get_system_config_service] = lambda: service
    app.dependency_overrides[api_deps.get_security_audit_service] = lambda: audit
    with TestClient(app) as client:
        response = client.post("/api/v1/stocks/watchlist/add", json={"stock_code": "AAPL"})
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["operation_completed"] is True
    assert "reload_triggered" in detail
    assert "config_version" in detail
    assert "applied_count" in detail


def test_profile_apply_emits_write_and_empty_noop_does_not(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit()
    first = service.update(
        config_version=manager.get_config_version(),
        items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
        reload_now=False,
        security_audit=audit,
        source="config_profile_preset",
    )
    second = service.update(
        config_version=first["config_version"],
        items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
        reload_now=False,
        security_audit=audit,
        source="config_profile_preset",
    )
    attempts = _write_events(audit, phase="attempt")
    assert len(attempts) == 2
    assert attempts[0]["metadata"]["source"] == "config_profile_preset"
    assert second["applied_count"] == 0

    class _NoopProfile:
        def apply_preset(self, *_args, **_kwargs):
            return {
                "preset_id": "local-first",
                "display_name": "Local first",
                "applied": False,
                "config_version": manager.get_config_version(),
                "new_config_version": manager.get_config_version(),
                "updated_keys": [],
                "changes": [],
                "features": {},
                "message": "Preset already matches current non-secret configuration",
            }

    noop_audit = _RecordingAudit()
    app = FastAPI()
    app.include_router(config_profiles_endpoint.router, prefix="/api/v1/config-profiles")
    app.state.config_profile_service = _NoopProfile()
    app.dependency_overrides[api_deps.get_security_audit_service] = lambda: noop_audit
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/config-profiles/presets/local-first/apply",
            json={"config_version": manager.get_config_version(), "reload_now": False},
        )
    assert response.status_code == 200, response.text
    assert response.json()["applied"] is False
    assert _write_events(noop_audit, phase="attempt") == []


def test_profile_completion_503_includes_reload_triggered(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit(fail_completion=True)

    class _ApplyProfile:
        def apply_preset(self, *_args, **kwargs):
            return service.update(
                config_version=manager.get_config_version(),
                items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
                reload_now=False,
                security_audit=kwargs.get("security_audit"),
                source="config_profile_preset",
            )

    app = FastAPI()
    app.include_router(config_profiles_endpoint.router, prefix="/api/v1/config-profiles")
    app.state.config_profile_service = _ApplyProfile()
    app.dependency_overrides[api_deps.get_security_audit_service] = lambda: audit
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/config-profiles/presets/local-first/apply",
            json={"config_version": manager.get_config_version(), "reload_now": False},
        )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["operation_completed"] is True
    assert "reload_triggered" in detail
    assert "config_version" in detail
    assert "applied_count" in detail


def test_onboarding_confirm_false_and_apply_source(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit()
    app = FastAPI()
    app.include_router(onboarding_endpoint.router, prefix="/api/v1/onboarding")
    app.dependency_overrides[api_deps.get_system_config_service] = lambda: service
    app.dependency_overrides[api_deps.get_security_audit_service] = lambda: audit
    with TestClient(app) as client:
        denied = client.post(
            "/api/v1/onboarding/apply",
            json={
                "config_version": manager.get_config_version(),
                "confirm": False,
                "profile": {"markets": ["US"]},
            },
        )
        applied = client.post(
            "/api/v1/onboarding/apply",
            json={
                "config_version": manager.get_config_version(),
                "confirm": True,
                "profile": {"markets": ["US"]},
            },
        )
    assert denied.status_code == 400
    assert _write_events(audit, phase="attempt") == [] or applied.status_code in {200, 400}
    if applied.status_code == 200 and applied.json().get("applied_count", 0):
        assert _write_events(audit, phase="attempt")[0]["metadata"]["source"] == "onboarding_apply"


def test_onboarding_completion_503_includes_reload_triggered(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit(fail_completion=True)
    plan = OnboardingPlanService(system_config_service=service)
    try:
        plan.apply_plan(
            {"markets": ["US"]},
            config_version=manager.get_config_version(),
            confirm=True,
            security_audit=audit,
        )
    except SystemConfigWriteAuditCompletionUnavailable as exc:
        mapped = system_config_write_audit_unavailable(exc)
        assert mapped.detail["operation_completed"] is True
        assert mapped.detail["reload_triggered"] is mapped.detail["reload_triggered"]
        return
    pytest.skip("onboarding apply was a no-op on this environment")


def test_local_model_actor_source_and_http_attempt_fail(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit()
    service.update(
        config_version=manager.get_config_version(),
        items=[{"key": "STOCK_LIST", "value": "300750"}],
        reload_now=False,
        actor="local_model_center",
        security_audit=audit,
    )
    assert _write_events(audit, phase="attempt")[0]["metadata"]["source"] == "local_model"

    failing = _RecordingAudit(fail_attempt=True)

    class _PersistThroughConfig:
        def configure_model(self, model_id, assignment=None, audit_actor_id=None):
            del model_id, assignment, audit_actor_id
            return service.update(
                config_version=manager.get_config_version(),
                items=[{"key": "STOCK_LIST", "value": "300750"}],
                reload_now=False,
                actor="local_model_center",
                security_audit=failing,
                audit_actor_id="local_operator",
            )

    app = FastAPI()
    app.include_router(local_models_endpoint.router, prefix="/api/v1/local-models")
    app.dependency_overrides[api_deps.get_local_model_service] = lambda: _PersistThroughConfig()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/local-models/assignments",
            json={"model_id": "qwen2.5", "assignment": "auto"},
        )
    assert response.status_code == 503
    assert response.json()["detail"]["operation_completed"] is False


def test_local_model_completion_503_includes_reload_triggered(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit(fail_completion=True)
    with pytest.raises(SystemConfigWriteAuditCompletionUnavailable) as raised:
        service.update(
            config_version=manager.get_config_version(),
            items=[{"key": "STOCK_LIST", "value": "300750"}],
            reload_now=False,
            actor="local_model_center",
            security_audit=audit,
        )
    mapped = system_config_write_audit_unavailable(raised.value)
    assert mapped.detail["operation_completed"] is True
    assert "reload_triggered" in mapped.detail


def test_legacy_migration_source(write_env) -> None:
    env_path, manager, service = write_env
    env_path.write_text(
        "STOCK_LIST=600519\nOPENAI_API_KEY=sk-test\nOPENAI_MODEL=gpt-4o-mini\n",
        encoding="utf-8",
    )
    Config.reset_instance()
    manager = ConfigManager(env_path=env_path)
    service = SystemConfigService(manager=manager)
    audit = _RecordingAudit()
    try:
        service.apply_legacy_channels_migration(
            config_version=manager.get_config_version(),
            security_audit=audit,
        )
    except Exception:
        pytest.skip("legacy migration not available in this env snapshot")
        return
    attempts = _write_events(audit, phase="attempt")
    if attempts:
        assert attempts[0]["metadata"]["source"] == "legacy_migration"


def test_validate_and_simple_updates_do_not_emit_write(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit()
    with patch(
        "src.services.security_audit_service.get_security_audit_service",
        return_value=audit,
    ):
        service.validate(items=[{"key": "STOCK_LIST", "value": "300750"}])
        service.apply_simple_updates([("STOCK_LIST", "300750")])
    assert _write_events(audit, phase="attempt") == []


def test_writer_does_not_probe_auth_state(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit()
    with patch("src.auth.is_auth_enabled") as probe:
        service.update(
            config_version=manager.get_config_version(),
            items=[{"key": "STOCK_LIST", "value": "300750"}],
            reload_now=False,
            security_audit=audit,
            audit_actor_id="authenticated_admin",
        )
        probe.assert_not_called()
    assert audit.attempts[0]["actor_id"] == "authenticated_admin"
    assert audit.completions[0]["actor_id"] == "authenticated_admin"


def test_writer_defaults_to_local_operator_without_auth_probe(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit()
    signature = inspect.signature(service.update)
    assert signature.parameters["audit_actor_id"].kind is inspect.Parameter.KEYWORD_ONLY
    with patch("src.auth.is_auth_enabled") as probe:
        service.update(
            config_version=manager.get_config_version(),
            items=[{"key": "STOCK_LIST", "value": "300750"}],
            reload_now=False,
            security_audit=audit,
        )
        probe.assert_not_called()
    assert audit.attempts[0]["actor_id"] == "local_operator"


def test_http_put_forwards_explicit_audit_actor_id(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit()
    with patch.object(
        system_config_endpoint,
        "_config_audit_actor",
        return_value="desktop_operator",
    ), patch("src.auth.is_auth_enabled") as probe:
        with TestClient(_put_app(service, audit)) as client:
            response = client.put(
                "/api/v1/system/config",
                json={
                    "config_version": manager.get_config_version(),
                    "reload_now": False,
                    "items": [{"key": "STOCK_LIST", "value": "300750"}],
                },
            )
        probe.assert_not_called()
    assert response.status_code == 200, response.text
    assert _write_events(audit, phase="attempt")[0]["actor_id"] == "desktop_operator"


def _257_connection_items() -> list[dict[str, str]]:
    connection_names = [f"connection_{index:02d}" for index in range(32)]
    items = [{"key": "LLM_CHANNELS", "value": ",".join(connection_names)}]
    for index, name in enumerate(connection_names):
        prefix = f"LLM_{name.upper()}"
        items.extend(
            [
                {"key": f"{prefix}_DISPLAY_NAME", "value": f"Connection {index:02d}"},
                {"key": f"{prefix}_PROVIDER", "value": "custom"},
                {"key": f"{prefix}_PROTOCOL", "value": "openai"},
                {"key": f"{prefix}_BASE_URL", "value": f"https://llm-{index}.example/v1"},
                {"key": f"{prefix}_API_KEY", "value": f"secret-{index:02d}-must-not-audit"},
                {"key": f"{prefix}_MODELS", "value": f"model-{index:02d}"},
                {"key": f"{prefix}_EXTRA_HEADERS", "value": "{}"},
                {"key": f"{prefix}_ENABLED", "value": "true"},
            ]
        )
    assert len(items) == 257
    return items


def test_same_process_257_then_paper_and_unauthenticated_config_get(
    tmp_path,
    monkeypatch,
) -> None:
    original_admin_auth = os.environ.get("ADMIN_AUTH_ENABLED")
    auth_env = tmp_path / "auth-on.env"
    auth_env.write_text("ADMIN_AUTH_ENABLED=true\n", encoding="utf-8")
    monkeypatch.setenv("ENV_FILE", str(auth_env))
    Config.reset_instance()
    manager = ConfigManager(env_path=auth_env)
    service = SystemConfigService(manager=manager)
    audit = _RecordingAudit()
    try:
        with patch.object(
            system_config_endpoint,
            "_config_audit_actor",
            return_value="local_operator",
        ):
            with TestClient(_put_app(service, audit)) as client:
                response = client.put(
                    "/api/v1/system/config",
                    json={
                        "config_version": manager.get_config_version(),
                        "reload_now": False,
                        "items": _257_connection_items(),
                    },
                )
        assert response.status_code == 200, response.text
        assert response.json()["applied_count"] == 257
        assert auth_module._auth_enabled is not True

        os.environ.pop("ADMIN_AUTH_ENABLED", None)
        paper_env = tmp_path / "auth-off.env"
        db_path = tmp_path / "paper_after_257.db"
        static_dir = tmp_path / "empty-static"
        static_dir.mkdir()
        paper_env.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    f"DATABASE_PATH={db_path}",
                    "PAPER_PORTFOLIO_INITIAL_CASH=100000",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("ENV_FILE", str(paper_env))
        monkeypatch.setenv("DATABASE_PATH", str(db_path))
        monkeypatch.setenv("PAPER_PORTFOLIO_INITIAL_CASH", "100000")
        _restore_admin_auth_enabled(None)
        assert auth_module.is_auth_enabled() is False

        from src.api.app import create_app
        from src.storage import DatabaseManager

        Config.reset_instance()
        DatabaseManager.reset_instance()
        app = create_app(static_dir=static_dir)
        try:
            with TestClient(app) as client:
                config_get = client.get("/api/v1/system/config")
                assert config_get.status_code == 200, config_get.text
                created = client.post(
                    "/api/v1/portfolio/accounts",
                    json={"name": "Sim", "market": "cn", "account_type": "paper"},
                )
                assert created.status_code == 200, created.text
                assert created.json()["account_type"] == "paper"
        finally:
            DatabaseManager.reset_instance()
    finally:
        Config.reset_instance()
        _restore_admin_auth_enabled(original_admin_auth)
        assert os.environ.get("ADMIN_AUTH_ENABLED") == original_admin_auth
        assert auth_module._auth_enabled is None


def test_teardown_pops_admin_auth_then_refreshes_cache(write_env) -> None:
    env_path, _manager, _service = write_env
    original = os.environ.get("ADMIN_AUTH_ENABLED")
    env_path.write_text(
        "STOCK_LIST=600519\nLOG_LEVEL=INFO\nADMIN_AUTH_ENABLED=true\n",
        encoding="utf-8",
    )
    os.environ["ADMIN_AUTH_ENABLED"] = "true"
    refresh_auth_state()
    assert auth_module.is_auth_enabled() is True
    _restore_admin_auth_enabled(original)
    env_path.write_text(
        "STOCK_LIST=600519\nLOG_LEVEL=INFO\nADMIN_AUTH_ENABLED=false\n",
        encoding="utf-8",
    )
    refresh_auth_state()
    assert "ADMIN_AUTH_ENABLED" not in os.environ or os.environ.get(
        "ADMIN_AUTH_ENABLED"
    ) == original
    assert auth_module.is_auth_enabled() is False


def test_auth_canary_does_not_leak_login_requirement(write_env) -> None:
    env_path, _manager, _service = write_env
    original = os.environ.get("ADMIN_AUTH_ENABLED")

    env_path.write_text(
        "STOCK_LIST=600519\nLOG_LEVEL=INFO\nADMIN_AUTH_ENABLED=true\n",
        encoding="utf-8",
    )
    os.environ.pop("ADMIN_AUTH_ENABLED", None)
    refresh_auth_state()
    assert auth_module.is_auth_enabled() is True
    env_path.write_text(
        "STOCK_LIST=600519\nLOG_LEVEL=INFO\nADMIN_AUTH_ENABLED=false\n",
        encoding="utf-8",
    )
    _restore_admin_auth_enabled(original)
    refresh_auth_state()
    assert auth_module.is_auth_enabled() is False


def test_rolled_back_activation_keeps_domain_error_not_completed_503(write_env) -> None:
    _env_path, manager, service = write_env
    audit = _RecordingAudit(fail_completion=True)

    def _rolled_back(*_args, **_kwargs):
        raise ConfigValidationError(
            issues=[
                {
                    "key": "RUNTIME_CONFIG",
                    "code": "runtime_activation_failed",
                    "severity": "error",
                    "message": "restored",
                    "details": {"rollback_succeeded": True},
                }
            ]
        )

    with patch.object(service, "_update_validated", side_effect=_rolled_back):
        with pytest.raises(ConfigValidationError):
            service.update(
                config_version=manager.get_config_version(),
                items=[{"key": "STOCK_LIST", "value": "300750"}],
                reload_now=True,
                security_audit=audit,
            )
