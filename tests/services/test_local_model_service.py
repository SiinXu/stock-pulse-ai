"""Local model runtime, task, and configuration service contracts."""

from __future__ import annotations

import os
import threading
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import Mock, patch

import requests

from src.services.local_model_service import (
    LOCAL_MODEL_PULL_TASK_KIND,
    OLLAMA_MAX_EVENT_BYTES,
    OLLAMA_MAX_JSON_BYTES,
    LocalModelInUseError,
    LocalModelNotAllowedError,
    LocalModelNotInstalledError,
    LocalModelRuntimeRequestError,
    LocalModelRuntimeUnavailableError,
    LocalModelService,
    LocalModelValidationError,
    OllamaPullProgress,
    OllamaRuntimeClient,
    get_ollama_runtime_identity,
    normalize_local_model_id,
    normalize_ollama_base_url,
)
from src.services.task_queue import AnalysisTaskQueue, TaskInfo
from src.services.system_config_service import ConfigConflictError, ConfigValidationError
from src.task_execution import TaskCommand, TaskRunContext, TaskStatusEnum, deep_thaw
from tests._llm_env_isolation import strip_ambient_llm_env
from tests.system_config_service_test_support import _SystemConfigServiceTestCaseBase


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: bytes = b"{}",
        lines: Optional[List[bytes]] = None,
    ) -> None:
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.content = payload
        self._lines = lines or []
        self.closed = False

    def iter_lines(self):
        yield from self._lines

    def iter_content(self, chunk_size: int):
        content = b"\n".join(self._lines) if self._lines else self.content
        for offset in range(0, len(content), chunk_size):
            yield content[offset: offset + chunk_size]

    def close(self) -> None:
        self.closed = True


class _FakeTaskQueue:
    def __init__(self) -> None:
        self.pending: List[TaskInfo] = []
        self.tasks: Dict[str, TaskInfo] = {}
        self.run_task = None
        self.command: Optional[TaskCommand] = None
        self.progress_updates: List[tuple] = []
        self.cancel_requested = False
        self.cancel_after_progress = False

    def list_pending_tasks(self) -> List[TaskInfo]:
        return list(self.pending)

    def submit(self, command: TaskCommand) -> str:
        self.command = command
        metadata = deep_thaw(command.metadata)
        task_id = "local-model-pull-task"
        task = TaskInfo(
            task_id=task_id,
            trace_id=command.trace_id or task_id,
            kind=command.kind,
            stock_code=str(metadata["stock_code"]),
            stock_name=str(metadata["stock_name"]),
            report_type=str(metadata["report_type"]),
            message=str(metadata["message"]),
            failure_error_code=command.failure_error_code,
        )
        self.tasks[task.task_id] = task
        self.pending = [task]
        self.run_task = lambda: self._run_command(task)
        return task_id

    def _run_command(self, task: TaskInfo) -> Any:
        assert self.command is not None
        task.status = TaskStatusEnum.PROCESSING

        def update_progress(progress: int, message: Optional[str] = None) -> None:
            self.progress_updates.append(((task.task_id, progress, message), {}))
            task.progress = progress
            task.message = message
            if self.cancel_after_progress:
                self.cancel_requested = True

        context = TaskRunContext(
            task_id=task.task_id,
            trace_id=task.trace_id or task.task_id,
            command=self.command,
            update_progress=update_progress,
            append_flow_event=lambda _event: None,
            is_cancel_requested=lambda: self.cancel_requested,
            commit_final_result=lambda operation: (
                (False, None)
                if self.cancel_requested
                else (True, operation())
            ),
        )
        result = self.command.run(context)
        task.status = (
            TaskStatusEnum.CANCELLED
            if self.cancel_requested
            else TaskStatusEnum.COMPLETED
        )
        task.result = None if self.cancel_requested else result
        self.pending = []
        return result

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        return self.tasks.get(task_id)


class _FakeRuntimeClient:
    def __init__(self, installed: Optional[List[str]] = None) -> None:
        self.installed = list(installed) if installed is not None else [
            "qwen3:4b",
            "stockpulse/finance:latest",
        ]
        self.list_calls = 0
        self.pulled: List[str] = []
        self.deleted: List[str] = []

    def list_installed_models(self) -> List[str]:
        self.list_calls += 1
        return list(self.installed)

    def pull_model(self, model_id: str, *, on_progress, is_cancel_requested=None) -> None:
        if is_cancel_requested is not None and is_cancel_requested():
            return
        self.pulled.append(model_id)
        if model_id not in self.installed:
            self.installed.append(model_id)
        on_progress(OllamaPullProgress(percent=42, status="pulling manifest"))
        if is_cancel_requested is not None and is_cancel_requested():
            return
        on_progress(OllamaPullProgress(percent=99, status="success"))

    def delete_model(self, model_id: str) -> None:
        self.deleted.append(model_id)


class LocalModelRuntimeClientTestCase(_SystemConfigServiceTestCaseBase):
    def test_model_identifiers_accept_namespaces_but_reject_command_input(self) -> None:
        self.assertEqual(normalize_local_model_id("stockpulse/finance-q4:latest"), "stockpulse/finance-q4:latest")
        for candidate in ("", "../model", "qwen3:8b;rm", "model$(whoami)", "model name"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(LocalModelValidationError):
                    normalize_local_model_id(candidate)

    def test_base_url_is_server_origin_only(self) -> None:
        self.assertEqual(
            normalize_ollama_base_url("http://LOCALHOST:11434/v1/"),
            "http://localhost:11434",
        )
        self.assertEqual(normalize_ollama_base_url("http://LOCALHOST:80"), "http://localhost")
        self.assertEqual(normalize_ollama_base_url("https://LOCALHOST:443"), "https://localhost")
        self.assertEqual(
            get_ollama_runtime_identity("http://localhost:80"),
            get_ollama_runtime_identity("http://localhost"),
        )
        for candidate in (
            "file:///tmp/ollama",
            "http://user:secret@localhost:11434",
            "http://localhost:11434?target=internal",
        ):
            with self.subTest(candidate=candidate):
                with self.assertRaises(LocalModelValidationError):
                    normalize_ollama_base_url(candidate)

    def test_list_installed_models_uses_no_redirects_and_filters_invalid_names(self) -> None:
        response = _FakeResponse(
            payload=(
                b'{"models":['
                b'{"name":"qwen3:4b"},'
                b'{"model":"stockpulse/finance:latest"},'
                b'{"name":"bad model"}]}'
            )
        )
        session = Mock()
        session.request.return_value = response

        models = OllamaRuntimeClient("http://127.0.0.1:11434", session=session).list_installed_models()

        self.assertEqual(models, ["qwen3:4b", "stockpulse/finance:latest"])
        request = session.request.call_args
        self.assertEqual(request.args[:2], ("GET", "http://127.0.0.1:11434/api/tags"))
        self.assertFalse(request.kwargs["allow_redirects"])
        self.assertTrue(response.closed)

    def test_pull_emits_normalized_progress_and_requires_terminal_success(self) -> None:
        response = _FakeResponse(
            lines=[
                b'{"status":"pulling","total":100,"completed":25}',
                b'{"status":"success"}',
            ]
        )
        session = Mock()
        session.request.return_value = response
        progress: List[OllamaPullProgress] = []

        OllamaRuntimeClient("http://127.0.0.1:11434", session=session).pull_model(
            "qwen3:4b",
            on_progress=progress.append,
        )

        self.assertEqual(progress[0], OllamaPullProgress(percent=25, status="pulling"))
        self.assertEqual(progress[-1], OllamaPullProgress(percent=99, status="success"))
        request = session.request.call_args
        self.assertEqual(request.args[:2], ("POST", "http://127.0.0.1:11434/api/pull"))
        self.assertEqual(request.kwargs["json"], {"name": "qwen3:4b", "stream": True})
        self.assertTrue(response.closed)

    def test_pull_cancellation_before_request_does_not_contact_the_runtime(self) -> None:
        session = Mock()

        OllamaRuntimeClient(
            "http://127.0.0.1:11434",
            session=session,
        ).pull_model(
            "qwen3:4b",
            on_progress=lambda _progress: None,
            is_cancel_requested=lambda: True,
        )

        session.request.assert_not_called()

    def test_pull_cancellation_between_events_closes_the_stream(self) -> None:
        response = _FakeResponse(
            lines=[
                b'{"status":"pulling","total":100,"completed":25}',
                b'{"status":"success"}',
            ]
        )
        session = Mock()
        session.request.return_value = response
        progress: List[OllamaPullProgress] = []

        OllamaRuntimeClient(
            "http://127.0.0.1:11434",
            session=session,
        ).pull_model(
            "qwen3:4b",
            on_progress=progress.append,
            is_cancel_requested=lambda: bool(progress),
        )

        self.assertEqual(progress, [OllamaPullProgress(percent=25, status="pulling")])
        self.assertTrue(response.closed)

    def test_pull_absolute_deadline_applies_despite_continuous_progress(self) -> None:
        response = _FakeResponse(
            lines=[
                b'{"status":"pulling","total":100,"completed":25}',
                b'{"status":"success"}',
            ]
        )
        session = Mock()
        session.request.return_value = response
        now = 0.0

        def monotonic() -> float:
            nonlocal now
            now += 0.25
            return now

        with patch(
            "src.services.local_model_service.time.monotonic",
            side_effect=monotonic,
        ):
            with self.assertRaisesRegex(
                LocalModelRuntimeRequestError,
                "timed out",
            ):
                OllamaRuntimeClient(
                    "http://127.0.0.1:11434",
                    session=session,
                ).pull_model(
                    "qwen3:4b",
                    on_progress=lambda _progress: None,
                    timeout_seconds=1,
                )

        self.assertTrue(response.closed)

    def test_connection_failure_is_stable_and_does_not_echo_the_target(self) -> None:
        session = Mock()
        session.request.side_effect = requests.ConnectionError(
            "failed http://private-runtime.example:11434/api/tags"
        )

        with self.assertRaises(LocalModelRuntimeUnavailableError) as caught:
            OllamaRuntimeClient("http://private-runtime.example:11434", session=session).list_installed_models()

        self.assertNotIn("private-runtime", str(caught.exception))

    def test_interrupted_stream_is_mapped_to_a_stable_runtime_error(self) -> None:
        class _InterruptedResponse(_FakeResponse):
            def iter_content(self, chunk_size: int):
                yield b'{"models":['
                raise requests.ConnectionError(
                    "failed http://private-runtime.example:11434/api/tags"
                )

        response = _InterruptedResponse()
        session = Mock()
        session.request.return_value = response

        with self.assertRaises(LocalModelRuntimeUnavailableError) as caught:
            OllamaRuntimeClient(
                "http://private-runtime.example:11434",
                session=session,
            ).list_installed_models()

        self.assertNotIn("private-runtime", str(caught.exception))
        self.assertTrue(response.closed)

    def test_runtime_response_limits_are_enforced_before_json_or_ndjson_parsing(self) -> None:
        oversized_json = _FakeResponse(payload=b"x" * (OLLAMA_MAX_JSON_BYTES + 1))
        oversized_event = _FakeResponse(lines=[b" " * (OLLAMA_MAX_EVENT_BYTES + 1)])
        session = Mock()
        session.request.side_effect = [oversized_json, oversized_event]
        client = OllamaRuntimeClient("http://127.0.0.1:11434", session=session)

        with self.assertRaises(LocalModelRuntimeRequestError):
            client.list_installed_models()
        with self.assertRaises(LocalModelRuntimeRequestError):
            client.pull_model("qwen3:4b", on_progress=lambda _progress: None)

        self.assertTrue(oversized_json.closed)
        self.assertTrue(oversized_event.closed)


class LocalModelServiceTestCase(_SystemConfigServiceTestCaseBase):
    def setUp(self) -> None:
        super().setUp()
        self._saved_legacy_model_env = {
            key: os.environ.pop(key)
            for key in LocalModelService._LEGACY_PRIMARY_KEYS
            if key in os.environ
        }

    def tearDown(self) -> None:
        # Runtime activation intentionally refreshes os.environ. Remove keys
        # created by this test before the shared fixture restores its original
        # ambient snapshot, so later tests still treat their temp .env as the
        # only configuration source.
        strip_ambient_llm_env()
        for key in LocalModelService._LEGACY_PRIMARY_KEYS:
            os.environ.pop(key, None)
        super().tearDown()
        os.environ.update(self._saved_legacy_model_env)

    def _local_service(
        self,
        *,
        queue: Optional[_FakeTaskQueue] = None,
        client: Optional[_FakeRuntimeClient] = None,
        activation_handler: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
        imported_model_metadata: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
    ) -> tuple[LocalModelService, _FakeTaskQueue, _FakeRuntimeClient]:
        queue = queue or _FakeTaskQueue()
        client = client or _FakeRuntimeClient()
        service = LocalModelService(
            system_config_service=self.service,
            task_queue=queue,
            pullable_model_ids=lambda: {"qwen3:4b", "stockpulse/finance:latest"},
            client_factory=lambda _base_url: client,
            activation_handler=activation_handler,
            imported_model_metadata=imported_model_metadata,
        )
        return service, queue, client

    @staticmethod
    def _unregister(
        service: LocalModelService,
        model_id: str = "qwen3:4b",
    ) -> Dict[str, object]:
        config_version, values = service._config_snapshot()
        return service.unregister_model(
            model_id,
            expected_config_version=config_version,
            expected_runtime_identity=get_ollama_runtime_identity(
                service._base_url(values)
            ),
        )

    def test_auto_activation_creates_a_runnable_ollama_channel_when_no_primary_exists(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, _queue, _client = self._local_service()

        result = service.configure_model("qwen3:4b", assignment="auto")
        values = self.manager.read_config_map()

        self.assertTrue(result["selected_primary"])
        self.assertEqual(values["LLM_CONFIG_MODE"], "channels")
        self.assertEqual(values["GENERATION_BACKEND"], "litellm")
        self.assertEqual(values["LLM_CHANNELS"], "ollama")
        self.assertEqual(values["LLM_OLLAMA_PROVIDER"], "ollama")
        self.assertEqual(values["LLM_OLLAMA_PROTOCOL"], "ollama")
        self.assertEqual(values["LLM_OLLAMA_MODELS"], "qwen3:4b")
        self.assertEqual(values["LITELLM_MODEL"], "ollama/qwen3:4b")

    def test_assignment_rejects_a_catalog_model_that_is_not_installed(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, _queue, _client = self._local_service(
            client=_FakeRuntimeClient(installed=[]),
        )

        with self.assertRaises(LocalModelNotInstalledError):
            service.configure_model("qwen3:4b", assignment="primary")

        self.assertNotIn("LLM_OLLAMA_MODELS", self.manager.read_config_map())

    def test_installed_non_catalog_model_cannot_bypass_the_catalog_allowlist(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, _queue, _client = self._local_service(
            client=_FakeRuntimeClient(installed=["licensed/finance:q4"]),
        )

        with self.assertRaises(LocalModelNotAllowedError):
            service.configure_model("licensed/finance:q4", assignment="auto")

        self.assertNotIn("LLM_OLLAMA_MODELS", self.manager.read_config_map())

    def test_validated_imported_model_can_be_reassigned_but_not_deleted(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_OLLAMA_BASE_URL=http://127.0.0.1:11434",
        )
        seen_identities: List[str] = []

        def imported(runtime_identity: str) -> List[Dict[str, Any]]:
            seen_identities.append(runtime_identity)
            return [
                {
                    "model_id": "licensed/finance:q4",
                    "display_name": "\u00a0Licensed Finance Q4\u00a0",
                    "minimum_memory_gb": 16,
                    "license_id": "LicenseRef-Finance",
                }
            ]

        service, _queue, client = self._local_service(
            client=_FakeRuntimeClient(installed=["licensed/finance:q4"]),
            imported_model_metadata=imported,
        )

        result = service.configure_model("licensed/finance:q4", assignment="auto")
        configuration = service.get_configuration()

        self.assertTrue(result["selected_primary"])
        self.assertEqual(
            configuration["imported_models"][0]["display_name"],
            "\u00a0Licensed Finance Q4\u00a0",
        )
        self.assertTrue(seen_identities)
        self.assertTrue(all(len(identity) == 64 for identity in seen_identities))
        with self.assertRaises(LocalModelNotAllowedError):
            service.delete_model("licensed/finance:q4")
        self.assertEqual(client.deleted, [])

    def test_desktop_import_requires_snapshot_and_persists_metadata_before_config(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_OLLAMA_BASE_URL=http://127.0.0.1:11434",
        )
        service, _queue, client = self._local_service(
            client=_FakeRuntimeClient(installed=["licensed/finance:q4"]),
        )
        configuration = service.get_configuration()
        runtime_identity = get_ollama_runtime_identity("http://127.0.0.1:11434")
        events: List[str] = []

        with self.assertRaises(ConfigConflictError):
            service.activate_desktop_imported_model(
                "licensed/finance:q4",
                expected_config_version="stale",
                expected_runtime_identity=runtime_identity,
                persist_metadata=lambda: events.append("metadata"),
            )

        result = service.activate_desktop_imported_model(
            "licensed/finance:q4",
            expected_config_version=configuration["config_version"],
            expected_runtime_identity=runtime_identity,
            persist_metadata=lambda: events.append("metadata"),
        )

        self.assertEqual(events, ["metadata"])
        self.assertTrue(result["selected_primary"])
        self.assertEqual(client.list_calls, 1)

    def test_desktop_activation_rejects_changed_config_or_runtime_before_probe(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_OLLAMA_BASE_URL=http://127.0.0.1:11434",
        )
        service, _queue, client = self._local_service()
        configuration = service.get_configuration()

        with self.assertRaises(ConfigConflictError):
            service.activate_desktop_model(
                "qwen3:4b",
                expected_config_version="stale-version",
                expected_runtime_identity=get_ollama_runtime_identity(
                    "http://127.0.0.1:11434"
                ),
            )
        with self.assertRaises(ConfigConflictError):
            service.activate_desktop_model(
                "qwen3:4b",
                expected_config_version=configuration["config_version"],
                expected_runtime_identity=get_ollama_runtime_identity(
                    "http://127.0.0.1:22434"
                ),
            )

        self.assertEqual(client.list_calls, 0)
        self.assertNotIn("LLM_OLLAMA_MODELS", self.manager.read_config_map())

    def test_desktop_activation_uses_the_matching_server_owned_snapshot(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_OLLAMA_BASE_URL=http://127.0.0.1:11434",
        )
        service, _queue, client = self._local_service()
        configuration = service.get_configuration()

        result = service.activate_desktop_model(
            "qwen3:4b",
            expected_config_version=configuration["config_version"],
            expected_runtime_identity=get_ollama_runtime_identity(
                "http://127.0.0.1:11434"
            ),
        )

        self.assertTrue(result["selected_primary"])
        self.assertEqual(client.list_calls, 1)

    def test_auto_activation_preserves_an_existing_primary_model(self) -> None:
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
        service, _queue, _client = self._local_service()

        result = service.configure_model("qwen3:4b", assignment="auto")
        values = self.manager.read_config_map()

        self.assertFalse(result["selected_primary"])
        self.assertEqual(values["LITELLM_MODEL"], "openai/gpt-4o")
        self.assertEqual(values["LLM_CHANNELS"], "cloud,ollama")

    def test_auto_activation_preserves_an_implicit_channel_primary(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=channels",
            "LLM_CHANNELS=cloud",
            "LLM_CLOUD_PROVIDER=openai",
            "LLM_CLOUD_PROTOCOL=openai",
            "LLM_CLOUD_API_KEY=secret-value",
            "LLM_CLOUD_MODELS=gpt-4o",
            "LLM_CLOUD_ENABLED=true",
        )
        service, _queue, _client = self._local_service()

        result = service.configure_model("qwen3:4b", assignment="auto")
        values = self.manager.read_config_map()

        self.assertFalse(result["selected_primary"])
        self.assertNotIn("LITELLM_MODEL", values)
        self.assertEqual(values["LLM_CHANNELS"], "cloud,ollama")

    def test_auto_activation_preserves_an_existing_cli_backend(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "GENERATION_BACKEND=codex_cli",
        )
        service, _queue, _client = self._local_service()

        result = service.configure_model("qwen3:4b", assignment="auto")
        values = self.manager.read_config_map()

        self.assertFalse(result["selected_primary"])
        self.assertEqual(values["GENERATION_BACKEND"], "codex_cli")
        self.assertNotIn("LITELLM_MODEL", values)

    def test_auto_activation_ignores_inactive_legacy_credentials_in_channels_mode(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=channels",
            "GEMINI_API_KEY=inactive-secret-value",
        )
        service, _queue, _client = self._local_service()

        result = service.configure_model("qwen3:4b", assignment="auto")
        values = self.manager.read_config_map()

        self.assertTrue(result["selected_primary"])
        self.assertEqual(values["LLM_CONFIG_MODE"], "channels")
        self.assertEqual(values["LITELLM_MODEL"], "ollama/qwen3:4b")

    def test_auto_activation_pins_legacy_mode_instead_of_silently_superseding_it(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "GEMINI_API_KEY=secret-value",
        )
        service, _queue, _client = self._local_service()

        result = service.configure_model("qwen3:4b", assignment="auto")
        values = self.manager.read_config_map()

        self.assertFalse(result["selected_primary"])
        self.assertEqual(values["LLM_CONFIG_MODE"], "legacy")
        self.assertEqual(values["LLM_CHANNELS"], "ollama")
        self.assertNotIn("LITELLM_MODEL", values)

    def test_auto_activation_ignores_a_disabled_declared_channel(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=auto",
            "LLM_CHANNELS=stale",
            "LLM_STALE_ENABLED=false",
            "LLM_STALE_PROTOCOL=openai",
            "LLM_STALE_API_KEY=secret-value",
            "LLM_STALE_MODELS=gpt-4o",
            "GEMINI_API_KEY=secret-value",
        )
        service, _queue, _client = self._local_service()

        result = service.configure_model("qwen3:4b", assignment="auto")
        values = self.manager.read_config_map()

        self.assertFalse(result["selected_primary"])
        self.assertEqual(values["LLM_CONFIG_MODE"], "legacy")
        self.assertNotIn("LITELLM_MODEL", values)

    def test_unroutable_channel_cannot_displace_legacy_through_partial_update(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=auto",
            "LLM_CHANNELS=stale",
            "LLM_STALE_ENABLED=true",
            "LLM_STALE_PROTOCOL=openai",
            "LLM_STALE_MODELS=gpt-4o",
            "GEMINI_API_KEY=secret-value",
        )
        service, _queue, _client = self._local_service()

        with self.assertRaises(ConfigValidationError):
            service.configure_model("qwen3:4b", assignment="auto")

        values = self.manager.read_config_map()
        self.assertEqual(values["LLM_CONFIG_MODE"], "auto")
        self.assertEqual(values["LLM_CHANNELS"], "stale")
        self.assertNotIn("LITELLM_MODEL", values)
        self.assertNotIn("LLM_OLLAMA_MODELS", values)

    def test_agent_assignment_rejects_when_only_declared_channels_are_unroutable(self) -> None:
        for channel_values in (
            (
                "LLM_STALE_ENABLED=false",
                "LLM_STALE_API_KEY=secret-value",
            ),
            ("LLM_STALE_ENABLED=true",),
        ):
            with self.subTest(channel_values=channel_values):
                strip_ambient_llm_env()
                self._rewrite_env(
                    "ADMIN_AUTH_ENABLED=true",
                    "LLM_CONFIG_MODE=auto",
                    "LLM_CHANNELS=stale",
                    "LLM_STALE_PROTOCOL=openai",
                    "LLM_STALE_MODELS=gpt-4o",
                    "GEMINI_API_KEY=secret-value",
                    *channel_values,
                )
                service, _queue, _client = self._local_service()

                with self.assertRaises(LocalModelValidationError):
                    service.configure_model("qwen3:4b", assignment="agent")

                self.assertNotIn(
                    "AGENT_LITELLM_MODEL",
                    self.manager.read_config_map(),
                )

    def test_agent_assignment_rejects_an_incompatible_legacy_source(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "GEMINI_API_KEY=secret-value",
        )
        service, _queue, _client = self._local_service()

        with self.assertRaises(LocalModelValidationError):
            service.configure_model("qwen3:4b", assignment="agent")

        values = self.manager.read_config_map()
        self.assertNotIn("LLM_CONFIG_MODE", values)
        self.assertNotIn("AGENT_LITELLM_MODEL", values)
        self.assertNotIn("LITELLM_MODEL", values)

    def test_auto_activation_keeps_yaml_as_the_effective_primary_source(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LITELLM_CONFIG=/tmp/litellm.yaml",
        )
        service, _queue, _client = self._local_service()

        result = service.configure_model("qwen3:4b", assignment="auto")
        values = self.manager.read_config_map()

        self.assertFalse(result["selected_primary"])
        self.assertEqual(values["LITELLM_CONFIG"], "/tmp/litellm.yaml")
        self.assertEqual(values["LLM_CHANNELS"], "ollama")
        self.assertNotIn("LLM_CONFIG_MODE", values)
        self.assertNotIn("LITELLM_MODEL", values)

    def test_explicit_primary_and_agent_assignments_are_independent(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, _queue, _client = self._local_service()

        service.configure_model("qwen3:4b", assignment="primary")
        service.configure_model("stockpulse/finance:latest", assignment="agent")
        values = self.manager.read_config_map()

        self.assertEqual(values["LITELLM_MODEL"], "ollama/qwen3:4b")
        self.assertEqual(values["AGENT_LITELLM_MODEL"], "ollama/stockpulse/finance:latest")
        self.assertEqual(values["AGENT_GENERATION_BACKEND"], "litellm")
        self.assertEqual(values["LLM_OLLAMA_MODELS"], "qwen3:4b,stockpulse/finance:latest")

    def test_active_assignments_block_deletion_before_runtime_mutation(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, _queue, client = self._local_service()
        service.configure_model("qwen3:4b", assignment="primary")

        with self.assertRaises(LocalModelInUseError):
            service.delete_model("qwen3:4b")

        self.assertEqual(client.deleted, [])

    def test_active_model_refs_block_deletion_before_runtime_mutation(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CHANNELS=ollama",
            "LLM_OLLAMA_MODELS=qwen3:4b",
            "AGENT_LITELLM_MODEL=modelref:v1:local_ollama:ollama%2Fqwen3%3A4b",
        )
        service, _queue, client = self._local_service()

        with self.assertRaises(LocalModelInUseError):
            service.delete_model("qwen3:4b")

        self.assertEqual(client.deleted, [])

    def test_vision_and_fallback_refs_block_deletion_before_runtime_mutation(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=channels",
            "LLM_CHANNELS=ollama,cloud",
            "LLM_OLLAMA_PROVIDER=ollama",
            "LLM_OLLAMA_PROTOCOL=ollama",
            "LLM_OLLAMA_MODELS=qwen3:4b",
            "LLM_OLLAMA_ENABLED=true",
            "LLM_CLOUD_PROVIDER=openai",
            "LLM_CLOUD_PROTOCOL=openai",
            "LLM_CLOUD_API_KEY=secret-value",
            "LLM_CLOUD_MODELS=gpt-4o",
            "LLM_CLOUD_ENABLED=true",
            "LITELLM_MODEL=openai/gpt-4o",
            "VISION_MODEL=ollama/qwen3:4b",
            "LITELLM_FALLBACK_MODELS=ollama/qwen3:4b",
        )
        service, _queue, client = self._local_service()

        with self.assertRaises(LocalModelInUseError):
            service.delete_model("qwen3:4b")

        self.assertEqual(client.deleted, [])
        self.assertEqual(
            self.manager.read_config_map()["LLM_OLLAMA_MODELS"],
            "qwen3:4b",
        )

    def test_implicit_primary_blocks_deletion_before_runtime_mutation(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=channels",
            "LLM_CHANNELS=ollama",
            "LLM_OLLAMA_PROVIDER=ollama",
            "LLM_OLLAMA_PROTOCOL=ollama",
            "LLM_OLLAMA_MODELS=qwen3:4b",
            "LLM_OLLAMA_ENABLED=true",
        )
        service, _queue, client = self._local_service()

        with self.assertRaises(LocalModelInUseError):
            service.delete_model("qwen3:4b")

        self.assertEqual(client.deleted, [])

    def test_inactive_auto_mode_channel_does_not_block_deletion_when_yaml_wins(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=auto",
            "LITELLM_CONFIG=/tmp/litellm.yaml",
            "LLM_CHANNELS=ollama",
            "LLM_OLLAMA_PROVIDER=ollama",
            "LLM_OLLAMA_PROTOCOL=ollama",
            "LLM_OLLAMA_MODELS=qwen3:4b",
            "LLM_OLLAMA_ENABLED=true",
        )
        service, _queue, client = self._local_service()

        result = service.delete_model("qwen3:4b")

        self.assertTrue(result["deleted"])
        self.assertEqual(client.deleted, ["qwen3:4b"])

    def test_delete_restores_registration_when_runtime_mutation_fails(self) -> None:
        class _DeleteFailureClient(_FakeRuntimeClient):
            def delete_model(self, model_id: str) -> None:
                raise LocalModelRuntimeRequestError("runtime rejected delete")

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
        service, _queue, _client = self._local_service(
            client=_DeleteFailureClient(),
        )

        with self.assertRaises(LocalModelRuntimeRequestError):
            service.delete_model("qwen3:4b")

        values = self.manager.read_config_map()
        self.assertEqual(values["LLM_CHANNELS"], "cloud,ollama")
        self.assertEqual(values["LLM_OLLAMA_MODELS"], "qwen3:4b")

    def test_delete_does_not_restore_registration_when_weights_are_gone(self) -> None:
        class _AmbiguousDeleteClient(_FakeRuntimeClient):
            def delete_model(self, model_id: str) -> None:
                self.installed = [
                    item for item in self.installed if item.lower() != model_id.lower()
                ]
                raise LocalModelRuntimeRequestError("runtime disconnected after delete")

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
        service, _queue, _client = self._local_service(
            client=_AmbiguousDeleteClient(),
        )

        result = service.delete_model("qwen3:4b")

        values = self.manager.read_config_map()
        self.assertTrue(result["deleted"])
        self.assertEqual(values["LLM_CHANNELS"], "cloud")
        self.assertEqual(values["LLM_OLLAMA_MODELS"], "")

    def test_delete_recovery_preserves_concurrent_local_model_changes(self) -> None:
        test_case = self

        class _ConcurrentDeleteFailureClient(_FakeRuntimeClient):
            def delete_model(self, model_id: str) -> None:
                test_case._rewrite_env(
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
                    "LLM_OLLAMA_MODELS=stockpulse/finance:latest",
                    "LLM_OLLAMA_ENABLED=true",
                    "LITELLM_MODEL=openai/gpt-4o",
                )
                raise LocalModelRuntimeRequestError("runtime rejected delete")

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
        service, _queue, _client = self._local_service(
            client=_ConcurrentDeleteFailureClient(),
        )

        with self.assertRaises(LocalModelRuntimeRequestError):
            service.delete_model("qwen3:4b")

        values = self.manager.read_config_map()
        self.assertEqual(values["LLM_CHANNELS"], "cloud,ollama")
        self.assertEqual(
            values["LLM_OLLAMA_MODELS"],
            "stockpulse/finance:latest",
        )

    def test_pull_reuses_task_queue_progress_and_activates_after_success(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, queue, client = self._local_service()

        task = service.start_pull("qwen3:4b")
        result = queue.run_task()

        self.assertEqual(task.report_type, LOCAL_MODEL_PULL_TASK_KIND)
        self.assertEqual(client.pulled, ["qwen3:4b"])
        self.assertEqual(result["model_id"], "qwen3:4b")
        self.assertTrue(result["activated"])
        self.assertTrue(result["selected_primary"], service.get_configuration())
        self.assertEqual(queue.progress_updates[0][0][1], 42)
        self.assertIsInstance(queue.command, TaskCommand)
        self.assertEqual(self.manager.read_config_map()["LITELLM_MODEL"], "ollama/qwen3:4b")

    def test_pull_reuses_an_inflight_task_without_repeating_runtime_preflight(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, _queue, client = self._local_service()

        first = service.start_pull("qwen3:4b")
        second = service.start_pull("qwen3:4b")

        self.assertEqual(second.task_id, first.task_id)
        self.assertEqual(client.list_calls, 1)

    def test_pull_allows_unrelated_assignment_while_activation_keeps_snapshot_guard(self) -> None:
        pull_started = threading.Event()
        release_pull = threading.Event()
        assignment_finished = threading.Event()
        pull_result: Dict[str, object] = {}

        class _BlockingPullClient(_FakeRuntimeClient):
            def pull_model(self, model_id: str, *, on_progress, is_cancel_requested=None) -> None:
                pull_started.set()
                self.assert_released = release_pull.wait(timeout=5)
                super().pull_model(
                    model_id,
                    on_progress=on_progress,
                    is_cancel_requested=is_cancel_requested,
                )

        client = _BlockingPullClient()
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, queue, _client = self._local_service(client=client)
        service.start_pull("qwen3:4b")

        def run_pull() -> None:
            pull_result.update(queue.run_task())

        pull_thread = threading.Thread(target=run_pull)
        pull_thread.start()
        self.assertTrue(pull_started.wait(timeout=5))

        def assign() -> None:
            service.configure_model("stockpulse/finance:latest", assignment="agent")
            assignment_finished.set()

        assignment_thread = threading.Thread(target=assign)
        assignment_thread.start()
        assignment_thread.join(timeout=5)
        self.assertFalse(assignment_thread.is_alive())
        self.assertTrue(assignment_finished.is_set())

        release_pull.set()
        pull_thread.join(timeout=5)
        self.assertFalse(pull_thread.is_alive())
        self.assertTrue(client.assert_released)
        self.assertFalse(pull_result["activated"])

    def test_pull_cancellation_skips_activation_through_the_task_context(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        queue = _FakeTaskQueue()
        queue.cancel_after_progress = True
        service, _queue, client = self._local_service(queue=queue)

        service.start_pull("qwen3:4b")
        result = queue.run_task()

        self.assertEqual(client.pulled, ["qwen3:4b"])
        self.assertFalse(result["activated"])
        self.assertEqual(
            queue.tasks["local-model-pull-task"].status,
            TaskStatusEnum.CANCELLED,
        )
        self.assertNotIn("LLM_OLLAMA_MODELS", self.manager.read_config_map())

    def test_pull_rechecks_cancellation_after_activation_resolution(self) -> None:
        activation_started = threading.Event()
        release_activation = threading.Event()
        service_holder: Dict[str, LocalModelService] = {}

        def activate(
            normalized,
            *,
            config_version,
            values,
            base_url,
            is_cancel_requested,
            commit_final_result,
        ):
            activation_started.set()
            assert release_activation.wait(timeout=5)
            return service_holder["service"]._activate_completed_pull(
                normalized,
                config_version=config_version,
                values=values,
                base_url=base_url,
                is_cancel_requested=is_cancel_requested,
                commit_final_result=commit_final_result,
            )

        queue = _FakeTaskQueue()
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, _queue, client = self._local_service(
            queue=queue,
            activation_handler=activate,
        )
        service_holder["service"] = service
        service.start_pull("qwen3:4b")
        worker_result: Dict[str, Any] = {}

        worker = threading.Thread(
            target=lambda: worker_result.update(queue.run_task())
        )
        worker.start()
        self.assertTrue(activation_started.wait(timeout=5))
        queue.cancel_requested = True
        release_activation.set()
        worker.join(timeout=5)

        self.assertFalse(worker.is_alive())
        self.assertEqual(client.pulled, ["qwen3:4b"])
        self.assertFalse(worker_result["activated"])
        self.assertFalse(worker_result["selected_primary"])
        self.assertEqual(
            queue.tasks["local-model-pull-task"].status,
            TaskStatusEnum.CANCELLED,
        )
        self.assertNotIn("LLM_OLLAMA_MODELS", self.manager.read_config_map())

    def test_pull_final_config_commit_rejects_cancel_and_shutdown_winners(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")

        for winner, expected_status in (
            ("cancel", TaskStatusEnum.CANCELLED),
            ("shutdown", TaskStatusEnum.INTERRUPTED),
        ):
            with self.subTest(winner=winner):
                original_instance = AnalysisTaskQueue._instance
                AnalysisTaskQueue._instance = None
                queue = AnalysisTaskQueue(max_workers=1)
                commit_reached = threading.Event()
                release_commit = threading.Event()
                original_commit = queue._commit_final_result

                def delay_commit(task_id, operation):
                    commit_reached.set()
                    assert release_commit.wait(timeout=5)
                    return original_commit(task_id, operation)

                queue._commit_final_result = delay_commit
                service, _queue, client = self._local_service(queue=queue)
                try:
                    task = service.start_pull("qwen3:4b")
                    future = queue._futures[task.task_id]
                    self.assertTrue(commit_reached.wait(timeout=5))

                    if winner == "cancel":
                        self.assertEqual(
                            queue.cancel(task.task_id).status,
                            TaskStatusEnum.CANCEL_REQUESTED,
                        )
                    else:
                        queue.shutdown()

                    release_commit.set()
                    future.result(timeout=5)

                    self.assertEqual(client.pulled, ["qwen3:4b"])
                    self.assertEqual(
                        queue.get(task.task_id).status,
                        expected_status,
                    )
                    self.assertNotIn(
                        "LLM_OLLAMA_MODELS",
                        self.manager.read_config_map(),
                    )
                finally:
                    release_commit.set()
                    queue.shutdown()
                    AnalysisTaskQueue._instance = original_instance

    def test_registration_restore_requires_weights_on_the_original_runtime(self) -> None:
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
        service, _queue, client = self._local_service()
        unregistered = self._unregister(service)

        blocked_version, _values = service._config_snapshot()
        with self.assertRaises(ConfigConflictError):
            self.service.update(
                config_version=blocked_version,
                items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
                reload_now=False,
                validate_connectivity=False,
                actor="test",
            )

        restored = service.restore_registration(
            "qwen3:4b",
            recovery_token=unregistered["recovery_token"],
        )

        released_version, _values = service._config_snapshot()
        self.service.update(
            config_version=released_version,
            items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
            reload_now=False,
            validate_connectivity=False,
            actor="test",
        )

        self.assertIn("qwen3:4b", restored["registered_models"])
        self.assertEqual(self.manager.read_config_map()["LLM_CHANNELS"], "cloud,ollama")
        self.assertEqual(self.manager.read_config_map()["LOG_LEVEL"], "DEBUG")
        self.assertEqual(client.list_calls, 1)

    def test_successful_desktop_delete_finalization_revokes_recovery(self) -> None:
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
        service, _queue, _client = self._local_service()
        unregistered = self._unregister(service)

        finalized = service.finalize_unregistration(
            "qwen3:4b",
            recovery_token=unregistered["recovery_token"],
        )
        retried = service.finalize_unregistration(
            "qwen3:4b",
            recovery_token=unregistered["recovery_token"],
        )

        self.assertEqual(finalized["registered_models"], [])
        self.assertTrue(finalized["deleted"])
        self.assertTrue(retried["deleted"])
        with self.assertRaises(LocalModelValidationError):
            service.restore_registration(
                "qwen3:4b",
                recovery_token=unregistered["recovery_token"],
            )

    def test_pending_desktop_delete_blocks_re_registration_until_finalized(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=channels",
            "LLM_CHANNELS=cloud,ollama",
            "LLM_CLOUD_PROVIDER=openai",
            "LLM_CLOUD_PROTOCOL=openai",
            "LLM_CLOUD_API_KEY=secret-value",
            "LLM_CLOUD_MODELS=gpt-4o",
            "LLM_CLOUD_ENABLED=true",
            "LLM_OLLAMA_MODELS=qwen3:4b",
            "LITELLM_MODEL=openai/gpt-4o",
        )
        service, _queue, client = self._local_service()
        unregistered = self._unregister(service)

        with self.assertRaises(LocalModelInUseError):
            service.configure_model("qwen3:4b", assignment="auto")

        self.assertEqual(client.list_calls, 0)
        service.finalize_unregistration(
            "qwen3:4b",
            recovery_token=unregistered["recovery_token"],
        )

    def test_unregistered_desktop_delete_is_reserved_without_creating_registration(self) -> None:
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
        service, _queue, client = self._local_service()
        reserved = self._unregister(service)

        self.assertTrue(reserved["recovery_token"])
        self.assertFalse(reserved.get("deleted", False))
        with self.assertRaises(LocalModelInUseError):
            service.configure_model("qwen3:4b", assignment="auto")
        with self.assertRaises(LocalModelInUseError):
            service.start_pull("qwen3:4b")
        with self.assertRaises(LocalModelInUseError):
            service.delete_model("qwen3:4b")
        self.assertEqual(client.deleted, [])
        self.assertEqual(client.list_calls, 0)

        restored = service.restore_registration(
            "qwen3:4b",
            recovery_token=reserved["recovery_token"],
        )
        self.assertNotIn("qwen3:4b", restored["registered_models"])

        reserved_again = self._unregister(service)
        finalized = service.finalize_unregistration(
            "qwen3:4b",
            recovery_token=reserved_again["recovery_token"],
        )
        self.assertTrue(finalized["deleted"])
        service.start_pull("qwen3:4b")

    def test_pending_desktop_delete_blocks_config_assignment_until_finalized(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=channels",
            "LLM_CHANNELS=cloud,ollama",
            "LLM_CLOUD_PROVIDER=openai",
            "LLM_CLOUD_PROTOCOL=openai",
            "LLM_CLOUD_API_KEY=secret-value",
            "LLM_CLOUD_MODELS=gpt-4o",
            "LLM_CLOUD_ENABLED=true",
            "LLM_OLLAMA_MODELS=qwen3:4b",
            "LITELLM_MODEL=openai/gpt-4o",
        )
        service, _queue, _client = self._local_service()
        unregistered = self._unregister(service)
        current_version, _values = service._config_snapshot()

        with self.assertRaises(ConfigConflictError):
            self.service.update(
                config_version=current_version,
                items=[
                    {"key": "LLM_CHANNELS", "value": "cloud,ollama"},
                    {"key": "LLM_OLLAMA_MODELS", "value": "qwen3:4b"},
                    {"key": "LITELLM_MODEL", "value": "ollama/qwen3:4b"},
                ],
                reload_now=False,
                validate_connectivity=False,
                actor="test",
            )

        finalized = service.finalize_unregistration(
            "qwen3:4b",
            recovery_token=unregistered["recovery_token"],
        )
        released_version, _values = service._config_snapshot()
        self.service.update(
            config_version=released_version,
            items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
            reload_now=False,
            validate_connectivity=False,
            actor="test",
        )

        self.assertTrue(finalized["deleted"])
        self.assertEqual(self.manager.read_config_map()["LOG_LEVEL"], "DEBUG")

    def test_registration_restore_rejects_when_original_runtime_lacks_weights(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_CONFIG_MODE=channels",
            "LLM_CHANNELS=cloud,ollama",
            "LLM_CLOUD_PROVIDER=openai",
            "LLM_CLOUD_PROTOCOL=openai",
            "LLM_CLOUD_API_KEY=secret-value",
            "LLM_CLOUD_MODELS=gpt-4o",
            "LLM_CLOUD_ENABLED=true",
            "LLM_OLLAMA_MODELS=qwen3:4b",
            "LITELLM_MODEL=openai/gpt-4o",
        )
        service, _queue, client = self._local_service()
        unregistered = self._unregister(service)
        client.installed = []

        with self.assertRaises(LocalModelNotInstalledError):
            service.restore_registration(
                "qwen3:4b",
                recovery_token=unregistered["recovery_token"],
            )
        with self.assertRaises(LocalModelValidationError):
            service.restore_registration(
                "qwen3:4b",
                recovery_token=unregistered["recovery_token"],
            )

        self.assertEqual(self.manager.read_config_map()["LLM_OLLAMA_MODELS"], "")
        self.assertEqual(client.list_calls, 1)

    def test_registration_restore_probes_the_original_runtime_snapshot(self) -> None:
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
        client = _FakeRuntimeClient()
        probed_base_urls: List[str] = []

        def client_factory(base_url: str) -> _FakeRuntimeClient:
            probed_base_urls.append(base_url)
            return client

        service = LocalModelService(
            system_config_service=self.service,
            task_queue=_FakeTaskQueue(),
            pullable_model_ids=lambda: {"qwen3:4b"},
            client_factory=client_factory,
        )
        unregistered = self._unregister(service)

        with patch.object(
            service,
            "_base_url",
            return_value="http://127.0.0.1:11500",
        ):
            restored = service.restore_registration(
                "qwen3:4b",
                recovery_token=unregistered["recovery_token"],
            )

        self.assertEqual(probed_base_urls, ["http://127.0.0.1:11434"])
        self.assertEqual(client.list_calls, 1)
        self.assertIn("qwen3:4b", restored["registered_models"])

    def test_registration_restore_rejects_a_stale_config_version(self) -> None:
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
        service, _queue, _client = self._local_service()
        unregistered = self._unregister(service)
        self.manager.apply_updates(
            updates=[("LOG_LEVEL", "DEBUG")],
            sensitive_keys=set(),
            mask_token="******",
        )

        with self.assertRaises(ConfigConflictError):
            service.restore_registration(
                "qwen3:4b",
                recovery_token=unregistered["recovery_token"],
            )

        with self.assertRaises(LocalModelValidationError):
            service.restore_registration(
                "qwen3:4b",
                recovery_token=unregistered["recovery_token"],
            )

        released_version, _values = service._config_snapshot()
        self.service.update(
            config_version=released_version,
            items=[{"key": "LOG_LEVEL", "value": "INFO"}],
            reload_now=False,
            validate_connectivity=False,
            actor="test",
        )

        self.assertEqual(self.manager.read_config_map()["LLM_OLLAMA_MODELS"], "")
        self.assertEqual(self.manager.read_config_map()["LOG_LEVEL"], "INFO")

    def test_expired_desktop_delete_lease_allows_config_updates(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, _queue, _client = self._local_service()

        with patch(
            "src.services.local_model_service.time.monotonic",
            return_value=100.0,
        ):
            unregistered = self._unregister(service)

        with patch(
            "src.services.local_model_service.time.monotonic",
            return_value=401.0,
        ):
            current_version, _values = service._config_snapshot()
            self.service.update(
                config_version=current_version,
                items=[{"key": "LOG_LEVEL", "value": "DEBUG"}],
                reload_now=False,
                validate_connectivity=False,
                actor="test",
            )
            with self.assertRaises(LocalModelValidationError):
                service.finalize_unregistration(
                    "qwen3:4b",
                    recovery_token=unregistered["recovery_token"],
                )

        self.assertEqual(self.manager.read_config_map()["LOG_LEVEL"], "DEBUG")

    def test_registration_restore_rejects_an_unrelated_model_or_unissued_token(self) -> None:
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
        service, _queue, _client = self._local_service()
        unregistered = self._unregister(service)

        with self.assertRaises(LocalModelValidationError):
            service.restore_registration(
                "stockpulse/finance:latest",
                recovery_token=unregistered["recovery_token"],
            )
        with self.assertRaises(LocalModelValidationError):
            service.restore_registration(
                "qwen3:4b",
                recovery_token="never-issued",
            )
        service.finalize_unregistration(
            "qwen3:4b",
            recovery_token=unregistered["recovery_token"],
        )
        with self.assertRaises(LocalModelValidationError):
            service.restore_registration(
                "qwen3:4b",
                recovery_token=unregistered["recovery_token"],
            )

        self.assertEqual(self.manager.read_config_map()["LLM_OLLAMA_MODELS"], "")

    def test_registration_restore_rejects_an_expired_token(self) -> None:
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
        service, _queue, _client = self._local_service()

        with patch(
            "src.services.local_model_service.time.monotonic",
            return_value=100.0,
        ):
            unregistered = self._unregister(service)

        with patch(
            "src.services.local_model_service.time.monotonic",
            return_value=401.0,
        ):
            with self.assertRaises(LocalModelValidationError):
                service.restore_registration(
                    "qwen3:4b",
                    recovery_token=unregistered["recovery_token"],
                )

        self.assertEqual(self.manager.read_config_map()["LLM_OLLAMA_MODELS"], "")

    def test_delete_rejects_a_model_with_an_active_pull_before_runtime_mutation(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, _queue, client = self._local_service()
        service.start_pull("qwen3:4b")

        with self.assertRaises(LocalModelInUseError):
            service.delete_model("qwen3:4b")

        self.assertEqual(client.deleted, [])

    def test_unregister_rejects_a_model_with_an_active_pull(self) -> None:
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
        service, _queue, _client = self._local_service()
        service.start_pull("qwen3:4b")

        with self.assertRaises(LocalModelInUseError):
            self._unregister(service)

        self.assertEqual(
            self.manager.read_config_map()["LLM_OLLAMA_MODELS"],
            "qwen3:4b",
        )

    def test_pull_does_not_activate_against_a_changed_runtime_snapshot(self) -> None:
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_OLLAMA_BASE_URL=http://127.0.0.1:11434",
        )
        service, queue, client = self._local_service()

        service.start_pull("qwen3:4b")
        self._rewrite_env(
            "ADMIN_AUTH_ENABLED=true",
            "LLM_OLLAMA_BASE_URL=http://127.0.0.1:22434",
        )
        result = queue.run_task()

        self.assertEqual(client.pulled, ["qwen3:4b"])
        self.assertFalse(result["activated"])
        self.assertFalse(result["selected_primary"])
        self.assertNotIn("LLM_OLLAMA_MODELS", self.manager.read_config_map())

    def test_pull_keeps_unexpected_activation_errors_separate_from_download(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, queue, client = self._local_service()

        service.start_pull("qwen3:4b")
        service._activate_completed_pull = Mock(
            side_effect=RuntimeError("unexpected activation failure")
        )
        result = queue.run_task()

        self.assertEqual(client.pulled, ["qwen3:4b"])
        self.assertFalse(result["activated"])
        self.assertFalse(result["selected_primary"])

    def test_runtime_unavailable_status_is_actionable_without_raw_error(self) -> None:
        class _UnavailableClient:
            def list_installed_models(self):
                raise LocalModelRuntimeUnavailableError("private endpoint failed")

        service = LocalModelService(
            system_config_service=self.service,
            task_queue=_FakeTaskQueue(),
            pullable_model_ids=lambda: {"qwen3:4b"},
            client_factory=lambda _base_url: _UnavailableClient(),
        )

        self.assertEqual(
            service.get_runtime_status(),
            {
                "runtime": "ollama",
                "status": "unavailable",
                "installed_models": [],
                "manual_pull_supported": True,
            },
        )
