"""Local model runtime, task, and configuration service contracts."""

from __future__ import annotations

import os
from typing import Dict, List, Optional
from unittest.mock import Mock

import requests

from src.services.local_model_service import (
    LOCAL_MODEL_PULL_TASK_KIND,
    OLLAMA_MAX_EVENT_BYTES,
    OLLAMA_MAX_JSON_BYTES,
    LocalModelInUseError,
    LocalModelNotInstalledError,
    LocalModelRuntimeRequestError,
    LocalModelRuntimeUnavailableError,
    LocalModelService,
    LocalModelValidationError,
    OllamaPullProgress,
    OllamaRuntimeClient,
    normalize_local_model_id,
    normalize_ollama_base_url,
)
from src.services.task_queue import TaskInfo
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
        self.progress_updates: List[tuple] = []

    def list_pending_tasks(self) -> List[TaskInfo]:
        return list(self.pending)

    def submit_background_task(self, run_task, **kwargs) -> TaskInfo:
        self.run_task = run_task
        task = TaskInfo(
            task_id=kwargs["task_id"],
            trace_id=kwargs["trace_id"],
            stock_code=kwargs["stock_code"],
            stock_name=kwargs["stock_name"],
            report_type=kwargs["report_type"],
            message=kwargs["message"],
        )
        self.tasks[task.task_id] = task
        self.pending = [task]
        return task

    def update_task_progress(self, *args, **kwargs) -> None:
        self.progress_updates.append((args, kwargs))

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

    def pull_model(self, model_id: str, *, on_progress) -> None:
        self.pulled.append(model_id)
        if model_id not in self.installed:
            self.installed.append(model_id)
        on_progress(OllamaPullProgress(percent=42, status="pulling manifest"))
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
    ) -> tuple[LocalModelService, _FakeTaskQueue, _FakeRuntimeClient]:
        queue = queue or _FakeTaskQueue()
        client = client or _FakeRuntimeClient()
        service = LocalModelService(
            system_config_service=self.service,
            task_queue=queue,
            pullable_model_ids=lambda: {"qwen3:4b", "stockpulse/finance:latest"},
            client_factory=lambda _base_url: client,
        )
        return service, queue, client

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

        with self.assertRaises(LocalModelRuntimeRequestError):
            service.delete_model("qwen3:4b")

        values = self.manager.read_config_map()
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
        self.assertEqual(
            queue.progress_updates[0][1]["message_code"],
            "local_model.pull.progress",
        )
        self.assertEqual(self.manager.read_config_map()["LITELLM_MODEL"], "ollama/qwen3:4b")

    def test_pull_reuses_an_inflight_task_without_repeating_runtime_preflight(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, _queue, client = self._local_service()

        first = service.start_pull("qwen3:4b")
        second = service.start_pull("qwen3:4b")

        self.assertEqual(second.task_id, first.task_id)
        self.assertEqual(client.list_calls, 1)

    def test_delete_rejects_a_model_with_an_active_pull_before_runtime_mutation(self) -> None:
        self._rewrite_env("ADMIN_AUTH_ENABLED=true")
        service, _queue, client = self._local_service()
        service.start_pull("qwen3:4b")

        with self.assertRaises(LocalModelInUseError):
            service.delete_model("qwen3:4b")

        self.assertEqual(client.deleted, [])

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
        service._configure_model_from_snapshot = Mock(
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
