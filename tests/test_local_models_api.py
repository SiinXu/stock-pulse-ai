"""Local model API validation, progress, and error-boundary contracts."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from api import app as api_app
from api.app import create_app
from api import deps as api_deps
from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import local_models
from src.services.local_model_service import (
    LOCAL_MODEL_PULL_TASK_KIND,
    LocalModelInUseError,
    LocalModelNotInstalledError,
    LocalModelRuntimeUnavailableError,
    LocalModelService,
    OllamaPullProgress,
    get_ollama_runtime_identity,
)
from src.services.task_queue import TaskInfo, TaskStatus
from src.services.system_config_service import SystemConfigService
from src.task_execution import TaskRunContext
from tests.system_config_service_test_support import _SystemConfigServiceTestCaseBase


DEFAULT_RUNTIME_IDENTITY = get_ollama_runtime_identity("http://127.0.0.1:11434")
ALTERNATE_RUNTIME_IDENTITY = get_ollama_runtime_identity("http://127.0.0.1:22434")


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
        self.activate_desktop_model = Mock(return_value=self.configure_model.return_value)
        self.unregister_model = Mock(
            return_value=self.configure_model.return_value
            | {"deleted": False, "recovery_token": "registration-recovery-1"}
        )
        self.restore_registration = Mock(return_value=self.configure_model.return_value)
        self.finalize_unregistration = Mock(
            return_value=self.configure_model.return_value | {"deleted": True}
        )

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


def test_local_model_dependency_constructs_one_stateful_service_under_concurrency() -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(system_config_service=Mock()),
        )
    )
    expected = object()
    callers = 8
    ready = threading.Barrier(callers)

    def construct(**_kwargs):
        time.sleep(0.02)
        return expected

    def resolve():
        ready.wait(timeout=2)
        return api_deps.get_local_model_service(request)

    with (
        patch.object(api_deps, "LocalModelService", side_effect=construct) as factory,
        patch.object(api_deps, "get_task_queue", return_value=Mock()),
        ThreadPoolExecutor(max_workers=callers) as executor,
    ):
        resolved = list(executor.map(lambda _index: resolve(), range(callers)))

    assert all(service is expected for service in resolved)
    factory.assert_called_once()


def test_local_model_dependency_shares_concurrent_system_config_service() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    expected_system_service = object()
    expected_local_service = object()
    callers = 8
    ready = threading.Barrier(callers)

    def construct_system_service():
        time.sleep(0.02)
        return expected_system_service

    def construct_local_service(**kwargs):
        assert kwargs["system_config_service"] is expected_system_service
        return expected_local_service

    def resolve(index: int):
        ready.wait(timeout=2)
        if index % 2:
            return api_deps.get_system_config_service(request)
        return api_deps.get_local_model_service(request)

    with (
        patch.object(
            api_deps,
            "SystemConfigService",
            side_effect=construct_system_service,
        ) as system_factory,
        patch.object(
            api_deps,
            "LocalModelService",
            side_effect=construct_local_service,
        ) as local_factory,
        patch.object(api_deps, "get_task_queue", return_value=Mock()),
        ThreadPoolExecutor(max_workers=callers) as executor,
    ):
        resolved = list(executor.map(resolve, range(callers)))

    assert all(
        service is (expected_system_service if index % 2 else expected_local_service)
        for index, service in enumerate(resolved)
    )
    assert request.app.state.system_config_service is expected_system_service
    assert request.app.state.local_model_service is expected_local_service
    system_factory.assert_called_once()
    local_factory.assert_called_once()


def test_app_lifespan_rebinds_local_model_configuration_authority() -> None:
    app = FastAPI()
    request = SimpleNamespace(app=app)
    system_services = [object(), object()]
    scheduler_services = [Mock(), Mock()]

    def construct_local_service(**kwargs):
        return SimpleNamespace(
            system_config_service=kwargs["system_config_service"],
            retire_pull_activation=Mock(),
        )

    async def exercise_two_lifespans():
        resolved = []
        for _index in range(2):
            async with api_app.app_lifespan(app):
                system_service = app.state.system_config_service
                local_service = api_deps.get_local_model_service(request)
                assert local_service.system_config_service is system_service
                resolved.append((system_service, local_service))
            assert not hasattr(app.state, "local_model_service")
            assert not hasattr(app.state, "system_config_service")
            assert api_deps._get_active_local_model_service(request) is None
        return resolved

    with (
        patch.object(
            api_app,
            "RuntimeSchedulerService",
            side_effect=scheduler_services,
        ),
        patch.object(
            api_app,
            "SystemConfigService",
            side_effect=system_services,
        ),
        patch.object(api_app, "_schedule_stock_index_background_refresh"),
        patch.object(
            api_deps,
            "LocalModelService",
            side_effect=construct_local_service,
        ),
        patch.object(api_deps, "get_task_queue", return_value=Mock()),
        patch("src.config.get_config", return_value=SimpleNamespace(schedule_run_immediately=False)),
    ):
        first, second = asyncio.run(exercise_two_lifespans())

    assert first[0] is system_services[0]
    assert second[0] is system_services[1]
    assert first[1] is not second[1]
    first[1].retire_pull_activation.assert_called_once()
    second[1].retire_pull_activation.assert_called_once()
    scheduler_services[0].stop.assert_called_once()
    scheduler_services[1].stop.assert_called_once()


def test_local_model_lifespan_shutdown_waits_for_admitted_activation() -> None:
    app = FastAPI()
    request = SimpleNamespace(app=app)
    activation_started = threading.Event()
    release_activation = threading.Event()
    shutdown_waiting_for_lifecycle = threading.Event()
    shutdown_finished = threading.Event()
    activation_observed_active = []
    activation_result = {}

    def activate(*_args, **_kwargs):
        activation_started.set()
        assert release_activation.wait(timeout=5)
        activation_observed_active.append(app.state.local_model_services_active)
        return {"selected_primary": False}

    service = SimpleNamespace(
        _activate_completed_pull=Mock(side_effect=activate),
        retire_pull_activation=Mock(),
    )
    app.state.local_model_services_active = True
    app.state.local_model_service = service
    app.state.system_config_service = object()

    class _ObservedLifecycleLock:
        def __init__(self) -> None:
            self.lock = threading.RLock()

        def __enter__(self):
            if threading.current_thread().name == "local-model-shutdown":
                shutdown_waiting_for_lifecycle.set()
            return self.lock.__enter__()

        def __exit__(self, *args):
            return self.lock.__exit__(*args)

    def run_activation() -> None:
        activation_result["value"] = api_deps._activate_active_local_model_pull(
            request,
            "qwen3:4b",
            config_version="config-1",
            values={},
            base_url="http://127.0.0.1:11434",
            is_cancel_requested=lambda: False,
        )

    def shutdown() -> None:
        api_deps.end_local_model_service_lifespan(app)
        shutdown_finished.set()

    with patch.object(
        api_deps,
        "_LOCAL_MODEL_SERVICE_INIT_LOCK",
        _ObservedLifecycleLock(),
    ):
        activation_thread = threading.Thread(target=run_activation)
        activation_thread.start()
        assert activation_started.wait(timeout=5)
        shutdown_thread = threading.Thread(
            target=shutdown,
            name="local-model-shutdown",
        )
        shutdown_thread.start()
        assert shutdown_waiting_for_lifecycle.wait(timeout=5)
        shutdown_thread.join(timeout=0.1)

        assert shutdown_thread.is_alive()
        assert app.state.local_model_services_active is True
        release_activation.set()
        activation_thread.join(timeout=5)
        shutdown_thread.join(timeout=5)

    assert not activation_thread.is_alive()
    assert not shutdown_thread.is_alive()
    assert shutdown_finished.is_set()
    assert activation_observed_active == [True]
    assert activation_result["value"] == {"selected_primary": False}
    assert app.state.local_model_services_active is False
    assert not hasattr(app.state, "local_model_service")
    assert not hasattr(app.state, "system_config_service")
    service.retire_pull_activation.assert_called_once()


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
        self.runtime_models = ["qwen3:4b"]

        test_case = self

        class _InstalledRuntime:
            def list_installed_models(self):
                test_case.runtime_probe_count += 1
                return list(test_case.runtime_models)

        task_queue = Mock()
        task_queue.list_pending_tasks.return_value = []
        self.local_model_service = LocalModelService(
            system_config_service=self.service,
            task_queue=task_queue,
            pullable_model_ids=lambda: {"qwen3:4b"},
            client_factory=lambda _base_url: _InstalledRuntime(),
        )

    def test_stale_pull_worker_uses_the_current_lifespan_configuration_lease(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=channels",
            "LLM_CHANNELS=cloud",
            "LLM_CLOUD_PROVIDER=openai",
            "LLM_CLOUD_PROTOCOL=openai",
            "LLM_CLOUD_API_KEY=secret-value",
            "LLM_CLOUD_MODELS=gpt-4o",
            "LLM_CLOUD_ENABLED=true",
            "LITELLM_MODEL=openai/gpt-4o",
        )
        app = FastAPI()
        request = SimpleNamespace(app=app)
        pull_started = threading.Event()
        release_pull = threading.Event()
        command_holder = {}
        worker_result = {}
        pull_task = TaskInfo(
            task_id="lifespan-pull-task",
            trace_id="lifespan-pull-task",
            stock_code="qwen3:4b",
            status=TaskStatus.PENDING,
            report_type=LOCAL_MODEL_PULL_TASK_KIND,
        )

        class _BlockingRuntime:
            def list_installed_models(self):
                return ["qwen3:4b", "stockpulse/finance:latest"]

            def pull_model(self, model_id, *, on_progress, is_cancel_requested=None):
                self.model_id = model_id
                pull_started.set()
                assert release_pull.wait(timeout=5)
                on_progress(OllamaPullProgress(percent=99, status="success"))

        runtime = _BlockingRuntime()
        queue = Mock()
        queue.list_pending_tasks.side_effect = lambda: (
            [pull_task]
            if "command" in command_holder and pull_task.status in {
                TaskStatus.PENDING,
                TaskStatus.PROCESSING,
                TaskStatus.CANCEL_REQUESTED,
            }
            else []
        )
        queue.get_task.side_effect = lambda task_id: (
            pull_task if task_id == pull_task.task_id else None
        )

        def submit(command):
            command_holder["command"] = command
            return pull_task.task_id

        queue.submit.side_effect = submit

        def construct_local_service(**kwargs):
            return LocalModelService(
                **kwargs,
                client_factory=lambda _base_url: runtime,
            )

        system_services = [
            SystemConfigService(manager=self.manager),
            SystemConfigService(manager=self.manager),
        ]
        scheduler_services = [Mock(), Mock()]

        def run_pull_worker() -> None:
            command = command_holder["command"]
            pull_task.status = TaskStatus.PROCESSING
            context = TaskRunContext(
                task_id=pull_task.task_id,
                trace_id=pull_task.trace_id,
                command=command,
                update_progress=lambda progress, _message=None: setattr(
                    pull_task, "progress", progress
                ),
                append_flow_event=lambda _event: None,
                is_cancel_requested=lambda: False,
            )
            result = command.run(context)
            worker_result.update(result)
            pull_task.result = result
            pull_task.status = TaskStatus.COMPLETED

        async def exercise_two_lifespans():
            async with api_app.app_lifespan(app):
                service_a = api_deps.get_local_model_service(request)
                accepted = service_a.start_pull("qwen3:4b")
                assert accepted.task_id == pull_task.task_id
                worker = threading.Thread(target=run_pull_worker)
                worker.start()
                assert pull_started.wait(timeout=5)

            async with api_app.app_lifespan(app):
                service_b = api_deps.get_local_model_service(request)
                assert service_b is not service_a
                service_b._activate_completed_pull = Mock(
                    wraps=service_b._activate_completed_pull
                )
                assert service_b.get_pull(pull_task.task_id)["status"] == "processing"
                configuration = service_b.get_configuration()
                reservation = service_b.unregister_model(
                    "stockpulse/finance:latest",
                    expected_config_version=configuration["config_version"],
                    expected_runtime_identity=DEFAULT_RUNTIME_IDENTITY,
                )
                release_pull.set()
                worker.join(timeout=5)
                assert not worker.is_alive()
                service_b.finalize_unregistration(
                    "stockpulse/finance:latest",
                    recovery_token=reservation["recovery_token"],
                )
                return service_a, service_b

        with (
            patch.object(
                api_app,
                "RuntimeSchedulerService",
                side_effect=scheduler_services,
            ),
            patch.object(
                api_app,
                "SystemConfigService",
                side_effect=system_services,
            ),
            patch.object(api_app, "_schedule_stock_index_background_refresh"),
            patch.object(
                api_deps,
                "LocalModelService",
                side_effect=construct_local_service,
            ),
            patch.object(api_deps, "get_task_queue", return_value=queue),
            patch.object(
                api_deps,
                "get_pullable_local_model_ids",
                return_value={"qwen3:4b", "stockpulse/finance:latest"},
            ),
            patch(
                "src.config.get_config",
                return_value=SimpleNamespace(schedule_run_immediately=False),
            ),
        ):
            service_a, service_b = asyncio.run(exercise_two_lifespans())

        self.assertEqual(runtime.model_id, "qwen3:4b")
        self.assertFalse(worker_result["activated"])
        self.assertFalse(worker_result["selected_primary"])
        self.assertNotIn("LLM_OLLAMA_MODELS", self.manager.read_config_map())
        service_b._activate_completed_pull.assert_called_once()
        self.assertFalse(service_a._accepts_pull_activation)
        self.assertFalse(service_b._accepts_pull_activation)

    def test_unregister_then_restore_probes_weights_across_the_real_api_boundary(self) -> None:
        configuration = self.local_model_service.get_configuration()
        unregistered = asyncio.run(
            _request(
                self.local_model_service,
                "DELETE",
                "/api/v1/local-models/registrations",
                json={
                    "model_id": "qwen3:4b",
                    "expected_config_version": configuration["config_version"],
                    "expected_runtime_identity": DEFAULT_RUNTIME_IDENTITY,
                },
            )
        )
        self.assertEqual(unregistered.status_code, 200, unregistered.text)
        self.assertFalse(unregistered.json()["deleted"])

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
        self.assertEqual(self.runtime_probe_count, 1)

    def test_restore_rejects_missing_weights_across_the_real_api_boundary(self) -> None:
        configuration = self.local_model_service.get_configuration()
        unregistered = asyncio.run(
            _request(
                self.local_model_service,
                "DELETE",
                "/api/v1/local-models/registrations",
                json={
                    "model_id": "qwen3:4b",
                    "expected_config_version": configuration["config_version"],
                    "expected_runtime_identity": DEFAULT_RUNTIME_IDENTITY,
                },
            )
        )
        self.assertEqual(unregistered.status_code, 200, unregistered.text)
        self.runtime_models = []

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

        self.assertEqual(restored.status_code, 409, restored.text)
        self.assertEqual(
            self.local_model_service.get_configuration()["registered_models"],
            [],
        )
        self.assertEqual(self.runtime_probe_count, 1)

    def test_unregistered_model_receives_a_reservation_without_becoming_registered(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=channels",
            "LLM_CHANNELS=cloud",
            "LLM_CLOUD_PROVIDER=openai",
            "LLM_CLOUD_PROTOCOL=openai",
            "LLM_CLOUD_API_KEY=secret-value",
            "LLM_CLOUD_MODELS=gpt-4o",
            "LLM_CLOUD_ENABLED=true",
            "LITELLM_MODEL=openai/gpt-4o",
        )
        configuration = self.local_model_service.get_configuration()

        reserved = asyncio.run(
            _request(
                self.local_model_service,
                "DELETE",
                "/api/v1/local-models/registrations",
                json={
                    "model_id": "qwen3:4b",
                    "expected_config_version": configuration["config_version"],
                    "expected_runtime_identity": DEFAULT_RUNTIME_IDENTITY,
                },
            )
        )

        self.assertEqual(reserved.status_code, 200, reserved.text)
        self.assertTrue(reserved.json()["recovery_token"])
        self.assertEqual(reserved.json()["registered_models"], [])

        restored = asyncio.run(
            _request(
                self.local_model_service,
                "POST",
                "/api/v1/local-models/registrations",
                json={
                    "model_id": "qwen3:4b",
                    "recovery_token": reserved.json()["recovery_token"],
                },
            )
        )

        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["registered_models"], [])
        self.assertEqual(self.runtime_probe_count, 0)

    def test_unregister_rejects_a_changed_desktop_runtime_before_mutation(self) -> None:
        configuration = self.local_model_service.get_configuration()

        response = asyncio.run(
            _request(
                self.local_model_service,
                "DELETE",
                "/api/v1/local-models/registrations",
                json={
                    "model_id": "qwen3:4b",
                    "expected_config_version": configuration["config_version"],
                    "expected_runtime_identity": ALTERNATE_RUNTIME_IDENTITY,
                },
            )
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            self.local_model_service.get_configuration()["registered_models"],
            ["qwen3:4b"],
        )

    def test_finalize_revokes_recovery_across_the_real_api_boundary(self) -> None:
        configuration = self.local_model_service.get_configuration()
        unregistered = asyncio.run(
            _request(
                self.local_model_service,
                "DELETE",
                "/api/v1/local-models/registrations",
                json={
                    "model_id": "qwen3:4b",
                    "expected_config_version": configuration["config_version"],
                    "expected_runtime_identity": DEFAULT_RUNTIME_IDENTITY,
                },
            )
        )
        token = unregistered.json()["recovery_token"]

        finalized = asyncio.run(
            _request(
                self.local_model_service,
                "POST",
                "/api/v1/local-models/registration-recoveries/finalize",
                json={"model_id": "qwen3:4b", "recovery_token": token},
            )
        )
        retried = asyncio.run(
            _request(
                self.local_model_service,
                "POST",
                "/api/v1/local-models/registration-recoveries/finalize",
                json={"model_id": "qwen3:4b", "recovery_token": token},
            )
        )
        restored = asyncio.run(
            _request(
                self.local_model_service,
                "POST",
                "/api/v1/local-models/registrations",
                json={"model_id": "qwen3:4b", "recovery_token": token},
            )
        )

        self.assertEqual(finalized.status_code, 200, finalized.text)
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(finalized.json()["registered_models"], [])
        self.assertTrue(finalized.json()["deleted"])
        self.assertTrue(retried.json()["deleted"])
        self.assertEqual(restored.status_code, 400, restored.text)
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


def test_desktop_activation_passes_only_snapshot_assertions_to_the_service() -> None:
    service = _FakeLocalModelService()

    response = asyncio.run(
        _request(
            service,
            "POST",
            "/api/v1/local-models/desktop-activations",
            json={
                "model_id": "qwen3:4b",
                "expected_config_version": "config-1",
                "expected_runtime_identity": DEFAULT_RUNTIME_IDENTITY,
            },
        )
    )

    assert response.status_code == 200
    service.activate_desktop_model.assert_called_once_with(
        "qwen3:4b",
        expected_config_version="config-1",
        expected_runtime_identity=DEFAULT_RUNTIME_IDENTITY,
    )


def test_desktop_snapshot_requests_reject_caller_controlled_runtime_urls() -> None:
    for method, path in (
        ("POST", "/api/v1/local-models/desktop-activations"),
        ("DELETE", "/api/v1/local-models/registrations"),
    ):
        service = _FakeLocalModelService()
        response = asyncio.run(
            _request(
                service,
                method,
                path,
                json={
                    "model_id": "qwen3:4b",
                    "expected_config_version": "config-1",
                    "expected_runtime_identity": DEFAULT_RUNTIME_IDENTITY,
                    "expected_runtime_base_url": "http://169.254.169.254/latest",
                },
            )
        )

        assert response.status_code == 422
        service.activate_desktop_model.assert_not_called()
        service.unregister_model.assert_not_called()


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


def test_unregistration_finalization_revokes_the_server_issued_recovery_token() -> None:
    service = _FakeLocalModelService()

    response = asyncio.run(
        _request(
            service,
            "POST",
            "/api/v1/local-models/registration-recoveries/finalize",
            json={"model_id": "qwen3:4b", "recovery_token": "registration-recovery-1"},
        )
    )

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    service.finalize_unregistration.assert_called_once_with(
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
        "/api/v1/local-models/desktop-activations",
        "/api/v1/local-models/models",
        "/api/v1/local-models/pulls",
        "/api/v1/local-models/pulls/{task_id}",
        "/api/v1/local-models/registrations",
        "/api/v1/local-models/registration-recoveries/finalize",
        "/api/v1/local-models/runtime",
    ):
        assert static["paths"][path] == runtime["paths"][path]
    for schema in (
        "LocalModelAssignmentRequest",
        "LocalModelConfigurationResponse",
        "LocalModelDesktopActivationRequest",
        "LocalModelDesktopUnregistrationRequest",
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
