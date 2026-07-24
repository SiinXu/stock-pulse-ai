"""Local model API validation, progress, and error-boundary contracts."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
from fastapi import FastAPI

from api.app import create_app
from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import local_models
from src.services.local_model_service import (
    LocalModelInUseError,
    LocalModelNotInstalledError,
    LocalModelRuntimeUnavailableError,
    LocalModelService,
)
from src.services.task_queue import TaskInfo, TaskStatus
from tests.system_config_service_test_support import _SystemConfigServiceTestCaseBase


class _FakeLocalModelService:
    def __init__(self) -> None:
        self.start_pull = Mock(
            return_value=TaskInfo(
                task_id="pull-task-1",
                trace_id="pull-task-1",
                stock_code="qwen3:4b",
                status=TaskStatus.PENDING,
                report_type="local_model_pull",
            )
        )
        self.get_pull = Mock(
            return_value={
                "task_id": "pull-task-1",
                "status": "processing",
                "progress": 37,
                "model_id": "qwen3:4b",
                "error": None,
                "result": None,
            }
        )
        self.configure_model = Mock(
            return_value={
                "success": True,
                "config_version": "config-2",
                "registered_models": ["qwen3:4b"],
                "primary_model": "ollama/qwen3:4b",
                "agent_model": "",
                "model_id": "qwen3:4b",
                "selected_primary": True,
                "selected_agent": False,
                "updated_keys": ["LLM_CHANNELS", "LITELLM_MODEL"],
                "warnings": [],
                "applied_count": 2,
                "skipped_masked_count": 0,
                "reload_triggered": True,
            }
        )
        self.delete_model = Mock(return_value=self.configure_model.return_value | {"deleted": True})
        self.unregister_model = Mock(
            return_value=self.configure_model.return_value
            | {"deleted": True, "recovery_token": "registration-recovery-1"}
        )
        self.restore_registration = Mock(return_value=self.configure_model.return_value)

    def get_runtime_status(self):
        return {
            "runtime": "ollama",
            "status": "running",
            "installed_models": ["qwen3:4b"],
            "manual_pull_supported": False,
        }

    def get_configuration(self):
        return {
            "config_version": "config-1",
            "registered_models": ["qwen3:4b"],
            "primary_model": "ollama/qwen3:4b",
            "agent_model": "",
        }


def _build_app(service: _FakeLocalModelService) -> FastAPI:
    app = FastAPI()
    app.include_router(local_models.router, prefix="/api/v1/local-models")
    app.dependency_overrides[local_models.get_local_model_service] = lambda: service
    add_error_handlers(app)
    return app


async def _request(service: _FakeLocalModelService, method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=_build_app(service), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


class LocalModelApiIntegrationTestCase(_SystemConfigServiceTestCaseBase):
    """Exercise the API, service, and optimistic configuration boundary together."""

    def setUp(self) -> None:
        super().setUp()
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=channels",
            "LLM_CHANNELS=cloud,ollama",
            "LLM_CLOUD_PROVIDER=openai",
            "LLM_CLOUD_PROTOCOL=openai",
            "LLM_CLOUD_API_KEY=secret-value",
            "LLM_CLOUD_MODELS=gpt-4o",
            "LLM_CLOUD_ENABLED=true",
            "LLM_OLLAMA_PROVIDER=ollama",
            "LLM_OLLAMA_PROTOCOL=ollama",
            "LLM_OLLAMA_MODELS=qwen3:4b",
            "LLM_OLLAMA_ENABLED=true",
            "LITELLM_MODEL=openai/gpt-4o",
        )
        self.runtime_probe_count = 0

        test_case = self

        class _StoppedRuntime:
            def list_installed_models(self):
                test_case.runtime_probe_count += 1
                raise AssertionError("registration recovery must not probe Ollama")

        task_queue = Mock()
        task_queue.list_pending_tasks.return_value = []
        self.local_model_service = LocalModelService(
            system_config_service=self.service,
            task_queue=task_queue,
            pullable_model_ids=lambda: {"qwen3:4b"},
            client_factory=lambda _base_url: _StoppedRuntime(),
        )

    def test_unregister_then_restore_crosses_the_real_config_boundary_offline(self) -> None:
        unregistered = asyncio.run(
            _request(
                self.local_model_service,
                "DELETE",
                "/api/v1/local-models/registrations",
                json={"model_id": "qwen3:4b"},
            )
        )
        self.assertEqual(unregistered.status_code, 200, unregistered.text)

        restored = asyncio.run(
            _request(
                self.local_model_service,
                "POST",
                "/api/v1/local-models/registrations",
                json={
                    "model_id": "qwen3:4b",
                    "recovery_token": unregistered.json()["recovery_token"],
                },
            )
        )

        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["registered_models"], ["qwen3:4b"])
        self.assertEqual(self.runtime_probe_count, 0)


def test_runtime_response_combines_transport_and_configuration_state() -> None:
    response = asyncio.run(_request(_FakeLocalModelService(), "GET", "/api/v1/local-models/runtime"))

    assert response.status_code == 200
    assert response.json() == {
        "runtime": "ollama",
        "status": "running",
        "installed_models": ["qwen3:4b"],
        "manual_pull_supported": False,
        "configuration": {
            "config_version": "config-1",
            "registered_models": ["qwen3:4b"],
            "primary_model": "ollama/qwen3:4b",
            "agent_model": "",
        },
    }


def test_pull_request_forbids_caller_controlled_base_url_before_service_invocation() -> None:
    service = _FakeLocalModelService()

    response = asyncio.run(
        _request(
            service,
            "POST",
            "/api/v1/local-models/pulls",
            json={"model_id": "qwen3:4b", "base_url": "http://169.254.169.254/latest"},
        )
    )

    assert response.status_code == 422
    service.start_pull.assert_not_called()
    request_schema = _build_app(service).openapi()["components"]["schemas"]["LocalModelRequest"]
    assert "base_url" not in request_schema["properties"]
    assert request_schema["additionalProperties"] is False


def test_pull_acceptance_and_progress_use_the_existing_task_contract() -> None:
    service = _FakeLocalModelService()

    accepted = asyncio.run(
        _request(
            service,
            "POST",
            "/api/v1/local-models/pulls",
            json={"model_id": "qwen3:4b"},
        )
    )
    progress = asyncio.run(
        _request(service, "GET", "/api/v1/local-models/pulls/pull-task-1")
    )

    assert accepted.status_code == 202
    assert accepted.json()["task_id"] == "pull-task-1"
    assert progress.status_code == 200
    assert progress.json()["progress"] == 37
    service.start_pull.assert_called_once_with("qwen3:4b")


def test_pull_acceptance_serializes_a_reused_cancel_requested_task() -> None:
    service = _FakeLocalModelService()
    service.start_pull.return_value.status = TaskStatus.CANCEL_REQUESTED

    response = asyncio.run(
        _request(
            service,
            "POST",
            "/api/v1/local-models/pulls",
            json={"model_id": "qwen3:4b"},
        )
    )

    assert response.status_code == 202
    assert response.json()["status"] == "cancel_requested"


def test_unreachable_runtime_returns_manual_command_without_endpoint_details() -> None:
    service = _FakeLocalModelService()
    service.start_pull.side_effect = LocalModelRuntimeUnavailableError(
        "failed http://private-runtime.example:11434/api/tags"
    )

    response = asyncio.run(
        _request(
            service,
            "POST",
            "/api/v1/local-models/pulls",
            json={"model_id": "qwen3:4b"},
        )
    )

    assert response.status_code == 424
    assert response.json()["error"] == "local_model_runtime_unavailable"
    assert response.json()["params"]["manual_command"] == "ollama pull qwen3:4b"
    assert "private-runtime" not in response.text


def test_delete_rejects_an_active_model_before_mutation() -> None:
    service = _FakeLocalModelService()
    service.delete_model.side_effect = LocalModelInUseError("active")

    response = asyncio.run(
        _request(
            service,
            "DELETE",
            "/api/v1/local-models/models",
            json={"model_id": "qwen3:4b"},
        )
    )

    assert response.status_code == 409
    assert response.json()["error"] == "local_model_in_use"


def test_assignment_forbids_unknown_fields_and_keeps_primary_action_explicit() -> None:
    service = _FakeLocalModelService()
    response = asyncio.run(
        _request(
            service,
            "POST",
            "/api/v1/local-models/assignments",
            json={"model_id": "qwen3:4b", "assignment": "primary"},
        )
    )

    assert response.status_code == 200
    assert response.json()["selected_primary"] is True
    service.configure_model.assert_called_once_with("qwen3:4b", assignment="primary")


def test_assignment_rejects_a_catalog_model_missing_from_the_runtime() -> None:
    service = _FakeLocalModelService()
    service.configure_model.side_effect = LocalModelNotInstalledError("not installed")

    response = asyncio.run(
        _request(
            service,
            "POST",
            "/api/v1/local-models/assignments",
            json={"model_id": "qwen3:4b", "assignment": "agent"},
        )
    )

    assert response.status_code == 409
    assert response.json()["error"] == "local_model_not_installed"
    assert "manual_command" not in response.json().get("params", {})


def test_registration_restore_passes_the_server_issued_recovery_token() -> None:
    service = _FakeLocalModelService()

    response = asyncio.run(
        _request(
            service,
            "POST",
            "/api/v1/local-models/registrations",
            json={"model_id": "qwen3:4b", "recovery_token": "registration-recovery-1"},
        )
    )

    assert response.status_code == 200
    service.restore_registration.assert_called_once_with(
        "qwen3:4b",
        recovery_token="registration-recovery-1",
    )


def test_registration_restore_rejects_a_caller_supplied_config_version() -> None:
    service = _FakeLocalModelService()

    response = asyncio.run(
        _request(
            service,
            "POST",
            "/api/v1/local-models/registrations",
            json={"model_id": "qwen3:4b", "config_version": "current-version"},
        )
    )

    assert response.status_code == 422
    service.restore_registration.assert_not_called()


def test_static_openapi_contains_the_local_model_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    static = json.loads(
        (root / "docs/architecture/api_spec.json").read_text(encoding="utf-8")
    )
    runtime = create_app().openapi()

    for path in (
        "/api/v1/local-models/assignments",
        "/api/v1/local-models/configuration",
        "/api/v1/local-models/models",
        "/api/v1/local-models/pulls",
        "/api/v1/local-models/pulls/{task_id}",
        "/api/v1/local-models/registrations",
        "/api/v1/local-models/runtime",
    ):
        assert static["paths"][path] == runtime["paths"][path]
    for schema in (
        "LocalModelAssignmentRequest",
        "LocalModelConfigurationResponse",
        "LocalModelMutationResponse",
        "LocalModelPullAccepted",
        "LocalModelPullResult",
        "LocalModelPullStatus",
        "LocalModelRegistrationRestoreRequest",
        "LocalModelRequest",
        "LocalModelRuntimeResponse",
        "LocalModelUnregistrationResponse",
    ):
        assert static["components"]["schemas"][schema] == runtime["components"][
            "schemas"
        ][schema]
